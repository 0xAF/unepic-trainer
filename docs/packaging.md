# AppImage packaging and releases

Target: native x86_64 Linux, glibc 2.36+. A pinned Python 3.12 / Debian 12 container
freezes the trainer with PyInstaller and packages an AppDir using appimagetool.
Python, Qt/PySide6 and pygdbmi are bundled; GDB is a host dependency.
Game files and raw research exports are not build inputs.

## Local build

Run from the repository root with Docker available:

```bash
docker build -t unepic-trainer-builder -f packaging/Dockerfile packaging
docker run --rm --init --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -e QT_QPA_PLATFORM=offscreen -e PYTHONPATH=/src/src \
  -v "$PWD:/src" unepic-trainer-builder \
  bash -c 'python -m pytest -q -rs && bash packaging/build-appimage.sh && python packaging/smoke.py dist/Unepic-Trainer-0.1.0-x86_64.AppImage'
```

Outputs: `dist/Unepic-Trainer-<version>-x86_64.AppImage` and `dist/SHA256SUMS`.
The container runs as your user so generated files remain writable.

Build inputs are pinned in the Dockerfile, requirements file and build script.
The continuous runtime asset is checksum-pinned; replacement upstream fails
verification instead of silently changing the build. Refresh that pin deliberately
when needed. Bit-for-bit reproducibility is not claimed.

## Verification

The full suite runs before packaging. The actual AppImage is checked for CLI help,
metadata, real system GDB/MI startup and identity, and extracted-artifact Qt startup
in demo/normal modes with graceful SIGTERM cleanup. CI repeats GUI checks with X11
under Xvfb as well as offscreen. These checks do not attach to Unepic.
Fixture attachment tests may skip when the host/container denies ptrace.

The frozen launcher restores host library paths before exec(GDB). Backups use a
writable XDG directory outside the mounted AppImage.

## Automated releases

`.github/workflows/build.yml` runs on main pushes, pull requests and manual dispatch,
uploading tested AppImage artifacts. A pushed `v*` tag also publishes a release.
Only the release job receives `contents: write`; it uses `GITHUB_TOKEN` and needs
no personal access token.

Update the package version and documentation, commit/push, then tag:

```bash
git tag -a v0.1.0 -m 'Unepic Trainer 0.1.0'
git push origin v0.1.0
```

A tag mismatch, failed test, checksum or smoke check prevents publication.
The release is drafted, assets uploaded, then published. Published assets are
not replaced on retries.

Dependency notices and source locations are described in
[third-party notices](../THIRD_PARTY_NOTICES.md). Before claiming complete game
coverage, verify the downloaded AppImage on a desktop with active hooks,
disconnect/close, room changes and save/reload.


## Version 0.1.0 verification (2026-10-12)

- Host Arch suite: 914 passed, no skips.
- Debian/Python 3.12 build suite: 914 passed, no skips.
- [Main CI](https://github.com/0xAF/unepic-trainer/actions/runs/38175774849): 914 passed in 14.97s, both GUI smoke modes passed.
- [Tag/release CI](https://github.com/0xAF/unepic-trainer/actions/runs/38175908260): 914 passed in 13.01s, offscreen/X11 checks and publication succeeded.
- [Published release](https://github.com/0xAF/unepic-trainer/releases/tag/v0.1.0): AppImage and SHA256SUMS downloaded, checksum and GitHub digest matched; system GDB/MI and demo/normal startup/cleanup passed on Arch.

Published AppImage: 74,000,888 bytes, SHA256
`8b0732bc666d4b0bfbeba2579364c950488b08ef57ab800573404f43b3366017`.
The local `dist/` copy is the downloaded release artifact. Actual-game attachment
and remaining gameplay scenarios are not established by these packaging checks.
