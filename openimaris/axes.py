from __future__ import annotations

import math

import numpy as np
from vispy import scene


def nice_spacing(size: float) -> float:
    if size <= 0:
        return 1.0
    raw = size / 5
    magnitude = 10 ** math.floor(math.log10(raw))
    normalized = raw / magnitude
    step = 1 if normalized < 1.5 else 2 if normalized < 3.5 else 5 if normalized < 7.5 else 10
    return step * magnitude


def _ticks(size: float, spacing: float) -> np.ndarray:
    count = max(1, math.floor(size / spacing + 1e-6))
    return np.arange(count + 1, dtype=np.float32) * spacing


def _format_tick(value: float) -> str:
    if float(value).is_integer():
        return f"{value:.0f}"
    return f"{value:.3f}".rstrip("0").rstrip(".")


class AxisScene:
    def __init__(self, parent) -> None:
        self.parent = parent
        self.size = (1.0, 1.0, 1.0)
        self.spacing = (1.0, 1.0, 1.0)
        self.color = (0.65, 0.68, 0.72, 1.0)
        self.visibility = {"box": True, "grid": True, "ticks": True, "labels": True}
        self.visuals: dict[str, list] = {}

    def clear(self) -> None:
        for visuals in self.visuals.values():
            for visual in visuals:
                visual.parent = None
        self.visuals.clear()

    def rebuild(self, size: tuple[float, float, float], spacing: tuple[float, float, float]) -> None:
        self.clear()
        self.size = size
        self.spacing = spacing
        x, y, z = size
        sx, sy, sz = spacing
        tick_size = max(size) * 0.012
        label_offset = max(size) * 0.04
        axis_offset = max(size) * 0.13

        corners = np.array(
            [[0, 0, 0], [x, 0, 0], [x, y, 0], [0, y, 0], [0, 0, z], [x, 0, z], [x, y, z], [0, y, z]],
            dtype=np.float32,
        )
        edges = [0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6, 6, 7, 7, 4, 0, 4, 1, 5, 2, 6, 3, 7]
        self.visuals["box"] = [self._line(corners[edges], self.color, 1.2)]

        grid = []
        for value in _ticks(x, sx)[1:]:
            grid.extend([[value, 0, 0], [value, y, 0], [value, 0, 0], [value, 0, z]])
        for value in _ticks(y, sy)[1:]:
            grid.extend([[0, value, 0], [x, value, 0], [0, value, 0], [0, value, z]])
        for value in _ticks(z, sz)[1:]:
            grid.extend([[0, 0, value], [x, 0, value], [0, 0, value], [0, y, value]])
        grid_color = (*self.color[:3], 0.22)
        self.visuals["grid"] = [self._line(np.asarray(grid, dtype=np.float32), grid_color, 0.7)] if grid else []

        ticks, positions, labels = [], [], []
        for value in _ticks(x, sx):
            ticks.extend([[value, 0, 0], [value, -tick_size, 0]])
            positions.append([value, -label_offset, 0])
            labels.append(_format_tick(value))
        for value in _ticks(y, sy):
            ticks.extend([[0, value, 0], [-tick_size, value, 0]])
            positions.append([-label_offset, value, 0])
            labels.append(_format_tick(value))
        for value in _ticks(z, sz):
            ticks.extend([[x, y, value], [x + tick_size, y, value]])
            positions.append([x + label_offset, y, value])
            labels.append(_format_tick(value))
        self.visuals["ticks"] = [self._line(np.asarray(ticks, dtype=np.float32), self.color, 1.0)]
        self.visuals["ticks"].append(self._text(labels, positions, 8))

        axis_labels = self._text(
            ["X [µm]", "Y [µm]", "Z [µm]"],
            [[x / 2, -axis_offset, 0], [-axis_offset, y / 2, 0], [x + label_offset, y, z + axis_offset * 0.6]],
            11,
        )
        self.visuals["labels"] = [axis_labels]
        for kind, visible in self.visibility.items():
            self.set_visible(kind, visible)

    def _line(self, positions, color, width):
        line = scene.visuals.Line(
            pos=positions,
            color=color,
            width=width,
            connect="segments",
            parent=self.parent,
            method="gl",
        )
        line.set_gl_state("translucent", depth_test=False, cull_face=False)
        return line

    def _text(self, labels, positions, font_size):
        text = scene.visuals.Text(
            labels,
            pos=np.asarray(positions, dtype=np.float32),
            color=self.color,
            font_size=font_size,
            anchor_x="center",
            anchor_y="center",
            parent=self.parent,
        )
        text.set_gl_state("translucent", depth_test=False, cull_face=False)
        return text

    def set_visible(self, kind: str, visible: bool) -> None:
        self.visibility[kind] = visible
        for visual in self.visuals.get(kind, []):
            visual.visible = visible

    def set_color(self, color: tuple[float, float, float, float]) -> None:
        self.color = color
        self.rebuild(self.size, self.spacing)
