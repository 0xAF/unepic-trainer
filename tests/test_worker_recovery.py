import os
import time
from PySide6.QtWidgets import QApplication


def wait_for(app,predicate):
    deadline = time.monotonic()+5
    while not predicate() and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_failed_detach_keeps_window_and_worker_alive(monkeypatch):
    from unepic_trainer import ui
    from unepic_trainer.backend import BackendError
    from unepic_trainer.processes import identify

    class RefusingBackend:
        def __init__(self):
            self.identity = identify(os.getpid())
            self.unsafe = True
            self.attempts = 0

        def detach(self):
            self.attempts += 1
            if self.attempts == 1:
                raise BackendError('Restore required before detaching')
            self.identity = None

    monkeypatch.setattr(ui,'Backend',RefusingBackend)
    app = QApplication.instance() or QApplication([])
    window = ui.Window()
    window.show()
    try:
        window.close()
        wait_for(app,lambda:'Restore required' in window.error.text() and not window._closing)
        assert window.isVisible()
        assert window.thread.isRunning()
        assert not window.heal_button.isEnabled()
    finally:
        window.close()
        wait_for(app,lambda:not window.thread.isRunning())
