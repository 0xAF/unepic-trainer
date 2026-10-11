# Third-party components

MIT covers this project's original code, documentation and icon. Unepic, Steam and
their assets are not included and belong to their respective owners.

The AppImage includes unmodified libraries under their own licenses. Collected texts
are in `usr/share/doc/unepic-trainer/licenses/` inside it. Use `--appimage-extract`
to inspect the bundle or replace dynamically loaded libraries under
`usr/bin/unepic-trainer/_internal/`.

| Component | Upstream source / licensing |
|---|---|
| Python 3.12 | [Source and license](https://www.python.org/downloads/source/) |
| PySide6 / Shiboken6 6.11.2 | [Source](https://code.qt.io/cgit/pyside/pyside-setup.git/), [licenses](https://doc.qt.io/qtforpython-6/licenses.html) |
| Qt 6.11.2 | [Corresponding source](https://download.qt.io/archive/qt/6.11/6.11.2/), [licensing](https://doc.qt.io/qt-6/licensing.html) |
| pygdbmi 0.11.0.0 | [MIT-licensed source](https://github.com/cs01/pygdbmi) |
| PyInstaller bootloader 6.22.3 | [Source and generated-application license exception](https://github.com/pyinstaller/pyinstaller) |
| AppImage type-2 runtime | [Source and licenses](https://github.com/AppImage/type2-runtime) |
| Debian shared libraries | [Source packages](https://sources.debian.org/) |

GDB is installed separately and is not bundled. Build tools such as appimagetool
and pytest are not part of the application. [Packaging](docs/packaging.md) records
pinned inputs.
