"""Orbit camera that can rotate through the poles with an ordinary drag."""

import math

import numpy as np
from vispy.scene.cameras import TurntableCamera


class FreeTurntableCamera(TurntableCamera):
    def _update_rotation(self, event) -> None:
        position = np.asarray(event.mouse_event.pos, dtype=float)
        if self._event_value is None:
            self._rotation_pos = np.asarray(event.mouse_event.press_event.pos, dtype=float)
        dx, dy = position - self._rotation_pos
        self._rotation_pos = position

        # Azimuth acts around world Z, so its screen direction reverses past
        # either pole. Use incremental motion to avoid a jump when crossing it.
        midpoint_elevation = self.elevation + dy * 0.25
        direction = -1 if math.cos(math.radians(midpoint_elevation)) < 0 else 1
        # Commit both angles together; each public setter would otherwise
        # recalculate the complete scene transform for the same mouse event.
        self._azimuth = (self.azimuth - dx * 0.5 * direction + 180) % 360 - 180
        self._elevation = (self.elevation + dy * 0.5 + 180) % 360 - 180
        self._event_value = self.azimuth, self.elevation
        self.view_changed()

    @TurntableCamera.elevation.setter
    def elevation(self, value: float) -> None:
        # VisPy clamps elevation to +/-90 degrees. Wrap instead so a left
        # mouse drag can continue through the top/bottom into an inverted view.
        value = (float(value) + 180) % 360 - 180
        if value == self._elevation:
            return
        self._elevation = value
        self.view_changed()

    def orbit(self, azim: float, elev: float) -> None:
        self.azimuth += azim
        self.elevation += elev
