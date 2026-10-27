from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen
from PySide6.QtWidgets import QApplication

from .axis_layout import layout_axis_text
from .volume_view import VolumeView


def _render_scene(view: VolumeView, scale: int, include_text: bool) -> tuple[Image.Image, list[dict], list]:
    if view.data is None:
        raise ValueError("请先打开一幅三维图像")
    if scale not in (1, 2, 4):
        raise ValueError("导出倍率必须是 1、2 或 4")

    view.finish_interaction()
    original_size = view.canvas.size
    original_text_visibility = view.axes.text_visible
    width, height = original_size
    target = width * scale, height * scale
    if max(target) > 8192:
        raise ValueError(f"导出尺寸 {target[0]} × {target[1]} 过大，请选择较低倍率")

    text_items = []
    frame = []
    try:
        view.axes.set_text_visible(include_text)
        if target != original_size:
            view.canvas.size = target
        view.canvas.update()
        QApplication.processEvents()
        view.sync_axes()
        view.canvas.update()
        QApplication.processEvents()
        pixels = view.canvas.render()
        if not include_text:
            text_items = view.projected_axis_text()
            size = np.asarray(view.axes.size, dtype=float)
            projection_scale = np.array((pixels.shape[1], pixels.shape[0])) / view.canvas.size
            frame = [
                view.axes._project(view.view.scene.transform, (x, y, z)) * projection_scale
                for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])
            ]
            for item, source in zip(text_items, view.axes.visible_text_items()):
                if item.get("axis") in ("x", "y", "z"):
                    axis = "xyz".index(item["axis"])
                    start = np.clip(np.asarray(source.get("tick_start", source["position"]), dtype=float), 0, size)
                    end = start.copy()
                    start[axis], end[axis] = 0, size[axis]
                    item["frame"] = frame
                    item["axis_line"] = [
                        view.axes._project(view.view.scene.transform, point) * projection_scale for point in (start, end)
                    ]
            logical_width, logical_height = view.canvas.size
            pixel_scale_x = pixels.shape[1] / logical_width
            pixel_scale_y = pixels.shape[0] / logical_height
            for item in text_items:
                item["x"] *= pixel_scale_x
                item["y"] *= pixel_scale_y
                for key in ("tick_start", "tick_end"):
                    if key in item:
                        point = np.asarray(item[key], dtype=float)
                        item[key] = (point[0] * pixel_scale_x, point[1] * pixel_scale_y)
    finally:
        view.axes.set_text_visible(original_text_visibility)
        if view.canvas.size != original_size:
            view.canvas.size = original_size
        view.canvas.update()
        QApplication.processEvents()

    array = np.asarray(pixels)
    if array.ndim != 3 or array.shape[0] < 1 or array.shape[1] < 1:
        raise RuntimeError("三维画面捕获失败")
    return Image.fromarray(array), text_items, frame


def render_image(view: VolumeView, scale: int = 1) -> Image.Image:
    image, _, _ = _render_scene(view, scale, include_text=True)
    return image


def export_png(view: VolumeView, path: str | Path, scale: int = 2) -> tuple[int, int]:
    image = render_image(view, scale)
    image.save(Path(path), format="PNG", dpi=(144 * scale, 144 * scale))
    return image.size


def _clear_axis_label_frame(item: dict, items: list[dict], metrics: QFontMetricsF, sx: float, sy: float) -> np.ndarray:
    """Keep X/Y titles outside the projected frame and their tick labels."""
    center = np.array((item["x"] * sx, item["y"] * sy))
    if "frame" not in item or "axis_line" not in item:
        return center
    frame = np.asarray(item["frame"]) * (sx, sy)
    start, end = np.asarray(item["axis_line"]) * (sx, sy)
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length < 1e-9:
        return center
    normal = np.array((-direction[1], direction[0])) / length
    if np.dot(center - frame.mean(axis=0), normal) < 0:
        normal = -normal

    # A rectangle's extent along the outward normal includes its full width;
    # using only font height fails when the projected edge is steeply tilted.
    def extent(text: str) -> float:
        bounds = metrics.tightBoundingRect(text)
        return (abs(normal[0]) * bounds.width() + abs(normal[1]) * bounds.height()) / 2

    boundary = float(np.max(frame @ normal))
    for tick in items:
        if tick["kind"] == "ticks" and item.get("axis") is not None and tick.get("axis") == item["axis"]:
            position = np.array((tick["x"] * sx, tick["y"] * sy))
            boundary = max(boundary, float(position @ normal) + extent(tick["text"]))
    gap = metrics.height() * 0.25
    distance = max(0.0, boundary + extent(item["text"]) + gap - float(center @ normal))
    return center + normal * distance


