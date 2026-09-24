# -*- mode: python ; coding: utf-8 -*-

# PhotoSer Free — PyInstaller one-file build
# Copyright (C) 2026 JemikiVa

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    'waitress',
    'pystray',
    'PIL.ImageTk',
    'zeroconf',
]

# Keep the build resilient to optional backend modules used by installed packages.
hiddenimports += collect_submodules('waitress')


a = Analysis(
    ['PhotoSer_Free.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PhotoSer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='photoser_app_icon.ico',
    version='version_info.txt',
)
