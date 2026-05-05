"""
GameShark Code Manager for N64 Operator

GameShark codes for N64 work by patching RAM at specific addresses every frame.
Mupen64Plus supports this natively via its cheat system.

Code format:
  XXXXXXXX YYYY
  Where XXXXXXXX is the address (with type encoded in first byte)
  And YYYY is the value to write

First byte of address encodes the write type:
  80 = write 1 byte (8-bit)
  81 = write 2 bytes (16-bit)
  D0 = conditional: next line runs if 1-byte address != value
  D1 = conditional: next line runs if 2-byte address != value

Mupen64Plus .cht format:
  cn GameName
  cd XXXXXXXX YYYY
  cn SomeOtherGame
  ...

We generate this format from our stored codes and pass it to Mupen64Plus.
"""

import json
import logging
import os
import platform
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


def _get_app_data_dir() -> Path:
    """Return the platform-appropriate app data directory."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "N64Operator"


# User's custom cheat file location
_USER_CHEATS_DIR = _get_app_data_dir() / "cheats"


@dataclass
class CheatCode:
    """A single GameShark/cheat code entry."""
    name: str
    code: str           # Raw code string, may be multi-line (multiple patches)
    enabled: bool = False
    description: str = ""

    def lines(self) -> List[str]:
        """Return individual code lines (some cheats have multiple patches)."""
        return [l.strip() for l in self.code.strip().splitlines() if l.strip()]

    def is_valid(self) -> bool:
        """Validate GameShark code format."""
        for line in self.lines():
            # Should match XXXXXXXX YYYY pattern
            if not re.match(r'^[0-9A-Fa-f]{8}\s+[0-9A-Fa-f]{4}$', line.strip()):
                return False
        return len(self.lines()) > 0


@dataclass
class GameCheats:
    """All cheat codes for a specific game."""
    game_code: str
    game_title: str
    codes: List[CheatCode] = field(default_factory=list)

    @property
    def enabled_codes(self) -> List[CheatCode]:
        return [c for c in self.codes if c.enabled]

    def add_code(self, name: str, code: str, enabled: bool = False) -> CheatCode:
        cheat = CheatCode(name=name, code=code, enabled=enabled)
        self.codes.append(cheat)
        return cheat

    def to_mupen_cht(self) -> str:
        """Generate Mupen64Plus .cht format for enabled cheats."""
        lines = [f"cn {self.game_title}"]
        for cheat in self.enabled_codes:
            for line in cheat.lines():
                lines.append(f"cd {line}")
        return "\n".join(lines) + "\n"


class CheatManager:
    """
    Manages GameShark codes across all games.

    Features:
    - Load bundled codes from game database
    - User can add custom codes
    - Enable/disable individual codes
    - Generate Mupen64Plus cheat file for active game
    - Persist user changes to disk
    """

    def __init__(self):
        self._user_codes: Dict[str, List[dict]] = {}  # game_code -> [{name,code,enabled}]
        self._loaded = False
        _USER_CHEATS_DIR.mkdir(parents=True, exist_ok=True)

    def load_user_codes(self) -> None:
        """Load user's custom/modified cheat codes from disk."""
        user_file = _USER_CHEATS_DIR / "user_codes.json"
        if user_file.exists():
            try:
                data = json.loads(user_file.read_text())
                self._user_codes = data
                logger.info(f"Loaded user cheat codes for {len(data)} games")
            except Exception as e:
                logger.warning(f"Failed to load user cheats: {e}")
        self._loaded = True

    def save_user_codes(self) -> None:
        """Persist user code modifications to disk."""
        try:
            user_file = _USER_CHEATS_DIR / "user_codes.json"
            user_file.write_text(json.dumps(self._user_codes, indent=2))
        except Exception as e:
            logger.error(f"Failed to save user cheats: {e}")

    def get_cheats_for_game(self, game_code: str, bundled_codes: List[dict]) -> GameCheats:
        """
        Get all cheats for a game — merging bundled database codes with
        user customisations (enable/disable state + custom codes).
        """
        if not self._loaded:
            self.load_user_codes()

        user_overrides = {c["name"]: c for c in self._user_codes.get(game_code, [])}

        codes = []
        # Start with bundled codes
        for entry in bundled_codes:
            name = entry.get("name", "")
            override = user_overrides.get(name)
            codes.append(CheatCode(
                name=name,
                code=entry.get("code", ""),
                enabled=override.get("enabled", entry.get("enabled", False)) if override else entry.get("enabled", False),
                description=entry.get("description", ""),
            ))

        # Add user's custom codes not in the bundled set
        bundled_names = {e.get("name") for e in bundled_codes}
        for user_code in self._user_codes.get(game_code, []):
            if user_code.get("name") not in bundled_names:
                codes.append(CheatCode(
                    name=user_code.get("name", "Custom Code"),
                    code=user_code.get("code", ""),
                    enabled=user_code.get("enabled", False),
                ))

        from src.database.game_db import get_game_database
        db = get_game_database()
        gi = db.lookup_by_game_code(game_code)
        title = gi.title if gi else game_code

        return GameCheats(game_code=game_code, game_title=title, codes=codes)

    def set_code_enabled(self, game_code: str, code_name: str, enabled: bool) -> None:
        """Toggle a specific cheat code on/off."""
        if game_code not in self._user_codes:
            self._user_codes[game_code] = []

        existing = next((c for c in self._user_codes[game_code] if c["name"] == code_name), None)
        if existing:
            existing["enabled"] = enabled
        else:
            self._user_codes[game_code].append({"name": code_name, "enabled": enabled})

        self.save_user_codes()

    def add_custom_code(self, game_code: str, name: str, code: str) -> Optional[CheatCode]:
        """Add a new user-supplied cheat code."""
        cheat = CheatCode(name=name, code=code, enabled=False)
        if not cheat.is_valid():
            logger.warning(f"Invalid cheat code format: {code}")
            return None

        if game_code not in self._user_codes:
            self._user_codes[game_code] = []

        self._user_codes[game_code].append({"name": name, "code": code, "enabled": False})
        self.save_user_codes()
        return cheat

    def write_mupen_cheat_file(self, game_cheats: GameCheats) -> Optional[Path]:
        """
        Write a Mupen64Plus-compatible cheat file for the active game.
        Returns the path to the written file.
        """
        if not game_cheats.enabled_codes:
            return None

        cheat_path = _USER_CHEATS_DIR / f"{game_cheats.game_code}.cht"
        try:
            cheat_path.write_text(game_cheats.to_mupen_cht())
            logger.info(f"Wrote cheat file: {cheat_path}")
            return cheat_path
        except Exception as e:
            logger.error(f"Failed to write cheat file: {e}")
            return None


# Singleton
_cheat_manager: Optional[CheatManager] = None

def get_cheat_manager() -> CheatManager:
    global _cheat_manager
    if _cheat_manager is None:
        _cheat_manager = CheatManager()
    return _cheat_manager
