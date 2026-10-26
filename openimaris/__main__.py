from __future__ import annotations

import argparse
import sys
from pathlib import Path

import qdarktheme
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from vispy import use

from . import __version__


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenImaris 三维显微图像查看器")
    parser.add_argument("image", nargs="?", help="启动时打开的 IMS 或 TIFF 图像")
    parser.add_argument("--version", action="version", version=f"OpenImaris {__version__}")
    args = parser.parse_args()

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenImaris.Desktop.0.1")
    use(app="pyside6", gl="gl2")
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("OpenImaris")
    app.setOrganizationName("OpenImaris")
    app.setStyle("Fusion")
    qdarktheme.setup_theme("dark")
    app.setWindowIcon(QIcon(str(Path(__file__).parent / "assets" / "icon.svg")))

    try:
        from .main_window import MainWindow

        window = MainWindow(args.image)
        window.show()
    except Exception as error:
        QMessageBox.critical(None, "OpenImaris 启动失败", f"{error}\n\n请确认显卡驱动支持 OpenGL 2.1 或更高版本。")
        return 1
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
