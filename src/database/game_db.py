"""
N64 Game Database
==================
Loads from bundled JSON, identifies ROMs by CRC1 then game code,
fetches cover art from libretro thumbnails (free, no API key).
"""

import json
import logging
import sqlite3
import threading
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

_HERE     = Path(__file__).parent
_DB_JSON  = _HERE / "n64_games.json"

# Cover art / save cache location
import os, platform as _plat
if _plat.system() == "Windows":
    _CACHE_DIR = Path(os.environ.get("APPDATA", Path.home())) / "N64Operator" / "cache"
elif _plat.system() == "Darwin":
    _CACHE_DIR = Path.home() / "Library" / "Application Support" / "N64Operator" / "cache"
else:
    _CACHE_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "N64Operator" / "cache"
_CACHE_DB   = _CACHE_DIR / "game_cache.db"

# Bundled cover art shipped with the app (PNG files named by game code)
_COVERS_DIR = _HERE / "covers"

# Libretro thumbnail base — free, no API key, great N64 coverage
_LIBRETRO_BASE = "https://thumbnails.libretro.com/Nintendo%20-%20Nintendo%2064/Named_Boxarts/"


class CartridgeStatus(Enum):
    UNKNOWN    = auto()
    OFFICIAL   = auto()
    UNOFFICIAL = auto()


@dataclass
class GameInfo:
    title:            str
    game_code:        str        = ""
    publisher:        str        = ""
    developer:        str        = ""
    year:             int        = 0
    region:           str        = ""
    genre:            str        = ""
    players:          int        = 0
    description:      str        = ""
    cover_url:        str        = ""
    crc1:             str        = ""
    cartridge_status: CartridgeStatus = CartridgeStatus.UNKNOWN
    gameshark_codes:  List[dict] = field(default_factory=list)

    @property
    def players_str(self) -> str:
        if self.players == 1: return "1 Player"
        if self.players >= 2: return f"1–{self.players} Players"
        return ""


