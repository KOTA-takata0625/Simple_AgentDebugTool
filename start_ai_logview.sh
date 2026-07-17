#!/bin/bash

set -euo pipefail

# One-time local setting:
# Set this to your VS Code workspaceStorage path on your machine.
export WORKSPACE_STORAGE_DIR="$HOME/.vscode-server/data/User/workspaceStorage"

# Usage:
#   ./start_ai_logview.sh [YYYY-MM-DD] [--host 127.0.0.1] [--port 5001] [--python-bin python3]

DATE_ARG=""
HOST="127.0.0.1"
PORT="5001"
PYTHON_BIN="python3"
DATE=""

usage() {
  echo "Usage: ./start_ai_logview.sh [YYYY-MM-DD] [--date YYYY-MM-DD] [--host 127.0.0.1] [--port 5001] [--python-bin python3]"
  echo "workspaceStorage is configured in this script: WORKSPACE_STORAGE_DIR"
}

parse_args() {
  if [[ $# -gt 0 && "$1" != -* ]]; then
    DATE_ARG="$1"
    shift
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      --date)
        if [[ $# -lt 2 ]]; then
          echo "missing value for --date" >&2
          exit 1
        fi
        DATE_ARG="$2"
        shift 2
        ;;
      --host)
        if [[ $# -lt 2 ]]; then
          echo "missing value for --host" >&2
          exit 1
        fi
        HOST="$2"
        shift 2
        ;;
      --port)
        if [[ $# -lt 2 ]]; then
          echo "missing value for --port" >&2
          exit 1
        fi
        PORT="$2"
        shift 2
        ;;
      --python-bin)
        if [[ $# -lt 2 ]]; then
          echo "missing value for --python-bin" >&2
          exit 1
        fi
        PYTHON_BIN="$2"
        shift 2
        ;;
      *)
        echo "unknown option: $1" >&2
        exit 1
        ;;
    esac
  done
}

validate_runtime() {
  local workspace_storage="$1"
  local python_bin="$2"
  local finder_script="$3"

  if [[ ! -d "$workspace_storage" ]]; then
    echo "workspaceStorage not found: $workspace_storage" >&2
    echo "Edit WORKSPACE_STORAGE_DIR in this script to match your machine." >&2
    exit 1
  fi

  if ! command -v "$python_bin" >/dev/null 2>&1; then
    echo "python command not found: $python_bin" >&2
    exit 1
  fi

  if [[ ! -x "$finder_script" ]]; then
    if [[ -f "$finder_script" ]]; then
      chmod +x "$finder_script"
    else
      echo "finder script not found: $finder_script" >&2
      exit 1
    fi
  fi
}

build_sessions_index() {
  local root_dir="$1"
  local finder_script="$2"
  local index_file="$3"

  echo "[1/2] Build sessions index for date: $DATE"
  "$PYTHON_BIN" "$root_dir/src_parse/build_sessions_index.py" \
    --date "$DATE" \
    --finder-script "$finder_script" \
    --output "$index_file" \
    --ensure-extracted
}

start_app() {
  local root_dir="$1"
  local index_file="$2"
  local finder_script="$3"

  echo "[2/2] Start app"
  "$PYTHON_BIN" "$root_dir/src_view/web_app.py" \
    --sessions-index "$index_file" \
    --finder-script "$finder_script" \
    --host "$HOST" \
    --port "$PORT"
}

main() {
  local root_dir=""
  local workspace_storage=""
  local index_file=""
  local finder_script=""

  parse_args "$@"
  DATE="${DATE_ARG:-$(date +%F)}"
  root_dir="$(cd "$(dirname "$0")" && pwd)"
  workspace_storage="$WORKSPACE_STORAGE_DIR"
  index_file="$root_dir/data/sessions_index.json"
  finder_script="$root_dir/src_parse/find_debug_logs.sh"

  validate_runtime "$workspace_storage" "$PYTHON_BIN" "$finder_script"
  build_sessions_index "$root_dir" "$finder_script" "$index_file"
  start_app "$root_dir" "$index_file" "$finder_script"
}

main "$@"
