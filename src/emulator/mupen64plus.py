"""
Mupen64Plus Emulator Integration — v0.4.1
==========================================

Bundled download URLs (v2.6.0 official release):
  Windows : mupen64plus-bundle-win64-2.6.0.zip   → mupen64plus-ui-console.exe
  macOS   : mupen64plus-bundle-osx-2.6.0.zip     → mupen64plus
  Linux   : mupen64plus-bundle-linux64-2.6.0.tar.gz → mupen64plus

Priority order when finding the emulator:
  1. Bundled copy  — <app_dir>/emulator/  (downloaded on first run)
  2. System PATH
  3. Known install locations
"""

import logging, os, platform, shutil, subprocess, tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

# ── Bundle paths ──────────────────────────────────────────────────────────────
_APP_DIR   = Path(__file__).parent.parent.parent   # project root
BUNDLE_DIR = _APP_DIR / "emulator"

# Exact executable names inside the zip/tarball
BUNDLE_EXE = {
    "Windows": BUNDLE_DIR / "mupen64plus-ui-console.exe",
    "Darwin":  BUNDLE_DIR / "mupen64plus",
    "Linux":   BUNDLE_DIR / "mupen64plus",
}

# ── Official v2.6.0 download URLs ────────────────────────────────────────────
BASE = "https://github.com/mupen64plus/mupen64plus-core/releases/download/2.6.0"
DOWNLOAD_URLS = {
    "Windows": (f"{BASE}/mupen64plus-bundle-win64-2.6.0.zip",   "zip"),
    "Darwin":  (f"{BASE}/mupen64plus-bundle-osx-2.6.0.zip",    "zip"),
    "Linux":   (f"{BASE}/mupen64plus-bundle-linux64-2.6.0.tar.gz", "tar"),
}

# ── System search (fallback) ──────────────────────────────────────────────────
MUPEN_EXECUTABLES = {
    "Windows": ["mupen64plus-ui-console.exe", "mupen64plus.exe"],
    "Darwin":  ["mupen64plus"],
    "Linux":   ["mupen64plus"],
}

MUPEN_SEARCH_PATHS = {
    "Windows": [
        Path(os.environ.get("PROGRAMFILES",      "C:/Program Files"))       / "mupen64plus",
        Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "mupen64plus",
        Path("C:/mupen64plus"),
        Path.home() / "mupen64plus",
    ],
    "Darwin":  [Path("/usr/local/bin"), Path("/opt/homebrew/bin")],
    "Linux":   [Path("/usr/bin"), Path("/usr/local/bin"), Path("/opt/mupen64plus")],
}


def _get_app_data_dir() -> Path:
    s = platform.system()
    if s == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif s == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / "N64Operator"; d.mkdir(parents=True, exist_ok=True)
    return d


