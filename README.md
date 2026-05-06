# N64 Operator

<p align="center">
  <img src="https://img.shields.io/badge/version-0.6.3-green" />
  <img src="https://img.shields.io/badge/platform-Windows-blue" />
  <img src="https://img.shields.io/badge/python-3.10%2B-yellow" />
  <img src="https://img.shields.io/badge/emulator-Mupen64Plus%202.6.0-orange" />
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" />
</p>

<p align="center">
  A clean desktop application for reading Nintendo 64 cartridges via the DreamDump64 USB dumper and launching them in Mupen64Plus — with automatic game identification, cover art, and full controller mapping.
</p>

---

## Overview

Insert a cartridge into your DreamDump64, plug it into USB, and N64 Operator handles the rest. It detects the device, waits for the dump to complete, identifies the game, and gets you playing in a few clicks.



---

## Features

- 🎮 **One-click launch** — reads the cart, identifies the game, launches the emulator
- 📀 **Auto-detects DreamDump64** — finds the drive automatically when plugged in
- 🗂️ **293-game database** — identifies games by CRC32, game code, and title
- 🖼️ **Cover art** — bundled art for common titles, fetches the rest from libretro CDN
- ✅ **Cartridge authentication** — Official Cartridge badge for CRC-verified dumps
- 🎯 **Controller mapping** — full button remapping for any USB controller
- 🕹️ **Any controller supported** — Xbox, PlayStation, N64 adapter, keyboard
- ⬇️ **Auto-installs Mupen64Plus** — downloads and sets up the emulator on first run
- 🔄 **Cart swap support** — New Game flow guides you through swapping cartridges

---

## Hardware Required

| Device | Where to get it |
|---|---|
| **DreamDump64** | [dreammods.net](https://dreammods.net) |
| **USB controller** | Any USB gamepad — N64 adapter, Xbox, PlayStation, or generic |

The DreamDump64 mounts as a standard USB mass storage device. No drivers required.

---

## Quick Start

### Run from source
```bash
# 1. Clone or download the repo
# 2. Double-click run.bat
# That's it — first run sets up the environment automatically
```

### Build a standalone EXE
```bash
# 1. Run run.bat at least once first
# 2. Double-click BUILD.bat
# Output: dist\N64Operator.exe
```

---

## First Time Setup

1. Plug in your DreamDump64
2. Launch the app via `run.bat`
3. Go to **Help → Install Emulator** to download Mupen64Plus (~8MB)
4. Insert a cartridge — the app detects and reads it automatically
5. Click **PLAY**

---

## Controller Setup

Go to **Emulator → Controller Setup**:

1. Select **USB / Gamepad** or **Keyboard**
2. Pick your controller from the dropdown
3. Click any N64 button slot, then press the matching button on your controller
4. Or use the **N64 adapter**, **Xbox**, or **PlayStation** preset to auto-fill
5. Click **Save & Apply**

---

## Project Structure

```
n64op-new/
├── main.py                        # Entry point
├── N64Operator.py                 # Self-bootstrapping launcher
├── run.bat                        # One-click dev runner
├── BUILD.bat                      # PyInstaller EXE builder
├── requirements.txt
└── src/
    ├── core/
    │   └── rom.py                 # ROM parsing, format detection
    ├── hardware/
    │   └── device.py              # DreamDump64 detection & reading
    ├── database/
    │   ├── game_db.py             # Game database, cover art, pricing
    │   └── n64_games.json         # 293-game bundled database
    ├── emulator/
    │   └── mupen64plus.py         # Launcher, auto-download, controller config
    └── ui/
        ├── playback.py            # Main window
        ├── controller.py          # Controller mapping dialog
        └── settings.py            # Settings dialog
```

---

## How It Works

### Reading a cartridge
The DreamDump64 dumps the cartridge ROM to a file on its virtual drive. N64 Operator monitors the file size and validates the ROM magic bytes — only reading once the dump is stable and confirmed valid. This prevents the "Unrecognized ROM" errors that occur when reading a partially-written file.

### Identifying the game
Games are matched in priority order:
1. **CRC32** — exact match against No-Intro verified database (confirms authentic dump)
2. **Game code** — 4-character code from ROM header (e.g. `NSME` = Super Mario 64 USA)
3. **Title string** — 20-character title from ROM header as fallback

### Launching
The ROM is saved to `AppData\Roaming\N64Operator\roms\` before launch. The controller config (`InputAutoCfg.ini` and `mupen64plus.cfg`) is written fresh before every launch — in ASCII with Windows line endings, which is what Mupen64Plus requires.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| PyQt6 | ≥ 6.6.0 | UI framework |
| pyusb | ≥ 1.2.1 | USB device detection |
| pygame | ≥ 2.5.0 | Controller input detection |
| Mupen64Plus | 2.6.0 | N64 emulator (auto-downloaded) |

Install dependencies:
```bash
pip install -r requirements.txt
```

---

## Compatibility

| Platform | Status |
|---|---|
| Windows 10 / 11 | ✅ Fully supported |
| macOS | ⚠️ Partial (no auto-install, manual Mupen64Plus setup) |
| Linux | ⚠️ Partial (manual setup required) |

---

## Roadmap

- [ ] Full No-Intro CRC database integration
- [ ] Bundled cover art for all 293 games
- [ ] Hide Mupen64Plus console window after launch
- [ ] Cartridge save file management
- [ ] macOS / Linux polish

---

## License

MIT — free to use, modify, and distribute.

---

## Acknowledgements

- [Mupen64Plus](https://mupen64plus.org/) — open source N64 emulator
- [libretro thumbnails](https://thumbnails.libretro.com/) — cover art CDN
- [No-Intro](https://no-intro.org/) — verified ROM database
- Inspired by the [Epilogue Operator](https://www.epilogue.co/)
