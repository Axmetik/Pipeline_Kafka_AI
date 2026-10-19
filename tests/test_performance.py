"""Measurement math and isolation, independent of benchmark outcomes."""
from contextlib import redirect_stdout
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from performance.telemetry import Sink,current,span,timed
from performance.analysis import quantiles,summarize,read,clock_steps
from performance.database import validate


class PerformanceTests(unittest.TestCase):
    def test_linear_quantiles_and_empty(self):
        self.assertEqual(quantiles([])['p99'],None)
        self.assertEqual(quantiles([0,100]),dict(n=2,p50=50,p95=95,p99=99))

    def test_timing_preserves_result_and_exception(self):
        row={};token=current.set(row)
        try:
            self.assertEqual(timed(lambda x:x+1,'test')(3),4)
            def fail():raise ValueError('original')
            with self.assertRaisesRegex(ValueError,'original'):timed(fail,'test')()
            self.assertEqual(row['test_calls'],2)
            self.assertGreater(row['test_ns'],0)
        finally:current.reset(token)

    def test_span_is_inert_without_message_context(self):
        with span('test'):pass
        self.assertIsNone(current.get())

    def test_async_sink_flushes_and_accounts_for_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'telemetry.jsonl';sink=Sink(path,capacity=1)
            for i in range(1000):sink.emit('sample',index=i)
            sink.close();sink.close()
            rows=read(path)
            self.assertEqual(rows[-1]['kind'],'telemetry_end')
            self.assertEqual(len(rows)-1+sink.dropped,1000)
            with self.assertRaises(RuntimeError):sink.emit('late')

    def test_integrity_rejects_duplicates_and_offset_divergence(self):
        correct=dict(measurements=2,event_ids=2,measurement_ids=2,forecasts=4,scores=6,
                     receipts=2,errors=0,duplicate_deliveries=0,next_offset=2,
                     broker_next_offset=2,kafka_end_offset=2,offsets=[0,1,2])
        self.assertEqual(validate(correct,2),[])
        bad={**correct,'broker_next_offset':1,'duplicate_deliveries':1}
        self.assertEqual(len(validate(bad,2)),2)

    def test_summary_excludes_warmup_and_preserves_negative_latency(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'producer.jsonl').write_text('\n'.join(json.dumps(r) for r in [
                dict(kind='publication',phase='warmup',offset=0,ack_ns=999999,send_epoch_ns=10),
                dict(kind='publication',phase='measured',offset=1,ack_ns=1000000,send_epoch_ns=3000000)]))
            (root/'worker.jsonl').write_text(json.dumps(dict(kind='message',offset=1,process_ns=2000000,db_ack_epoch_ns=2000000)))
            result=summarize(root)
            self.assertEqual(result['publications'],1)
            self.assertEqual(result['latency_ms']['publication_ack']['p50'],1)
            self.assertEqual(result['latency_ms']['send_to_db_ack']['p50'],-1)

    def test_same_registered_inputs_for_all_runs(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/'configs/system-performance-v1.json').read_text())
        self.assertEqual(config['warmup'],300);self.assertEqual(config['measured'],3600)
        self.assertEqual(len(config['orders']),5)
        for block in config['orders']:self.assertEqual(set(block),{'slow','demo','max'})
        self.assertEqual(config['modes']['slow'],1)

    def test_clock_steps_account_for_bracketed_read_uncertainty(self):
        rows=[dict(epoch_ns=100_000_000,mono_ns=0,clock_read_uncertainty_ns=0),
              dict(epoch_ns=200_000_000,mono_ns=80_000_000,clock_read_uncertainty_ns=20_000_000),
              dict(epoch_ns=300_000_000,mono_ns=200_000_000,clock_read_uncertainty_ns=0)]
        self.assertEqual(clock_steps(rows),[0,0])
        rows[1]['clock_read_uncertainty_ns']=0
        self.assertEqual(clock_steps(rows),[20,20])

    def test_dashboard_skipped_states_are_censored_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)
            (path/'producer.jsonl').write_text(json.dumps(dict(kind='publication',phase='measured',offset=0,ack_ns=1,send_epoch_ns=1)))
            (path/'visibility.jsonl').write_text(json.dumps(dict(kind='visible',measurement_id='not-rendered',kafka_offset=0,available_lower_ns=1,available_upper_ns=2)))
            result=summarize(path)
            self.assertEqual(result['dashboard']['censored'],1)
            self.assertEqual(result['dashboard']['availability_to_dom_midpoint_ms']['n'],0)

    def test_failing_writer_does_not_deadlock_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            sink=Sink(directory,capacity=1)  # opening a directory as a file fails
            sink.thread.join(timeout=2)
            with self.assertRaisesRegex(RuntimeError,'Incomplete telemetry'):sink.close()


if __name__=='__main__':unittest.main()