def get_install_instructions() -> str:
    return (
        "Mupen64Plus should download automatically on first launch.\n\n"
        "If it failed:\n"
        "  • Check your internet connection and restart N64 Operator\n\n"
        "Manual install:\n"
        "  Windows: https://mupen64plus.org/\n"
        "  macOS:   brew install mupen64plus\n"
        "  Linux:   sudo apt install mupen64plus"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Downloader — called by N64Operator.py on first run
# ─────────────────────────────────────────────────────────────────────────────

def download_mupen64plus(progress_callback=None) -> bool:
    """
    Download and extract the official Mupen64Plus v2.6.0 bundle.
    Returns True on success.
    progress_callback(message: str, percent: float)
    """
    import urllib.request, urllib.error, zipfile, tarfile, io

    system = platform.system()
    bundle_exe = BUNDLE_EXE.get(system)

    def _prog(msg, pct=0):
        logger.info(f"[mupen] {msg}")
        if progress_callback:
            progress_callback(msg, pct)

    if bundle_exe and bundle_exe.exists():
        _prog("Mupen64Plus already installed.", 100)
        return True

    url_info = DOWNLOAD_URLS.get(system)
    if not url_info:
        _prog(f"No bundled download for {system}.", 100)
        return False

    url, archive_type = url_info
    filename = url.split("/")[-1]

    try:
        # ── Download ─────────────────────────────────────────────────
        _prog(f"Downloading {filename}…", 5)
        buf = io.BytesIO()
        req = urllib.request.Request(url, headers={"User-Agent": "N64Operator/0.3"})

        with urllib.request.urlopen(req, timeout=180) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            while True:
                chunk = resp.read(65536)
                if not chunk: break
                buf.write(chunk)
                done += len(chunk)
                if total:
                    pct = 5 + int(done / total * 72)
                    _prog(
                        f"Downloading Mupen64Plus…  "
                        f"{done//(1024*1024)} / {total//(1024*1024)} MB",
                        pct,
                    )

        # ── Extract ──────────────────────────────────────────────────
        _prog("Extracting…", 79)
        BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
        buf.seek(0)

        if archive_type == "zip":
            with zipfile.ZipFile(buf) as zf:
                members = zf.namelist()
                tops = {Path(m).parts[0] for m in members if Path(m).parts}
                strip = (list(tops)[0] + "/") if len(tops) == 1 else ""
                for i, member in enumerate(members):
                    _prog(f"Extracting…  {i+1}/{len(members)}", 79 + int(i/max(len(members),1)*18))
                    rel = member[len(strip):] if (strip and member.startswith(strip)) else member
                    if not rel: continue
                    dest = BUNDLE_DIR / rel
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(member))

        elif archive_type == "tar":
            with tarfile.open(fileobj=buf, mode="r:gz") as tf:
                members = tf.getmembers()
                tops = {Path(m.name).parts[0] for m in members if Path(m.name).parts}
                strip = (list(tops)[0] + "/") if len(tops) == 1 else ""
                for i, member in enumerate(members):
                    _prog(f"Extracting…  {i+1}/{len(members)}", 79 + int(i/max(len(members),1)*18))
                    rel = member.name[len(strip):] if (strip and member.name.startswith(strip)) else member.name
                    if not rel: continue
                    dest = BUNDLE_DIR / rel
                    if member.isdir():
                        dest.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with tf.extractfile(member) as src:
                            dest.write_bytes(src.read())
                        # Preserve executable bit on Unix
                        if system in ("Darwin", "Linux") and (member.mode & 0o100):
                            dest.chmod(dest.stat().st_mode | 0o111)

        # ── Verify ───────────────────────────────────────────────────
        if bundle_exe and bundle_exe.exists():
            _prog("Mupen64Plus ready!", 100)
            return True

        # Search for the exe in case it landed in a subfolder
        patterns = MUPEN_EXECUTABLES.get(system, ["mupen64plus"])
        for pat in patterns:
            found = list(BUNDLE_DIR.rglob(pat))
            if found:
                shutil.copy2(found[0], BUNDLE_DIR / pat)
                if system in ("Darwin", "Linux"):
                    (BUNDLE_DIR / pat).chmod(0o755)
                _prog("Mupen64Plus ready!", 100)
                return True

        _prog("Extraction done but executable not found.", 0)
        logger.error(f"Bundle contents: {list(BUNDLE_DIR.rglob('*'))[:20]}")
        return False

    except urllib.error.URLError as e:
        _prog(f"Network error: {e.reason}", 0)
        return False
    except Exception as e:
        _prog(f"Download failed: {e}", 0)
        logger.exception("Mupen64Plus download error")
        return False


# ─────────────────────────────────────────────────────────────────────────────



