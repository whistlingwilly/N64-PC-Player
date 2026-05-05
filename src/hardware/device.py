"""
N64 Hardware — DreamDump64 Device Manager
==========================================

The DreamDump64 mounts as USB mass storage (drive letter on Windows).
When a cartridge is inserted it writes ROMF.Z64 to the drive.

Key behaviours:
  - We wait for the file to STOP changing size AND have valid N64 magic bytes
    before reading — the device may take several seconds to dump the cart
  - The monitor loop fires state callbacks but never triggers reads itself
  - Only PlaybackWindow._start_load() triggers actual ROM reading
"""

import os
import platform
import threading
import time
import logging
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Optional, Callable, List, Tuple

logger = logging.getLogger(__name__)

ROM_FILENAME_Z64 = "ROMF.Z64"
ROM_FILENAME_N64 = "ROM.N64"
DRIVE_LABEL      = "DreamDump64"

N64_ROM_MIN_SIZE  =  4 * 1024 * 1024   # 4 MB
N64_ROM_MAX_SIZE  = 64 * 1024 * 1024   # 64 MB
N64_ROM_TYPICAL   =  8 * 1024 * 1024   # 8 MB

# Valid first bytes for any N64 ROM format
VALID_FIRST_BYTES = {0x80, 0x37, 0x40}

KNOWN_DEVICES: List[Tuple[int, int, str]] = [
    (0x1A86, 0x7523, "CH340/CH341 USB-Serial (DreamDump64)"),
    (0x0403, 0x6001, "FTDI FT232RL"),
]


class DeviceState(Enum):
    DISCONNECTED       = auto()
    CONNECTED          = auto()   # Drive mounted, no valid ROM yet
    CARTRIDGE_DETECTED = auto()   # Valid ROM file confirmed
    DUMPING            = auto()   # Reading bytes
    READY              = auto()   # ROM loaded
    ERROR              = auto()


@dataclass
class N64Device:
    name:       str = "DreamDump64"
    mount_path: Optional[Path] = None

    def rom_path_any(self) -> Optional[Path]:
        """Return a ROM path only if the file exists and is large enough."""
        if not self.mount_path:
            return None
        for name in (ROM_FILENAME_Z64, ROM_FILENAME_N64):
            p = self.mount_path / name
            try:
                if p.exists() and p.stat().st_size >= N64_ROM_MIN_SIZE:
                    return p
            except OSError:
                continue
        return None


class DumpProgress:
    def __init__(self, total_bytes: int):
        self.total_bytes = total_bytes
        self.bytes_read  = 0
        self.start_time  = time.time()

    @property
    def percent(self) -> float:
        return (self.bytes_read / self.total_bytes * 100.0) if self.total_bytes else 0.0

    @property
    def bytes_per_second(self) -> float:
        e = time.time() - self.start_time
        return self.bytes_read / e if e > 0 else 0.0


# ── Drive finders ─────────────────────────────────────────────────────────────

def _find_dreamdump64_drive() -> Optional[Path]:
    system = platform.system()
    if system == "Windows":  return _find_drive_windows()
    if system == "Darwin":   return _find_drive_macos()
    return _find_drive_linux()


def _find_drive_windows() -> Optional[Path]:
    try:
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if not (bitmask & 1):
                bitmask >>= 1
                continue
            bitmask >>= 1
            drive = f"{letter}:\\"
            try:
                vol = ctypes.create_unicode_buffer(256)
                ctypes.windll.kernel32.GetVolumeInformationW(
                    drive, vol, 256, None, None, None, None, 0)
                if DRIVE_LABEL.lower() in vol.value.lower():
                    logger.info(f"DreamDump64 found by label: {drive}")
                    return Path(drive)
                # Fallback: ROM file present
                dp = Path(drive)
                if (dp / ROM_FILENAME_Z64).exists() or (dp / ROM_FILENAME_N64).exists():
                    logger.info(f"DreamDump64 found by ROM file: {drive}")
                    return dp
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Windows drive scan error: {e}")
    return None


