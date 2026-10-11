import struct
import pytest
from test_progression import ProgressionMemory


class KillPointsMemory(ProgressionMemory):
    def __init__(self):
        super().__init__(); p = self.profile
        self.put(p.hero+0x174,'i',8); self.put(p.hero+0x178,'i',1)
        self.put(p.hero+0x234,'I',0)
        self.put(p.custom_map,'I',0); self.put(p.player_count,'I',1)
        self.put(p.active_hero,'Q',p.hero)


def test_snapshot_reads_authoritative_kp_without_extra_memory_round_trips():
    from unepic_trainer.character import read_character
    m = KillPointsMemory(); m.reads.clear(); s = read_character(m)
    assert s.kill_points == 8 and s.kill_points_unlocked
    assert len(m.reads) <= 6 and not m.writes


@pytest.mark.parametrize('amount',[1,10,100])
def test_kp_queue_is_one_shot_and_does_not_modify_the_counter_externally(amount):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    m = KillPointsMemory(); p = m.profile; mode = Progression()
    before = m.read(p.hero+0x160,0x2c)
    mode.submit(m,'kill-points',amount)
    assert m.read(p.hero+0x160,0x2c) == before
    assert struct.unpack('<I',m.read(mode.config+4,4))[0] == 5
    assert mode.pending
    with pytest.raises(BackendError,match='pending'): mode.submit(m,'kill-points',amount)
    m.put(mode.config+12,'I',2); assert mode.poll(m) == ('kill-points',amount)
    mode.disable_all(m); assert not m.active_patches


@pytest.mark.parametrize('condition',['locked','full','negative','excess','custom','players','active','amount'])
def test_kp_invalid_context_never_installs_a_patch_or_writes(condition):
    from unepic_trainer.progression import Progression
    from unepic_trainer.backend import BackendError
    m = KillPointsMemory(); p = m.profile; amount = 1
    if condition == 'locked': m.put(p.hero+0x178,'i',0)
    elif condition == 'full': m.put(p.hero+0x174,'i',25)
    elif condition == 'negative': m.put(p.hero+0x174,'i',-1)
    elif condition == 'excess': m.put(p.hero+0x174,'i',26)
    elif condition == 'custom': m.put(p.custom_map,'I',1)
    elif condition == 'players': m.put(p.player_count,'I',2)
    elif condition == 'active': m.put(p.active_hero,'Q',p.hero+4)
    elif condition == 'amount': amount = 2
    with pytest.raises(BackendError): Progression().submit(m,'kill-points',amount)
    assert not m.writes and not m.active_patches


def test_worker_kp_requires_backup_serializes_saving_and_reports_capped_result(tmp_path):
    from unepic_trainer.ui import Worker
    from unepic_trainer.backend import BackendError
    w = Worker(tmp_path,None); m = KillPointsMemory(); m.identity = object(); w.backend = m
    w._refresh = lambda: None
    errors=[]; statuses=[]; w.operation_failed.connect(errors.append); w.status_changed.connect(statuses.append)
    def fail(): raise BackendError('Backup unavailable')
    w._backup_before_change=fail; w.dispatch('kill-points',1)
    assert errors == ['Backup unavailable'] and not m.writes
    w._backup_before_change=lambda: None; w.saving.pending=True; w.dispatch('kill-points',1)
    assert 'save' in errors[-1].lower() and not m.writes
    w.saving.pending=False; w.dispatch('kill-points',100)
    assert w.progression.pending
    m.put(w.progression.config+12,'I',2); w._poll_progression(m)
    assert 'Kill Points' in statuses[-1] and 'maximum 5 KP' in statuses[-1]
