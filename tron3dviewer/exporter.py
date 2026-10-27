from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfWriter, Transformation
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRectF, QSizeF
from PySide6.QtGui import (
    QColor, QColorSpace, QFont, QFontMetricsF, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QTransform,
)
from PySide6.QtWidgets import QApplication

from .axis_layout import layout_axis_text
from .i18n import tr
from .pdf_fonts import use_system_arial
from .volume_view import VolumeView


def _project_pdf_scene(view: VolumeView, pixel_size=None, line_visibility=None) -> tuple[list[dict], list, dict]:
    """Share projected geometry between the size dialog and the PDF capture."""
    scale = np.asarray(pixel_size or view.canvas.size) / view.canvas.size
    size = np.asarray(view.axes.size, dtype=float)

    def project(point):
        return view.axes._project(view.view.scene.transform, point) * scale

    frame = [project((x, y, z)) for x in (0, size[0]) for y in (0, size[1]) for z in (0, size[2])]
    items = view.projected_axis_text()
    for item, source in zip(items, view.axes.visible_text_items()):
        axis = "xyz".index(item["axis"])
        start = np.clip(np.asarray(source.get("tick_start", source["position"]), dtype=float), 0, size)
        end = start.copy()
        start[axis], end[axis] = 0, size[axis]
        item["frame"] = frame
        item["axis_line"] = [project(start), project(end)]
        item["x"] *= scale[0]
        item["y"] *= scale[1]
        for key in ("tick_start", "tick_end"):
            if key in item:
                item[key] = np.asarray(item[key]) * scale
    visibility = view.axes.visibility if line_visibility is None else line_visibility
    lines = {
        kind: [project(point) for point in view.axes.visuals[kind][0].pos]
        for kind in ("box", "grid") if visibility[kind] and view.axes.visuals.get(kind)
    }
    return items, frame, lines


def _render_scene(
    view: VolumeView, scale: int, include_text: bool, *, vector_axis_lines: bool = False
) -> tuple[Image.Image, list[dict], list]:
    if view.data is None:
        raise ValueError(tr("请先打开一幅三维图像"))
    if scale not in (1, 2, 4):
        raise ValueError(tr("导出倍率必须是 1、2 或 4"))

    view.finish_interaction()
    original_size = view.canvas.size
    original_text_visibility = view.axes.text_visible
    original_line_visibility = {kind: view.axes.visibility[kind] for kind in ("box", "grid")}
    width, height = original_size
    target = width * scale, height * scale
    if max(target) > 8192:
        raise ValueError(tr("导出尺寸 {width} × {height} 过大，请选择较低倍率", width=target[0], height=target[1]))

    text_items = []
    frame = []
    axis_lines = {}
    try:
        view.axes.set_text_visible(include_text)
        if vector_axis_lines:
            for kind in ("box", "grid"):
                view.axes.set_visible(kind, False)
        if target != original_size:
            view.canvas.size = target
        view.canvas.update()
        QApplication.processEvents()
        view.sync_axes()
        view.canvas.update()
        QApplication.processEvents()
        pixels = view.canvas.render()
        if not include_text:
            text_items, frame, lines = _project_pdf_scene(
                view, (pixels.shape[1], pixels.shape[0]), original_line_visibility,
            )
            if vector_axis_lines:
                axis_lines = lines
    finally:
        view.axes.set_text_visible(original_text_visibility)
        for kind, visible in original_line_visibility.items():
            view.axes.set_visible(kind, visible)
        if view.canvas.size != original_size:
            view.canvas.size = original_size
        view.canvas.update()
        QApplication.processEvents()

    array = np.asarray(pixels)
    if array.ndim != 3 or array.shape[0] < 1 or array.shape[1] < 1:
        raise RuntimeError(tr("三维画面捕获失败"))
    image = Image.fromarray(array)
    image.info["axis_lines"] = axis_lines
    return image, text_items, frame


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


