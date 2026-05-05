"""
N64 Operator — Playback Window  v0.6.4
"""
from __future__ import annotations

import logging, math, os, platform, sys, threading
from pathlib import Path
from typing import Optional

from PyQt6.QtCore    import Qt, QThread, pyqtSignal, QTimer, QRectF
from PyQt6.QtGui     import (QFont, QColor, QPainter, QPen, QBrush,
                              QPixmap, QPainterPath, QKeySequence, QAction)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QFrame,
    QVBoxLayout, QHBoxLayout, QPushButton, QProgressBar,
    QFileDialog, QMessageBox, QStackedWidget, QScrollArea,
    QDialog,
)

logger = logging.getLogger(__name__)

BG       = "#0D0D0F"
BG_BAR   = "#111114"
BG_CARD  = "#161618"
BG_SURF  = "#1E1E22"
BORDER   = "#2A2A2E"
BORD_MID = "#38383F"
TEXT_1   = "#EFEFEF"
TEXT_2   = "#88889A"
TEXT_3   = "#44445A"
GREEN    = "#3DDC84"
RED      = "#FF5555"
AMBER    = "#FFB84D"

_SANS = '"Segoe UI","-apple-system","SF Pro Text","Ubuntu","Noto Sans",system-ui,sans-serif'
_MONO = '"Cascadia Code","Consolas","SF Mono",monospace'

STYLESHEET = f"""
* {{ font-family:{_SANS}; color:{TEXT_1}; outline:none; }}
QMainWindow, QWidget#root {{ background:{BG}; }}
QWidget {{ background:transparent; }}
QWidget#bar {{ background:{BG_BAR}; border-bottom:1px solid {BORDER}; }}

QPushButton#play {{
    background:{TEXT_1}; color:{BG}; border:none; border-radius:10px;
    font-size:14px; font-weight:800; letter-spacing:1.8px; padding:16px 54px;
}}
QPushButton#play:hover   {{ background:#FFFFFF; }}
QPushButton#play:pressed {{ background:#CCCCCC; }}
QPushButton#play:disabled {{ background:{BG_SURF}; color:{TEXT_3}; }}

QPushButton#sec {{
    background:transparent; border:1px solid {BORD_MID}; border-radius:7px;
    color:{TEXT_2}; font-size:12px; font-weight:600; padding:9px 18px;
}}
QPushButton#sec:hover {{ background:{BG_SURF}; color:{TEXT_1}; border-color:#555560; }}

QPushButton#link {{
    background:transparent; border:none; color:{TEXT_2};
    font-size:13px; text-decoration:underline; padding:4px;
}}
QPushButton#link:hover {{ color:{TEXT_1}; }}

QPushButton#icon {{
    background:transparent; border:none; color:{TEXT_3}; font-size:17px;
    padding:8px; min-width:32px; max-width:32px; min-height:32px; max-height:32px;
    border-radius:6px;
}}
QPushButton#icon:hover {{ background:{BG_SURF}; color:{TEXT_2}; }}

QProgressBar {{
    background:{BG_SURF}; border:none; border-radius:3px; height:4px; font-size:0px;
}}
QProgressBar::chunk {{ background:{TEXT_1}; border-radius:3px; }}

QLabel#log {{
    background:{BG_BAR}; border-top:1px solid {BORDER};
    color:{TEXT_3}; font-size:11px; font-family:{_MONO}; padding:5px 16px;
}}

QMenu {{
    background:{BG_SURF}; border:1px solid {BORD_MID}; border-radius:8px;
    padding:6px; font-size:13px;
}}
QMenu::item {{ padding:8px 20px; border-radius:5px; }}
QMenu::item:selected {{ background:{BG_CARD}; }}
QMenu::separator {{ height:1px; background:{BORDER}; margin:4px 10px; }}

QScrollBar:vertical {{ background:transparent; width:4px; }}
QScrollBar::handle:vertical {{ background:{BORD_MID}; border-radius:2px; min-height:20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}

QDialog {{ background:{BG}; }}
"""


# ── Tiny helpers ──────────────────────────────────────────────────────────────

def _div():
    f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"border:none;border-top:1px solid {BORDER};background:transparent;")
    f.setMaximumHeight(1); return f

def _lbl(text, color=TEXT_1, size=13, weight=400):
    l = QLabel(text)
    l.setStyleSheet(f"color:{color};font-size:{size}px;font-weight:{weight};")
    return l


class _Dot(QWidget):
    def __init__(self, p=None):
        super().__init__(p); self._c = QColor(TEXT_3); self.setFixedSize(9, 9)
    def set(self, h): self._c = QColor(h); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(self._c); p.drawEllipse(0, 0, 9, 9)


class DotsAnimation(QWidget):
    def __init__(self, size=10, gap=16, parent=None):
        super().__init__(parent)
        self._s = size; self._g = gap
        self._col = QColor(TEXT_1); self._phase = 0.0
        self._t = QTimer(self); self._t.timeout.connect(self._tick)
        self.setFixedSize(size * 3 + gap * 2 + 10, size * 3 + 10)
    def start(self):
        if not self._t.isActive(): self._t.start(38)
    def stop(self): self._t.stop()
    def _tick(self): self._phase = (self._phase + 0.065) % (2 * math.pi); self.update()
    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._s // 2
        x0 = (self.width() - (self._s * 3 + self._g * 2)) // 2
        cy = self.height() // 2
        for i in range(3):
            off = i * (2 * math.pi / 3)
            dy  = int(math.sin(self._phase - off) * (r * 0.7))
            alpha = int((math.sin(self._phase - off) + 1) / 2 * 155 + 80)
            c = QColor(self._col); c.setAlpha(alpha)
            cx = x0 + i * (self._s + self._g) + r
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(c)
            p.drawEllipse(cx - r, cy + dy - r, self._s, self._s)


