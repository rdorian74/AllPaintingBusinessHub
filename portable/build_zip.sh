#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${ROOT}/dist"
ZIP_NAME="AllPaintingBusinessHub-portable.zip"

mkdir -p "${DIST}"
cd "${ROOT}"

echo "Building ${ZIP_NAME}..."
zip -r "${DIST}/${ZIP_NAME}" . -x "*.git*" "dist/*"
echo "✅ Zip created at ${DIST}/${ZIP_NAME}"
