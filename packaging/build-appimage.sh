#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[[ "$(uname -m)" == x86_64 ]] || { echo 'Only x86_64 builds are supported' >&2; exit 1; }
version="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
if [[ -n "${RELEASE_TAG:-}" && "$RELEASE_TAG" != "v$version" ]]; then
    echo "Tag $RELEASE_TAG does not match package version v$version" >&2
    exit 1
fi
mkdir -p build/appimage-tools dist
download_checked() {
    local url="$1" file="$2" checksum="$3"
    if [[ ! -f "$file" ]]; then
        curl --fail --location --retry 3 "$url" --output "$file"
    fi
    printf '%s  %s\n' "$checksum" "$file" | sha256sum --check --status
    chmod +x "$file"
}
download_checked \
    https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage \
    build/appimage-tools/appimagetool.AppImage \
    ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0
download_checked \
    https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-x86_64 \
    build/appimage-tools/runtime-x86_64 \
    156f4bdbde9c52d01814600013e0a273f0118dc2de98975f3c8c63427ec79074
rm -rf -- build/installed
python -m pip install --no-deps --no-build-isolation --target build/installed .
export PYTHONPATH="$PWD/build/installed:$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
export PYINSTALLER_CONFIG_DIR="$PWD/build/pyinstaller-cache"
python -m PyInstaller --noconfirm --clean --onedir --name unepic-trainer \
    --paths src --copy-metadata unepic-trainer \
    --distpath build/frozen --workpath build/pyinstaller --specpath build \
    packaging/launcher.py
appdir=build/UnepicTrainer.AppDir
rm -rf -- "$appdir"
mkdir -p "$appdir/usr/bin" "$appdir/usr/share/doc/unepic-trainer"
cp -a build/frozen/unepic-trainer "$appdir/usr/bin/"
cp packaging/AppRun "$appdir/AppRun"
chmod +x "$appdir/AppRun"
cp packaging/unepic-trainer.desktop packaging/unepic-trainer.svg "$appdir/"
ln -s unepic-trainer.svg "$appdir/.DirIcon"
cp LICENSE THIRD_PARTY_NOTICES.md "$appdir/usr/share/doc/unepic-trainer/"
python packaging/collect-licenses.py "$appdir"
desktop-file-validate "$appdir/unepic-trainer.desktop"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 build/appimage-tools/appimagetool.AppImage \
    --runtime-file build/appimage-tools/runtime-x86_64 "$appdir" \
    "dist/Unepic-Trainer-$version-x86_64.AppImage"
chmod +x "dist/Unepic-Trainer-$version-x86_64.AppImage"
(cd dist && sha256sum "Unepic-Trainer-$version-x86_64.AppImage" > SHA256SUMS)
