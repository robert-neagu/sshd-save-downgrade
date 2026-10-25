#!/usr/bin/env python3
"""Convert Zelda: Skyward Sword HD (Switch) saves from v1.0.1 format to v1.0.0 format.

Usage:
    python3 sshd_save_downgrade.py convert <save folder> <output folder>
    python3 sshd_save_downgrade.py verify <save folder or wiiking2.sav>

The save folder is the one holding wiiking2.sav, skip.dat and the .screenshot files.
`convert` writes a converted copy to the output folder; the input is never modified.
`verify` only reads a save and reports its version and whether its checksums are valid.

See README.md for the save format.
"""
import argparse
import shutil
import struct
import sys
import zlib
from pathlib import Path

FILE_SIZE = 0x1DE20
MAGIC = b"PROJ"
VERSION_OFF = 0x1C
VERSION_100 = 43
VERSION_101 = 44
VERSION_NAMES = {VERSION_100: "v1.0.0", VERSION_101: "v1.0.1"}
SLOT_BASE = 0x20
SLOT_SIZE = 0x53C0
SLOT_DATA = 0x53BC
SLOT_COUNT = 4
GAP = 0x2238
REC_BASE = 0x1D9B0
REC_SIZE = 0x118
TABLE_OFF = 0x64
TABLE_101 = bytes([0, 1, 2, 3, 4, 5, 6, 7, 0xFF])
SLOT_NAMES = ["file 1", "file 2", "file 3", "autosave"]


class SaveError(Exception):
    pass


def slot_crc(buf, k):
    """CRC-32 over slot data + 0x2238 zero bytes + the slot's record."""
    base = SLOT_BASE + k * SLOT_SIZE
    rec = REC_BASE + k * REC_SIZE
    crc = zlib.crc32(buf[base:base + SLOT_DATA])
    crc = zlib.crc32(bytes(GAP), crc)
    return zlib.crc32(buf[rec:rec + REC_SIZE], crc)


def stored_crc(buf, k):
    return struct.unpack_from("<I", buf, SLOT_BASE + k * SLOT_SIZE + SLOT_DATA)[0]


def check_crcs(buf):
    return [stored_crc(buf, k) == slot_crc(buf, k) for k in range(SLOT_COUNT)]


def slot_used(buf, k):
    base = SLOT_BASE + k * SLOT_SIZE
    return struct.unpack_from("<Q", buf, base)[0] != 0  # play time


def check_header(buf):
    if len(buf) != FILE_SIZE or buf[:4] != MAGIC:
        raise SaveError("This doesn't look like a Skyward Sword HD wiiking2.sav.")
    return struct.unpack_from("<I", buf, VERSION_OFF)[0]


def downgrade(buf, log=print):
    buf = bytearray(buf)
    version = check_header(buf)
    if version == VERSION_100:
        raise SaveError("This save is already in v1.0.0 format; nothing to do.")
    if version != VERSION_101:
        raise SaveError(f"Unknown save version {version}; expected {VERSION_101} (v1.0.1).")
    ok = check_crcs(buf)
    if not all(ok):
        bad = ", ".join(SLOT_NAMES[k] for k in range(SLOT_COUNT) if not ok[k])
        raise SaveError(f"Checksum check failed on the original ({bad}); refusing to convert.")

    struct.pack_into("<I", buf, VERSION_OFF, VERSION_100)
    for k in range(SLOT_COUNT):
        t = REC_BASE + k * REC_SIZE + TABLE_OFF
        table = bytes(buf[t:t + len(TABLE_101)])
        if table == TABLE_101:
            buf[t:t + len(TABLE_101)] = bytes(len(TABLE_101))
            log(f"  {SLOT_NAMES[k]}: cleared v1.0.1 table")
        elif any(table):
            log(f"  {SLOT_NAMES[k]}: unexpected data in record table, left as is: {table.hex(' ')}")
        struct.pack_into("<I", buf, SLOT_BASE + k * SLOT_SIZE + SLOT_DATA, slot_crc(buf, k))

    assert all(check_crcs(buf))
    return bytes(buf)


def find_sav(path):
    path = Path(path)
    sav = path / "wiiking2.sav" if path.is_dir() else path
    if not sav.is_file():
        raise SaveError(f"No wiiking2.sav found at {path}")
    return sav


def cmd_convert(src, dst):
    src, dst = Path(src), Path(dst)
    sav = find_sav(src)
    src_dir = sav.parent
    if dst.exists() and dst.resolve() == src_dir.resolve():
        raise SaveError("Output folder must be different from the input folder.")
    print(f"Converting {sav}")
    out = downgrade(sav.read_bytes())
    dst.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.name != "wiiking2.sav" and not f.name.startswith("."):
            shutil.copy2(f, dst / f.name)
    (dst / "wiiking2.sav").write_bytes(out)
    print(f"Done: {dst / 'wiiking2.sav'} (v1.0.0 format, checksums valid)")


def cmd_verify(path):
    sav = find_sav(path)
    buf = sav.read_bytes()
    version = check_header(buf)
    print(f"{sav}")
    print(f"  version: {version} ({VERSION_NAMES.get(version, 'unknown')})")
    ok = check_crcs(buf)
    for k in range(SLOT_COUNT):
        state = "used" if slot_used(buf, k) else "empty"
        print(f"  {SLOT_NAMES[k]:9s} {state:5s}  checksum {'OK' if ok[k] else 'BAD'}")
    return all(ok)


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Convert Zelda: Skyward Sword HD saves from v1.0.1 to v1.0.0 format.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="convert a v1.0.1 save folder to v1.0.0 format")
    c.add_argument("src", help="save folder containing wiiking2.sav (or the file itself)")
    c.add_argument("dst", help="output folder for the converted save")
    v = sub.add_parser("verify", help="show a save's version and check its checksums")
    v.add_argument("path", help="save folder or wiiking2.sav")
    args = p.parse_args(argv)
    try:
        if args.cmd == "convert":
            cmd_convert(args.src, args.dst)
            return 0
        return 0 if cmd_verify(args.path) else 1
    except SaveError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
