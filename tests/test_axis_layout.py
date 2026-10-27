from types import SimpleNamespace
import unittest

import numpy as np
from PySide6.QtGui import QFont, QFontMetricsF, QImage
from PySide6.QtWidgets import QApplication
from vispy.visuals.transforms import MatrixTransform

from openimaris.axes import AxisScene, _text_size
from openimaris.axis_layout import layout_axis_text
from openimaris.exporter import _layout_pdf_ticks


class AxisLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def projection(sign=1, scale=1):
        matrix = np.array(((10, -10, 0, 0), (5 * sign, 5 * sign, -10 * sign, 0),
                           (0, 0, 1, 0), (0, 0, 0, 1)), dtype=float)
        matrix[:2] *= scale
        return MatrixTransform(matrix.T)

    def test_z_title_stays_at_axis_midpoint_after_inversion(self):
        axes = AxisScene(None)
        axes._line = lambda *args: SimpleNamespace(visible=True, parent=None, set_data=lambda **kwargs: None)
        axes._text = lambda *args: SimpleNamespace(visible=True, parent=None)
        axes.size, axes.spacing = (40, 30, 12), (10, 5, 2)
        for sign in (1, -1, 1):
            transform = self.projection(sign)
            axes.update_layout(transform)
            title = next(item for item in axes.text_items if item["kind"] == "labels" and item["axis"] == "z")
            ticks = [item for item in axes.text_items if item["kind"] == "ticks" and item["axis"] == "z"]
            first = axes._project(transform, ticks[0]["tick_start"])
            last = axes._project(transform, ticks[-1]["tick_start"])
            tangent = (last - first) / np.linalg.norm(last - first)
            center = axes._project(transform, title["position"])
            self.assertAlmostEqual(float((center - (first + last) / 2) @ tangent), 0, places=5)
            self.assertAlmostEqual(title["rotation"], -90)

    def test_rotating_axes_reuses_visuals_and_glyphs(self):
        axes = AxisScene(None)
        axes.rebuild((40, 30, 12), (10, 5, 2))
        self.assertEqual(axes.visuals["labels"][0].font_size, axes.visuals["ticks"][1].font_size)
        original = {kind: list(visuals) for kind, visuals in axes.visuals.items()}
        axes.set_visible("grid", False)
        axes.set_text_visible(False)
        for sign in (1, -1, 1):
            transform = self.projection(sign)
            axes.update_layout(transform)
            for kind, visuals in axes.visuals.items():
                self.assertEqual(visuals, original[kind])
            self.assertFalse(axes.visuals["grid"][0].visible)
            self.assertFalse(axes.visuals["ticks"][1].visible)
            self.assertEqual(len(axes.text_visuals), 2)
            self.assertEqual(list(axes.visuals["ticks"][1].text),
                             [item["text"] for item in axes.text_items if item["kind"] == "ticks"])
            np.testing.assert_allclose(axes.visuals["ticks"][1].pos,
                                       [item["position"] for item in axes.text_items if item["kind"] == "ticks"])

    def test_z_points_away_from_adjacent_xy_labels(self):
        # X and Y both point down on the page; Z must use the other outward
        # direction at a silhouette corner, pointing up instead.
        transform = self.projection()
        axes = AxisScene(None)
        axes._line = lambda *args: SimpleNamespace(visible=True)
        axes._text = lambda *args: SimpleNamespace(visible=True)
        axes.size, axes.spacing = (40, 30, 12), (10, 5, 2)
        axes.update_layout(transform)
        z_ticks = [item for item in axes.text_items if item.get("axis") == "z" and item["kind"] == "ticks"]
        xy_ticks = [item for item in axes.text_items if item.get("axis") in ("x", "y") and item["kind"] == "ticks"]
        for item in z_ticks:
            direction = transform.map(item["tick_end"]) - transform.map(item["tick_start"])
            self.assertLess(direction[1], 0)
        for item in xy_ticks:
            direction = transform.map(item["tick_end"]) - transform.map(item["tick_start"])
            self.assertGreater(direction[1], 0)
        z_positions = np.array([transform.map(item["position"]) for item in z_ticks])
        xy_positions = np.array([transform.map(item["position"]) for item in xy_ticks])
        font = QFont("Arial")
        font.setPointSizeF(8)
        glyph_height = QFontMetricsF(font).tightBoundingRect("0").height()
        self.assertGreater(np.min(np.linalg.norm(z_positions[:, None] - xy_positions[None, :], axis=2)), glyph_height + 2)

    def test_screen_text_clears_axes_and_titles_for_long_numbers(self):
        for dpi in (96, 144, 192):
            for angle in (0, 15, 65, 90, 120, 175):
                for side in (-1, 1):
                    with self.subTest(dpi=dpi, angle=angle, side=side):
                        tangent = np.array((np.cos(np.deg2rad(angle)), np.sin(np.deg2rad(angle))))
                        normal = np.array((-tangent[1], tangent[0])) * side
                        start, end = np.zeros(2), tangent * 600
                        frame = np.array((start, end, start - normal * 200, end - normal * 200))
                        items = []
                        for axis in "xyz":
                            for index, text in enumerate(("0", "100", "1000", "10000", "0.125")):
                                point = tangent * index * 150
                                items.append({"axis": axis, "kind": "ticks", "text": text,
                                              "position": point + normal * 2, "tick_start": point,
                                              "tick_end": point + normal * 5, "axis_line": (start, end)})
                            title = end + tangent * 20 if axis == "z" else (start + end) / 2 + normal * 10
                            items.append({"axis": axis, "kind": "labels", "text": f"{axis.upper()} [µm]",
                                          "position": title, "frame": frame})

                        def measure(item):
                            return _text_size(item["text"], 8, dpi)

                        def extent(item, direction):
                            angle = np.deg2rad(item.get("rotation", 0))
                            along = np.array((np.cos(angle), np.sin(angle)))
                            across = np.array((-along[1], along[0]))
                            return np.abs((direction @ along, direction @ across)) @ measure(item) / 2

                        placed = layout_axis_text(items, measure, gap=3 * dpi / 96)
                        for axis in "xyz":
                            ticks = [item for item in placed if item["axis"] == axis and item["kind"] == "ticks"]
                            offsets = []
                            for tick in ticks:
                                delta = tick["position"] - tick["tick_end"]
                                self.assertAlmostEqual(delta @ tangent, 0, places=6)
                                self.assertGreaterEqual(delta @ normal - extent(tick, normal), 3 * dpi / 96 - 1e-6)
                                offsets.append(delta @ normal)
                            self.assertAlmostEqual(max(offsets), min(offsets), places=6)
                            title = next(item for item in placed if item["axis"] == axis and item["kind"] == "labels")
                            direction = normal
                            boundary = max(item["position"] @ direction + extent(item, direction) for item in ticks)
                            self.assertGreaterEqual(title["position"] @ direction - extent(title, direction),
                                                    boundary + 3 * dpi / 96 - 1e-6)
                            self.assertAlmostEqual(float((title["position"] - (start + end) / 2) @ tangent), 0, places=6)
                            if axis == "z":
                                self.assertLessEqual(np.sin(np.deg2rad(title["rotation"])), 1e-9)

    def test_zoom_repositions_text_even_without_changing_edges(self):
        axes = AxisScene(None)
        axes.rebuild((576, 576, 1710), (100, 100, 200))
        layouts = []
        for scale in (0.05, 0.2, 0.05):
            transform = self.projection(scale=scale)
            axes.update_layout(transform)
            layouts.append(axes.layout)
            ticks = [item for item in axes.text_items if item["axis"] == "z" and item["kind"] == "ticks"]
            normal = axes._project(transform, ticks[0]["tick_end"]) - axes._project(transform, ticks[0]["tick_start"])
            normal[1] = 0  # This projection keeps Z vertical on the screen.
            normal /= np.linalg.norm(normal)
            for tick in ticks:
                delta = axes._project(transform, tick["position"]) - axes._project(transform, tick["tick_end"])
                width, _ = _text_size(tick["text"], 8, 96)
                self.assertGreaterEqual(delta @ normal - width / 2, 3 - 1e-5)
            np.testing.assert_allclose(axes.visuals["ticks"][1].pos,
                                       [item["position"] for item in axes.text_items if item["kind"] == "ticks"])
        self.assertEqual(layouts[0], layouts[1])
        self.assertEqual(layouts[1], layouts[2])

    def test_pdf_axes_have_equal_physical_gaps_and_centred_columns(self):
        device = QImage(10, 10, QImage.Format.Format_RGB32)
        device.setDotsPerMeterX(round(1200 / 0.0254))
        device.setDotsPerMeterY(round(1200 / 0.0254))
        for font_size in (8, 14):
            font = QFont("Arial")
            font.setPointSizeF(font_size)
            metrics = QFontMetricsF(font, device)
            for sx, sy in ((1, 1), (2, 0.7)):
                with self.subTest(font=font_size, scale=(sx, sy)):
                    items = []
                    for axis, angle in zip("xyz", (15, 120, 90)):
                        radians = np.deg2rad(angle)
                        tangent = np.array((np.cos(radians), np.sin(radians)))
                        outward = np.array((-tangent[1], tangent[0]))
                        for index, text in enumerate(("0", "10", "1000")):
                            start = tangent * index * 200
                            end = start + outward * 15
                            items.append({"axis": axis, "kind": "ticks", "text": text,
                                          "x": end[0], "y": end[1], "tick_start": start, "tick_end": end,
                                          "axis_line": (np.zeros(2), tangent * 400)})
                        items.append({"axis": axis, "kind": "labels", "text": f"{axis.upper()} [µm]",
                                      "x": tangent[0] * 200, "y": tangent[1] * 200,
                                      "axis_line": (np.zeros(2), tangent * 400)})
                    result = _layout_pdf_ticks(items, metrics, sx, sy)
                    gaps = []
                    for axis in "xyz":
                        ticks = [item for item in result if item["axis"] == axis and item["kind"] == "ticks"]
                        a, b = ticks[0]["axis_line"]
                        tangent = (b - a) / np.linalg.norm(b - a)
                        normal = np.array((-tangent[1], tangent[0]))
                        offsets, clearances = [], []
                        for item in ticks:
                            offset = np.dot(np.array((item["x"], item["y"])) - item["tick_end"], normal)
                            along_axis = np.dot(np.array((item["x"], item["y"])) - item["tick_end"], tangent)
                            self.assertAlmostEqual(along_axis, 0, places=6)
                            rect = metrics.tightBoundingRect(item["text"])
                            extent = (abs(normal[0]) * rect.width() + abs(normal[1]) * rect.height()) / 2
                            offsets.append(offset)
                            clearances.append(offset - extent)
                        self.assertAlmostEqual(max(offsets), min(offsets), places=6)
                        gaps.append(min(clearances))
                        title = next(item for item in result if item["axis"] == axis and item["kind"] == "labels")
                        title_center = np.array((title["x"], title["y"]))
                        self.assertAlmostEqual(float((title_center - (a + b) / 2) @ tangent), 0, places=6)
                        if axis == "z":
                            self.assertAlmostEqual(title["rotation"], -90)
                    self.assertAlmostEqual(max(gaps), min(gaps), places=6)
                    self.assertGreater(min(gaps), 0)


if __name__ == "__main__":
    unittest.main()
