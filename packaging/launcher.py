"""Frozen entry point; internal checks also run without a game installed."""
import os
import shutil
import sys

from unepic_trainer.runtime import gdb_launch_command, system_program_environment


if sys.argv[1:2] == ['--system-gdb']:
    executable = shutil.which('gdb')
    if executable is None:
        sys.exit('GDB is required: install the gdb package using your distribution package manager.')
    os.execvpe(executable, [executable, *sys.argv[2:]], system_program_environment())

if sys.argv[1:2] == ['--packaging-check']:
    import json
    from importlib.metadata import version
    from pathlib import Path
    from PySide6.QtCore import qVersion
    from pygdbmi.gdbcontroller import GdbController
    from unepic_trainer.runtime import default_data_directory

    controller = GdbController(command=gdb_launch_command())
    try:
        responses = controller.write('-gdb-version')
        assert any(row['type'] == 'result' and row['message'] == 'done' for row in responses)
        actual = Path(os.readlink(f'/proc/{controller.gdb_process.pid}/exe')).resolve()
        assert actual == Path(shutil.which('gdb')).resolve(), actual
        print(json.dumps({'version': version('unepic-trainer'), 'qt': qVersion(),
                          'gdb': str(actual), 'data_directory': str(default_data_directory())}))
    finally:
        controller.exit()
    sys.exit(0)

from unepic_trainer.ui import main

raise SystemExit(main())
