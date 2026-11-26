#!/usr/bin/env bash
# Stop the eye wallpaper and remove it from login autostart.
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/stop.sh"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/eyes-desktop.desktop" && echo "Autostart entry removed"
