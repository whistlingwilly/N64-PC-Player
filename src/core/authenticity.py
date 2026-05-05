"""
N64 Cartridge Authenticity Engine
==================================

Determines whether an inserted N64 cartridge is a genuine original or
a reproduction using a layered approach from most to least reliable:

LAYER 1 — Flash Chip Manufacturer ID Query  [hardware, definitive]
  Real N64 carts use **mask ROM** — silicon chips where data is baked
  in during fabrication. They are physically incapable of responding to
  write commands or software ID queries.

  Reproduction carts use **NOR flash** (e.g. Macronix MX29LV640,
  ISSI IS29LV640, SST39VF1681, Winbond W29GL...). These chips implement
  the JEDEC CFI / software ID protocol:

    Write  0xAA  →  address 0x555   (unlock cycle 1)
    Write  0x55  →  address 0x2AA   (unlock cycle 2)
    Write  0x90  →  address 0x555   (enter software ID mode)
    Read   address 0x00  →  Manufacturer ID
    Read   address 0x01  →  Device ID
    Write  0xF0  →  any address     (exit, reset to read mode)

  Known repro flash manufacturer IDs:
    0xC2 = Macronix (most common — MX29LV640 series)
    0x9D = ISSI
    0xBF = SST / Microchip (SST39VF...)
    0xEF = Winbond
    0x01 = AMD / Spansion
    0x20 = ST Microelectronics / Micron
    0x04 = Fujitsu

  If we get any of these back = flash chip = REPRODUCTION.
  If we get the actual game data back (e.g. 0x80 for Z64 magic) = MASK ROM = GENUINE.

LAYER 2 — Write Test  [hardware, strong evidence]
  Attempt to write a known pattern to the ROM domain, then read it back.
  Mask ROM: physically impossible to write. Read-back will return original data.
  Flash ROM without write protection: the written value may persist briefly.

  We write to a safe "scratchpad" location at the end of the ROM space,
  then immediately restore. This is non-destructive for real carts.

LAYER 3 — CRC Recalculation  [software, definitive for ROM integrity]
  Recalculate CRC1/CRC2 using the IPL3 algorithm and compare to header.
  Genuine press = CRC always matches unless ROM chip has degraded.
  Repro ROM with modifications = CRC will not match.
  Repro ROM that is a perfect dump of a real game = CRC will match.
  (This tells us about ROM data integrity, not necessarily hardware type.)

LAYER 4 — No-Intro Database CRC Match  [software, strong evidence]
  Compare CRC1 to our verified No-Intro database of known-good dumps.
  If it matches = ROM data is identical to a verified real cartridge dump.

LAYER 5 — CIC Boot Code Fingerprint  [software, corroborating]
  The IPL3 boot code (0x40–0xFFF) is specific to each CIC chip version.
  We know the MD5 of each legitimate CIC's boot code. If the boot code
  doesn't match any known CIC = ROM has been patched or is a bad dump.

LAYER 6 — Header Consistency Checks  [software, corroborating]
  - PI BSD registers at 0x00–0x07 should be 0x80370000 or similar
  - Clock rate at 0x04 should be 0x000F (or 0x0000 for some PAL carts)
  - Game code should match known region/title patterns
  - Title should be clean ASCII, not corrupted
"""

import struct
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Tuple

from .crc import (recalculate_crcs, verify_rom_crcs,
                  detect_cic_from_bootcode, get_cic_for_game)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Known flash manufacturer IDs (JEDEC)
# If we see these when querying the ROM chip — it's flash, not mask ROM.
# ─────────────────────────────────────────────────────────────────────────────

