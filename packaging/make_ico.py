from pathlib import Path

from PySide6.QtGui import QGuiApplication, QIcon


root = Path(__file__).resolve().parents[1]
destination = root / "build" / "OpenImaris.ico"
destination.parent.mkdir(parents=True, exist_ok=True)
app = QGuiApplication([])
icon = QIcon(str(root / "openimaris" / "assets" / "icon.svg"))
if icon.isNull() or not icon.pixmap(256, 256).save(str(destination)):
    raise RuntimeError("无法生成 Windows 应用图标")
