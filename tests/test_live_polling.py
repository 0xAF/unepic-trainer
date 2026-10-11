"""Periodic display updates must not interrupt gameplay or change memory."""
from contextlib import contextmanager
from types import SimpleNamespace
import os

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest

from test_minions import MinionMemory


@pytest.mark.parametrize('energy_enabled',[False,True])
def test_periodic_poll_reads_player_and_pets_without_stopping_or_writing(
        tmp_path,monkeypatch,energy_enabled):
    from PySide6.QtWidgets import QApplication
    from unepic_trainer import ui
    app = QApplication.instance() or QApplication([])
    worker = ui.Worker(tmp_path,None)
    memory = MinionMemory()
    memory.identity = SimpleNamespace(pid=1)
    worker.backend = memory
    worker.energy_lock = SimpleNamespace(active=energy_enabled)
    monkeypatch.setattr(ui,'is_current',lambda identity: True)

    class Reader:
        profile = memory.profile
        read = memory.read

        @contextmanager
        def stopped(self):
            yield self

    @contextmanager
    def live():
        yield Reader()

    def forbidden_stop():
        pytest.fail('Periodic polling must not stop the target')

    memory.live = live
    memory.stopped = forbidden_stop
    heroes = []; pets = []; errors = []
    worker.snapshot_updated.connect(heroes.append)
    worker.minions_updated.connect(pets.append)
    worker.operation_failed.connect(errors.append)
    for _ in range(3):
        worker.poll()
    assert not errors
    assert len(heroes) == 3 and heroes[-1].current_hp == 75.5
    assert len(pets) == 3 and pets[-1][0].energy == 25
    assert memory.writes == []


def test_denied_live_access_pauses_only_for_explicit_refresh(tmp_path,monkeypatch):
    from unepic_trainer import ui
    from unepic_trainer.backend import LiveReadUnavailable
    worker = ui.Worker(tmp_path,None); memory = MinionMemory()
    memory.identity = SimpleNamespace(pid=1)
    worker.backend = memory
    monkeypatch.setattr(ui,'is_current',lambda identity: True)
    attempts = []; stops = []
    @contextmanager
    def live():
        attempts.append(True)
        raise LiveReadUnavailable('Permission denied')
        yield
    @contextmanager
    def stopped():
        stops.append(True)
        yield memory
    memory.live = live; memory.stopped = stopped
    heroes = []; statuses = []
    worker.snapshot_updated.connect(heroes.append)
    worker.status_changed.connect(statuses.append)
    for _ in range(3): worker.poll()
    assert len(attempts) == 1 and not stops
    assert 'manual readings' in statuses[-1] and not heroes
    worker.dispatch('refresh',None)
    assert heroes[-1].current_hp == 75.5 and stops
    count = len(stops)
    for _ in range(3): worker.poll()
    assert len(stops) == count and not memory.writes


def test_transition_retries_live_sample_without_stopping(tmp_path,monkeypatch):
    from unepic_trainer import ui
    from unepic_trainer.backend import BackendError
    memory = MinionMemory(); memory.identity = SimpleNamespace(pid=1)
    worker = ui.Worker(tmp_path,None); worker.backend = memory
    monkeypatch.setattr(ui,'is_current',lambda identity: True)
    attempts = []
    class Reader:
        profile = memory.profile
        read = memory.read
        @contextmanager
        def stopped(self): yield self
    @contextmanager
    def live():
        attempts.append(True)
        if len(attempts) == 1:
            raise BackendError('Scene changed')
        yield Reader()
    memory.live = live
    memory.stopped = lambda: pytest.fail('Must not stop on a live read failure')
    heroes = []; errors = []
    worker.snapshot_updated.connect(heroes.append)
    worker.operation_failed.connect(errors.append)
    worker.poll()
    assert len(attempts) == 2 and heroes[-1].current_hp == 75.5
    assert not errors and not memory.writes
