# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for N64 Operator
# Run:  pyinstaller N64Operator.spec

import sys
from pathlib import Path

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle the game database JSON
        ('src/database/n64_games.json', 'src/database'),
        ('src/database/covers', 'src/database/covers'),
    ],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'sqlite3',
        'urllib.request',
        'urllib.parse',
        'xml.etree.ElementTree',
        'src.core.rom',
        'src.core.crc',
        'src.core.authenticity',
        'src.database.game_db',
        'src.database.gameshark',
        'src.hardware.device',
        'src.emulator.mupen64plus',
        'src.ui.playback',
        'src.ui.settings',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'scipy',
        'PIL', 'cv2', 'wx', 'gtk',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='N64Operator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No terminal window — GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/icon.ico',   # Uncomment when you have an icon
)
