#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${REPO_ROOT}/.runtime"
PYTHON_DIR="${RUNTIME_DIR}/python"
PYTHON_BIN="${PYTHON_DIR}/bin/python3"

mkdir -p "${RUNTIME_DIR}"

if [[ -x "${PYTHON_BIN}" ]]; then
  echo "Using bundled Python at ${PYTHON_BIN}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
  echo "Using system Python at ${PYTHON_BIN}"
else
  echo "No Python found. Bootstrapping with uv..."
  UV_VERSION="0.4.30"
  ARCH="$(uname -m)"
  if [[ "${ARCH}" == "arm64" ]]; then
    UV_TARBALL="uv-aarch64-apple-darwin.tar.gz"
  else
    UV_TARBALL="uv-x86_64-apple-darwin.tar.gz"
  fi
  UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_TARBALL}"
  curl -L "${UV_URL}" -o "${RUNTIME_DIR}/${UV_TARBALL}"
  tar -xzf "${RUNTIME_DIR}/${UV_TARBALL}" -C "${RUNTIME_DIR}"
  UV_BIN="${RUNTIME_DIR}/uv"
  export UV_PYTHON_INSTALL_DIR="${PYTHON_DIR}"
  "${UV_BIN}" python install 3.11
  PYTHON_BIN="${PYTHON_DIR}/bin/python3"
fi

SERVICES=(
  "ai-agent"
  "bid-addendum-agent"
  "bid-system-v2/bid-center"
  "bid-system-v2/bid-email-scanner"
  "bid-system-v2/bid-pipedrive-sync"
  "bid-system-v2/bid-calendar"
  "bid-system-v2/bid-notifications"
  "bid-system-v2/bid-quote-sent-mover"
  "bid-system-v2/bid-followup-creator"
  "estimate-generator"
  "invoice-generator"
  "invoice_converter"
  "followup-manager"
  "payroll_app"
  "quickbooks-sync"
  "master-dashboard"
  "subhub-dashboard"
)

for service in "${SERVICES[@]}"; do
  service_path="${REPO_ROOT}/${service}"
  requirements="${service_path}/requirements.txt"
  venv_path="${service_path}/venv"
  if [[ ! -d "${venv_path}" ]]; then
    echo "Creating venv for ${service}..."
    "${PYTHON_BIN}" -m venv "${venv_path}"
  fi
  pip_bin="${venv_path}/bin/pip"
  if [[ -f "${requirements}" ]]; then
    echo "Installing requirements for ${service}..."
    "${pip_bin}" install --upgrade pip
    "${pip_bin}" install -r "${requirements}"
  fi
done

echo "✅ macOS portable setup complete."
