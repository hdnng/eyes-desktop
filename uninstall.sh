#!/usr/bin/env bash
# Stop the wallpaper, remove it from login autostart and put the old desktop wallpaper back.
DIR="$(cd "$(dirname "$0")" && pwd)"
"$DIR/stop.sh"
rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/eyes-desktop.desktop" && echo "Autostart entry removed"
"$DIR/tools/static_wallpaper.sh" restore
