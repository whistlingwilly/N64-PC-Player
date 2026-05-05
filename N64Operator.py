"""
N64 Operator — Self-Bootstrapping Launcher  v0.6.4
====================================================

Double-click this file. That's it.

First run:
  1. Creates a private Python environment (.n64op_env/)
  2. Installs PyQt6 and other dependencies silently
  3. Downloads Mupen64Plus automatically (Windows)
  4. Launches the app

Every run after: launches instantly.
No terminal. No setup. No installing anything manually.
"""

import sys, os, subprocess, threading
from pathlib import Path

APP_DIR  = Path(__file__).parent.resolve()
VENV_DIR = APP_DIR / ".n64op_env"
MARKER   = VENV_DIR / ".ready"

REQUIRED_PACKAGES = [
    "PyQt6>=6.6.0",
    "pyusb>=1.2.1",
    "requests>=2.28.0",
    "Pillow>=10.6.4",
]

def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"

def _in_venv() -> bool:
    return (str(VENV_DIR) in sys.executable or
            str(VENV_DIR) in os.environ.get("VIRTUAL_ENV", ""))

def _ready() -> bool:
    return MARKER.exists() and _venv_python().exists()


# ── Already set up → re-exec inside venv immediately ─────────────────────────
if _ready() and not _in_venv():
    os.execv(str(_venv_python()), [str(_venv_python()), __file__] + sys.argv[1:])


# ── Running inside venv → launch the Qt app ───────────────────────────────────
if _in_venv() or _ready():
    try:
        import platform as _plat
        if _plat.system() == "Windows":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "N64Operator.Playback.0.3")
                try:    ctypes.windll.shcore.SetProcessDpiAwareness(2)
                except: ctypes.windll.user32.SetProcessDPIAware()
            except: pass
        elif _plat.system() == "Darwin":
            os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

        sys.path.insert(0, str(APP_DIR))
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt, QCoreApplication
        QCoreApplication.setApplicationName("N64 Operator")
        QCoreApplication.setApplicationVersion("0.6.4")
        QCoreApplication.setOrganizationName("N64 Operator")
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(sys.argv)
        from src.ui.playback import PlaybackWindow
        win = PlaybackWindow(); win.show()
        sys.exit(app.exec())

    except Exception as e:
        if MARKER.exists(): MARKER.unlink()
        try:
            import tkinter as tk; from tkinter import messagebox
            tk.Tk().withdraw()
            messagebox.showerror("N64 Operator — Error",
                f"Failed to launch:\n\n{e}\n\n"
                "Delete the .n64op_env folder next to this file and try again.")
        except: input(f"Error: {e}\nPress Enter.")
        sys.exit(1)


# ── First run — show splash + install everything in background ────────────────
import tkinter as tk
from tkinter import ttk
import math

BG     = "#0D0D0F"
BG_BAR = "#111114"
TEXT_1 = "#EFEFEF"
TEXT_2 = "#88889A"
TEXT_3 = "#44445A"
GREEN  = "#3DDC84"
RED    = "#FF5555"


class SplashApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("N64 Operator")
        self.root.geometry("440x540")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth()  - 440) // 2
        y = (self.root.winfo_screenheight() - 540) // 2
        self.root.geometry(f"440x540+{x}+{y}")

        # Title bar strip
        tk.Label(self.root, text="● N64 Operator", bg=BG_BAR, fg=TEXT_2,
                 font=("Segoe UI", 10, "bold"), anchor="w",
                 padx=16, pady=12).pack(fill="x")
        tk.Frame(self.root, bg="#2A2A2E", height=1).pack(fill="x")

        tk.Frame(self.root, bg=BG, height=50).pack(fill="x")

        # Animated dots
        dots_frame = tk.Frame(self.root, bg=BG); dots_frame.pack()
        self._dots = []
        for _ in range(3):
            l = tk.Label(dots_frame, text="●", bg=BG, fg=TEXT_3, font=("Segoe UI", 14))
            l.pack(side="left", padx=8)
            self._dots.append(l)
        self._dot_phase = 0

        tk.Frame(self.root, bg=BG, height=28).pack(fill="x")

        self._heading = tk.Label(self.root, text="Setting up…", bg=BG, fg=TEXT_1,
                                  font=("Segoe UI", 22, "bold"))
        self._heading.pack()

        tk.Frame(self.root, bg=BG, height=12).pack(fill="x")

        self._status = tk.StringVar(value="Preparing…")
        tk.Label(self.root, textvariable=self._status, bg=BG, fg=TEXT_2,
                 font=("Segoe UI", 11), wraplength=380, justify="center").pack(padx=20)

        tk.Frame(self.root, bg=BG, height=24).pack(fill="x")

        style = ttk.Style(); style.theme_use("default")
        style.configure("Dark.Horizontal.TProgressbar",
                         background=TEXT_1, troughcolor="#1E1E22",
                         bordercolor=BG, lightcolor=TEXT_1, darkcolor=TEXT_1, thickness=4)
        self._bar = ttk.Progressbar(self.root, style="Dark.Horizontal.TProgressbar",
                                     mode="indeterminate", length=320)
        self._bar.pack(); self._bar.start(12)

        tk.Frame(self.root, bg=BG, height=10).pack(fill="x")

        self._pct = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self._pct, bg=BG, fg=TEXT_3,
                 font=("Segoe UI", 10)).pack()

        tk.Frame(self.root, bg=BG, height=60).pack(fill="x")

        self._hint = tk.Label(self.root, text="This only happens once — future launches are instant.",
                               bg=BG, fg=TEXT_3, font=("Segoe UI", 10))
        self._hint.pack()

        self._animate_dots()
        threading.Thread(target=self._run_setup, daemon=True).start()

    def _animate_dots(self):
        for i, d in enumerate(self._dots):
            d.config(fg=TEXT_1 if i == self._dot_phase else TEXT_3)
        self._dot_phase = (self._dot_phase + 1) % 3
        self.root.after(400, self._animate_dots)

    def _set(self, msg, pct=""):
        self.root.after(0, lambda: self._status.set(msg))
        self.root.after(0, lambda: self._pct.set(pct))

    def _set_bar(self, val):
        def _do():
            self._bar.stop()
            self._bar.config(mode="determinate", value=val)
        self.root.after(0, _do)

    # ── Setup steps ───────────────────────────────────────────────────

    def _run_setup(self):
        try:
            self._step_venv()
            self._step_pip()
            self._step_packages()
            self._step_mupen()
            self._step_verify()
            MARKER.touch()

            def _done():
                self._heading.config(text="Ready!", fg=GREEN)
                self._status.set("Launching N64 Operator…")
                self._pct.set("")
                self._hint.config(text="Starting up…")
            self.root.after(0, _done)

            import time; time.sleep(1.2)
            self.root.after(0, self._relaunch)

        except Exception as e:
            def _fail():
                self._heading.config(text="Setup failed", fg=RED)
                self._status.set(f"{e}\n\nClose this window and try again.")
                self._bar.stop(); self._bar.config(mode="determinate", value=0)
                self._pct.set("")
            self.root.after(0, _fail)

    def _step_venv(self):
        self._set("Creating private environment…", "Step 1 of 4")
        self._set_bar(8)
        if VENV_DIR.exists(): return
        r = subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)],
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"venv failed:\n{r.stderr[:300]}")

    def _step_pip(self):
        self._set("Upgrading package manager…", "Step 2 of 4")
        self._set_bar(18)
        subprocess.run([str(_venv_python()), "-m", "pip", "install",
                        "--upgrade", "pip", "-q", "--quiet"],
                       capture_output=True, timeout=60)

    def _step_packages(self):
        python = str(_venv_python())
        for i, pkg in enumerate(REQUIRED_PACKAGES):
            name = pkg.split(">=")[0].split("==")[0]
            pct  = 22 + int(i / len(REQUIRED_PACKAGES) * 35)
            self._set(f"Installing {name}…", f"Step 3 of 4  ({i+1}/{len(REQUIRED_PACKAGES)})")
            self._set_bar(pct)
            r = subprocess.run([python, "-m", "pip", "install", pkg, "-q", "--quiet"],
                               capture_output=True, text=True, timeout=180)
            if r.returncode != 0:
                raise RuntimeError(f"Failed to install {name}:\n{r.stderr[:300]}")
        self._set_bar(58)

    def _step_mupen(self):
        """Download Mupen64Plus using the module's downloader."""
        import sys as _sys
        _sys.path.insert(0, str(APP_DIR))
        try:
            from src.emulator.mupen64plus import download_mupen64plus, BUNDLE_EXE
            import platform
            if platform.system() != "Windows":
                return   # macOS / Linux: user installs via package manager

            bundle_exe = BUNDLE_EXE["Windows"]
            if bundle_exe.exists():
                return   # already there

            self._set("Downloading Mupen64Plus (N64 emulator)…", "Step 4 of 4")
            self._set_bar(60)

            def _prog(msg, pct):
                # map 0-100 → 60-97 on our bar
                bar_pct = 60 + int(pct * 0.37)
                self._set(msg, "Step 4 of 4")
                self._set_bar(bar_pct)

            ok = download_mupen64plus(progress_callback=_prog)
            if not ok:
                # Not fatal — user can still open ROMs, just can't play yet
                self._set("Mupen64Plus download skipped (no internet?).\nYou can still load ROMs.", "")
                import time; time.sleep(2)

        except Exception as e:
            # Non-fatal
            self._set(f"Mupen64Plus download skipped: {e}", "")
            import time; time.sleep(1.5)

    def _step_verify(self):
        self._set("Verifying installation…", "Almost done")
        self._set_bar(98)
        r = subprocess.run([str(_venv_python()), "-c", "import PyQt6; print('ok')"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or "ok" not in r.stdout:
            raise RuntimeError("PyQt6 verification failed.")
        self._set_bar(100)

    def _relaunch(self):
        self.root.destroy()
        python = str(_venv_python())
        if sys.platform == "win32":
            subprocess.Popen([python, __file__] + sys.argv[1:],
                             creationflags=0x00000008 | 0x08000000,
                             close_fds=True)
        else:
            subprocess.Popen([python, __file__] + sys.argv[1:])
        sys.exit(0)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    SplashApp().run()
