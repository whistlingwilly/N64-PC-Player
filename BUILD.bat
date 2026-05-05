@echo off
chcp 65001 >nul 2>&1
title N64 Operator - Build EXE v0.3.4

echo.
echo   N64 Operator v0.3.4 - Build Single EXE
echo   ------------------------------------------
echo   Mupen64Plus will be downloaded automatically
echo   on first launch - no manual install needed.
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python not found.
    echo          Download: https://www.python.org/downloads/
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PV=%%v
echo   [OK] Python %PV%

if not exist venv ( python -m venv venv )
call venv\Scripts\activate.bat
echo   [OK] Virtual environment ready

python -m pip install --upgrade pip -q --quiet 2>nul
echo   [->] Installing dependencies...
pip install PyQt6>=6.6.0 pyusb>=1.2.1 requests>=2.28.0 Pillow>=10.0.0 -q --quiet
pip install pyinstaller>=6.0 -q --quiet
echo   [OK] Dependencies installed

if exist build ( rmdir /s /q build )
if exist dist\N64Operator.exe ( del /f /q dist\N64Operator.exe )

echo.
echo   [->] Building N64Operator.exe...
echo.

pyinstaller ^
    --onefile ^
    --windowed ^
    --name "N64Operator" ^
    --add-data "src\database\n64_games.json;src\database" ^
    --hidden-import PyQt6.QtCore ^
    --hidden-import PyQt6.QtGui ^
    --hidden-import PyQt6.QtWidgets ^
    --hidden-import PyQt6.sip ^
    --hidden-import src.core.rom ^
    --hidden-import src.core.crc ^
    --hidden-import src.core.authenticity ^
    --hidden-import src.database.game_db ^
    --hidden-import src.database.gameshark ^
    --hidden-import src.hardware.device ^
    --hidden-import src.emulator.mupen64plus ^
    --hidden-import src.ui.playback ^
    --hidden-import src.ui.settings ^
    --hidden-import urllib.request ^
    --hidden-import urllib.error ^
    --hidden-import zipfile ^
    --hidden-import json ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --noconfirm ^
    main.py

if errorlevel 1 (
    echo   [ERROR] Build failed.
    pause & exit /b 1
)

echo.
echo   ================================================
echo   [OK] SUCCESS - dist\N64Operator.exe
echo.
echo   On first launch, Mupen64Plus will download
echo   automatically. Users need no extra installs.
echo   ================================================
echo.
explorer dist
pause
