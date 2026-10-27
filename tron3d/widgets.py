from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSignalBlocker, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from .i18n import tr

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
    def __init__(self, parent, aspect_ratio: float, show_grid: bool = True, settings=None, figure_size=None) -> None:
        super().__init__(parent)

        def saved(key, default, value_type):
            return settings.value(f"pdf_export/{key}", default, type=value_type) if settings is not None else default

        self.setWindowTitle(tr("导出矢量文字 PDF"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.width_spin = NoWheelDoubleSpinBox()
        self.height_spin = NoWheelDoubleSpinBox()
        self.font_spin = NoWheelDoubleSpinBox()
        self.frame_width_spin = NoWheelDoubleSpinBox()
        self.grid_width_spin = NoWheelDoubleSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(1.0, 200.0)
            spin.setDecimals(2)
            spin.setSuffix(" cm")
        self._aspect_ratio = aspect_ratio
        self._figure_size = figure_size
        self.width_spin.setValue(saved("width_cm", 16.0, float))
        self.height_spin.setValue(self.width_spin.value() / aspect_ratio)
        self.width_spin.valueChanged.connect(self._update_height)
        self.height_spin.valueChanged.connect(self._update_width)
        self.font_spin.setRange(4.0, 48.0)
        self.font_spin.setDecimals(1)
        self.font_spin.setValue(saved("font_size", 8.0, float))
        self.font_spin.setSuffix(" pt")
        for spin, key, value in (
            (self.frame_width_spin, "frame_width_pt", 1.0), (self.grid_width_spin, "grid_width_pt", 0.5),
        ):
            spin.setRange(0.1, 20.0)
            spin.setDecimals(2)
            spin.setValue(saved(key, value, float))
            spin.setSuffix(" pt")
        self.scale_combo = NoWheelComboBox()
        self.scale_combo.addItems(["1×", tr("2×（高清）"), tr("4×（超清）")])
        self.scale_combo.setCurrentIndex(max(0, min(2, saved("scale_index", 1, int))))
        form.addRow(tr("Figure 宽度"), self.width_spin)
        form.addRow(tr("Figure 高度"), self.height_spin)
        form.addRow(tr("坐标文字大小"), self.font_spin)
        form.addRow(tr("Frame 线宽"), self.frame_width_spin)
        form.addRow(tr("Grid 线宽"), self.grid_width_spin)
        form.setRowVisible(self.grid_width_spin, show_grid)
        form.addRow(tr("体渲染清晰度"), self.scale_combo)
        layout.addLayout(form)
        self.transparent_outside_frame_check = QCheckBox(tr("Frame 外无背景（黑色文字）"))
        self.transparent_outside_frame_check.setChecked(saved("transparent_outside_frame", True, bool))
        self.transparent_outside_frame_check.setToolTip(tr("仅保留 Frame 内的当前背景，外侧透明，文字和外侧刻度线为黑色，方便科研组图。"))
        layout.addWidget(self.transparent_outside_frame_check)
        size_tip = tr("宽高包含完整坐标文字，自动去除外围留白并保持三维图像比例。")
        self.width_spin.setToolTip(size_tip)
        self.height_spin.setToolTip(size_tip)
        for spin in (self.font_spin, self.frame_width_spin, self.grid_width_spin):
            spin.valueChanged.connect(lambda _: self._update_height(self.width_spin.value()))
        self._update_height(self.width_spin.value())
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_height(self, width: float) -> None:
        blocker = QSignalBlocker(self.height_spin)
        height = width / self._aspect_ratio
        if self._figure_size is not None:
            try:
                _, height = self._figure_size(width_cm=width, **self._size_options())
            except ValueError:
                return
        self.height_spin.setValue(height)

    def _update_width(self, height: float) -> None:
        blocker = QSignalBlocker(self.width_spin)
        width = height * self._aspect_ratio
        if self._figure_size is not None:
            try:
                width, _ = self._figure_size(height_cm=height, **self._size_options())
            except ValueError:
                return
        self.width_spin.setValue(width)

    def _size_options(self) -> dict:
        return dict(font_size=self.font_spin.value(), frame_width_pt=self.frame_width_spin.value(),
                    grid_width_pt=self.grid_width_spin.value())

    def save_settings(self, settings) -> None:
        values = {
            "width_cm": self.width_spin.value(),
            "font_size": self.font_spin.value(),
            "frame_width_pt": self.frame_width_spin.value(),
            "grid_width_pt": self.grid_width_spin.value(),
            "scale_index": self.scale_combo.currentIndex(),
            "transparent_outside_frame": self.transparent_outside_frame_check.isChecked(),
        }
        for key, value in values.items():
            settings.setValue(f"pdf_export/{key}", value)

    def values(self) -> tuple[float, float, float, int, float, float]:
        return (
            self.width_spin.value(), self.height_spin.value(), self.font_spin.value(),
            (1, 2, 4)[self.scale_combo.currentIndex()], self.frame_width_spin.value(), self.grid_width_spin.value(),
        )
