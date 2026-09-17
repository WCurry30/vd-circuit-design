#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
bash "${ROOT}/experiments/scripts/install_third_party.sh"
python3 -m venv "${ROOT}/.runtime/venv"
"${ROOT}/.runtime/venv/bin/python" -m pip install --upgrade pip
"${ROOT}/.runtime/venv/bin/python" -m pip install -r "${ROOT}/experiments/configs/requirements.runtime.lock.txt"
echo "Runtime ready at ${ROOT}/.runtime"
