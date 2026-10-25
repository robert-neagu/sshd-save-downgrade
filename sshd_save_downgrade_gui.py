#!/usr/bin/env python3
# sshd-save-downgrade by Robert Neagu: https://github.com/robert-neagu/sshd-save-downgrade
# Copyright (c) 2026 Robert Neagu. SPDX-License-Identifier: MIT
"""Desktop GUI for sshd_save_downgrade.py (Windows, macOS, Linux).

Usage:
    python3 sshd_save_downgrade_gui.py [save folder]

Uses tkinter from the standard library. Everything is drawn on canvases with
anti-aliased shapes rendered in Python, so it looks the same on every platform.
There are three styles (Switch, Skyward Sword and a high-contrast Simple one), each
in light and dark. Controls follow the Switch: A / Enter confirms, B / Esc closes,
X switches the style, Y switches light and dark and the arrow keys move the cursor.
A gamepad does the same on Windows (XInput) and Linux (/dev/input/js*).
"""
import base64
import glob
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog
    from tkinter import font as tkfont
except ImportError:  # some Linux distros and Homebrew ship Python without Tk
    tk = None

import sshd_save_downgrade as sd

APP_NAME = "SSHD Save Downgrader"
OUT_NAME = "Skyward Sword HD save (v1.0.0)"
SHOT_W, SHOT_H = 256, 144  # <slot>.screenshot is raw RGBA at this size
BASE_W = 820  # window size in unscaled pixels; the height depends on the style
BASE_H = {"switch": 630, "skyward": 630, "simple": 710}

STYLES = ("switch", "skyward", "simple")  # X cycles through them in this order
STYLE_NAMES = {"switch": "Switch", "skyward": "Skyward Sword", "simple": "Simple"}

THEMES = {
    "switch": {
        "light": {
            "bg": "#EBEBEB", "card": "#FFFFFF", "text": "#2D2D2D", "sub": "#7D7D7D",
            "line": "#D0D0D0", "empty": "#E3E3E3", "cursor": ("#00BEF0", "#8ADFF8"),
            "accent": "#E60012", "on_accent": "#FFFFFF", "blue": "#0AB0E0",
            "off": "#D2D2D2", "on_off": "#F7F7F7",
            "ok": "#16A34A", "warn": "#E88A00", "bad": "#E60012", "info": "#0AB0E0",
        },
        "dark": {
            "bg": "#2D2D2D", "card": "#464646", "text": "#FFFFFF", "sub": "#AFAFAF",
            "line": "#505050", "empty": "#3A3A3A", "cursor": ("#1EE6C8", "#8FF5E4"),
            "accent": "#F0283C", "on_accent": "#FFFFFF", "blue": "#2EBFEA",
            "off": "#575757", "on_off": "#8C8C8C",
            "ok": "#3DD27A", "warn": "#FFA62B", "bad": "#FF5A5F", "info": "#2EBFEA",
        },
    },
    # Skyloft by day and the sky at night: parchment or navy cards with a gold trim
    "skyward": {
        "light": {
            "bg": "#D6E8F3", "card": "#FBF5E6", "text": "#2B2536", "sub": "#6D6878",
            "line": "#B5C7D5", "empty": "#EEE4CC", "cursor": ("#D99A17", "#FFDB7A"),
            "frame": "#C9A24A", "step": "#C9A24A", "on_step": "#2B2536",
            "accent": "#2E5AA6", "on_accent": "#FFFFFF", "blue": "#3F8EC4",
            "off": "#DCD3BD", "on_off": "#8F8770",
            "ok": "#3B8B4E", "warn": "#C0770F", "bad": "#B5333A", "info": "#2E5AA6",
        },
        "dark": {
            "bg": "#0E1A2F", "card": "#1A2A47", "text": "#F3E9D0", "sub": "#A3AEC4",
            "line": "#2C3D5E", "empty": "#22345A", "cursor": ("#E6B43A", "#FFE7A3"),
            "frame": "#B8903C", "step": "#C9A24A", "on_step": "#0E1A2F",
            "accent": "#D6AA4C", "on_accent": "#1A1426", "blue": "#4A93CC",
            "off": "#2B3B5B", "on_off": "#6E7C98",
            "ok": "#55BE76", "warn": "#EFA23A", "bad": "#EE5E67", "info": "#5F9FD8",
        },
    },
    # high contrast for low vision: 7:1 text, a border on every card, a cursor that stays still
    "simple": {
        "light": {
            "bg": "#F2F2F2", "card": "#FFFFFF", "text": "#000000", "sub": "#333333",
            "line": "#767676", "empty": "#E6E6E6", "cursor": ("#000000", "#000000"),
            "frame": "#4D4D4D", "accent": "#0B4FB3", "on_accent": "#FFFFFF", "blue": "#0B4FB3",
            "off": "#C8C8C8", "on_off": "#3D3D3D",
            "ok": "#0A7B33", "warn": "#9A5B00", "bad": "#C0001A", "info": "#0B4FB3",
        },
        "dark": {
            "bg": "#000000", "card": "#121212", "text": "#FFFFFF", "sub": "#DDDDDD",
            "line": "#8C8C8C", "empty": "#262626", "cursor": ("#FFD400", "#FFD400"),
            "frame": "#BFBFBF", "accent": "#8CC4FF", "on_accent": "#000000",
            "blue": "#8CC4FF", "on_blue": "#000000", "off": "#3A3A3A", "on_off": "#D6D6D6",
            "ok": "#5EE08C", "on_ok": "#000000", "warn": "#FFB224", "on_warn": "#000000",
            "bad": "#FF7A7A", "on_bad": "#000000", "info": "#8CC4FF", "on_info": "#000000",
        },
    },
}

FONTS = [  # first installed wins; rounded fonts first for the Nintendo look
    "Nunito", "M PLUS Rounded 1c", "Varela Round", "Segoe UI Variable Text", "Segoe UI",
    "SF Pro Text", "Helvetica Neue", "Inter", "Cantarell", "Ubuntu", "Noto Sans",
    "Open Sans", "DejaVu Sans", "Liberation Sans", "Arial", "Helvetica",
]
SERIF_FONTS = [  # headings in the Skyward Sword style
    "Cinzel", "Marcellus", "Trajan Pro", "Palatino Linotype", "Book Antiqua", "Palatino",
    "TeX Gyre Pagella", "P052", "URW Palladio L", "Georgia", "Noto Serif", "DejaVu Serif",
    "Liberation Serif", "Times New Roman",
]
LEGIBLE_FONTS = [  # fonts designed for easy reading first
    "Atkinson Hyperlegible Next", "Atkinson Hyperlegible", "Verdana", "Segoe UI", "Tahoma",
    "DejaVu Sans", "Noto Sans", "Open Sans", "Cantarell", "Ubuntu", "Liberation Sans",
    "Arial", "Helvetica",
]

# Per style: fonts (display is for bold text), card corner radius, card border and cursor
# ring width, text scale, whether the cursor pulses and buttons bounce, and whether the
# header buttons spell out what they do.
LOOKS = {
    "switch": {"fonts": FONTS, "display": None, "radius": 14, "frame": 0, "ring": 3,
               "text": 1.0, "motion": True, "labels": False},
    "skyward": {"fonts": FONTS, "display": SERIF_FONTS, "radius": 8, "frame": 2, "ring": 3,
                "text": 1.0, "motion": True, "labels": False},
    "simple": {"fonts": LEGIBLE_FONTS, "display": None, "radius": 6, "frame": 2, "ring": 4,
               "text": 1.15, "motion": False, "labels": True},
}


def on(t, key):
    """Color for a glyph or label drawn on top of t[key]."""
    return t.get("on_" + key, "#FFFFFF")


# ---------------------------------------------------------------- save helpers

