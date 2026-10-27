from __future__ import annotations

import math
from functools import lru_cache
from importlib.resources import files

import numpy as np
from PIL import ImageFont
from PySide6.QtCore import QTimer
from vispy import scene

from .axis_layout import choose_z_edge, layout_axis_text


DEFAULT_AXIS_VISIBILITY = {"box": True, "grid": False, "ticks": True, "labels": True}


@lru_cache(maxsize=1)
def _axis_font():
    # Measure the same bundled face used by Vispy, without OS font substitution.
    path = files("vispy.util.fonts").joinpath("data", "OpenSans-Regular.ttf")
    return ImageFont.truetype(str(path), 256)


@lru_cache(maxsize=512)
def _text_size(text: str, font_size: float, dpi: float) -> tuple[float, float]:
    font = _axis_font()
    _, top, _, bottom = font.getbbox(text + "hy")
    scale = font_size * dpi / (72 * 256)
    # Vispy's vertical anchor includes ascenders/descenders from 'hy'. Leave a
    # pixel for the SDF edge rather than relying on integer glyph rounding.
    return max(font.getlength(text), font.getbbox(text)[2]) * scale + 1, (bottom - top) * scale + 1


def nice_spacing(size: float) -> float:
    """Choose readable 1/2/5 spacing without imposing an interval limit."""
    if size <= 0:
        return 1.0
    raw = size / 3
    magnitude = 10 ** math.floor(math.log10(raw))
    normalized = raw / magnitude
    # Keep a 2-step longer before jumping to 5: a 200 µm interval remains
    # useful across a 1000–1200 µm range even with five or six intervals.
    step = 1 if normalized < 1.5 else 2 if normalized < 4.5 else 5 if normalized < 7.5 else 10
    spacing = step * magnitude
    # Short micrometre axes benefit from 5 µm steps rather than dense 2 µm ticks.
    return max(5.0, spacing) if size >= 10 else spacing


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
        self.visibility = DEFAULT_AXIS_VISIBILITY.copy()
        self.visuals: dict[str, list] = {}
        self.text_visuals: list[tuple[str, object]] = []
        self.text_items: list[dict] = []
        self.text_visible = True
        self.layout = (0, 0, 0, 0, 0, -1, -1, 0)
        self._text_transform = None
        self._screen_text = parent is not None and parent.canvas is not None
        if parent is not None and parent.canvas is not None:
            parent.canvas.events.resize.connect(self._on_resize)

    def _on_resize(self, event) -> None:
        # Wait until the view's viewport transform reflects the new canvas size.
        QTimer.singleShot(0, self._refresh_text_layout)

    def _refresh_text_layout(self) -> None:
        if self.visuals and self.parent is not None:
            self.update_layout(self.parent.transform)

    def clear(self) -> None:
        for visuals in self.visuals.values():
            for visual in visuals:
                visual.parent = None
        self.visuals.clear()
        self.text_visuals.clear()
        self.text_items.clear()

    @staticmethod
    def _project(transform, position) -> np.ndarray:
        mapped = np.asarray(transform.map(position), dtype=float).ravel()
        if mapped.size >= 4 and abs(mapped[3]) > 1e-12:
            return mapped[:2] / mapped[3]
        return mapped[:2]

    def update_layout(self, transform) -> bool:
        self._text_transform = transform
        x, y, z = self.size
        center = self._project(transform, (x / 2, y / 2, z / 2))
        plane_centers = [self._project(transform, (x / 2, y / 2, value)) for value in (0, z)]
        xy_z_side = int(plane_centers[1][1] > plane_centers[0][1])
        xy_z = xy_z_side * z
        x_midpoints = ((x / 2, 0, xy_z), (x / 2, y, xy_z))
        y_midpoints = ((0, y / 2, xy_z), (x, y / 2, xy_z))
        x_projected = [self._project(transform, point) for point in x_midpoints]
        y_projected = [self._project(transform, point) for point in y_midpoints]
        x_side = int(x_projected[1][1] > x_projected[0][1])
        y_side = int(y_projected[1][1] > y_projected[0][1])

        def outward_sign(midpoint, axis):
            edge = self._project(transform, midpoint)
            outward = edge - center
            norm = np.linalg.norm(outward)
            if norm < 1e-9:
                return -1
            outward /= norm
            scores = []
            for sign in (-1, 1):
                shifted = list(midpoint)
                shifted[axis] += sign * max(self.size) * 0.05
                direction = self._project(transform, shifted) - edge
                scores.append(float(np.dot(direction, outward)))
            return -1 if scores[0] >= scores[1] else 1

        x_label_sign = outward_sign(x_midpoints[x_side], 1)
        y_label_sign = outward_sign(y_midpoints[y_side], 0)
        offset = max(self.size) * 0.04
        xy_positions = [[value, x_side * y + x_label_sign * offset, xy_z] for value in _ticks(x, self.spacing[0])]
        xy_positions.extend([y_side * x + y_label_sign * offset, value, xy_z] for value in _ticks(y, self.spacing[1]))
        zx, zy, z_direction = choose_z_edge(
            lambda point: self._project(transform, point), self.size, _ticks(z, self.spacing[2]), xy_positions
        )
        layout = (x_side, y_side, zx, zy, z_direction, x_label_sign, y_label_sign, xy_z_side)
        if layout == self.layout and self.visuals:
            self._update_text_layout(transform)
            return False
        self.layout = layout
        self.rebuild(self.size, self.spacing, layout_only=bool(self.visuals))
        return True

    def rebuild(
        self, size: tuple[float, float, float], spacing: tuple[float, float, float], *, layout_only: bool = False
    ) -> None:
        if not layout_only:
            self.clear()
        self.size = size
        self.spacing = spacing
        x, y, z = size
        sx, sy, sz = spacing
        x_side, y_side, zx, zy, z_direction, x_label_sign, y_label_sign, xy_z_side = self.layout
        xy_z = xy_z_side * z
        tick_size = max(size) * 0.012
        label_offset = max(size) * 0.04
        axis_offset = max(size) * 0.13

        if not layout_only:
            self._rebuild_frame(size, spacing)

        ticks, positions, labels, tick_axes = [], [], [], []
        y_edge = x_side * y
        x_out = x_label_sign
        for value in _ticks(x, sx):
            ticks.extend([[value, y_edge, xy_z], [value, y_edge + x_out * tick_size, xy_z]])
            positions.append([value, y_edge + x_out * label_offset, xy_z])
            labels.append(_format_tick(value))
            tick_axes.append("x")
        x_label = [x / 2, y_edge + x_out * axis_offset, xy_z]

        x_edge = y_side * x
        y_out = y_label_sign
        for value in _ticks(y, sy):
            ticks.extend([[x_edge, value, xy_z], [x_edge + y_out * tick_size, value, xy_z]])
            positions.append([x_edge + y_out * label_offset, value, xy_z])
            labels.append(_format_tick(value))
            tick_axes.append("y")
        y_label = [x_edge + y_out * axis_offset, y / 2, xy_z]

        cx, cy = zx * x, zy * y
        z_out = (-1 if zx == 0 else 1) if z_direction == 0 else 0
        w_out = (-1 if zy == 0 else 1) if z_direction == 1 else 0
        for value in _ticks(z, sz):
            ticks.extend([[cx, cy, value], [cx + z_out * tick_size, cy + w_out * tick_size, value]])
            positions.append([cx + z_out * label_offset, cy + w_out * label_offset, value])
            labels.append(_format_tick(value))
            tick_axes.append("z")
        z_label = [cx + z_out * axis_offset, cy + w_out * axis_offset, z / 2]

        self.text_items = [
            {
                "text": label,
                "position": tuple(position),
                "kind": "ticks",
                "axis": axis,
                "tick_start": tuple(start),
                "tick_end": tuple(end),
            }
            for label, position, axis, start, end in zip(labels, positions, tick_axes, ticks[::2], ticks[1::2])
        ]
        self.text_items.extend(
            {"text": text, "position": tuple(position), "kind": "labels", "axis": axis}
            for text, position, axis in zip(("X [µm]", "Y [µm]", "Z [µm]"), (x_label, y_label, z_label), "xyz")
        )
        for item in self.text_items:
            item["base_position"] = item["position"]
        tick_positions = np.asarray(ticks, dtype=np.float32)
        label_positions = (x_label, y_label, z_label)
        if layout_only:
            # Rotation only relocates annotations. Keep the GL programs,
            # glyph buffers, box and grid instead of recreating scene nodes.
            self.visuals["ticks"][0].set_data(pos=tick_positions)
            self.visuals["ticks"][1].pos = positions
            self.visuals["labels"][0].pos = label_positions
        else:
            self.visuals["ticks"] = [self._line(tick_positions, self.color, 1.0)]
            self.visuals["ticks"].append(self._text(labels, positions, 8, "ticks"))
            self.visuals["labels"] = [self._text(("X [µm]", "Y [µm]", "Z [µm]"), label_positions, 8, "labels")]
        self._apply_visibility()
        if self._text_transform is not None:
            self._update_text_layout(self._text_transform)

    def _update_text_layout(self, transform) -> None:
        """Move text in pixels, then unproject at each anchor's original depth."""
        project = lambda point: self._project(transform, point)
        size = np.asarray(self.size)
        frame = np.array([project((x, y, z)) for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])])
        projected = []
        for source in self.text_items:
            item = dict(source, position=project(source["base_position"]), frame=frame)
            axis = "xyz".index(source["axis"])
            start = np.clip(np.asarray(source.get("tick_start", source["base_position"]), dtype=float), 0, size)
            end = start.copy()
            start[axis], end[axis] = 0, size[axis]
            item["axis_line"] = np.array((project(start), project(end)))
            for key in ("tick_start", "tick_end"):
                if key in source:
                    item[key] = project(source[key])
            projected.append(item)
        canvas = self.parent.canvas if self.parent is not None else None
        dpi = float(canvas.dpi) if canvas is not None else 96.0

        def measure(item):
            return _text_size(item["text"], 8, dpi)

        placed = layout_axis_text(projected, measure, gap=3 * dpi / 96)
        for source, item in zip(self.text_items, placed):
            mapped = np.asarray(transform.map(source["base_position"]), dtype=float).ravel().copy()
            mapped[:2] = item["position"] * (mapped[3] if mapped.size >= 4 else 1)
            world = np.asarray(transform.imap(mapped), dtype=float).ravel()
            if world.size >= 4:
                world = world[:3] / world[3]
            source["position"] = tuple(world[:3])
            source["rotation"] = item.get("rotation", 0)
        # Keep annotations in screen space, independent of camera depth.
        positions = placed if self._screen_text else self.text_items
        self.visuals["ticks"][1].pos = [item["position"] for item in positions if item["kind"] == "ticks"]
        self.visuals["labels"][0].pos = [item["position"] for item in positions if item["kind"] == "labels"]
        self.visuals["labels"][0].rotation = [item.get("rotation", 0) for item in placed if item["kind"] == "labels"]

    def _rebuild_frame(self, size, spacing) -> None:
        x, y, z = size
        sx, sy, sz = spacing
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

    def _line(self, positions, color, width):
        line = scene.visuals.Line(
            pos=positions, color=color, width=width, connect="segments", parent=self.parent, method="gl"
        )
        line.set_gl_state("translucent", depth_test=False, cull_face=False)
        return line

    def _text(self, labels, positions, font_size, kind):
        text = scene.visuals.Text(
            labels,
            pos=np.asarray(positions, dtype=np.float32),
            color=self.color,
            font_size=font_size,
            anchor_x="center",
            anchor_y="center",
            parent=self.parent.canvas.scene if self._screen_text else self.parent,
        )
        text.set_gl_state("translucent", depth_test=False, cull_face=False, scissor_test=False, stencil_test=False)
        if self._screen_text:
            text.order = 100  # Draw the overlay after the volume view.
        self.text_visuals.append((kind, text))
        return text

    def _apply_visibility(self) -> None:
        for kind, visuals in self.visuals.items():
            for visual in visuals:
                visual.visible = self.visibility[kind]
        for kind, visual in self.text_visuals:
            visual.visible = self.text_visible and self.visibility[kind]

    def set_visible(self, kind: str, visible: bool) -> None:
        self.visibility[kind] = visible
        self._apply_visibility()

    def set_text_visible(self, visible: bool) -> None:
        self.text_visible = visible
        self._apply_visibility()

    def visible_text_items(self) -> list[dict]:
        return [item for item in self.text_items if self.visibility[item["kind"]]]

    def projected_bounds(self, transform) -> tuple[np.ndarray, np.ndarray]:
        """Screen bounds of the volume frame and visible axis annotations."""
        x, y, z = self.size
        points = [self._project(transform, (cx, cy, cz))
                  for cx in (0, x) for cy in (0, y) for cz in (0, z)]
        canvas = self.parent.canvas if self.parent is not None else None
        dpi = float(canvas.dpi) if canvas is not None else 96.0
        for item in self.visible_text_items():
            center = self._project(transform, item["position"])
            width, height = _text_size(item["text"], 8, dpi)
            angle = np.deg2rad(item.get("rotation", 0))
            cosine, sine = abs(np.cos(angle)), abs(np.sin(angle))
            half_size = np.array((width * cosine + height * sine,
                                  width * sine + height * cosine)) / 2
            points.extend((center - half_size, center + half_size))
        return np.min(points, axis=0), np.max(points, axis=0)

    def set_color(self, color: tuple[float, float, float, float]) -> None:
        self.color = color
        self.rebuild(self.size, self.spacing)
