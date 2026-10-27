import unittest

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from openimaris.widgets import NoWheelSlider, PdfExportDialog


class WidgetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_pdf_dialog_defaults_to_transparent_outside_frame(self):
        dialog = PdfExportDialog(None, 4 / 3)
        self.assertTrue(dialog.transparent_outside_frame_check.isChecked())
        dialog.close()

    def test_slider_ignores_wheel_but_keeps_keyboard_control(self):
        slider = NoWheelSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(50)
        for delta in (-120, 120):
            event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, delta),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(slider, event)
            self.assertEqual(slider.value(), 50)
            self.assertFalse(event.isAccepted())
        QTest.keyClick(slider, Qt.Key.Key_Right)
        self.assertEqual(slider.value(), 51)
        slider.close()


if __name__ == "__main__":
    unittest.main()
