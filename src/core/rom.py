"""
N64 ROM parser.

Formats:
  .z64  Big-endian (native)     Magic: 0x80...
  .v64  Byte-swapped            Magic: 0x37...
  .n64  Little-endian           Magic: 0x40...

We always normalise to Z64 internally.
"""

import logging
import struct
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ROMFormat(Enum):
    Z64     = "z64"
    V64     = "v64"
    N64     = "n64"
    UNKNOWN = "unknown"


COUNTRY_CODES = {
    0x41: "Asia",    0x42: "Brazil",  0x43: "China",
    0x44: "Germany", 0x45: "USA",     0x46: "France",
    0x47: "Gateway", 0x49: "Italy",   0x4A: "Japan",
    0x4B: "Korea",   0x4E: "Canada",  0x50: "Europe",
    0x53: "Spain",   0x55: "Australia",
    0x57: "Scandinavia", 0x58: "Europe", 0x59: "Europe",
}


@dataclass
class ROMHeader:
    pi_bsd_dom1_lat_reg: int
    pi_bsd_dom1_pwd_reg: int
    pi_bsd_dom1_pgs_reg: int
    pi_bsd_dom1_rls_reg: int
    clock_rate:       int
    boot_address:     int
    libultra_version: int
    check_code:       int
    title:            str
    game_code:        str
    mask_rom_version: int
    country_code:     int

    @property
    def crc1(self) -> int:
        return (self.check_code >> 32) & 0xFFFFFFFF

    @property
    def crc2(self) -> int:
        return self.check_code & 0xFFFFFFFF

    @property
    def region(self) -> str:
        return COUNTRY_CODES.get(self.country_code,
                                  f"Unknown (0x{self.country_code:02X})")

    @property
    def is_ntsc(self) -> bool:
        return self.country_code in (0x45, 0x4A, 0x42, 0x43, 0x41, 0x55, 0x4E, 0x47)


@dataclass
class ROMInfo:
    path:       Optional[Path]
    format:     ROMFormat
    size_bytes: int
    header:     ROMHeader
    data:       bytes = field(repr=False)

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def title_clean(self) -> str:
        return self.header.title.strip()


def detect_format(data: bytes) -> ROMFormat:
    """Detect ROM byte-order from first byte (most reliable)."""
    if len(data) < 4:
        return ROMFormat.UNKNOWN
    first = data[0]
    logger.debug(f"ROM first bytes: {data[:4].hex()}  first=0x{first:02X}")
    if first == 0x80:
        return ROMFormat.Z64
    if first == 0x37:
        return ROMFormat.V64
    if first == 0x40:
        return ROMFormat.N64
    # Also try exact magic
    magic = struct.unpack(">I", data[:4])[0]
    if magic == 0x80371240: return ROMFormat.Z64
    if magic == 0x37804012: return ROMFormat.V64
    if magic == 0x40123780: return ROMFormat.N64
    logger.warning(f"Unknown ROM magic: 0x{magic:08X}  bytes={data[:8].hex()}")
    return ROMFormat.UNKNOWN


def byteswap_v64(data: bytes) -> bytes:
    arr = bytearray(data)
    for i in range(0, len(arr) - 1, 2):
        arr[i], arr[i+1] = arr[i+1], arr[i]
    return bytes(arr)


def byteswap_n64(data: bytes) -> bytes:
    arr = bytearray(data)
    for i in range(0, len(arr) - 3, 4):
        arr[i], arr[i+1], arr[i+2], arr[i+3] = arr[i+3], arr[i+2], arr[i+1], arr[i]
    return bytes(arr)


def normalize_to_z64(data: bytes, fmt: ROMFormat) -> bytes:
    if fmt == ROMFormat.Z64: return data
    if fmt == ROMFormat.V64: return byteswap_v64(data)
    if fmt == ROMFormat.N64: return byteswap_n64(data)
    raise ValueError("Cannot normalize unknown ROM format")


def parse_header(data: bytes) -> ROMHeader:
    """
    Parse N64 ROM header. Data must be Z64 (big-endian).

    N64 ROM header layout (all big-endian):
      0x00: PI BSD DOM1 registers (4 bytes)
      0x04: Clock rate (4 bytes)
      0x08: Boot address (4 bytes)
      0x0C: Libultra version (4 bytes)
      0x10: CRC1 (4 bytes)
      0x14: CRC2 (4 bytes)
      0x18: Reserved (8 bytes)
      0x20: Title (20 bytes ASCII)
      0x34: Reserved (7 bytes)
      0x3B: Game code (4 bytes ASCII)
      0x3F: Mask ROM version (1 byte)
    """
    if len(data) < 64:
        raise ValueError(f"ROM too short: {len(data)} bytes (need 64)")

    pi0, pi1, pi2, pi3 = data[0], data[1], data[2], data[3]
    clock_rate,     = struct.unpack(">I", data[0x04:0x08])
    boot_address,   = struct.unpack(">I", data[0x08:0x0C])
    libultra,       = struct.unpack(">I", data[0x0C:0x10])
    crc1,           = struct.unpack(">I", data[0x10:0x14])
    crc2,           = struct.unpack(">I", data[0x14:0x18])
    check_code      = (crc1 << 32) | crc2

    title = data[0x20:0x34].decode("ascii", errors="replace").rstrip("\x00").strip()

    # Game code: 4 bytes at 0x3B
    raw_code = data[0x3B:0x3F]
    game_code = raw_code.decode("ascii", errors="replace").strip("\x00").strip()

    mask_rom_version = data[0x3F]

    # Country/region code is the 3rd byte of the game code (index 2 = 0x3D)
    country_code = data[0x3D] if len(data) > 0x3D else 0x00

    logger.debug(
        f"Header parsed: title={title!r} code={game_code!r} "
        f"crc1=0x{crc1:08X} country=0x{country_code:02X}"
    )

    return ROMHeader(
        pi_bsd_dom1_lat_reg=pi0,
        pi_bsd_dom1_pwd_reg=pi1,
        pi_bsd_dom1_pgs_reg=pi2,
        pi_bsd_dom1_rls_reg=pi3,
        clock_rate=clock_rate,
        boot_address=boot_address,
        libultra_version=libultra,
        check_code=check_code,
        title=title,
        game_code=game_code,
        mask_rom_version=mask_rom_version,
        country_code=country_code,
    )


def load_rom_from_bytes(data: bytes, path: Optional[Path] = None) -> ROMInfo:
    fmt = detect_format(data)
    if fmt == ROMFormat.UNKNOWN:
        raise ValueError(
            f"Unrecognised ROM format.\n"
            f"First bytes: {data[:8].hex() if len(data) >= 8 else data.hex()}\n"
            f"Expected 0x80 (Z64), 0x37 (V64) or 0x40 (N64) as first byte."
        )
    z64 = normalize_to_z64(data, fmt)
    header = parse_header(z64)
    return ROMInfo(path=path, format=fmt, size_bytes=len(z64), header=header, data=z64)


def load_rom_from_file(path: Path) -> ROMInfo:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"ROM file not found: {path}")
    return load_rom_from_bytes(path.read_bytes(), path=path)


def save_rom_to_file(rom: ROMInfo, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rom.data)
