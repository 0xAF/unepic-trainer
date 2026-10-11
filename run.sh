#!/usr/bin/env bash
set -euo pipefail
trainer_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$trainer_root"
export PYTHONPATH="$trainer_root/src${PYTHONPATH:+:$PYTHONPATH}"
trainer_python=python
if [[ -x "$trainer_root/.venv/bin/python" ]]; then
    trainer_python="$trainer_root/.venv/bin/python"
fi
exec "$trainer_python" -m unepic_trainer --project-dir "$trainer_root" "$@"
