#!/bin/bash

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 YYYY-MM-DD" >&2
  exit 1
fi

TARGET_DATE="$1"
if ! [[ "$TARGET_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "invalid date format: $TARGET_DATE (expected YYYY-MM-DD)" >&2
  exit 1
fi

BASE_DIR="${WORKSPACE_STORAGE_DIR:-$HOME/.vscode-server/data/User/workspaceStorage}"
if [[ ! -d "$BASE_DIR" ]]; then
  echo "workspaceStorage not found: $BASE_DIR" >&2
  exit 1
fi

NEXT_DATE="$(date -d "$TARGET_DATE + 1 day" +%Y-%m-%d)"

find "$BASE_DIR" \
  -mindepth 4 \
  -maxdepth 4 \
  -type d \
  -path "*/GitHub.copilot-chat/debug-logs/*" \
  -newermt "${TARGET_DATE} 00:00:00" \
  ! -newermt "${NEXT_DATE} 00:00:00" \
  | sort
