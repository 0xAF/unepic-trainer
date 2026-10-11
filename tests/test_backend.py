import struct
import pytest
from conftest import attach_or_skip


def test_real_read_write_resume_detach(target):
    from unepic_trainer.backend import Backend
    proc, data, identity, profile = target
    backend = Backend(profile)
    attach_or_skip(backend,identity)
    try:
        with backend.stopped():
            assert struct.unpack('<i',backend.read(data['value'],4))[0] == 100
            backend.write(data['value'],struct.pack('<i',80))
            assert struct.unpack('<i',backend.read(data['value'],4))[0] == 80
        proc.stdin.write('value\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '80'
    finally:
        backend.detach()
    assert proc.poll() is None


def test_unmapped_memory_error_and_process_exit(target):
    from unepic_trainer.backend import Backend, BackendError
    proc, data, identity, profile = target
    backend = Backend(profile)
    attach_or_skip(backend,identity)
    try:
        with backend.stopped():
            with pytest.raises(BackendError):
                backend.read(1,4)
        proc.kill(); proc.wait(timeout=5)
        with pytest.raises(BackendError,match='process'):
            backend.read(data['value'],4)
    finally:
        backend.detach()


def test_wrong_build_never_attaches(target):
    from unepic_trainer.backend import Backend, BackendError
    from unepic_trainer.profiles import Profile
    _, _, identity, _ = target
    backend = Backend(Profile())
    with pytest.raises(BackendError,match='build'):
        backend.attach(identity)
    assert backend.identity is None


def test_real_mmap_fallback_restores_code_and_waiting_thread(target):
    """Reserve the waiting PC so real GDB must use the verified game store."""
    from unepic_trainer.backend import Backend
    proc, _, identity, profile = target
    backend = Backend(profile)
    attach_or_skip(backend,identity)
    try:
        with backend.stopped():
            names = ('rax','rdi','rsi','rdx','r10','r8','r9','rcx','r11',
                     'rip','eflags','orig_rax')
            saved = {name:backend.evaluate('$'+name) for name in names}
            waiting_pc = saved['rip']
            waiting_code = backend.read(waiting_pc,3)
            # A reservation exercises the same fallback as a shared thread PC.
            backend.active_patches[waiting_pc] = waiting_code
            try:
                cave = backend.allocate_near(profile.damage_store,4096)
                assert backend.read(cave,16) == b'\0'*16
                assert backend.read(profile.damage_store,8) == profile.original
                assert backend.read(waiting_pc,3) == waiting_code
                assert {name:backend.evaluate('$'+name) for name in names} == saved
                assert backend.active_patches == {waiting_pc:waiting_code}
                assert not backend.unsafe
            finally:
                backend.active_patches.pop(waiting_pc,None)
        proc.stdin.write('damage\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '75 75'
    finally:
        backend.detach()
