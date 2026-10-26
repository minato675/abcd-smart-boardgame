#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  printf '%s\n' \
    "Usage: $(basename "$0") [wakeword-module options]" \
    "" \
    "Starts wakeword_module with the Jetson USB microphone." \
    "Additional options are passed to the module."
}

fail() {
  printf 'run-shadow: %s\n' "$1" >&2
  exit 1
}

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${WAKEWORD_VENV:-$ROOT_DIR/.venv}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ -n "${WAKEWORD_CONFIG:-}" ]]; then
  CONFIG_PATH="$WAKEWORD_CONFIG"
elif [[ -f "$ROOT_DIR/config/shadow.yaml" ]]; then
  CONFIG_PATH="$ROOT_DIR/config/shadow.yaml"
else
  CONFIG_PATH="$ROOT_DIR/config/shadow.conf"
fi
[[ -f "$CONFIG_PATH" ]] || fail "configuration not found: $CONFIG_PATH"

load_ssafy() {
  local env_file="$1"
  local file_mode ssafy_value

  file_mode="$(stat -c '%a' -- "$env_file" 2>/dev/null)" ||
    fail "cannot inspect credential file: $env_file"
  [[ "$file_mode" == "600" ]] ||
    fail "credential file must have mode 600: $env_file"
  ssafy_value="$(awk -F= '$1 == "SSAFY" { sub(/^[^=]*=/, ""); print; exit }' "$env_file")"
  [[ -n "$ssafy_value" ]] ||
    fail "credential file does not contain SSAFY: $env_file"
  export SSAFY="$ssafy_value"
}

if [[ -z "${SSAFY:-}" ]]; then
  PROJECT_ENV="${WAKEWORD_ENV_FILE:-$ROOT_DIR/.env.shadow}"
  USER_HOME="$(getent passwd "$(id -u)" | awk -F: 'NR == 1 { print $6 }')"
  USER_ENV="${WAKEWORD_USER_ENV_FILE:-}"
  if [[ -z "$USER_ENV" && -n "$USER_HOME" ]]; then
    USER_ENV="${XDG_CONFIG_HOME:-$USER_HOME/.config}/wakeword/ssafy.env"
  fi

  if [[ -f "$PROJECT_ENV" ]]; then
    load_ssafy "$PROJECT_ENV"
  elif [[ -n "$USER_ENV" && -f "$USER_ENV" ]]; then
    load_ssafy "$USER_ENV"
  else
    fail "SSAFY is not set; create a mode-600 credential file at $PROJECT_ENV or $USER_ENV"
  fi
fi

command -v pactl >/dev/null 2>&1 ||
  fail "pactl is required to select the Jetson USB microphone"
if [[ -z "${XDG_RUNTIME_DIR:-}" ]]; then
  XDG_RUNTIME_DIR="/run/user/$(id -u)"
  export XDG_RUNTIME_DIR
fi
pactl info >/dev/null 2>&1 ||
  fail "PulseAudio/PipeWire is unavailable for this user"

SOURCE_LIST="$(pactl list short sources)" ||
  fail "could not list PulseAudio sources"
SELECTED_SOURCE="${WAKEWORD_PULSE_SOURCE:-${PULSE_SOURCE:-}}"
if [[ -z "$SELECTED_SOURCE" ]]; then
  SELECTED_SOURCE="$(printf '%s\n' "$SOURCE_LIST" | awk '$2 ~ /^alsa_input\.usb-/ { print $2; exit }')"
fi
if [[ -z "$SELECTED_SOURCE" ]]; then
  printf '%s\n' "run-shadow: no USB microphone source was found." >&2
  printf '%s\n' "$SOURCE_LIST" >&2
  exit 1
fi
if ! printf '%s\n' "$SOURCE_LIST" |
  awk -v wanted="$SELECTED_SOURCE" '$2 == wanted { found = 1 } END { exit found ? 0 : 1 }'; then
  fail "PulseAudio source not found: $SELECTED_SOURCE"
fi
export PULSE_SOURCE="$SELECTED_SOURCE"

PYTHON_BIN="$VENV_DIR/bin/python"
[[ -x "$PYTHON_BIN" ]] ||
  fail "Python environment not found at $VENV_DIR; install project dependencies first"

"$PYTHON_BIN" - "$CONFIG_PATH" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("run-shadow: PyYAML is missing; install project dependencies first", file=sys.stderr)
    raise SystemExit(1)

config_path = Path(sys.argv[1])
with config_path.open(encoding="utf-8") as config_file:
    config = yaml.safe_load(config_file) or {}

audio = config.get("audio") or {}
mqtt = config.get("mqtt") or {}
errors = []

if audio.get("device") != "pulse":
    errors.append("audio.device must be pulse")
if mqtt.get("username_env") != "SSAFY":
    errors.append("mqtt.username_env must be SSAFY")
if mqtt.get("password_env") != "SSAFY":
    errors.append("mqtt.password_env must be SSAFY")

if errors:
    for error in errors:
        print(f"run-shadow: {error}", file=sys.stderr)
    raise SystemExit(1)
PY

if command -v pgrep >/dev/null 2>&1; then
  RUNNING_PIDS="$(pgrep -u "$(id -u)" -f 'python.*-m wakeword_module' || true)"
  if [[ -n "$RUNNING_PIDS" ]]; then
    printf 'run-shadow: wakeword_module is already running (pid %s).\n' "$RUNNING_PIDS" >&2
    exit 0
  fi
fi

exec env PULSE_SOURCE="$PULSE_SOURCE" "$PYTHON_BIN" -m wakeword_module \
  --config "$CONFIG_PATH" "$@"
