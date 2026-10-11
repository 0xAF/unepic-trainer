import struct
import pytest
from test_character import Memory


class PatchMemory(Memory):
    def __init__(self):
        super().__init__()
        self.unsafe = False
        self.active_patches = {}
        self.ips = [0x500000]
        self.put_code(self.profile.damage_store,self.profile.original)
        self.put_code(self.profile.dot_damage_store,self.profile.dot_original)
        self.cave = 0x2000000
        self.fail_site_once = False
        self.fail_at = None

    def put_code(self,address,data):
        for i,b in enumerate(data): self.data[address+i] = b

    def instruction_pointers(self): return self.ips

    def allocate_near(self,address,size):
        self.put_code(self.cave,b'\0'*size)
        return self.cave

    def write(self,address,data):
        super().write(address,data)
        if address == self.fail_at or (address == self.profile.damage_store and self.fail_site_once):
            self.fail_at = None
            self.fail_site_once = False
            from unepic_trainer.backend import BackendError
            raise BackendError('Injected write failure after partial patch')


def test_enable_disable_and_partial_patch_recovery():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    mode = GodMode()
    mode.enable(memory); mode.enable(memory)
    assert mode.active
    assert memory.read(memory.profile.damage_store,8)[0] == 0xe9
    with pytest.raises(BackendError):
        # Restoration refuses an unexpected third-party patch.
        memory.write(memory.profile.damage_store,b'12345678')
        mode.disable(memory)
    assert mode.active and memory.active_patches
    memory.write(memory.profile.damage_store,mode.patch)
    mode.disable(memory); mode.disable(memory)
    assert memory.read(memory.profile.damage_store,8) == bytes.fromhex('f30f1193ec040000')
    assert not mode.active and not memory.active_patches
    memory.fail_site_once = True
    with pytest.raises(BackendError): mode.enable(memory)
    assert memory.read(memory.profile.damage_store,8) == bytes.fromhex('f30f1193ec040000')
    assert not mode.active and not memory.unsafe


def test_wrong_bytes_and_instruction_pointer_refused():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    memory.put_code(memory.profile.damage_store,b'\0'*8)
    with pytest.raises(BackendError): GodMode().enable(memory)
    assert memory.writes == []
    memory = PatchMemory()
    memory.ips = [memory.profile.damage_store+2]
    with pytest.raises(BackendError): GodMode().enable(memory)
    assert memory.writes == []


@pytest.mark.parametrize('protected',[True,False])
@pytest.mark.parametrize('store,xmm_number',[('f30f1193ec040000',2),('f30f119bec040000',3)])
def test_emulated_hook_preserves_registers_flags_and_red_zone(protected,store,xmm_number):
    from unepic_trainer.hooks import build_hook
    unicorn = pytest.importorskip('unicorn')
    from unicorn import x86_const as x
    uc = unicorn.Uc(unicorn.UC_ARCH_X86,unicorn.UC_MODE_64)
    for address in (0x100000,0x200000,0x300000,0x400000,0x500000):
        uc.mem_map(address,0x2000)
    entity,slot,cave,return_to,stack = 0x100000,0x200000,0x300000,0x400000,0x501000
    original = bytes.fromhex(store)
    code = build_hook(cave,return_to,slot,original)
    uc.mem_write(cave,code)
    uc.mem_write(slot,struct.pack('<Q',entity if protected else entity+0x100))
    uc.mem_write(entity+0x4ec,struct.pack('<f',100))
    uc.mem_write(stack-128,b'Z'*128)
    uc.reg_write(x.UC_X86_REG_RSP,stack)
    uc.reg_write(x.UC_X86_REG_RBX,entity)
    uc.reg_write(x.UC_X86_REG_RAX,0x1122334455667788)
    uc.reg_write(x.UC_X86_REG_RCX,0x123456789)
    uc.reg_write(x.UC_X86_REG_RDX,0xaabbccddeeff)
    uc.reg_write(x.UC_X86_REG_EFLAGS,0x246)
    xmm = int.from_bytes(struct.pack('<f',75)+b'Q'*12,'little')
    xmm_register = getattr(x,f"UC_X86_REG_XMM{xmm_number}")
    uc.reg_write(xmm_register,xmm)
    uc.emu_start(cave,return_to,count=100)
    hp = struct.unpack('<f',uc.mem_read(entity+0x4ec,4))[0]
    assert hp == (100 if protected else 75)
    assert uc.reg_read(x.UC_X86_REG_RIP) == return_to
    assert uc.reg_read(x.UC_X86_REG_RAX) == 0x1122334455667788
    assert uc.reg_read(x.UC_X86_REG_RBX) == entity
    assert uc.reg_read(x.UC_X86_REG_RCX) == 0x123456789
    assert uc.reg_read(x.UC_X86_REG_RDX) == 0xaabbccddeeff
    assert uc.reg_read(x.UC_X86_REG_RSP) == stack
    assert uc.reg_read(x.UC_X86_REG_EFLAGS) == 0x246
    assert uc.reg_read(xmm_register) == xmm
    assert bytes(uc.mem_read(stack-128,128)) == b'Z'*128


