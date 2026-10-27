import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PySide6.QtWidgets import QApplication
import tifffile

from tron3d.main_window import MainWindow


class SessionWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self):
        window = MainWindow()
        self.addCleanup(window.close)
        self.addCleanup(window.volume_view.canvas.close)
        return window

    def test_language_is_saved_and_restored(self):
        settings = Mock()
        settings.value.return_value = "en"
        with patch("tron3d.main_window.QSettings", return_value=settings):
            window = MainWindow()
            self.addCleanup(window.close)
            self.addCleanup(window.volume_view.canvas.close)
            self.assertTrue(window.language_actions["en"].isChecked())
            self.assertEqual(window.file_label.text(), "No image loaded")
            window.set_language("zh_CN")
            settings.setValue.assert_called_with("language", "zh_CN")

    def test_language_switches_all_sidebar_text_without_restarting(self):
        window = self.make_window()
        self.addCleanup(window.set_language, "zh_CN")
        window.spatial_spins[0].setValue(12.5)
        window.language_actions["en"].trigger()
        self.assertEqual(window.spatial_spins[0].value(), 12.5)
        self.assertEqual(window.windowTitle(), "Tron 3D viewer — 3D Microscopy Viewer")
        self.assertEqual(window.file_label.text(), "No image loaded")
        self.assertEqual(window.save_action.text(), "Save IMS")
        self.assertEqual(window.background_combo.itemText(0), "Black Background")
        self.assertEqual(
            [window.tabs.tabText(index) for index in range(window.tabs.count())],
            ["Calibration", "Channels & Display", "Axes", "View", "Export"],
        )
        self.assertTrue(window.language_actions["en"].isChecked())
        window.language_actions["zh_CN"].trigger()
        self.assertEqual(window.file_label.text(), "尚未加载图像")
        self.assertEqual(window.tabs.tabText(0), "空间校准")

    def test_sidebar_groups_settings_into_tabs(self):
        window = self.make_window()
        labels = [window.tabs.tabText(index) for index in range(window.tabs.count())]
        self.assertEqual(labels, ["空间校准", "通道与显示", "坐标轴", "视角", "导出"])
        self.assertEqual(window.tabs.currentIndex(), 0)
        self.assertTrue(window.tabs.widget(0).isAncestorOf(window.spatial_mode))
        for control in (window.channel_list, window.low_spin, window.gamma_spin, window.opacity_slider):
            self.assertTrue(window.tabs.widget(1).isAncestorOf(control))

    def test_saved_ims_restores_camera_calibration_channels_and_sidebar(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.tif"
            output = Path(directory) / "session.ims"
            pixels = np.arange(2 * 5 * 6 * 7, dtype=np.uint16).reshape(2, 5, 6, 7)
            tifffile.imwrite(source, pixels, photometric="minisblack", metadata={"axes": "CZYX"})
            window = self.make_window()
            with patch("tron3d.main_window.QMessageBox.critical") as error:
                window.open_volume(str(source))
                error.assert_not_called()
                window.spatial_mode.setCurrentIndex(0)
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
            with patch("tron3d.main_window.QMessageBox.critical") as error:
                restored.open_volume(str(output))
                error.assert_not_called()
            actual = restored.volume_view.capture_view_state(restored.channel_settings, restored.channel_list.currentRow())
            self.assertEqual(actual, expected)
            np.testing.assert_allclose(restored.volume_view.volumes[0].clim, original_clim)
            self.assertEqual(restored.data.voxel_size, (2.5, 3.5, 4.5))
            self.assertEqual([spin.value() for spin in restored.spatial_spins], [17.5, 21, 22.5])
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
            with patch("tron3d.main_window.QFileDialog.getSaveFileName") as dialog:
                restored.save_current()
                dialog.assert_not_called()
            with patch("tron3d.main_window.QMessageBox.critical") as error:
                restored.open_volume(str(source))
                error.assert_not_called()
            self.assertEqual(restored.volume_view.background, "black")
            self.assertTrue(all(check.isChecked() for check in restored.axis_checks.values()))


if __name__ == "__main__":
    unittest.main()
