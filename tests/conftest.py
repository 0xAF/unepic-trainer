from dataclasses import replace
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

import pytest


@pytest.fixture
def target(tmp_path):
    if not shutil.which('gcc') or not shutil.which('gdb'):
        pytest.skip('GCC and GDB required for integration test')
    from unepic_trainer.processes import identify
    from unepic_trainer.profiles import Profile
    binary = tmp_path / 'target'
    subprocess.run(['gcc','-g','-O0','-fno-pie','-no-pie',
                    str(Path(__file__).parent/'fixtures/target.c'),'-o',str(binary)],check=True)
    proc = subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    data = json.loads(proc.stdout.readline())
    profile = replace(Profile(), sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                      **{k:v for k,v in data.items() if k not in ('pid','value')})
    try:
        yield proc, data, identify(proc.pid), profile
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)
        proc.stdin.close()
        proc.stdout.close()


def attach_or_skip(backend, identity):
    from unepic_trainer.backend import BackendError
    try:
        backend.attach(identity)
    except BackendError as error:
        if 'Operation not permitted' in str(error):
            pytest.skip('Sandbox denies ptrace: ' + str(error))
        raise