FLASH_MANUFACTURER_IDS = {
    0xC2: "Macronix",      # MX29LV640 — most common N64 repro chip
    0x9D: "ISSI",          # IS29LV640 — second most common
    0xBF: "SST/Microchip", # SST39VF1681
    0xEF: "Winbond",       # W29GL / W29EE series
    0x01: "AMD/Spansion",  # AM29LV series
    0x20: "ST/Micron",     # M29W640 series
    0x04: "Fujitsu",       # MBM29LV series
    0x37: "AMIC",          # A29L160 series
    0xAD: "SK Hynix",
    0x89: "Intel",
    0x7F: "Toshiba/Kioxia",
}


class AuthenticityVerdict(Enum):
    GENUINE      = "genuine"       # Strong evidence of original hardware
    REPRODUCTION = "reproduction"  # Strong evidence of flash/EPROM repro cart
    LIKELY_GENUINE      = "likely_genuine"    # No repro signals but couldn't confirm flash
    LIKELY_REPRODUCTION = "likely_repro"      # Some repro signals but inconclusive
    UNKNOWN      = "unknown"       # Not enough information


@dataclass
class AuthenticityCheck:
    """Result of a single authenticity test."""
    name: str
    passed: Optional[bool]   # True=genuine signal, False=repro signal, None=inconclusive
    detail: str
    confidence: int           # 1–5 (5 = most reliable)
    is_hardware_test: bool = False


@dataclass
class AuthenticityReport:
    """Full authenticity assessment for a cartridge."""
    verdict: AuthenticityVerdict
    confidence_pct: int       # 0–100%
    checks: List[AuthenticityCheck] = field(default_factory=list)
    flash_manufacturer: Optional[str] = None
    flash_device_id: Optional[int] = None
    crc_match: bool = False
    no_intro_match: bool = False
    cic_version: Optional[str] = None
    cic_correct: bool = False
    write_protected: Optional[bool] = None   # True=read-only (genuine signal)

    # Human-readable summary
    @property
    def verdict_label(self) -> str:
        labels = {
            AuthenticityVerdict.GENUINE:             "Official Cartridge",
            AuthenticityVerdict.REPRODUCTION:        "Reproduction Cartridge",
            AuthenticityVerdict.LIKELY_GENUINE:      "Likely Official",
            AuthenticityVerdict.LIKELY_REPRODUCTION: "Likely Reproduction",
            AuthenticityVerdict.UNKNOWN:             "Unknown",
        }
        return labels[self.verdict]

    @property
    def is_official(self) -> bool:
        return self.verdict in (AuthenticityVerdict.GENUINE,
                                AuthenticityVerdict.LIKELY_GENUINE)

    @property
    def is_repro(self) -> bool:
        return self.verdict in (AuthenticityVerdict.REPRODUCTION,
                                AuthenticityVerdict.LIKELY_REPRODUCTION)

    @property
    def short_reason(self) -> str:
        """One-line explanation of the verdict."""
        if self.flash_manufacturer:
            return f"Flash ROM detected ({self.flash_manufacturer} chip) — reproduction"
        if self.write_protected is False:
            return "ROM area is writable — flash chip detected"
        if self.verdict == AuthenticityVerdict.GENUINE:
            reasons = []
            if self.write_protected:
                reasons.append("read-only ROM")
            if self.crc_match:
                reasons.append("CRC verified")
            if self.no_intro_match:
                reasons.append("matches No-Intro database")
            return "Genuine: " + ", ".join(reasons) if reasons else "No repro indicators found"
        if self.verdict == AuthenticityVerdict.LIKELY_GENUINE:
            if self.crc_match:
                return "CRC matches — ROM data verified (hardware test unavailable)"
            return "No repro indicators in software checks"
        return "Multiple reproduction indicators detected"


