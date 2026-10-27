from pathlib import Path
import subprocess

from PySide6.QtGui import QGuiApplication, QIcon


root = Path(__file__).resolve().parents[1]
iconset = root / "build" / "OpenImaris.iconset"
iconset.mkdir(parents=True, exist_ok=True)
app = QGuiApplication([])
icon = QIcon(str(root / "tron3d" / "assets" / "icon.svg"))
if icon.isNull():
    raise RuntimeError("无法读取应用图标")

for base_size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        size = base_size * scale
        suffix = "@2x" if scale == 2 else ""
        destination = iconset / f"icon_{base_size}x{base_size}{suffix}.png"
        if not icon.pixmap(size, size).save(str(destination)):
            raise RuntimeError(f"无法生成图标：{destination}")

subprocess.run(
    ["iconutil", "--convert", "icns", str(iconset), "--output", str(root / "build" / "OpenImaris.icns")],
    check=True,
)
