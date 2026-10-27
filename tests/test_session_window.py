import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication
import tifffile

from openimaris.main_window import MainWindow


class SessionWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        self.addCleanup(window.volume_view.canvas.close)
        return window

    def test_saved_ims_restores_camera_calibration_channels_and_sidebar(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.tif"
            output = Path(directory) / "session.ims"
            pixels = np.arange(2 * 5 * 6 * 7, dtype=np.uint16).reshape(2, 5, 6, 7)
            tifffile.imwrite(source, pixels, photometric="minisblack", metadata={"axes": "CZYX"})
            window = self.make_window()
            with patch("openimaris.main_window.QMessageBox.critical") as error:
                window.open_volume(str(source))
                error.assert_not_called()
                for spin, value in zip(window.spatial_spins, (2.5, 3.5, 4.5)):
                    spin.setValue(value)
                window.apply_spatial_calibration()
                for spin in window.axis_spacing_spins:
                    spin.setValue(100)
                    self.assertEqual(spin.text(), "100")
                    spin.stepUp()
                    self.assertEqual(spin.value(), 150)
                    spin.stepDown()
                    self.assertEqual(spin.value(), 100)
                for spin, value in zip(window.axis_spacing_spins, (2, 4, 6)):
                    spin.setValue(value)
                window.axis_checks["grid"].setChecked(False)
                window.axis_checks["labels"].setChecked(False)
                window.background_combo.setCurrentIndex(1)
                window.volume_view.set_rotation(-128.5, 137, 63)
                window.volume_view.camera.center = (4, 3, 2)
                window.volume_view.camera.scale_factor = 34.5
                window.volume_view.camera.distance = 77
                # A display range wider than the original texture range must
                # not change the visible channel's brightness after reopening.
                window.high_spin.setValue(500)
                original_clim = window.volume_view.volumes[0].clim
                window.channel_list.setCurrentRow(1)
                window.gamma_spin.setValue(1.35)
                window.opacity_slider.setValue(35)
                window.visible_check.setChecked(False)
                window.low_spin.setValue(10)
                window.high_spin.setValue(500)
                window.channel_settings[1]["color"] = (0.4, 0.5, 0.6)
                window.volume_view.set_color(1, (0.4, 0.5, 0.6))
                expected = window.volume_view.capture_view_state(window.channel_settings, 1)
                expected = json.loads(json.dumps(expected))
                window._save_ims_to(output)
                error.assert_not_called()
            self.assertEqual(window.data.source, output)
            restored = self.make_window()
            with patch("openimaris.main_window.QMessageBox.critical") as error:
                restored.open_volume(str(output))
                error.assert_not_called()
            actual = restored.volume_view.capture_view_state(restored.channel_settings, restored.channel_list.currentRow())
            self.assertEqual(actual, expected)
            np.testing.assert_allclose(restored.volume_view.volumes[0].clim, original_clim)
            self.assertEqual(restored.data.voxel_size, (2.5, 3.5, 4.5))
            self.assertEqual([spin.value() for spin in restored.spatial_spins], [2.5, 3.5, 4.5])
            self.assertEqual([spin.value() for spin in restored.axis_spacing_spins], [2, 4, 6])
            self.assertEqual(restored.gamma_spin.value(), 1.35)
            self.assertEqual(restored.opacity_slider.value(), 35)
            self.assertFalse(restored.visible_check.isChecked())
            self.assertFalse(restored.axis_checks["grid"].isChecked())
            self.assertFalse(restored.axis_checks["labels"].isChecked())
            self.assertEqual(restored.background_combo.currentIndex(), 1)
            self.assertFalse(restored.volume_view.volumes[1].visible)
            self.assertEqual(restored.volume_view.volumes[1].gamma, 1.35)
            self.assertAlmostEqual(restored.volume_view.volumes[1].opacity, 0.35)
            with patch("openimaris.main_window.QFileDialog.getSaveFileName") as dialog:
                restored.save_current()
                dialog.assert_not_called()
            with patch("openimaris.main_window.QMessageBox.critical") as error:
                restored.open_volume(str(source))
                error.assert_not_called()
            self.assertEqual(restored.volume_view.background, "black")
            self.assertTrue(all(check.isChecked() for check in restored.axis_checks.values()))


if __name__ == "__main__":
    unittest.main()
