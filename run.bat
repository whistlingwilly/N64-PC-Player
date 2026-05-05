@echo off
title N64 Operator v0.6.4 - Dev Run
chcp 65001 >nul 2>&1
color 0A
echo.
echo  ================================================
echo   N64 Operator v0.6.4
echo  ================================================
echo.

if not exist venv (
    echo  Setting up Python environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install PyQt6 pyusb pygame -q --quiet
    echo  Done.
) else (
    call venv\Scripts\activate.bat
    pip install pygame -q --quiet --exists-action i
)

echo  Running...
echo.
python main.py
pause
