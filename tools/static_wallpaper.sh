#!/usr/bin/env bash
# Keep the desktop's own wallpaper in step with the live one.
#
# GNOME draws its configured wallpaper itself in the activities overview (the three-finger
# swipe) and behind the lock screen, where the live window does not appear. This sets that
# wallpaper to a still frame of the ASCII picture, and puts the old one back on 'restore'.
#
# usage: tools/static_wallpaper.sh set [eyes.py options...]
#        tools/static_wallpaper.sh restore
set -u
DIR="$(cd "$(dirname "$0")/.." && pwd)"
STATE="${XDG_DATA_HOME:-$HOME/.local/share}/eyes-desktop"
SAVED="$STATE/previous-wallpaper"
SCHEMA=org.gnome.desktop.background

have_gnome() {
  command -v gsettings >/dev/null 2>&1 && gsettings list-schemas 2>/dev/null | grep -qx "$SCHEMA"
}

case "${1:-}" in
  set)
    if ! have_gnome; then
      echo "note: no GNOME background settings here; the overview keeps its own wallpaper"
      exit 0
    fi
    mkdir -p "$STATE"
    if [ ! -f "$SAVED" ]; then             # remember the user's wallpaper, once
      for key in picture-uri picture-uri-dark picture-options; do
        if gsettings list-keys "$SCHEMA" | grep -qx "$key"; then
          printf '%s=%s\n' "$key" "$(gsettings get "$SCHEMA" "$key")"
        fi
      done > "$SAVED"
    fi
    # a new file name each time: GNOME caches wallpapers by their URI
    OUT="$STATE/wallpaper-$(date +%s).png"
    if ! python3 "$DIR/eyes.py" --snapshot "$OUT" "${@:2}" >/dev/null; then
      echo "note: could not render the still wallpaper; the overview keeps the old one"
      exit 0
    fi
    gsettings set "$SCHEMA" picture-uri "file://$OUT"
    if gsettings list-keys "$SCHEMA" | grep -qx picture-uri-dark; then
      gsettings set "$SCHEMA" picture-uri-dark "file://$OUT"
    fi
    gsettings set "$SCHEMA" picture-options zoom
    for f in "$STATE"/wallpaper-*.png; do
      [ "$f" != "$OUT" ] && rm -f -- "$f"
    done
    echo "Desktop wallpaper set to a still of the ASCII picture (shown in the activities overview)"
    ;;
  restore)
    if [ -f "$SAVED" ] && have_gnome; then
      while IFS='=' read -r key value; do
        [ -n "$key" ] && [ -n "$value" ] && gsettings set "$SCHEMA" "$key" "$value"
      done < "$SAVED"
      rm -f -- "$SAVED"
      echo "Previous desktop wallpaper restored"
    fi
    rm -f -- "$STATE"/wallpaper-*.png
    ;;
  *)
    echo "usage: $0 set|restore" >&2
    exit 2
    ;;
esac
