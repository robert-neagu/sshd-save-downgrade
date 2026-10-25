#!/usr/bin/env python3
"""Desktop GUI for sshd_save_downgrade.py (Windows, macOS, Linux).

Usage:
    python3 sshd_save_downgrade_gui.py [save folder]

Uses tkinter from the standard library. Everything is drawn on canvases with
anti-aliased shapes rendered in Python, so it looks the same on every platform.
Controls follow the Switch: A / Enter confirms, B / Esc closes, Y switches the
theme and the arrow keys move the cursor.
"""
import base64
import math
import os
import shutil
import struct
import subprocess
import sys
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
BASE_W = 820  # window size in unscaled pixels
BASE_H = 626

THEMES = {
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
}

FONTS = [  # first installed wins; rounded fonts first for the Nintendo look
    "Nunito", "M PLUS Rounded 1c", "Varela Round", "Segoe UI Variable Text", "Segoe UI",
    "SF Pro Text", "Helvetica Neue", "Inter", "Cantarell", "Ubuntu", "Noto Sans",
    "Open Sans", "DejaVu Sans", "Liberation Sans", "Arial", "Helvetica",
]


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

    def rrect(self, x0, y0, x1, y1, r, fill, bg, tags=()):
        x0, y0, x1, y1 = round(x0), round(y0), round(x1), round(y1)
        r = int(min(r, (x1 - x0) / 2, (y1 - y0) / 2))
        kw = {"fill": fill, "outline": "", "tags": tags}
        if r <= 0:
            self.create_rectangle(x0, y0, x1, y1, **kw)
            return
        self.create_rectangle(x0 + r, y0, x1 - r, y1, **kw)
        self.create_rectangle(x0, y0 + r, x1, y1 - r, **kw)
        for i, (x, y) in enumerate(((x0, y0), (x1 - r, y0), (x0, y1 - r), (x1 - r, y1 - r))):
            self.create_image(x, y, image=self.app.corner(r, fill, bg, i), anchor="nw", tags=tags)

    def text(self, x, y, s, size, color, bold=False, anchor="w", **kw):
        return self.create_text(x, y, text=s, font=self.app.font(size, bold), fill=color,
                                anchor=anchor, **kw)

    def icon(self, x, y, glyph, size, color, bg, disc=None):
        """Glyph centred at x, y, optionally on a filled disc."""
        self.create_image(x, y, image=self.app.icon(glyph, size, color, bg, disc))


class Focusable(Surface):
    """A card the Switch-style cursor can sit on. A / Enter or a click activates it."""
    radius = 14

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
        self.pressed = False
        self.redraw()
        self.command()

    def redraw(self):
        self.configure(bg=self.app.t["bg"], cursor="hand2" if self.enabled else "")
        self.delete("all")
        self.draw_ring()
        m = self.app.margin + (self.app.px(2) if self.pressed else 0)
        self.draw_card(m, m, self.w - m, self.h - m)

    def draw_ring(self):
        self.delete("ring")
        if self.app.selected is not self:
            return
        a, bg = self.app, self.app.t["bg"]
        ring, r = a.cursor_color(), a.px(self.radius)
        rw, gap = a.px(3), a.px(2)
        self.rrect(0, 0, self.w, self.h, r + rw + gap, ring, bg, tags="ring")
        self.rrect(rw, rw, self.w - rw, self.h - rw, r + gap, bg, ring, tags="ring")
        self.tag_lower("ring")

    def draw_card(self, x0, y0, x1, y1):
        pass


