import struct
import pytest
from test_progression import ProgressionMemory


class GoldMemory(ProgressionMemory):
    def __init__(self):
        super().__init__()
        p = self.profile
        self.put(p.custom_map,'I',0); self.put(p.player_count,'I',1)
        self.put(p.active_hero,'Q',p.hero)
        self.descriptor = p.item_table
        self.put_code(p.item_table, b'\0'*0x1c8)
        self.put(p.item_table+0xb9400,'I',1)
        self.put(self.descriptor,'I',0x238d)
        self.put_code(self.descriptor+4,b'gold\0')
        self.put(self.descriptor+0x70,'I',1000000)
        self.put(p.hero+0x140c,'I',1)
        self.entry = p.hero+0x1418
        self.put_code(self.entry,b'\0'*0xb8)
        self.put(self.entry,'Q',self.descriptor)
        for primary,mirror,value in ((8,0x34,250),(0x10,0x38,0),(0x18,0x3c,100),(0x24,0x40,0)):
            self.put(self.entry+primary,'I',value^0xabcdef01)
            self.put(self.entry+mirror,'I',value^0x12345678)
        for name in ('item_add','item_merge','item_create','item_lookup'):
            self.put_code(getattr(p,name+'_store'),getattr(p,name+'_original'))


@pytest.mark.parametrize('amount',[100,1000,10000])
@pytest.mark.parametrize('empty',[False,True])
def test_gold_queues_native_award_without_direct_inventory_writes(amount,empty):
    from unepic_trainer.progression import Progression
    m = GoldMemory(); p = m.profile
    if empty: m.put(p.hero+0x140c,'I',0)
    before = m.read(m.entry,0xb8)
    mode = Progression(); mode.submit(m,'gold',amount)
    assert mode.pending and m.read(m.entry,0xb8) == before
    assert struct.unpack('<I',m.read(mode.config+4,4))[0] == 3
    assert struct.unpack('<Q',m.read(mode.config+40,8))[0] == m.descriptor
    m.put(mode.config+12,'I',2)
    assert mode.poll(m) == ('gold',amount)
    mode.disable_all(m); assert not m.active_patches


@pytest.mark.parametrize('invalid',['amount','full','pair','pointer','alignment','overflow','count',
                                   'table-count','missing','name','unique','category','function','capacity',
                                   'custom','players','hero'])
def test_gold_rejects_invalid_inventory_without_writes(invalid):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    m = GoldMemory(); p = m.profile; amount = 10000
    if invalid == 'amount': amount = 10
    elif invalid == 'custom': m.put(p.custom_map,'I',1)
    elif invalid == 'players': m.put(p.player_count,'I',2)
    elif invalid == 'hero': m.put(p.active_hero,'Q',p.hero+4)
    elif invalid == 'full': m.put(p.hero+0x140c,'I',512)
    elif invalid == 'pair': m.put(m.entry+0x38,'I',0)
    elif invalid == 'pointer': m.put(m.entry,'Q',0)
    elif invalid == 'alignment': m.put(m.entry,'Q',m.descriptor+4)
    elif invalid == 'count': m.put(p.hero+0x140c,'I',0xffffffff)
    elif invalid == 'table-count': m.put(p.item_table+0xb9400,'I',1665)
    elif invalid == 'missing': m.put(m.descriptor,'I',9999)
    elif invalid == 'name': m.put_code(m.descriptor+4,b'X'*64)
    elif invalid == 'unique': m.put(m.descriptor+0xe8,'I',1)
    elif invalid == 'category': m.put(m.descriptor+0x58,'I',1)
    elif invalid == 'function': m.put_code(p.item_add_store,b'\0'*16)
    elif invalid == 'capacity': m.put(m.descriptor+0x70,'I',1)
    elif invalid == 'overflow':
        m.put(m.entry+8,'I',0x7fffffff^0xabcdef01)
        m.put(m.entry+0x34,'I',0x7fffffff^0x12345678)
    with pytest.raises(BackendError): Progression().submit(m,'gold',amount)
    assert not m.writes and not m.active_patches


def test_worker_gold_has_backup_gate_and_reports_completion(tmp_path):
    from unepic_trainer.ui import Worker
    from unepic_trainer.backend import BackendError
    worker = Worker(tmp_path,None); m = GoldMemory(); worker.backend = m
    m.identity = object()
    worker._refresh = lambda: None
    errors = []; statuses = []
    worker.operation_failed.connect(errors.append); worker.status_changed.connect(statuses.append)
    def fail(): raise BackendError('Backup unavailable')
    worker._backup_before_change = fail; worker.dispatch('gold',1000)
    assert errors == ['Backup unavailable'] and not m.writes
    worker._backup_before_change = lambda: None; worker.dispatch('gold',1000)
    assert worker.progression.pending
    m.put(worker.progression.config+12,'I',2); worker._poll_progression(m)
    assert statuses[-1] == 'Added 1000 gold'
