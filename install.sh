#!/usr/bin/env bash
# Make the eye wallpaper start on login (current user only, nothing system-wide), then start it now.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
FILE="$AUTOSTART/eyes-desktop.desktop"

if ! python3 -c "import tkinter, PIL.ImageTk, Xlib" 2>/dev/null; then
  echo "Missing packages. Install them once with:"
  echo "  sudo apt install python3-tk python3-pil python3-pil.imagetk python3-xlib"
  exit 1
fi
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
  echo "Note: this is a Wayland session; the eye only follows the mouse fully under 'Ubuntu on Xorg'."
fi

chmod +x "$DIR/start.sh" "$DIR/stop.sh" "$DIR/uninstall.sh"
mkdir -p "$AUTOSTART"
cat >"$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Eyes Desktop
Comment=ASCII eye wallpaper that follows the mouse
Exec="$DIR/start.sh"
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
EOF
echo "Autostart entry written: $FILE"
"$DIR/start.sh"
