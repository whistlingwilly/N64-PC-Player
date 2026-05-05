"""
N64 Operator - Controller Settings
====================================
Press-to-detect button mapping for ANY controller:
  - USB N64 adapters
  - Xbox controllers (XInput/SDL)
  - PlayStation controllers (DualShock/DualSense)
  - Generic USB gamepads
  - Keyboard

Uses pygame for real-time joystick event detection.
"""
from __future__ import annotations
import json, logging, os, platform, threading, time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore    import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui     import QKeySequence
from PyQt6.QtWidgets import (
    QDialog, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QFrame, QGridLayout, QScrollArea, QMessageBox,
    QRadioButton,
)

logger = logging.getLogger(__name__)

BG       = "#0D0D0F"
BG_SURF  = "#1E1E22"
BG_CARD  = "#161618"
BORDER   = "#2A2A2E"
BORD_MID = "#38383F"
TEXT_1   = "#EFEFEF"
TEXT_2   = "#88889A"
TEXT_3   = "#44445A"
GREEN    = "#3DDC84"
AMBER    = "#FFB84D"
RED      = "#FF5555"
BLUE     = "#4D9EFF"
_SANS    = '"Segoe UI",system-ui,sans-serif'

STYLE = f"""
QDialog, QWidget {{ background:{BG}; font-family:{_SANS}; color:{TEXT_1}; }}
QWidget {{ background:transparent; }}
QLabel  {{ background:transparent; }}
QComboBox {{
    background:{BG_SURF}; border:1px solid {BORD_MID}; border-radius:6px;
    color:{TEXT_1}; padding:7px 12px; font-size:12px; min-width:200px;
}}
QComboBox::drop-down {{ border:none; width:24px; }}
QComboBox QAbstractItemView {{
    background:{BG_SURF}; border:1px solid {BORD_MID}; color:{TEXT_1};
    selection-background-color:{BG_CARD};
}}
QRadioButton {{ color:{TEXT_2}; font-size:13px; spacing:8px; }}
QRadioButton::indicator {{
    width:16px; height:16px; border-radius:8px;
    border:2px solid {BORD_MID}; background:{BG_SURF};
}}
QRadioButton::indicator:checked {{ background:{GREEN}; border-color:{GREEN}; }}
QRadioButton:checked {{ color:{TEXT_1}; font-weight:600; }}
QPushButton#primary {{
    background:{TEXT_1}; color:{BG}; border:none; border-radius:8px;
    font-size:13px; font-weight:700; padding:12px 32px;
}}
QPushButton#primary:hover {{ background:#FFFFFF; }}
QPushButton#secondary {{
    background:transparent; border:1px solid {BORD_MID}; border-radius:7px;
    color:{TEXT_2}; font-size:11px; font-weight:600; padding:7px 14px;
}}
QPushButton#secondary:hover {{ background:{BG_SURF}; color:{TEXT_1}; }}
QPushButton#bind {{
    background:{BG_SURF}; border:1px solid {BORD_MID}; border-radius:6px;
    color:{TEXT_1}; font-size:11px; font-weight:600;
    padding:5px 8px; min-width:100px; text-align:center;
}}
QPushButton#bind:hover {{ border-color:#555560; background:{BG_CARD}; }}
QPushButton#bind[state="listening"] {{
    background:{BLUE}18; border:1.5px solid {BLUE}; color:{BLUE}; font-weight:700;
}}
QPushButton#bind[state="bound"] {{
    background:{GREEN}12; border:1px solid {GREEN}44; color:{GREEN};
}}
QPushButton#bind[state="unbound"] {{ color:{TEXT_3}; border-color:{BORDER}; }}
QScrollBar:vertical {{ background:transparent; width:5px; }}
QScrollBar::handle:vertical {{ background:{BORD_MID}; border-radius:2px; min-height:24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
"""

