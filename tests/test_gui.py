"""Tests for the GUI. Helper tests always run; App tests need tkinter, a display and ../saves.

Run: python3 -m unittest discover -s tests
"""
import os
import sys
import tempfile
import unittest
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
        app = gui.App(self.root, src=src, theme="light")
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
        app.action("theme")
        self.assertEqual(app.theme, "dark")
        self.root.update()


if __name__ == "__main__":
    unittest.main()
