import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from types import SimpleNamespace
from test_minions import MinionMemory


def test_worker_actions_and_disconnect_restore_all_protection(tmp_path,monkeypatch):
    from PySide6.QtWidgets import QApplication
    from unepic_trainer import ui
    app = QApplication.instance() or QApplication([])
    worker = ui.Worker(tmp_path,None)
    memory = MinionMemory()
    memory.identity = SimpleNamespace(pid=1,executable='/tmp/unepic-fixture')
    memory.resume = lambda: None
    memory.detach = lambda: setattr(memory,'identity',None)
    worker.backend = memory
    worker._refresh = lambda: None
    worker._backup_before_change = lambda: setattr(worker,'backup','saved')
    monkeypatch.setattr(ui,'is_current',lambda identity: True)
    errors = []; states = []
    worker.operation_failed.connect(errors.append)
    worker.minion_state_changed.connect(lambda hp,en: states.append((hp,en)))
    for action in ('minion-heal','minion-god','minion-energy','god'):
        worker.dispatch(action,True)
    assert not errors and worker.backup == 'saved'
    assert worker.mode.active and worker.mode.minion_active and worker.energy_lock.active
    assert states[-1] == (True,True) and len(memory.active_patches) == 5
    worker.dispatch('detach',None)
    assert not errors and not memory.active_patches and memory.identity is None
    assert states[-1] == (False,False)


def test_backup_failure_prevents_minion_writes(tmp_path):
    from unepic_trainer import ui
    from unepic_trainer.backend import BackendError
    worker = ui.Worker(tmp_path,None); memory = MinionMemory()
    memory.identity = SimpleNamespace(pid=1)
    worker.backend = memory
    def fail(): raise BackendError('Backup unavailable')
    worker._backup_before_change = fail
    errors = []; worker.operation_failed.connect(errors.append)
    for action in ('minion-heal','minion-god','minion-energy'):
        worker.dispatch(action,True)
    assert errors == ['Backup unavailable']*3
    assert memory.writes == [] and not memory.active_patches