def _write_n64_controller_config(config_dir: Path) -> None:
    """
    Write InputAutoCfg.ini so Mupen64Plus auto-maps 'USB Joystick' to
    the correct N64 buttons on launch.

    Mupen reads InputAutoCfg.ini BEFORE mupen64plus.cfg.
    If the joystick name is not found there, it falls back to keyboard.

    Button numbers from Project64 Player 2 mapping on this hardware:
      A=Button5   B=Button4   Start=Button9  Z=Button8
      L=Button6   R=Button7
      C-Up=Button0  C-Down=Button2  C-Left=Button3  C-Right=Button1
      D-Pad = POV Hat 0
      Analog = X-axis / Y-axis
    """
    config_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. InputAutoCfg.ini — maps joystick NAME → buttons ──────────────
    # Mupen looks for [JoystickName] sections here to auto-configure input
    # Write to BOTH the exe folder and config_dir - Mupen checks both
    auto_cfg_path = config_dir / "InputAutoCfg.ini"

    # Read existing entries so we don't lose other joystick profiles
    existing_lines = []
    skip_section   = False
    if auto_cfg_path.exists():
        try:
            for line in auto_cfg_path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s.startswith("["):
                    # Skip our section — we'll re-add it below
                    skip_section = (s == "[USB Joystick]")
                if not skip_section:
                    existing_lines.append(line)
        except Exception:
            pass

    usb_joystick_entry = """; USB N64 controller auto-config - written by N64 Operator
[USB Joystick]
plugged = True
plugin = 2
mouse = False
AnalogDeadzone = "4096,4096"
AnalogPeak = "32768,32768"
DPad R = "hat(0 Right)"
DPad L = "hat(0 Left)"
DPad D = "hat(0 Down)"
DPad U = "hat(0 Up)"
Start = "button(9)"
Z Trig = "button(8)"
B Button = "button(4)"
A Button = "button(5)"
C Button R = "button(1)"
C Button L = "button(3)"
C Button D = "button(2)"
C Button U = "button(0)"
R Trig = "button(7)"
L Trig = "button(6)"
Mempak switch = ""
Rumblepak switch = ""
X Axis = "axis(0-,0+)"
Y Axis = "axis(1-,1+)"
"""

    try:
        out = "\r\n".join(existing_lines).rstrip() + "\r\n\r\n" + usb_joystick_entry.replace("\n","\r\n")
        auto_cfg_path.write_bytes(out.encode("ascii", errors="replace"))
        logger.info(f"InputAutoCfg.ini written: {auto_cfg_path}")
        # Also write to exe parent dir — Mupen checks there too
        exe_cfg = config_dir.parent / "InputAutoCfg.ini"
        if exe_cfg.parent.exists():
            exe_cfg.write_text(out, encoding="utf-8")
            logger.info(f"InputAutoCfg.ini also written to exe dir: {exe_cfg}")
    except Exception as e:
        logger.warning(f"Could not write InputAutoCfg.ini: {e}")

    # ── 2. mupen64plus.cfg — sets Player 1 = device 0 ──────────────────────
    # Belt-and-suspenders: also set Player 1 in main config
    cfg_path = config_dir / "mupen64plus.cfg"
    player1_block = """
[Input-SDL-Control1]
version = 2
plugged = True
plugin = 2
mouse = False
device = 0
AnalogDeadzone = "4096,4096"
AnalogPeak = "32768,32768"
DPad R = "hat(0 Right)"
DPad L = "hat(0 Left)"
DPad D = "hat(0 Down)"
DPad U = "hat(0 Up)"
Start = "button(9)"
Z Trig = "button(8)"
B Button = "button(4)"
A Button = "button(5)"
C Button R = "button(1)"
C Button L = "button(3)"
C Button D = "button(2)"
C Button U = "button(0)"
R Trig = "button(7)"
L Trig = "button(6)"
Mempak switch = ""
Rumblepak switch = ""
X Axis = "axis(0-,0+)"
Y Axis = "axis(1-,1+)"

[Input-SDL-Control2]
version = 2
plugged = False
plugin = 1
mouse = False
device = -1

[Input-SDL-Control3]
version = 2
plugged = False
plugin = 1
mouse = False
device = -1

[Input-SDL-Control4]
version = 2
plugged = False
plugin = 1
mouse = False
device = -1
"""
    # Keep non-input sections, replace input sections
    existing_cfg = {}
    current_sec   = None
    if cfg_path.exists():
        try:
            for line in cfg_path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if s.startswith("[") and s.endswith("]"):
                    current_sec = s[1:-1]
                    existing_cfg[current_sec] = []
                elif current_sec:
                    existing_cfg[current_sec].append(line)
        except Exception:
            pass

    try:
        out_lines = []
        for sec, sec_lines in existing_cfg.items():
            if not sec.startswith("Input-SDL-Control"):
                out_lines.append(f"[{sec}]")
                out_lines.extend(sec_lines)
                out_lines.append("")
        out_lines.append(player1_block)
        cfg_path.write_text("\n".join(out_lines), encoding="utf-8")
        logger.info(f"mupen64plus.cfg written: {cfg_path}")
    except Exception as e:
        logger.warning(f"Could not write mupen64plus.cfg: {e}")


@dataclass
class EmulatorConfig:
    fullscreen:   bool = False
    resolution:   str  = "1280x720"
    video_plugin: str  = "mupen64plus-video-glide64mk2"   # included in 2.6.0 bundle
    audio_plugin: str  = "mupen64plus-audio-sdl"
    input_plugin: str  = "mupen64plus-input-sdl"
    rsp_plugin:   str  = "mupen64plus-rsp-hle"
    save_dir:     Optional[Path] = None
    config_dir:   Optional[Path] = None
    extra_args:   List[str] = field(default_factory=list)

    @classmethod
    def default(cls) -> "EmulatorConfig":
        d = _get_app_data_dir()
        return cls(save_dir=d / "saves", config_dir=d / "config")


@dataclass
class EmulatorSession:
    process:       Optional[subprocess.Popen]
    rom_temp_path: Optional[Path] = None

    def wait(self):
        if self.process: self.process.wait()
    def terminate(self):
        if self.process and self.process.poll() is None: self.process.terminate()
    def __del__(self):
        if self.rom_temp_path:
            try: self.rom_temp_path.unlink(missing_ok=True)
            except: pass


class EmulatorNotFoundError(Exception):
    pass


