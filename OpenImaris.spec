# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['build/openimaris_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('openimaris/assets', 'openimaris/assets'),
        ('.venv/Lib/site-packages/vispy/glsl', 'vispy/glsl'),
        ('.venv/Lib/site-packages/vispy/io/_data', 'vispy/io/_data'),
    ],
    hiddenimports=['vispy.app.backends._pyside6'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQuick', 'PySide6.QtQml'],
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
    name='OpenImaris',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['build/openimaris.ico'],
)
