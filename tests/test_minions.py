import struct
import pytest
from test_hooks import PatchMemory


class MinionMemory(PatchMemory):
    room = 0x300000
    pet = 0x110000
    foreign = 0x120000

    def allocate_near(self,address,size):
        candidate = self.cave + getattr(self,'allocations',0)*4096
        self.allocations = getattr(self,'allocations',0)+1
        self.put_code(candidate,b'\0'*size)
        return candidate

    def __init__(self):
        super().__init__()
        self.put(self.profile.hero+0x197c0, 'Q', self.room)
        self.put(0x100000+0x58c, 'I', 42)
        self.put(self.room+0xbef0, 'i', 2)
        self.put(self.room+0xbef8, 'Q', self.pet)
        self.put(self.room+0xbf00, 'Q', self.foreign)
        for entity, owner in ((self.pet,42),(self.foreign,99)):
            self.put_code(entity, b'\0'*0x650)
            self.put(entity+0x170,'i',4)
            self.put(entity+0x64c,'I',owner)
            self.put(entity+0x4e8,'i',80)
            self.put(entity+0x4ec,'f',40)
            self.put(entity+0x178,'i',100)
            self.put(entity+0x608,'f',25)
        for site, original in ((0x48907b,'f30f118308060000'),
                               (0x488e0c,'f30f118708060000'),
                               (0x489170,'f30f118f08060000')):
            self.put_code(site,bytes.fromhex(original))


def test_owned_minion_read_heal_and_maximum_energy_only():
    from unepic_trainer.minions import read_minions, heal_minions, refill_energy
    memory = MinionMemory()
    pet, = read_minions(memory)
    assert (pet.entity,pet.current_hp,pet.max_hp,pet.energy,pet.max_energy) == (memory.pet,40,80,25,100)
    heal_minions(memory)
    refill_energy(memory)
    assert memory.read(memory.pet+0x4ec,4) == struct.pack('<f',80)
    assert memory.read(memory.pet+0x608,4) == struct.pack('<f',100)
    assert memory.read(memory.foreign+0x4ec,4) == struct.pack('<f',40)
    assert memory.read(memory.foreign+0x608,4) == struct.pack('<f',25)
    assert {address for address,_ in memory.writes} == {memory.pet+0x4ec,memory.pet+0x608}


@pytest.mark.parametrize('offset,kind,value',[(0x64c,'I',0),(0x170,'i',3),
    (0x5c8,'i',0x73),(0x5c8,'i',0x76),(0x4ec,'f',0)])
def test_unavailable_or_unowned_minion_never_written(offset,kind,value):
    from unepic_trainer.minions import read_minions, heal_minions
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.put(memory.pet+offset,kind,value)
    assert read_minions(memory) == ()
    with pytest.raises(BackendError): heal_minions(memory)
    assert memory.writes == []


@pytest.mark.parametrize('offset,kind,value',[(0x608,'f',float('nan')),(0x608,'f',101),
    (0x4ec,'f',float('inf')),(0x4e8,'i',-1)])
def test_invalid_minion_values_reject_all_writes(offset,kind,value):
    from unepic_trainer.minions import heal_minions
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.put(memory.pet+offset,kind,value)
    with pytest.raises(BackendError): heal_minions(memory)
    assert memory.writes == []


def test_missing_energy_does_not_prevent_hp_healing():
    from unepic_trainer.minions import read_minions, heal_minions, refill_energy
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.put(memory.pet+0x178,'i',0)
    assert read_minions(memory)[0].max_energy == 0
    heal_minions(memory)
    with pytest.raises(BackendError): refill_energy(memory)
    assert len(memory.writes) == 1


def test_room_bounds_and_integrity_reject_writes():
    from unepic_trainer.minions import heal_minions
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.put(memory.room+0xbef0,'i',4097)
    with pytest.raises(BackendError): heal_minions(memory)
    memory.put(memory.room+0xbef0,'i',2)
    memory.put(memory.profile.detection_flag,'I',1)
    with pytest.raises(BackendError): heal_minions(memory)
    assert memory.writes == []


def test_player_and_minion_toggles_share_hooks_but_are_independent():
    from unepic_trainer.hooks import GodMode, EnergyLock
    memory = MinionMemory(); mode = GodMode(); energy = EnergyLock()
    mode.enable(memory)
    mode.enable(memory,'minion')
    assert mode.active and mode.minion_active
    mode.disable(memory)
    assert not mode.active and mode.minion_active and len(memory.active_patches) == 2
    energy.enable(memory)
    assert energy.active and memory.read(memory.pet+0x608,4) == struct.pack('<f',100)
    energy.disable(memory)
    assert not energy.active and mode.minion_active and len(memory.active_patches) == 2
    mode.disable(memory,'minion')
    assert not memory.active_patches