class Mupen64PlusLauncher:

    def __init__(self, config: Optional[EmulatorConfig] = None):
        self.config = config or EmulatorConfig.default()
        self._executable: Optional[Path] = None

    def set_executable(self, path) -> None:
        self._executable = Path(path)

    def find_executable(self) -> Optional[Path]:
        if self._executable and self._executable.exists():
            return self._executable

        system = platform.system()

        # 1. Bundled copy
        bundle_exe = BUNDLE_EXE.get(system)
        if bundle_exe and bundle_exe.exists():
            logger.info(f"Using bundled emulator: {bundle_exe}")
            return bundle_exe

        # 2. PATH
        for name in MUPEN_EXECUTABLES.get(system, ["mupen64plus"]):
            found = shutil.which(name)
            if found:
                return Path(found)

        # 3. Known locations
        for base in MUPEN_SEARCH_PATHS.get(system, []):
            for name in MUPEN_EXECUTABLES.get(system, ["mupen64plus"]):
                c = base / name
                if c.exists(): return c

        return None

    def is_available(self) -> bool:
        return self.find_executable() is not None

    def launch_from_bytes(self, rom_data: bytes, title: str = "rom") -> EmulatorSession:
        safe = "".join(c for c in title if c.isalnum() or c in " _-")[:40]
        tmp  = tempfile.NamedTemporaryFile(prefix=f"n64op_{safe}_", suffix=".z64", delete=False)
        try:
            tmp.write(rom_data); tmp.close()
            session = self.launch_from_file(Path(tmp.name))
            session.rom_temp_path = Path(tmp.name)
            return session
        except:
            Path(tmp.name).unlink(missing_ok=True); raise


def _hide_console_window(pid: int) -> None:
    """
    Find the console (text) window belonging to a process and hide it,
    while leaving any graphical windows (the game) untouched.

    Uses ctypes/Win32 EnumWindows to walk all top-level windows,
    match by PID, then check if the window class is a console
    (ConsoleWindowClass) before hiding it.
    """
    try:
        import ctypes
        import ctypes.wintypes

        user32   = ctypes.windll.user32
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible          = user32.IsWindowVisible
        ShowWindow               = user32.ShowWindow
        GetClassNameW            = user32.GetClassNameW
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool,
                                          ctypes.wintypes.HWND,
                                          ctypes.wintypes.LPARAM)

        console_classes = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}

        def _enum_callback(hwnd, _lparam):
            # Get the PID for this window
            win_pid = ctypes.wintypes.DWORD(0)
            GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
            if win_pid.value != pid:
                return True   # Not our process, keep enumerating

            if not IsWindowVisible(hwnd):
                return True   # Already hidden

            # Get window class name
            buf = ctypes.create_unicode_buffer(256)
            GetClassNameW(hwnd, buf, 256)
            cls = buf.value

            if cls in console_classes:
                ShowWindow(hwnd, 0)   # SW_HIDE
                logger.info(f"Hid console window (class={cls}, pid={pid})")

            return True   # Keep enumerating

        cb = WNDENUMPROC(_enum_callback)
        user32.EnumWindows(cb, 0)

    except Exception as e:
        logger.debug(f"_hide_console_window failed (non-fatal): {e}")

    def launch_from_file(self, rom_path: Path) -> EmulatorSession:
        exe = self.find_executable()
        if not exe:
            raise EmulatorNotFoundError(
                "Mupen64Plus not found.\n\n"
                "Use Help → Install Emulator to download it."
            )

        import time

        # Run from exe's own directory — DLLs and plugins resolve from there
        cwd = exe.parent

        # Write controller config to a dedicated config subdir,
        # then pass --configdir so Mupen reads from exactly there.
        cfg_dir = exe.parent / "config"
        cfg_dir.mkdir(exist_ok=True)
        _write_n64_controller_config(cfg_dir)

        # Confirm file written
        auto_cfg = cfg_dir / "InputAutoCfg.ini"
        if auto_cfg.exists():
            logger.info(f"InputAutoCfg.ini OK: {auto_cfg} ({auto_cfg.stat().st_size}B)")
        else:
            logger.error(f"InputAutoCfg.ini MISSING: {auto_cfg}")
        _write_n64_controller_config(exe.parent)

        cmd = [
            str(exe),
            "--configdir", str(cfg_dir),
            "--gfx", "mupen64plus-video-glide64mk2",
            str(rom_path),
        ]
        logger.info(f"Launch: {exe.name}  ROM: {rom_path.name}  cwd: {cwd}")

        try:
            # Fire and forget — no pipes, no waiting.
            # Output goes to the console window (visible, useful for debugging).
            proc = subprocess.Popen(cmd, cwd=str(cwd))
            logger.info(f"Mupen64Plus started (pid={proc.pid})")
            return EmulatorSession(process=proc)

        except FileNotFoundError:
            raise EmulatorNotFoundError(
                f"Executable not found: {exe}\n\n"
                "Use Help → Install Emulator."
            )
        except PermissionError:
            raise EmulatorNotFoundError(f"Permission denied: {exe}")
