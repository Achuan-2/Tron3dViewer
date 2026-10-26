from __future__ import annotations

import numpy as np
from vispy import scene
from vispy.color import Colormap
from vispy.visuals.transforms import STTransform

from .axes import AxisScene, nice_spacing
from .data import VolumeData


CHANNEL_COLORS = [
    (0.1, 1.0, 0.1),
    (1.0, 0.1, 0.1),
    (0.1, 0.8, 1.0),
    (1.0, 0.1, 1.0),
    (1.0, 0.9, 0.1),
    (0.2, 0.4, 1.0),
]


class VolumeView:
    def __init__(self) -> None:
        self.canvas = scene.SceneCanvas(keys="interactive", bgcolor="black", show=False)
        self.view = self.canvas.central_widget.add_view()
        self.camera = scene.cameras.TurntableCamera(
            fov=0,
            elevation=28,
            azimuth=38,
            distance=1500,
            center=(0, 0, 0),
        )
        self.view.camera = self.camera
        self.data: VolumeData | None = None
        self.volumes: list[scene.visuals.Volume] = []
        self.box: scene.visuals.Line | None = None
        self.axes = AxisScene(self.view.scene)
        self.axis_spacing: tuple[float, float, float] | None = None
        self.base_ranges: list[tuple[float, float]] = []

    @property
    def native(self):
        return self.canvas.native

    def set_volume(self, data: VolumeData) -> None:
        for volume in self.volumes:
            volume.parent = None
        if self.box is not None:
            self.box.parent = None
        self.volumes.clear()
        self.data = data
        self.base_ranges = data.display_ranges.copy()

        sx, sy, sz = data.voxel_size
        for index, channel in enumerate(data.channels):
            low, high = data.display_ranges[index]
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
            volume.set_gl_state("additive", depth_test=False, cull_face=False)
            volume.transform = STTransform(scale=(sx, sy, sz))
            self.volumes.append(volume)

        self.axis_spacing = tuple(nice_spacing(size) for size in data.physical_size)
        self.axes.rebuild(data.physical_size, self.axis_spacing)
        self.reset_view()

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
        self.camera.elevation = 45
        self.camera.azimuth = 38
        self.camera.roll = 0
        self.canvas.update()

    def set_view(self, name: str) -> None:
        if self.data is None:
            return
        self.reset_view()
        if name == "xy":
            self.camera.elevation = 90
            self.camera.azimuth = -90
        elif name == "xz":
            self.camera.elevation = 0
            self.camera.azimuth = -90
        elif name == "yz":
            self.camera.elevation = 0
            self.camera.azimuth = 0
        self.canvas.update()

    def set_visible(self, index: int, visible: bool) -> None:
        self.volumes[index].visible = visible
        self.canvas.update()

    def set_opacity(self, index: int, opacity: float) -> None:
        volume = self.volumes[index]
        volume.opacity = max(0.001, opacity)
        volume.set_gl_state("additive", depth_test=False, cull_face=False)
        self.canvas.update()

    def set_color(self, index: int, rgb: tuple[float, float, float]) -> None:
        self.volumes[index].cmap = Colormap([(0, 0, 0), rgb])
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

    def set_background(self, color: str) -> None:
        self.canvas.bgcolor = color
        axis_color = (0.65, 0.68, 0.72, 1.0) if color == "black" else (0.12, 0.14, 0.18, 1.0)
        self.axes.set_color(axis_color)
        self.canvas.update()
