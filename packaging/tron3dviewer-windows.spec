# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path


root = Path.cwd()
vispy = Path(importlib.util.find_spec("vispy").origin).parent

a = Analysis(
    [str(root / "packaging" / "tron3dviewer_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "tron3dviewer" / "assets"), "tron3dviewer/assets"),
        (str(root / "tron3dviewer" / "i18n"), "tron3dviewer/i18n"),
        (str(vispy / "glsl"), "vispy/glsl"),
        (str(vispy / "io" / "_data"), "vispy/io/_data"),
    ],
    hiddenimports=["vispy.app.backends._pyside6"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick", "PySide6.QtQml"],
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
    name="tron3dviewer",
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
    icon=[str(root / "build" / "tron3dviewer.ico")],
)
