from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np
import tifffile

from tron3dviewer.data import _ims_number, load_volume
from tron3dviewer.ims import _attributes, save_ims
from tron3dviewer.session import LEGACY_VIEW_STATE_PATHS, VIEW_STATE_PATH


def display_state(channel_count=2):
    return {
        "version": 1,
        "camera": {"elevation": -128.5, "azimuth": 62.25, "roll": 180.0, "fov": 0.0,
                   "center": [5.0, 8.0, 11.0], "scale_factor": 73.0, "distance": 128.0},
        "axes": {"spacing": [2.5, 4.0, 7.0],
                 "visibility": {"box": True, "grid": False, "ticks": True, "labels": False}},
        "background": "white",
        "channels": [{"visible": index != 0, "color": [0.1, 0.8, 0.3], "opacity": 0.65,
                      "gamma": 1.35, "range": [12.0, 385.0]} for index in range(channel_count)],
        "selected_channel": channel_count - 1,
    }


class ImsSavingTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "原始图像.tif"
        self.pixels = np.arange(2 * 2 * 5 * 6 * 7, dtype=np.uint16).reshape(2, 2, 5, 6, 7)
        tifffile.imwrite(self.source, self.pixels, photometric="minisblack", metadata={"axes": "TCZYX"})

    def test_tiff_save_preserves_full_resolution_all_times_and_settings(self):
        data = load_volume(self.source, max_size=3)
        self.assertEqual(data.voxel_scale, (3, 3, 3))
        data.voxel_size = (6, 9, 12)
        original = self.source.read_bytes()
        state = display_state()
        path = self.root / "保存的视图.ims"
        save_ims(data, path, state)
        restored = load_volume(path)
        self.assertEqual(restored.shape, (5, 6, 7))
        self.assertEqual(restored.voxel_size, (2, 3, 4))
        self.assertEqual(restored.view_state, state)
        self.assertEqual(self.source.read_bytes(), original)
        for index, channel in enumerate(restored.channels):
            np.testing.assert_array_equal(channel, self.pixels[0, index])
        with h5py.File(path, "r") as ims:
            self.assertIn("tron3dviewer/ViewState", ims)
            for legacy in LEGACY_VIEW_STATE_PATHS:
                self.assertNotIn(legacy, ims)
            for time in range(2):
                for channel in range(2):
                    group = ims[f"DataSet/ResolutionLevel 0/TimePoint {time}/Channel {channel}"]
                    np.testing.assert_array_equal(group["Data"][:], self.pixels[time, channel])
                    self.assertEqual(group["Data"].dtype, self.pixels.dtype)
                    self.assertEqual(group["Histogram"][:].sum(), 5 * 6 * 7)
            self.assertEqual(ims["Thumbnail/Data"].shape, (256, 1024))

    def test_legacy_display_settings_are_read_and_upgraded(self):
        for index, legacy in enumerate(LEGACY_VIEW_STATE_PATHS):
            with self.subTest(legacy=legacy):
                path = self.root / f"legacy_{index}.ims"
                state = display_state()
                save_ims(load_volume(self.source), path, state)
                with h5py.File(path, "r+") as ims:
                    ims.require_group(legacy.rsplit("/", 1)[0])
                    ims.move(VIEW_STATE_PATH, legacy)
                restored = load_volume(path)
                self.assertEqual(restored.view_state, state)
                state["camera"]["roll"] = 42.0
                save_ims(restored, path, state)
                with h5py.File(path, "r") as ims:
                    self.assertIn(VIEW_STATE_PATH, ims)
                self.assertEqual(load_volume(path).view_state, state)

    def test_ims_copy_and_in_place_save_preserve_other_resolutions_and_objects(self):
        source = self.root / "original.ims"
        state = display_state()
        save_ims(load_volume(self.source), source, state)
        with h5py.File(source, "r+") as ims:
            ims.create_dataset("Scene8/Objects/Vertices", data=np.array([[1, 2, 3]], dtype=np.float32))
            for channel in range(2):
                ims.copy(f"DataSet/ResolutionLevel 0/TimePoint 0/Channel {channel}",
                         ims.require_group("DataSet/ResolutionLevel 1/TimePoint 0"), name=f"Channel {channel}")
        before = source.read_bytes()
        data = load_volume(source, max_size=3)
        data.voxel_size = (6, 9, 12)
        output = self.root / "copy.ims"
        save_ims(data, output, state)
        self.assertEqual(source.read_bytes(), before)
        data = load_volume(output)
        state["camera"]["roll"] = 42.0
        save_ims(data, output, state)
        self.assertEqual(load_volume(output).view_state, state)
        with h5py.File(output, "r") as ims:
            np.testing.assert_array_equal(ims["Scene8/Objects/Vertices"][:], [[1, 2, 3]])
            self.assertIn("ResolutionLevel 1", ims["DataSet"])
            np.testing.assert_array_equal(ims["DataSet/ResolutionLevel 0/TimePoint 1/Channel 1/Data"][:], self.pixels[1, 1])

    def test_save_from_lower_resolution_retains_native_calibration(self):
        source = self.root / "multiscale.ims"
        save_ims(load_volume(self.source), source, display_state())
        with h5py.File(source, "r+") as ims:
            for channel in range(2):
                ims.create_dataset(f"DataSet/ResolutionLevel 1/TimePoint 0/Channel {channel}/Data",
                                   data=self.pixels[0, channel, ::2, ::2, ::2])
        preview = load_volume(source, max_size=4)
        self.assertIn("ResolutionLevel 1", preview.original_axes)
        preview.voxel_size = tuple(scale * native for scale, native in zip(preview.voxel_scale, (2, 3, 4)))
        output = self.root / "multiscale_saved.ims"
        save_ims(preview, output, display_state())
        self.assertEqual(load_volume(output).voxel_size, (2, 3, 4))

    def test_failed_write_does_not_overwrite_existing_file(self):
        output = self.root / "existing.ims"
        output.write_bytes(b"existing destination")
        with patch("tron3dviewer.ims._write_settings", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                save_ims(load_volume(self.source), output, display_state())
        self.assertEqual(output.read_bytes(), b"existing destination")
        self.assertEqual(list(self.root.glob(".existing-*.ims")), [])

    def test_calibration_converts_units_and_preserves_physical_origin(self):
        for unit, scale in (("nm", 0.001), ("m", 1e6)):
            with self.subTest(unit=unit):
                source = self.root / f"{unit}.ims"
                save_ims(load_volume(self.source), source, display_state())
                with h5py.File(source, "r+") as ims:
                    image = ims["DataSetInfo/Image"]
                    _attributes(image, Unit=unit)
                    for axis, (origin, size, voxel) in enumerate(zip((1, 2, 3), (7, 6, 5), (0.5, 1, 2))):
                        _attributes(image, **{f"ExtMin{axis}": origin / scale,
                                              f"ExtMax{axis}": (origin + size * voxel) / scale})
                data = load_volume(source)
                np.testing.assert_allclose(data.voxel_size, (0.5, 1, 2))
                data.voxel_size = (1.5, 2.5, 3.5)
                save_ims(data, source, display_state())
                np.testing.assert_allclose(load_volume(source).voxel_size, (1.5, 2.5, 3.5))
                with h5py.File(source, "r") as ims:
                    image = ims["DataSetInfo/Image"]
                    np.testing.assert_allclose([_ims_number(image, f"ExtMin{axis}") for axis in range(3)], (1, 2, 3))

    def test_unreadable_display_settings_do_not_prevent_opening_pixels(self):
        path = self.root / "settings.ims"
        save_ims(load_volume(self.source), path, display_state())
        for invalid in ("not JSON", '{"version": 2}', '{"version": 1, "camera": null}'):
            with h5py.File(path, "r+") as ims:
                del ims[VIEW_STATE_PATH]
                ims.create_dataset(VIEW_STATE_PATH, data=invalid)
            restored = load_volume(path)
            self.assertIsNone(restored.view_state)
            np.testing.assert_array_equal(restored.channels[0], self.pixels[0, 0])


if __name__ == "__main__":
    unittest.main()
