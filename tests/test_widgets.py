import unittest

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tron3d.i18n import set_language
from tron3d.widgets import NoWheelSlider, PdfExportDialog


class WidgetsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_pdf_dialog_uses_selected_language(self):
        self.addCleanup(set_language, "zh_CN")
        set_language("en")
        dialog = PdfExportDialog(None, 4 / 3)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.windowTitle(), "Export PDF with Vector Text")
        self.assertEqual(dialog.scale_combo.itemText(1), "2× (High Quality)")
        self.assertEqual(dialog.transparent_outside_frame_check.text(), "Transparent Outside Frame (Black Text)")

    def test_pdf_dialog_defaults_to_transparent_outside_frame(self):
        dialog = PdfExportDialog(None, 4 / 3)
        self.assertTrue(dialog.transparent_outside_frame_check.isChecked())
        dialog.close()

    def test_pdf_dialog_locks_aspect_ratio_when_either_dimension_changes(self):
        dialog = PdfExportDialog(None, 4 / 3)
        self.addCleanup(dialog.close)
        dialog.width_spin.setValue(20.0)
        self.assertAlmostEqual(dialog.height_spin.value(), 15.0, places=2)
        dialog.height_spin.setValue(9.0)
        self.assertAlmostEqual(dialog.width_spin.value(), 12.0, places=2)
        self.assertAlmostEqual(dialog.width_spin.value() / dialog.height_spin.value(), 4 / 3, places=2)

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
