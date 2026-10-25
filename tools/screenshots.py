#!/usr/bin/env python3
"""Regenerate the README screenshots in docs/ (Linux with X11 or XWayland only).

Usage:
    python3 tools/screenshots.py <v1.0.1 save folder>

Opens the GUI in each theme and copies the pixels of its own window (X11
XGetImage by window id, so nothing else on screen can end up in the image).
The shown folder paths are replaced with neutral ones.
"""
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sshd_save_downgrade_gui as gui  # noqa: E402

SCALE = 1.5  # rendered at 1.5x so it stays sharp on HiDPI screens
SHOWN_SRC = Path("/home/user/.config/Ryujinx/bis/user/save/0000000000000001/0")
SHOWN_DST = Path("/home/user/Desktop") / gui.OUT_NAME


class XImage(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("width", "height", "xoffset", "format")] + \
               [("data", ctypes.c_void_p)] + \
               [(name, ctypes.c_int) for name in ("byte_order", "bitmap_unit", "bitmap_bit_order",
                                                  "bitmap_pad", "depth", "bytes_per_line",
                                                  "bits_per_pixel")]


def grab_png(root):
    """PNG bytes of the Tk root window's contents."""
    x11 = ctypes.CDLL("libX11.so.6")
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XGetImage.restype = ctypes.POINTER(XImage)
    x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                              ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
    dpy = x11.XOpenDisplay(None)
    if not dpy:
        raise SystemExit("Can't open the X display.")
    img = x11.XGetImage(dpy, root.winfo_id(), 0, 0, root.winfo_width(), root.winfo_height(),
                        0xFFFFFFFF, 2)  # all planes, ZPixmap
    if not img or img.contents.bits_per_pixel != 32:
        raise SystemExit("XGetImage failed or returned an unexpected pixel format.")
    im = img.contents
    data = ctypes.string_at(im.data, im.bytes_per_line * im.height)
    raw = bytearray()
    for j in range(im.height):
        raw.append(0)
        line = data[j * im.bytes_per_line:j * im.bytes_per_line + im.width * 4]
        for i in range(0, len(line), 4):  # BGRX -> RGBA
            raw += bytes((line[i + 2], line[i + 1], line[i], 255))
    return gui.encode_png(im.width, im.height, raw)


def capture(save, theme, out):
    root = gui.tk.Tk()
    app = gui.App(root, src=save, theme=theme)
    if app.load_error:
        raise SystemExit(f"Couldn't load {save}: {app.load_error}")
    app.src_dir = SHOWN_SRC
    app.set_dest(SHOWN_DST)
    app.refresh()
    app.select(app.convert_btn)
    app.root.after_cancel(app._timers.pop("tick"))  # freeze the cursor pulse at full strength
    app._pulse_level = 0
    app.convert_btn.draw_ring()
    root.after(1000, root.quit)  # give the window manager time to map and paint it
    root.mainloop()
    root.update()
    out.write_bytes(grab_png(root))
    app.close()
    print(f"wrote {out}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__)
    gui.App._pick_scale = lambda self: SCALE
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    for theme in ("light", "dark"):
        capture(argv[0], theme, docs / f"screenshot-{theme}.png")


if __name__ == "__main__":
    main()
