"""
N64 Operator — Settings Dialog
Sidebar navigation, 5 sections.
"""

import logging
import platform
from pathlib import Path
from typing import Optional, List, Dict

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QFrame, QHBoxLayout, QVBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QStackedWidget,
    QLineEdit, QComboBox, QCheckBox, QScrollArea, QFileDialog,
    QTextEdit, QDialogButtonBox, QMessageBox, QSizePolicy,
)

logger = logging.getLogger(__name__)

# ── Minimal colour tokens (standalone, no shared styles) ─────────────────────
BG       = "#0D0D0F"
BG_PANEL = "#111114"
BG_SURF  = "#1E1E22"
BG_HOVER = "#26262C"
BORDER   = "#2A2A2E"
BORD_MID = "#383840"
BORD_FOC = "#555560"
TEXT_1   = "#EEEEEE"
TEXT_2   = "#888899"
TEXT_3   = "#4A4A5A"
ACCENT   = "#1A8FE3"

SANS = ('"Segoe UI", "-apple-system", "SF Pro Display", '
        '"Ubuntu", "Noto Sans", system-ui, sans-serif')
MONO = '"Cascadia Code", "Consolas", "SF Mono", monospace'

STYLE = f"""
* {{ font-family: {SANS}; color: {TEXT_1}; outline: none; }}
QWidget {{ background: transparent; }}
QDialog {{ background: {BG}; }}

QListWidget#sidebar {{
    background: {BG_PANEL};
    border: none;
    border-right: 1px solid {BORDER};
    outline: none;
}}
QListWidget#sidebar::item {{
    color: {TEXT_2}; padding: 11px 18px; border: none;
}}
QListWidget#sidebar::item:hover {{
    background: {BG_SURF}; color: {TEXT_1};
}}
QListWidget#sidebar::item:selected {{
    background: {BG_SURF}; color: {TEXT_1};
    border-left: 3px solid {ACCENT}; padding-left: 15px;
}}

QPushButton#btnSec {{
    background: transparent; border: 1px solid {BORD_MID};
    border-radius: 6px; color: {TEXT_2}; font-size: 12px;
    font-weight: 600; padding: 8px 16px;
}}
QPushButton#btnSec:hover {{
    background: {BG_SURF}; color: {TEXT_1}; border-color: {BORD_FOC};
}}
QPushButton#btnPrimary {{
    background: {TEXT_1}; color: {BG};
    border: none; border-radius: 7px;
    font-weight: 800; padding: 10px 28px;
}}
QPushButton#btnPrimary:hover {{ background: #FFFFFF; }}

QCheckBox {{ spacing: 10px; color: {TEXT_1}; font-size: 13px; }}
QCheckBox::indicator {{
    width: 34px; height: 18px; border-radius: 9px;
    background: {BG_SURF}; border: 1px solid {BORD_MID};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QComboBox {{
    background: {BG_SURF}; border: 1px solid {BORD_MID};
    border-radius: 6px; padding: 7px 12px; color: {TEXT_1};
    font-size: 13px; min-width: 160px;
}}
QComboBox:hover {{ border-color: {BORD_FOC}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {BG_SURF}; border: 1px solid {BORD_MID};
    color: {TEXT_1}; selection-background-color: {BG_HOVER};
    outline: none; padding: 4px;
}}

QLineEdit {{
    background: {BG}; border: 1px solid {BORD_MID};
    border-radius: 6px; padding: 8px 12px; color: {TEXT_1};
    font-size: 13px;
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}

QTextEdit#logOut {{
    background: {BG_PANEL}; border: 1px solid {BORDER};
    color: #66FF88; font-family: {MONO};
    font-size: 11px; padding: 8px;
}}

QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BORD_MID}; border-radius: 2px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QDialogButtonBox QPushButton {{
    background: {BG_SURF}; border: 1px solid {BORD_MID};
    border-radius: 6px; color: {TEXT_1}; padding: 8px 22px;
    font-weight: 600; min-width: 80px;
}}
QDialogButtonBox QPushButton:hover {{
    background: {BG_HOVER}; border-color: {BORD_FOC};
}}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hdiv():
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"border:none; border-top:1px solid {BORDER}; background:transparent;")
    f.setMaximumHeight(1)
    return f


def _section(text):
    l = QLabel(text)
    l.setStyleSheet(
        f"color:{TEXT_3}; font-size:10px; font-weight:700; letter-spacing:1.5px;"
    )
    return l


def _header(title, sub=""):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 16)
    v.setSpacing(4)
    h = QLabel(title)
    h.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
    h.setStyleSheet(f"color:{TEXT_1};")
    v.addWidget(h)
    if sub:
        s = QLabel(sub)
        s.setStyleSheet(f"color:{TEXT_2}; font-size:12px;")
        s.setWordWrap(True)
        v.addWidget(s)
    v.addWidget(_hdiv())
    return w


def _row(label, widget, desc=""):
    c = QWidget()
    h = QHBoxLayout(c)
    h.setContentsMargins(0, 0, 0, 0)
    lv = QVBoxLayout()
    lv.setSpacing(2)
    ll = QLabel(label)
    ll.setStyleSheet(f"color:{TEXT_1}; font-size:13px; font-weight:500;")
    lv.addWidget(ll)
    if desc:
        dl = QLabel(desc)
        dl.setStyleSheet(f"color:{TEXT_3}; font-size:11px;")
        lv.addWidget(dl)
    h.addLayout(lv)
    h.addStretch()
    h.addWidget(widget)
    return c


def _scroll_page():
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 20, 40)
    layout.setSpacing(16)
    scroll.setWidget(content)
    outer = QWidget()
    ov = QVBoxLayout(outer)
    ov.setContentsMargins(0, 0, 0, 0)
    ov.addWidget(scroll)
    return outer, layout


# ── Pages ─────────────────────────────────────────────────────────────────────

class PlaybackPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        p, lay = _scroll_page()
        lay.addWidget(_header("Playback", "Configure N64 Operator behaviour."))

        self.chk_auto = QCheckBox()
        lay.addWidget(_row("Auto-launch on cartridge insert",
                           self.chk_auto,
                           "Start the game automatically when the drive mounts"))

        self.chk_save = QCheckBox()
        self.chk_save.setChecked(True)
        lay.addWidget(_row("Save ROM dump to disk", self.chk_save,
                           "Auto-save dumped ROMs to your ROMs folder"))

        lay.addWidget(_hdiv())
        lay.addWidget(_section("ROM FOLDER"))

        rrow = QHBoxLayout()
        self.rom_edit = QLineEdit()
        self.rom_edit.setPlaceholderText("~/N64ROMs")
        rrow.addWidget(self.rom_edit)
        b = QPushButton("Browse")
        b.setObjectName("btnSec")
        b.clicked.connect(self._browse)
        rrow.addWidget(b)
        rw = QWidget(); rw.setLayout(rrow)
        lay.addWidget(_row("ROM save folder", rw))
        lay.addStretch()

        QVBoxLayout(self).addWidget(p)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select ROM folder")
        if d:
            self.rom_edit.setText(d)


class EmulatorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        p, lay = _scroll_page()
        lay.addWidget(_header("Emulator Core",
                              "N64 Operator uses Mupen64Plus. "
                              "Leave all paths blank to auto-detect."))

        lay.addWidget(_section("MUPEN64PLUS"))
        prow = QHBoxLayout()
        self.mupen_edit = QLineEdit()
        self.mupen_edit.setPlaceholderText("Auto-detect")
        prow.addWidget(self.mupen_edit)
        b = QPushButton("Browse")
        b.setObjectName("btnSec")
        b.clicked.connect(self._browse)
        prow.addWidget(b)
        pw = QWidget(); pw.setLayout(prow)
        lay.addWidget(_row("Executable path", pw, "Leave blank to auto-detect"))

        lay.addWidget(_hdiv())
        lay.addWidget(_section("PLUGINS"))

        self.video = QComboBox()
        self.video.addItems(["mupen64plus-video-GLideN64",
                             "mupen64plus-video-Rice",
                             "mupen64plus-video-angrylion"])
        lay.addWidget(_row("Video plugin", self.video, "GLideN64 recommended"))

        self.audio = QComboBox()
        self.audio.addItems(["mupen64plus-audio-sdl", "mupen64plus-audio-sdl2"])
        lay.addWidget(_row("Audio plugin", self.audio))

        self.rsp = QComboBox()
        self.rsp.addItems(["mupen64plus-rsp-hle", "mupen64plus-rsp-cxd4"])
        lay.addWidget(_row("RSP plugin", self.rsp, "HLE is faster; CXD4 more accurate"))
        lay.addStretch()

        QVBoxLayout(self).addWidget(p)

    def _browse(self):
        ext = "*.exe" if platform.system() == "Windows" else ""
        p, _ = QFileDialog.getOpenFileName(self, "Mupen64Plus executable", "", ext)
        if p:
            self.mupen_edit.setText(p)


class GraphicsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        p, lay = _scroll_page()
        lay.addWidget(_header("Graphics", "Display and rendering settings."))

        lay.addWidget(_section("DISPLAY"))

        self.res = QComboBox()
        self.res.addItems(["Native (320×240)", "1x (640×480)", "2x (960×720)",
                           "3x (1280×960)", "4x (1920×1440)"])
        self.res.setCurrentIndex(3)
        lay.addWidget(_row("Internal resolution", self.res,
                           "Higher = sharper, more GPU load"))

        self.fullscreen = QCheckBox()
        lay.addWidget(_row("Fullscreen", self.fullscreen))

        self.vsync = QCheckBox()
        self.vsync.setChecked(True)
        lay.addWidget(_row("V-Sync", self.vsync, "Reduces screen tearing"))

        lay.addWidget(_hdiv())
        lay.addWidget(_section("ASPECT RATIO"))

        self.aspect = QComboBox()
        self.aspect.addItems(["4:3 (Original)", "16:9 (Widescreen hack)", "Stretch"])
        lay.addWidget(_row("Aspect ratio", self.aspect))

        lay.addWidget(_hdiv())
        lay.addWidget(_section("SHADERS"))

        self.shader = QComboBox()
        self.shader.addItems(["None", "CRT-Royale", "CRT-Easymode",
                              "xBR (Smooth)", "HQ4x", "Scanlines", "VHS"])
        lay.addWidget(_row("Shader preset", self.shader))
        lay.addStretch()

        QVBoxLayout(self).addWidget(p)


class ControlsPage(QWidget):
    BUTTONS = [
        ("A Button", "a_button"), ("B Button", "b_button"),
        ("Z Trigger", "z_trigger"), ("Start", "start"),
        ("D-Pad Up", "dpad_up"), ("D-Pad Down", "dpad_down"),
        ("D-Pad Left", "dpad_left"), ("D-Pad Right", "dpad_right"),
        ("L Trigger", "l_trigger"), ("R Trigger", "r_trigger"),
        ("C-Up", "c_up"), ("C-Down", "c_down"),
        ("C-Left", "c_left"), ("C-Right", "c_right"),
        ("Stick Up", "stick_up"), ("Stick Down", "stick_down"),
        ("Stick Left", "stick_left"), ("Stick Right", "stick_right"),
    ]
    DEFAULTS = {
        "a_button":"X", "b_button":"Z", "z_trigger":"LShift", "start":"Return",
        "dpad_up":"T", "dpad_down":"G", "dpad_left":"F", "dpad_right":"H",
        "l_trigger":"Q", "r_trigger":"W",
        "c_up":"I", "c_down":"K", "c_left":"J", "c_right":"L",
        "stick_up":"Up", "stick_down":"Down", "stick_left":"Left", "stick_right":"Right",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        p, lay = _scroll_page()
        lay.addWidget(_header("Controls",
                              "Keyboard and gamepad bindings for all 18 N64 inputs."))
        lay.addWidget(_section("KEYBOARD BINDINGS"))

        self._edits: Dict[str, QLineEdit] = {}
        for label, kid in self.BUTTONS:
            e = QLineEdit(self.DEFAULTS.get(kid, ""))
            e.setFixedWidth(90)
            e.setPlaceholderText("Click to bind")
            self._edits[kid] = e
            lay.addWidget(_row(label, e))

        lay.addWidget(_hdiv())
        lay.addWidget(_section("GAMEPAD"))

        self.gamepad = QComboBox()
        self.gamepad.addItems(["Auto-detect", "Player 1", "Player 2"])
        lay.addWidget(_row("Active gamepad", self.gamepad))

        self.deadzone = QComboBox()
        self.deadzone.addItems(["10%", "15%", "20%", "25%"])
        lay.addWidget(_row("Stick dead zone", self.deadzone))

        rst = QPushButton("Reset to Defaults")
        rst.setObjectName("btnSec")
        rst.clicked.connect(self._reset)
        lay.addWidget(rst)
        lay.addStretch()

        QVBoxLayout(self).addWidget(p)

    def _reset(self):
        for kid, e in self._edits.items():
            e.setText(self.DEFAULTS.get(kid, ""))


class GameSharkPage(QWidget):
    codes_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._game_code: Optional[str] = None
        self._rows: List[QWidget] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_header("GameShark Codes",
                                "Enable cheats for the current game."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._list_lay = QVBoxLayout(self._content)
        self._list_lay.setContentsMargins(0, 0, 20, 12)
        self._list_lay.setSpacing(8)

        self._empty_lbl = QLabel("No codes available for this game.\nAdd custom codes below.")
        self._empty_lbl.setStyleSheet(f"color:{TEXT_3}; font-size:13px;")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_lay.addWidget(self._empty_lbl)
        self._list_lay.addStretch()

        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

        # Add code area
        outer.addWidget(_hdiv())
        add = QWidget()
        add.setStyleSheet(f"background:{BG_PANEL};")
        al = QVBoxLayout(add)
        al.setContentsMargins(0, 12, 20, 16)
        al.setSpacing(8)
        al.addWidget(_section("ADD CUSTOM CODE"))

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Code name  (e.g. Infinite Lives)")
        al.addWidget(self._name_edit)

        code_row = QHBoxLayout()
        self._code_edit = QLineEdit()
        self._code_edit.setPlaceholderText("8033B21D 0063")
        self._code_edit.setFont(QFont("Consolas", 12))
        code_row.addWidget(self._code_edit)
        ab = QPushButton("Add")
        ab.setObjectName("btnSec")
        ab.clicked.connect(self._add)
        code_row.addWidget(ab)
        al.addLayout(code_row)
        hint = QLabel("Format: XXXXXXXX YYYY")
        hint.setStyleSheet(f"color:{TEXT_3}; font-size:11px;")
        al.addWidget(hint)
        outer.addWidget(add)

    def load_for_game(self, game_code: str, codes: List[dict]):
        self._game_code = game_code
        for r in self._rows:
            self._list_lay.removeWidget(r)
            r.deleteLater()
        self._rows.clear()
        if not codes:
            self._empty_lbl.show()
            return
        self._empty_lbl.hide()
        for cd in codes:
            row = self._make_row(cd)
            self._list_lay.insertWidget(self._list_lay.count()-1, row)
            self._rows.append(row)

    def _make_row(self, cd: dict) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"QFrame{{background:{BG_SURF};border-radius:7px;border:1px solid {BORDER};}}"
        )
        lay = QHBoxLayout(row)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)

        chk = QCheckBox()
        chk.setChecked(cd.get("enabled", False))
        lay.addWidget(chk)

        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(QLabel(cd.get("name", "")))
        cl = QLabel(cd.get("code", "").replace("\n", "  |  "))
        cl.setStyleSheet(
            f"color:{TEXT_3}; font-size:10px; font-family:'Consolas',monospace;"
        )
        info.addWidget(cl)
        lay.addLayout(info)
        lay.addStretch()

        name = cd.get("name", "")
        def on_toggle(checked, n=name):
            from src.database import get_cheat_manager
            if self._game_code:
                get_cheat_manager().set_code_enabled(self._game_code, n, checked)
            self.codes_changed.emit()
        chk.toggled.connect(on_toggle)
        return row

    def _add(self):
        name = self._name_edit.text().strip()
        code = self._code_edit.text().strip()
        if not name or not code:
            return
        from src.database import get_cheat_manager
        from src.database.gameshark import CheatCode
        c = CheatCode(name=name, code=code)
        if not c.is_valid():
            QMessageBox.warning(self, "Invalid Code",
                                f"'{code}' is not a valid GameShark code.\nFormat: XXXXXXXX YYYY")
            return
        if self._game_code:
            get_cheat_manager().add_custom_code(self._game_code, name, code)
        row = self._make_row({"name": name, "code": code, "enabled": False})
        self._list_lay.insertWidget(self._list_lay.count()-1, row)
        self._rows.append(row)
        self._name_edit.clear()
        self._code_edit.clear()
        self._empty_lbl.hide()
        self.codes_changed.emit()


# ── Main dialog ───────────────────────────────────────────────────────────────

SIDEBAR_ITEMS = [
    "⚙   Playback",
    "🎮  Emulator",
    "🖥   Graphics",
    "🕹   Controls",
    "💥  GameShark",
]


class SettingsDialog(QDialog):
    def __init__(self, parent=None, initial_page=0,
                 game_code="", game_codes=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(780, 560)
        self.setStyleSheet(STYLE)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Sidebar
        sb_w = QWidget()
        sb_w.setFixedWidth(190)
        sb_w.setStyleSheet(
            f"background:{BG_PANEL}; border-right:1px solid {BORDER};"
        )
        sb_l = QVBoxLayout(sb_w)
        sb_l.setContentsMargins(0, 0, 0, 0)
        sb_l.setSpacing(0)

        title = QLabel("SETTINGS")
        title.setStyleSheet(
            f"color:{TEXT_3}; font-size:10px; font-weight:700; "
            f"letter-spacing:1.5px; padding:20px 18px 12px;"
        )
        sb_l.addWidget(title)
        sb_l.addWidget(_hdiv())

        self._sidebar = QListWidget()
        self._sidebar.setObjectName("sidebar")
        for item_label in SIDEBAR_ITEMS:
            it = QListWidgetItem(item_label)
            it.setSizeHint(QSize(190, 42))
            self._sidebar.addItem(it)
        sb_l.addWidget(self._sidebar)
        sb_l.addStretch()
        lay.addWidget(sb_w)

        # Content
        self._stack = QStackedWidget()
        cw = QWidget()
        cw.setStyleSheet(f"background:{BG};")
        cl = QVBoxLayout(cw)
        cl.setContentsMargins(30, 26, 30, 16)

        self._playback = PlaybackPage()
        self._emulator = EmulatorPage()
        self._graphics = GraphicsPage()
        self._controls = ControlsPage()
        self._gameshark = GameSharkPage()

        for pg in [self._playback, self._emulator, self._graphics,
                   self._controls, self._gameshark]:
            self._stack.addWidget(pg)

        cl.addWidget(self._stack)

        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        close = QPushButton("Close")
        close.setObjectName("btnSec")
        close.clicked.connect(self.accept)
        btn_bar.addWidget(close)
        cl.addLayout(btn_bar)

        lay.addWidget(cw, 1)

        self._sidebar.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._sidebar.setCurrentRow(initial_page)

        if game_code and game_codes:
            self._gameshark.load_for_game(game_code, game_codes)

    def get_emulator_path(self):
        return self._emulator.mupen_edit.text().strip()
