import os
import pytest
from pygdbmi.gdbmiparser import parse_response


class RecordedTransport:
    def __init__(self,*batches):
        self.batches = [[parse_response(line) for line in batch] for batch in batches]
        self.sent = []

    def write(self,command,**kwargs): self.sent.append(command)
    def get_gdb_response(self,**kwargs): return self.batches.pop(0) if self.batches else []


def backend_with(*batches):
    from unepic_trainer.backend import Backend
    from unepic_trainer.processes import identify
    backend = Backend(timeout=0.05)
    backend.identity = identify(os.getpid())
    backend._gdb = RecordedTransport(*batches)
    return backend


def test_contiguous_read_and_missing_bytes():
    from unepic_trainer.backend import BackendError
    backend = backend_with(['1^done,memory=[{begin="0x1000",contents="6400"},'
                            '{begin="0x1002",contents="0000"}]'])
    assert backend.read(0x1000,4) == bytes.fromhex('64000000')
    backend = backend_with(['1^done,memory=[{begin="0x1000",contents="6400"}]'])
    with pytest.raises(BackendError,match='Incomplete'): backend.read(0x1000,4)


def test_verified_write_and_gdb_error():
    from unepic_trainer.backend import BackendError
    backend = backend_with(['1^done'],['2^done,memory=[{begin="0x1000",contents="50"}]'])
    backend.write(0x1000,b'P')
    assert backend._gdb.sent[0] == '1-data-write-memory-bytes 0x1000 50'
    backend = backend_with(['1^done'],['2^done,memory=[{begin="0x1000",contents="00"}]'])
    with pytest.raises(BackendError,match='verification'): backend.write(0x1000,b'P')
    backend = backend_with(['1^error,msg="Cannot access memory"'])
    with pytest.raises(BackendError,match='Cannot access'): backend.read(0x1000,4)


def test_async_immediate_stop_is_not_overwritten_by_resume():
    backend = backend_with(['1^running','*running,thread-id="all"',
                            '*stopped,reason="signal-received",signal-name="SIGTRAP"'])
    backend.resume()
    assert not backend._running


def test_interrupt_waits_for_separate_stop_notification():
    backend = backend_with(['1^done'],['*stopped,reason="signal-received",signal-name="SIGINT"'])
    backend._running = True
    backend.pause()
    assert not backend._running


def test_timeout_and_detach_refuses_live_patch():
    from unepic_trainer.backend import BackendError
    backend = backend_with([])
    with pytest.raises(BackendError,match='timeout'): backend.read(0x1000,1)
    backend.active_patches[0x1000] = b'A'
    with pytest.raises(BackendError,match='Restore'): backend.detach()
