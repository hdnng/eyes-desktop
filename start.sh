#!/usr/bin/env bash
# Start the eye wallpaper in the background (stops a running copy first).
# Extra arguments go to eyes.py, e.g. ./start.sh --theme light
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${XDG_CACHE_HOME:-$HOME/.cache}/eyes-desktop.log"
mkdir -p "$(dirname "$LOG")"

pkill -f "$DIR/eyes.py" 2>/dev/null
nohup python3 "$DIR/eyes.py" "$@" >"$LOG" 2>&1 &
echo "eyes-desktop started (log: $LOG)"
