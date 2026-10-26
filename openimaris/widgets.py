from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


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
