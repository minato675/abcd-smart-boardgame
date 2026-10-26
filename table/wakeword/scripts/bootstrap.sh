#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${WAKEWORD_VENV:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python 3.11+ is required; set PYTHON_BIN to its executable." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11+ is required")
PY

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("existing .venv uses Python < 3.11; remove it or set WAKEWORD_VENV")
PY

PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV_DIR/bin/python" -m pip install --requirement "$ROOT_DIR/requirements.lock"
PIP_DISABLE_PIP_VERSION_CHECK=1 "$VENV_DIR/bin/python" -m pip install --no-deps --no-build-isolation --editable "$ROOT_DIR"

if [[ ! -f "$ROOT_DIR/config/development.yaml" ]]; then
  echo "Missing config/development.yaml" >&2
  exit 1
fi

"$VENV_DIR/bin/python" -m wakeword_module.manifest \
  --config "$ROOT_DIR/config/development.yaml" \
  --allow-unverified

echo "Setup complete."
echo "Run: $VENV_DIR/bin/python -m pytest"
echo "Run: $VENV_DIR/bin/python -m wakeword_module --config $ROOT_DIR/config/development.yaml"
