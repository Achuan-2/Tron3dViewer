from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication

from tron3d.data import VolumeData
from tron3d.exporter import _render_scene, render_image
from tron3d.volume_view import VolumeView


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

    def test_reset_view_uses_default_oblique_angles(self):
        self.view.set_rotation(10, 20, 30)
        self.view.reset_view()
        self.assertEqual(self.view.camera.elevation, 30)
        self.assertEqual(self.view.camera.azimuth, 60)
        self.assertEqual(self.view.camera.roll, 180)

    def test_default_depth_increases_downward_and_flip_toggles_it(self):
        def depth_direction():
            transform = self.view.view.scene.transform
            near = self.view.axes._project(transform, (0, 0, 0))
            far = self.view.axes._project(transform, (0, 0, self.view.data.physical_size[2]))
            return far[1] - near[1]

        self.assertGreater(depth_direction(), 0)
        self.view.flip_z()
        self.assertLess(depth_direction(), 0)
        self.view.reset_view()
        self.assertGreater(depth_direction(), 0)
        for preset in ("xy", "xz", "yz"):
            self.view.set_view(preset)
            self.assertEqual(self.view.camera.roll, 0)

    def test_pdf_capture_separates_vector_lines_and_restores_visibility(self):
        self.view.axes.set_visible("grid", False)
        image, _, _ = _render_scene(self.view, 1, include_text=False, vector_axis_lines=True)
        self.assertIn("box", image.info["axis_lines"])
        self.assertNotIn("grid", image.info["axis_lines"])
        self.assertTrue(self.view.axes.visuals["box"][0].visible)
        self.assertFalse(self.view.axes.visuals["grid"][0].visible)

    def test_grid_uses_far_faces_through_rotation_and_inversion(self):
        size = np.asarray(self.view.data.physical_size)
        grid = self.view.axes.visuals["grid"][0]
        for elevation in (30, -30, 135, -135):
            for azimuth in (15, 105, 195, 285):
                for roll in (0, 180):
                    with self.subTest(elevation=elevation, azimuth=azimuth, roll=roll):
                        self.view.set_rotation(elevation, roll, azimuth)
                        self.assertIs(self.view.axes.visuals["grid"][0], grid)
                        for axis, side in enumerate(self.view.axes.grid_sides):
                            near, far = size / 2, size / 2
                            far[axis] = side * size[axis]
                            near[axis] = (1 - side) * size[axis]
                            camera = self.view.camera.transform
                            self.assertLess(camera.imap(far)[2], camera.imap(near)[2])
                        # Every segment lies on a selected rear face.
                        planes = np.asarray(self.view.axes.grid_sides) * size
                        for start, end in np.asarray(grid.pos).reshape(-1, 2, 3):
                            self.assertTrue(np.any(np.isclose(start, planes) & np.isclose(end, planes)))

    def test_background_grid_does_not_darken_bright_volume_signal(self):
        self.view.axes.set_visible("grid", False)
        baseline = np.asarray(self.view.canvas.render())[:, :, 1].astype(int)
        self.view.axes.set_visible("grid", True)
        with_grid = np.asarray(self.view.canvas.render())[:, :, 1].astype(int)
        signal = baseline > 180
        self.assertTrue(np.any(signal))
        self.assertGreaterEqual(np.min(with_grid[signal] - baseline[signal]), -1)

    def test_reset_view_fits_all_axis_text_for_tall_and_flat_volumes(self):
        self.view.canvas.show()
        for viewport in ((1080, 800), (480, 360), (640, 960)):
            self.view.canvas.size = viewport
            self.app.processEvents()
            for size in ((512, 512, 1210), (47, 36, 13), (2000, 20, 100)):
                with self.subTest(viewport=viewport, physical_size=size):
                    self.view.update_spatial_calibration(tuple(
                        length / pixels for length, pixels in zip(size, self.view.data.shape[::-1])
                    ))
                    lower, upper = self.view.axes.projected_bounds(self.view.view.scene.transform)
                    self.assertTrue(np.all(lower >= 10), lower)
                    self.assertTrue(np.all(upper <= np.asarray(viewport) - 10), upper)

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
