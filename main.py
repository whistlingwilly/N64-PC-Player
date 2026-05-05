"""
N64 Operator Playback — v0.6.4
Nintendo 64 Cartridge Reader & Launcher

Like Epilogue's GB/SN Operator, but for N64.
Just double-click and go.
"""

import sys
import os
import platform
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Platform tweaks before Qt starts ─────────────────────────────────────────
if platform.system() == "Windows":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "N64Operator.Playback.0.3"
        )
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass
elif platform.system() == "Darwin":
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")
elif platform.system() == "Linux":
    if "WAYLAND_DISPLAY" in os.environ and "QT_QPA_PLATFORM" not in os.environ:
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QCoreApplication

    QCoreApplication.setApplicationName("N64 Operator")
    QCoreApplication.setApplicationVersion("0.6.4")
    QCoreApplication.setOrganizationName("N64 Operator")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    if platform.system() == "Darwin":
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, True)

    from src.ui.playback import PlaybackWindow
    win = PlaybackWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
