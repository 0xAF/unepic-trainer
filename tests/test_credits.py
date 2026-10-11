import struct
import pytest
from test_gold import GoldMemory


class CreditsMemory(GoldMemory):
    def __init__(self):
        super().__init__(); p = self.profile
        self.put(self.descriptor,'I',0x238e)
        self.put_code(self.descriptor+4,b'credits\0')
        self.put_code(p.credit_scores,b'\0'*60)
        self.put_code(p.credit_types,b'\0'*60)
        self.put(p.credit_scores,'i',500); self.put(p.credit_types,'i',2)
        self.put(p.credit_scores+60,'i',-1)
        self.put(p.hero+0x170,'i',250)


@pytest.mark.parametrize('amount',[100,1000,10000])
def test_credits_queue_source_counter_change_without_touching_gold_or_achievements(amount):
    from unepic_trainer.progression import Progression
    m = CreditsMemory(); p = m.profile
    before = m.read(m.entry,0xb8); scores = m.read(p.credit_scores,64)
    mode = Progression(); mode.submit(m,'credits',amount)
    assert mode.pending and m.read(m.entry,0xb8) == before
    assert m.read(p.credit_scores,64) == scores
    assert struct.unpack('<i',m.read(p.hero+0x170,4))[0] == 250
    assert struct.unpack('<I',m.read(mode.config+4,4))[0] == 4
    m.put(mode.config+12,'I',2); assert mode.poll(m) == ('credits',amount)
    mode.disable_all(m); assert not m.active_patches


@pytest.mark.parametrize('condition',['score-invalid','score-overflow','balance-negative','balance-overflow','sentinel','amount','pair'])
def test_credits_reject_invalid_source_balance_without_writes(condition):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    m = CreditsMemory(); p = m.profile; amount = 100
    if condition == 'score-invalid': m.put(p.credit_scores,'i',-1)
    elif condition == 'score-overflow':
        m.put(p.credit_scores,'i',0x7fffffff); m.put(p.credit_scores+4,'i',1); m.put(p.credit_types+4,'i',2)
    elif condition == 'balance-negative': m.put(p.hero+0x170,'i',501)
    elif condition == 'balance-overflow': m.put(p.hero+0x170,'i',-0x7fffffff)
    elif condition == 'sentinel': m.put(p.credit_scores+60,'i',0)
    elif condition == 'amount': amount = 1
    elif condition == 'pair': m.put(m.entry+0x34,'I',0)
    with pytest.raises(BackendError): Progression().submit(m,'credits',amount)
    assert not m.writes and not m.active_patches


def test_worker_credits_respects_backup_and_reports_full_currency_name(tmp_path):
    from unepic_trainer.ui import Worker
    from unepic_trainer.backend import BackendError
    worker = Worker(tmp_path,None); m = CreditsMemory(); m.identity = object(); worker.backend = m
    worker._refresh = lambda: None
    errors=[]; statuses=[]; worker.operation_failed.connect(errors.append); worker.status_changed.connect(statuses.append)
    def fail(): raise BackendError('Backup unavailable')
    worker._backup_before_change = fail; worker.dispatch('credits',100)
    assert errors == ['Backup unavailable'] and not m.writes
    worker._backup_before_change = lambda: None; worker.dispatch('credits',100)
    m.put(worker.progression.config+12,'I',2); worker._poll_progression(m)
    assert statuses[-1] == 'Added 100 Unepic Credits'
