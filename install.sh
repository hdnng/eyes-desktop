#!/usr/bin/env bash
# Make the wallpaper start on login (current user only, nothing system-wide), then start it now.
# Also sets the desktop's own wallpaper to a still frame of the picture, so the activities
# overview matches; pass --keep-wallpaper to leave it alone. uninstall.sh puts the old one back.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
STATIC=1
for arg in "$@"; do
  [ "$arg" = "--keep-wallpaper" ] && STATIC=0
done
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
FILE="$AUTOSTART/eyes-desktop.desktop"

if ! python3 -c "import tkinter, PIL.ImageTk, Xlib, numpy" 2>/dev/null; then
  echo "Missing Python packages. Install them once, for example:"
  echo "  Debian/Ubuntu: sudo apt install python3-tk python3-pil python3-pil.imagetk python3-xlib python3-numpy"
  echo "  Fedora:        sudo dnf install python3-tkinter python3-pillow-tk python3-xlib python3-numpy"
  echo "  Arch:          sudo pacman -S tk python-pillow python-xlib python-numpy"
  exit 1
fi
if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
  echo "Note: this is a Wayland session. The wallpaper runs, but the eyes can only follow the mouse"
  echo "everywhere in an X11 session (on Ubuntu: 'Ubuntu on Xorg' on the login screen)."
fi

chmod +x "$DIR/start.sh" "$DIR/stop.sh" "$DIR/uninstall.sh" "$DIR/tools/static_wallpaper.sh"
mkdir -p "$AUTOSTART"
cat >"$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Eyes Desktop
Comment=ASCII face wallpaper that follows the mouse
Exec="$DIR/start.sh"
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=3
EOF
echo "Autostart entry written: $FILE"
EYES_SET_STATIC=$STATIC "$DIR/start.sh"
if [ "$STATIC" = 1 ]; then
  echo "The activities overview will show a still of the picture in a moment (old wallpaper is saved)."
fi