class Header(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        s, y = a.px(44), self.h // 2
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


class Divider(Surface):
    def draw(self):
        a = self.app
        self.create_line(a.margin, self.h // 2, self.w - a.margin, self.h // 2, fill=a.t["line"])


class ThemeButton(Focusable):
    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        r = (x1 - x0) // 2
        self.rrect(x0, y0, x1, y1, r, t["card"], t["bg"])
        glyph = "sun" if a.theme == "dark" else "moon"
        self.icon((x0 + x1) // 2, (y0 + y1) // 2, glyph, a.px(26), t["text"], t["card"])


class StepLabel(Surface):
    def __init__(self, master, app, w, h, number, label):
        super().__init__(master, app, w, h)
        self.number, self.label = number, label

    def draw(self):
        a, t = self.app, self.app.t
        s, x, y = a.px(20), a.margin + a.px(2), self.h // 2
        self.icon(x + s // 2, y, None, s, t["text"], t["bg"], disc=t["sub"])
        self.text(x + s // 2, y, str(self.number), 11, t["bg"], bold=True, anchor="center")
        self.text(x + s + a.px(8), y, self.label, 13, t["sub"], bold=True)


class Tile(Focusable):
    """Big list-style card: icon disc, title, subtitle, optional pill, chevron."""

    def __init__(self, master, app, w, h, command, glyph, disc_key, content):
        super().__init__(master, app, w, h, command)
        self.glyph, self.disc_key, self.content = glyph, disc_key, content

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        card = t["card"]
        self.rrect(x0, y0, x1, y1, a.px(self.radius), card, t["bg"])
        cy = (y0 + y1) // 2
        d = a.px(44)
        self.icon(x0 + a.px(18) + d // 2, cy, self.glyph, d, "#FFFFFF", card, disc=t[self.disc_key])
        title, subtitle, pill = self.content()
        tx = x0 + a.px(18) + d + a.px(16)
        right = x1 - a.px(44)
        self.icon(x1 - a.px(26), cy, "chevron", a.px(22), t["sub"], card)
        if pill:
            text, color = pill
            f = a.fontobj(12, True)
            pw, ph = f.measure(text) + a.px(24), a.px(26)
            self.rrect(right - pw, cy - ph // 2, right, cy + ph // 2, ph // 2, t[color], card)
            self.text(right - pw // 2, cy, text, 12, "#FFFFFF", bold=True, anchor="center")
            right -= pw + a.px(14)
        maxw = right - tx
        self.text(tx, cy - a.px(11), a.elide(title, 16, True, maxw), 16, t["text"], bold=True)
        self.text(tx, cy + a.px(12), a.elide(subtitle, 12, False, maxw), 12, t["sub"])


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
        self.rrect(m, m, self.w - m, self.h - m, a.px(14), card, t["bg"])
        tw, th = self.thumb_size()
        x0, y0 = m + pad, m + pad
        info = a.slots[self.k] if a.slots else None
        img = a.thumb(self.k, tw, th) if info and info["used"] else None
        if img:
            self.create_image(x0, y0, image=img, anchor="nw")
        else:
            self.rrect(x0, y0, x0 + tw, y0 + th, a.px(9), t["empty"], card)
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


class StatusView(Surface):
    def draw(self):
        a, t = self.app, self.app.t
        kind, title, detail = a.status
        s = a.px(30)
        x, cy = a.margin + a.px(4), self.h // 2
        glyph = {"ok": "check", "info": "info"}.get(kind, "bang")
        self.icon(x + s // 2, cy, glyph, s, "#FFFFFF", t["bg"], disc=t[kind])
        tx = x + s + a.px(14)
        width = self.w - tx - a.px(4)
        if detail:
            self.text(tx, cy - a.px(1), title, 14, t["text"], bold=True, anchor="sw")
            self.text(tx, cy + a.px(2), detail, 11, t["sub"], anchor="nw", width=width)
        else:
            self.text(tx, cy, title, 14, t["text"], bold=True, width=width)


class PillButton(Focusable):
    def __init__(self, master, app, w, h, command, primary):
        super().__init__(master, app, w, h, command)
        self.primary, self.label, self.flash = primary, "", False

    def draw_card(self, x0, y0, x1, y1):
        a, t = self.app, self.app.t
        if self.flash:
            fill, fg = t["ok"], "#FFFFFF"
        elif not self.enabled:
            fill, fg = t["off"], t["on_off"]
        elif self.primary:
            fill, fg = t["accent"], t["on_accent"]
        else:
            fill, fg = t["card"], t["text"]
        self.rrect(x0, y0, x1, y1, (y1 - y0) // 2, fill, t["bg"])
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if self.flash:
            self.icon(cx - a.px(36), cy, "check", a.px(26), fg, fill)
            self.text(cx - a.px(20), cy, "Done", 16, fg, bold=True)
        else:
            self.text(cx, cy, self.label, 16 if self.primary else 14, fg, bold=True, anchor="center")


class Footer(Surface):
    HINTS = (("A", "OK", "ok"), ("B", "Close", "close"), ("Y", "Theme", "theme"))

    def draw(self):
        a, t = self.app, self.app.t
        self.create_line(a.margin, 0, self.w - a.margin, 0, fill=t["line"])
        cy = self.h // 2
        self.text(a.margin + a.px(4), cy, "Your original save is never modified.", 12, t["sub"])
        x = self.w - a.margin - a.px(4)
        s = a.px(22)
        for letter, label, action in reversed(self.HINTS):
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
    def __init__(self, root, src=None, theme=None):
        self.root = root
        self.theme = theme or ("dark" if system_prefers_dark() else "light")
        self.t = THEMES[self.theme]
        self.scale = self._pick_scale()
        self.margin = self.px(5)  # room around each card for the cursor ring
        self.family = self._pick_family()
        self.surfaces, self.selected = [], None
        self._fonts, self._images, self._shots, self._thumbs = {}, {}, {}, {}
        self._pulse, self._pulse_level = 0.0, None
        self._timers = {}  # name -> pending after() id

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
                  self.root.winfo_screenheight() * 0.88 / BASE_H)
        return max(0.75, min(dpi_scale, fit))

    def px(self, v):
        return round(v * self.scale)

    def _pick_family(self):
        default = tkfont.nametofont("TkDefaultFont").actual("family")
        if sys.platform == "darwin":
            return default
        installed = {f.lower(): f for f in tkfont.families(self.root)}
        return next((installed[f.lower()] for f in FONTS if f.lower() in installed), default)

    def font(self, size, bold=False):
        return (self.family, -self.px(size), "bold" if bold else "normal")

    def fontobj(self, size, bold=False):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(root=self.root, family=self.family, size=-self.px(size),
                                           weight="bold" if bold else "normal")
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

    def corner(self, r, fill, bg, i):
        cx, cy = (r, 0)[i % 2], (r, 0)[i // 2]
        return self._cached(("corner", r, fill, bg, i),
                            lambda: raster(self.root, r, r, bg, [(circle(cx, cy, r), fill)]))

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
        bg = self.t["bg"]
        return self._cached(("emblem", size, bg), lambda: raster(
            self.root, size, size, bg, [(rbox(0, 0, size, size, size * .28), THEMES["light"]["accent"]),
                                        (g_rewind(size), "#FFFFFF")]))

    def thumb(self, k, w, h):
        """Slot screenshot scaled to w x h with rounded corners, or None."""
        data = self._shots.get(k)
        if data is None:
            return None
        card = self.t["card"]
        key = (k, w, h, card)
        if key not in self._thumbs:
            rows = resize_rgba(data, SHOT_W, SHOT_H, w, h)
            r = self.px(9)
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
        return mix(a, b, (self._pulse_level or 0) / 7)

    # ---- layout

    def _build(self):
        px, root = self.px, self.root
        W = px(BASE_W)
        pad = px(24) - self.margin
        cw = W - 2 * pad
        self.frame = tk.Frame(root, bg=self.t["bg"], padx=pad, pady=px(14))
        self.frame.pack(fill="both", expand=True)
        f = self.frame

        top = tk.Frame(f, bg=self.t["bg"])
        top.pack(fill="x")
        th = px(56) + self.margin
        self.theme_btn = ThemeButton(top, self, th, th, lambda: self.action("theme"))
        self.theme_btn.pack(side="right")
        Header(top, self, cw - th, th).pack(side="left")
        Divider(f, self, cw, px(12)).pack(anchor="w")

        StepLabel(f, self, cw, px(34), 1, "Your v1.0.1 save").pack(anchor="w")
        self.src_tile = Tile(f, self, cw, px(74) + 2 * self.margin, self.pick_source,
                             "folder", "accent", self._src_content)
        self.src_tile.pack(anchor="w")

        row = tk.Frame(f, bg=self.t["bg"])
        row.pack(anchor="w", pady=(px(2), 0))
        gap = px(8)
        sw = (cw - 3 * gap) // 4
        self.slot_cards = []
        for k in range(sd.SLOT_COUNT):
            card = SlotCard(row, self, sw, 0, k)
            tw, thh = card.thumb_size()
            card.h = thh + px(64) + 2 * self.margin
            card.configure(height=card.h)
            card.pack(side="left", padx=(0 if k == 0 else gap, 0))
            self.slot_cards.append(card)

        StepLabel(f, self, cw, px(34), 2, "Output folder").pack(anchor="w", pady=(px(4), 0))
        self.dst_tile = Tile(f, self, cw, px(66) + 2 * self.margin, self.pick_dest,
                             "tray", "blue", self._dst_content)
        self.dst_tile.pack(anchor="w")

        bottom = tk.Frame(f, bg=self.t["bg"])
        bottom.pack(fill="x", pady=(px(12), px(6)))
        bh = px(54) + 2 * self.margin
        self.convert_btn = PillButton(bottom, self, px(200), bh, self.convert, primary=True)
        self.convert_btn.pack(side="right")
        self.show_btn = PillButton(bottom, self, px(160), bh, self.show_output, primary=False)
        self.show_btn.label = "Show folder"
        self.bottom_w = cw
        self.status_view = StatusView(bottom, self, cw - self.convert_btn.w, bh)
        self.status_view.pack(side="left")

        Footer(f, self, cw, px(46)).pack(anchor="w")
        self.frames = [self.frame, top, row, bottom]

    def focus_order(self):
        order = [self.theme_btn, self.src_tile, self.dst_tile]
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
        # resize the status first so the row never asks for more than the window width
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
            self.theme = "dark" if self.theme == "light" else "light"
            self.t = THEMES[self.theme]
            self.redraw_all()

    def pick_source(self):
        start = self.src_dir if self.src_dir and self.src_dir.is_dir() else Path.home()
        path = filedialog.askdirectory(parent=self.root, initialdir=str(start), mustexist=True,
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
        path = filedialog.askdirectory(parent=self.root, initialdir=str(start), mustexist=False,
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
        """Pulse the cursor ring like the Switch menu."""
        self._pulse += 0.12
        level = round((math.sin(self._pulse) + 1) / 2 * 7)
        if level != self._pulse_level:
            self._pulse_level = level
            if self.selected is not None:
                self.selected.draw_ring()
        self._timers["tick"] = self.root.after(50, self._tick)

    def close(self):
        for timer in self._timers.values():
            self.root.after_cancel(timer)
        self.root.destroy()


def app_icon_png(size):
    """Window icon as a PNG with real transparency."""
    shape, glyph = rbox(0, 0, size, size, size * .28), g_rewind(size)
    red = rgb(THEMES["light"]["accent"])
    raw = bytearray()
    for j in range(size):
        raw.append(0)
        for i in range(size):
            x, y = i + .5, j + .5
            a = min(max(.5 - shape(x, y), 0), 1)
            w = min(max(.5 - glyph(x, y), 0), 1)
            raw += bytes(round(c + (255 - c) * w) for c in red) + bytes([round(a * 255)])

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


GLYPHS = {
    "folder": g_folder, "tray": g_tray, "check": g_check, "bang": g_bang, "info": g_info,
    "chevron": g_chevron, "arrow": g_arrow, "moon": g_moon, "sun": g_sun,
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
