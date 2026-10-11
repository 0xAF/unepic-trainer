import struct
import pytest
from test_minions import MinionMemory


class ProgressionMemory(MinionMemory):
    def __init__(self):
        super().__init__()
        p = self.profile
        self.put(p.campaign_mode,'I',0)
        self.put(p.simulation_flag,'I',0)
        self.put_code(self.room+0x24af4,b'\0'*12)
        for name in ('progression','points_add','xp_cap','xp_set','xp_award'):
            self.put_code(getattr(p,name+'_store'),getattr(p,name+'_original'))


@pytest.mark.parametrize('action,amount',[('points',1),('points',10),('points',100),('level-up',0)])
def test_requests_are_one_shot_and_restore_update_entry(action,amount):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    memory = ProgressionMemory(); mode = Progression()
    protected = memory.read(memory.profile.hero+0x160,0x2c)
    mode.submit(memory,action,amount)
    assert mode.pending and len(memory.active_patches) == 1
    assert memory.read(memory.profile.hero+0x160,0x2c) == protected
    with pytest.raises(BackendError,match='pending'): mode.submit(memory,action,amount)
    assert mode.poll(memory) is None
    memory.put(mode.config+12,'I',2)
    assert mode.poll(memory) == (action,amount)
    assert not mode.pending and mode.poll(memory) is None
    mode.disable_all(memory)
    assert not memory.active_patches
    assert memory.read(memory.profile.progression_store,8) == memory.profile.progression_original


def test_progression_executes_on_native_cpu_without_ptrace(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    fixtures = Path(__file__).parent/'fixtures'
    library = tmp_path/'progression.so'
    subprocess.run(['gcc','-shared','-fPIC','-O0',str(fixtures/'progression_native.c'),
                    '-o',str(library)],check=True,capture_output=True)
    env = dict(os.environ,PYTHONPATH=str(Path(__file__).parents[1]/'src'))
    result = subprocess.run([sys.executable,str(fixtures/'progression_native.py'),str(library)],
                            env=env,capture_output=True,text=True,timeout=10)
    assert result.returncode == 0,result.stdout+result.stderr
    assert 'restoration passed' in result.stdout


def test_real_gdb_progression_is_immediate_and_all_hooks_restore(tmp_path):
    from dataclasses import replace
    import hashlib
    from pathlib import Path
    import subprocess
    from conftest import attach_or_skip
    from unepic_trainer.backend import Backend
    from unepic_trainer.profiles import Profile
    from unepic_trainer.processes import identify
    from unepic_trainer.progression import Progression
    from unepic_trainer.hooks import GodMode,EnergyLock
    binary = tmp_path/'progression-target'
    subprocess.run(['gcc','-O0','-g','-fno-pie','-no-pie','-DPROGRESSION_PROCESS',
        str(Path(__file__).parent/'fixtures/progression_native.c'),'-o',str(binary)],check=True)
    symbols = {}
    for line in subprocess.check_output(['nm','-P',str(binary)],text=True).splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1] != 'U': symbols[fields[0]] = int(fields[2],16)
    image = binary.read_bytes()
    def original(name):
        address = symbols[name]
        phoff = struct.unpack_from('<Q',image,32)[0]
        size,count = struct.unpack_from('<HH',image,54)
        for i in range(count):
            kind,flags,offset,va,_,filesz,_,_ = struct.unpack_from('<IIQQQQQQ',image,phoff+i*size)
            if kind == 1 and va <= address and address+16 <= va+filesz:
                return image[offset+address-va:offset+address-va+16]
        raise AssertionError('Native function not in file-backed ELF segment')
    fields = {name:symbols[symbol] for name,symbol in (
        ('hero','hero'),('entity_slot','entity_slot'),('primary_key','key_a'),('mirror_key','key_b'),
        ('detection_flag','detection'),('penalty_flag','penalty'),('campaign_mode','campaign_mode'),
        ('simulation_flag','simulation_flag'),('damage_store','damage_store'),('dot_damage_store','dot_damage_store'),
        ('energy_store','energy_store'),('energy_regen_store','energy_regen_store'),('energy_cap_store','energy_cap_store'),
        ('progression_store','character_update'))}
    for name in ('points_add','xp_cap','xp_set','xp_award'):
        fields[name+'_store'] = symbols[name]; fields[name+'_original'] = original(name)
    p = replace(Profile(),sha256=hashlib.sha256(image).hexdigest(),**fields)
    process = subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    backend = Backend(p); mode = Progression(); hp = GodMode(); energy = EnergyLock()
    try:
        assert process.stdout.readline().strip() == 'ready'
        attach_or_skip(backend,identify(process.pid))
        hp.enable(backend); hp.enable(backend,'minion'); energy.enable(backend)
        def update(expected):
            process.stdin.write('update\n'); process.stdin.flush()
            assert process.stdout.readline().strip() == expected
        mode.submit(backend,'points',100); update('3 250 105')
        with backend.live() as reader: assert mode.poll(reader) == ('points',100)
        mode.submit(backend,'level-up'); update('4 0 110')
        with backend.live() as reader: assert mode.poll(reader) == ('level-up',0)
        update('4 0 110')
        mode.disable_all(backend); energy.disable_all(backend); hp.disable_all(backend)
        with backend.stopped():
            assert backend.read(p.progression_store,8) == p.progression_original
        assert not backend.active_patches
        backend.detach(); update('4 0 110')
    finally:
        if backend.identity is not None:
            mode.disable_all(backend); energy.disable_all(backend); hp.disable_all(backend); backend.detach()
        process.kill(); process.wait(timeout=5); process.stdin.close(); process.stdout.close()


