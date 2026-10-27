from pathlib import Path
import tempfile
import unittest

import numpy as np
import tifffile

from openimaris.data import _as_channels, load_volume


class TiffLoadingTest(unittest.TestCase):
    def test_plain_multipage_stack_preserves_pixels_and_calibration(self):
        pixels = np.arange(7 * 8 * 10, dtype=np.uint16).reshape(7, 8, 10)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "正常成像_stack.tif"
            with tifffile.TiffWriter(source) as writer:
                for page in pixels:
                    writer.write(page, metadata=None, description="Stack_Step_Z_um: 5.0000")
            with tifffile.TiffFile(source) as tif:
                self.assertEqual(tif.series[0].axes, "IYX")

            volume = load_volume(source)
            self.assertEqual(volume.original_axes, "IYX")
            self.assertEqual(len(volume.channels), 1)
            self.assertEqual(volume.voxel_size, (1.0, 1.0, 5.0))
            np.testing.assert_array_equal(volume.channels[0], pixels)

            preview = load_volume(source, max_size=5)
            self.assertEqual(preview.downsample_factor, 2)
            self.assertEqual(preview.voxel_size, (2.0, 2.0, 10.0))
            np.testing.assert_array_equal(preview.channels[0], pixels[::2, ::2, ::2])

    def test_unspecified_stack_axis_preserves_page_order(self):
        pixels = np.arange(5 * 6 * 7, dtype=np.uint16).reshape(5, 6, 7)
        channels, axes = _as_channels(pixels, "QYX")
        self.assertEqual(axes, "QYX")
        self.assertEqual(len(channels), 1)
        np.testing.assert_array_equal(channels[0], pixels)

    def test_unknown_axis_alongside_z_remains_unsupported(self):
        with self.assertRaisesRegex(ValueError, "IZYX"):
            _as_channels(np.zeros((2, 3, 4, 5), dtype=np.uint16), "IZYX")

    def test_explicit_channel_and_time_axes_preserve_existing_behavior(self):
        pixels = np.arange(2 * 3 * 4 * 5 * 6, dtype=np.uint16).reshape(2, 3, 4, 5, 6)
        channels, axes = _as_channels(pixels, "TCZYX")
        self.assertEqual(axes, "TCZYX")
        self.assertEqual(len(channels), 3)
        for index, channel in enumerate(channels):
            np.testing.assert_array_equal(channel, pixels[0, index])


if __name__ == "__main__":
    unittest.main()
