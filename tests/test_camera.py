from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from tron3dviewer.camera import FreeTurntableCamera


class FreeTurntableCameraTest(unittest.TestCase):
    @staticmethod
    def drag(camera, press, dx, dy):
        event = SimpleNamespace(mouse_event=SimpleNamespace(press_event=press, pos=press.pos + (dx, dy)))
        camera._update_rotation(event)

    def test_drag_moves_front_of_volume_with_pointer_after_inversion(self):
        # Project a point facing the camera before/after a small horizontal
        # drag. Assert its actual screen direction, rather than angle signs.
        for elevation in (45, 89, 91, 135, -45, -91, -135, 179):
            for roll in (0, 90, 180, -90):
                for dx in (-2, 2):
                    with self.subTest(elevation=elevation, roll=roll, dx=dx):
                        camera = FreeTurntableCamera(elevation=elevation, azimuth=38, roll=roll)
                        camera._update_camera_pos()
                        point = camera.transform.map((0, 0, 1))
                        press = SimpleNamespace(pos=np.array((200, 200)))
                        self.drag(camera, press, dx, 0)
                        camera._update_camera_pos()
                        projected = camera.transform.imap(point)
                        self.assertGreater(projected[0] * dx, 0)

    def test_diagonal_drag_crosses_pole_without_azimuth_jump(self):
        camera = FreeTurntableCamera(elevation=85, azimuth=38)
        press = SimpleNamespace(pos=np.array((200, 200)))
        previous = camera.azimuth
        for offset in range(2, 42, 2):
            self.drag(camera, press, offset, offset)
            self.assertLessEqual(abs(camera.azimuth - previous), 1.01)
            previous = camera.azimuth
        self.assertEqual(camera.elevation, 105)
        self.assertGreater(camera.azimuth, 38)

    def test_one_transform_update_per_mouse_move(self):
        camera = FreeTurntableCamera(elevation=45, azimuth=38)
        camera.view_changed = Mock()
        self.drag(camera, SimpleNamespace(pos=np.array((200, 200))), 10, 20)
        camera.view_changed.assert_called_once()

    def test_mouse_drag_can_cross_both_poles(self):
        for elevation, dy, expected in ((45, 180, 135), (-45, -180, -135)):
            with self.subTest(elevation=elevation):
                camera = FreeTurntableCamera(elevation=elevation, azimuth=38)
                camera._event_value = None
                press = SimpleNamespace(pos=np.array((200, 200)))
                event = SimpleNamespace(mouse_event=SimpleNamespace(press_event=press, pos=np.array((200, 200 + dy))))
                camera._update_rotation(event)
                self.assertEqual(camera.elevation, expected)
                self.assertEqual(camera.azimuth, 38)

    def test_orbit_wraps_without_clamping(self):
        camera = FreeTurntableCamera(elevation=80)
        camera.orbit(0, 20)
        self.assertEqual(camera.elevation, 100)
        camera.orbit(0, 100)
        self.assertEqual(camera.elevation, -160)
        camera.orbit(0, -200)
        self.assertEqual(camera.elevation, 0)


if __name__ == "__main__":
    unittest.main()