@pytest.mark.parametrize('site',[0x48907b,0x488e0c,0x489170])
def test_energy_partial_install_restores_every_site(site):
    from unepic_trainer.hooks import EnergyLock
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.fail_at = site
    mode = EnergyLock()
    with pytest.raises(BackendError): mode.enable(memory)
    assert not mode.active and not memory.active_patches and not memory.unsafe
    assert memory.read(memory.pet+0x608,4) == struct.pack('<f',25)
    for address,original in mode._sites(memory): assert memory.read(address,8) == original


def test_energy_foreign_patch_refuses_disconnect_and_restore_retry_recovers():
    from unepic_trainer.hooks import EnergyLock
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); mode = EnergyLock(); mode.enable(memory)
    site = memory.profile.energy_cap_store
    patch = memory.read(site,8)
    memory.put_code(site,b'12345678'); memory.writes.clear()
    with pytest.raises(BackendError): mode.disable_all(memory)
    assert memory.writes == [] and memory.unsafe and mode.active
    memory.put_code(site,patch); memory.fail_at = site
    with pytest.raises(BackendError): mode.disable_all(memory)
    assert memory.unsafe and mode.active and len(memory.active_patches) == 1
    mode.disable_all(memory)
    assert not memory.unsafe and not mode.active and not memory.active_patches


def test_failed_feature_mask_write_requires_recovery_instead_of_stale_state():
    from unepic_trainer.hooks import GodMode
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); mode = GodMode(); mode.enable(memory)
    memory.fail_at = mode.config
    with pytest.raises(BackendError): mode.enable(memory,'minion')
    assert memory.unsafe and mode.active
    mode.disable_all(memory)
    assert not memory.unsafe and not memory.active_patches


@pytest.mark.parametrize('mask',range(8))
@pytest.mark.parametrize('actor',['player','pet','foreign','wrong_type','recalled','dead','no_player'])
@pytest.mark.parametrize('store,register,energy',[
    ('f30f1193ec040000','RBX',False),('f30f119bec040000','RBX',False),
    ('f30f118308060000','RBX',True),('f30f118708060000','RDI',True),
    ('f30f118f08060000','RDI',True)])
def test_protection_on_cpu_preserves_context_and_selects_owned_live_pet(mask,actor,store,register,energy):
    from unepic_trainer.hooks import build_protection_hook
    import unicorn
    from unicorn import x86_const as x
    uc = unicorn.Uc(unicorn.UC_ARCH_X86,unicorn.UC_MODE_64)
    for address in (0x100000,0x200000,0x300000,0x400000,0x500000): uc.mem_map(address,0x2000)
    player,pet,slot,config,cave,end,stack = 0x100000,0x101000,0x200000,0x200100,0x300000,0x400000,0x501000
    entity = player if actor == 'player' else pet
    uc.mem_write(slot,struct.pack('<Q',0 if actor == 'no_player' else player))
    uc.mem_write(config,bytes([mask]))
    uc.mem_write(player+0x58c,struct.pack('<I',42))
    uc.mem_write(pet+0x170,struct.pack('<i',3 if actor == 'wrong_type' else 4))
    uc.mem_write(pet+0x64c,struct.pack('<I',99 if actor == 'foreign' else 42))
    uc.mem_write(pet+0x5c8,struct.pack('<i',0x73 if actor == 'recalled' else 0))
    uc.mem_write(entity+0x4ec,struct.pack('<f',0 if actor == 'dead' else 80))
    uc.mem_write(entity+0x178,struct.pack('<i',100))
    uc.mem_write(entity+0x608,struct.pack('<f',100))
    code = build_protection_hook(cave,end,slot,bytes.fromhex(store),config,energy)
    uc.mem_write(cave,code); uc.mem_write(stack-128,b'Z'*128)
    values = {'RAX':0x11223344,'RBX':0x88776655,'RCX':0x99887766,'RDX':0x12345678,'RDI':0xaabbccdd,'RSP':stack}
    values[register] = entity
    for name,value in values.items(): uc.reg_write(getattr(x,'UC_X86_REG_'+name),value)
    uc.reg_write(x.UC_X86_REG_EFLAGS,0x246)
    for i in range(4): uc.reg_write(getattr(x,f'UC_X86_REG_XMM{i}'),int.from_bytes(struct.pack('<f',50)+bytes([65+i])*12,'little'))
    xmm_before = [uc.reg_read(getattr(x,f'UC_X86_REG_XMM{i}')) for i in range(4)]
    uc.emu_start(cave,end,count=200)
    owned = actor == 'pet'
    protected = bool(mask & (4 if energy else 2)) and owned
    if not energy and actor == 'player': protected = bool(mask&1)
    offset = 0x608 if energy else 0x4ec
    expected = (100 if energy else 80) if protected else 50
    assert struct.unpack('<f',uc.mem_read(entity+offset,4))[0] == expected
    for name,value in values.items(): assert uc.reg_read(getattr(x,'UC_X86_REG_'+name)) == value
    assert uc.reg_read(x.UC_X86_REG_EFLAGS) == 0x246
    assert [uc.reg_read(getattr(x,f'UC_X86_REG_XMM{i}')) for i in range(4)] == xmm_before
    assert bytes(uc.mem_read(stack-128,128)) == b'Z'*128
