from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from pypdf import PdfReader
from PySide6.QtWidgets import QApplication

from tron3d.exporter import export_pdf


class PdfColorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_rgb_pixels_are_lossless_and_color_managed(self):
        pixels = np.random.default_rng(42).integers(0, 256, (64, 96, 3), dtype=np.uint8)
        background = Image.fromarray(pixels)
        frame = [(4, 4), (92, 4), (92, 60), (4, 60)]
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0.65, 0.68, 0.72, 1)))
        with tempfile.TemporaryDirectory() as directory:
            for transparent in (False, True):
                with self.subTest(transparent=transparent):
                    path = Path(directory) / "colors.pdf"
                    with patch("tron3d.exporter._render_scene", return_value=(background, [], frame)):
                        export_pdf(view, path, transparent_outside_frame=transparent)
                    page = PdfReader(path).pages[0]
                    colors = page["/Resources"]["/ColorSpace"]
                    self.assertNotIn("/CSpcmyk", colors)
                    self.assertNotIn("/PCSpcmyk", colors)
                    srgb = colors["/DefaultRGB"]
                    self.assertEqual(srgb[0], "/ICCBased")
                    profile = srgb[1].get_object()
                    self.assertEqual(profile["/N"], 3)
                    self.assertEqual(profile.get_data()[16:20], b"RGB ")
                    self.assertEqual(page["/Group"]["/CS"], srgb)
                    images = list(page["/Resources"]["/XObject"].values())
                    self.assertEqual(len(images), 1)
                    embedded = images[0].get_object()
                    self.assertEqual(embedded["/ColorSpace"], srgb)
                    self.assertNotIn("/DCTDecode", str(embedded["/Filter"]))
                    np.testing.assert_array_equal(np.asarray(page.images[0].image.convert("RGB")), pixels)

    def test_text_uses_editable_system_arial(self):
        background = Image.new("RGB", (100, 100), "black")
        frame = [(20, 20), (80, 20), (80, 80), (20, 80)]
        items = [{"text": "100 µm", "x": 30, "y": 50, "kind": "ticks", "axis": "z"}]
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0, 0, 0, 1)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arial.pdf"
            with patch("tron3d.exporter._render_scene", return_value=(background, items, frame)):
                export_pdf(view, path)
            page = PdfReader(path).pages[0]
            font = next(iter(page["/Resources"]["/Font"].values())).get_object()
            self.assertEqual(font["/BaseFont"], "/ArialMT")
            self.assertEqual(font["/Subtype"], "/TrueType")
            self.assertEqual(font["/Encoding"], "/WinAnsiEncoding")
            self.assertNotIn("/FontFile2", font["/FontDescriptor"].get_object())
            self.assertIn("100 µm", page.extract_text())

    def test_frame_and_grid_use_configured_point_widths(self):
        background = Image.new("RGB", (100, 100), "black")
        background.info["axis_lines"] = {
            "box": [(20, 20), (80, 20), (80, 20), (80, 80)],
            "grid": [(50, 20), (50, 80)],
        }
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0.5, 0.5, 0.5, 1)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "widths.pdf"
            with patch("tron3d.exporter._render_scene", return_value=(background, [], [])):
                export_pdf(view, path, transparent_outside_frame=False, frame_width_pt=2, grid_width_pt=0.5)
            content = PdfReader(path).pages[0].get_contents().get_data().decode("ascii")
            self.assertRegex(content, r"33\.3333\d* w")
            grid_path = content.split("/GState", 1)[1].split(" gs\n", 1)[1].split("h f", 1)[0]
            coordinates = [float(token) for token in grid_path.split() if token[0].isdigit()]
            self.assertAlmostEqual(max(coordinates[::2]) - min(coordinates[::2]), 1200 / 72 * 0.5, places=3)