@pytest.mark.parametrize('invalid',['mode','simulation','dead','flags','pair','function','cap','overflow','room','amount'])
def test_invalid_requests_make_no_writes(invalid):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    memory = ProgressionMemory(); p = memory.profile; action,amount = 'points',100
    if invalid == 'mode': memory.put(p.campaign_mode,'I',1)
    elif invalid == 'simulation': memory.put(p.simulation_flag,'I',1)
    elif invalid == 'dead': memory.put(0x1004ec,'f',0)
    elif invalid == 'flags': memory.put(p.detection_flag,'I',1)
    elif invalid == 'pair': memory.put(p.hero+0x188,'I',0)
    elif invalid == 'function': memory.put_code(p.xp_award_store,b'\0'*16)
    elif invalid == 'room': memory.put(p.hero+0x197c0,'Q',0)
    elif invalid == 'amount': amount = 2
    else:
        offset,mirror,value = (0x168,0x184,25) if invalid == 'cap' else (0x16c,0x188,0x7fffffff)
        memory.put(p.hero+offset,'I',value^0xabcdef01)
        memory.put(p.hero+mirror,'I',value^0x12345678)
        if invalid == 'cap': action,amount = 'level-up',0
    with pytest.raises(BackendError): Progression().submit(memory,action,amount)
    assert memory.writes == [] and not memory.active_patches


def test_failed_request_write_is_cancelled_and_retry_is_safe():
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    memory = ProgressionMemory(); mode = Progression()
    mode.submit(memory,'points',1); memory.put(mode.config+12,'I',2); mode.poll(memory)
    memory.fail_at = mode.config+4
    with pytest.raises(BackendError): mode.submit(memory,'points',100)
    assert not mode.pending and not memory.unsafe
    assert memory.read(mode.config+4,36) == b'\0'*36
    memory.ips = [mode.cave+10]
    with pytest.raises(BackendError,match='dispatcher'): mode.submit(memory,'points',10)
    mode.disable_all(memory)


def test_failed_cancel_keeps_game_paused_until_patch_recovery():
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    class FailedCancel(ProgressionMemory):
        blocked = None
        def write(self,address,data):
            super().write(address,data)
            if address == self.blocked: raise BackendError('Request clear failure')
    memory = FailedCancel(); mode = Progression()
    mode.enable(memory); memory.blocked = mode.config+4
    with pytest.raises(BackendError): mode.submit(memory,'points',100)
    assert memory.unsafe and mode.active and memory.active_patches
    memory.blocked = None; mode.disable_all(memory)
    assert not memory.unsafe and not memory.active_patches and not mode.pending


