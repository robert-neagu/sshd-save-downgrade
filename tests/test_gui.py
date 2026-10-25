"""Tests for the GUI. Helper tests always run; App tests need tkinter, a display and ../saves.

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sshd_save_downgrade as sd  # noqa: E402
import sshd_save_downgrade_gui as gui  # noqa: E402

SAVES = ROOT / "saves"


def save_dir(name):
    p = SAVES / name
    if not (p / "wiiking2.sav").is_file():
        raise unittest.SkipTest(f"missing {p}")
    return p


class TestHelpers(unittest.TestCase):
    def test_format_play_time(self):
        self.assertEqual(gui.format_play_time(0), "0m")
        self.assertEqual(gui.format_play_time(59 * 60), "59m")
        self.assertEqual(gui.format_play_time(75 * 3600 + 7 * 60 + 30), "75h 07m")

    def test_resize_rgba_same_size_is_identity(self):
        data = bytes(range(256)) * 4  # 16 x 16 RGBA
        rows = gui.resize_rgba(data, 16, 16, 16, 16)
        for j in range(16):
            for i in range(16):
                o = (j * 16 + i) * 4
                self.assertEqual([round(c) for c in rows[j][i]], list(data[o:o + 3]))

    def test_find_save_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            with self.assertRaises(sd.SaveError):
                gui.find_save_dir(tmp)
            nested = tmp / "0"
            nested.mkdir()
            (nested / "wiiking2.sav").write_bytes(b"x")
            self.assertEqual(gui.find_save_dir(tmp), nested)  # one level down
            self.assertEqual(gui.find_save_dir(nested), nested)
            self.assertEqual(gui.find_save_dir(nested / "wiiking2.sav"), nested)
            other = tmp / "1"
            other.mkdir()
            (other / "wiiking2.sav").write_bytes(b"x")
            with self.assertRaises(sd.SaveError):
                gui.find_save_dir(tmp)  # ambiguous

    def test_output_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            empty = tmp / "empty"
            empty.mkdir()
            self.assertEqual(gui.resolve_output_choice(empty, None), empty)
            self.assertEqual(gui.resolve_output_choice(tmp / "new", None), tmp / "new")
            has_save = tmp / "recomp"
            has_save.mkdir()
            (has_save / "wiiking2.sav").write_bytes(b"x")
            self.assertEqual(gui.resolve_output_choice(has_save, None), has_save)
            # a busy folder like the Desktop gets a subfolder instead of loose files
            self.assertEqual(gui.resolve_output_choice(tmp, None), tmp / gui.OUT_NAME)
            self.assertEqual(gui.resolve_output_choice(has_save, has_save), has_save / gui.OUT_NAME)

    def test_unique_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(gui.unique_output(tmp), tmp / gui.OUT_NAME)
            (tmp / gui.OUT_NAME).mkdir()
            self.assertEqual(gui.unique_output(tmp), tmp / gui.OUT_NAME)  # empty is reusable
            (tmp / gui.OUT_NAME / "wiiking2.sav").write_bytes(b"x")
            self.assertEqual(gui.unique_output(tmp), tmp / f"{gui.OUT_NAME} 2")

    def test_system_env_restores_library_path_when_frozen(self):
        with mock.patch.dict(os.environ, {"LD_LIBRARY_PATH": "/tmp/_MEI1"}, clear=False):
            self.assertEqual(gui.system_env()["LD_LIBRARY_PATH"], "/tmp/_MEI1")  # not frozen
            with mock.patch.object(sys, "frozen", True, create=True):
                self.assertNotIn("LD_LIBRARY_PATH", gui.system_env())
                os.environ["LD_LIBRARY_PATH_ORIG"] = "/opt/lib"
                env = gui.system_env()
                self.assertEqual(env["LD_LIBRARY_PATH"], "/opt/lib")
                self.assertNotIn("LD_LIBRARY_PATH_ORIG", env)

    def test_app_icon_is_png(self):
        self.assertTrue(gui.app_icon_png(16).startswith(b"\x89PNG\r\n\x1a\n"))

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "settings.json"
            self.assertEqual(gui.load_settings(path), {})
            gui.save_settings(path, {"style": "simple"})
            self.assertEqual(gui.load_settings(path), {"style": "simple"})
            path.write_text("not json")
            self.assertEqual(gui.load_settings(path), {})

    def test_every_style_has_both_modes_with_the_same_keys(self):
        keys = set(gui.THEMES["switch"]["light"])
        for style in gui.STYLES:
            self.assertIn(style, gui.LOOKS)
            for mode in ("light", "dark"):
                self.assertLessEqual(keys, set(gui.THEMES[style][mode]), (style, mode))
                if gui.LOOKS[style]["frame"]:
                    self.assertIn("frame", gui.THEMES[style][mode])

    def test_simple_style_is_high_contrast(self):
        def lum(c):
            ch = [v / 255 for v in gui.rgb(c)]
            ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
            return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]

        def ratio(a, b):
            hi, lo = sorted((lum(a), lum(b)), reverse=True)
            return (hi + 0.05) / (lo + 0.05)

        for mode, t in gui.THEMES["simple"].items():
            for bg in ("bg", "card"):  # WCAG AAA for text
                self.assertGreaterEqual(ratio(t["text"], t[bg]), 7, (mode, bg))
                self.assertGreaterEqual(ratio(t["sub"], t[bg]), 7, (mode, bg))
                self.assertGreaterEqual(ratio(t["cursor"][0], t[bg]), 3, (mode, bg))
            for key in ("accent", "blue", "ok", "warn", "bad", "info"):  # labels on colored pills
                self.assertGreaterEqual(ratio(gui.on(t, key), t[key]), 4.5, (mode, key))
            self.assertGreaterEqual(ratio(t["on_off"], t["off"]), 4.5, mode)

    def test_joystick_events(self):
        def ev(value, kind, num):
            return gui.struct.pack("=IhBB", 0, value, kind, num)
        buttons = [gui.BTN_A, gui.BTN_B, gui.BTN_X, gui.BTN_Y]
        axes = [gui.ABS_X, gui.ABS_Y, gui.ABS_HAT0X]
        dirs = {}
        data = (ev(1, 0x81, 0) + ev(1, 1, 0) + ev(0, 1, 0) + ev(1, 1, 2) + ev(1, 1, 3)
                + ev(-32767, 2, 1) + ev(-30000, 2, 1) + ev(0, 2, 1) + ev(32767, 2, 2) + ev(1, 1, 9))
        # init event and release ignored; held stick moves once; unknown button ignored
        self.assertEqual(gui.js_actions(data, buttons, axes, False, dirs),
                         ["ok", "style", "theme", "up", "right"])
        # a Nintendo pad reports its right button (A) as BTN_B
        self.assertEqual(gui.js_actions(ev(1, 1, 1) + ev(1, 1, 0), buttons, axes, True, {}),
                         ["ok", "close"])

    def test_xinput_edges(self):
        state, acts = gui.xinput_actions(0, 0x1000 | 0x4000, 0, 0)
        self.assertEqual(acts, ["ok", "style"])
        state, acts = gui.xinput_actions(state, 0x1000, 0, 30000)  # A held, stick up
        self.assertEqual(acts, ["up"])
        state, acts = gui.xinput_actions(state, 0, 0, 30000)
        self.assertEqual(acts, [])
        self.assertEqual(gui.xinput_actions(state, 0, 30000, 0)[1], ["right"])

    def test_sdf_png_alpha_follows_shape(self):
        png = gui.sdf_png(8, 8, gui.circle(4, 4, 3), "#FF0000")
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        start = png.index(b"IDAT")
        size = int.from_bytes(png[start - 4:start], "big")
        raw = zlib.decompress(png[start + 4:start + 4 + size])
        stride = 1 + 8 * 4  # filter byte + 8 RGBA pixels
        centre = 4 * stride + 1 + 4 * 4
        self.assertEqual(raw[centre:centre + 4], b"\xff\x00\x00\xff")  # opaque red
        self.assertEqual(raw[1 + 3], 0)  # top-left pixel is fully transparent


class TestApp(unittest.TestCase):
    def setUp(self):
        if gui.tk is None:
            self.skipTest("no tkinter")
        try:
            self.root = gui.tk.Tk()
        except gui.tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.apps = []
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        for app in self.apps:
            app.close()
        self.tmp.cleanup()

    def app(self, src=None):
        app = gui.App(self.root, src=src, theme="light", remember=False)
        self.apps.append(app)
        self.root.update()
        return app

    def test_starts_empty(self):
        app = self.app()
        self.assertFalse(app.convert_btn.enabled)
        self.assertFalse(app.dst_tile.enabled)
        self.assertIs(app.selected, app.src_tile)

    def test_convert_matches_known_good(self):
        app = self.app(save_dir("mine-v1.0.1"))
        self.assertEqual(app.version, sd.VERSION_101)
        self.assertEqual([s["used"] for s in app.slots], [True, False, False, True])
        self.assertIsNotNone(app._shots[0])
        self.assertIs(app.selected, app.convert_btn)
        app.set_dest(self.out)
        app.refresh()
        self.assertTrue(app.convert_btn.enabled)
        app.convert()
        self.assertEqual(app.result[0], "ok", app.result)
        good = save_dir("mine-converted-v1.0.0") / "wiiking2.sav"
        self.assertEqual((self.out / "wiiking2.sav").read_bytes(), good.read_bytes())
        self.assertTrue((self.out / "skip.dat").is_file())
        self.assertEqual(app.show_btn.winfo_manager(), "pack")
        self.assertIn(app.show_btn, app.focus_order())

    def test_overwrite_keeps_backup(self):
        app = self.app(save_dir("mine-v1.0.1"))
        self.out.mkdir()
        (self.out / "wiiking2.sav").write_bytes(b"old save")
        app.set_dest(self.out)
        app.refresh()
        self.assertEqual(app.status[0], "warn")
        self.assertEqual(app.convert_btn.label, "Overwrite")
        app.convert()
        self.assertEqual((self.out / "wiiking2.sav.bak").read_bytes(), b"old save")
        self.assertTrue(all(sd.check_crcs((self.out / "wiiking2.sav").read_bytes())))

    def test_v100_save_is_not_converted(self):
        app = self.app(save_dir("fresh-v1.0.0"))
        app.set_dest(self.out)
        app.refresh()
        self.assertFalse(app.convert_btn.enabled)
        self.assertIn("already v1.0.0", app.status[1])

    def test_folder_without_save(self):
        app = self.app(self.tmp.name)
        self.assertIsNotNone(app.load_error)
        self.assertEqual(app.status[0], "bad")
        self.assertFalse(app.convert_btn.enabled)

    def test_same_folder_refused(self):
        src = save_dir("mine-v1.0.1")
        app = self.app(src)
        app.set_dest(src)
        app.refresh()
        self.assertFalse(app.convert_btn.enabled)

    def test_keyboard_navigation_and_theme(self):
        app = self.app(save_dir("mine-v1.0.1"))
        app.select(app.src_tile)
        app.move(1)
        self.assertIs(app.selected, app.dst_tile)
        app.move(-1)
        app.move(-1)
        self.assertIs(app.selected, app.theme_btn)
        app.move(-1)
        self.assertIs(app.selected, app.style_btn)
        app.action("theme")
        self.assertEqual(app.theme, "dark")
        self.root.update()

    def test_styles_rebuild_and_keep_state(self):
        app = self.app(save_dir("mine-v1.0.1"))
        app.set_dest(self.out)
        app.refresh()
        app.select(app.dst_tile)
        seen = []
        for _ in gui.STYLES:
            app.action("style")
            self.root.update()
            seen.append(app.style)
            self.assertEqual(app.selected, app.dst_tile)  # the cursor stays on the same control
            self.assertTrue(app.convert_btn.enabled)
            self.assertLessEqual(self.root.winfo_reqwidth(), app.px(gui.BASE_W))
            self.assertLessEqual(self.root.winfo_reqheight(), app.px(gui.BASE_H[app.style]))
            app.action("theme")
            self.root.update()
        self.assertEqual(seen, ["skyward", "simple", "switch"])
        app.set_style("simple")
        app.convert()
        self.assertEqual(app.result[0], "ok", app.result)
        app.set_style("skyward")
        self.assertEqual(app.show_btn.winfo_manager(), "pack")  # result survives the rebuild
        self.root.update()

    def test_style_and_theme_are_remembered(self):
        path = Path(self.tmp.name) / "settings.json"
        with mock.patch.object(gui, "settings_file", lambda: path):
            app = gui.App(self.root, theme="light")
            self.apps.append(app)
            app.action("style")
            self.assertEqual(gui.load_settings(path), {"style": "skyward"})
            app.action("theme")
            self.assertEqual(gui.load_settings(path), {"style": "skyward", "theme": "dark"})
            app.close()
            self.apps.remove(app)
            self.root = gui.tk.Tk()
            self.root.withdraw()
            app = gui.App(self.root)
            self.apps.append(app)
            self.assertEqual((app.style, app.theme), ("skyward", "dark"))

    def test_gamepad_drives_the_app(self):
        app = self.app(save_dir("mine-v1.0.1"))
        app.pads = mock.Mock()
        app.pads.poll.return_value = ["up", "style"]
        app.has_focus = lambda: True
        app.select(app.src_tile)
        app._poll_pads()
        self.assertEqual(app.style, "skyward")
        self.assertIs(app.selected, app.theme_btn)
        app.busy = True  # a file dialog is open
        app._poll_pads()
        self.assertEqual(app.style, "skyward")


if __name__ == "__main__":
    unittest.main()
