"""Writable data paths and system-program isolation for frozen builds."""
import os
from pathlib import Path
import sys


def default_data_directory() -> Path:
    if not getattr(sys, 'frozen', False):
        return Path.cwd()
    configured = Path(os.environ.get('XDG_DATA_HOME') or '')
    base = configured if configured.is_absolute() else Path.home() / '.local/share'
    return base / 'unepic-trainer'


def system_program_environment() -> dict[str, str]:
    env = dict(os.environ)
    original = env.get('LD_LIBRARY_PATH_ORIG')
    if original is None:
        env.pop('LD_LIBRARY_PATH', None)
    else:
        env['LD_LIBRARY_PATH'] = original
    env.pop('QT_PLUGIN_PATH', None)
    env.pop('QT_QPA_PLATFORM_PLUGIN_PATH', None)
    return env


def gdb_launch_command() -> list[str]:
    options = ['--nx', '--quiet', '--interpreter=mi3', '-iex', 'set auto-load off']
    if getattr(sys, 'frozen', False):
        # The bundled launcher restores the host library path before exec(GDB).
        return [sys.executable, '--system-gdb', *options]
    return ['gdb', *options]
