import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('frozen', [False, True])
def test_gdb_command_uses_wrapper_only_when_frozen(monkeypatch, frozen):
    from unepic_trainer.runtime import gdb_launch_command
    monkeypatch.setattr(sys, 'frozen', frozen, raising=False)
    command = gdb_launch_command()
    expected = [sys.executable, '--system-gdb'] if frozen else ['gdb']
    assert command[:len(expected)] == expected
    assert '--interpreter=mi3' in command
    assert command[-2:] == ['-iex', 'set auto-load off']


def test_source_keeps_working_directory(monkeypatch, tmp_path):
    from unepic_trainer.runtime import default_data_directory
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.chdir(tmp_path)
    assert default_data_directory() == tmp_path


def test_frozen_data_directory_uses_xdg(monkeypatch, tmp_path):
    from unepic_trainer.runtime import default_data_directory
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
    assert default_data_directory() == tmp_path / 'unepic-trainer'


@pytest.mark.parametrize('xdg', ['', 'relative/path'])
def test_frozen_ignores_invalid_xdg(monkeypatch, xdg):
    from unepic_trainer.runtime import default_data_directory
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setenv('XDG_DATA_HOME', xdg)
    assert default_data_directory() == Path.home() / '.local/share/unepic-trainer'


@pytest.mark.parametrize('original', [None, '', '/system/library path'])
def test_external_program_environment_restores_library_path(monkeypatch, original):
    from unepic_trainer.runtime import system_program_environment
    monkeypatch.setenv('LD_LIBRARY_PATH', '/appimage/bundled-libraries')
    monkeypatch.setenv('QT_PLUGIN_PATH', '/appimage/qt-plugins')
    monkeypatch.delenv('LD_LIBRARY_PATH_ORIG', raising=False)
    if original is not None:
        monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', original)
    before = dict(os.environ)
    result = system_program_environment()
    assert result.get('LD_LIBRARY_PATH') == original
    assert 'QT_PLUGIN_PATH' not in result
    assert dict(os.environ) == before


def test_frozen_gdb_wrapper_runs_system_gdb():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root / 'src'),
               LD_LIBRARY_PATH='/missing/bundled-libraries')
    env.pop('LD_LIBRARY_PATH_ORIG', None)
    result = subprocess.run([sys.executable, str(root / 'packaging/launcher.py'),
                             '--system-gdb', '--version'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'GNU gdb' in result.stdout
