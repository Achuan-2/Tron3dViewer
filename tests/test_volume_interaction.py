from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from openimaris.data import VolumeData
from openimaris.exporter import render_image
from openimaris.volume_view import VolumeView


class VolumeInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.view = VolumeView()
        self.view.set_volume(VolumeData(
            channels=[np.ones((12, 16, 20), dtype=np.uint8)] * 2,
            channel_names=["A", "B"], voxel_size=(1, 1, 1), source=Path("test.tif"),
            original_axes="CZYX", downsample_factor=1, display_ranges=[(0, 1)] * 2,
        ))
        self.steps = [0.8, 1.0]
        for volume, step in zip(self.view.volumes, self.steps):
            volume.relative_step_size = step

    def tearDown(self):
        self.view.canvas.close()

    def test_drag_batches_axis_updates_and_release_restores_each_channel(self):
        event = SimpleNamespace(type="mouse_move", is_dragging=True)
        with patch.object(self.view.axes, "update_layout", wraps=self.view.axes.update_layout) as update_layout:
            for _ in range(100):
                self.view._axes_changed(event)
            update_layout.assert_not_called()
            self.assertTrue(self.view._axes_timer.isActive())
            self.assertEqual([v.relative_step_size for v in self.view.volumes], [1.6, 1.6])
            self.view._axes_timer.timeout.emit()
            update_layout.assert_called_once()
        self.view._axes_changed(SimpleNamespace(type="mouse_release"))
        self.assertEqual([v.relative_step_size for v in self.view.volumes], self.steps)
        self.assertFalse(self.view._axes_timer.isActive())
        self.assertFalse(self.view._interaction_timer.isActive())

    def test_hover_keeps_full_quality_and_wheel_idle_restores_it(self):
        self.view._axes_changed(SimpleNamespace(type="mouse_move", is_dragging=False))
        self.assertFalse(self.view._interaction_timer.isActive())
        self.assertEqual([v.relative_step_size for v in self.view.volumes], self.steps)
        self.view._axes_changed(SimpleNamespace(type="mouse_wheel"))
        self.assertTrue(self.view._interaction_timer.isActive())
        self.view._interaction_timer.timeout.emit()
        self.assertEqual([v.relative_step_size for v in self.view.volumes], self.steps)

    def test_export_during_interaction_uses_full_quality(self):
        self.view._axes_changed(SimpleNamespace(type="mouse_move", is_dragging=True))

        def capture():
            self.assertEqual([v.relative_step_size for v in self.view.volumes], self.steps)
            self.assertFalse(self.view._interaction_timer.isActive())
            return np.zeros((16, 20, 4), dtype=np.uint8)

        with patch.object(self.view.canvas, "render", side_effect=capture):
            self.assertEqual(render_image(self.view).size, (20, 16))


if __name__ == "__main__":
    unittest.main()
