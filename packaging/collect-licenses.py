"""Retain dependency and distribution notices with the frozen application."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import subprocess
import sys

output = Path(sys.argv[1]) / 'usr/share/doc/unepic-trainer/licenses'
output.mkdir(parents=True, exist_ok=True)
for package in ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
                'pygdbmi', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph', 'packaging'):
    info = distribution(package)
    for item in info.files or []:
        if any(word in str(item).lower() for word in ('license', 'copying', 'notice')):
            source = Path(info.locate_file(item))
            if source.is_file():
                target = output / package / str(item).replace('../', '')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
shutil.copy2('/usr/local/lib/python3.12/LICENSE.txt', output / 'Python-LICENSE.txt')
for source in Path('/usr/share/doc').glob('*/copyright'):
    target = output / 'Debian' / source.parent.name / 'copyright'
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                'https://raw.githubusercontent.com/AppImage/type2-runtime/8f39b89e2ac31e1640b3d3f7e9a5108e6ce805fa/LICENSE',
                '--output', str(output / 'AppImage-runtime-LICENSE')], check=True)
# PySide wheels declare their licenses but omit the full texts. Retain the
# matching upstream release's license directory explicitly.
qt_notices = output / 'Qt-PySide6-6.11.2'
qt_notices.mkdir(exist_ok=True)
for name in ('Apache-2.0.txt', 'BSD-3-Clause.txt', 'GFDL-1.3-no-invariants-only.txt',
             'GPL-2.0-only.txt', 'GPL-3.0-only.txt', 'LGPL-3.0-only.txt',
             'LicenseRef-Qt-Commercial.txt', 'Qt-GPL-exception-1.0.txt'):
    subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                    'https://raw.githubusercontent.com/pyside/pyside-setup/v6.11.2/LICENSES/' + name,
                    '--output', str(qt_notices / name)], check=True)
