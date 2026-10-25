# Skyward Sword HD Save Downgrader

Convert **The Legend of Zelda: Skyward Sword HD** (Nintendo Switch) saves from **v1.0.1** back to **v1.0.0** format.

Version 1.0.0 refuses saves written by 1.0.1 and reports them as corrupted. That's a problem if you want to play on something that only supports 1.0.0, like [Sky Recomp](https://github.com/Apolinario-coder/SkyRecomp) (the native PC port) or a 1.0.0 setup for speedrunning. This tool rewrites a 1.0.1 save so 1.0.0 accepts it, keeping all your progress.

It also documents the save format, including the per-slot checksum, which as far as I know wasn't publicly documented before.

> **Experimental.** This has been tested on a small number of saves. Always keep a backup of your original save.

## Requirements

Python 3.8 or newer. No extra packages. Works on Windows, Linux and macOS.

## Usage

Get your save folder (the one containing `wiiking2.sav`, `skip.dat` and the `.screenshot` files):

- **Ryujinx / Ryubing:** right-click the game → *Open User Save Directory*
- **Switch:** dump the save with a save manager such as [JKSV](https://github.com/J-D-K/JKSV)

Convert it:

```bash
python3 sshd_save_downgrade.py convert path/to/save-folder path/to/output-folder
```

The original folder is never modified. The output folder gets a converted `wiiking2.sav` plus copies of the other files. Put those files into the 1.0.0 game's save folder.

Check a save without changing it:

```bash
python3 sshd_save_downgrade.py verify path/to/save-folder
```

```
path/to/save-folder/wiiking2.sav
  version: 44 (v1.0.1)
  file 1    used   checksum OK
  file 2    empty  checksum OK
  file 3    empty  checksum OK
  autosave  used   checksum OK
```

Going the other way needs no tool: 1.0.1 loads 1.0.0 saves and upgrades them itself.

## What the conversion changes

1. Sets the save version in the header from 44 to 43.
2. Clears a 9-byte table that 1.0.1 adds to each used slot's record (1.0.0 leaves it as zeros).
3. Recomputes the checksum of every slot.

Nothing else is touched. The tool refuses to convert a save whose checksums don't verify, so it won't turn an unexpected file into a broken one.

## Save format

All values are little-endian. `wiiking2.sav` is `0x1DE20` bytes.

| Offset | Size | Contents |
|---|---|---|
| `0x00000` | `0x20` | Header: `"PROJ"` magic, then the save version as a `u32` at `0x1C` |
| `0x00020` | `4 × 0x53C0` | Slots: file 1, file 2, file 3, autosave |
| `0x14F20` | `0x8A90` | Other data, not covered by the slot checksums |
| `0x1D9B0` | `4 × 0x118` | Slot records, one per slot |
| `0x1DE10` | `0x10` | Zero padding |

### Header version

| Value | Written by |
|---|---|
| 43 (`0x2B`) | v1.0.0 |
| 44 (`0x2C`) | v1.0.1 |

### Slots

Each slot is `0x53BC` bytes of game data followed by a `u32` checksum at `+0x53BC`.

| Slot offset | Contents |
|---|---|
| `+0x0000` | Play time (`u64`, ticks at 19.2 MHz) |
| `+0x0008` | Save time (`u64`) |
| `+0x0010` | Link's position (3 × `f32`) |
| `+0x53BC` | Checksum (`u32`) |

Empty slots have a play time of 0.

### Slot records

| Record offset | Contents |
|---|---|
| `+0x00` | Random UUID (v4), generated when the slot is created |
| `+0x10` | `u16`, unknown (appears to be a counter) |
| `+0x54` | Copy of the UUID |
| `+0x64` | v1.0.1 only: `00 01 02 03 04 05 06 07 FF` in used slots |

### Checksum

Each slot's checksum is a standard **CRC-32** (the zlib / IEEE 802.3 one: reflected polynomial `0xEDB88320`, init `0xFFFFFFFF`, final XOR `0xFFFFFFFF`) over a `0x770C`-byte message:

```
slot data (0x53BC bytes) + 0x2238 zero bytes + slot record (0x118 bytes)
```

```python
crc = zlib.crc32(slot_data)
crc = zlib.crc32(bytes(0x2238), crc)
crc = zlib.crc32(record, crc)
```

Because the record (with its UUID) is part of the checksum, copying a slot into another save only works if you copy its record too. The `0x2238` zero bytes are most likely a reserved area of the in-memory save structure. They've been zero in every save examined.

### How it was worked out

Slots with identical data but different UUIDs had different checksums, so the UUID had to be part of the checksummed data. Treating the checksum as a linear function over GF(2), the differences between those slots gave `0x104C11DB7` (the CRC-32 polynomial) as the common factor. Solving for the UUID's position placed it inside a `0x118`-byte block at the end of the message, and the same method found the `0x2238`-byte gap between the slot data and the record. The result matches every slot of every save tested.

## Development

Tests run against real saves placed in a local `saves/` folder, which is gitignored (see `tests/test_saves.py` for the expected layout). Without it, the tests are skipped.

```bash
python3 -m unittest discover -s tests -v
```

## Disclaimer

This is an unofficial fan tool. It isn't affiliated with or endorsed by Nintendo. *The Legend of Zelda* and *Skyward Sword* are trademarks of Nintendo. No game files or save data are included in this repository.

## License

[MIT](LICENSE)
