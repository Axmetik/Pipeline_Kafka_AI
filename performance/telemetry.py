"""Bounded asynchronous JSONL telemetry, with explicit loss accounting."""
from contextvars import ContextVar
from contextlib import contextmanager
import json
from pathlib import Path
import queue
import threading
import time

current = ContextVar('performance_message', default=None)


class Sink:
    def __init__(self, path, capacity=20000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue(capacity)
        self.dropped = 0
        self.error = None
        self.closed = False
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def emit(self, kind, *, flush=False, **values):
        if self.closed:
            raise RuntimeError('Telemetry already closed')
        before=time.perf_counter_ns()
        epoch=time.time_ns()
        after=time.perf_counter_ns()
        row = dict(kind=kind, epoch_ns=epoch, mono_ns=(before+after)//2,
                   clock_read_uncertainty_ns=(after-before)//2, _flush=flush, **values)
        try:
            self.queue.put_nowait(row)
        except queue.Full:
            self.dropped += 1

    def _write(self):
        try:
            with self.path.open('a', buffering=65536) as out:
                deadline=time.monotonic()+1
                while True:
                    try:
                        row = self.queue.get(timeout=max(0,deadline-time.monotonic()))
                    except queue.Empty:
                        out.flush();deadline=time.monotonic()+1
                        continue
                    if row is None:
                        break
                    flush=row.pop('_flush',False)
                    out.write(json.dumps(row, allow_nan=False, separators=(',', ':')) + '\n')
                    if flush or time.monotonic()>=deadline:
                        out.flush()  # background thread, never fsync on the worker path
                        deadline=time.monotonic()+1
                out.write(json.dumps({'kind':'telemetry_end','dropped':self.dropped})+'\n')
        except Exception as exc:
            self.error = type(exc).__name__

    def close(self):
        if self.closed:
            return
        self.closed = True
        # Never deadlock if the writer has failed or storage is unavailable.
        while self.thread.is_alive():
            try:
                self.queue.put(None, timeout=.1)
                break
            except queue.Full:
                continue
        self.thread.join(timeout=10)
        if self.thread.is_alive() or self.error:
            raise RuntimeError('Incomplete telemetry: '+str(self.error or 'writer timeout'))


@contextmanager
def span(name):
    row = current.get()
    start = time.perf_counter_ns()
    try:
        yield
    finally:
        if row is not None:
            row[name+'_ns'] = row.get(name+'_ns', 0) + time.perf_counter_ns()-start
            row[name+'_calls'] = row.get(name+'_calls', 0)+1


def timed(function, name):
    def call(*args, **kwargs):
        with span(name):
            return function(*args, **kwargs)
    return call
