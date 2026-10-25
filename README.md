# Skyward Sword HD Save Downgrader

Convert **The Legend of Zelda: Skyward Sword HD** (Nintendo Switch) saves from **v1.0.1** back to **v1.0.0** format.

Version 1.0.0 refuses saves written by 1.0.1 and reports them as corrupted. That's a problem if you want to play on something that only supports 1.0.0, like [Sky Recomp](https://github.com/Apolinario-coder/SkyRecomp) (the native PC port) or a 1.0.0 setup for speedrunning. This tool rewrites a 1.0.1 save so 1.0.0 accepts it, keeping all your progress.

It also documents the save format, including the per-slot checksum, which as far as I know wasn't publicly documented before.

> **Experimental.** This has been tested on a small number of saves. Always keep a backup of your original save.

> **AI Assisted.** This tool was made with the help of AI (Claude Code). See [Disclaimer](#disclaimer).

## Download

Get the file for your system from the [latest release](https://github.com/robert-neagu/sshd-save-downgrade/releases/latest). The apps need nothing else installed.

| System | File |
|---|---|
| Windows | `sshd-save-downgrader-windows.exe` |
| macOS (Apple Silicon) | `sshd-save-downgrader-macos.zip` |
| Linux (x86-64) | `sshd-save-downgrader-linux` |
| Anything with Python 3.8+ | `sshd_save_downgrade_gui.py` (GUI) or `sshd_save_downgrade.py` (command line) |

The apps aren't signed, so the first launch needs an extra step:

- **Windows:** SmartScreen warns about an unknown publisher. Click **More info**, then **Run anyway**.
- **macOS:** unzip, then open `sshd-save-downgrader.app`. Gatekeeper blocks unsigned apps: right-click the app and choose **Open**. On macOS 15 and newer that no longer works; instead try to open it once, then go to **System Settings > Privacy & Security** and click **Open Anyway**. Or remove the quarantine flag in Terminal:

  ```bash
  xattr -dr com.apple.quarantine sshd-save-downgrader.app
  ```

- **Linux:** make the file executable, then run it. It's built on Ubuntu 22.04, so it needs a distro at least that new (glibc 2.35 or newer).

  ```bash
  chmod +x sshd-save-downgrader-linux
  ./sshd-save-downgrader-linux
  ```

On an Intel Mac, or anything else without a matching app, use the `.py` files.

## Running the Python files

Python 3.8 or newer. No extra packages. Works on Windows, Linux and macOS. The command line tool needs nothing beyond Python itself.

The GUI uses tkinter, which ships with Python on Windows and with the python.org installer on macOS. Some setups need it installed separately:

| System | Command |
|---|---|
| Debian / Ubuntu | `sudo apt install python3-tk` |
| Fedora | `sudo dnf install python3-tkinter` |
| Arch | `sudo pacman -S tk` |
| macOS (Homebrew Python) | `brew install python-tk` |

## Usage

Get your save folder (the one containing `wiiking2.sav`, `skip.dat` and the `.screenshot` files):

- **Ryujinx / Ryubing:** right-click the game → *Open User Save Directory*
- **Switch:** dump the save with a save manager such as [JKSV](https://github.com/J-D-K/JKSV)

### GUI

Start the app you downloaded, or run the script:

```bash
python3 sshd_save_downgrade_gui.py
```

On Windows you can also double-click `sshd_save_downgrade_gui.py`. Then:

1. Click **Your v1.0.1 save** and pick the save folder. The GUI shows the save's version and each slot with its screenshot, play time and checksum.
2. Check the **Output folder**. It defaults to a new `Skyward Sword HD save (v1.0.0)` folder on your Desktop. If you pick a folder that already has other files in it, the GUI creates that subfolder inside it. If you pick a folder that already holds a save, the GUI replaces that save and keeps the old one as `wiiking2.sav.bak`.
3. Click **Convert**, then **Show folder**.

The GUI also works with the keyboard, using Switch-style controls: arrow keys move the cursor, A or Enter selects, B or Esc closes, Y switches between the light and dark theme. You can also pass the save folder when starting it, e.g. `python3 sshd_save_downgrade_gui.py path/to/save-folder` or `./sshd-save-downgrader-linux path/to/save-folder`.

### Command line

The command line tool is `sshd_save_downgrade.py` (it isn't part of the downloadable apps). Convert a save:

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

Tests run against real saves placed in a local `saves/` folder, which is gitignored (see `tests/test_saves.py` for the expected layout). Without it, the tests are skipped. The GUI tests also need tkinter and a display, and are skipped without them.

```bash
python3 -m unittest discover -s tests -v
```

### Releases

Pushing a tag like `v1.2.0` runs `.github/workflows/release.yml`. It runs the tests and builds the apps with [PyInstaller](https://pyinstaller.org) on Windows, macOS and Linux. Then it publishes a GitHub release with the three apps and both `.py` files. To build the app locally (PyInstaller is only needed for building):

```bash
python3 -m venv .venv
.venv/bin/pip install "pyinstaller>=6.22,<7"
.venv/bin/pyinstaller --onefile --windowed --name sshd-save-downgrader sshd_save_downgrade_gui.py
```

The app ends up in `dist/`. On macOS, use `--onedir` instead of `--onefile` to get a `.app` bundle.

## Disclaimer

This is an unofficial fan tool. It isn't affiliated with or endorsed by Nintendo. *The Legend of Zelda* and *Skyward Sword* are trademarks of Nintendo. No game files or save data are included in this repository.

This tool is **AI Assisted**: the code, tests and documentation were written with the help of an AI coding assistant (Claude Code). It was tested on real saves, including loading a converted save in v1.0.0, but it comes with no warranty. Keep a backup of your save.

## License

[MIT](LICENSE)
