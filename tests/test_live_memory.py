"""Read actual process memory without sending any debugger commands."""
import ctypes
import os

import pytest

from test_transport import backend_with


def test_live_view_reads_changes_while_running_and_is_read_only():
    from unepic_trainer.backend import BackendError
    backend = backend_with()
    backend._running = True
    value = ctypes.c_uint32(123)
    with backend.live() as reader:
        assert int.from_bytes(reader.read(ctypes.addressof(value),4),'little') == 123
        value.value = 456
        assert int.from_bytes(reader.read(ctypes.addressof(value),4),'little') == 456
        with pytest.raises(BackendError,match='read-only'):
            reader.write(ctypes.addressof(value),b'\0'*4)
    assert backend._running and backend._gdb.sent == []
    assert value.value == 456
    with pytest.raises(BackendError,match='closed'):
        reader.read(ctypes.addressof(value),4)


def test_permission_denial_does_not_fall_back_to_interrupt(monkeypatch):
    from unepic_trainer import backend as module
    backend = backend_with(); backend._running = True
    def denied(*args): raise PermissionError('Denied by host policy')
    monkeypatch.setattr(module.os,'open',denied)
    with pytest.raises(module.LiveReadUnavailable,match='Refresh'):
        with backend.live(): pytest.fail('Must not yield a view')
    assert backend._running and backend._gdb.sent == []


def test_expired_identity_closes_live_descriptor(monkeypatch):
    from unepic_trainer import backend as module
    backend = backend_with()
    checks = iter((True,True,False))
    monkeypatch.setattr(module,'is_current',lambda identity: next(checks))
    with pytest.raises(module.BackendError,match='identity changed'):
        with backend.live() as reader:
            fd = reader._fd
    with pytest.raises(OSError): os.fstat(fd)
    assert backend._gdb.sent == []


def test_live_descriptor_closes_on_parser_failure():
    backend = backend_with()
    with pytest.raises(ValueError,match='Bad snapshot'):
        with backend.live() as reader:
            fd = reader._fd
            raise ValueError('Bad snapshot')
    with pytest.raises(OSError): os.fstat(fd)


@pytest.mark.parametrize('address,size',[(0,4),(-1,4),(1,0),(1,1024*1024+1)])
def test_invalid_live_range_is_rejected(address,size):
    from unepic_trainer.backend import BackendError
    backend = backend_with()
    with backend.live() as reader:
        with pytest.raises(BackendError,match='Invalid memory range'):
            reader.read(address,size)
    assert backend._gdb.sent == []


def test_incomplete_live_read_is_rejected(monkeypatch):
    from unepic_trainer import backend as module
    backend = backend_with()
    monkeypatch.setattr(module.os,'pread',lambda *args: b'x')
    with backend.live() as reader:
        with pytest.raises(module.BackendError,match='Incomplete'):
            reader.read(0x10000,4)


def test_unsafe_session_cannot_open_a_live_view():
    from unepic_trainer.backend import BackendError
    backend = backend_with(); backend.unsafe = True
    with pytest.raises(BackendError,match='Recovery required'):
        with backend.live(): pytest.fail('Must not yield a view')
    assert backend._gdb.sent == []


def test_live_reads_follow_a_running_native_fixture(target):
    from unepic_trainer.backend import Backend,LiveReadUnavailable
    from unepic_trainer.character import read_character
    from unepic_trainer.minions import read_minions
    from test_transport import RecordedTransport
    proc,data,identity,profile = target
    backend = Backend(profile)
    backend.identity = identity
    backend._gdb = RecordedTransport()
    backend._running = True
    try:
        with backend.live() as reader:
            assert read_character(reader).current_hp == 100
            pet, = read_minions(reader)
            assert (pet.current_hp,pet.energy) == (40,25)
            # The process must execute commands while the view is open.
            proc.stdin.write('pets\n'); proc.stdin.flush()
            assert proc.stdout.readline().strip() == '25 15 25 15'
            pet, = read_minions(reader)
            assert (pet.current_hp,pet.energy) == (25,15)
    except LiveReadUnavailable as error:
        pytest.skip('Host denies live memory access: '+str(error))
    assert backend._running and backend._gdb.sent == []
