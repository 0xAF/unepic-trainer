"""Verify the packaged debugger, Qt startup and normal signal cleanup."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

appimage = str(Path(sys.argv[1]).resolve())
env = dict(os.environ, APPIMAGE_EXTRACT_AND_RUN='1',
           QT_QPA_PLATFORM=os.environ.get('QT_QPA_PLATFORM', 'offscreen'))
subprocess.run([appimage, '--help'], env=env, check=True, timeout=30)
subprocess.run([appimage, '--packaging-check'], env=env, check=True, timeout=30)
with tempfile.TemporaryDirectory(prefix='appimage-smoke-', dir='build') as directory:
    directory = Path(directory).resolve()
    subprocess.run([appimage, '--appimage-extract'], cwd=directory,
                   capture_output=True, check=True, timeout=30)
    # Test the exact extracted artifact. Its AppRun execs the trainer, so its
    # exit status tests cleanup rather than the extract-and-run supervisor.
    launcher = str(directory / 'squashfs-root/AppRun')
    for mode in ('--demo', None):
        command = [launcher] + ([mode] if mode else [])
        process = subprocess.Popen(command, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            time.sleep(3)
            assert process.poll() is None, process.communicate()
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, (process.returncode, stdout, stderr)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate()
print('AppImage debugger, demo/normal Qt startup and SIGTERM cleanup passed.')
