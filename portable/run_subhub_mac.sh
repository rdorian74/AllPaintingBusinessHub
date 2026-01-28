#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${ROOT}/subhub-dashboard/venv/bin/python"
if [[ -x "${PYTHON}" ]]; then
  "${PYTHON}" "${ROOT}/subhub-dashboard/app.py"
else
  python3 "${ROOT}/subhub-dashboard/app.py"
fi
