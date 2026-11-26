#!/usr/bin/env bash
# Start the wallpaper in the background (stops a running copy first).
# Extra arguments go to eyes.py, e.g. ./start.sh --theme light
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="${XDG_CACHE_HOME:-$HOME/.cache}/eyes-desktop.log"
STATE="${XDG_DATA_HOME:-$HOME/.local/share}/eyes-desktop"
mkdir -p "$(dirname "$LOG")"

pkill -f "$DIR/eyes.py" 2>/dev/null
nohup python3 "$DIR/eyes.py" "$@" >"$LOG" 2>&1 &
echo "eyes-desktop started (log: $LOG)"

# keep the desktop's own (still) wallpaper matching, if install.sh set it up
if [ -f "$STATE/previous-wallpaper" ] || [ "${EYES_SET_STATIC:-0}" = 1 ]; then
  "$DIR/tools/static_wallpaper.sh" set "$@" >>"$LOG" 2>&1 &
fi