class CoverArt(QWidget):
    def __init__(self, size=200, parent=None):
        super().__init__(parent)
        self._sz = size; self._R = 14.0
        self._px = None; self._loading = False; self._phase = 0.0
        self.setFixedSize(size, size)
        self._t = QTimer(self); self._t.timeout.connect(self._tick)

    def show_loading(self):
        self._px = None; self._loading = True; self._t.start(45); self.update()

    def show_image(self, data: Optional[bytes]):
        self._loading = False; self._t.stop(); self._px = None
        if data:
            px = QPixmap()
            if px.loadFromData(data) and not px.isNull():
                self._px = px.scaled(
                    self._sz, self._sz,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
        self.update()

    def clear(self):
        self._px = None; self._loading = False; self._t.stop(); self.update()

    def _tick(self): self._phase = (self._phase + 0.07) % (2 * math.pi); self.update()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height(); R = self._R

        if self._px:
            path = QPainterPath(); path.addRoundedRect(QRectF(0, 0, w, h), R, R)
            p.setClipPath(path)
            x = (w - self._px.width()) // 2; y = (h - self._px.height()) // 2
            p.drawPixmap(x, y, self._px); return

        path = QPainterPath(); path.addRoundedRect(QRectF(0, 0, w, h), R, R)
        p.fillPath(path, QBrush(QColor(BG_SURF)))

        if self._loading:
            alpha = int((math.sin(self._phase) + 1) / 2 * 100 + 40)
            bc = QColor(TEXT_2); bc.setAlpha(alpha)
        else:
            bc = QColor(BORD_MID)
        p.setPen(QPen(bc, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(1, 1, w - 2, h - 2), R - 0.5, R - 0.5)

        # N64 cart silhouette
        cw = int(w * 0.48); ch = int(h * 0.58)
        cx = (w - cw) // 2; cy = (h - ch) // 2 - 6; bv = 11
        cart = QPainterPath()
        cart.moveTo(cx + bv, cy); cart.lineTo(cx + cw - bv, cy)
        cart.lineTo(cx + cw, cy + bv); cart.lineTo(cx + cw, cy + ch)
        cart.lineTo(cx, cy + ch); cart.lineTo(cx, cy + bv); cart.closeSubpath()
        p.setPen(QPen(QColor(BORD_MID), 1.5)); p.setBrush(QBrush(QColor(BG_CARD)))
        p.drawPath(cart)

        pw = int(cw * 0.75); ph = 7
        px_ = cx + (cw - pw) // 2; py = cy + ch - ph - 4
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(QColor(BG_SURF)))
        p.drawRect(px_, py, pw, ph); p.setBrush(QBrush(QColor(BORD_MID)))
        pin_x = px_ + 4
        while pin_x + 3 < px_ + pw - 4:
            p.drawRect(pin_x, py + 1, 3, ph - 2); pin_x += 8

        if self._loading:
            p.setPen(QColor(TEXT_3)); p.setFont(QFont("Segoe UI", 9))
            p.drawText(0, cy + ch + 8, w, 20, Qt.AlignmentFlag.AlignCenter, "Loading…")


# ── Screens ───────────────────────────────────────────────────────────────────

class SearchingScreen(QWidget):
    not_working     = pyqtSignal()
    refresh_clicked = pyqtSignal()

    def __init__(self, p=None):
        super().__init__(p)
        lay = QVBoxLayout(self); lay.setContentsMargins(40, 0, 40, 0); lay.setSpacing(0)
        lay.addStretch(2)

        self._dots = DotsAnimation(size=10, gap=16); self._dots.start()
        lay.addWidget(self._dots, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(38)

        h = QLabel("Searching…"); h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStyleSheet(f"color:{TEXT_1};font-size:26px;font-weight:700;letter-spacing:-0.5px;")
        lay.addWidget(h)
        lay.addSpacing(14)

        self._sub = QLabel("Looking for your DreamDump64 drive.\nPlease make sure it's connected.")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setStyleSheet(f"color:{TEXT_2};font-size:13px;")
        lay.addWidget(self._sub)
        lay.addSpacing(24)

        rb = QPushButton("↻  Refresh"); rb.setObjectName("sec")
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.clicked.connect(self.refresh_clicked)
        rb.setFixedWidth(120)
        lay.addWidget(rb, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch(3)

        nw = QPushButton("Not working?"); nw.setObjectName("link")
        nw.setCursor(Qt.CursorShape.PointingHandCursor)
        nw.clicked.connect(self.not_working)
        lay.addWidget(nw, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(32)

    def set_sub(self, t): self._sub.setText(t)


class ReadingScreen(QWidget):
    def __init__(self, p=None):
        super().__init__(p)
        lay = QVBoxLayout(self); lay.setContentsMargins(48, 0, 48, 0); lay.setSpacing(0)
        lay.addStretch(2)

        self._cover = CoverArt(size=150); self._cover.show_loading()
        lay.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addSpacing(32)

        h = QLabel("Reading cartridge…"); h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.setStyleSheet(f"color:{TEXT_1};font-size:22px;font-weight:700;")
        lay.addWidget(h)
        lay.addSpacing(8)

        self._sub = QLabel("Waiting for cartridge dump to finish…")
        self._sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sub.setStyleSheet(f"color:{TEXT_2};font-size:13px;")
        lay.addWidget(self._sub)
        lay.addSpacing(30)

        self._bar = QProgressBar(); self._bar.setRange(0, 100); self._bar.setValue(0)
        self._bar.setFixedHeight(4); lay.addWidget(self._bar)
        lay.addSpacing(10)

        self._pct = QLabel(""); self._pct.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pct.setStyleSheet(f"color:{TEXT_3};font-size:11px;")
        lay.addWidget(self._pct)
        lay.addStretch(3)

    def set_progress(self, pct: float, label: str = ""):
        self._bar.setValue(int(pct))
        self._pct.setText(f"{pct:.0f}%  {label}" if label else f"{pct:.0f}%")

    def set_sub(self, t): self._sub.setText(t)


class GameScreen(QWidget):
    play_clicked     = pyqtSignal()
    save_clicked     = pyqtSignal()
    new_game_clicked = pyqtSignal()

    def __init__(self, p=None):
        super().__init__(p)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget(); cl = QVBoxLayout(content)
        cl.setContentsMargins(36, 32, 36, 24); cl.setSpacing(0)

        top = QHBoxLayout(); top.setSpacing(28)
        top.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Left: cover + auth
        lcol = QVBoxLayout(); lcol.setAlignment(Qt.AlignmentFlag.AlignTop); lcol.setSpacing(8)
        self._cover = CoverArt(size=190); lcol.addWidget(self._cover)
        self._auth = QLabel("")
        self._auth.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._auth.setStyleSheet(f"color:{TEXT_3};font-size:11px;font-weight:600;")
        lcol.addWidget(self._auth); lcol.addStretch()
        top.addLayout(lcol)

        # Right: info
        rcol = QVBoxLayout(); rcol.setAlignment(Qt.AlignmentFlag.AlignTop); rcol.setSpacing(0)

        self._title = QLabel("—"); self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"color:{TEXT_1};font-size:21px;font-weight:800;letter-spacing:-0.5px;")
        rcol.addWidget(self._title); rcol.addSpacing(6)

        self._sub2 = QLabel("")
        self._sub2.setStyleSheet(f"color:{TEXT_2};font-size:12px;font-weight:600;")
        rcol.addWidget(self._sub2)
        rcol.addSpacing(16); rcol.addWidget(_div()); rcol.addSpacing(14)

        self._desc = QLabel(""); self._desc.setWordWrap(True)
        self._desc.setStyleSheet(f"color:{TEXT_2};font-size:12px;")
        rcol.addWidget(self._desc)
        rcol.addSpacing(16); rcol.addWidget(_div()); rcol.addSpacing(14)

        mg = QHBoxLayout(); mg.setSpacing(24)
        self._mr = self._meta("REGION", "—"); self._mg = self._meta("GENRE",   "—")
        self._ms = self._meta("SIZE",   "—"); self._mp = self._meta("PLAYERS", "—")
        for m in [self._mr, self._mg, self._ms, self._mp]: mg.addLayout(m)
        mg.addStretch(); rcol.addLayout(mg); rcol.addStretch()
        top.addLayout(rcol, 1)

        cl.addLayout(top)
        cl.addSpacing(28); cl.addWidget(_div()); cl.addSpacing(20)

        # Action buttons
        acts = QHBoxLayout(); acts.setSpacing(10)

        self._btn_play = QPushButton("PLAY"); self._btn_play.setObjectName("play")
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.setEnabled(False)
        self._btn_play.clicked.connect(self.play_clicked)
        acts.addWidget(self._btn_play)

        self._btn_save = QPushButton("💾  Save ROM"); self._btn_save.setObjectName("sec")
        self._btn_save.setEnabled(False)
        self._btn_save.clicked.connect(self.save_clicked)
        acts.addWidget(self._btn_save)

        self._btn_new = QPushButton("⏏  New Game"); self._btn_new.setObjectName("sec")
        self._btn_new.setToolTip("Insert a new cartridge")
        self._btn_new.clicked.connect(self.new_game_clicked)
        acts.addWidget(self._btn_new)

        acts.addStretch(); cl.addLayout(acts)
        scroll.setWidget(content); QVBoxLayout(self).addWidget(scroll)

    def _meta(self, lbl: str, val: str):
        col = QVBoxLayout(); col.setSpacing(3)
        ll = QLabel(lbl)
        ll.setStyleSheet(
            f"color:{TEXT_3};font-size:9px;font-weight:700;letter-spacing:1.5px;")
        vl = QLabel(val)
        vl.setStyleSheet(f"color:{TEXT_1};font-size:12px;font-weight:600;")
        col.addWidget(ll); col.addWidget(vl); col._v = vl; return col

    def load(self, rom, game):
        self._title.setText(game.title)
        parts = []
        if getattr(game, "publisher", ""): parts.append(game.publisher)
        if getattr(game, "year", 0):       parts.append(str(game.year))
        self._sub2.setText("  ·  ".join(parts))

        desc = getattr(game, "description", "")
        self._desc.setText(desc[:300] + "…" if len(desc) > 300 else desc)

        self._mr._v.setText(getattr(game, "region",  None) or "—")
        self._mg._v.setText(getattr(game, "genre",   None) or "—")
        mb = getattr(rom, "size_mb", 0)
        self._ms._v.setText(f"{mb:.0f} MB" if mb else "—")
        ps = (getattr(game, "players_str", "")
              or (str(getattr(game, "players", 0)) if getattr(game, "players", 0) else "—"))
        self._mp._v.setText(ps)

        # Auth badge
        from src.database.game_db import CartridgeStatus
        cs = getattr(game, "cartridge_status", CartridgeStatus.UNKNOWN)
        if cs == CartridgeStatus.OFFICIAL:
            self._auth.setText("✓  Official Cartridge")
            self._auth.setStyleSheet(f"color:{GREEN};font-size:11px;font-weight:700;")
        elif cs == CartridgeStatus.UNOFFICIAL:
            self._auth.setText("⚠  Unofficial / Repro")
            self._auth.setStyleSheet(f"color:{AMBER};font-size:11px;font-weight:700;")
        else:
            self._auth.setText("")

        self._btn_play.setEnabled(True); self._btn_save.setEnabled(True)
        self._cover.clear(); self._cover.show_loading()

    def set_cover(self, data: Optional[bytes]):
        self._cover.show_image(data)


# ── Background threads ────────────────────────────────────────────────────────

class MonitorThread(QThread):
    state_changed = pyqtSignal(object, object)

    def __init__(self, mgr, p=None):
        super().__init__(p); self._mgr = mgr

    def run(self):
        self._mgr.on_state_change = lambda s, d: self.state_changed.emit(s, d)
        self._mgr.start_monitoring(); self.exec()

    def stop(self):
        self._mgr.stop_monitoring(); self.quit(); self.wait(3000)


class LoadThread(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(bytes)
    error    = pyqtSignal(str)

    def __init__(self, mgr, p=None):
        super().__init__(p); self._mgr = mgr

    def run(self):
        try:
            data = self._mgr.dump_rom(progress_callback=self._prog)
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))

    def _prog(self, prog):
        bps = prog.bytes_per_second
        label = f"({bps / (1024*1024):.1f} MB/s)" if bps > 0.5 else "Waiting…"
        self.progress.emit(prog.percent, label)


# ── Main window ───────────────────────────────────────────────────────────────

class PlaybackWindow(QMainWindow):
    S_SEARCH  = 0
    S_READING = 1
    S_GAME    = 2

    def __init__(self):
        super().__init__()
        self._rom              = None
        self._game             = None
        self._mgr              = None
        self._monitor          = None
        self._load_thread      = None
        self._loading          = False     # Guard against double reads
        self._current_session  = None     # Keep session alive so temp ROM isn't deleted

        self._setup()
        self._build_ui()
        self._build_menu()
        self._start_monitor()

    # ── Window ────────────────────────────────────────────────────────

    def _setup(self):
        self.setWindowTitle("N64 Operator")
        self.setMinimumSize(450, 560)
        self.resize(500, 640)
        self.setStyleSheet(STYLESHEET)

    def _build_ui(self):
        root = QWidget(); root.setObjectName("root")
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root); vbox.setContentsMargins(0, 0, 0, 0); vbox.setSpacing(0)

        # Title bar
        bar = QWidget(); bar.setObjectName("bar"); bar.setFixedHeight(50)
        bl = QHBoxLayout(bar); bl.setContentsMargins(20, 0, 12, 0); bl.setSpacing(0)
        logo = QLabel("●")
        logo.setStyleSheet(f"color:{TEXT_1};font-size:14px;margin-right:10px;")
        bl.addWidget(logo)
        bl.addWidget(_lbl("Playback", TEXT_2, 13, 600))
        bl.addStretch()
        self._dot = _Dot(); bl.addWidget(self._dot); bl.addSpacing(8)
        self._status_lbl = _lbl("Searching", TEXT_3, 12, 500)
        bl.addWidget(self._status_lbl); bl.addSpacing(14)
        gear = QPushButton("⚙"); gear.setObjectName("icon"); gear.setToolTip("Settings")
        gear.clicked.connect(self._settings); bl.addWidget(gear)
        vbox.addWidget(bar); vbox.addWidget(_div())

        # Screen stack
        self._stack  = QStackedWidget()
        self._s0     = SearchingScreen()
        self._s1     = ReadingScreen()
        self._s2     = GameScreen()
        self._stack.addWidget(self._s0)
        self._stack.addWidget(self._s1)
        self._stack.addWidget(self._s2)
        vbox.addWidget(self._stack, 1)

        # Log strip
        self._log_lbl = QLabel("N64 Operator v0.6.4")
        self._log_lbl.setObjectName("log"); self._log_lbl.setFixedHeight(26)
        vbox.addWidget(self._log_lbl)

        # Wire signals
        self._s0.not_working.connect(self._not_working)
        self._s0.refresh_clicked.connect(self._scan_now)
        self._s2.play_clicked.connect(self._play)
        self._s2.save_clicked.connect(self._save)
        self._s2.new_game_clicked.connect(self._new_game)

        self._show(self.S_SEARCH)

    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet(f"background:{BG};color:{TEXT_2};border:none;padding:2px;")

        def act(label, slot, shortcut=None):
            a = QAction(label, self); a.triggered.connect(slot)
            if shortcut: a.setShortcut(QKeySequence(shortcut))
            return a

        f = mb.addMenu("File")
        f.addAction(act("Open ROM File…", self._open_file, "Ctrl+O"))
        f.addAction(act("Save ROM…",      self._save,      "Ctrl+S"))
        f.addSeparator()
        f.addAction(act("Quit", self.close, "Ctrl+Q"))

        d = mb.addMenu("Device")
        d.addAction(act("Probe Drive", self._probe))
        d.addAction(act("Refresh",     self._scan_now))

        e = mb.addMenu("Emulator")
        e.addAction(act("Play",                self._play,               "Ctrl+Return"))
        e.addAction(act("Controller Setup…",   self._controller_settings,"Ctrl+Shift+C"))
        e.addAction(act("Diagnose…",           self._diagnose_emulator))
        e.addSeparator()
        e.addAction(act("Settings…",           self._settings))

        h = mb.addMenu("Help")
        h.addAction(act("Install Emulator (Mupen64Plus)", self._install_emulator))
        h.addSeparator()
        h.addAction(act("About", self._about))

    # ── Screen helpers ────────────────────────────────────────────────

    def _show(self, idx: int):
        self._stack.setCurrentIndex(idx)
        c, l = {
            self.S_SEARCH:  (TEXT_3, "Searching"),
            self.S_READING: (AMBER,  "Reading"),
            self.S_GAME:    (GREEN,  "Ready"),
        }.get(idx, (TEXT_3, ""))
        self._dot.set(c); self._status_lbl.setText(l)

    def _log(self, msg: str):
        logger.info(msg)
        self._log_lbl.setText(msg[:90] + "…" if len(msg) > 90 else msg)

    # ── Monitor ───────────────────────────────────────────────────────

    def _start_monitor(self):
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from src.hardware.device import DeviceManager
        except ImportError as e:
            self._log(f"Import error: {e}"); return

        self._mgr = DeviceManager()
        self._monitor = MonitorThread(self._mgr, self)
        self._monitor.state_changed.connect(self._on_state)
        self._monitor.start()
        self._log("N64 Operator v0.6.4 — waiting for DreamDump64…")

        # On startup, only check if drive is present — do NOT auto-read.
        # The ROM file may be stale from a previous cartridge.
        # A read is only triggered when the drive is freshly plugged in.
        QTimer.singleShot(800, self._check_drive_presence)

    def _check_drive_presence(self):
        """
        Startup-only check: just show whether the drive is connected.
        Does NOT read the ROM — that only happens on fresh plug-in or Refresh.
        """
        try:
            from src.hardware.device import _find_dreamdump64_drive, N64Device, DeviceState
        except ImportError:
            return
        if not self._mgr:
            return
        try:
            mount = _find_dreamdump64_drive()
        except Exception:
            mount = None

        if mount:
            with self._mgr._lock:
                self._mgr._device = N64Device(name="DreamDump64", mount_path=mount)
            self._log(f"Drive found: {mount} — unplug, swap cart, replug to load a game")
            self._s0.set_sub(
                f"DreamDump64 found at  {mount}\n"
                "Unplug, swap cartridge, plug back in — or click Refresh to read current cart."
            )
        else:
            self._log("No DreamDump64 drive found.")
            self._s0.set_sub(
                "Looking for DreamDump64…\n"
                "Plug it in with a cartridge inserted."
            )

    def _scan_now(self):
        """
        Refresh button — scan for drive AND read whatever ROM is currently on it.
        Use this when you've just plugged in with the cart you want to play.
        """
        try:
            from src.hardware.device import _find_dreamdump64_drive, N64Device, DeviceState
        except ImportError:
            return
        if not self._mgr:
            return
        try:
            mount = _find_dreamdump64_drive()
        except Exception:
            mount = None

        if not mount:
            self._log("No DreamDump64 drive found.")
            self._s0.set_sub(
                "DreamDump64 not found.\n"
                "Plug it in with a cartridge inserted, then click Refresh."
            )
            return

        with self._mgr._lock:
            self._mgr._device = N64Device(name="DreamDump64", mount_path=mount)

        rom = self._mgr._device.rom_path_any()
        if rom:
            self._log(f"Drive: {mount} — reading ROM…")
            self._trigger_load()
        else:
            self._log(f"Drive: {mount} — no ROM file yet")
            self._s0.set_sub(
                f"DreamDump64 at  {mount}\n"
                "No cartridge detected yet — insert one and click Refresh."
            )

    def _on_state(self, state, device):
        """Monitor loop callbacks — drive plug/unplug only."""
        try:
            from src.hardware.device import DeviceState
        except ImportError:
            return

        if state == DeviceState.DISCONNECTED:
            self._loading = False
            self._show(self.S_SEARCH)
            self._s0.set_sub("DreamDump64 disconnected.\nPlug it back in.")
            self._log("Drive disconnected.")

        elif state == DeviceState.CONNECTED:
            # Drive just freshly plugged in — wait for dump then read
            mount = str(device.mount_path) if device and device.mount_path else "?"
            self._log(f"Drive connected: {mount} — waiting for ROM dump…")
            self._show(self.S_SEARCH)
            self._s0.set_sub(
                f"DreamDump64 connected at  {mount}\n"
                "Waiting for cartridge dump to finish…"
            )
            # Poll until ROM file appears (device takes a few seconds to dump)
            QTimer.singleShot(3000, self._scan_now)

    def _trigger_load(self):
        """Start reading the ROM — guarded against double calls."""
        if self._loading:
            logger.debug("Already loading — ignoring duplicate trigger")
            return
        if self._stack.currentIndex() == self.S_GAME:
            logger.debug("Already showing game — ignoring trigger")
            return
        self._loading = True
        self._show(self.S_READING)
        self._start_load()

    def _start_load(self):
        if not self._mgr: return
        # Kill any previous load thread
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(1000)

        self._load_thread = LoadThread(self._mgr, self)
        self._load_thread.progress.connect(self._on_progress)
        self._load_thread.finished.connect(self._on_loaded)
        self._load_thread.error.connect(self._on_err)
        self._load_thread.start()

    def _on_progress(self, pct: float, label: str):
        self._s1.set_progress(pct, label)
        if label == "Waiting…":
            self._s1.set_sub("Waiting for cartridge dump to finish…")
        elif pct > 0:
            self._s1.set_sub("Reading from DreamDump64…")

    def _on_loaded(self, data: bytes):
        self._loading = False
        try:
            base = str(Path(__file__).parent.parent.parent)
            if base not in sys.path: sys.path.insert(0, base)
            from src.core.rom import load_rom_from_bytes
            from src.database.game_db import GameDatabase

            self._rom  = load_rom_from_bytes(data)
            db = GameDatabase(); db.load()
            h  = self._rom.header
            logger.info(
                f"ROM: title={h.title!r}  code={h.game_code!r}  "
                f"crc1=0x{h.crc1:08X}  {self._rom.size_mb:.0f}MB"
            )
            self._game = db.lookup_rom(self._rom)
            self._s2.load(self._rom, self._game)
            self._show(self.S_GAME)
            self._log(f"Loaded: {self._game.title}  [{h.game_code}]")

            # Fetch cover art in background
            db.fetch_cover_art(
                self._game,
                callback=lambda d: QTimer.singleShot(0, lambda: self._s2.set_cover(d))
            )
        except Exception as e:
            self._on_err(str(e))

    def _on_err(self, msg: str):
        self._loading = False
        self._log(f"Error: {msg}")
        QMessageBox.critical(self, "Load Error", msg)
        self._show(self.S_SEARCH)
        self._s0.set_sub(
            "Failed to read cartridge.\n"
            "Try ejecting and re-inserting it, then click Refresh."
        )

    # ── Actions ───────────────────────────────────────────────────────

    def _play(self):
        if not self._rom:
            return
        try:
            from src.emulator.mupen64plus import Mupen64PlusLauncher, EmulatorNotFoundError, BUNDLE_EXE
        except ImportError as e:
            QMessageBox.critical(self, "Error", str(e)); return

        launcher = Mupen64PlusLauncher()
        exe = launcher.find_executable()

        if not exe:
            self._install_emulator(); return

        title = self._game.title if self._game else "rom"
        self._log(f"Launching {title}…")

        # Save ROM to a permanent file in AppData — NO temp files, no GC issues
        import os, platform as _plat
        if _plat.system() == "Windows":
            rom_dir = Path(os.environ.get("APPDATA", Path.home())) / "N64Operator" / "roms"
        else:
            rom_dir = Path.home() / ".n64operator" / "roms"
        rom_dir.mkdir(parents=True, exist_ok=True)
        # Use identified game title for filename (may differ from what was loaded)
        game_title = (self._game.title if self._game else title)
        safe = "".join(c for c in game_title if c.isalnum() or c in " _-")[:40].strip()
        rom_path = rom_dir / f"{safe}.z64"

        try:
            rom_path.write_bytes(self._rom.data)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not write ROM file:\n{e}"); return

        import subprocess

        import subprocess
        # Write correct controller config, pass --configdir explicitly
        from src.ui.controller import ControllerDialog
        from src.emulator.mupen64plus import _write_n64_controller_config
        cfg_dir = exe.parent / 'config'
        cfg_dir.mkdir(exist_ok=True)
        saved_mode = ControllerDialog.get_saved_mode()
        if saved_mode == 'keyboard':
            _dlg = ControllerDialog(exe_dir=exe.parent)
            _dlg._write_keyboard_config(cfg_dir)
            logger.info('Using keyboard input mode')
        else:
            _write_n64_controller_config(cfg_dir)
            logger.info('Using USB controller input mode')

        cmd = [
            str(exe),
            '--configdir', str(cfg_dir),
            '--gfx', 'mupen64plus-video-glide64mk2',
            str(rom_path),
        ]
        self._log(f"Running: {exe.name}  {rom_path.name} [{saved_mode}]")

        def _do_launch():
            try:
                proc = subprocess.Popen(cmd, cwd=str(exe.parent))
                self._current_session = proc   # keep reference alive
                QTimer.singleShot(0, lambda: self._log(f"Playing: {title}"))
            except FileNotFoundError:
                msg = f"Executable not found:\n{exe}"
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Launch Error", msg))
            except Exception as e:
                err = str(e)
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Launch Error", err))

        threading.Thread(target=_do_launch, daemon=True).start()

    def _new_game(self):
        """Go back to searching. Tell user to unplug/replug for a new cart."""
        self._rom     = None
        self._game    = None
        self._loading = False
        self._poll_baseline = None
        self._show(self.S_SEARCH)
        self._s0.set_sub(
            "To load a different cartridge:\n"
            "1. Unplug the DreamDump64 from USB\n"
            "2. Swap the cartridge\n"
            "3. Plug it back in — it will dump & load automatically"
        )
        self._log("Unplug DreamDump64, swap cart, plug back in.")
        QTimer.singleShot(3000, self._poll_new_cart)

    def _poll_new_cart(self):
        """Poll every 2s watching for the ROM file on the drive to change."""
        if self._stack.currentIndex() != self.S_SEARCH:
            return   # Already moved on

        if not self._mgr or not self._mgr.device:
            # Drive gone — stop polling, monitor handles reconnect
            return

        rom = self._mgr.device.rom_path_any()
        if not rom:
            self._s0.set_sub(
                "No ROM file on drive yet.\n"
                "Insert a cartridge and wait for the device to dump it."
            )
            QTimer.singleShot(2000, self._poll_new_cart)
            return

        try:
            st  = rom.stat()
            cur = (round(st.st_mtime, 1), st.st_size)
        except OSError:
            QTimer.singleShot(2000, self._poll_new_cart)
            return

        if self._poll_baseline is None:
            # First read — record baseline
            self._poll_baseline = cur
            self._s0.set_sub(
                f"Drive has ROM ({cur[1]//(1024*1024)} MB) — waiting for new dump.\n"
                "Swap the cartridge now, then wait ~10 seconds."
            )
            QTimer.singleShot(2000, self._poll_new_cart)
        elif cur != self._poll_baseline:
            # File changed — new cart has been dumped
            mb = cur[1] // (1024 * 1024)
            self._log(f"New cartridge dump detected ({mb} MB) — reading…")
            self._poll_baseline = None
            self._trigger_load()
        else:
            # No change yet — keep waiting
            QTimer.singleShot(2000, self._poll_new_cart)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open N64 ROM", str(Path.home()),
            "N64 ROMs (*.z64 *.v64 *.n64);;All files (*.*)")
        if not path: return
        try:
            from src.core.rom import load_rom_from_file
            from src.database.game_db import GameDatabase
            self._rom  = load_rom_from_file(Path(path))
            db = GameDatabase(); db.load()
            self._game = db.lookup_rom(self._rom)
            self._s2.load(self._rom, self._game)
            self._show(self.S_GAME)
            self._log(f"Opened: {self._game.title}")
            db.fetch_cover_art(
                self._game,
                callback=lambda d: QTimer.singleShot(0, lambda: self._s2.set_cover(d))
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _save(self):
        if not self._rom: return
        name = (self._game.title if self._game else "rom").replace("/", "-") + ".z64"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ROM", str(Path.home() / name), "N64 ROM (*.z64)")
        if path:
            try:
                Path(path).write_bytes(self._rom.data)
                self._log(f"Saved: {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))

    def _probe(self):
        try:
            from src.hardware.device import DeviceManager
            r = DeviceManager().probe_device()
            lines = []
            dd = r.get("dreamdump64_drive")
            if dd:
                lines.append(f"★  DreamDump64: {dd}")
                for d in r.get("devices", []):
                    if d.get("rom_present"):
                        valid = "✓ valid" if d.get("rom_valid") else "✗ invalid magic"
                        lines.append(f"   ROM: {d.get('rom_size_mb','?')} MB  {valid}")
                    elif d.get("manufacturer") == "DreamDump64":
                        lines.append("   No ROM — insert a cartridge")
            else:
                lines.append("DreamDump64 not detected.")
            QMessageBox.information(self, "Device Probe", "\n".join(lines))
        except Exception as e:
            QMessageBox.warning(self, "Probe Error", str(e))

    def _not_working(self):
        QMessageBox.information(self, "Not Working?",
            "DreamDump64 not detected?\n\n"
            "1. Plug in the USB cable\n"
            "2. It should appear as a drive in File Explorer\n"
            "3. Insert a cartridge — the device dumps it (~5-10 sec)\n"
            "4. Click  ↻ Refresh  to scan again\n\n"
            "You can also open a ROM directly:\nFile → Open ROM File")

    def _install_emulator(self):
        from src.emulator.mupen64plus import Mupen64PlusLauncher
        launcher = Mupen64PlusLauncher()
        if launcher.is_available():
            QMessageBox.information(self, "Emulator Ready",
                f"Mupen64Plus is installed.\n\n"
                f"Location: {launcher.find_executable()}\n\n"
                "Click PLAY to start your game.")
            return
        if platform.system() != "Windows":
            QMessageBox.information(self, "Install Mupen64Plus",
                "macOS:  brew install mupen64plus\n"
                "Linux:  sudo apt install mupen64plus")
            return
        dlg = _InstallDialog(self); dlg.exec()
        if Mupen64PlusLauncher().is_available():
            self._log("Mupen64Plus ready — click PLAY!")

    def _diagnose_emulator(self):
        """Show exactly where the emulator is, whether it exists, and test-launch it."""
        import os, subprocess as sp, platform as _plat
        from src.emulator.mupen64plus import Mupen64PlusLauncher, BUNDLE_DIR, BUNDLE_EXE

        launcher = Mupen64PlusLauncher()
        exe      = launcher.find_executable()

        lines = ["=== EMULATOR DIAGNOSTIC ===", ""]

        # Exe location
        bundle_exe = BUNDLE_EXE.get(_plat.system())
        lines.append(f"Expected bundle path:")
        lines.append(f"  {bundle_exe}")
        lines.append(f"  Exists: {bundle_exe.exists() if bundle_exe else 'N/A'}")
        lines.append("")
        lines.append(f"find_executable() returned:")
        lines.append(f"  {exe}")
        lines.append(f"  Exists: {exe.exists() if exe else 'N/A'}")
        lines.append("")

        # Bundle dir contents
        if BUNDLE_DIR.exists():
            files = sorted(BUNDLE_DIR.iterdir())[:15]
            lines.append(f"Bundle dir ({BUNDLE_DIR}):")
            for f in files:
                lines.append(f"  {f.name}  ({f.stat().st_size//1024} KB)")
        else:
            lines.append(f"Bundle dir does not exist: {BUNDLE_DIR}")
        lines.append("")

        # ROM status
        if self._rom:
            import os as _os, platform as _plat2
            if _plat2.system() == "Windows":
                rom_dir = Path(_os.environ.get("APPDATA", Path.home())) / "N64Operator" / "roms"
            else:
                rom_dir = Path.home() / ".n64operator" / "roms"
            title = self._game.title if self._game else "rom"
            safe  = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
            rom_path = rom_dir / f"{safe}.z64"
            lines.append(f"ROM would be saved to:")
            lines.append(f"  {rom_path}")
            lines.append(f"  Dir exists: {rom_dir.exists()}")
        else:
            lines.append("No ROM loaded yet.")

        QMessageBox.information(self, "Emulator Diagnostic", "\n".join(lines))

    def _controller_settings(self):
        """Open the controller mapping dialog."""
        try:
            from src.ui.controller import ControllerDialog
            from src.emulator.mupen64plus import Mupen64PlusLauncher
            exe = Mupen64PlusLauncher().find_executable()
            exe_dir = exe.parent if exe else None
            dlg = ControllerDialog(self, exe_dir=exe_dir)
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Controller Settings", str(e))

    def _about(self):
        QMessageBox.about(self, "About N64 Operator",
            "<b>N64 Operator</b> v0.6.4<br><br>"
            "Nintendo 64 cartridge reader &amp; launcher.<br>"
            "Supports the DreamDump64 mass-storage dumper.<br><br>"
            f"Platform: {platform.system()} {platform.release()}")

    def _settings(self):
        try:
            from src.ui.settings import SettingsDialog
            dlg = SettingsDialog(self,
                game_code=getattr(self._game, "game_code", ""),
                game_codes=getattr(self._game, "gameshark_codes", []))
            dlg.exec()
        except Exception as e:
            QMessageBox.warning(self, "Settings", str(e))

    def closeEvent(self, e):
        if self._monitor: self._monitor.stop()
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.wait(2000)
        super().closeEvent(e)


# ── Install dialog ────────────────────────────────────────────────────────────

class _DownloadThread(QThread):
    progress = pyqtSignal(str, float)
    done     = pyqtSignal(bool)

    def run(self):
        from src.emulator.mupen64plus import download_mupen64plus
        ok = download_mupen64plus(
            progress_callback=lambda msg, pct: self.progress.emit(msg, pct))
        self.done.emit(ok)


class _InstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Install Emulator")
        self.setFixedSize(480, 300)
        self.setStyleSheet(STYLESHEET)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint)

        lay = QVBoxLayout(self); lay.setContentsMargins(32, 28, 32, 24); lay.setSpacing(0)

        self._head = QLabel("Install Mupen64Plus")
        self._head.setStyleSheet(f"color:{TEXT_1};font-size:18px;font-weight:700;")
        lay.addWidget(self._head); lay.addSpacing(8)

        self._sub = QLabel(
            "Mupen64Plus is the N64 emulator that powers playback.\n"
            "It will download from GitHub (~8 MB) and install automatically.")
        self._sub.setWordWrap(True)
        self._sub.setStyleSheet(f"color:{TEXT_2};font-size:12px;")
        lay.addWidget(self._sub); lay.addSpacing(28)

        self._bar = QProgressBar(); self._bar.setRange(0, 100); self._bar.setValue(0)
        self._bar.setFixedHeight(4); self._bar.setVisible(False)
        lay.addWidget(self._bar); lay.addSpacing(10)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{TEXT_3};font-size:11px;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._status); lay.addStretch()

        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.addStretch()

        self._cancel = QPushButton("Cancel"); self._cancel.setObjectName("sec")
        self._cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._cancel)

        self._install = QPushButton("Install"); self._install.setObjectName("play")
        self._install.clicked.connect(self._start)
        btn_row.addWidget(self._install)

        lay.addLayout(btn_row)
        self._thread = None

    def _start(self):
        self._install.setEnabled(False); self._install.setText("Installing…")
        self._cancel.setEnabled(False)
        self._bar.setVisible(True); self._bar.setValue(0)
        self._thread = _DownloadThread(self)
        self._thread.progress.connect(self._on_progress)
        self._thread.done.connect(self._on_done)
        self._thread.start()

    def _on_progress(self, msg: str, pct: float):
        self._bar.setValue(int(pct)); self._status.setText(msg)

    def _on_done(self, ok: bool):
        if ok:
            self._head.setText("Ready!")
            self._head.setStyleSheet(f"color:{GREEN};font-size:18px;font-weight:700;")
            self._sub.setText("Mupen64Plus installed.\nClick PLAY to launch your game.")
            self._bar.setValue(100); self._status.setText("")
            self._install.setText("Done  ✓"); self._install.setEnabled(True)
            self._install.clicked.disconnect(); self._install.clicked.connect(self.accept)
            self._cancel.setVisible(False)
        else:
            self._head.setText("Download Failed")
            self._head.setStyleSheet(f"color:{RED};font-size:18px;font-weight:700;")
            self._sub.setText(
                "Could not download Mupen64Plus.\n"
                "Check your internet connection and try again.")
            self._install.setText("Retry"); self._install.setEnabled(True)
            self._cancel.setEnabled(True)
