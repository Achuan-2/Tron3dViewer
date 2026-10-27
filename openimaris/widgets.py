from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class ChannelGradientBar(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(38)
        self.name = ""
        self.color = (0.0, 1.0, 0.0)
        self.low = 0.0
        self.high = 1.0
        self.base_range = (0.0, 1.0)
        self.gamma = 1.0

    def set_display(self, name, color, low, high, base_range, gamma) -> None:
        self.name = name
        self.color = color
        self.low = low
        self.high = high
        self.base_range = base_range
        self.gamma = gamma
        self.update()

    def paintEvent(self, event) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 7, self.width() - 2, self.height() - 14)
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        for index in range(21):
            position = index / 20
            intensity = position ** self.gamma
            gradient.setColorAt(position, QColor.fromRgbF(*(channel * intensity for channel in self.color)))
        painter.fillRect(rect, gradient)
        painter.setPen(QPen(QColor("#8b96a5"), 1))
        painter.drawRect(rect)

        base_low, base_high = self.base_range
        span = max(base_high - base_low, 1e-12)
        for value, top in ((self.low, True), (self.high, False)):
            fraction = min(1.0, max(0.0, (value - base_low) / span))
            x = rect.left() + fraction * rect.width()
            if top:
                points = [(x, 1), (x - 5, 7), (x + 5, 7)]
            else:
                points = [(x, self.height() - 1), (x - 5, self.height() - 7), (x + 5, self.height() - 7)]
            path = QPainterPath(QPointF(*points[0]))
            path.lineTo(QPointF(*points[1]))
            path.lineTo(QPointF(*points[2]))
            path.closeSubpath()
            painter.fillPath(path, QColor("#d9e1ea"))
            painter.drawPath(path)

        painter.setPen(QColor("white"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.name)


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:
        event.ignore()


class NoWheelSlider(QSlider):
    def wheelEvent(self, event) -> None:
        event.ignore()


class PdfExportDialog(QDialog):
    def __init__(self, parent, aspect_ratio: float) -> None:
        super().__init__(parent)
        self.setWindowTitle("导出矢量文字 PDF")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.width_spin = NoWheelDoubleSpinBox()
        self.height_spin = NoWheelDoubleSpinBox()
        self.font_spin = NoWheelDoubleSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(1.0, 200.0)
            spin.setDecimals(2)
            spin.setSuffix(" cm")
        self.width_spin.setValue(16.0)
        self.height_spin.setValue(16.0 / aspect_ratio)
        self.font_spin.setRange(4.0, 48.0)
        self.font_spin.setDecimals(1)
        self.font_spin.setValue(8.0)
        self.font_spin.setSuffix(" pt")
        self.scale_combo = NoWheelComboBox()
        self.scale_combo.addItems(["1×", "2×（高清）", "4×（超清）"])
        self.scale_combo.setCurrentIndex(1)
        form.addRow("Figure 宽度", self.width_spin)
        form.addRow("Figure 高度", self.height_spin)
        form.addRow("坐标文字大小", self.font_spin)
        form.addRow("体渲染清晰度", self.scale_combo)
        layout.addLayout(form)
        self.transparent_outside_frame_check = QCheckBox("Frame 外无背景（黑色文字）")
        self.transparent_outside_frame_check.setChecked(True)
        self.transparent_outside_frame_check.setToolTip("仅保留 Frame 内的当前背景，外侧透明，文字和外侧刻度线为黑色，方便科研组图。")
        layout.addWidget(self.transparent_outside_frame_check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[float, float, float, int]:
        return self.width_spin.value(), self.height_spin.value(), self.font_spin.value(), (1, 2, 4)[self.scale_combo.currentIndex()]
