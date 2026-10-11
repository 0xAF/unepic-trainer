import os
from dataclasses import replace
import pytest


def remote_fixture(energy=False):
    from unepic_trainer.backend import Backend
    from unepic_trainer.processes import identify

    class KernelBoundary(Backend):
        def __init__(self):
            super().__init__()
            self.identity = identify(os.getpid())
            self._gdb = object()
            self.regs = {name:i for i,name in enumerate(
                ('rax','rdi','rsi','rdx','r10','r8','r9','rcx','r11','rip','eflags','orig_rax'))}
            self.regs['rip'] = 0x400000
            self.memory = b'ABC'
            self.profile = replace(self.profile,damage_store=0x600000)
            self.game_code = bytes.fromhex("f30f1193ec040000")
            self.energy_code = bytes.fromhex('f30f118308060000') if energy else None
            self.ips = [0x400000,0x500000]
            self.writes = []
            self.locking = 'off'
            self.unexpected = False

        def read(self,address,size):
            if address == self.profile.energy_store and self.energy_code is not None:
                return self.energy_code[:size]
            if address == 0x600000 and size in (3,8):
                return self.game_code[:size]
            if address != 0x400000:
                from unepic_trainer.backend import BackendError
                raise BackendError('Unmapped fixture instruction')
            assert address == 0x400000 and size == 3
            return self.memory

        def write(self,address,data):
            self.writes.append((address,data))
            assert len(data) == 3
            if address == self.profile.energy_store:
                self.energy_code = data+self.energy_code[len(data):]
            elif address == 0x600000:
                self.game_code = data + self.game_code[len(data):]
            else:
                assert address == 0x400000
                self.memory = data

        def evaluate(self,expr): return self.regs[expr[1:]]
        def set_register(self,name,value): self.regs[name] = value
        def instruction_pointers(self): return self.ips

        def _command(self,command):
            if command == '-gdb-show scheduler-locking': return {'value':self.locking}
            if command.startswith('-gdb-set scheduler-locking '):
                self.locking = command.rsplit(' ',1)[1]
            elif command == '-exec-continue':
                site = self.regs['rip']
                assert self.read(site,3) == bytes.fromhex('0f05cc')
                assert self.locking == 'on'
                assert (self.regs['rax'],self.regs['rdi'],self.regs['rsi'],
                        self.regs['rdx'],self.regs['r10'],self.regs['r8'],self.regs['r9']) == (
                        9,0x10000000,4096,7,0x100022,0xffffffffffffffff,0)
                self.regs['rax'] = 0x10000000
                self.regs['rip'] = site+3
                self._running = False
                self._stop_count += 1
                self._last_stop = {'signal-name':'SIGSEGV' if self.unexpected else 'SIGTRAP'}
            else: raise AssertionError(command)
            return {}

    return KernelBoundary()


@pytest.mark.parametrize('unexpected',[False,True])
def test_remote_syscall_restores_code_registers_scheduler(unexpected):
    from unepic_trainer.backend import BackendError
    backend = remote_fixture()
    backend.unexpected = unexpected
    registers = dict(backend.regs)
    if unexpected:
        with pytest.raises(BackendError):
            backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0))
    else:
        assert backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0)) == 0x10000000
    assert backend.regs == registers
    assert backend.memory == b'ABC'
    assert backend.locking == 'off'
    assert backend.unsafe is unexpected


def test_near_mapping_uses_free_page_and_signed_jump_range():
    from unepic_trainer.backend import find_near_gap, BackendError
    assert find_near_gap(0x400000,[(0x10000,0x401000)],4096) == 0x401000
    with pytest.raises(BackendError):
        find_near_gap(0x400000,[(0x10000,0x90000000)],4096)


@pytest.mark.parametrize('unexpected',[False,True])
def test_shared_thread_pc_uses_verified_fallback_and_restores_state(unexpected):
    from unepic_trainer.backend import BackendError
    backend = remote_fixture()
    backend.ips = [0x400000,0x400000,0x500000]
    backend.unexpected = unexpected
    registers = dict(backend.regs)
    if unexpected:
        with pytest.raises(BackendError,match='Unexpected syscall stop'):
            backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0))
    else:
        assert backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0)) == 0x10000000
    assert backend.regs == registers
    assert backend.memory == b'ABC'
    assert backend.game_code == bytes.fromhex('f30f1193ec040000')
    assert not backend.active_patches
    assert backend.locking == 'off'
    assert backend.unsafe is unexpected


@pytest.mark.parametrize('blocked',['thread','bytes','patch_before','patch_inside'])
def test_shared_pc_fallback_refuses_occupied_or_unverified_instruction(blocked):
    from unepic_trainer.backend import BackendError
    backend = remote_fixture()
    backend.ips = [0x400000,0x400000,0x500000]
    if blocked == 'thread': backend.ips.append(0x600002)
    elif blocked == 'bytes': backend.game_code = b'12345678'
    elif blocked == 'patch_before': backend.active_patches[0x5fffff] = b'ABCD'
    else: backend.active_patches[0x600001] = b'ABCD'
    registers = dict(backend.regs)
    patches = dict(backend.active_patches)
    with pytest.raises(BackendError):
        backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0))
    assert not backend.writes
    assert backend.regs == registers and backend.active_patches == patches
    assert not backend.unsafe


def test_second_protection_allocation_can_use_unoccupied_energy_instruction():
    backend = remote_fixture(energy=True)
    backend.ips = [0x400000,0x400000]
    backend.active_patches[backend.profile.damage_store] = backend.profile.original
    registers = dict(backend.regs)
    assert backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0)) == 0x10000000
    assert backend.writes[0][0] == backend.profile.energy_store
    assert backend.energy_code == bytes.fromhex('f30f118308060000')
    assert backend.regs == registers and not backend.unsafe
    assert backend.active_patches == {backend.profile.damage_store:backend.profile.original}


def test_third_allocation_can_use_progression_entry_with_protection_sites_occupied():
    backend = remote_fixture()
    backend.ips = [0x400000,0x400000]
    backend.active_patches = {site:original for site,original in (
        (backend.profile.damage_store,backend.profile.original),
        (backend.profile.energy_store,bytes.fromhex('f30f118308060000')),
        (backend.profile.energy_regen_store,bytes.fromhex('f30f118708060000')),
        (backend.profile.energy_cap_store,bytes.fromhex('f30f118f08060000')))}
    read,write = backend.read,backend.write
    code = [backend.profile.progression_original]
    def read_entry(address,size):
        return code[0][:size] if address == backend.profile.progression_store else read(address,size)
    def write_entry(address,data):
        if address == backend.profile.progression_store:
            backend.writes.append((address,data)); code[0] = data+code[0][len(data):]
        else: write(address,data)
    backend.read,backend.write = read_entry,write_entry
    registers,patches = dict(backend.regs),dict(backend.active_patches)
    assert backend.remote_syscall(9,(0x10000000,4096,7,0x100022,-1,0)) == 0x10000000
    assert backend.writes[0][0] == backend.profile.progression_store
    assert code[0] == backend.profile.progression_original and backend.regs == registers
    assert backend.active_patches == patches and not backend.unsafe
