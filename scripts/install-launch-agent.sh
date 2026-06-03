#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="$ROOT_DIR/launchd/com.jolyi.codex-status-light.plist.template"
TARGET="$HOME/Library/LaunchAgents/com.jolyi.codex-status-light.plist"
LOG_DIR="$HOME/.codex/log"

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

python3 - "$TEMPLATE" "$TARGET" "$ROOT_DIR" "$HOME" <<'PY'
from pathlib import Path
import sys

template_path = Path(sys.argv[1])
target_path = Path(sys.argv[2])
root_dir = sys.argv[3]
home_dir = sys.argv[4]

content = template_path.read_text(encoding="utf-8")
content = content.replace("/ABSOLUTE/PATH/TO/codex-status-light", root_dir)
content = content.replace("/Users/REPLACE_WITH_YOUR_USERNAME", home_dir)
target_path.write_text(content, encoding="utf-8")
PY

launchctl unload "$TARGET" 2>/dev/null || true
launchctl load "$TARGET"

echo "Installed LaunchAgent: $TARGET"
echo "Logs:"
echo "  $LOG_DIR/codex-status-light.out.log"
echo "  $LOG_DIR/codex-status-light.err.log"