# ── N64 button definitions ────────────────────────────────────────────────────
N64_BUTTONS = [
    ("A Button",   "A",        "Face"),
    ("B Button",   "B",        "Face"),
    ("Start",      "START",    "Face"),
    ("Z Trig",     "Z",        "Face"),
    ("L Trig",     "L",        "Triggers"),
    ("R Trig",     "R",        "Triggers"),
    ("DPad U",     "D-Up",     "D-Pad"),
    ("DPad D",     "D-Down",   "D-Pad"),
    ("DPad L",     "D-Left",   "D-Pad"),
    ("DPad R",     "D-Right",  "D-Pad"),
    ("C Button U", "C-Up",     "C-Buttons"),
    ("C Button D", "C-Down",   "C-Buttons"),
    ("C Button L", "C-Left",   "C-Buttons"),
    ("C Button R", "C-Right",  "C-Buttons"),
    ("X Axis",     "Stick ←→", "Analog"),
    ("Y Axis",     "Stick ↑↓", "Analog"),
]
GROUPS = ["Face", "Triggers", "D-Pad", "C-Buttons", "Analog"]

# Built-in presets
DEFAULT_USB_N64 = {
    "A Button":"button(5)", "B Button":"button(4)",
    "Start":"button(9)", "Z Trig":"button(8)",
    "L Trig":"button(6)", "R Trig":"button(7)",
    "DPad U":"hat(0 Up)", "DPad D":"hat(0 Down)",
    "DPad L":"hat(0 Left)", "DPad R":"hat(0 Right)",
    "C Button U":"button(0)", "C Button D":"button(2)",
    "C Button L":"button(3)", "C Button R":"button(1)",
    "X Axis":"axis(0-,0+)", "Y Axis":"axis(1-,1+)",
}
DEFAULT_XBOX = {
    "A Button":"button(0)", "B Button":"button(1)",
    "Start":"button(7)", "Z Trig":"axis(4+)",
    "L Trig":"button(4)", "R Trig":"button(5)",
    "DPad U":"hat(0 Up)", "DPad D":"hat(0 Down)",
    "DPad L":"hat(0 Left)", "DPad R":"hat(0 Right)",
    "C Button U":"axis(3-)", "C Button D":"axis(3+)",
    "C Button L":"axis(2-)", "C Button R":"axis(2+)",
    "X Axis":"axis(0-,0+)", "Y Axis":"axis(1-,1+)",
}
DEFAULT_PS = {
    "A Button":"button(1)", "B Button":"button(0)",
    "Start":"button(9)", "Z Trig":"axis(4+)",
    "L Trig":"button(4)", "R Trig":"button(5)",
    "DPad U":"hat(0 Up)", "DPad D":"hat(0 Down)",
    "DPad L":"hat(0 Left)", "DPad R":"hat(0 Right)",
    "C Button U":"axis(3-)", "C Button D":"axis(3+)",
    "C Button L":"axis(2-)", "C Button R":"axis(2+)",
    "X Axis":"axis(0-,0+)", "Y Axis":"axis(1-,1+)",
}
DEFAULT_KEYBOARD = {
    "A Button":"key(x)", "B Button":"key(z)",
    "Start":"key(Return)", "Z Trig":"key(shift)",
    "L Trig":"key(a)", "R Trig":"key(s)",
    "DPad U":"key(Up)", "DPad D":"key(Down)",
    "DPad L":"key(Left)", "DPad R":"key(Right)",
    "C Button U":"key(i)", "C Button D":"key(k)",
    "C Button L":"key(j)", "C Button R":"key(l)",
    "X Axis":"key(276) key(275)", "Y Axis":"key(273) key(274)",
}


def _display(val: str) -> str:
    if not val: return "— unbound —"
    v = val.strip()
    if v.startswith("button(") and v.endswith(")"): return f"Btn {v[7:-1]}"
    if v.startswith("axis("):
        inner = v[5:-1]
        if "," in inner:
            ax = inner.split(",")[0].rstrip("+-")
            return f"Axis {ax}"
        return f"Axis {inner}"
    if v.startswith("hat("):
        parts = v[4:-1].split()
        return f"Hat {parts[1]}" if len(parts) > 1 else "Hat"
    if v.startswith("key(") and v.endswith(")"): return v[4:-1].upper()
    return v


