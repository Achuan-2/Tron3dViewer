# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path
import tomllib


root = Path.cwd()
vispy = Path(importlib.util.find_spec("vispy").origin).parent
with (root / "pyproject.toml").open("rb") as file:
    version = tomllib.load(file)["project"]["version"]

a = Analysis(
    [str(root / "packaging" / "openimaris_launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "openimaris" / "assets"), "openimaris/assets"),
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
    [],
    exclude_binaries=True,
    name="OpenImaris",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OpenImaris",
)
app = BUNDLE(
    coll,
    name="OpenImaris.app",
    icon=str(root / "build" / "OpenImaris.icns"),
    bundle_identifier="org.openimaris.OpenImaris",
    version=version,
    info_plist={
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHighResolutionCapable": True,
    },
)
