"""Exercise the actual Qt main loop in a disposable trainer process."""
import os
from pathlib import Path
import select
import signal
import subprocess
import sys

import pytest


def start_trainer(*,close=False,demo=False,gdb_pid_file=None,refuse_once=False):
    debugger = ''
    if gdb_pid_file is not None:
        debugger = f'''
    from pathlib import Path
    from pygdbmi.gdbcontroller import GdbController
    result.worker.backend._gdb = GdbController(command=['gdb','--nx','--quiet','--interpreter=mi3'])
    Path({str(gdb_pid_file)!r}).write_text(str(result.worker.backend._gdb.gdb_process.pid))
'''
    code = f'''
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from unepic_trainer import ui
if {refuse_once!r}:
    real_backend = ui.Backend
    class RefusingBackend(real_backend):
        refused = False
        def detach(self):
            if not self.refused:
                self.refused = True
                raise ui.BackendError('Restore required before detaching')
            super().detach()
    ui.Backend = RefusingBackend
real_window = ui.Window
def window(*args,**kwargs):
    result = real_window(*args,**kwargs)
{debugger}
    if {refuse_once!r}:
        result.worker.shutdown_rejected.connect(lambda: print('REJECTED',flush=True))
    # Do not depend on Qt's implicit last-window shutdown policy.
    QApplication.instance().setQuitOnLastWindowClosed(False)
    QTimer.singleShot(0,lambda: print('READY',flush=True))
    {'QTimer.singleShot(100,result.close)' if close else ''}
    return result
ui.Window = window
raise SystemExit(ui.main())
'''
    env = dict(os.environ,QT_QPA_PLATFORM='offscreen',
               PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    args = [sys.executable,'-c',code]+(['--demo'] if demo else [])
    proc = subprocess.Popen(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            text=True,start_new_session=True)
    ready,_,_ = select.select([proc.stdout],[],[],5)
    if not ready or proc.stdout.readline().strip() != 'READY':
        proc.kill(); output=proc.communicate(timeout=3)
        pytest.fail(f'Trainer did not start: {output}')
    return proc


@pytest.mark.parametrize('demo',[False,True])
def test_window_close_ends_cli_process(demo):
    proc = start_trainer(close=True,demo=demo)
    try:
        output = proc.communicate(timeout=3)
        assert proc.returncode == 0, output
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=3)


@pytest.mark.parametrize('termination',[None,signal.SIGINT])
def test_cli_shutdown_also_reaps_its_gdb_child(tmp_path,termination):
    pid_file = tmp_path/'debugger.pid'
    proc = start_trainer(close=termination is None,gdb_pid_file=pid_file)
    gdb_pid = int(pid_file.read_text())
    try:
        if termination is not None:
            # A terminal interrupt reaches the debugger's process group too.
            os.killpg(proc.pid,termination)
        output = proc.communicate(timeout=3)
        assert proc.returncode == 0,output
        assert not Path(f'/proc/{gdb_pid}').exists()
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=3)
        if Path(f'/proc/{gdb_pid}').exists():
            os.kill(gdb_pid,signal.SIGKILL)


def test_terminal_signal_keeps_failed_recovery_alive_until_retry():
    proc = start_trainer(refuse_once=True)
    try:
        proc.send_signal(signal.SIGINT)
        ready,_,_ = select.select([proc.stdout],[],[],3)
        assert ready and proc.stdout.readline().strip() == 'REJECTED'
        assert proc.poll() is None
        proc.send_signal(signal.SIGINT)
        output = proc.communicate(timeout=3)
        assert proc.returncode == 0, output
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=3)


@pytest.mark.parametrize('demo',[False,True])
@pytest.mark.parametrize('termination',[signal.SIGINT,signal.SIGTERM])
def test_terminal_signal_closes_window_and_ends_cli_process(demo,termination):
    proc = start_trainer(demo=demo)
    try:
        proc.send_signal(termination)
        output = proc.communicate(timeout=3)
        assert proc.returncode == 0, output
        assert 'KeyboardInterrupt' not in output[1]
    finally:
        if proc.poll() is None:
            proc.kill(); proc.communicate(timeout=3)