def _pdf_content_layout(items: list[dict], frame: list, axis_lines: dict, metrics: QFontMetricsF,
                        sx: float, sy: float, frame_width: float, grid_width: float) -> tuple[list[dict], QRectF]:
    """Measure the painted scene, including glyph rotation and stroke extents."""
    placements = _layout_pdf_ticks(items, metrics, sx, sy)
    bounds = QRectF()
    if len(frame):
        points = np.asarray(frame) * (sx, sy)
        lower, upper = points.min(axis=0), points.max(axis=0)
        bounds = QRectF(QPointF(*lower), QPointF(*upper))
    for kind, width in (("box", frame_width), ("grid", grid_width)):
        points = np.asarray(axis_lines.get(kind, []))
        if len(points):
            points = points * (sx, sy)
            lower, upper = points.min(axis=0) - width / 2, points.max(axis=0) + width / 2
            bounds = bounds.united(QRectF(QPointF(*lower), QPointF(*upper)))
    for item in placements:
        if item["kind"] == "labels" and item.get("axis") != "z":
            item["x"], item["y"] = _clear_axis_label_frame(item, placements, metrics, 1, 1)
        glyphs = metrics.tightBoundingRect(item["text"])
        glyphs.translate(-glyphs.center())
        transform = QTransform().translate(item["x"], item["y"]).rotate(item.get("rotation", 0))
        bounds = bounds.united(transform.mapRect(glyphs))
        if "tick_start" in item:
            # Tick vectors are drawn with a fixed 0.5 pt pen.
            points = np.asarray((item["tick_start"], item["tick_end"]))
            radius = metrics.fontDpi() / 72 * 0.25
            lower, upper = points.min(axis=0) - radius, points.max(axis=0) + radius
            bounds = bounds.united(QRectF(QPointF(*lower), QPointF(*upper)))
    return placements, bounds


def _fit_pdf_content(items, frame, axis_lines, metrics, size, frame_width, grid_width):
    """Fit geometry before painting; fixed-size text must never be clipped.

    The dialog supplies a content-based aspect ratio, so its normal export
    uses equal X/Y scales. Independent API dimensions retain their existing
    behaviour while still including every label in the requested page size.
    """
    sx = sy = 1.0
    for _ in range(100):
        placements, bounds = _pdf_content_layout(
            items, frame, axis_lines, metrics, sx, sy, frame_width, grid_width,
        )
        if bounds.isEmpty():
            raise ValueError(tr("无法确定 Frame 轮廓，请调整视角后重试"))
        factors = np.asarray(size) / (bounds.width(), bounds.height())
        if np.max(np.abs(factors - 1)) < 1e-7:
            return sx, sy, placements, bounds
        sx *= factors[0]
        sy *= factors[1]
    raise ValueError(tr("页面过小，无法完整容纳坐标文字，请增大宽高或减小字体。"))


def pdf_figure_size(view: VolumeView, *, width_cm: float | None = None, height_cm: float | None = None,
                    font_size: float = 8.0, frame_width_pt: float = 1.0,
                    grid_width_pt: float = 0.5) -> tuple[float, float]:
    """Size the tight page without rendering or changing the current camera.

    Exactly one dimension is fixed. Solve the uniform scene scale with the
    same PDF-device font metrics used by export, preserving volume proportions.
    """
    if (width_cm is None) == (height_cm is None):
        raise ValueError("Specify exactly one PDF figure dimension")
    view.finish_interaction()
    items, frame, lines = _project_pdf_scene(view)
    # Use the same 1200 DPI as QPdfWriter, without opening a PDF paint device.
    device = QImage(1, 1, QImage.Format.Format_RGB888)
    device.setDotsPerMeterX(round(1200 / 0.0254))
    device.setDotsPerMeterY(round(1200 / 0.0254))
    font = QFont("Arial")
    font.setPointSizeF(font_size)
    metrics = QFontMetricsF(font, device)
    fixed_width = width_cm is not None
    target = (width_cm if fixed_width else height_cm) * 1200 / 2.54
    scale = 1.0
    for _ in range(100):
        _, bounds = _pdf_content_layout(items, frame, lines, metrics, scale, scale,
                                        frame_width_pt * 1200 / 72, grid_width_pt * 1200 / 72)
        length = bounds.width() if fixed_width else bounds.height()
        factor = target / max(length, 1e-9)
        if abs(factor - 1) < 1e-7:
            return bounds.width() * 2.54 / 1200, bounds.height() * 2.54 / 1200
        scale *= factor
    raise ValueError(tr("页面过小，无法完整容纳坐标文字，请增大宽高或减小字体。"))