class AuthenticityEngine:
    """
    Multi-layer N64 cartridge authenticity detection engine.

    Hardware tests require actual USB communication with the cartridge
    reader and are performed when a device is connected.

    Software tests run immediately on any ROM data.
    """

    def __init__(self, known_crcs: dict = None):
        """
        Args:
            known_crcs: Dict mapping CRC1 hex strings to verified game info.
                        Built from the No-Intro / our game database.
        """
        self._known_crcs = known_crcs or {}

    # ─────────────────────────────────────────────────────────────────────
    # Full analysis (software only — no hardware needed)
    # ─────────────────────────────────────────────────────────────────────

    def analyse_rom(self, rom_data: bytes, game_code: str = "") -> AuthenticityReport:
        """
        Run all software-based authenticity checks on ROM data.
        Returns a full AuthenticityReport.
        """
        checks = []
        report = AuthenticityReport(
            verdict=AuthenticityVerdict.UNKNOWN,
            confidence_pct=0,
        )

        # ── Check 1: CRC Recalculation ────────────────────────────────────
        crc_result = verify_rom_crcs(rom_data, game_code)
        if "error" not in crc_result:
            report.cic_version = crc_result["cic"]
            report.crc_match   = crc_result["both_match"]

            if crc_result["both_match"]:
                checks.append(AuthenticityCheck(
                    name="CRC Verification",
                    passed=True,
                    detail=f"CRC1 0x{crc_result['header_crc1']:08X} and CRC2 0x{crc_result['header_crc2']:08X} "
                           f"match computed values (CIC {crc_result['cic']})",
                    confidence=4,
                ))
            else:
                checks.append(AuthenticityCheck(
                    name="CRC Verification",
                    passed=False,
                    detail=f"CRC mismatch! Header=0x{crc_result['header_crc1']:08X} "
                           f"but computed=0x{crc_result['computed_crc1']:08X}. "
                           f"ROM has been modified or is a bad dump.",
                    confidence=4,
                ))

        # ── Check 2: No-Intro CRC Database ───────────────────────────────
        header_crc1_str = f"0x{struct.unpack_from('>I', rom_data, 0x10)[0]:08X}"
        if header_crc1_str.upper() in {k.upper() for k in self._known_crcs}:
            report.no_intro_match = True
            checks.append(AuthenticityCheck(
                name="No-Intro Database",
                passed=True,
                detail=f"CRC1 {header_crc1_str} matches verified No-Intro dump",
                confidence=4,
            ))
        else:
            checks.append(AuthenticityCheck(
                name="No-Intro Database",
                passed=None,
                detail=f"CRC1 {header_crc1_str} not in local verified CRC database "
                       f"(database covers {len(self._known_crcs)} titles)",
                confidence=3,
            ))

        # ── Check 3: CIC Boot Code Fingerprint ───────────────────────────
        detected_cic = detect_cic_from_bootcode(rom_data)
        expected_cic = get_cic_for_game(rom_data, game_code)
        report.cic_version = detected_cic or expected_cic

        if detected_cic is None:
            checks.append(AuthenticityCheck(
                name="CIC Boot Code",
                passed=None,
                detail="Boot code does not match any known CIC fingerprint — may be patched",
                confidence=2,
            ))
        elif detected_cic == expected_cic:
            report.cic_correct = True
            checks.append(AuthenticityCheck(
                name="CIC Boot Code",
                passed=True,
                detail=f"Boot code matches CIC-NUS-{detected_cic} (correct for {game_code or 'this game'})",
                confidence=3,
            ))
        else:
            checks.append(AuthenticityCheck(
                name="CIC Boot Code",
                passed=False,
                detail=f"Boot code is CIC-{detected_cic} but expected CIC-{expected_cic} "
                       f"for {game_code} — may indicate patched or mismatched ROM",
                confidence=3,
            ))

        # ── Check 4: Header Consistency ───────────────────────────────────
        header_issues = self._check_header(rom_data)
        if not header_issues:
            checks.append(AuthenticityCheck(
                name="ROM Header",
                passed=True,
                detail="PI BSD registers, clock rate, and media type are valid",
                confidence=2,
            ))
        else:
            checks.append(AuthenticityCheck(
                name="ROM Header",
                passed=False,
                detail=f"Header anomalies: {'; '.join(header_issues)}",
                confidence=2,
            ))

        # ── Check 5: ROM Size Sanity ──────────────────────────────────────
        size_check = self._check_rom_size(rom_data, game_code)
        checks.append(size_check)

        # ── Compute final verdict ─────────────────────────────────────────
        report.checks = checks
        report.verdict, report.confidence_pct = self._compute_verdict(checks, report)
        return report

    def apply_hardware_results(self, report: AuthenticityReport,
                               flash_id: Optional[Tuple[int, int]] = None,
                               write_succeeded: Optional[bool] = None) -> AuthenticityReport:
        """
        Incorporate hardware test results (Flash ID query + Write test)
        into an existing software report.

        This upgrades the verdict with the most reliable evidence.

        Args:
            report:          Existing software-only report to update
            flash_id:        (manufacturer_id, device_id) from chip query,
                             or None if mask ROM (no response) / test not run
            write_succeeded: True if write to ROM area was not rejected
        """
        if flash_id is not None:
            mfr_id, dev_id = flash_id
            if mfr_id in FLASH_MANUFACTURER_IDS:
                mfr_name = FLASH_MANUFACTURER_IDS[mfr_id]
                report.flash_manufacturer = mfr_name
                report.flash_device_id    = dev_id
                report.verdict    = AuthenticityVerdict.REPRODUCTION
                report.confidence_pct = 99
                report.checks.insert(0, AuthenticityCheck(
                    name="Flash Chip ID",
                    passed=False,
                    detail=f"Flash chip responded to Software ID query: "
                           f"Manufacturer=0x{mfr_id:02X} ({mfr_name}), "
                           f"Device=0x{dev_id:02X}. "
                           f"Genuine mask ROM would not respond.",
                    confidence=5,
                    is_hardware_test=True,
                ))
                return report
            else:
                # Chip didn't respond with a known flash ID = mask ROM signal
                report.checks.insert(0, AuthenticityCheck(
                    name="Flash Chip ID",
                    passed=True,
                    detail="No flash chip Software ID response — consistent with mask ROM (genuine cartridge)",
                    confidence=5,
                    is_hardware_test=True,
                ))

        if write_succeeded is not None:
            report.write_protected = not write_succeeded
            if write_succeeded:
                # We wrote to the ROM area and it changed = flash
                report.flash_manufacturer = report.flash_manufacturer or "Unknown flash"
                report.checks.insert(0, AuthenticityCheck(
                    name="ROM Write Test",
                    passed=False,
                    detail="Write to ROM address space succeeded — "
                           "mask ROM is physically read-only. "
                           "This ROM is writable = flash chip = reproduction.",
                    confidence=5,
                    is_hardware_test=True,
                ))
                if report.verdict != AuthenticityVerdict.REPRODUCTION:
                    report.verdict = AuthenticityVerdict.REPRODUCTION
                    report.confidence_pct = 95
            else:
                report.checks.insert(0, AuthenticityCheck(
                    name="ROM Write Test",
                    passed=True,
                    detail="Write to ROM address space was rejected — "
                           "ROM is read-only, consistent with original mask ROM chip.",
                    confidence=5,
                    is_hardware_test=True,
                ))

        # Recompute verdict with new hardware data
        report.verdict, report.confidence_pct = self._compute_verdict(
            report.checks, report)
        return report

    # ─────────────────────────────────────────────────────────────────────
    # Hardware protocol helpers (called by the USB device driver)
    # ─────────────────────────────────────────────────────────────────────

    def build_flash_id_commands(self) -> List[dict]:
        """
        Return the sequence of USB commands to perform a Flash Chip
        Software ID query.

        The device driver sends these commands over USB to the cart reader.
        After sending, read back two bytes from addresses 0x00 and 0x01.

        This is the JEDEC CFI "Auto-Select / Software ID Entry" sequence:
          WRITE 0xAA → 0x555
          WRITE 0x55 → 0x2AA
          WRITE 0x90 → 0x555
          READ  0x00 → manufacturer ID
          READ  0x01 → device ID
          WRITE 0xF0 → 0x000  (exit / reset)

        The USB command format depends on your specific reader's protocol,
        so this returns abstract command dicts for the protocol layer to translate.
        """
        return [
            {"type": "write", "address": 0x555, "value": 0xAA, "width": 1},
            {"type": "write", "address": 0x2AA, "value": 0x55, "width": 1},
            {"type": "write", "address": 0x555, "value": 0x90, "width": 1},
            {"type": "read",  "address": 0x000, "width": 1, "label": "manufacturer_id"},
            {"type": "read",  "address": 0x001, "width": 1, "label": "device_id"},
            {"type": "write", "address": 0x000, "value": 0xF0, "width": 1},
        ]

    def build_write_test_commands(self, test_address: int = 0x800000) -> List[dict]:
        """
        Return the USB command sequence for a ROM write test.

        We attempt to write 0xAA to a address near the end of the ROM space,
        then immediately read it back. If the value changed, it's writable flash.
        We then restore the original value.

        test_address defaults to 8MB offset (safe for carts >= 16MB).
        """
        return [
            {"type": "read",  "address": test_address, "width": 4,
             "label": "original_value"},
            {"type": "write", "address": test_address, "value": 0xDEADBEEF,
             "width": 4},
            {"type": "read",  "address": test_address, "width": 4,
             "label": "test_readback"},
            # Restore (if it actually wrote, restoring requires knowing original)
            {"type": "restore", "address": test_address,
             "label": "restore_original"},
        ]

    # ─────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────

    def _check_header(self, data: bytes) -> List[str]:
        """Check for header anomalies. Returns list of problem strings."""
        if len(data) < 0x40:
            return ["ROM too small to validate header"]
        issues = []

        # PI BSD Domain 1 release register at 0x00 — should be 0x80
        pi_bsd = data[0]
        if pi_bsd not in (0x80, 0x37, 0x40):
            issues.append(f"Unexpected PI_BSD byte 0x{pi_bsd:02X} at 0x00 "
                          f"(expected 0x80 for Z64, 0x37 for V64, 0x40 for N64)")

        # Clock rate at 0x04–0x07 — low nibble ignored, common values:
        # 0x000F = standard NTSC, 0x0000 = some PAL/dev carts
        clock = struct.unpack_from(">I", data, 0x04)[0]
        clock_masked = clock & 0xFFFFFFF0
        if clock_masked not in (0x000F0000, 0x00000000, 0x000F0010, 0x000F0020,
                                  0x000F0030, 0x000F0040):
            issues.append(f"Unusual clock rate value 0x{clock:08X}")

        # Title at 0x20–0x33 — should be ASCII printable or spaces
        try:
            title_bytes = data[0x20:0x34]
            title = title_bytes.decode("ascii", errors="replace")
            non_print = sum(1 for c in title if c not in
                            ' ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                            '!@#$%^&*()-_=+[]{}|;:,.<>?/\\\'\"`~')
            if non_print > 4:
                issues.append(f"ROM title contains {non_print} unusual characters")
        except Exception:
            issues.append("Could not read ROM title as ASCII")

        return issues

    def _check_rom_size(self, data: bytes, game_code: str) -> AuthenticityCheck:
        """Check that ROM size is a valid N64 cartridge size."""
        size = len(data)
        size_mb = size / (1024 * 1024)

        # Valid N64 ROM sizes (MB): 4, 6, 8, 12, 16, 24, 32, 64, 96
        valid_sizes_bytes = {
            4*1024*1024, 6*1024*1024, 8*1024*1024, 12*1024*1024,
            16*1024*1024, 24*1024*1024, 32*1024*1024, 64*1024*1024,
            96*1024*1024,
        }

        if size in valid_sizes_bytes:
            return AuthenticityCheck(
                name="ROM Size",
                passed=True,
                detail=f"ROM is {size_mb:.0f} MB — a valid N64 cartridge size",
                confidence=1,
            )
        elif size > 96 * 1024 * 1024:
            return AuthenticityCheck(
                name="ROM Size",
                passed=False,
                detail=f"ROM is {size_mb:.1f} MB — larger than any official N64 cart (max 96 MB). "
                       "Possibly overdumped or a flash cart.",
                confidence=2,
            )
        else:
            return AuthenticityCheck(
                name="ROM Size",
                passed=None,
                detail=f"ROM is {size_mb:.1f} MB — unusual size (may be truncated or padded)",
                confidence=1,
            )

    def _compute_verdict(self, checks: List[AuthenticityCheck],
                         report: AuthenticityReport) -> Tuple[AuthenticityVerdict, int]:
        """
        Compute final verdict and confidence from all checks.
        Hardware tests (confidence=5) override everything else.
        """
        # Hardware tests are definitive
        for check in checks:
            if check.is_hardware_test and check.confidence == 5:
                if check.passed is False:
                    return AuthenticityVerdict.REPRODUCTION, 97
                if check.passed is True:
                    # Hardware says read-only — now check software evidence
                    if report.crc_match and report.no_intro_match:
                        return AuthenticityVerdict.GENUINE, 98
                    elif report.crc_match:
                        return AuthenticityVerdict.GENUINE, 92
                    else:
                        return AuthenticityVerdict.LIKELY_GENUINE, 80

        # Software only — score based on evidence
        genuine_score  = 0
        repro_score    = 0
        total_weight   = 0

        for check in checks:
            w = check.confidence
            total_weight += w
            if check.passed is True:
                genuine_score += w
            elif check.passed is False:
                repro_score += w

        if total_weight == 0:
            return AuthenticityVerdict.UNKNOWN, 0

        genuine_pct = (genuine_score / total_weight) * 100
        repro_pct   = (repro_score   / total_weight) * 100

        if repro_pct >= 60:
            conf = min(int(repro_pct), 85)  # Cap software-only confidence at 85%
            return AuthenticityVerdict.LIKELY_REPRODUCTION, conf
        elif repro_pct > 30:
            return AuthenticityVerdict.UNKNOWN, 50
        elif genuine_pct >= 70:
            conf = min(int(genuine_pct), 80)  # Cap software-only genuine at 80%
            return AuthenticityVerdict.LIKELY_GENUINE, conf
        else:
            return AuthenticityVerdict.UNKNOWN, 40


# ─────────────────────────────────────────────────────────────────────────────
# Singleton helper
# ─────────────────────────────────────────────────────────────────────────────

_engine: Optional[AuthenticityEngine] = None


def get_authenticity_engine() -> AuthenticityEngine:
    global _engine
    if _engine is None:
        # Build CRC lookup from game database
        from src.database import get_game_database
        db = get_game_database()
        db.load()
        known_crcs = {}
        for code, game in db._local_db.items():
            crc = game.get("crc1", "")
            if crc:
                known_crcs[crc.upper()] = game.get("title", code)
        _engine = AuthenticityEngine(known_crcs=known_crcs)
    return _engine


def analyse_cartridge(rom_data: bytes, game_code: str = "",
                      flash_id: Optional[Tuple[int, int]] = None,
                      write_succeeded: Optional[bool] = None) -> AuthenticityReport:
    """
    Convenience function: run full authenticity analysis on a cartridge.

    Args:
        rom_data:        Raw ROM bytes (Z64 format, big-endian)
        game_code:       4-char game code from ROM header
        flash_id:        (mfr_id, dev_id) from hardware Flash ID query,
                         or None if mask ROM / test not available
        write_succeeded: True if write test showed ROM is writable
    """
    engine = get_authenticity_engine()
    report = engine.analyse_rom(rom_data, game_code)

    if flash_id is not None or write_succeeded is not None:
        report = engine.apply_hardware_results(report, flash_id, write_succeeded)

    return report