def test_real_god_mode_affects_player_not_enemy(target):
    from conftest import attach_or_skip
    from unepic_trainer.backend import Backend
    from unepic_trainer.hooks import GodMode
    proc, data, identity, profile = target
    backend = Backend(profile)
    attach_or_skip(backend,identity)
    mode = GodMode()
    try:
        mode.enable(backend)
        proc.stdin.write('damage\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '100 75'
        proc.stdin.write('burn\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '100 65'
        mode.disable(backend)
        proc.stdin.write('damage\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '75 40'
        proc.stdin.write('burn\n'); proc.stdin.flush()
        assert proc.stdout.readline().strip() == '65 30'
    finally:
        mode.disable(backend)
        backend.detach()


def test_both_damage_paths_are_patched_and_restored():
    from unepic_trainer.hooks import GodMode
    memory = PatchMemory()
    mode = GodMode()
    mode.enable(memory)
    sites = (memory.profile.damage_store,memory.profile.dot_damage_store)
    assert all(memory.read(site,8)[0] == 0xe9 for site in sites)
    assert set(memory.active_patches) == set(sites)
    mode.disable(memory)
    assert memory.read(sites[0],8) == memory.profile.original
    assert memory.read(sites[1],8) == memory.profile.dot_original
    assert not mode.active and not memory.active_patches


@pytest.mark.parametrize('failure',["bytes","ip"])
def test_dot_site_is_checked_before_any_writes(failure):
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    if failure == "bytes":
        memory.put_code(memory.profile.dot_damage_store,b"12345678")
    else:
        memory.ips = [memory.profile.dot_damage_store+2]
    with pytest.raises(BackendError): GodMode().enable(memory)
    assert memory.writes == []


def test_second_site_partial_write_rolls_back_both_sites():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    memory.fail_at = memory.profile.dot_damage_store
    mode = GodMode()
    with pytest.raises(BackendError,match="Injected write failure"):
        mode.enable(memory)
    assert memory.read(memory.profile.damage_store,8) == memory.profile.original
    assert memory.read(memory.profile.dot_damage_store,8) == memory.profile.dot_original
    assert not mode.active and not memory.active_patches and not memory.unsafe


def test_restore_failure_keeps_remaining_site_recoverable():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    mode = GodMode()
    mode.enable(memory)
    memory.fail_at = memory.profile.dot_damage_store
    with pytest.raises(BackendError,match="restored"):
        mode.disable(memory)
    assert mode.active and memory.unsafe
    assert memory.active_patches == {memory.profile.dot_damage_store:memory.profile.dot_original}
    mode.disable(memory)
    assert not mode.active and not memory.unsafe and not memory.active_patches


def test_foreign_dot_patch_refuses_restoration_of_both_sites():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = PatchMemory()
    mode = GodMode()
    mode.enable(memory)
    memory.put_code(memory.profile.dot_damage_store,b'12345678')
    memory.writes.clear()
    with pytest.raises(BackendError,match='Unexpected hook bytes'):
        mode.disable(memory)
    assert memory.writes == []
    assert mode.active and memory.unsafe and len(memory.active_patches) == 2


def test_failed_enable_rollback_remains_recoverable():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError

    class FailedRollback(PatchMemory):
        refuse_rollback = True

        def write(self,address,data):
            if (address == self.profile.damage_store and data == self.profile.original
                    and self.refuse_rollback):
                raise BackendError('Injected rollback failure')
            super().write(address,data)

    memory = FailedRollback()
    memory.fail_at = memory.profile.dot_damage_store
    mode = GodMode()
    with pytest.raises(BackendError,match='could not be restored'):
        mode.enable(memory)
    assert mode.active and memory.unsafe
    assert memory.active_patches == {memory.profile.damage_store:memory.profile.original}
    memory.refuse_rollback = False
    mode.disable(memory)
    assert not mode.active and not memory.unsafe and not memory.active_patches