def _detect_type(name: str) -> str:
    n = name.lower()
    if any(x in n for x in ["xbox","xinput","x-box","microsoft"]): return "xbox"
    if any(x in n for x in ["playstation","dualshock","dualsense","ps4","ps5","sony"]): return "ps"
    if any(x in n for x in ["n64","nintendo 64","retrolink","mayflash"]): return "n64"
    return "generic"


def _list_joysticks() -> list[tuple[int,str]]:
    try:
        import pygame
        if not pygame.get_init(): pygame.init()
        pygame.joystick.quit(); pygame.joystick.init()
        return [(i, pygame.joystick.Joystick(i).get_name())
                for i in range(pygame.joystick.get_count())]
    except Exception:
        return []


# ── Background detector ───────────────────────────────────────────────────────

class JoystickDetector(QObject):
    detected = pyqtSignal(str)
    error    = pyqtSignal(str)
    DEAD     = 0.55

    def __init__(self):
        super().__init__()
        self._active = False

    def start(self, joy_index: int = 0):
        self._active = True
        self._idx    = joy_index
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def stop(self): self._active = False

    def _run(self):
        try:
            import pygame
            if not pygame.get_init(): pygame.init()
            if not pygame.joystick.get_init(): pygame.joystick.init()
            n = pygame.joystick.get_count()
            if n == 0:
                self.error.emit("No controller detected. Plug it in and click ⟳ Refresh.")
                return
            joy = pygame.joystick.Joystick(min(self._idx, n-1))
            joy.init()
            pygame.event.pump()
            baseline = {i: joy.get_axis(i) for i in range(joy.get_numaxes())}
            deadline = time.time() + 15
            while self._active and time.time() < deadline:
                pygame.event.pump()
                for i in range(joy.get_numbuttons()):
                    if joy.get_button(i):
                        self.detected.emit(f"button({i})"); return
                for i in range(joy.get_numhats()):
                    h = joy.get_hat(i)
                    m = {(0,1):"Up",(0,-1):"Down",(-1,0):"Left",(1,0):"Right"}.get(h)
                    if m: self.detected.emit(f"hat({i} {m})"); return
                for i in range(joy.get_numaxes()):
                    v = joy.get_axis(i) - baseline.get(i, 0)
                    if v >  self.DEAD: self.detected.emit(f"axis({i}+)"); return
                    if v < -self.DEAD: self.detected.emit(f"axis({i}-)"); return
                time.sleep(0.02)
            if self._active:
                self.error.emit("Timed out. No input detected.")
        except ImportError:
            self.error.emit("pygame not installed — run run.bat to install it.")
        except Exception as e:
            self.error.emit(str(e))


# ── Bind button ───────────────────────────────────────────────────────────────

