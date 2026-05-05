"""
N64 ROM CRC Recalculation

Implements the CRC1/CRC2 algorithm used by the N64's IPL3 (boot code).
The checksum is computed over 1MB of ROM data (bytes 0x1000–0x101000).
The exact computation depends on which CIC security chip the game uses —
different CIC versions use different seed values.

Reference: https://github.com/Dragorn421/n64checksum
Reference: http://n64dev.org/n64crc.html (original implementation)

CIC versions and their seed bytes:
  6101 / 7101  →  seed = 0x3F (games: Starfox 64 early builds)
  6102 / 7101  →  seed = 0x3F (standard — Mario 64, most games)
  6103 / 7103  →  seed = 0x78 (Banjo-Kazooie, Paper Mario, DK64...)
  6105 / 7105  →  seed = 0x91 (Zelda OoT, Zelda MM, Jet Force Gemini...)
  6106 / 7106  →  seed = 0x85 (Yoshi's Story, F-Zero X, Cruisin' USA...)
"""

import struct
from typing import Tuple, Optional

# CIC seed values — used to initialise the checksum algorithm
CIC_SEEDS = {
    "6101": 0x3F,
    "6102": 0x3F,
    "6103": 0x78,
    "6105": 0x91,
    "6106": 0x85,
    "7101": 0x3F,
    "7102": 0x3F,
    "7103": 0x78,
    "7105": 0x91,
    "7106": 0x85,
}

# Known IPL3 (boot code) MD5 fingerprints → CIC version
# Boot code lives at bytes 0x40–0xFFF in the ROM (4032 bytes)
BOOT_CODE_MD5 = {
    "900b4a5b68edb71f4c7ed52acd814fc5": "6101",
    "e24dd796b2fa16511521139d28c8356b": "6102",
    "319038097346e12c26c3c21b56f86f23": "6103",
    "ff22a296e55d34ab0a077dc2ba5f5796": "6105",
    "6460387749ac0bd925aa5430bc7864fe": "6106",
    "955894c2e40a698bf98a67b78a4e28fa": "7102",
}

# Known CIC for specific game codes (overrides boot-code detection if needed)
GAME_CODE_CIC = {
    # 6102 (standard) — most games
    "NSME": "6102", "NT2E": "6102", "NKJE": "6102", "NMFE": "6102",
    "NBLE": "6102", "NSFE": "6102", "NCGE": "6102", "NTHE": "6102",
    "NE4E": "6102", "NPKE": "6102", "NTTE": "6102", "NWRE": "6102",
    # 6103 — Rare games, Paper Mario
    "NBKE": "6103", "NAHE": "6103", "NDOE": "6103", "NMQE": "6103",
    "NM2E": "6103", "NM3E": "6103",
    # 6105 — Zelda games, Jet Force Gemini
    "NZSE": "6105", "NZLE": "6105", "NPFE": "6105", "NJFE": "6105",
    # 6106 — F-Zero X, Yoshi's Story, Cruis'n
    "NFZE": "6106", "NYSE": "6106", "NCUE": "6106", "NCWE": "6106",
    "NCXE": "6106",
}

ROL32 = lambda v, n: ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def _compute_crc(data: bytes, cic_seed: int) -> Tuple[int, int]:
    """
    Compute CRC1 and CRC2 over 1MB of ROM data starting at offset 0x1000.

    This implements the algorithm from IPL3 that the N64 uses to verify
    the cartridge at boot time.
    """
    MAGIC = 0x6C078965

    def ROT(v, n): return ROL32(v, n)

    seed = cic_seed
    t1 = t2 = t3 = t4 = t5 = t6 = (seed * MAGIC + 1) & 0xFFFFFFFF

    # Process 1MB of ROM starting at 0x1000
    start = 0x1000
    end   = min(0x101000, len(data))
    chunk = data[start:end]

    # Pad to 1MB if needed
    if len(chunk) < 0x100000:
        chunk = chunk + b'\x00' * (0x100000 - len(chunk))

    for i in range(0, 0x100000, 4):
        d = struct.unpack_from(">I", chunk, i)[0]

        old_t6 = t6
        t6 = (t6 + d) & 0xFFFFFFFF
        if t6 < d:
            t4 = (t4 + 1) & 0xFFFFFFFF
        t3 ^= d
        r  = ROT(d, d & 0x1F)
        t5 = (t5 + r) & 0xFFFFFFFF
        if t2 > d:
            t2 ^= r
        else:
            t2 ^= (t6 ^ d) & 0xFFFFFFFF
        t1 = (t1 + (t5 ^ d)) & 0xFFFFFFFF

    crc1 = (t6 ^ t4 ^ t3) & 0xFFFFFFFF
    crc2 = (t5 ^ t2 ^ t1) & 0xFFFFFFFF
    return crc1, crc2


def detect_cic_from_bootcode(data: bytes) -> Optional[str]:
    """
    Fingerprint the boot code (IPL3) at bytes 0x40–0xFFF to determine
    which CIC security chip was used.
    Returns the CIC version string ("6102", "6103", etc.) or None.
    """
    import hashlib
    if len(data) < 0x1000:
        return None
    boot_code = data[0x40:0x1000]
    md5 = hashlib.md5(boot_code).hexdigest()
    return BOOT_CODE_MD5.get(md5)


def get_cic_for_game(data: bytes, game_code: str) -> str:
    """
    Determine the CIC version for a given game.
    Priority: game code lookup → boot code fingerprint → default 6102
    """
    code = game_code.strip().upper()
    if code in GAME_CODE_CIC:
        return GAME_CODE_CIC[code]
    detected = detect_cic_from_bootcode(data)
    if detected:
        return detected
    return "6102"  # Most common default


def recalculate_crcs(data: bytes, game_code: str = "") -> Tuple[int, int]:
    """
    Recalculate the CRC1 and CRC2 checksums from ROM data.

    Args:
        data:      Raw ROM bytes (must be normalised to big-endian Z64 format)
        game_code: 4-char game code (used to select correct CIC seed)

    Returns:
        (crc1, crc2) as 32-bit unsigned integers
    """
    cic = get_cic_for_game(data, game_code)
    seed = CIC_SEEDS.get(cic, CIC_SEEDS["6102"])
    return _compute_crc(data, seed)


def verify_rom_crcs(data: bytes, game_code: str = "") -> dict:
    """
    Full CRC verification report.

    Returns:
        {
          "header_crc1": int,     # CRC1 stored in ROM header
          "header_crc2": int,     # CRC2 stored in ROM header
          "computed_crc1": int,   # CRC1 we calculated from data
          "computed_crc2": int,   # CRC2 we calculated from data
          "crc1_match": bool,
          "crc2_match": bool,
          "both_match": bool,
          "cic": str,             # Detected CIC version
        }
    """
    if len(data) < 0x20:
        return {"error": "ROM too small to contain header"}

    # Read CRC values from header (bytes 0x10–0x17, big-endian)
    header_crc1, header_crc2 = struct.unpack_from(">II", data, 0x10)

    cic = get_cic_for_game(data, game_code)
    seed = CIC_SEEDS.get(cic, CIC_SEEDS["6102"])
    computed_crc1, computed_crc2 = _compute_crc(data, seed)

    match1 = header_crc1 == computed_crc1
    match2 = header_crc2 == computed_crc2

    return {
        "header_crc1":   header_crc1,
        "header_crc2":   header_crc2,
        "computed_crc1": computed_crc1,
        "computed_crc2": computed_crc2,
        "crc1_match":    match1,
        "crc2_match":    match2,
        "both_match":    match1 and match2,
        "cic":           cic,
    }