def _layout_pdf_ticks(items: list[dict], metrics: QFontMetricsF, sx: float, sy: float) -> list[dict]:
    """Use one physical gap between tick ends and each axis's text envelope.

    Work in PDF units so the spacing is independent of voxel dimensions,
    export resolution and page aspect ratio. A shared envelope per axis keeps
    one- and multi-digit labels centred in the same column.
    """
    placed = []
    for source in items:
        item = dict(source, x=source["x"] * sx, y=source["y"] * sy)
        for key in ("frame", "axis_line", "tick_start", "tick_end"):
            if key in source:
                item[key] = np.asarray(source[key]) * (sx, sy)
        placed.append(item)

    for item in placed:
        item["position"] = np.array((item["x"], item["y"]))

    def measure(item):
        bounds = metrics.tightBoundingRect(item["text"])
        return bounds.width(), bounds.height()

    placed = layout_axis_text(placed, measure, metrics.height() * 0.25)
    for item in placed:
        item["x"], item["y"] = item["position"]
    return placed


def _frame_outline(points: list) -> list[tuple[float, float]]:
    """Convex hull of the projected box, including rotated and face-on views."""
    ordered = sorted(set(tuple(point) for point in points))

    def cross(origin, a, b):
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])

    def half_hull(sequence):
        hull = []
        for point in sequence:
            while len(hull) >= 2 and cross(hull[-2], hull[-1], point) <= 0:
                hull.pop()
            hull.append(point)
        return hull

    return half_hull(ordered)[:-1] + half_hull(reversed(ordered))[:-1]


def export_pdf(
    view: VolumeView,
    path: str | Path,
    scale: int = 2,
    width_cm: float = 16.0,
    height_cm: float = 12.0,
    font_size: float = 8.0,
    transparent_outside_frame: bool = False,
) -> tuple[int, int]:
    if not all(np.isfinite(value) and value > 0 for value in (width_cm, height_cm, font_size)):
        raise ValueError("Figure 宽、高和字体大小必须是大于 0 的数值")
    image, text_items, frame = _render_scene(view, scale, include_text=False)
    rgb = image.convert("RGB")
    qimage = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()

    writer = QPdfWriter(str(Path(path)))
    writer.setTitle(view.data.source.name if view.data else "OpenImaris rendering")
    writer.setCreator("OpenImaris")
    writer.setResolution(1200)
    writer.setPageSize(QPageSize(QSizeF(width_cm * 10, height_cm * 10), QPageSize.Unit.Millimeter))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    if not painter.isActive():
        raise RuntimeError("无法创建 PDF 页面")
    try:
        page = QRectF(0, 0, writer.width(), writer.height())
        sx = writer.width() / image.width
        sy = writer.height() / image.height
        if transparent_outside_frame:
            outline = _frame_outline(frame)
            if len(outline) < 3:
                raise ValueError("无法确定 Frame 轮廓，请调整视角后重试")
            clip = QPainterPath(QPointF(outline[0][0] * sx, outline[0][1] * sy))
            for x, y in outline[1:]:
                clip.lineTo(x * sx, y * sy)
            clip.closeSubpath()
            # A PDF clipping path leaves the outside genuinely unpainted,
            # rather than baking a white background into the image.
            painter.save()
            painter.setClipPath(clip)
            painter.drawImage(page, qimage)
            painter.restore()

            # Tick extensions lie outside the box: redraw those portions as
            # black vectors without changing the frame's interior appearance.
            outside = QPainterPath()
            outside.addRect(page)
            painter.save()
            painter.setClipPath(outside.subtracted(clip))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor("black"), writer.resolution() / 72 * 0.5))
            for item in text_items:
                if "tick_start" in item and "tick_end" in item:
                    start, end = np.asarray((item["tick_start"], item["tick_end"])) * (sx, sy)
                    painter.drawLine(QPointF(*start), QPointF(*end))
            painter.restore()
        else:
            painter.drawImage(page, qimage)
        text_color = QColor("black") if transparent_outside_frame else QColor.fromRgbF(*view.axes.color[:3])
        painter.setPen(text_color)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        font = QFont("Arial")
        font.setPointSizeF(font_size)
        painter.setFont(font)
        # Measure in PDF device units, matching drawText at the writer's DPI.
        metrics = QFontMetricsF(font, writer)
        placements = _layout_pdf_ticks(text_items, metrics, sx, sy)
        for item in placements:
            x, y = item["x"], item["y"]
            if item["kind"] == "labels" and item.get("axis") != "z":
                x, y = _clear_axis_label_frame(item, placements, metrics, 1, 1)
            bounds = metrics.tightBoundingRect(item["text"])
            # drawText takes a baseline; center the visible glyphs on the anchor.
            painter.save()
            painter.translate(x, y)
            painter.rotate(item.get("rotation", 0))
            painter.drawText(QPointF(-bounds.center().x(), -bounds.center().y()), item["text"])
            painter.restore()
    finally:
        painter.end()
    return image.size


def export_image(view: VolumeView, path: str | Path, scale: int = 1) -> tuple[int, int]:
    destination = Path(path)
    if destination.suffix.lower() == ".png":
        return export_png(view, destination, scale)
    if destination.suffix.lower() == ".pdf":
        return export_pdf(view, destination, scale)
    raise ValueError("导出格式必须是 .pdf 或 .png")