def _write_srgb_pdf(data: bytes, path: str | Path, page_size_pt: tuple[float, float]) -> None:
    """Tag Qt's device RGB image and vectors with the same sRGB profile.

    Qt ignores QImage profiles in ordinary PDF output. Explicit ICCBased
    colors prevent a viewer's working RGB/CMYK profile from defining them.
    """
    writer = PdfWriter(clone_from=BytesIO(data))
    profile = DecodedStreamObject()
    profile.set_data(bytes(QColorSpace(QColorSpace.NamedColorSpace.SRgb).iccProfile()))
    profile.update({NameObject("/N"): NumberObject(3), NameObject("/Alternate"): NameObject("/DeviceRGB")})
    srgb = ArrayObject([NameObject("/ICCBased"), writer._add_object(profile.flate_encode())])
    for page in writer.pages:
        # Qt rounds its MediaBox to whole points. Keep the requested physical
        # size and top-left origin, including glyphs in the fractional strip.
        width, height = page_size_pt
        page.add_transformation(Transformation().translate(0, height - float(page.mediabox.height)))
        page.mediabox.upper_right = (width, height)
        use_system_arial(page, writer)
        resources = page["/Resources"]
        colors = resources["/ColorSpace"]
        colors[NameObject("/DefaultRGB")] = srgb
        colors[NameObject("/CSp")] = srgb
        colors[NameObject("/PCSp")] = ArrayObject([NameObject("/Pattern"), srgb])
        # Keep resources RGB-only alongside the forced RGB paint engine;
        # Qt declares unused CMYK entries even in this mode.
        for name in ("/CSpcmyk", "/PCSpcmyk"):
            colors.pop(name, None)
        for reference in resources.get("/XObject", {}).values():
            image = reference.get_object()
            if image.get("/Subtype") == "/Image" and image.get("/ColorSpace") == "/DeviceRGB":
                image[NameObject("/ColorSpace")] = srgb
        page[NameObject("/Group")] = DictionaryObject({
            NameObject("/S"): NameObject("/Transparency"), NameObject("/CS"): srgb,
        })
    writer.compress_identical_objects()
    writer.write(str(path))


