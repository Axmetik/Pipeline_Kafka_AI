"""Run the UNCHANGED MVP worker with process-local measurement adapters."""
import os
import time
BOOT_EPOCH = time.time_ns()
BOOT_MONO = time.perf_counter_ns()


def install(sink):
    import builtins
    from contextlib import contextmanager
    import json
    from sqlalchemy import event
    import integration.energy_worker as worker
    from integration.runtime import Runtime
    from ai.energy_forecaster import EnergyForecaster
    from anomaly.artifacts import Bundle
    import anomaly.artifacts as artifacts
    from sklearn.ensemble import IsolationForest
    from processing.energy_processor import EnergyProcessor
    from anomaly.features import FeatureStream
    from performance.telemetry import current, span, timed
    from performance.clock_domain import domain
    sink.emit('clock_domain',**domain())

    factory = worker.create_engine
    def engine(*args, **kwargs):
        result = factory(*args, **kwargs)
        result.dialect.do_commit = timed(result.dialect.do_commit, 'db_commit_ack')
        begin = result.begin
        @contextmanager
        def transaction():
            with span('transaction'):
                with begin() as connection:
                    yield connection
        result.begin = transaction
        @event.listens_for(result, 'before_cursor_execute')
        def before(conn, cursor, statement, parameters, context, many):
            context.perf_started = time.perf_counter_ns()
        @event.listens_for(result, 'after_cursor_execute')
        def after(conn, cursor, statement, parameters, context, many):
            row = current.get()
            if row is not None:
                row['sql_ns'] = row.get('sql_ns', 0)+time.perf_counter_ns()-context.perf_started
                row['sql_calls'] = row.get('sql_calls', 0)+1
        return result
    worker.create_engine = engine
    EnergyForecaster.predict = timed(EnergyForecaster.predict, 'hgb')
    Bundle.forecast = timed(Bundle.forecast, 'rf')
    IsolationForest.score_samples = timed(IsolationForest.score_samples, 'if')
    artifacts.ae_score = timed(artifacts.ae_score, 'ae')
    # These scopes are nested: primary_features includes the processor's own call;
    # anomaly_features is reported separately, never summed with its child span.
    EnergyProcessor.process = timed(EnergyProcessor.process, 'energy_features')
    FeatureStream.step = timed(FeatureStream.step, 'anomaly_features')
    Runtime.compute = timed(Runtime.compute, 'runtime')
    initialize = worker.Processor.__init__
    def init(self, *args, **kwargs):
        start = time.perf_counter_ns()
        initialize(self, *args, **kwargs)
        sink.emit('history_restored', duration_ns=time.perf_counter_ns()-start,
                  next_offset=self.runtime_next_offset)
    worker.Processor.__init__ = init
    poll = worker.KafkaConsumer.poll
    polled = {}
    def get(self, *args, **kwargs):
        result = poll(self, *args, **kwargs)
        instant = time.perf_counter_ns()
        for messages in result.values():
            for m in messages:
                polled[m.offset] = instant
        return result
    worker.KafkaConsumer.poll = get
    process = worker.Processor.process
    pending = {}
    first_message = True
    def invoke(self, offset, key, value):
        start = time.perf_counter_ns()
        row = dict(offset=offset, process_start_epoch_ns=time.time_ns())
        token = current.set(row)
        try:
            result = process(self, offset, key, value)
            end=time.perf_counter_ns()
            row.update(outcome=result['outcome'], process_ns=end-start,db_ack_mono_ns=end,
                       db_ack_epoch_ns=time.time_ns(), poll_to_db_ns=end-polled.pop(offset, start))
            pending.clear()
            pending.update(row)
            return result
        except Exception as exc:
            sink.emit('process_error', offset=offset, error=type(exc).__name__)
            raise
        finally:
            current.reset(token)
    worker.Processor.process = invoke
    commit = worker.KafkaConsumer.commit
    def acknowledge(self, *args, **kwargs):
        nonlocal first_message
        start = time.perf_counter_ns()
        result = commit(self, *args, **kwargs)
        duration=time.perf_counter_ns()-start
        if pending:
            if first_message and os.environ.get('PERF_CONTROL'):
                from pathlib import Path
                control=Path(os.environ['PERF_CONTROL'])/'worker-progress.json'
                temporary=control.with_suffix('.tmp')
                temporary.write_text(json.dumps({key:pending[key] for key in ('offset','db_ack_epoch_ns')}))
                temporary.replace(control)
            sink.emit('message', flush=first_message, **pending, kafka_commit_ack_ns=duration)
            first_message=False
            pending.clear()
        return result
    worker.KafkaConsumer.commit = acknowledge
    output = builtins.print
    def printing(*args, **kwargs):
        if args and isinstance(args[0], str) and args[0].startswith('{'):
            try:
                record = json.loads(args[0])
                if record.get('state') == 'ready':
                    sink.emit('ready', boot_epoch_ns=BOOT_EPOCH, boot_mono_ns=BOOT_MONO,
                              startup_ns=time.perf_counter_ns()-BOOT_MONO, **record)
                    polled.clear()  # recovery journal poll entries are not deliveries
            except ValueError:
                pass
        output(*args, **kwargs)
    worker.print = printing


def main():
    import signal
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    from performance.telemetry import Sink
    sink = Sink(os.environ['PERF_OUTPUT']+'/worker.jsonl')
    try:
        install(sink)
        from integration.energy_worker import main as run
        run()
    finally:
        sink.close()


if __name__ == '__main__':
    main()