def format_play_time(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def load_shot(path):
    """Raw RGBA bytes of a slot screenshot, or None if missing or unexpected."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return data if len(data) == SHOT_W * SHOT_H * 4 else None


def resize_rgba(data, sw, sh, dw, dh):
    """Bilinear resize of RGBA bytes; returns rows of (r, g, b) tuples."""
    rows = []
    fx, fy = sw / dw, sh / dh
    for j in range(dh):
        y = min(max((j + 0.5) * fy - 0.5, 0), sh - 1)
        y0 = int(y)
        y1 = min(y0 + 1, sh - 1)
        ty = y - y0
        row = []
        for i in range(dw):
            x = min(max((i + 0.5) * fx - 0.5, 0), sw - 1)
            x0 = int(x)
            x1 = min(x0 + 1, sw - 1)
            tx = x - x0
            a, b = (y0 * sw + x0) * 4, (y0 * sw + x1) * 4
            c, d = (y1 * sw + x0) * 4, (y1 * sw + x1) * 4
            px = []
            for ch in range(3):
                top = data[a + ch] + (data[b + ch] - data[a + ch]) * tx
                bot = data[c + ch] + (data[d + ch] - data[c + ch]) * tx
                px.append(top + (bot - top) * ty)
            row.append(px)
        rows.append(row)
    return rows


def find_save_dir(path):
    """The folder holding wiiking2.sav: path itself, or its only subfolder that has one."""
    path = Path(path)
    if path.is_file():
        return path.parent
    if (path / "wiiking2.sav").is_file():
        return path
    try:
        hits = [p.parent for p in path.glob("*/wiiking2.sav")]
    except OSError:
        hits = []
    if len(hits) == 1:
        return hits[0]
    raise sd.SaveError("No wiiking2.sav in that folder.")


def default_output_base():
    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def unique_output(parent):
    """parent/OUT_NAME, numbered if that folder already exists and isn't empty."""
    n = 1
    while True:
        p = Path(parent) / (OUT_NAME if n == 1 else f"{OUT_NAME} {n}")
        if not p.exists() or (p.is_dir() and not any(p.iterdir())):
            return p
        n += 1


def resolve_output_choice(picked, src_dir):
    """Folder the user picked in the dialog -> the folder to write into.

    An empty folder or one holding a save is used as is. Any other folder gets a
    new subfolder, so picking e.g. the Desktop doesn't scatter files over it."""
    picked = Path(picked)
    if src_dir is not None and picked.resolve() == Path(src_dir).resolve():
        return unique_output(picked)
    if not picked.exists() or (picked / "wiiking2.sav").exists() or not any(picked.iterdir()):
        return picked
    return unique_output(picked)


def system_env():
    """Environment for starting system programs. A PyInstaller build on Linux points
    LD_LIBRARY_PATH at its bundled libraries, which can break xdg-open and friends."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = orig
    return env


def reveal(path):
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)], env=system_env())


def system_prefers_dark():
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                 capture_output=True, text=True, timeout=2).stdout
            return "dark" in out.lower()
        out = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                             capture_output=True, text=True, timeout=2, env=system_env()).stdout
        return "dark" in out.lower()
    except Exception:
        return False


def settings_file():
    """Where the chosen style and light / dark mode are remembered."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "sshd-save-downgrade" / "settings.json"


def load_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(path, data):
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass  # only a convenience; the app works the same without it


# ---------------------------------------------------------------- gamepads
# Just for fun: the face buttons do what their letters say in the footer. Only the standard
# library is used, so this is Windows (XInput) and Linux (the kernel joystick API) only.

PAD_STICK = 16384  # half tilt counts as a press

# Linux key and axis codes (linux/input-event-codes.h)
BTN_A, BTN_B, BTN_X, BTN_Y = 0x130, 0x131, 0x133, 0x134
ABS_X, ABS_Y, ABS_HAT0X, ABS_HAT0Y = 0x00, 0x01, 0x10, 0x11
JS_BUTTONS = {BTN_A: "ok", BTN_B: "close", BTN_X: "style", BTN_Y: "theme",
              0x220: "up", 0x221: "down", 0x222: "left", 0x223: "right"}
JS_AXES = {ABS_X: ("left", "right"), ABS_HAT0X: ("left", "right"),
           ABS_Y: ("up", "down"), ABS_HAT0Y: ("up", "down")}


def js_actions(data, buttons, axes, swap_ab, dirs):
    """Actions from raw js_event structs (u32 time, s16 value, u8 type, u8 number).

    buttons and axes map the joystick's numbers to key and axis codes; dirs keeps
    each axis's last direction so holding a stick moves the cursor only once."""
    out = []
    for i in range(0, len(data) - 7, 8):
        _, value, kind, num = struct.unpack_from("=IhBB", data, i)
        init, kind = kind & 0x80, kind & 0x7F  # init events report the state on open
        if kind == 1 and num < len(buttons):
            code = buttons[num]
            if swap_ab and code in (BTN_A, BTN_B):
                code ^= 1  # Nintendo pads report the right button (A) as BTN_B
            if value and not init and code in JS_BUTTONS:
                out.append(JS_BUTTONS[code])
        elif kind == 2 and num < len(axes) and axes[num] in JS_AXES:
            d = -1 if value < -PAD_STICK else 1 if value > PAD_STICK else 0
            if d and d != dirs.get(num) and not init:
                out.append(JS_AXES[axes[num]][d > 0])
            dirs[num] = d
    return out


def _js_ioctl(nr, size):
    return (2 << 30) | (size << 16) | (ord("j") << 8) | nr  # _IOR('j', nr, size)


class Joystick:
    def __init__(self, path):
        self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        self.buttons, self.axes, name = [BTN_A, BTN_B, BTN_X, BTN_Y], [ABS_X, ABS_Y], ""
        try:
            import fcntl
            buf = bytearray(128)
            fcntl.ioctl(self.fd, _js_ioctl(0x13, 128), buf)  # JSIOCGNAME
            name = buf.split(b"\0")[0].decode(errors="replace")
            buf = bytearray(64)
            fcntl.ioctl(self.fd, _js_ioctl(0x32, 64), buf)  # JSIOCGAXMAP
            self.axes = list(buf)
            buf = bytearray(1024)
            fcntl.ioctl(self.fd, _js_ioctl(0x34, 1024), buf)  # JSIOCGBTNMAP
            self.buttons = list(struct.unpack("=512H", buf))
        except (ImportError, OSError):
            pass  # keep the usual Xbox numbering
        self.swap_ab = "nintendo" in name.lower()
        self.dirs = {}

    def read(self):
        out = []
        while True:
            try:
                data = os.read(self.fd, 8 * 64)
            except BlockingIOError:
                return out
            if not data:
                return out
            out += js_actions(data, self.buttons, self.axes, self.swap_ab, self.dirs)

    def close(self):
        os.close(self.fd)


class LinuxPads:
    def __init__(self):
        self.devices, self.next_scan = {}, 0.0

    def poll(self):
        now = time.monotonic()
        if now >= self.next_scan:  # pick up controllers plugged in later
            self.next_scan = now + 2
            for path in glob.glob("/dev/input/js*"):
                if path not in self.devices:
                    try:
                        self.devices[path] = Joystick(path)
                    except OSError:
                        pass
        out = []
        for path, js in list(self.devices.items()):
            try:
                out += js.read()
            except OSError:  # unplugged
                js.close()
                del self.devices[path]
        return out

    def close(self):
        for js in self.devices.values():
            js.close()
        self.devices = {}


XINPUT_BUTTONS = {0x0001: "up", 0x0002: "down", 0x0004: "left", 0x0008: "right",
                  0x1000: "ok", 0x2000: "close", 0x4000: "style", 0x8000: "theme"}


def xinput_actions(prev, buttons, lx, ly):
    """(new state, actions) for one XInput pad; the left stick acts as the D-pad."""
    if lx < -PAD_STICK:
        buttons |= 0x0004
    elif lx > PAD_STICK:
        buttons |= 0x0008
    if ly > PAD_STICK:  # XInput's y axis points up
        buttons |= 0x0001
    elif ly < -PAD_STICK:
        buttons |= 0x0002
    return buttons, [name for bit, name in XINPUT_BUTTONS.items() if buttons & bit and not prev & bit]


class XInputPads:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                self.dll = ctypes.WinDLL(name)
                break
            except OSError:
                continue
        else:
            raise OSError("XInput isn't available")

        class Gamepad(ctypes.Structure):
            _fields_ = [("buttons", wintypes.WORD), ("lt", wintypes.BYTE), ("rt", wintypes.BYTE),
                        ("lx", wintypes.SHORT), ("ly", wintypes.SHORT),
                        ("rx", wintypes.SHORT), ("ry", wintypes.SHORT)]

        class State(ctypes.Structure):
            _fields_ = [("packet", wintypes.DWORD), ("pad", Gamepad)]

        self.state, self.ref = State(), ctypes.byref
        self.prev, self.retry = [0] * 4, [0.0] * 4

    def poll(self):
        out, now = [], time.monotonic()
        for i in range(4):
            if now < self.retry[i]:
                continue
            if self.dll.XInputGetState(i, self.ref(self.state)):
                # not connected; asking an empty slot is slow, so only check it now and then
                self.prev[i], self.retry[i] = 0, now + 2
                continue
            p = self.state.pad
            self.prev[i], acts = xinput_actions(self.prev[i], p.buttons, p.lx, p.ly)
            out += acts
        return out

    def close(self):
        pass


def gamepads():
    """Gamepad reader for this platform, or None."""
    try:
        if sys.platform.startswith("linux"):
            return LinuxPads()
        if sys.platform == "win32":
            return XInputPads()
    except OSError:
        pass
    return None


# ------------------------------------------------- anti-aliased shape raster

def rgb(c):
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def mix(a, b, t):
    a, b = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def circle(cx, cy, r):
    return lambda x, y: math.hypot(x - cx, y - cy) - r


def rbox(x0, y0, x1, y1, r):
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2 - r, (y1 - y0) / 2 - r

    def f(x, y):
        qx, qy = abs(x - cx) - hx, abs(y - cy) - hy
        return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
    return f


def seg(ax, ay, bx, by, w):
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy or 1e-9

    def f(x, y):
        t = min(max(((x - ax) * dx + (y - ay) * dy) / ll, 0), 1)
        return math.hypot(x - ax - dx * t, y - ay - dy * t) - w / 2
    return f


def poly(*pts):
    """Convex polygon."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    edges = []
    for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
        nx, ny = by - ay, ax - bx
        n = math.hypot(nx, ny)
        nx, ny = nx / n, ny / n
        if (cx - ax) * nx + (cy - ay) * ny > 0:
            nx, ny = -nx, -ny
        edges.append((ax, ay, nx, ny))
    return lambda x, y: max((x - ax) * nx + (y - ay) * ny for ax, ay, nx, ny in edges)


def union(*fs):
    return lambda x, y: min(f(x, y) for f in fs)


def minus(a, b):
    return lambda x, y: max(a(x, y), -b(x, y))


def put_rows(img, rows):
    img.put(" ".join("{" + " ".join("#%02x%02x%02x" % (round(r), round(g), round(b))
                                     for r, g, b in row) + "}" for row in rows))


def raster(master, w, h, bg, layers):
    """PhotoImage of w x h px: bg with each (sdf, color) layer painted on top, anti-aliased."""
    img = tk.PhotoImage(master=master, width=w, height=h)
    base = rgb(bg)
    cols = [(f, rgb(c)) for f, c in layers]
    rows = []
    for j in range(h):
        y = j + 0.5
        row = []
        for i in range(w):
            x = i + 0.5
            r, g, b = base
            for f, (cr, cg, cb) in cols:
                a = 0.5 - f(x, y)
                if a <= 0:
                    continue
                if a >= 1:
                    r, g, b = cr, cg, cb
                else:
                    r, g, b = r + (cr - r) * a, g + (cg - g) * a, b + (cb - b) * a
            row.append((r, g, b))
        rows.append(row)
    put_rows(img, rows)
    return img


# Glyphs in a unit square, scaled to the icon size. Each returns an sdf.
def g_folder(s):
    return union(rbox(.2 * s, .34 * s, .8 * s, .76 * s, .07 * s),
                 rbox(.2 * s, .27 * s, .47 * s, .42 * s, .06 * s))


def g_tray(s):
    w = .085 * s
    return union(seg(.5 * s, .22 * s, .5 * s, .56 * s, w), seg(.35 * s, .43 * s, .5 * s, .58 * s, w),
                 seg(.65 * s, .43 * s, .5 * s, .58 * s, w), seg(.24 * s, .6 * s, .24 * s, .76 * s, w),
                 seg(.24 * s, .76 * s, .76 * s, .76 * s, w), seg(.76 * s, .76 * s, .76 * s, .6 * s, w))


def g_check(s):
    w = .11 * s
    return union(seg(.29 * s, .52 * s, .44 * s, .67 * s, w), seg(.44 * s, .67 * s, .72 * s, .37 * s, w))


def g_bang(s):
    return union(seg(.5 * s, .27 * s, .5 * s, .56 * s, .12 * s), circle(.5 * s, .73 * s, .07 * s))


def g_info(s):
    return union(circle(.5 * s, .28 * s, .07 * s), seg(.5 * s, .46 * s, .5 * s, .74 * s, .12 * s))


def g_chevron(s):
    w = .1 * s
    return union(seg(.4 * s, .27 * s, .62 * s, .5 * s, w), seg(.62 * s, .5 * s, .4 * s, .73 * s, w))


def g_moon(s):
    return minus(circle(.5 * s, .5 * s, .3 * s), circle(.66 * s, .37 * s, .25 * s))


def g_sun(s):
    rays = [seg(.5 * s + math.cos(a) * .27 * s, .5 * s + math.sin(a) * .27 * s,
                .5 * s + math.cos(a) * .36 * s, .5 * s + math.sin(a) * .36 * s, .07 * s)
            for a in (i * math.pi / 4 for i in range(8))]
    return union(circle(.5 * s, .5 * s, .16 * s), *rays)


def g_arrow(s):
    w = .1 * s
    return union(seg(.2 * s, .5 * s, .78 * s, .5 * s, w), seg(.58 * s, .3 * s, .78 * s, .5 * s, w),
                 seg(.58 * s, .7 * s, .78 * s, .5 * s, w))


def g_rewind(s):
    return union(poly((.2 * s, .5 * s), (.5 * s, .3 * s), (.5 * s, .7 * s)),
                 poly((.5 * s, .5 * s), (.8 * s, .3 * s), (.8 * s, .7 * s)))


def g_sparkle(s):
    return union(poly((.5 * s, .08 * s), (.6 * s, .5 * s), (.5 * s, .92 * s), (.4 * s, .5 * s)),
                 poly((.08 * s, .5 * s), (.5 * s, .4 * s), (.92 * s, .5 * s), (.5 * s, .6 * s)))


def g_diamond(s):
    return poly((.5 * s, .1 * s), (.9 * s, .5 * s), (.5 * s, .9 * s), (.1 * s, .5 * s))


def g_sword(s):
    return union(poly((.5 * s, .17 * s), (.56 * s, .25 * s), (.56 * s, .6 * s), (.44 * s, .6 * s),
                      (.44 * s, .25 * s)),
                 rbox(.33 * s, .6 * s, .67 * s, .66 * s, .03 * s),
                 rbox(.47 * s, .66 * s, .53 * s, .78 * s, .02 * s), circle(.5 * s, .8 * s, .04 * s))


# ------------------------------------------------------------------- widgets

class Surface(tk.Canvas if tk else object):
    """A canvas that redraws itself from the app state."""

    def __init__(self, master, app, w, h):
        super().__init__(master, width=w, height=h, highlightthickness=0, bd=0,
                         bg=app.t["bg"], takefocus=0)
        self.app, self.w, self.h = app, w, h
        app.surfaces.append(self)

    def redraw(self):
        self.configure(bg=self.app.t["bg"])
        self.delete("all")
        self.draw()

    def draw(self):
        pass

    def rrect(self, x0, y0, x1, y1, r, fill, bg, tags=(), edge=None, bw=0):
        """Rounded rectangle, optionally with a border of width bw in the edge color."""
        x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
        r = int(min(r, (x1 - x0) / 2, (y1 - y0) / 2))
        if not edge or r < bw:
            edge, bw = fill, 0
        for color, d in ((edge, 0), (fill, bw)) if bw else ((fill, 0),):
            kw = {"fill": color, "outline": "", "tags": tags}
            if r <= 0:
                self.create_rectangle(x0 + d, y0 + d, x1 - d, y1 - d, **kw)
                continue
            self.create_rectangle(x0 + r, y0 + d, x1 - r, y1 - d, **kw)
            self.create_rectangle(x0 + d, y0 + r, x1 - d, y1 - r, **kw)
        if r <= 0:
            return
        for i, (x, y) in enumerate(((x0, y0), (x1 - r, y0), (x0, y1 - r), (x1 - r, y1 - r))):
            self.create_image(x, y, image=self.app.corner(r, fill, bg, i, edge, bw), anchor="nw", tags=tags)

    def card(self, x0, y0, x1, y1, r, fill, bg):
        """Rounded card, inside a border if the style has one."""
        a = self.app
        self.rrect(x0, y0, x1, y1, r, fill, bg, edge=a.t.get("frame"), bw=a.px(a.look["frame"]))

    def text(self, x, y, s, size, color, bold=False, anchor="w", **kw):
        return self.create_text(x, y, text=s, font=self.app.font(size, bold), fill=color,
                                anchor=anchor, **kw)

    def icon(self, x, y, glyph, size, color, bg, disc=None):
        """Glyph centred at x, y, optionally on a filled disc."""
        self.create_image(x, y, image=self.app.icon(glyph, size, color, bg, disc))

    def icon_label(self, cx, cy, glyph, isize, label, size, color, bg):
        """Glyph and label side by side, centred together at cx, cy."""
        a = self.app
        gap = a.px(8)
        x = cx - (isize + gap + a.fontobj(size, True).measure(label)) // 2
        self.icon(x + isize // 2, cy, glyph, isize, color, bg)
        self.text(x + isize + gap, cy, label, size, color, bold=True)


class Focusable(Surface):
    """A card the Switch-style cursor can sit on. A / Enter or a click activates it."""
    pill = False  # fully rounded card, so the ring is too

    def __init__(self, master, app, w, h, command):
        super().__init__(master, app, w, h)
        self.command, self.enabled, self.pressed = command, True, False
        self.bind("<Enter>", lambda e: self.enabled and app.select(self))
        self.bind("<ButtonPress-1>", lambda e: self.enabled and app.select(self))
        self.bind("<ButtonRelease-1>", self._release)
        self.configure(cursor="hand2")

    def _release(self, e):
        if 0 <= e.x < self.w and 0 <= e.y < self.h:
            self.activate()

    def activate(self):
        if not self.enabled or self.pressed:
            return
        self.pressed = True  # quick press-in bounce, then run the command
        self.redraw()
        self.after(90, self._fire)

    def _fire(self):
        if not self.winfo_exists():  # the style changed meanwhile and rebuilt the window
            return
        self.pressed = False
        self.redraw()
        self.command()

    def redraw(self):
        a = self.app
        self.configure(bg=a.t["bg"], cursor="hand2" if self.enabled else "")
        self.delete("all")
        m = a.margin + (a.px(2) if self.pressed and a.look["motion"] else 0)
        self.draw_card(m, m, self.w - m, self.h - m)
        self.draw_ring()

    def draw_ring(self):
        self.delete("ring")
        if self.app.selected is not self:
            return
        a, w, h = self.app, self.w, self.h
        ring, rw = a.cursor_color(), a.px(a.look["ring"])
        gap = a.margin - rw  # ring hugs the canvas edge, concentric with the card
        r = (min(w, h) - 2 * a.margin) // 2 if self.pill else a.px(a.look["radius"])
        r = min(r + rw + gap, w // 2, h // 2)  # outer radius, following the card's corners
        kw = {"fill": ring, "outline": "", "tags": "ring"}
        for box in ((r, 0, w - r, rw), (r, h - rw, w - r, h), (0, r, rw, h - r), (w - rw, r, w, h - r)):
            self.create_rectangle(*box, **kw)
        for i, (x, y) in enumerate(((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
            self.create_image(x, y, image=a.ring_corner(r, rw, ring, i), anchor="nw", tags="ring")
        self.tag_raise("ring")

    def draw_card(self, x0, y0, x1, y1):
        pass


class Header(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        y = self.h // 2
        if a.style == "simple":
            x = a.margin + a.px(4)
            maxw = self.w - x - a.px(8)
            self.text(x, y - a.px(12), a.elide("Save Downgrader", 22, True, maxw), 22, t["text"], bold=True)
            self.text(x, y + a.px(15), a.elide("Skyward Sword HD: v1.0.1 to v1.0.0", 12, False, maxw),
                      12, t["sub"])
            return
        s = a.px(44)
        self.create_image(a.margin, y, image=a.emblem(s), anchor="w")
        x = a.margin + s + a.px(14)
        self.text(x, y - a.px(10), "Save Downgrader", 20, t["text"], bold=True)
        y += a.px(13)
        # subtitle parts with drawn separators, so no font needs the bullet or arrow glyphs
        for part in ("Skyward Sword HD", "dot", "v1.0.1", "arrow", "v1.0.0"):
            if part == "dot":
                d = a.px(4)
                self.icon(x + a.px(10), y, None, d, t["sub"], t["bg"], disc=t["sub"])
                x += a.px(20)
            elif part == "arrow":
                self.icon(x + a.px(12), y, "arrow", a.px(16), t["sub"], t["bg"])
                x += a.px(24)
            else:
                x = self.bbox(self.text(x, y, part, 12, t["sub"]))[2]
        if a.style == "skyward":  # a few sparkles drifting by the title
            for dx, dy, size in ((64, -14, 18), (38, 8, 12), (92, 12, 9)):
                self.icon(self.w - a.px(dx), self.h // 2 + a.px(dy), "sparkle", a.px(size),
                          t["frame"], t["bg"])


class Divider(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        y = self.h // 2
        if a.style != "skyward":
            self.create_line(a.margin, y, self.w - a.margin, y, fill=t["line"])
            return
        c, gap = self.w // 2, a.px(14)
        self.create_line(a.margin, y, c - gap, y, fill=t["frame"])
        self.create_line(c + gap, y, self.w - a.margin, y, fill=t["frame"])
        self.icon(c, y, "diamond", a.px(14), t["frame"], t["bg"])


class ThemeButton(Focusable):
    pill = True

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        self.card(x0, y0, x1, y1, (y1 - y0) // 2, t["card"], t["bg"])
        glyph = "sun" if a.theme == "dark" else "moon"
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if a.look["labels"]:
            self.icon_label(cx, cy, glyph, a.px(24), a.theme_label(), 14, t["text"], t["card"])
        else:
            self.icon(cx, cy, glyph, a.px(26), t["text"], t["card"])


class StyleButton(Focusable):
    pill = True

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        self.card(x0, y0, x1, y1, (y1 - y0) // 2, t["card"], t["bg"])
        self.icon_label((x0 + x1) // 2, (y0 + y1) // 2, "sparkle", a.px(22), a.style_label(), 14,
                        t["text"], t["card"])


class StepLabel(Surface):
    def __init__(self, master, app, w, h, number, label):
        super().__init__(master, app, w, h)
        self.number, self.label = number, label

    def draw(self):
        a, t = self.app, self.app.t
        s, x, y = a.px(20), a.margin + a.px(2), self.h // 2
        if a.style == "simple":
            self.text(x, y, f"Step {self.number}: {self.label}", 14, t["text"], bold=True)
            return
        self.icon(x + s // 2, y, None, s, t["text"], t["bg"], disc=t.get("step", t["sub"]))
        self.text(x + s // 2, y, str(self.number), 11, t.get("on_step", t["bg"]), bold=True,
                  anchor="center")
        self.text(x + s + a.px(8), y, self.label, 13, t["sub"], bold=True)


class Tile(Focusable):
    """Big list-style card: icon disc, title, subtitle, optional pill, chevron."""

    def __init__(self, master, app, w, h, command, glyph, disc_key, content):
        super().__init__(master, app, w, h, command)
        self.glyph, self.disc_key, self.content = glyph, disc_key, content

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        card = t["card"]
        self.card(x0, y0, x1, y1, a.px(a.look["radius"]), card, t["bg"])
        cy = (y0 + y1) // 2
        d = a.px(44)
        self.icon(x0 + a.px(18) + d // 2, cy, self.glyph, d, on(t, self.disc_key), card,
                  disc=t[self.disc_key])
        title, subtitle, pill = self.content()
        tx = x0 + a.px(18) + d + a.px(16)
        right = x1 - a.px(44)
        self.icon(x1 - a.px(26), cy, "chevron", a.px(22), t["sub"], card)
        if pill:
            text, color = pill
            f = a.fontobj(12, True)
            pw, ph = f.measure(text) + a.px(24), a.px(26 * a.look["text"])
            self.rrect(right - pw, cy - ph // 2, right, cy + ph // 2, ph // 2, t[color], card)
            self.text(right - pw // 2, cy, text, 12, on(t, color), bold=True, anchor="center")
            right -= pw + a.px(14)
        maxw = right - tx
        dy = a.px(11 * a.look["text"])
        self.text(tx, cy - dy, a.elide(title, 16, True, maxw), 16, t["text"], bold=True)
        self.text(tx, cy + dy, a.elide(subtitle, 12, False, maxw), 12, t["sub"])


class SlotCard(Surface):
    def __init__(self, master, app, w, h, k):
        super().__init__(master, app, w, h)
        self.k = k

    def thumb_size(self):
        a = self.app
        w = self.w - 2 * a.margin - 2 * a.px(8)
        return w, round(w * 9 / 16)

    def draw(self):
        a, t = self.app, self.app.t
        m, pad = a.margin, a.px(8)
        card = t["card"]
        self.card(m, m, self.w - m, self.h - m, a.px(a.look["radius"]), card, t["bg"])
        tw, th = self.thumb_size()
        x0, y0 = m + pad, m + pad
        info = a.slots[self.k] if a.slots else None
        img = a.thumb(self.k, tw, th) if info and info["used"] else None
        if img:
            self.create_image(x0, y0, image=img, anchor="nw")
        else:
            self.rrect(x0, y0, x0 + tw, y0 + th, a.thumb_radius(), t["empty"], card)
            label = "Empty" if info else ""
            self.text(x0 + tw // 2, y0 + th // 2, label, 12, t["sub"], anchor="center")
        ty = y0 + th + a.px(16)
        self.text(x0 + a.px(2), ty, sd.SLOT_NAMES[self.k].capitalize(), 14, t["text"], bold=True)
        if info and info["used"]:
            self.text(x0 + tw - a.px(2), ty, format_play_time(info["time"]), 12, t["sub"], anchor="e")
        sy = ty + a.px(20)
        if info:
            ok = info["crc"]
            color = t["ok"] if ok else t["bad"]
            label = "Checksum OK" if ok else "Checksum bad"
        else:
            color, label = t["off"], "No save loaded"
        dot = a.px(8)
        self.icon(x0 + a.px(2) + dot // 2, sy, None, dot, color, card, disc=color)
        self.text(x0 + a.px(2) + dot + a.px(7), sy, label, 11, t["sub"])


class SlotList(Surface):
    """The Simple style's slot overview: one row of plain text per slot, no thumbnails."""
    ROW = 30

    def draw(self):
        a, t = self.app, self.app.t
        m, card = a.margin, t["card"]
        self.card(m, m, self.w - m, self.h - m, a.px(a.look["radius"]), card, t["bg"])
        if not a.slots:
            label = "No slots to show." if a.src_dir else "The slots are listed here once you choose a save."
            self.text(self.w // 2, self.h // 2, label, 13, t["sub"], anchor="center")
            return
        x, row, top = m + a.px(20), a.px(self.ROW), m + a.px(10)
        cols = (x, x + a.px(170), x + a.px(400))
        for k, info in enumerate(a.slots):
            cy = top + row * k + row // 2
            if k:
                self.create_line(x, top + row * k, self.w - m - a.px(20), top + row * k, fill=t["line"])
            self.text(cols[0], cy, sd.SLOT_NAMES[k].capitalize(), 14, t["text"], bold=True)
            played = f"{format_play_time(info['time'])} played" if info["used"] else "Empty"
            self.text(cols[1], cy, played, 14, t["text"])
            glyph, kind, label = ("check", "ok", "Checksum OK") if info["crc"] else ("bang", "bad", "Checksum bad")
            s = a.px(22)
            self.icon(cols[2] + s // 2, cy, glyph, s, on(t, kind), card, disc=t[kind])
            self.text(cols[2] + s + a.px(8), cy, label, 14, t["text"])


class StatusView(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        kind, title, detail = a.status
        s = a.px(30)
        x, cy = a.margin + a.px(4), self.h // 2
        glyph = {"ok": "check", "info": "info"}.get(kind, "bang")
        self.icon(x + s // 2, cy, glyph, s, on(t, kind), t["bg"], disc=t[kind])
        tx = x + s + a.px(14)
        width = self.w - tx - a.px(4)
        if detail:
            self.text(tx, cy - a.px(1), title, 14, t["text"], bold=True, anchor="sw", tags="msg")
            self.text(tx, cy + a.px(2), detail, 11, t["sub"], anchor="nw", width=width, tags="msg")
            y0, y1 = self.bbox("msg")[1::2]
            self.move("msg", 0, cy - (y0 + y1) // 2)  # centre the block, however many lines it wraps to
        else:
            self.text(tx, cy, title, 14, t["text"], bold=True, width=width)


class PillButton(Focusable):
    pill = True

    def __init__(self, master, app, w, h, command, primary):
        super().__init__(master, app, w, h, command)
        self.primary, self.label, self.flash = primary, "", False

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        if self.flash:
            fill, fg = t["ok"], on(t, "ok")
        elif not self.enabled:
            fill, fg = t["off"], t["on_off"]
        elif self.primary:
            fill, fg = t["accent"], t["on_accent"]
        else:
            fill, fg = t["card"], t["text"]
        self.card(x0, y0, x1, y1, (y1 - y0) // 2, fill, t["bg"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if self.flash:
            self.icon_label(cx, cy, "check", a.px(26), "Done", 16, fg, fill)
        else:
            self.text(cx, cy, self.label, 16 if self.primary else 14, fg, bold=True, anchor="center")


class Footer(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        self.create_line(a.margin, 0, self.w - a.margin, 0, fill=t["line"])
        cy = self.h // 2
        self.text(a.margin + a.px(4), cy, "Your original save is never modified.", 12, t["sub"])
        x = self.w - a.margin - a.px(4)
        s = a.px(22 * a.look["text"])
        hints = (("A", "OK", "ok"), ("B", "Close", "close"), ("X", "Style", "style"),
                 ("Y", a.theme_label(), "theme"))
        for letter, label, action in reversed(hints):
            tag = "hint_" + action
            label_id = self.text(x, cy, label, 13, t["text"], anchor="e", tags=tag)
            bx0 = self.bbox(label_id)[0]
            cx = bx0 - a.px(6) - s // 2
            self.create_image(cx, cy, image=a.icon(None, s, t["text"], t["bg"], disc=t["text"]), tags=tag)
            self.text(cx, cy, letter, 11, t["bg"], bold=True, anchor="center", tags=tag)
            self.tag_bind(tag, "<Button-1>", lambda e, act=action: a.action(act))
            x = cx - s // 2 - a.px(22)


# ---------------------------------------------------------------------- app

class App:
    FOCUSABLE = ("style_btn", "theme_btn", "src_tile", "dst_tile", "show_btn", "convert_btn")

    def __init__(self, root, src=None, theme=None, style=None, remember=True):
        """theme / style override the remembered ones; remember=False neither reads nor
        writes the settings file."""
        self.root = root
        self.settings_path = settings_file() if remember else None
        self.settings = load_settings(self.settings_path) if remember else {}
        saved_style, saved_theme = self.settings.get("style"), self.settings.get("theme")
        self.style = style or (saved_style if saved_style in STYLES else "switch")
        self.theme = theme or (saved_theme if saved_theme in ("light", "dark") else None) or \
            ("dark" if system_prefers_dark() else "light")
        self.scale = self._pick_scale()
        self._fonts, self._images, self._shots, self._thumbs = {}, {}, {}, {}
        self._apply_style()
        self.surfaces, self.selected = [], None
        self._pulse, self._pulse_level = 0.0, None
        self._timers = {}  # name -> pending after() id
        self.busy = self.closed = False  # busy: a file dialog is open
        self.pads = gamepads()

        self.src_dir = self.buf = self.version = self.load_error = None
        self.slots = None
        self.dst, self.dst_picked = None, False
        self.result = None  # status pinned after a conversion attempt
        self.status = ("info", "", "")

        root.title(APP_NAME)
        root.resizable(False, False)
        root.configure(bg=self.t["bg"])
        self._icons = [tk.PhotoImage(master=root, data=base64.b64encode(app_icon_png(s)).decode()) for s in (64, 32)]
        root.iconphoto(True, *self._icons)
        self._build()
        for seq in ("<Return>", "<KP_Enter>", "<space>", "a", "A"):
            root.bind(seq, lambda e: self.action("ok"))
        for seq in ("<Escape>", "b", "B"):
            root.bind(seq, lambda e: self.action("close"))
        for seq in ("x", "X"):
            root.bind(seq, lambda e: self.action("style"))
        for seq in ("y", "Y"):
            root.bind(seq, lambda e: self.action("theme"))
        for seq, step in (("<Up>", -1), ("<Left>", -1), ("<Shift-Tab>", -1), ("<ISO_Left_Tab>", -1),
                          ("<Down>", 1), ("<Right>", 1), ("<Tab>", 1)):
            try:
                root.bind(seq, lambda e, s=step: (self.move(s), "break")[1])
            except tk.TclError:  # ISO_Left_Tab only exists on X11
                pass

        if src:
            self.load_source(src)
        self.refresh()
        self.select(self.convert_btn if self.convert_btn.enabled else self.src_tile)
        self._tick()

    # ---- sizing, fonts, images

    def _pick_scale(self):
        dpi_scale = max(1.0, self.root.winfo_fpixels("1i") / 96)
        fit = min(self.root.winfo_screenwidth() * 0.95 / BASE_W,
                  self.root.winfo_screenheight() * 0.88 / BASE_H[self.style])
        return max(0.75, min(dpi_scale, fit))

    def px(self, v):
        return round(v * self.scale)

    def _apply_style(self):
        self.look = LOOKS[self.style]
        self.t = THEMES[self.style][self.theme]
        self.margin = self.px(self.look["ring"] + 2)  # room around each card for the cursor ring
        self.family = self._pick_family(self.look["fonts"])
        self.display = self._pick_family(self.look["display"]) if self.look["display"] else self.family
        self._fonts = {}

    def _pick_family(self, names):
        default = tkfont.nametofont("TkDefaultFont").actual("family")
        if sys.platform == "darwin" and names is FONTS:
            return default
        installed = {f.lower(): f for f in tkfont.families(self.root)}
        return next((installed[f.lower()] for f in names if f.lower() in installed), default)

    def font(self, size, bold=False):
        return (self.display if bold else self.family, -self.px(size * self.look["text"]),
                "bold" if bold else "normal")

    def fontobj(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            family, px, weight = self.font(size, bold)
            self._fonts[key] = tkfont.Font(root=self.root, family=family, size=px, weight=weight)
        return self._fonts[key]

    def elide(self, text, size, bold, maxw):
        f = self.fontobj(size, bold)
        if f.measure(text) <= maxw:
            return text
        lo, hi = 0, len(text)
        while lo < hi:  # most characters kept with head + "..." + tail still fitting
            n = (lo + hi + 1) // 2
            if f.measure(text[:n // 2] + "..." + text[len(text) - (n - n // 2):]) <= maxw:
                lo = n
            else:
                hi = n - 1
        return text[:lo // 2] + "..." + text[len(text) - (lo - lo // 2):]

    def _cached(self, key, make):
        if key not in self._images:
            self._images[key] = make()
        return self._images[key]

    def corner(self, r, fill, bg, i, edge=None, bw=0):
        cx, cy = (r, 0)[i % 2], (r, 0)[i // 2]
        layers = [(circle(cx, cy, r), edge), (circle(cx, cy, r - bw), fill)] if bw else \
            [(circle(cx, cy, r), fill)]
        return self._cached(("corner", r, fill, bg, i, edge, bw),
                            lambda: raster(self.root, r, r, bg, layers))

    def ring_corner(self, r, w, color, i):
        """Corner of the cursor ring: a quarter annulus of width w and outer radius r, transparent
        elsewhere so it can sit on top of the card's own corner."""
        cx, cy = (r, 0)[i % 2], (r, 0)[i // 2]
        shape = minus(circle(cx, cy, r), circle(cx, cy, r - w))
        return self._cached(("ring", r, w, color, i), lambda: tk.PhotoImage(
            master=self.root, data=base64.b64encode(sdf_png(r, r, shape, color)).decode()))

    def icon(self, glyph, size, color, bg, disc=None):
        def make():
            layers = []
            if disc:
                layers.append((circle(size / 2, size / 2, size / 2), disc))
            if glyph:
                layers.append((GLYPHS[glyph](size), color))
            return raster(self.root, size, size, bg, layers)
        return self._cached(("icon", glyph, size, color, bg, disc), make)

    def emblem(self, size):
        bg, s = self.t["bg"], size
        if self.style == "skyward":  # a sword in a gold-trimmed diamond
            layers = [(poly((s / 2, 0), (s, s / 2), (s / 2, s), (0, s / 2)), "#C9A24A"),
                      (poly((s / 2, .1 * s), (.9 * s, s / 2), (s / 2, .9 * s), (.1 * s, s / 2)), "#1F3358"),
                      (g_sword(s), "#F4E6BF")]
        else:
            layers = [(rbox(0, 0, s, s, s * .28), THEMES["switch"]["light"]["accent"]),
                      (g_rewind(s), "#FFFFFF")]
        return self._cached(("emblem", self.style, size, bg), lambda: raster(self.root, s, s, bg, layers))

    def thumb_radius(self):
        return self.px(max(self.look["radius"] - 5, 2))

    def thumb(self, k, w, h):
        """Slot screenshot scaled to w x h with rounded corners, or None."""
        data = self._shots.get(k)
        if data is None:
            return None
        card, r = self.t["card"], self.thumb_radius()
        key = (k, w, h, card, r)
        if key not in self._thumbs:
            rows = resize_rgba(data, SHOT_W, SHOT_H, w, h)
            edge, cr = rbox(0, 0, w, h, r), rgb(card)
            for j in list(range(r)) + list(range(h - r, h)):
                for i in list(range(r)) + list(range(w - r, w)):
                    a = min(max(0.5 - edge(i + 0.5, j + 0.5), 0), 1)
                    rows[j][i] = [c + (p - c) * a for p, c in zip(rows[j][i], cr)]
            img = tk.PhotoImage(master=self.root, width=w, height=h)
            put_rows(img, rows)
            self._thumbs[key] = img
        return self._thumbs[key]

    def cursor_color(self):
        a, b = self.t["cursor"]
        return mix(a, b, (self._pulse_level or 0) / 7) if self.look["motion"] else a

    def theme_label(self):
        return "Light mode" if self.theme == "dark" else "Dark mode"

    def style_label(self, style=None):
        name = STYLE_NAMES[style or self.style]
        return f"Style: {name}" if self.look["labels"] else name

    # ---- layout

    def _build(self):
        px, root = self.px, self.root
        simple = self.style == "simple"
        W = px(BASE_W)
        pad = px(24) - self.margin
        cw = W - 2 * pad
        self.frame = tk.Frame(root, bg=self.t["bg"], padx=pad, pady=px(14))
        self.frame.pack(fill="both", expand=True)
        f = self.frame

        top = tk.Frame(f, bg=self.t["bg"])
        top.pack(fill="x")
        th = px(56) + self.margin

        def pill_w(labels, isize):  # wide enough for the longest label next to its icon
            return max(self.fontobj(14, True).measure(s) for s in labels) + px(isize + 8 + 28) + 2 * self.margin
        theme_w = pill_w(("Light mode", "Dark mode"), 24) if self.look["labels"] else th
        self.theme_btn = ThemeButton(top, self, theme_w, th, lambda: self.action("theme"))
        self.theme_btn.pack(side="right")
        style_w = pill_w((self.style_label(),), 22)
        self.style_btn = StyleButton(top, self, style_w, th, lambda: self.action("style"))
        self.style_btn.pack(side="right", padx=(0, px(4)))
        Header(top, self, cw - theme_w - style_w - px(4), th).pack(side="left")
        Divider(f, self, cw, px(12)).pack(anchor="w")

        StepLabel(f, self, cw, px(34), 1, "Your v1.0.1 save").pack(anchor="w")
        self.src_tile = Tile(f, self, cw, px(84 if simple else 74) + 2 * self.margin, self.pick_source,
                             "folder", "accent", self._src_content)
        self.src_tile.pack(anchor="w")

        row = tk.Frame(f, bg=self.t["bg"])
        row.pack(anchor="w", pady=(px(2), 0))
        if simple:
            SlotList(row, self, cw, px(4 * SlotList.ROW + 20) + 2 * self.margin).pack(anchor="w")
        else:
            gap = px(8)
            sw = (cw - 3 * gap) // 4
            for k in range(sd.SLOT_COUNT):
                card = SlotCard(row, self, sw, 0, k)
                card.h = card.thumb_size()[1] + px(64) + 2 * self.margin
                card.configure(height=card.h)
                card.pack(side="left", padx=(0 if k == 0 else gap, 0))

        StepLabel(f, self, cw, px(34), 2, "Output folder").pack(anchor="w", pady=(px(4), 0))
        self.dst_tile = Tile(f, self, cw, px(76 if simple else 66) + 2 * self.margin, self.pick_dest,
                             "tray", "blue", self._dst_content)
        self.dst_tile.pack(anchor="w")

        if simple:  # the status gets a row of its own, so long messages fit at the larger text size
            self.status_view = StatusView(f, self, cw, px(62))
            self.status_view.pack(anchor="w", pady=(px(8), 0))
        bottom = tk.Frame(f, bg=self.t["bg"])
        bottom.pack(fill="x", pady=(px(4 if simple else 12), px(6)))
        bh = px(58 if simple else 54) + 2 * self.margin
        self.convert_btn = PillButton(bottom, self, px(220 if simple else 200), bh, self.convert, primary=True)
        self.convert_btn.pack(side="right")
        self.show_btn = PillButton(bottom, self, px(180 if simple else 160), bh, self.show_output, primary=False)
        self.show_btn.label = "Show folder"
        self.bottom_w = None if simple else cw  # width the status shares with the buttons
        if not simple:
            self.status_view = StatusView(bottom, self, cw - self.convert_btn.w, bh)
            self.status_view.pack(side="left")

        Footer(f, self, cw, px(46)).pack(anchor="w")
        self.frames = [self.frame, top, row, bottom]

    def focus_order(self):
        order = [self.style_btn, self.theme_btn, self.src_tile, self.dst_tile]
        if self.show_btn.winfo_manager():
            order.append(self.show_btn)
        order.append(self.convert_btn)
        return [w for w in order if w.enabled]

    # ---- state

    def load_source(self, path):
        self.result = None
        self._shots, self._thumbs = {}, {}
        self.buf = self.version = self.slots = self.load_error = None
        src_dir = None
        try:
            src_dir = find_save_dir(path)
            buf = (src_dir / "wiiking2.sav").read_bytes()
            version = sd.check_header(buf)
        except (sd.SaveError, OSError) as e:
            self.src_dir = src_dir or Path(path)
            self.load_error = str(e) if isinstance(e, sd.SaveError) else f"Couldn't read the save: {e}"
            return
        self.src_dir, self.buf, self.version = src_dir, buf, version
        crcs = sd.check_crcs(self.buf)
        self.slots = []
        for k in range(sd.SLOT_COUNT):
            used = sd.slot_used(self.buf, k)
            self.slots.append({"used": used, "time": sd.play_time(self.buf, k), "crc": crcs[k]})
            if used:
                self._shots[k] = load_shot(self.src_dir / f"{k}.screenshot")
        if not self.dst_picked:
            self.dst = unique_output(default_output_base())

    def set_dest(self, path, picked=True):
        self.result = None
        self.dst, self.dst_picked = Path(path), picked

    def problem(self):
        """(kind, title, detail) explaining why we can't convert, or None."""
        if self.src_dir is None:
            return ("info", "Choose your save folder",
                    "Ryujinx / Ryubing: right-click the game, Open User Save Directory. "
                    "Switch: dump the save with JKSV.")
        if self.load_error:
            return ("bad", "That folder has no usable save", self.load_error)
        if self.version == sd.VERSION_100:
            return ("info", "This save is already v1.0.0", "v1.0.0 loads it as is. Nothing to convert.")
        if self.version != sd.VERSION_101:
            return ("bad", f"Unknown save version {self.version}", "Only v1.0.1 saves (version 44) are supported.")
        bad = [sd.SLOT_NAMES[k] for k, s in enumerate(self.slots) if not s["crc"]]
        if bad:
            return ("bad", "Checksum check failed", f"Bad slots: {', '.join(bad)}. The save may be damaged, "
                    "so it won't be converted.")
        if self.dst is None:
            return ("info", "Choose an output folder", "")
        if self.dst.exists() and self.dst.resolve() == self.src_dir.resolve():
            return ("bad", "Pick a different output folder", "It can't be the same as the save folder.")
        return None

    def overwrites(self):
        return self.dst is not None and (self.dst / "wiiking2.sav").exists()

    def can_convert(self):
        return self.problem() is None

    def refresh(self):
        problem = self.problem()
        if self.result:
            self.status = self.result
        elif problem:
            self.status = problem
        elif self.overwrites():
            self.status = ("warn", "The output folder already has a save",
                           "Converting replaces it. The old one is kept as wiiking2.sav.bak.")
        else:
            used = sum(s["used"] for s in self.slots)
            self.status = ("info", "Ready to convert",
                           f"{used} of 4 slots in use. All checksums are valid.")
        self.convert_btn.enabled = problem is None
        if self.result and self.result[0] in ("ok", "warn"):
            self.convert_btn.label = "Convert again"
        else:
            self.convert_btn.label = "Overwrite" if problem is None and self.overwrites() else "Convert"
        self.dst_tile.enabled = self.src_dir is not None and not self.load_error
        self._show_folder_button(bool(self.result) and self.result[0] in ("ok", "warn")
                                 and self.dst.is_dir())
        if self.selected is not None and not self.selected.enabled:
            self.selected = self.src_tile
        self.redraw_all()

    def _show_folder_button(self, show):
        if show == self.show_btn.winfo_manager().startswith("pack"):
            return
        if self.bottom_w:  # resize the status first so the row never asks for more than the window width
            self.status_view.w = self.bottom_w - self.convert_btn.w - (self.show_btn.w if show else 0)
            self.status_view.configure(width=self.status_view.w)
        if show:
            self.show_btn.pack(side="right", after=self.convert_btn)
        else:
            self.show_btn.pack_forget()

    def redraw_all(self):
        self.root.configure(bg=self.t["bg"])
        for fr in self.frames:
            fr.configure(bg=self.t["bg"])
        for s in self.surfaces:
            s.redraw()

    def _src_content(self):
        if self.src_dir is None:
            return "Choose your save folder", "The folder with wiiking2.sav, skip.dat and the screenshots", None
        if self.load_error:
            return "No save found here", str(self.src_dir), ("Error", "bad")
        name = sd.VERSION_NAMES.get(self.version, f"version {self.version}")
        color = "blue" if self.version == sd.VERSION_101 else "sub"
        return "Skyward Sword HD save", str(self.src_dir), (name, color)

    def _dst_content(self):
        if self.dst is None:
            return "Converted save goes here", "Pick a save folder first", None
        if self.result and self.result[0] in ("ok", "warn"):
            pill = ("Converted", "ok")
        elif self.overwrites():
            pill = ("Replaces save", "warn")
        else:
            pill = None if self.dst.exists() else ("New folder", "ok")
        return self.dst.name, str(self.dst.parent), pill

    # ---- actions

    def select(self, w):
        if w is self.selected:
            return
        old, self.selected = self.selected, w
        if old is not None:
            old.redraw()
        if w is not None:
            w.redraw()

    def move(self, step):
        order = self.focus_order()
        if not order:
            return
        i = order.index(self.selected) if self.selected in order else -1
        self.select(order[(i + step) % len(order)] if i >= 0 else order[0])

    def action(self, name):
        if name == "ok" and self.selected is not None:
            self.selected.activate()
        elif name == "close":
            self.close()
        elif name == "theme":
            self.set_theme("dark" if self.theme == "light" else "light")
        elif name == "style":
            self.set_style(STYLES[(STYLES.index(self.style) + 1) % len(STYLES)])

    def set_theme(self, theme):
        self.theme = theme
        self.t = THEMES[self.style][theme]
        self.redraw_all()
        self._remember("theme", theme)

    def set_style(self, style):
        """Switch style. The layout differs between styles, so the window is rebuilt."""
        keep = next((n for n in self.FOCUSABLE if getattr(self, n) is self.selected), "src_tile")
        self.style = style
        self.scale = self._pick_scale()
        self._apply_style()
        self.frame.destroy()
        self.surfaces, self.selected = [], None
        self._build()
        self.refresh()
        w = getattr(self, keep)
        self.select(w if w in self.focus_order() else self.src_tile)
        self._remember("style", style)

    def _remember(self, key, value):
        if self.settings_path is not None:
            self.settings[key] = value
            save_settings(self.settings_path, self.settings)

    def _ask_folder(self, **kw):
        self.busy = True  # the gamepad mustn't drive the window behind the dialog
        try:
            return filedialog.askdirectory(parent=self.root, **kw)
        finally:
            self.busy = False

    def pick_source(self):
        start = self.src_dir if self.src_dir and self.src_dir.is_dir() else Path.home()
        path = self._ask_folder(initialdir=str(start), mustexist=True,
                                title="Choose the save folder (the one with wiiking2.sav)")
        if not path:
            return
        self.load_source(path)
        self.refresh()
        if self.convert_btn.enabled:
            self.select(self.convert_btn)

    def pick_dest(self):
        start = self.dst.parent if self.dst else default_output_base()
        while not start.is_dir() and start != start.parent:
            start = start.parent
        path = self._ask_folder(initialdir=str(start), mustexist=False,
                                title="Choose where to put the converted save")
        if not path:
            return
        self.set_dest(resolve_output_choice(path, self.src_dir))
        self.refresh()
        if self.convert_btn.enabled:
            self.select(self.convert_btn)

    def convert(self):
        if not self.can_convert():
            return
        log = []
        try:
            old = self.dst / "wiiking2.sav"
            if old.exists():
                shutil.copy2(old, self.dst / "wiiking2.sav.bak")
            sd.convert_folder(self.src_dir, self.dst, log=log.append)
        except (sd.SaveError, OSError) as e:
            self.result = ("bad", "Conversion failed", str(e))
            self.refresh()
            return
        notes = [line.strip() for line in log if "unexpected" in line]
        if notes:
            self.result = ("warn", "Converted, with a warning", " ".join(notes))
        else:
            self.result = ("ok", "Converted to v1.0.0",
                           f'Copy everything in "{self.dst.name}" into the v1.0.0 save folder.')
        self.refresh()
        self.select(self.show_btn if self.show_btn.winfo_manager() else self.convert_btn)
        self.convert_btn.flash = True
        self.convert_btn.redraw()
        self._timers["flash"] = self.root.after(1600, self._end_flash)

    def _end_flash(self):
        self.convert_btn.flash = False
        self.convert_btn.redraw()

    def show_output(self):
        if self.dst and self.dst.is_dir():
            try:
                reveal(self.dst)
            except OSError as e:
                self.result = ("bad", "Couldn't open the folder", str(e))
                self.refresh()

    def _tick(self):
        """Pulse the cursor ring like the Switch menu, and read the gamepads."""
        if self.look["motion"]:
            self._pulse += 0.12
            level = round((math.sin(self._pulse) + 1) / 2 * 7)
            if level != self._pulse_level:
                self._pulse_level = level
                if self.selected is not None:
                    self.selected.draw_ring()
        self._poll_pads()
        if not self.closed:
            self._timers["tick"] = self.root.after(50, self._tick)

    def _poll_pads(self):
        if self.pads is None:
            return
        try:
            actions = self.pads.poll()
        except Exception:  # a gimmick must never take the app down
            self.pads = None
            return
        if not actions or self.busy or not self.has_focus():
            return  # only while our window has the focus, like a game
        for name in dict.fromkeys(actions):  # one press seen by two devices counts once
            if self.closed:
                return
            if name in ("up", "left"):
                self.move(-1)
            elif name in ("down", "right"):
                self.move(1)
            else:
                self.action(name)

    def has_focus(self):
        return bool(str(self.root.tk.call("focus")))

    def close(self):
        self.closed = True
        for timer in self._timers.values():
            self.root.after_cancel(timer)
        if self.pads is not None:
            self.pads.close()
        self.root.destroy()


def app_icon_png(size):
    """Window icon as a PNG with real transparency."""
    shape, glyph = rbox(0, 0, size, size, size * .28), g_rewind(size)
    red = rgb(THEMES["switch"]["light"]["accent"])
    raw = bytearray()
    for j in range(size):
        raw.append(0)
        for i in range(size):
            x, y = i + .5, j + .5
            a = min(max(.5 - shape(x, y), 0), 1)
            w = min(max(.5 - glyph(x, y), 0), 1)
            raw += bytes(round(c + (255 - c) * w) for c in red) + bytes([round(a * 255)])
    return encode_png(size, size, raw)


def sdf_png(w, h, f, color):
    """PNG of shape f in color on a transparent background, anti-aliased."""
    c = bytes(rgb(color))
    raw = bytearray()
    for j in range(h):
        raw.append(0)
        for i in range(w):
            raw += c + bytes([round(min(max(.5 - f(i + .5, j + .5), 0), 1) * 255)])
    return encode_png(w, h, raw)


def encode_png(w, h, raw):
    """RGBA PNG from raw scanlines (each starting with a filter byte)."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


GLYPHS = {
    "folder": g_folder, "tray": g_tray, "check": g_check, "bang": g_bang, "info": g_info,
    "chevron": g_chevron, "arrow": g_arrow, "moon": g_moon, "sun": g_sun,
    "sparkle": g_sparkle, "diamond": g_diamond,
}


def _windows_setup():
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on HiDPI screens
    except Exception:
        pass
    try:  # hide the console window when started by double-clicking the .py file
        k32 = ctypes.windll.kernel32
        if k32.GetConsoleProcessList((ctypes.c_uint * 2)(), 2) == 1:
            ctypes.windll.user32.ShowWindow(k32.GetConsoleWindow(), 0)
    except Exception:
        pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if tk is None:
        print("This GUI needs tkinter, which your Python doesn't include.\n"
              "  Debian/Ubuntu: sudo apt install python3-tk\n"
              "  Fedora:        sudo dnf install python3-tkinter\n"
              "  Arch:          sudo pacman -S tk\n"
              "  macOS (Homebrew): brew install python-tk\n"
              "Or use the command line tool: python3 sshd_save_downgrade.py --help", file=sys.stderr)
        return 1
    if sys.platform == "win32":
        _windows_setup()
    root = tk.Tk()
    App(root, src=argv[0] if argv else None)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