def export_pdf(
    view: VolumeView,
    path: str | Path,
    scale: int = 2,
    width_cm: float = 16.0,
    height_cm: float = 12.0,
    font_size: float = 8.0,
    transparent_outside_frame: bool = True,
    frame_width_pt: float = 1.0,
    grid_width_pt: float = 0.5,
) -> tuple[int, int]:
    values = (width_cm, height_cm, font_size, frame_width_pt, grid_width_pt)
    if not all(np.isfinite(value) and value > 0 for value in values):
        raise ValueError(tr("Figure 宽、高、字体大小和线宽必须是大于 0 的数值"))
    image, text_items, frame = _render_scene(view, scale, include_text=False, vector_axis_lines=True)
    rgb = image.convert("RGB")
    qimage = QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()

    pdf_data = QByteArray()
    buffer = QBuffer(pdf_data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    writer = QPdfWriter(buffer)
    writer.setColorModel(QPdfWriter.ColorModel.RGB)
    writer.setTitle(view.data.source.name if view.data else "Tron 3D viewer rendering")
    writer.setCreator("Tron 3D viewer")
    writer.setResolution(1200)
    writer.setPageSize(QPageSize(QSizeF(width_cm * 10, height_cm * 10), QPageSize.Unit.Millimeter))
    writer.setPageMargins(QMarginsF(0, 0, 0, 0))
    painter = QPainter(writer)
    if not painter.isActive():
        raise RuntimeError(tr("无法创建 PDF 页面"))
    try:
        # JPEG chroma subsampling changes narrow, saturated fluorescence details.
        painter.setRenderHint(QPainter.RenderHint.LosslessImageRendering, True)
        page = QRectF(0, 0, width_cm * writer.resolution() / 2.54, height_cm * writer.resolution() / 2.54)
        font = QFont("Arial")
        font.setPointSizeF(font_size)
        painter.setFont(font)
        metrics = QFontMetricsF(font, writer)
        # Empty synthetic scenes have no frame; keep the captured image usable.
        content_frame = frame if len(frame) else [(0, 0), (image.width, image.height)]
        sx, sy, placements, bounds = _fit_pdf_content(
            text_items, content_frame, image.info.get("axis_lines", {}), metrics,
            (page.width(), page.height()), frame_width_pt * writer.resolution() / 72,
            grid_width_pt * writer.resolution() / 72,
        )
        if not transparent_outside_frame:
            painter.fillRect(page, QColor(getattr(view, "background", "black")))
        painter.translate(-bounds.left(), -bounds.top())
        raster_rect = QRectF(0, 0, image.width * sx, image.height * sy)
        if transparent_outside_frame:
            outline = _frame_outline(frame)
            if len(outline) < 3:
                raise ValueError(tr("无法确定 Frame 轮廓，请调整视角后重试"))
            clip = QPainterPath(QPointF(outline[0][0] * sx, outline[0][1] * sy))
            for x, y in outline[1:]:
                clip.lineTo(x * sx, y * sy)
            clip.closeSubpath()
            # A PDF clipping path leaves the outside genuinely unpainted,
            # rather than baking a white background into the image.
            painter.save()
            painter.setClipPath(clip)
            painter.drawImage(raster_rect, qimage)
            painter.restore()

            # Tick extensions lie outside the box: redraw those portions as
            # black vectors without changing the frame's interior appearance.
            outside = QPainterPath()
            outside.addRect(bounds)
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
            painter.drawImage(raster_rect, qimage)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for kind, width_pt in (("box", frame_width_pt), ("grid", grid_width_pt)):
            points = np.asarray(image.info.get("axis_lines", {}).get(kind, []))
            if len(points) == 0:
                continue
            color = (*view.axes.color[:3], 0.22 if kind == "grid" else view.axes.color[3])
            painter.setPen(QPen(QColor.fromRgbF(*color), writer.resolution() / 72 * width_pt))
            for start, end in zip(points[::2] * (sx, sy), points[1::2] * (sx, sy)):
                painter.drawLine(QPointF(*start), QPointF(*end))
        painter.restore()
        text_color = QColor("black") if transparent_outside_frame else QColor.fromRgbF(*view.axes.color[:3])
        painter.setPen(text_color)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        for item in placements:
            x, y = item["x"], item["y"]
            bounds = metrics.tightBoundingRect(item["text"])
            # drawText takes a baseline; center the visible glyphs on the anchor.
            painter.save()
            painter.translate(x, y)
            painter.rotate(item.get("rotation", 0))
            painter.drawText(QPointF(-bounds.center().x(), -bounds.center().y()), item["text"])
            painter.restore()
    finally:
        painter.end()
        buffer.close()
    _write_srgb_pdf(bytes(pdf_data), path, (width_cm * 72 / 2.54, height_cm * 72 / 2.54))
    return image.size


def export_image(view: VolumeView, path: str | Path, scale: int = 1) -> tuple[int, int]:
    destination = Path(path)
    if destination.suffix.lower() == ".png":
        return export_png(view, destination, scale)
    if destination.suffix.lower() == ".pdf":
        return export_pdf(view, destination, scale)
    raise ValueError(tr("导出格式必须是 .pdf 或 .png"))
