#!/bin/bash

set -euo pipefail

# One-time local setting:
# Set this to your VS Code workspaceStorage path on your machine.
export WORKSPACE_STORAGE_DIR="$HOME/.vscode-server/data/User/workspaceStorage"

# Usage:
#   ./start_ai_logview.sh [--port 5001]

PORT="5001"
PYTHON_BIN="python3"

usage() {
  echo "Usage: ./start_ai_logview.sh [--port PORT]"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      --port)
        if [[ $# -lt 2 ]]; then
          echo "missing value for --port" >&2
          exit 1
        fi
        PORT="$2"
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
  local finder_script="$2"

  if [[ ! -d "$workspace_storage" ]]; then
    echo "workspaceStorage not found: $workspace_storage" >&2
    echo "Edit WORKSPACE_STORAGE_DIR in this script to match your machine." >&2
    exit 1
  fi

  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "python command not found: $PYTHON_BIN" >&2
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

main() {
  parse_args "$@"
  local root_dir
  root_dir="$(cd "$(dirname "$0")" && pwd)"
  local finder_script="$root_dir/src_parse/find_debug_logs.sh"

  validate_runtime "$WORKSPACE_STORAGE_DIR" "$finder_script"

  echo "Start app: http://127.0.0.1:${PORT}/"
  "$PYTHON_BIN" "$root_dir/src_view/web_app.py" \
    --finder-script "$finder_script" \
    --host "127.0.0.1" \
    --port "$PORT"
}

main "$@"
