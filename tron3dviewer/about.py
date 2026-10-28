from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import __version__
from .i18n import tr


GITHUB_URL = "https://github.com/Achuan-2/Tron3dViewer"
DOI_URL = "https://doi.org/10.5281/zenodo.23724954"
AUTHOR_URL = "https://github.com/Achuan-2"
DONATION_URL = "https://pancake.waffo.ai/store/achuan-2-fdbho4ye/product/PROD_3F7Aa7c2NQlz9KmxcgxjQ7?type=onetime&currency=USD"


class AboutDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("关于 Tron 3D viewer"))
        self.setModal(True)
        self.setMinimumWidth(420)

        assets = Path(__file__).parent / "assets"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(16)
        icon_label = QLabel()
        icon_label.setPixmap(QPixmap(str(assets / "icon.svg")).scaled(
            64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        header.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        title_label = QLabel("Tron 3D viewer")
        title_font = title_label.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_layout.addWidget(title_label)
        title_layout.addWidget(QLabel(tr("版本 {version}", version=__version__)))
        description_label = QLabel(tr("轻量级、开源的三维显微图像查看器"))
        description_label.setWordWrap(True)
        title_layout.addWidget(description_label)
        header.addLayout(title_layout, stretch=1)
        layout.addLayout(header)

        self.author_label = self._link_label(f'{tr("作者")}: <a href="{AUTHOR_URL}">Achuan-2</a>')
        self.github_label = self._link_label(f'GitHub: <a href="{GITHUB_URL}">Achuan-2/Tron3dViewer</a>')
        self.doi_label = self._link_label(f'DOI: <a href="{DOI_URL}">10.5281/zenodo.23724954</a>')
        layout.addWidget(self.author_label)
        layout.addWidget(self.github_label)
        layout.addWidget(self.doi_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(divider)

        support_label = QLabel(tr("如果这个项目对你有帮助，欢迎赞赏支持"))
        support_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        support_label.setWordWrap(True)
        layout.addWidget(support_label)

        self.qr_label = QLabel()
        self.qr_label.setObjectName("wechatRewardQr")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_pixmap = QPixmap(str(assets / "wechat_reward.png"))
        self.qr_label.setPixmap(self.qr_pixmap.scaled(
            240, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        ))
        layout.addWidget(self.qr_label)

        qr_caption = QLabel(tr("微信扫码赞赏"))
        qr_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(qr_caption)

        self.donation_link = self._link_label(
            f'<a href="{html.escape(DONATION_URL, quote=True)}">{tr("其他赞赏方式（Buy me a coffee）")}</a>'
        )
        self.donation_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.donation_link)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _link_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        return label