@unittest.skipUnless(shutil.which("pdftocairo"), "Poppler is needed to inspect PDF transparency")
class PdfFrameBackgroundTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_frame_only_background_and_black_vector_annotations(self):
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0.65, 0.68, 0.72, 1)))
        # A rotated box silhouette, with duplicate and interior projected corners.
        frame = [(100, 80), (220, 50), (300, 100), (300, 220), (180, 250), (100, 200),
                 (200, 150), (100, 80)]
        items = [{"text": "100", "x": 60, "y": 150, "kind": "ticks", "axis": "z",
                  "tick_start": (100, 150), "tick_end": (85, 150)}]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for background_color in ("black", "white"):
                for transparent in (False, True):
                    for show_text in (False, True):
                        with self.subTest(background=background_color, transparent=transparent, text=show_text):
                            background = Image.new("RGBA", (400, 300), background_color)
                            ImageDraw.Draw(background).rectangle((180, 130, 220, 170), fill="lime")
                            with patch("tron3d.exporter._render_scene",
                                       return_value=(background, items if show_text else [], frame)):
                                export_pdf(view, output / "frame.pdf", width_cm=10.16, height_cm=7.62,
                                           transparent_outside_frame=transparent)
                            subprocess.run(
                                [shutil.which("pdftocairo"), "-r", "100", "-singlefile", "-png", "-transp",
                                 str(output / "frame.pdf"), str(output / "frame")],
                                check=True, capture_output=True,
                            )
                            with Image.open(output / "frame.png") as rendered:
                                pixels = np.asarray(rendered.convert("RGBA"))
                            self.assertEqual(pixels[10, 10, 3], 0 if transparent else 255)
                            expected = (0, 0, 0, 255) if background_color == "black" else (255, 255, 255, 255)
                            np.testing.assert_array_equal(pixels[110, 150], expected)
                            # Allow rounding in the PDF renderer's sRGB conversion.
                            np.testing.assert_allclose(pixels[150, 200], (0, 255, 0, 255), atol=2)
                            if transparent:
                                # Outside the slanted edge but inside its bounding rectangle.
                                self.assertEqual(pixels[55, 105, 3], 0)
                                text = pixels[130:170, 35:80]
                                opaque = text[..., 3] > 200
                                self.assertEqual(bool(opaque.any()), show_text)
                                if show_text:
                                    self.assertTrue(np.all(text[opaque, :3] == 0))
                                    tick = pixels[148:153, 86:98]
                                    self.assertTrue(np.any(tick[..., 3] > 200))
                                    self.assertTrue(np.all(tick[tick[..., 3] > 200, :3] == 0))

    def test_default_export_keeps_the_outside_transparent(self):
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0.65, 0.68, 0.72, 1)))
        background = Image.new("RGB", (100, 100), "black")
        frame = [(20, 20), (80, 20), (80, 80), (20, 80)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "default.pdf"
            with patch("tron3d.exporter._render_scene", return_value=(background, [], frame)):
                export_pdf(view, path, width_cm=2.54, height_cm=2.54)
            subprocess.run([shutil.which("pdftocairo"), "-r", "100", "-singlefile", "-png", "-transp",
                            str(path), str(path.with_suffix(""))], check=True, capture_output=True)
            with Image.open(path.with_suffix(".png")) as rendered:
                pixels = np.asarray(rendered.convert("RGBA"))
            self.assertEqual(pixels[10, 10, 3], 0)
            np.testing.assert_array_equal(pixels[50, 50], (0, 0, 0, 255))


@unittest.skipUnless(shutil.which("pdftoppm"), "Poppler is needed to inspect rendered PDF text")
class PdfTextAlignmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_xy_titles_clear_rotated_frames(self):
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0, 0, 0, 1)))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for angle in (-75, 0, 35, 80):
                for side in (-1, 1):
                    with self.subTest(angle=angle, side=side):
                        radians = np.deg2rad(angle)
                        tangent = np.array((np.cos(radians), np.sin(radians)))
                        normal = np.array((-tangent[1], tangent[0])) * side
                        center = np.array((200, 150))
                        start, end = center - tangent * 65, center + tangent * 65
                        frame = np.array((start, end, end - normal * 70, start - normal * 70))
                        axis = "x" if side == 1 else "y"
                        item = {"text": f"{axis.upper()} [µm]", "x": 200, "y": 150,
                                "kind": "labels", "axis": axis, "frame": frame, "axis_line": (start, end)}
                        background = Image.new("RGBA", (400, 300), "white")
                        ImageDraw.Draw(background).polygon([tuple(point) for point in frame], outline="red", width=2)
                        with patch("tron3d.exporter._render_scene", return_value=(background, [item], frame)):
                            export_pdf(view, output / "frame.pdf", font_size=14)
                        subprocess.run(
                            [shutil.which("pdftoppm"), "-r", "144", "-singlefile", "-png",
                             str(output / "frame.pdf"), str(output / "frame")], check=True, capture_output=True,
                        )
                        with Image.open(output / "frame.png") as rendered:
                            pixels = np.asarray(rendered.convert("RGB"))
                        rows, columns = np.nonzero(np.all(pixels < 100, axis=2))
                        self.assertGreater(len(rows), 0)
                        # Every visible glyph pixel must lie outside the frame's
                        # supporting edge, on either side and even for steep edges.
                        glyphs = np.column_stack(((columns + 0.5) * 400 / pixels.shape[1],
                                                 (rows + 0.5) * 300 / pixels.shape[0]))
                        clearance = np.min(glyphs @ normal) - np.max(frame @ normal)
                        self.assertGreater(clearance, 1.0)

    def test_rendered_text_is_centered_on_png_anchors(self):
        # Vary digit widths and X positions as on an upright or rolled Z axis.
        items = [
            {"text": text, "x": x, "y": y, "kind": "ticks", "axis": "z",
             "tick_start": (x + 45, y + 20), "tick_end": (x + 40, y + 15)}
            for text, x, y in [("0", 120, 60), ("10", 120, 140), ("1000", 155, 220)]
        ]
        items.append({"text": "Z [µm]", "x": 300, "y": 100, "kind": "labels", "axis": "z"})
        view = SimpleNamespace(data=None, axes=SimpleNamespace(color=(0, 0, 0, 1)))
        background = Image.new("RGBA", (400, 300), "white")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for width_cm, height_cm, font_size in [(16, 12, 8), (12, 16, 14)]:
                with self.subTest(page=(width_cm, height_cm), font_size=font_size):
                    pdf = output / "alignment.pdf"
                    with patch("tron3d.exporter._render_scene", return_value=(background, items, [])):
                        export_pdf(view, pdf, width_cm=width_cm, height_cm=height_cm, font_size=font_size,
                                   transparent_outside_frame=False)
                    subprocess.run(
                        [shutil.which("pdftoppm"), "-r", "144", "-singlefile", "-png", str(pdf), str(output / "page")],
                        check=True, capture_output=True,
                    )
                    with Image.open(output / "page.png") as rendered:
                        pixels = np.asarray(rendered.convert("L"))
                    sx, sy = pixels.shape[1] / 400, pixels.shape[0] / 300
                    for item in items:
                        x, y = item["x"] * sx, item["y"] * sy
                        left, top = round(x - 80), round(y - 40)
                        crop = pixels[top:top + 80, left:left + 160]
                        rows, columns = np.nonzero(crop < 128)
                        self.assertGreater(len(rows), 0, item["text"])
                        center_x = left + (columns.min() + columns.max() + 1) / 2
                        center_y = top + (rows.min() + rows.max() + 1) / 2
                        self.assertAlmostEqual(center_x, x, delta=2, msg=item["text"])
                        self.assertAlmostEqual(center_y, y, delta=2, msg=item["text"])


if __name__ == "__main__":
    unittest.main()