def _find_drive_macos() -> Optional[Path]:
    volumes = Path("/Volumes")
    if not volumes.exists():
        return None
    for vol in volumes.iterdir():
        if DRIVE_LABEL.lower() in vol.name.lower():
            return vol
        if (vol / ROM_FILENAME_Z64).exists() or (vol / ROM_FILENAME_N64).exists():
            return vol
    return None


def _find_drive_linux() -> Optional[Path]:
    import getpass
    user = getpass.getuser()
    for root in [Path(f"/media/{user}"), Path("/media"),
                 Path(f"/run/media/{user}"), Path("/mnt")]:
        if not root.exists():
            continue
        try:
            for entry in root.iterdir():
                if not entry.is_dir(): continue
                if DRIVE_LABEL.lower() in entry.name.lower(): return entry
                if (entry / ROM_FILENAME_Z64).exists() or (entry / ROM_FILENAME_N64).exists():
                    return entry
        except PermissionError:
            continue
    return None


def _is_valid_rom_file(path: Path) -> bool:
    """
    Quick check: read first byte of the file.
    Returns True if it looks like a valid N64 ROM (any byte-order format).
    """
    try:
        with open(path, "rb") as f:
            first = f.read(1)
        if not first:
            return False
        return first[0] in VALID_FIRST_BYTES
    except OSError:
        return False


# ── Device Manager ────────────────────────────────────────────────────────────