class GameDatabase:

    def __init__(self):
        self._lock      = threading.Lock()
        self._games     : List[dict]       = []
        self._code_idx  : Dict[str, int]   = {}   # exact game_code -> index
        self._crc_idx   : Dict[str, str]   = {}   # "0xNNNNNNNN" -> game_code
        self._loaded    = False

    def load(self) -> None:
        with self._lock:
            if self._loaded:
                return
            try:
                raw = json.loads(_DB_JSON.read_text(encoding="utf-8"))
                for game in raw.get("games", []):
                    code = game.get("game_code", "").upper().strip()
                    self._games.append(game)
                    idx = len(self._games) - 1
                    if code and code not in self._code_idx:
                        self._code_idx[code] = idx
                    crc = game.get("crc1", "").upper().strip()
                    if crc and code:
                        self._crc_idx[crc] = code
                logger.info(
                    f"DB loaded: {len(self._games)} games, "
                    f"{len(self._code_idx)} codes, {len(self._crc_idx)} CRCs"
                )
            except Exception as e:
                logger.error(f"DB load failed: {e}")
            self._loaded = True
            self._ensure_cache_db()

    def _ensure_cache_db(self):
        try:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(_CACHE_DB))
            conn.execute("""CREATE TABLE IF NOT EXISTS cover_art (
                game_code TEXT PRIMARY KEY,
                image_data BLOB,
                fetched_at REAL
            )""")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Cache DB init: {e}")

    # ── Lookup ────────────────────────────────────────────────────────

    def lookup_rom(self, rom_info) -> "GameInfo":
        """
        Identify a ROM. Returns GameInfo (may be a minimal fallback).
        Priority: CRC1 > exact code > title-based search > prefix > fallback.
        """
        self.load()
        game = None
        header_title = (rom_info.header.title or "").strip().upper()
        code = rom_info.header.game_code.upper().strip()

        logger.info(f"lookup_rom: title={header_title!r} code={code!r} "
                    f"crc1=0x{rom_info.header.crc1:08X}")

        # 1. CRC match (most reliable — confirms exact ROM)
        if rom_info.header.crc1:
            crc_key = f"0X{rom_info.header.crc1:08X}"
            db_code = self._crc_idx.get(crc_key)
            if db_code and db_code in self._code_idx:
                game = self._make_gameinfo(self._games[self._code_idx[db_code]])
                game.cartridge_status = CartridgeStatus.OFFICIAL
                logger.info(f"CRC match: {game.title} [{db_code}]")

        # 2. Header title match — MORE RELIABLE than game code for DreamDump64
        #    The ROM's own title field (e.g. "TOY STORY 2") is ground truth.
        #    Game code bytes can be misread due to dump format quirks.
        if not game and len(header_title) >= 4:
            best_match = None
            best_score = 0
            ht_clean = header_title.replace(" ", "").replace("-","")
            for g in self._games:
                db_title = g.get("title", "").upper().replace(" ", "").replace("-","")
                # Score based on how many chars of header title match DB title
                score = 0
                min_len = min(len(ht_clean), len(db_title), 12)
                for i in range(min_len):
                    if ht_clean[i] == db_title[i]:
                        score += 1
                    else:
                        break  # must match from start
                if score >= min(8, len(ht_clean)) and score > best_score:
                    best_score = score
                    best_match = g
            if best_match:
                game = self._make_gameinfo(best_match)
                game.cartridge_status = CartridgeStatus.UNOFFICIAL
                logger.info(f"Title match (score={best_score}): {game.title} "
                            f"(header={header_title!r})")

        # 3. Exact game code
        if not game and code in self._code_idx:
            game = self._make_gameinfo(self._games[self._code_idx[code]])
            game.cartridge_status = CartridgeStatus.UNOFFICIAL
            logger.info(f"Code match: {game.title} [{code}]")

        # 4. 3-char prefix
        if not game and len(code) >= 3:
            prefix = code[:3]
            for g in self._games:
                if g.get("game_code", "").upper().startswith(prefix):
                    game = self._make_gameinfo(g)
                    game.cartridge_status = CartridgeStatus.UNOFFICIAL
                    logger.info(f"Prefix match: {game.title} [{g.get('game_code')}]")
                    break

        # 5. Fallback: use header title directly
        if not game:
            title = rom_info.header.title.strip() or code or "Unknown Game"
            logger.info(f"No DB match — using header title: {title!r}")
            game = GameInfo(
                title=title,
                game_code=code,
                region=rom_info.header.region,
                cartridge_status=CartridgeStatus.UNKNOWN,
            )

        return game

    def _make_gameinfo(self, d: dict) -> GameInfo:
        return GameInfo(
            title       = d.get("title", ""),
            game_code   = d.get("game_code", ""),
            publisher   = d.get("publisher", ""),
            developer   = d.get("developer", ""),
            year        = d.get("year", 0),
            region      = d.get("region", ""),
            genre       = d.get("genre", ""),
            players     = d.get("players", 0),
            description = d.get("description", ""),
            cover_url   = d.get("cover_url", ""),
            crc1        = d.get("crc1", ""),
            gameshark_codes = d.get("gameshark_codes", []),
        )

    # ── Cover art ─────────────────────────────────────────────────────

    def fetch_cover_art(self, game_info: "GameInfo", callback=None) -> None:
        """Fetch cover art in background. Calls callback(bytes_or_None)."""
        threading.Thread(
            target=self._fetch_cover_thread,
            args=(game_info, callback),
            daemon=True,
        ).start()

    def _fetch_cover_thread(self, game: "GameInfo", callback) -> None:
        data = None
        try:
            # 0. Bundled cover — shipped with the app, instant, no network
            data = self._load_bundled_cover(game.game_code)

            # 1. Local cache (previously downloaded)
            if not data:
                data = self._load_cache(game.game_code)

            # 2. Bundled cover_url from DB
            if not data and game.cover_url:
                data = self._download(game.cover_url)
                if data:
                    self._save_cache(game.game_code, data)

            # 3. Libretro thumbnails CDN
            if not data:
                data = self._fetch_libretro(game.title)
                if data:
                    self._save_cache(game.game_code, data)

        except Exception as e:
            logger.debug(f"Cover art error for {game.title}: {e}")

        if callback:
            callback(data)

    def _load_bundled_cover(self, game_code: str) -> Optional[bytes]:
        """Load cover art bundled with the app (src/database/covers/{code}.png)."""
        if not game_code:
            return None
        # Try exact code first, then first 3 chars (regional variants)
        for code in [game_code.upper(), game_code.upper()[:3]]:
            p = _COVERS_DIR / f"{code}.png"
            if p.exists():
                try:
                    data = p.read_bytes()
                    logger.info(f"Bundled cover loaded: {p.name}")
                    return data
                except Exception:
                    pass
        return None

    def _fetch_libretro(self, title: str) -> Optional[bytes]:
        """
        Fetch cover art from libretro thumbnails CDN.
        Format: https://thumbnails.libretro.com/Nintendo - Nintendo 64/Named_Boxarts/{title}.png
        The title must match the libretro DB name (case-sensitive).
        """
        def _clean(t: str) -> str:
            for ch in ['/', chr(92), ':', '*', '?', '"', '<', '>', '|']:
                t = t.replace(ch, '_')
            return t.strip()

        # Build candidate title list to try
        candidates = [title]

        # libretro uses ' - ' instead of ': ' for subtitles
        if ': ' in title:
            candidates.append(title.replace(': ', ' - '))
            candidates.append(title.replace(': ', ' - ') + ' (USA)')

        # Try with (USA) suffix
        candidates.append(title + ' (USA)')

        # Try without subtitle
        if ':' in title:
            candidates.append(title.split(':')[0].strip())

        seen = set()
        for t in candidates:
            if t in seen: continue
            seen.add(t)
            # Libretro uses %20 for spaces, full URL encoding for other chars
            safe = urllib.parse.quote(_clean(t), safe="")
            url  = _LIBRETRO_BASE + safe + ".png"
            logger.debug(f"Libretro cover attempt: {url}")
            data = self._download(url, timeout=8)
            if data and len(data) > 500:
                logger.info(f"Cover art loaded for: {t!r}")
                return data

        logger.debug(f"No cover art found for: {title!r}")
        return None

    def _load_cache(self, game_code: str) -> Optional[bytes]:
        try:
            conn = sqlite3.connect(str(_CACHE_DB))
            row = conn.execute(
                "SELECT image_data FROM cover_art WHERE game_code = ?",
                (game_code,)
            ).fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None

    def _save_cache(self, game_code: str, data: bytes) -> None:
        try:
            conn = sqlite3.connect(str(_CACHE_DB))
            conn.execute(
                "INSERT OR REPLACE INTO cover_art (game_code, image_data, fetched_at) VALUES (?,?,?)",
                (game_code, data, time.time())
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Cache save failed: {e}")

    def _download(self, url: str, timeout: int = 8) -> Optional[bytes]:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "N64Operator/0.5"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            logger.debug(f"Download failed {url}: {e}")
            return None


# ── Singleton ──────────────────────────────────────────────────────────────────
_db: Optional[GameDatabase] = None

def get_game_database() -> GameDatabase:
    global _db
    if _db is None:
        _db = GameDatabase()
    return _db

def get_cheat_manager():
    """Stub — returns the database for cheat code access."""
    return get_game_database()
