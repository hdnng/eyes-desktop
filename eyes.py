#!/usr/bin/env python3
"""eyes-desktop: a live ASCII wallpaper for Ubuntu that watches the mouse.

Two scenes:
  face  (default) the GitHub avatar redrawn in ASCII: both eyes follow the pointer and blink,
        the water ripples where you click or glide, the hair drifts, specks twinkle and a soft
        light follows the pointer (scene_face.py)
  eye   the single ASCII eye of the profile card (scene_eye.py)

While the mouse rests, the eyes play the profile card's own routine. Needs an X11 session
(Ubuntu on Xorg) to see the pointer anywhere on screen; on Wayland it mostly idles.

usage: eyes.py [--scene face|eye] [--theme dark|light] [--monitor primary|N] [--window]
"""
import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path

import tkinter as tk
from Xlib import X, Xatom, display as xdisplay

from behaviour import Behaviour

ROOT = Path(__file__).resolve().parent
DEFAULTS = dict(scene="face", theme="dark", size=0.6, face_size=0.92, cell=5, position=[0.5, 0.5],
                monitor="primary", fps=24, ambient_fps=6, idle_after=8.0, background=None, font=None, effects={})
THEMES = {  # same palette as the profile card
    "dark": dict(bg="#0f2027", art="#9fd8e6", value="#7ee0c8"),
    "light": dict(bg="#f6f8fa", art="#203a43", value="#0a7d6c"),
}
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
         "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf"]


def get_monitors(d):
    try:
        if d.has_extension("RANDR"):
            res = d.xrandr_get_monitors(d.screen().root, is_active=True)
            mons = [dict(x=m.x, y=m.y, w=m.width_in_pixels, h=m.height_in_pixels, primary=bool(m.primary))
                    for m in res.monitors]
            if mons:
                return mons
    except Exception:
        pass
    s = d.screen()
    return [dict(x=0, y=0, w=s.width_in_pixels, h=s.height_in_pixels, primary=True)]


