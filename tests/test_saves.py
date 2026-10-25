"""Tests against real saves in ../saves (not committed). Skipped when the saves are missing.

Expected layout:
    saves/fresh-v1.0.0/          new game written by v1.0.0
    saves/fresh-v1.0.1/          new game written by v1.0.1
    saves/mine-v1.0.1/           long real save written by v1.0.1
    saves/mine-converted-v1.0.0/ that save after conversion, confirmed to load in v1.0.0

Run: python3 -m unittest discover -s tests
"""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import sshd_save_downgrade as sd  # noqa: E402

SAVES = ROOT / "saves"


def sav(name):
    p = SAVES / name / "wiiking2.sav"
    if not p.is_file():
        raise unittest.SkipTest(f"missing {p}")
    return p.read_bytes()


class TestSaves(unittest.TestCase):
    def test_all_checksums_valid(self):
        for name in ("fresh-v1.0.0", "fresh-v1.0.1", "mine-v1.0.1", "mine-converted-v1.0.0"):
            with self.subTest(save=name):
                self.assertTrue(all(sd.check_crcs(sav(name))))

    def test_versions(self):
        self.assertEqual(sd.check_header(sav("fresh-v1.0.0")), sd.VERSION_100)
        self.assertEqual(sd.check_header(sav("fresh-v1.0.1")), sd.VERSION_101)
        self.assertEqual(sd.check_header(sav("mine-v1.0.1")), sd.VERSION_101)

    def test_conversion_matches_known_good(self):
        out = sd.downgrade(sav("mine-v1.0.1"), log=lambda *_: None)
        self.assertEqual(out, sav("mine-converted-v1.0.0"))

    def test_conversion_only_touches_expected_bytes(self):
        src = sav("mine-v1.0.1")
        out = sd.downgrade(src, log=lambda *_: None)
        allowed = {sd.VERSION_OFF}
        for k in range(sd.SLOT_COUNT):
            crc = sd.SLOT_BASE + k * sd.SLOT_SIZE + sd.SLOT_DATA
            allowed.update(range(crc, crc + 4))
            t = sd.REC_BASE + k * sd.REC_SIZE + sd.TABLE_OFF
            allowed.update(range(t, t + len(sd.TABLE_101)))
        changed = {i for i in range(len(src)) if src[i] != out[i]}
        self.assertTrue(changed <= allowed, sorted(hex(i) for i in changed - allowed))

    def test_fresh_conversion_has_v100_shape(self):
        out = sd.downgrade(sav("fresh-v1.0.1"), log=lambda *_: None)
        ref = sav("fresh-v1.0.0")
        self.assertEqual(out[:0x20], ref[:0x20])
        for k in range(sd.SLOT_COUNT):
            t = sd.REC_BASE + k * sd.REC_SIZE + sd.TABLE_OFF
            self.assertEqual(out[t:t + 9], ref[t:t + 9])

    def test_refuses_v100(self):
        with self.assertRaises(sd.SaveError):
            sd.downgrade(sav("fresh-v1.0.0"))

    def test_refuses_bad_checksum(self):
        bad = bytearray(sav("mine-v1.0.1"))
        bad[sd.SLOT_BASE + 0x100] ^= 0xFF
        with self.assertRaises(sd.SaveError):
            sd.downgrade(bytes(bad))

    def test_convert_command_copies_folder(self):
        src = SAVES / "mine-v1.0.1"
        if not src.is_dir():
            self.skipTest("missing saves")
        with tempfile.TemporaryDirectory() as tmp:
            sd.cmd_convert(src, tmp)
            names = {p.name for p in Path(tmp).iterdir()}
            self.assertIn("wiiking2.sav", names)
            self.assertIn("skip.dat", names)
            self.assertNotIn(".nx_save_meta.bin", names)


if __name__ == "__main__":
    unittest.main()
