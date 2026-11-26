#!/usr/bin/env bash
# Stop the eye wallpaper.
DIR="$(cd "$(dirname "$0")" && pwd)"
pkill -f "$DIR/eyes.py" && echo "eyes-desktop stopped" || echo "eyes-desktop was not running"