class DeviceManager:

    def __init__(self):
        self._state  = DeviceState.DISCONNECTED
        self._device: Optional[N64Device] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._monitor_thread: Optional[threading.Thread] = None

        self.on_state_change: Optional[Callable] = None
        self.on_error:        Optional[Callable] = None

    @property
    def state(self) -> DeviceState:
        with self._lock: return self._state

    @property
    def device(self) -> Optional[N64Device]:
        with self._lock: return self._device

    def start_monitoring(self) -> None:
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, name="DriveMonitor", daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self) -> None:
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3.0)

    def dump_rom(self, progress_callback: Optional[Callable] = None) -> bytes:
        """
        Wait for the ROM file to be fully written, then read and return it.
        Raises RuntimeError if the drive or ROM is not available.
        """
        with self._lock:
            device = self._device

        if not device or not device.mount_path:
            raise RuntimeError("DreamDump64 drive not mounted.")

        # Find the ROM file (any format)
        rom_path = self._wait_for_valid_rom(device, progress_callback)
        if not rom_path:
            raise RuntimeError(
                "No valid ROM found on the DreamDump64 drive.\n"
                "Make sure a cartridge is inserted and the dump is complete.\n"
                "If this keeps failing, try ejecting and re-inserting the cartridge."
            )

        self._set_state(DeviceState.DUMPING)
        try:
            data = self._read_rom_file(rom_path, progress_callback)
            self._set_state(DeviceState.READY)
            return data
        except Exception as e:
            self._set_state(DeviceState.ERROR)
            raise

    def _wait_for_valid_rom(
        self,
        device: N64Device,
        progress_callback: Optional[Callable],
        timeout_secs: int = 60,
    ) -> Optional[Path]:
        """
        Wait until a ROM file exists on the drive, has a stable size,
        AND starts with valid N64 magic bytes.

        Returns the path when ready, or None if timeout.
        """
        logger.info("Waiting for valid ROM file on drive…")
        deadline = time.time() + timeout_secs
        prev_size: int = -1
        stable_count: int = 0

        while time.time() < deadline:
            rom = device.rom_path_any()

            if not rom:
                # No file yet
                if progress_callback:
                    p = DumpProgress(1); p.bytes_read = 0
                    progress_callback(p)
                time.sleep(2.0)
                prev_size = -1
                stable_count = 0
                continue

            try:
                cur_size = rom.stat().st_size
            except OSError:
                time.sleep(1.0)
                continue

            # Check magic bytes
            valid_magic = _is_valid_rom_file(rom)

            logger.info(
                f"ROM check: {rom.name}  size={cur_size//(1024*1024)}MB  "
                f"prev={prev_size//(1024*1024) if prev_size>=0 else '?'}MB  "
                f"stable={stable_count}  magic={'OK' if valid_magic else 'INVALID'}"
            )

            if valid_magic and cur_size == prev_size and cur_size >= N64_ROM_MIN_SIZE:
                stable_count += 1
                if stable_count >= 2:
                    logger.info(f"ROM ready: {rom}")
                    return rom
            else:
                stable_count = 0

            prev_size = cur_size

            if progress_callback:
                p = DumpProgress(max(cur_size, 1)); p.bytes_read = 0
                progress_callback(p)

            time.sleep(1.5)

        logger.warning("Timed out waiting for valid ROM")
        return None

    def _read_rom_file(
        self,
        path: Path,
        progress_callback: Optional[Callable] = None,
    ) -> bytes:
        """Read ROM file in chunks with progress reporting."""
        size = path.stat().st_size
        logger.info(f"Reading ROM: {path}  ({size / (1024*1024):.1f} MB)")

        progress = DumpProgress(size)
        chunk_size = 512 * 1024
        result = bytearray()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                result.extend(chunk)
                progress.bytes_read = len(result)
                if progress_callback:
                    progress_callback(progress)

        logger.info(f"ROM read complete: {len(result) // (1024*1024)} MB")
        return bytes(result)

    def probe_device(self) -> dict:
        result: dict = {"devices": [], "error": None, "dreamdump64_drive": None}
        drive = _find_dreamdump64_drive()
        if drive:
            result["dreamdump64_drive"] = str(drive)
            rom = drive / ROM_FILENAME_Z64
            valid = _is_valid_rom_file(rom) if rom.exists() else False
            result["devices"].append({
                "manufacturer": "DreamDump64",
                "product": f"Drive: {drive}",
                "rom_present": rom.exists(),
                "rom_valid": valid,
                "rom_size_mb": round(rom.stat().st_size / (1024*1024), 1) if rom.exists() else 0,
            })
        try:
            import usb.core, usb.util
            for dev in (usb.core.find(find_all=True) or []):
                try: mfr = usb.util.get_string(dev, dev.iManufacturer) or "Unknown"
                except: mfr = "Unknown"
                try: prod = usb.util.get_string(dev, dev.iProduct) or "Unknown"
                except: prod = "Unknown"
                result["devices"].append({
                    "vid": f"{dev.idVendor:04X}", "pid": f"{dev.idProduct:04X}",
                    "manufacturer": mfr, "product": prod,
                })
        except Exception:
            pass
        return result

    def _monitor_loop(self) -> None:
        """
        Watch for drive appearance/disappearance.
        Does NOT trigger ROM reads — only updates state.
        """
        was_connected = False

        while not self._stop_event.is_set():
            mount = _find_dreamdump64_drive()
            is_connected = mount is not None

            if is_connected and not was_connected:
                logger.info(f"DreamDump64 appeared: {mount}")
                with self._lock:
                    self._device = N64Device(name="DreamDump64", mount_path=mount)
                self._set_state(DeviceState.CONNECTED)

            elif not is_connected and was_connected:
                logger.info("DreamDump64 removed")
                with self._lock:
                    self._device = None
                self._set_state(DeviceState.DISCONNECTED)

            was_connected = is_connected
            self._stop_event.wait(timeout=1.5)

    def _set_state(self, new_state: DeviceState) -> None:
        with self._lock:
            old = self._state
            self._state = new_state
            device = self._device
        if old != new_state:
            logger.debug(f"State: {old.name} → {new_state.name}")
            if self.on_state_change:
                self.on_state_change(new_state, device)
