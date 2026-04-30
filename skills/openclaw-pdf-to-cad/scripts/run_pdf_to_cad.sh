#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PACKAGE_ROOT="${OPENCLAW_PDF_TO_CAD_HOME:-$REPO_ROOT}"

if [ -x "$SKILL_DIR/.venv/bin/python" ]; then
  PYTHON_BIN="$SKILL_DIR/.venv/bin/python"
elif [ -x "$PACKAGE_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$PACKAGE_ROOT/.venv/bin/python"
elif [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

"$PYTHON_BIN" "$SCRIPT_DIR/openclaw_pdf_to_cad.py" "$@"