def test_worker_progression_uses_backup_and_restores_pending_hook(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from unepic_trainer import ui
    from unepic_trainer.backend import BackendError
    worker = ui.Worker(tmp_path,None); memory = ProgressionMemory()
    memory.identity = SimpleNamespace(pid=1,executable='/tmp/test-progression')
    memory.detach = lambda: setattr(memory,'identity',None)
    worker.backend = memory; worker._refresh = lambda: None
    errors = []; pending = []; worker.operation_failed.connect(errors.append)
    worker.progression_pending.connect(pending.append)
    def fail(): raise BackendError('Backup unavailable')
    worker._backup_before_change = fail
    worker.dispatch('points',100); worker.dispatch('level-up',None)
    assert errors == ['Backup unavailable']*2 and not memory.writes
    errors.clear(); worker._backup_before_change = lambda: setattr(worker,'backup','saved')
    worker.dispatch('points',10)
    assert not errors and worker.backup == 'saved' and pending[-1]
    memory.put(worker.progression.config+12,'I',2)
    worker._poll_progression(memory)
    assert not pending[-1]
    worker.dispatch('level-up',None); assert pending[-1]
    monkeypatch.setattr(ui,'is_current',lambda identity: True)
    worker.dispatch('detach',None)
    assert not errors and not memory.active_patches and not pending[-1] and memory.identity is None


def test_cancelled_request_is_reported_without_being_hidden_by_live_retry(tmp_path):
    from unepic_trainer import ui
    worker = ui.Worker(tmp_path,None); memory = ProgressionMemory()
    worker.backend = memory; memory.live = memory.stopped
    worker.progression.submit(memory,'points',10)
    memory.put(worker.progression.config+12,'I',3)
    errors = []; worker.operation_failed.connect(errors.append)
    snapshot,pets = worker._live_snapshot()
    assert snapshot.level == 3 and pets
    assert len(errors) == 1 and 'cancelled' in errors[0]
    assert not worker.progression.pending


def test_progression_coexists_with_all_hp_and_energy_hooks():
    from unepic_trainer.progression import Progression
    from unepic_trainer.hooks import GodMode,EnergyLock
    memory = ProgressionMemory(); hp = GodMode(); energy = EnergyLock(); mode = Progression()
    hp.enable(memory); hp.enable(memory,'minion'); energy.enable(memory)
    mode.submit(memory,'level-up')
    assert len(memory.active_patches) == 6
    mode.disable_all(memory)
    assert len(memory.active_patches) == 5 and hp.active and hp.minion_active and energy.active
    energy.disable_all(memory); hp.disable_all(memory)
    assert not memory.active_patches


@pytest.mark.parametrize('action,amount',[('points',1),('points',10),('points',100),('level-up',0),
                                        ('gold',100),('gold',1000),('gold',10000),
                                        ('credits',100),('credits',1000),('credits',10000),
                                        ('kill-points',1),('kill-points',10),('kill-points',100)])
@pytest.mark.parametrize('condition',['valid','foreign','mode','dead','pair','room','level','overflow','disabled',
    'full','inventory-pair','inventory-pointer','table-count','descriptor','gold-amount','gold-capacity','empty','unlimited','native-fail',
    'credit-score','credit-sum','credit-balance','credit-sentinel',
    'kp-locked','kp-negative','kp-excess','kp-full','kp-amount','kp-near-cap','kp-custom','kp-players','kp-active'])
def test_dispatcher_calls_native_functions_once_and_preserves_cpu_context(action,amount,condition):
    from unepic_trainer.progression import build_progression_hook
    from dataclasses import replace
    from unepic_trainer.profiles import Profile
    import unicorn
    from unicorn import x86_const as x
    uc = unicorn.Uc(unicorn.UC_ARCH_X86,unicorn.UC_MODE_64)
    hero,entity,globals_,cave,end,stack,room = 0x100000,0x200000,0x300000,0x400000,0x401000,0x501008,0x600000
    table = 0x700000
    for address,size in ((hero,0x20000),(entity,0x2000),(globals_,0x2000),(cave,0x2000),
                         (0x500000,0x4000),(room,0x26000),(table,0xc0000)):
        uc.mem_map(address,size)
    p = replace(Profile(),hero=hero,entity_slot=globals_,primary_key=globals_+8,
        mirror_key=globals_+12,campaign_mode=globals_+16,simulation_flag=globals_+20,
        detection_flag=globals_+24,penalty_flag=globals_+28,points_add_store=end+0x100,
        xp_cap_store=end+0x200,xp_set_store=end+0x300,xp_award_store=end+0x400,
        item_table=table,item_add_store=end+0x500,custom_map=globals_+32,
        player_count=globals_+36,active_hero=globals_+40,credit_scores=globals_+0x300,credit_types=globals_+0x400)
    config = globals_+0x100
    def put(address,kind,value): uc.mem_write(address,struct.pack('<'+kind,value))
    def get(address,kind): return struct.unpack('<'+kind,uc.mem_read(address,struct.calcsize(kind)))[0]
    keya,keyb = 0xabcdef01,0x12345678
    put(p.entity_slot,'Q',entity); put(p.primary_key,'I',keya); put(p.mirror_key,'I',keyb)
    put(p.player_count,'I',1); put(p.active_hero,'Q',hero)
    put(hero+0x197c0,'Q',room); put(entity+0x4ec,'f',100)
    put(hero+0x174,'i',8); put(hero+0x178,'i',1)
    def set_pair(offset,mirror,value):
        put(hero+offset,'I',value^keya); put(hero+mirror,'I',value^keyb)
    def decoded(offset): return get(hero+offset,'I')^keya
    for off,mirror,value in ((0x160,0x17c,250),(0x164,0x180,1000),(0x168,0x184,3),(0x16c,0x188,5)):
        set_pair(off,mirror,value)
    put(config,'I',8)
    uc.mem_write(config+4,struct.pack('<IIIQI4xQQ',{'points':1,'level-up':2,'gold':3,'credits':4,'kill-points':5}[action],
                                    amount,1,entity,3,room,table if action in ('gold','credits') else 0))
    entry = hero+0x1418
    put(table+0xb9400,'I',1); put(table,'I',0x238d); uc.mem_write(table+4,b'gold\0')
    put(table+0x70,'I',1000000); put(hero+0x140c,'I',1); put(entry,'Q',table)
    for a,b,v in ((8,0x34,250),(0x10,0x38,0),(0x18,0x3c,100),(0x24,0x40,0)):
        put(entry+a,'I',v^keya); put(entry+b,'I',v^keyb)
    if action == 'credits':
        put(table,'I',0x238e); put(p.credit_scores,'i',500); put(p.credit_types,'i',2)
        put(p.credit_scores+60,'i',-1); put(hero+0x170,'i',250)
    if condition == 'mode': put(p.campaign_mode,'I',1)
    elif condition == 'dead': put(entity+0x4ec,'f',0)
    elif condition == 'pair': put(hero+0x188,'I',0)
    elif condition == 'room': put(hero+0x197c0,'Q',room+4)
    elif condition == 'level' and action == 'level-up': set_pair(0x168,0x184,4)
    elif condition == 'overflow': set_pair(0x16c,0x188,0x7fffffff)
    elif condition == 'disabled': put(config,'I',0)
    if action in ('gold','credits'):
        if condition == 'overflow':
            put(entry+8,'I',0x7fffffff^keya); put(entry+0x34,'I',0x7fffffff^keyb)
        elif condition == 'full': put(hero+0x140c,'I',512)
        elif condition == 'inventory-pair': put(entry+0x3c,'I',0)
        elif condition == 'inventory-pointer': put(entry,'Q',table+4)
        elif condition == 'table-count': put(table+0xb9400,'I',1665)
        elif condition == 'descriptor': put(table,'I',9999)
        elif condition == 'gold-amount': put(config+8,'I',2)
        elif condition == 'gold-capacity':
            put(table+0x70,'I',1); put(hero+0x140c,'I',512 if action == 'credits' else 511)
        elif condition == 'empty': put(hero+0x140c,'I',0)
        elif condition == 'unlimited': put(table+0x70,'I',0)
    if action == 'credits':
        if condition == 'credit-score': put(p.credit_scores,'i',-1)
        elif condition == 'credit-sum':
            put(p.credit_scores,'i',0x7fffffff); put(p.credit_scores+4,'i',1); put(p.credit_types+4,'i',2)
        elif condition == 'credit-balance': put(hero+0x170,'i',501)
        elif condition == 'credit-sentinel': put(p.credit_scores+60,'i',0)
    if action == 'kill-points':
        if condition == 'kp-locked': put(hero+0x178,'i',0)
        elif condition == 'kp-negative': put(hero+0x174,'i',-1)
        elif condition == 'kp-excess': put(hero+0x174,'i',26)
        elif condition in ('kp-full','overflow'): put(hero+0x174,'i',25)
        elif condition == 'kp-amount': put(config+8,'I',2)
        elif condition == 'kp-near-cap': put(hero+0x174,'i',24)
        elif condition == 'kp-custom': put(p.custom_map,'I',1)
        elif condition == 'kp-players': put(p.player_count,'I',2)
        elif condition == 'kp-active': put(p.active_hero,'Q',hero+4)
    kp_before = get(hero+0x174,'i')
    uc.mem_write(cave,build_progression_hook(cave,end,p,config))
    native_addresses = (p.points_add_store,p.xp_cap_store,p.xp_set_store,p.xp_award_store,p.item_add_store)
    for address in native_addresses: uc.mem_write(address,b'\xc3')
    names = ('RAX','RCX','RDX','RBX','RBP','RSI','RDI','R8','R9','R10','R11','R12','R13','R14','R15')
    values = {name:0x100012340000+i for i,name in enumerate(names)}
    values['RDI'] = hero+4 if condition == 'foreign' else hero
    xmm = [int.from_bytes(bytes([i+1])*16,'little') for i in range(16)]
    calls = []
    def native_call(uc,address,size,data):
        if address not in native_addresses: return
        assert uc.reg_read(x.UC_X86_REG_RSP)%16 == 8
        assert uc.reg_read(x.UC_X86_REG_RDI) == (hero+0x1400 if address == p.item_add_store else hero)
        assert not uc.reg_read(x.UC_X86_REG_EFLAGS)&0x400
        arg = uc.reg_read(x.UC_X86_REG_RSI)&0xffffffff
        calls.append((address,arg))
        result = 0
        if address == p.item_add_store:
            assert uc.reg_read(x.UC_X86_REG_RSI) == table+4
            assert uc.reg_read(x.UC_X86_REG_RDX) == 0 and uc.reg_read(x.UC_X86_REG_RCX) == 0
            assert uc.reg_read(x.UC_X86_REG_R8) == amount
            balance = 0 if condition == 'empty' else (get(entry+8,'I')^keya)
            put(entry+8,'I',(balance+amount)^keya); put(entry+0x34,'I',(balance+amount)^keyb)
            put(hero+0x140c,'I',1); result = 0 if condition == 'native-fail' else entry
        elif address == p.points_add_store: set_pair(0x16c,0x188,decoded(0x16c)+arg)
        elif address == p.xp_cap_store: result = decoded(0x164)
        elif address == p.xp_set_store: set_pair(0x160,0x17c,arg)
        else:
            assert arg == 1 and decoded(0x160) == decoded(0x164)
            set_pair(0x168,0x184,decoded(0x168)+1)
            set_pair(0x160,0x17c,0); set_pair(0x16c,0x188,decoded(0x16c)+5)
            set_pair(0x164,0x180,2000)
        for name in ('RAX','RCX','RDX','RSI','RDI','R8','R9','R10','R11'):
            uc.reg_write(getattr(x,'UC_X86_REG_'+name),0x76543210)
        uc.reg_write(x.UC_X86_REG_RAX,result)
        for i in range(16): uc.reg_write(getattr(x,f'UC_X86_REG_XMM{i}'),0)
        uc.reg_write(x.UC_X86_REG_MXCSR,0x1f80)
        uc.reg_write(x.UC_X86_REG_EFLAGS,0x202)
    uc.hook_add(unicorn.UC_HOOK_CODE,native_call)
    for iteration in range(2):
        for name,value in values.items(): uc.reg_write(getattr(x,'UC_X86_REG_'+name),value)
        for i,value in enumerate(xmm): uc.reg_write(getattr(x,f'UC_X86_REG_XMM{i}'),value)
        uc.reg_write(x.UC_X86_REG_MXCSR,0x3f80)
        uc.reg_write(x.UC_X86_REG_RSP,stack); uc.reg_write(x.UC_X86_REG_EFLAGS,0x646)
        uc.mem_write(stack-128,b'Z'*128)
        uc.emu_start(cave,end,count=1000)
        assert uc.reg_read(x.UC_X86_REG_RIP) == end
        assert uc.reg_read(x.UC_X86_REG_RSP) == stack-40  # displaced five PUSHes
        for name,value in values.items(): assert uc.reg_read(getattr(x,'UC_X86_REG_'+name)) == value
        assert uc.reg_read(x.UC_X86_REG_EFLAGS) == 0x646
        assert uc.reg_read(x.UC_X86_REG_MXCSR) == 0x3f80
        assert [uc.reg_read(getattr(x,f'UC_X86_REG_XMM{i}')) for i in range(16)] == xmm
        assert bytes(uc.mem_read(stack-128,88)) == b'Z'*88
    inventory_only = ('full','inventory-pair','inventory-pointer','table-count','descriptor','gold-amount','gold-capacity')
    valid = condition in ('valid','empty','unlimited') or (condition == 'level' and action != 'level-up') or (
        condition in inventory_only and action not in ('gold','credits')) or (
        condition == 'native-fail' and action != 'gold') or (
        condition.startswith('credit-') and action != 'credits') or (
        condition.startswith('kp-') and (action != 'kill-points' or condition == 'kp-near-cap'))
    if valid:
        assert get(config+12,'I') == 2
        assert decoded(0x16c) == 5+(amount if action == 'points' else 5 if action == 'level-up' else 0)
        assert decoded(0x168) == (4 if action == 'level-up' else 3)
        expected = ([p.points_add_store] if action == 'points' else [p.item_add_store] if action == 'gold' else
                    [] if action in ('credits','kill-points') else [p.xp_cap_store,p.xp_set_store,p.xp_award_store])
        assert [addr for addr,_ in calls] == expected
        if action == 'gold':
            assert (get(entry+8,'I')^keya) == (0 if condition == 'empty' else 250)+amount
            assert (get(entry+8,'I')^keya) == (get(entry+0x34,'I')^keyb)
        elif action == 'credits':
            assert get(hero+0x170,'i') == 250-amount
            assert get(p.credit_scores,'i') == 500
            assert get(entry+8,'I')^keya == 250  # Normal update, not the entry hook, rebuilds the item.
        elif action == 'kill-points':
            assert get(hero+0x174,'i') == (25 if amount != 1 or condition == 'kp-near-cap' else 13)
            assert get(hero+0x234,'I') == 1
        for off,mirror in ((0x160,0x17c),(0x164,0x180),(0x168,0x184),(0x16c,0x188)):
            assert decoded(off) == get(hero+mirror,'I')^keyb
    else:
        assert [address for address,_ in calls] == ([p.item_add_store] if condition == 'native-fail' and action == 'gold' else [])
        assert get(config+12,'I') == (1 if condition in ('foreign','disabled') else 3)
        if action == 'credits':
            assert get(hero+0x170,'i') == (501 if condition == 'credit-balance' else 250)
    if action != 'kill-points' or not valid:
        assert get(hero+0x174,'i') == kp_before
        assert get(hero+0x234,'I') == 0
