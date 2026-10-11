from pathlib import Path
import os
import platform
import shutil
import subprocess
import pytest


def test_trampoline_executes_on_real_cpu_without_debugger(tmp_path):
    if platform.machine() != 'x86_64' or not shutil.which('gcc'):
        pytest.skip('Linux x86-64 and GCC required')
    root = Path(__file__).resolve().parent.parent
    library = tmp_path/'target.so'
    subprocess.run(['gcc','-shared','-fPIC','-O0',str(root/'tests/fixtures/target.c'),
                    '-o',str(library)],check=True)
    environment = dict(os.environ,PYTHONPATH=str(root/'src'))
    result = subprocess.run(['python',str(root/'tests/fixtures/native_hook.py'),str(library)],
                            capture_output=True,text=True,env=environment,timeout=10)
    assert result.returncode == 0,result.stdout+result.stderr
    assert 'restore PASS' in result.stdout
