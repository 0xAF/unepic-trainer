import struct
import pytest
from test_minions import MinionMemory


class SaveMemory(MinionMemory):
    def __init__(self):
        super().__init__(); p = self.profile
        self.put(p.campaign_mode,'I',0); self.put(p.simulation_flag,'I',0)
        self.put(p.custom_map,'I',0); self.put(p.save_blocked,'I',0)
        self.put(p.player_count,'i',1); self.put(p.active_hero,'Q',p.hero)
        self.put(p.save_slot,'i',0); self.put_code(p.save_actions,b'\0'*16)
        self.put_code(self.room+0x24af4,b'\0'*12)
        self.put_code(p.save_dispatch_store,p.save_dispatch_original)
        self.put_code(p.save_writer_store,p.save_writer_original)


@pytest.mark.parametrize('slot',range(9))
def test_manual_save_queues_only_normal_request_and_reports_consumption(slot):
    from unepic_trainer.saving import SaveGame
    from unepic_trainer.backend import BackendError
    memory = SaveMemory(); memory.put(memory.profile.save_slot,'i',slot)
    mode = SaveGame(); mode.submit(memory)
    assert mode.pending and mode.slot == slot
    assert memory.writes == [(memory.profile.save_actions+12,struct.pack('<I',2))]
    with pytest.raises(BackendError,match='pending'): mode.submit(memory)
    memory.writes.clear()
    assert mode.poll(memory) is None and memory.writes == []
    memory.put(memory.profile.save_actions+12,'I',0)
    assert mode.poll(memory) == slot and not mode.pending
    assert mode.poll(memory) is None and memory.writes == []


@pytest.mark.parametrize('condition',['campaign','simulation','custom','blocked','multi','wrong_hero',
    'slot_low','slot_high','exit','room_load','load','existing','dead','integrity','code','room'])
def test_invalid_save_requests_make_no_writes(condition):
    from unepic_trainer.saving import SaveGame
    from unepic_trainer.backend import BackendError
    memory = SaveMemory(); p = memory.profile
    fields = {'campaign':(p.campaign_mode,'I',1),'simulation':(p.simulation_flag,'I',1),
        'custom':(p.custom_map,'I',1),'blocked':(p.save_blocked,'I',1),'multi':(p.player_count,'i',2),
        'wrong_hero':(p.active_hero,'Q',p.hero+4),'slot_low':(p.save_slot,'i',-1),
        'slot_high':(p.save_slot,'i',9),'exit':(p.save_actions,'I',1),'room_load':(p.save_actions+4,'I',1),
        'load':(p.save_actions+8,'I',1),'existing':(p.save_actions+12,'I',1),
        'dead':(0x1004ec,'f',0),'integrity':(p.penalty_flag,'I',1),'room':(p.hero+0x197c0,'Q',0)}
    if condition == 'code': memory.put_code(p.save_writer_store,b'\0'*16)
    else: memory.put(*fields[condition])
    with pytest.raises(BackendError): SaveGame().submit(memory)
    assert memory.writes == []


def test_failed_write_clears_request_and_failed_clear_requires_recovery():
    from unepic_trainer.saving import SaveGame
    from unepic_trainer.backend import BackendError
    memory = SaveMemory(); mode = SaveGame(); memory.fail_at = memory.profile.save_actions+12
    with pytest.raises(BackendError): mode.submit(memory)
    assert memory.read(memory.profile.save_actions+12,4) == b'\0'*4
    assert not mode.pending and not memory.unsafe
    class FailedClear(SaveMemory):
        fail = True
        def write(self,address,data):
            super().write(address,data)
            if address == self.profile.save_actions+12 and self.fail:
                raise BackendError('Injected persistent write failure')
    memory = FailedClear(); mode = SaveGame()
    with pytest.raises(BackendError): mode.submit(memory)
    assert memory.unsafe and mode.pending
    memory.fail = False; mode.cancel(memory)
    assert not memory.unsafe and not mode.pending


def test_disconnect_cancels_only_our_unprocessed_request():
    from unepic_trainer.saving import SaveGame
    memory = SaveMemory(); mode = SaveGame()
    mode.submit(memory); mode.cancel(memory)
    assert not mode.pending and memory.read(memory.profile.save_actions+12,4) == b'\0'*4
    mode.submit(memory); memory.put(memory.profile.save_actions+12,'I',1)
    memory.writes.clear(); mode.cancel(memory)
    assert memory.writes == [] and not mode.pending
    assert memory.read(memory.profile.save_actions+12,4) == struct.pack('<I',1)


def test_worker_save_uses_backup_then_read_only_polling_and_cleanup(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from unepic_trainer import ui
    from unepic_trainer.backend import BackendError
    worker = ui.Worker(tmp_path,None); memory = SaveMemory(); worker.backend = memory
    memory.identity = SimpleNamespace(pid=1,executable='/tmp/save-fixture')
    memory.live = memory.stopped; memory.detach = lambda: setattr(memory,'identity',None)
    errors=[]; pending=[]; statuses=[]
    worker.operation_failed.connect(errors.append); worker.save_pending.connect(pending.append)
    worker.status_changed.connect(statuses.append)
    def fail(): raise BackendError('Backup unavailable')
    worker._backup_before_change = fail; worker.dispatch('save-game',None)
    assert errors == ['Backup unavailable'] and not memory.writes
    errors.clear(); worker._backup_before_change = lambda: setattr(worker,'backup','saved')
    worker.dispatch('save-game',None)
    assert not errors and pending[-1] and worker.backup == 'saved'
    memory.put(memory.profile.save_actions+12,'I',0); memory.writes.clear()
    worker._live_snapshot()
    assert not pending[-1] and memory.writes == []
    assert 'processed' in statuses[-1] and 'saved' not in statuses[-1].lower()
    worker.dispatch('save-game',None); assert pending[-1]
    monkeypatch.setattr(ui,'is_current',lambda identity: True)
    worker.dispatch('detach',None)
    assert not errors and not pending[-1] and memory.identity is None
    assert memory.read(memory.profile.save_actions+12,4) == b'\0'*4


@pytest.mark.parametrize('action,blocked',[('save-game','progression'),('gold','saving'),('level-up','saving')])
def test_worker_serializes_character_changes_and_saving(tmp_path,action,blocked):
    from unepic_trainer.ui import Worker
    worker = Worker(tmp_path,None); memory = SaveMemory(); worker.backend = memory
    memory.identity = object()
    getattr(worker,blocked).pending = True
    errors = []; worker.operation_failed.connect(errors.append)
    worker.dispatch(action,100 if action == 'gold' else None)
    assert len(errors) == 1 and 'pending' in errors[0]
    assert not memory.writes and not memory.active_patches
