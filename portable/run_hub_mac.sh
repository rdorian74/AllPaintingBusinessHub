#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/master-dashboard/venv/bin/python"
if [[ -x "${PYTHON}" ]]; then
  "${PYTHON}" "${ROOT}/master-dashboard/app.py"
else
  python3 "${ROOT}/master-dashboard/app.py"
fi
