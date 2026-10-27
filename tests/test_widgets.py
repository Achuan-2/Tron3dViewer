import tempfile
import unittest

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tron3dviewer.i18n import set_language
from tron3dviewer.widgets import NoWheelSlider, PdfExportDialog


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

    def test_pdf_dialog_line_width_defaults_and_grid_visibility(self):
        dialog = PdfExportDialog(None, 4 / 3)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.frame_width_spin.value(), 1.0)
        self.assertEqual(dialog.grid_width_spin.value(), 0.5)
        self.assertFalse(dialog.grid_width_spin.isHidden())
        without_grid = PdfExportDialog(None, 4 / 3, show_grid=False)
        self.addCleanup(without_grid.close)
        self.assertTrue(without_grid.grid_width_spin.isHidden())

    def test_pdf_dialog_sizes_content_when_dimensions_or_text_change(self):
        # Model a scene with fixed-height text outside the scaled volume.
        def figure_size(*, width_cm=None, height_cm=None, font_size, **options):
            if width_cm is not None:
                return width_cm, width_cm * 2 + font_size / 10
            return (height_cm - font_size / 10) / 2, height_cm

        dialog = PdfExportDialog(None, 4 / 3, figure_size=figure_size)
        self.addCleanup(dialog.close)
        self.assertAlmostEqual(dialog.height_spin.value(), 32.8)
        dialog.width_spin.setValue(10)
        self.assertAlmostEqual(dialog.height_spin.value(), 20.8)
        dialog.height_spin.setValue(16.8)
        self.assertAlmostEqual(dialog.width_spin.value(), 8)
        dialog.font_spin.setValue(24)
        self.assertAlmostEqual(dialog.height_spin.value(), 18.4)

    def test_pdf_dialog_remembers_settings_and_uses_current_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = QSettings(directory + "/settings.ini", QSettings.Format.IniFormat)
            dialog = PdfExportDialog(None, 4 / 3, settings=settings)
            self.addCleanup(dialog.close)
            dialog.width_spin.setValue(20)
            dialog.font_spin.setValue(10)
            dialog.frame_width_spin.setValue(1.25)
            dialog.grid_width_spin.setValue(0.75)
            dialog.scale_combo.setCurrentIndex(2)
            dialog.transparent_outside_frame_check.setChecked(False)
            dialog.save_settings(settings)
            restored = PdfExportDialog(None, 2.0, settings=settings)
            self.addCleanup(restored.close)
            self.assertEqual(restored.width_spin.value(), 20)
            self.assertEqual(restored.height_spin.value(), 10)
            self.assertEqual(restored.font_spin.value(), 10)
            self.assertEqual(restored.frame_width_spin.value(), 1.25)
            self.assertEqual(restored.grid_width_spin.value(), 0.75)
            self.assertEqual(restored.scale_combo.currentIndex(), 2)
            self.assertFalse(restored.transparent_outside_frame_check.isChecked())

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
