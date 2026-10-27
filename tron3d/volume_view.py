from __future__ import annotations

import numpy as np
from PySide6.QtCore import QTimer
from vispy import scene
from vispy.color import Colormap
from vispy.visuals.transforms import STTransform

from .axes import AxisScene, nice_spacing
from .camera import FreeTurntableCamera
from .data import VolumeData


CHANNEL_COLORS = [
    (0.1, 1.0, 0.1),
    (1.0, 0.1, 0.1),
    (0.1, 0.8, 1.0),
    (1.0, 0.1, 1.0),
    (1.0, 0.9, 0.1),
    (0.2, 0.4, 1.0),
]

# Oblique default view matched to the reference framing.
DEFAULT_ELEVATION = 30.0
DEFAULT_AZIMUTH = 60.0
DEFAULT_ROLL = 180.0


class VolumeView:
    def __init__(self) -> None:
        self.canvas = scene.SceneCanvas(keys="interactive", bgcolor="black", show=False)
        self.view = self.canvas.central_widget.add_view()
        self.camera = FreeTurntableCamera(
            fov=0,
            elevation=DEFAULT_ELEVATION,
            azimuth=DEFAULT_AZIMUTH,
            roll=DEFAULT_ROLL,
            distance=1500,
            center=(0, 0, 0),
        )
        self.view.camera = self.camera
        self.data: VolumeData | None = None
        self.volumes: list[scene.visuals.Volume] = []
        self.channel_colors: list[tuple[float, float, float]] = []
        self.background = "black"
        self.box: scene.visuals.Line | None = None
        self.axes = AxisScene(self.view.scene)
        self.axis_spacing: tuple[float, float, float] | None = None
        self.base_ranges: list[tuple[float, float]] = []
        self.view_changed_callback = None
        self._interaction_steps: list[tuple[scene.visuals.Volume, float]] = []
        self._axes_timer = QTimer(self.native)
        self._axes_timer.setSingleShot(True)
        self._axes_timer.setInterval(33)
        self._axes_timer.timeout.connect(self.sync_axes)
        self._interaction_timer = QTimer(self.native)
        self._interaction_timer.setSingleShot(True)
        self._interaction_timer.setInterval(150)
        self._interaction_timer.timeout.connect(self.finish_interaction)
        self.canvas.events.mouse_release.connect(self._axes_changed)
        self.canvas.events.mouse_move.connect(self._axes_changed)
        self.canvas.events.mouse_wheel.connect(self._axes_changed)

    def _axes_changed(self, event=None) -> None:
        if event is None or event.type == "mouse_release":
            self.finish_interaction()
            return
        if event.type == "mouse_move" and not event.is_dragging:
            return
        if not self._interaction_steps:
            for volume in self.volumes:
                self._interaction_steps.append((volume, volume.relative_step_size))
                volume.relative_step_size = max(1.6, volume.relative_step_size)
        # Also recover full quality after a pause or a release outside the view.
        self._interaction_timer.start()
        if not self._axes_timer.isActive():
            self._axes_timer.start()

    def finish_interaction(self) -> None:
        """Restore stationary render quality, including before image export."""
        self._interaction_timer.stop()
        self._axes_timer.stop()
        for volume, step_size in self._interaction_steps:
            volume.relative_step_size = step_size
        self._interaction_steps.clear()
        self.sync_axes()
        self.canvas.update()

    def sync_axes(self) -> None:
        self._axes_timer.stop()
        if self.data is not None:
            self.axes.update_layout(self.view.scene.transform)
        if self.view_changed_callback is not None:
            self.view_changed_callback()

    def set_rotation(self, x_angle: float, y_angle: float, z_angle: float) -> None:
        self.camera.elevation = x_angle
        self.camera.roll = y_angle
        self.camera.azimuth = z_angle
        self.sync_axes()
        self.canvas.update()

    def projected_axis_text(self) -> list[dict]:
        """Project text anchors and tick geometry for vector export."""
        items = []
        for item in self.axes.visible_text_items():
            x, y = self.axes._project(self.view.scene.transform, item["position"])
            projected = {
                "text": item["text"], "x": float(x), "y": float(y),
                "kind": item["kind"], "axis": item["axis"],
            }
            if "tick_start" in item:
                projected["tick_start"] = self.axes._project(self.view.scene.transform, item["tick_start"])
                projected["tick_end"] = self.axes._project(self.view.scene.transform, item["tick_end"])
            items.append(projected)
        return items

    @property
    def native(self):
        return self.canvas.native

    def set_volume(self, data: VolumeData) -> None:
        self.finish_interaction()
        for volume in self.volumes:
            volume.parent = None
        if self.box is not None:
            self.box.parent = None
        self.volumes.clear()
        self.channel_colors.clear()
        self.background = "black"
        self.canvas.bgcolor = "black"
        self.data = data
        ranges = data.view_state.get("normalization_ranges", data.display_ranges) if data.view_state else data.display_ranges
        self.base_ranges = [tuple(bounds) for bounds in ranges]

        sx, sy, sz = data.voxel_size
        for index, channel in enumerate(data.channels):
            low, high = self.base_ranges[index]
            normalized = ((channel.astype(np.float32) - low) / (high - low)).clip(0, 1)
            color = data.colors[index] if data.colors else CHANNEL_COLORS[index % len(CHANNEL_COLORS)]
            volume = scene.visuals.Volume(
                np.ascontiguousarray(normalized),
                parent=self.view.scene,
                method="mip",
                cmap=Colormap([(0, 0, 0), color]),
                clim=(0, 1),
                interpolation="linear",
            )
            volume.transform = STTransform(scale=(sx, sy, sz))
            self.volumes.append(volume)
            self.channel_colors.append(color)
            self._apply_volume_style(index)

        self.axis_spacing = tuple(nice_spacing(size) for size in data.physical_size)
        self.axes.visibility = dict.fromkeys(self.axes.visibility, True)
        self.axes.color = (0.65, 0.68, 0.72, 1.0)
        self.axes.rebuild(data.physical_size, self.axis_spacing)
        self.reset_view()
        if data.view_state is not None:
            self.restore_view_state(data.view_state)

    def capture_view_state(self, channels: list[dict], selected_channel: int) -> dict:
        self.finish_interaction()
        camera = {key: float(getattr(self.camera, key)) for key in (
            "elevation", "azimuth", "roll", "fov", "scale_factor", "distance",
        )}
        camera["center"] = [float(value) for value in self.camera.center]
        return {
            "version": 1,
            "camera": camera,
            "axes": {"spacing": list(self.axis_spacing), "visibility": dict(self.axes.visibility)},
            "background": self.background,
            "channels": [dict(channel) for channel in channels],
            "normalization_ranges": [list(bounds) for bounds in self.base_ranges],
            "selected_channel": selected_channel,
        }

    def restore_view_state(self, state: dict) -> None:
        self.set_background(state["background"])
        self.set_axis_spacing(tuple(state["axes"]["spacing"]))
        for kind, visible in state["axes"]["visibility"].items():
            self.set_axis_visible(kind, visible)
        for index, channel in enumerate(state["channels"]):
            self.set_visible(index, channel["visible"])
            self.set_opacity(index, channel["opacity"])
            self.set_color(index, tuple(channel["color"]))
            self.set_gamma(index, channel["gamma"])
            self.set_contrast(index, *channel["range"])
        camera = state["camera"]
        self.camera.distance = camera["distance"]
        self.camera.set_state({key: camera[key] for key in (
            "elevation", "azimuth", "roll", "fov", "scale_factor", "center",
        )})
        self.sync_axes()
        self.canvas.update()

    def _create_box(self, shape: tuple[int, int, int]) -> scene.visuals.Line:
        z, y, x = shape
        corners = np.array(
            [
                [0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0],
                [0, 0, z], [x, 0, z], [x, y, z], [0, y, z],
            ],
            dtype=np.float32,
        )
        edges = [0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6, 6, 7, 7, 4, 0, 4, 1, 5, 2, 6, 3, 7]
        return scene.visuals.Line(
            pos=corners[edges],
            color=(0.45, 0.45, 0.45, 0.8),
            width=1,
            connect="segments",
            parent=self.view.scene,
            method="gl",
        )

    def update_spatial_calibration(self, voxel_size: tuple[float, float, float]) -> None:
        if self.data is None:
            return
        self.data.voxel_size = voxel_size
        for volume in self.volumes:
            volume.transform = STTransform(scale=voxel_size)
        if self.axis_spacing is None:
            self.axis_spacing = tuple(nice_spacing(size) for size in self.data.physical_size)
        self.axes.rebuild(self.data.physical_size, self.axis_spacing)
        self.reset_view()

    def set_axis_visible(self, kind: str, visible: bool) -> None:
        self.axes.set_visible(kind, visible)
        self.canvas.update()

    def set_axis_spacing(self, spacing: tuple[float, float, float]) -> None:
        if self.data is None:
            return
        self.axis_spacing = spacing
        self.axes.rebuild(self.data.physical_size, spacing)
        self.canvas.update()

    def reset_axis_spacing(self) -> tuple[float, float, float]:
        if self.data is None:
            return 1.0, 1.0, 1.0
        self.axis_spacing = tuple(nice_spacing(size) for size in self.data.physical_size)
        self.axes.rebuild(self.data.physical_size, self.axis_spacing)
        self.canvas.update()
        return self.axis_spacing

    def reset_view(self) -> None:
        if self.data is None:
            return
        size = self.data.physical_size
        self.camera.center = tuple(value / 2 for value in size)
        self.camera.scale_factor = max(size) * 1.25
        self.camera.distance = max(size) * 2.4
        self.camera.elevation = DEFAULT_ELEVATION
        self.camera.azimuth = DEFAULT_AZIMUTH
        self.camera.roll = DEFAULT_ROLL
        self._fit_axis_labels()
        self.canvas.update()

    def _fit_axis_labels(self) -> None:
        """Fit the projected frame and text inside the current viewport."""
        half_size = np.asarray(self.view.size, dtype=float) / 2
        available = half_size - 12 * self.canvas.dpi / 96
        if np.any(available <= 0):
            self.sync_axes()
            return
        # Text retains its pixel size as the volume shrinks, so recompute the
        # layout after scaling instead of estimating a fixed world-space margin.
        for _ in range(6):
            self.sync_axes()
            lower, upper = self.axes.projected_bounds(self.view.scene.transform)
            factor = float(np.max(np.maximum(half_size - lower, upper - half_size) / available))
            if factor <= 1:
                return
            self.camera.scale_factor *= factor * 1.02
        self.sync_axes()

    def flip_z(self) -> None:
        self.camera.roll = (self.camera.roll + 180) % 360
        self.sync_axes()
        self.canvas.update()

    def set_view(self, name: str) -> None:
        if self.data is None:
            return
        self.reset_view()
        if name in ("xy", "xz", "yz"):
            self.camera.roll = 0
        if name == "xy":
            self.camera.elevation = 90
            self.camera.azimuth = -90
        elif name == "xz":
            self.camera.elevation = 0
            self.camera.azimuth = -90
        elif name == "yz":
            self.camera.elevation = 0
            self.camera.azimuth = 0
        self._fit_axis_labels()
        self.canvas.update()

    def set_visible(self, index: int, visible: bool) -> None:
        self.volumes[index].visible = visible
        self.canvas.update()

    def set_opacity(self, index: int, opacity: float) -> None:
        self.volumes[index].opacity = max(0.001, opacity)
        self._apply_volume_style(index)
        self.canvas.update()

    def set_color(self, index: int, rgb: tuple[float, float, float]) -> None:
        self.channel_colors[index] = rgb
        self._apply_volume_style(index)
        self.canvas.update()

    def set_contrast(self, index: int, low: float, high: float) -> None:
        base_low, base_high = self.base_ranges[index]
        span = base_high - base_low
        low_norm = (low - base_low) / span
        high_norm = (high - base_low) / span
        self.volumes[index].clim = (low_norm, max(low_norm + 1e-6, high_norm))
        self.canvas.update()

    def set_gamma(self, index: int, gamma: float) -> None:
        self.volumes[index].gamma = gamma
        self.canvas.update()

    def _apply_volume_style(self, index: int) -> None:
        color = self.channel_colors[index]
        if self.background == "white":
            self.volumes[index].cmap = Colormap([(*color, 0), (*color, 1)])
            blend_mode = "translucent"
        else:
            self.volumes[index].cmap = Colormap([(0, 0, 0), color])
            blend_mode = "additive"
        self.volumes[index].set_gl_state(blend_mode, depth_test=False, cull_face=False)

    def set_background(self, color: str) -> None:
        self.background = color
        self.canvas.bgcolor = color
        for index in range(len(self.volumes)):
            self._apply_volume_style(index)
        axis_color = (0.65, 0.68, 0.72, 1.0) if color == "black" else (0.12, 0.14, 0.18, 1.0)
        self.axes.set_color(axis_color)
        self.canvas.update()