class BindButton(QPushButton):
    bind_requested = pyqtSignal(str)

    def __init__(self, n64_key: str, val: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("bind")
        self._key = n64_key
        self._val = val
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh()
        self.clicked.connect(lambda: self.bind_requested.emit(self._key))

    def set_value(self, val: str):
        self._val = val; self._refresh()

    def get_value(self) -> str: return self._val

    def set_listening(self, on: bool):
        if on:
            self.setText("▶  Press now…")
            self.setProperty("state", "listening")
        else:
            self._refresh()
        self.setStyle(self.style())

    def _refresh(self):
        self.setText(_display(self._val))
        self.setProperty("state", "bound" if self._val else "unbound")
        self.setStyle(self.style())


# ── Main dialog ───────────────────────────────────────────────────────────────

class ControllerDialog(QDialog):

    def __init__(self, parent=None, exe_dir: Optional[Path] = None):
        super().__init__(parent)
        self._exe_dir  = exe_dir
        self._prefs    = self._load_prefs()
        self._mode     = self._prefs.get("mode", "usb")
        self._joy_idx  = self._prefs.get("joy_index", 0)
        self._bindings : dict[str,str] = {}
        self._bind_btns: dict[str,BindButton] = {}
        self._detector : Optional[JoystickDetector] = None
        self._listen_key: Optional[str] = None

        self.setWindowTitle("Controller Settings")
        self.setMinimumSize(620, 700)
        self.setStyleSheet(STYLE)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint)

        self._build_ui()
        self._load_bindings_for_mode()
        self._rebuild_grid()
        self._refresh_joy_list()
        self._update_mode_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _div(self):
        f = QFrame(); f.setFrameShape(QFrame.Shape.HLine)
        f.setStyleSheet(
            f"border:none;border-top:1px solid {BORDER};background:transparent;")
        f.setMaximumHeight(1); return f

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20); lay.setSpacing(0)

        # Header
        t = QLabel("Controller Settings")
        t.setStyleSheet(f"color:{TEXT_1};font-size:18px;font-weight:700;")
        lay.addWidget(t); lay.addSpacing(4)
        s = QLabel("Map any controller to N64 buttons. "
                   "Click a slot then press the matching button on your device.")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{TEXT_2};font-size:12px;")
        lay.addWidget(s); lay.addSpacing(18)
        lay.addWidget(self._div()); lay.addSpacing(14)

        # Mode
        ml = QLabel("INPUT METHOD")
        ml.setStyleSheet(
            f"color:{TEXT_3};font-size:9px;font-weight:700;letter-spacing:1.5px;")
        lay.addWidget(ml); lay.addSpacing(8)
        mr = QHBoxLayout(); mr.setSpacing(10)
        self._rb_usb = QRadioButton("USB / Gamepad")
        self._rb_kbd = QRadioButton("Keyboard")
        for rb in (self._rb_usb, self._rb_kbd):
            c = QFrame()
            c.setStyleSheet(
                f"QFrame{{background:{BG_SURF};border:1px solid {BORD_MID};"
                f"border-radius:8px;padding:2px;}}")
            cl = QHBoxLayout(c); cl.setContentsMargins(14,8,14,8); cl.addWidget(rb)
            mr.addWidget(c)
        mr.addStretch()
        self._rb_usb.setChecked(self._mode == "usb")
        self._rb_kbd.setChecked(self._mode == "keyboard")
        self._rb_usb.toggled.connect(self._on_mode_changed)
        lay.addLayout(mr); lay.addSpacing(12)

        # Controller picker (USB only)
        self._ctrl_panel = QWidget()
        cp = QHBoxLayout(self._ctrl_panel)
        cp.setContentsMargins(0,0,0,0); cp.setSpacing(8)
        cp.addWidget(QLabel("Controller:"))
        self._joy_combo = QComboBox()
        self._joy_combo.currentIndexChanged.connect(self._on_joy_changed)
        cp.addWidget(self._joy_combo)
        ref = QPushButton("⟳"); ref.setObjectName("secondary")
        ref.setFixedWidth(36); ref.setToolTip("Refresh controller list")
        ref.clicked.connect(self._refresh_joy_list)
        cp.addWidget(ref)
        cp.addSpacing(12)
        pl = QLabel("Presets:")
        pl.setStyleSheet(f"color:{TEXT_2};font-size:12px;")
        cp.addWidget(pl)
        for lbl, dflt in [("N64 adapter", DEFAULT_USB_N64),
                           ("Xbox",        DEFAULT_XBOX),
                           ("PlayStation", DEFAULT_PS)]:
            b = QPushButton(lbl); b.setObjectName("secondary")
            b.clicked.connect(lambda _, d=dflt: self._apply_preset(d))
            cp.addWidget(b)
        cp.addStretch()
        lay.addWidget(self._ctrl_panel); lay.addSpacing(10)

        # Status hint
        self._hint = QLabel("Click any button slot to start mapping.")
        self._hint.setStyleSheet(
            f"background:{BG_SURF};color:{TEXT_2};font-size:11px;"
            f"padding:7px 14px;border-radius:6px;border:1px solid {BORDER};")
        lay.addWidget(self._hint); lay.addSpacing(12)
        lay.addWidget(self._div()); lay.addSpacing(10)

        # Binding grid (scrollable)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self._grid_host = QWidget()
        self._grid_lay  = QVBoxLayout(self._grid_host)
        self._grid_lay.setContentsMargins(0,0,0,0); self._grid_lay.setSpacing(14)
        scroll.setWidget(self._grid_host)
        lay.addWidget(scroll, 1)
        lay.addSpacing(12); lay.addWidget(self._div()); lay.addSpacing(14)

        # Bottom buttons
        bot = QHBoxLayout(); bot.setSpacing(10)
        clr = QPushButton("Clear All"); clr.setObjectName("secondary")
        clr.clicked.connect(self._clear_all); bot.addWidget(clr)
        bot.addStretch()
        can = QPushButton("Cancel"); can.setObjectName("secondary")
        can.clicked.connect(self.reject); bot.addWidget(can)
        sav = QPushButton("Save && Apply"); sav.setObjectName("primary")
        sav.clicked.connect(self._save); bot.addWidget(sav)
        lay.addLayout(bot)

    def _rebuild_grid(self):
        while self._grid_lay.count():
            item = self._grid_lay.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._bind_btns.clear()

        for group in GROUPS:
            items = [(k,d) for k,d,g in N64_BUTTONS if g == group]
            if not items: continue
            hdr = QLabel(group.upper())
            hdr.setStyleSheet(
                f"color:{TEXT_3};font-size:9px;font-weight:700;letter-spacing:1.2px;")
            self._grid_lay.addWidget(hdr)
            gw = QWidget(); grid = QGridLayout(gw)
            grid.setContentsMargins(0,0,0,0); grid.setSpacing(6)
            for i,(k,d) in enumerate(items):
                row,col = divmod(i,2)
                cell = QWidget(); cl = QHBoxLayout(cell)
                cl.setContentsMargins(0,0,0,0); cl.setSpacing(8)
                lbl = QLabel(d); lbl.setFixedWidth(80)
                lbl.setStyleSheet(f"color:{TEXT_2};font-size:12px;")
                cl.addWidget(lbl)
                bb = BindButton(k, self._bindings.get(k,""))
                bb.bind_requested.connect(self._on_bind_requested)
                cl.addWidget(bb); cl.addStretch()
                grid.addWidget(cell, row, col)
                self._bind_btns[k] = bb
            self._grid_lay.addWidget(gw)
        self._grid_lay.addStretch()

    # ── Mode / device ─────────────────────────────────────────────────────────

    def _update_mode_ui(self):
        usb = self._mode == "usb"
        self._ctrl_panel.setVisible(usb)
        if usb:
            self._hint.setText("Click a slot, then press the matching button on your controller.")
            self._hint.setStyleSheet(
                f"background:{BG_SURF};color:{TEXT_2};font-size:11px;"
                f"padding:7px 14px;border-radius:6px;border:1px solid {BORDER};")
        else:
            self._hint.setText(
                "Keyboard mode: click a slot, then press a key.  Esc = cancel.")
            self._hint.setStyleSheet(
                f"background:{AMBER}18;color:{AMBER};font-size:11px;"
                f"padding:7px 14px;border-radius:6px;border:1px solid {AMBER}44;")

    def _on_mode_changed(self):
        self._stop(); self._mode = "usb" if self._rb_usb.isChecked() else "keyboard"
        self._load_bindings_for_mode(); self._rebuild_grid(); self._update_mode_ui()

    def _refresh_joy_list(self):
        self._joy_combo.blockSignals(True); self._joy_combo.clear()
        joys = _list_joysticks()
        if not joys:
            self._joy_combo.addItem("No controllers detected", -1)
        else:
            for idx,name in joys:
                ct   = _detect_type(name)
                icon = {"xbox":"Xbox","ps":"PlayStation","n64":"N64 Adapter"}.get(ct,"Gamepad")
                self._joy_combo.addItem(f"🎮  {name}  ({icon})", idx)
                if not self._prefs.get("bindings_usb"):
                    if ct == "xbox": self._apply_preset(DEFAULT_XBOX)
                    elif ct == "ps": self._apply_preset(DEFAULT_PS)
            for i in range(self._joy_combo.count()):
                if self._joy_combo.itemData(i) == self._joy_idx:
                    self._joy_combo.setCurrentIndex(i); break
        self._joy_combo.blockSignals(False)

    def _on_joy_changed(self, i: int):
        d = self._joy_combo.itemData(i)
        if d is not None and d >= 0: self._joy_idx = d

    # ── Binding ───────────────────────────────────────────────────────────────

    def _on_bind_requested(self, n64_key: str):
        self._stop()
        self._listen_key = n64_key
        self._bind_btns[n64_key].set_listening(True)
        display = next((d for k,d,_ in N64_BUTTONS if k==n64_key), n64_key)
        if self._mode == "keyboard":
            self._set_hint(f"Press a key for  '{display}'…  (Esc = cancel)", BLUE)
            self.setFocus()
        else:
            self._set_hint(f"Press a button on your controller for  '{display}'…", BLUE)
            self._detector = JoystickDetector()
            self._detector.detected.connect(self._on_detected)
            self._detector.error.connect(self._on_det_error)
            self._detector.start(self._joy_idx)

    def _on_detected(self, val: str):
        if not self._listen_key: return
        k = self._listen_key
        # For analog sticks: expand single direction to bidirectional
        if "Axis" in k and val.startswith("axis(") and "," not in val:
            ax = val[5:-1].rstrip("+-")
            val = f"axis({ax}-,{ax}+)"
        self._bindings[k] = val
        self._bind_btns[k].set_value(val)
        d = next((dn for kn,dn,_ in N64_BUTTONS if kn==k), k)
        self._stop()
        self._set_hint(f"✓  '{d}' mapped to {_display(val)}   Click another slot to continue.", GREEN)

    def _on_det_error(self, msg: str):
        self._stop()
        self._set_hint(f"⚠  {msg}", RED)

    def _stop(self):
        if self._detector: self._detector.stop(); self._detector = None
        if self._listen_key:
            bb = self._bind_btns.get(self._listen_key)
            if bb: bb.set_listening(False)
            self._listen_key = None

    def keyPressEvent(self, ev):
        if self._mode == "keyboard" and self._listen_key:
            if ev.key() == Qt.Key.Key_Escape:
                self._stop()
                self._set_hint("Cancelled.", TEXT_2); return
            ks = QKeySequence(ev.key()).toString().lower()
            if ks and ks not in ("","unknown","meta"):
                k = self._listen_key
                self._bindings[k] = f"key({ks})"
                self._bind_btns[k].set_value(f"key({ks})")
                d = next((dn for kn,dn,_ in N64_BUTTONS if kn==k), k)
                self._stop()
                self._set_hint(f"✓  '{d}' mapped to {ks.upper()}   Click another slot to continue.", GREEN)
            return
        super().keyPressEvent(ev)

    def _set_hint(self, msg: str, color: str = TEXT_2):
        self._hint.setText(msg)
        bg = f"{color}14" if color not in (TEXT_2,TEXT_3) else BG_SURF
        border = f"{color}44" if color not in (TEXT_2,TEXT_3) else BORDER
        self._hint.setStyleSheet(
            f"background:{bg};color:{color};font-size:11px;"
            f"padding:7px 14px;border-radius:6px;border:1px solid {border};")

    # ── Presets / clear ───────────────────────────────────────────────────────

    def _apply_preset(self, d: dict):
        self._bindings = dict(d)
        for k,bb in self._bind_btns.items(): bb.set_value(self._bindings.get(k,""))

    def _clear_all(self):
        self._bindings = {}
        for bb in self._bind_btns.values(): bb.set_value("")

    # ── Load / save bindings ──────────────────────────────────────────────────

    def _load_bindings_for_mode(self):
        saved = self._prefs.get(f"bindings_{self._mode}", {})
        if saved:
            self._bindings = saved; return
        if self._mode == "keyboard":
            self._bindings = dict(DEFAULT_KEYBOARD); return
        joys = _list_joysticks()
        if joys:
            ct = _detect_type(joys[0][1])
            self._bindings = {
                "xbox": DEFAULT_XBOX, "ps": DEFAULT_PS
            }.get(ct, DEFAULT_USB_N64)
        else:
            self._bindings = dict(DEFAULT_USB_N64)

    # ── Write Mupen config ────────────────────────────────────────────────────

    def _save(self):
        self._stop(); self._save_prefs()
        if self._exe_dir:
            cfg_dir = self._exe_dir / "config"
            cfg_dir.mkdir(exist_ok=True)
            if self._mode == "keyboard":
                self._write_keyboard_config(cfg_dir)
            else:
                joys     = _list_joysticks()
                joy_name = (joys[self._joy_idx][1]
                            if joys and self._joy_idx < len(joys)
                            else "USB Joystick")
                self._write_usb_config(cfg_dir, joy_name)
        QMessageBox.information(self, "Saved",
            "Controller settings saved.\nTake effect on next PLAY.")
        self.accept()

    def _cfg_block(self, b: dict, device: int) -> str:
        def v(k): return b.get(k,"")
        return (
            "[Input-SDL-Control1]\r\n"
            "version = 2\r\nplugged = True\r\nplugin = 2\r\nmouse = False\r\n"
            f"device = {device}\r\n"
            "AnalogDeadzone = \"4096,4096\"\r\nAnalogPeak = \"32768,32768\"\r\n"
            f"DPad R = \"{v('DPad R')}\"\r\nDPad L = \"{v('DPad L')}\"\r\n"
            f"DPad D = \"{v('DPad D')}\"\r\nDPad U = \"{v('DPad U')}\"\r\n"
            f"Start = \"{v('Start')}\"\r\nZ Trig = \"{v('Z Trig')}\"\r\n"
            f"B Button = \"{v('B Button')}\"\r\nA Button = \"{v('A Button')}\"\r\n"
            f"C Button R = \"{v('C Button R')}\"\r\nC Button L = \"{v('C Button L')}\"\r\n"
            f"C Button D = \"{v('C Button D')}\"\r\nC Button U = \"{v('C Button U')}\"\r\n"
            f"R Trig = \"{v('R Trig')}\"\r\nL Trig = \"{v('L Trig')}\"\r\n"
            "Mempak switch = \"\"\r\nRumblepak switch = \"\"\r\n"
            f"X Axis = \"{v('X Axis')}\"\r\nY Axis = \"{v('Y Axis')}\"\r\n"
            "\r\n[Input-SDL-Control2]\r\nversion = 2\r\nplugged = False\r\n"
            "plugin = 1\r\nmouse = False\r\ndevice = -1\r\n"
            "\r\n[Input-SDL-Control3]\r\nversion = 2\r\nplugged = False\r\n"
            "plugin = 1\r\nmouse = False\r\ndevice = -1\r\n"
            "\r\n[Input-SDL-Control4]\r\nversion = 2\r\nplugged = False\r\n"
            "plugin = 1\r\nmouse = False\r\ndevice = -1\r\n"
        )

    def _write_usb_config(self, cfg_dir: Path, joy_name: str):
        b = self._bindings

        def v(k): return b.get(k,"")
        # InputAutoCfg.ini — maps joystick NAME to buttons
        autocfg = (
            f"; N64 Operator controller config\r\n"
            f"[{joy_name}]\r\n"
            f"plugged = True\r\nplugin = 2\r\nmouse = False\r\n"
            f"AnalogDeadzone = \"4096,4096\"\r\nAnalogPeak = \"32768,32768\"\r\n"
            f"DPad R = \"{v('DPad R')}\"\r\nDPad L = \"{v('DPad L')}\"\r\n"
            f"DPad D = \"{v('DPad D')}\"\r\nDPad U = \"{v('DPad U')}\"\r\n"
            f"Start = \"{v('Start')}\"\r\nZ Trig = \"{v('Z Trig')}\"\r\n"
            f"B Button = \"{v('B Button')}\"\r\nA Button = \"{v('A Button')}\"\r\n"
            f"C Button R = \"{v('C Button R')}\"\r\nC Button L = \"{v('C Button L')}\"\r\n"
            f"C Button D = \"{v('C Button D')}\"\r\nC Button U = \"{v('C Button U')}\"\r\n"
            f"R Trig = \"{v('R Trig')}\"\r\nL Trig = \"{v('L Trig')}\"\r\n"
            f"Mempak switch = \"\"\r\nRumblepak switch = \"\"\r\n"
            f"X Axis = \"{v('X Axis')}\"\r\nY Axis = \"{v('Y Axis')}\"\r\n"
        )
        try:
            (cfg_dir/"InputAutoCfg.ini").write_bytes(
                autocfg.encode("ascii","replace"))
            logger.info(f"InputAutoCfg.ini written for '{joy_name}'")
        except Exception as e:
            logger.warning(f"InputAutoCfg.ini write failed: {e}")

        self._write_cfg_file(cfg_dir, self._cfg_block(b, device=0))

    def _write_keyboard_config(self, cfg_dir: Path):
        b = self._bindings
        self._write_cfg_file(cfg_dir, self._cfg_block(b, device=-1))

    def _write_cfg_file(self, cfg_dir: Path, block: str):
        cfg_path = cfg_dir / "mupen64plus.cfg"
        try:
            existing = ""
            if cfg_path.exists():
                lines = []; skip = False
                for line in cfg_path.read_text(errors="replace").splitlines():
                    s = line.strip()
                    if s.startswith("["):
                        skip = s.startswith("[Input-SDL-Control")
                    if not skip:
                        lines.append(line)
                existing = "\r\n".join(lines).rstrip() + "\r\n\r\n"
            cfg_path.write_bytes(
                (existing + block).encode("ascii","replace"))
            logger.info(f"mupen64plus.cfg written: {cfg_path}")
        except Exception as e:
            logger.warning(f"mupen64plus.cfg write failed: {e}")

    # ── Prefs ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _prefs_path() -> Path:
        if platform.system() == "Windows":
            d = Path(os.environ.get("APPDATA", Path.home())) / "N64Operator"
        else:
            d = Path.home() / ".n64operator"
        d.mkdir(parents=True, exist_ok=True)
        return d / "controller_prefs.json"

    def _load_prefs(self) -> dict:
        try: return json.loads(self._prefs_path().read_text())
        except: return {}

    def _save_prefs(self):
        try:
            p = self._prefs_path()
            try: ex = json.loads(p.read_text())
            except: ex = {}
            ex["mode"] = self._mode
            ex["joy_index"] = self._joy_idx
            ex[f"bindings_{self._mode}"] = self._bindings
            p.write_text(json.dumps(ex, indent=2))
        except Exception as e:
            logger.warning(f"Prefs save failed: {e}")

    @staticmethod
    def get_saved_mode() -> str:
        try:
            if platform.system() == "Windows":
                p = Path(os.environ.get("APPDATA",Path.home())) / \
                    "N64Operator" / "controller_prefs.json"
            else:
                p = Path.home() / ".n64operator" / "controller_prefs.json"
            return json.loads(p.read_text()).get("mode","usb")
        except: return "usb"

    def closeEvent(self, e):
        self._stop(); super().closeEvent(e)