class App:
    def __init__(self, cfg, window_mode):
        self.cfg, self.window_mode = cfg, window_mode
        self.colors = dict(THEMES[cfg["theme"]])
        if cfg.get("background"):
            self.colors["bg"] = cfg["background"]
        self.font = cfg.get("font") or next((f for f in FONTS if os.path.exists(f)), None)
        if not self.font:
            sys.exit("No DejaVu Sans Mono font found; install fonts-dejavu-core or set \"font\" in config.json")

        self.x = xdisplay.Display()
        self.atom_type = self.x.intern_atom("_NET_WM_WINDOW_TYPE")
        self.atom_desktop = self.x.intern_atom("_NET_WM_WINDOW_TYPE_DESKTOP")
        self.desktop_cache = {}
        self.atoms = {n: self.x.intern_atom(n) for n in (
            "_NET_ACTIVE_WINDOW", "_NET_WM_STATE", "_NET_WM_STATE_MAXIMIZED_VERT",
            "_NET_WM_STATE_MAXIMIZED_HORZ", "_NET_WM_STATE_FULLSCREEN", "_NET_WM_STATE_HIDDEN")}
        self.hidden, self.next_cover = False, 0.0
        self.root = tk.Tk(className="eyes-desktop")
        self.root.title("eyes-desktop")
        self.root.configure(bg=self.colors["bg"])
        if not window_mode:
            self.root.wm_attributes("-type", "desktop")   # sit below every app window
        self.canvas = tk.Canvas(self.root, bg=self.colors["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.root.bind("<Escape>", lambda e: self.root.quit())
        self.canvas.bind("<Button-1>", lambda e: self.scene.click(e.x, e.y, time.monotonic()))
        signal.signal(signal.SIGTERM, lambda *a: self.root.quit())
        signal.signal(signal.SIGINT, lambda *a: self.root.quit())

        if cfg["scene"] == "eye":
            from scene_eye import EyeScene as Scene
        else:
            from scene_face import FaceScene as Scene
        self.scene = Scene(cfg, self.colors, self.font, self.canvas)

        now = time.monotonic()
        self.beh = Behaviour(cfg["idle_after"], now)
        self.last_tick, self.next_check = now, now + 3
        self.mons = None
        self.layout()

    def pick_monitor(self, mons):
        want = self.cfg["monitor"]
        if isinstance(want, int) and 0 <= want < len(mons):
            return mons[want]
        return next((m for m in mons if m["primary"]), mons[0])

    def layout(self):
        if self.window_mode:
            w, h = 1280, 720
            self.mons = [dict(x=0, y=0, w=w, h=h, primary=True)]
            self.root.geometry(f"{w}x{h}")
        else:
            self.mons = get_monitors(self.x)
            w = max(m["x"] + m["w"] for m in self.mons)
            h = max(m["y"] + m["h"] for m in self.mons)
            self.root.geometry(f"{w}x{h}+0+0")
        self.mon = self.pick_monitor(self.mons)
        self.canvas.delete("all")
        self.scene.layout(self.mon)

    def pointer(self):
        """(pointer in canvas coordinates or None, whether it is over the wallpaper itself)."""
        try:
            p = self.x.screen().root.query_pointer()
        except Exception:
            return None, False
        on_desktop = self.shows_wallpaper(p.child)
        if self.window_mode:
            return (p.root_x - self.root.winfo_rootx(), p.root_y - self.root.winfo_rooty()), on_desktop
        return (p.root_x, p.root_y), on_desktop

    def shows_wallpaper(self, wid):
        """True if the top-level window under the pointer is this wallpaper, the bare root, or
        another desktop-type window (such as GNOME's desktop icons); False over an app."""
        if wid in (0, X.NONE):
            return not self.window_mode
        if wid in self.desktop_cache:
            return self.desktop_cache[wid]
        result = False
        try:
            if wid == int(self.root.wm_frame(), 16) or wid == self.root.winfo_id():
                result = True
            else:
                win = self.x.create_resource_object("window", wid)
                todo = [win] + list(win.query_tree().children)   # the frame and the client it holds
                for w in todo[:8]:
                    prop = w.get_full_property(self.atom_type, Xatom.ATOM)
                    if prop is not None and self.atom_desktop in prop.value:
                        result = True
                        break
        except Exception:
            result = False
        if len(self.desktop_cache) > 256:
            self.desktop_cache.clear()
        self.desktop_cache[wid] = result
        return result

    def covered(self):
        """True when the focused window is maximised or fullscreen on our monitor, so the
        wallpaper cannot be seen and need not be drawn."""
        if self.window_mode:
            return False
        try:
            a = self.atoms
            root = self.x.screen().root
            prop = root.get_full_property(a["_NET_ACTIVE_WINDOW"], X.AnyPropertyType)
            if not prop or not prop.value or not prop.value[0]:
                return False
            win = self.x.create_resource_object("window", int(prop.value[0]))
            st = win.get_full_property(a["_NET_WM_STATE"], Xatom.ATOM)
            state = set(st.value) if st else set()
            if a["_NET_WM_STATE_HIDDEN"] in state:
                return False
            full = a["_NET_WM_STATE_FULLSCREEN"] in state or {
                a["_NET_WM_STATE_MAXIMIZED_VERT"], a["_NET_WM_STATE_MAXIMIZED_HORZ"]} <= state
            if not full:
                return False
            g = win.get_geometry()
            pos = root.translate_coords(win, 0, 0)
            cx, cy = pos.x + g.width / 2, pos.y + g.height / 2
            m = self.mon
            return m["x"] <= cx < m["x"] + m["w"] and m["y"] <= cy < m["y"] + m["h"]
        except Exception:
            return False

    def tick(self):
        now = time.monotonic()
        dt, self.last_tick = min(now - self.last_tick, 0.1), now
        if now >= self.next_cover:
            self.next_cover = now + 1.0
            self.hidden = self.covered()
        if self.hidden:                      # nothing to see: check again shortly, draw nothing
            self.root.after(500, self.tick)
            return
        ptr, self.beh.on_desktop = self.pointer()
        self.beh.update(now, dt, ptr, (self.mon["w"], self.mon["h"]), self.scene.focus)
        self.scene.frame(now, dt, self.beh)

        if now >= self.next_check and not self.window_mode:   # monitor plugged in or resolution changed
            self.next_check = now + 3
            if get_monitors(self.x) != self.mons:
                self.layout()

        spent = time.monotonic() - now
        self.root.after(max(1, int(1000 / self.cfg["fps"] - spent * 1000)), self.tick)

    def run(self):
        self.root.after(0, self.tick)
        self.root.mainloop()


def load_config(args):
    cfg = dict(DEFAULTS)
    path = Path(args.config) if args.config else ROOT / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text()))
    for k in ("scene", "theme", "size", "fps", "cell"):
        if getattr(args, k) is not None:
            cfg[k] = getattr(args, k)
    if args.monitor is not None:
        cfg["monitor"] = int(args.monitor) if args.monitor.isdigit() else args.monitor
    if cfg["theme"] not in THEMES:
        sys.exit(f"theme must be one of {', '.join(THEMES)}")
    if cfg["scene"] not in ("face", "eye"):
        sys.exit("scene must be 'face' or 'eye'")
    return cfg


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scene", choices=["face", "eye"])
    ap.add_argument("--theme", choices=list(THEMES))
    ap.add_argument("--size", type=float, help="eye scene: eye height as a fraction of the monitor height")
    ap.add_argument("--cell", type=int, help="face scene: character width in px at 1080p (smaller = more detail)")
    ap.add_argument("--monitor", help="'primary' or a monitor index")
    ap.add_argument("--fps", type=int)
    ap.add_argument("--config", help="path to a config.json")
    ap.add_argument("--window", action="store_true", help="run in a normal 1280x720 window, for trying it out")
    args = ap.parse_args()
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        print("warning: Wayland session - the pointer is only visible over X windows, so the eyes will mostly "
              "play their idle routine. Log in with 'Ubuntu on Xorg' for full mouse tracking.", file=sys.stderr)
    if not os.environ.get("DISPLAY"):
        sys.exit("No X display (DISPLAY is not set).")
    App(load_config(args), args.window).run()


if __name__ == "__main__":
    main()
