#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"
python3 experiments/scripts/final_report.py --verify-only
PYTHONPATH=revision/development python3 -m unittest discover -s revision/development -p 'test_*.py' -q
