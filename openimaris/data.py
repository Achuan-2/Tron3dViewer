from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile

from .session import read_view_state


@dataclass(slots=True)
class VolumeData:
    channels: list[np.ndarray]
    channel_names: list[str]
    voxel_size: tuple[float, float, float]
    source: Path
    original_axes: str
    downsample_factor: int
    display_ranges: list[tuple[float, float]]
    colors: list[tuple[float, float, float]] | None = None
    # Native voxels represented by one preview voxel, in XYZ order.
    voxel_scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    view_state: dict | None = None

    @property
    def shape(self) -> tuple[int, int, int]:
        return self.channels[0].shape

    @property
    def physical_size(self) -> tuple[float, float, float]:
        z, y, x = self.shape
        sx, sy, sz = self.voxel_size
        return x * sx, y * sy, z * sz


def _metadata_value(metadata: dict, description: str, key: str) -> float | None:
    value = metadata.get(key)
    if value is None:
        match = re.search(rf"(?:^|\n){re.escape(key)}:\s*([-+\d.eE]+)", description)
        if match:
            value = match.group(1)
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def _voxel_size(tif: tifffile.TiffFile) -> tuple[float, float, float]:
    metadata = tif.imagej_metadata or {}
    description = (tif.pages[0].description or "") + "\n" + str(metadata.get("Info", ""))
    z = _metadata_value(metadata, description, "spacing")
    z = z or _metadata_value(metadata, description, "Stack_Step_Z_um") or 1.0

    x = _metadata_value(metadata, description, "pixel_width")
    y = _metadata_value(metadata, description, "pixel_height")
    page = tif.pages[0]
    if x is None or y is None:
        try:
            x_tag = page.tags["XResolution"].value
            y_tag = page.tags["YResolution"].value
            x_res = float(x_tag[0]) / float(x_tag[1])
            y_res = float(y_tag[0]) / float(y_tag[1])
            unit = int(page.tags.get("ResolutionUnit", 2).value)
            unit_scale = {2: 25400.0, 3: 10000.0}.get(unit, 1.0)
            if x_res > 0 and x_res != 1 and y_res > 0 and y_res != 1:
                x = x if x is not None else unit_scale / x_res
                y = y if y is not None else unit_scale / y_res
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    return x or 1.0, y or 1.0, z


def _as_channels(array: np.ndarray, axes: str) -> tuple[list[np.ndarray], str]:
    axes = axes.upper()
    original_axes = axes
    # Plain multipage TIFFs use I (page) or Q (unspecified) for the stack
    # dimension. Treat a single grayscale stack as Z in this volume viewer.
    if axes in ("IYX", "QYX"):
        axes = "ZYX"
    if "T" in axes:
        if axes.count("T") != 1:
            raise ValueError(f"无法解释时间维度：{original_axes}")
        array = np.take(array, 0, axis=axes.index("T"))
        axes = axes.replace("T", "")

    if set(axes) - set("CZYX") or len(set(axes)) != len(axes):
        raise ValueError(f"暂不支持 TIFF 维度 {original_axes}；需要 ZYX、IYX、QYX、CZYX、ZCYX 或 TCZYX")
    if "Y" not in axes or "X" not in axes:
        raise ValueError("图像缺少 X/Y 空间维度")
    if "Z" not in axes:
        array = array[np.newaxis, ...]
        axes = "Z" + axes
    if "C" not in axes:
        array = array[np.newaxis, ...]
        axes = "C" + axes

    order = [axes.index(axis) for axis in "CZYX"]
    array = np.transpose(array, order)
    return [np.ascontiguousarray(channel) for channel in array], original_axes


def _display_range(channel: np.ndarray) -> tuple[float, float]:
    sample = channel[:: max(1, channel.shape[0] // 64)]
    low = float(np.min(sample))
    high = float(np.percentile(sample, 99.8))
    actual_high = float(np.max(sample))
    if high <= low:
        high = actual_high
    if high <= low:
        high = low + 1.0
    return low, high


def _preview_factor(shape: tuple[int, int, int], channel_count: int, max_voxels: int, max_size: int) -> int:
    return max(
        1,
        math.ceil((math.prod(shape) * channel_count / max_voxels) ** (1 / 3)),
        math.ceil(max(shape) / max_size),
    )


def _load_tiff(source: Path, max_voxels: int, max_size: int) -> VolumeData:
    with tifffile.TiffFile(source) as tif:
        if not tif.series:
            raise ValueError("TIFF 中没有可读取的图像")
        series = tif.series[0]
        array = series.asarray()
        voxel_size = _voxel_size(tif)

    if not np.issubdtype(array.dtype, np.number) or np.iscomplexobj(array):
        raise ValueError(f"不支持的数据类型：{array.dtype}")
    channels, original_axes = _as_channels(array, series.axes)
    if not channels or min(channels[0].shape) < 1:
        raise ValueError("图像数据为空")

    factor = _preview_factor(channels[0].shape, len(channels), max_voxels, max_size)
    if factor > 1:
        channels = [np.ascontiguousarray(channel[::factor, ::factor, ::factor]) for channel in channels]
        voxel_size = tuple(size * factor for size in voxel_size)

    return VolumeData(
        channels=channels,
        channel_names=[f"通道 {index + 1}" for index in range(len(channels))],
        voxel_size=voxel_size,
        source=source,
        original_axes=original_axes,
        downsample_factor=factor,
        display_ranges=[_display_range(channel) for channel in channels],
        voxel_scale=(factor, factor, factor),
    )


def _ims_text(value) -> str:
    array = np.asarray(value)
    if array.ndim > 0:
        return b"".join(array.tolist()).decode("utf-8", errors="replace") if array.dtype.kind == "S" else "".join(str(item) for item in array)
    item = array.item()
    return item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)


def _ims_number(group, key: str, default: float | None = None) -> float | None:
    try:
        return float(_ims_text(group.attrs[key]))
    except (KeyError, TypeError, ValueError):
        return default


def _load_ims(source: Path, max_voxels: int, max_size: int) -> VolumeData:
    import h5py

    try:
        with h5py.File(source, "r") as ims:
            dataset = ims["DataSet"]
            levels = sorted(
                (int(match.group(1)) for name in dataset if (match := re.fullmatch(r"ResolutionLevel (\d+)", name))),
            )
            if not levels:
                raise ValueError("IMS 中没有 ResolutionLevel 数据")
            if "TimePoint 0" not in dataset[f"ResolutionLevel {levels[0]}"]:
                raise ValueError("IMS 中没有第一时间点数据")

            selected_level = levels[-1]
            selected_shape = None
            factor = 1
            for level in levels:
                timepoint = dataset[f"ResolutionLevel {level}/TimePoint 0"]
                channel_indices = sorted(
                    int(match.group(1)) for name in timepoint if (match := re.fullmatch(r"Channel (\d+)", name))
                )
                if not channel_indices:
                    continue
                shape = timepoint[f"Channel {channel_indices[0]}/Data"].shape
                if len(shape) != 3:
                    raise ValueError(f"IMS 数据维度必须是 ZYX，实际为 {shape}")
                selected_level, selected_shape = level, shape
                factor = _preview_factor(shape, len(channel_indices), max_voxels, max_size)
                if factor == 1:
                    break
            if selected_shape is None:
                raise ValueError("IMS 中没有可读取的通道")

            timepoint = dataset[f"ResolutionLevel {selected_level}/TimePoint 0"]
            image_info = ims["DataSetInfo/Image"]
            full_shape = dataset[f"ResolutionLevel {levels[0]}/TimePoint 0/Channel 0/Data"].shape
            dimensions = [_ims_number(image_info, key, float(size)) or float(size) for key, size in zip("XYZ", full_shape[::-1])]
            valid_shape = tuple(
                min(storage, max(1, round(dimension * storage / full)))
                for dimension, storage, full in zip(dimensions[::-1], selected_shape, full_shape)
            )
            valid_slices = tuple(slice(0, size) for size in valid_shape)
            channels = [
                np.ascontiguousarray(timepoint[f"Channel {index}/Data"][valid_slices])
                for index in channel_indices
            ]
            extents = []
            for axis, size in zip("012", full_shape[::-1]):
                low = _ims_number(image_info, f"ExtMin{axis}", 0.0) or 0.0
                high = _ims_number(image_info, f"ExtMax{axis}", float(size))
                extents.append((high - low) if high is not None and high > low else float(size))
            unit_scale = {"um": 1.0, "µm": 1.0, "nm": 0.001, "mm": 1000.0, "cm": 10000.0, "m": 1e6}.get(
                _ims_text(image_info.attrs.get("Unit", "um")).lower(), 1.0
            )
            voxel_size = tuple(
                extent / dimension * full / current * factor * unit_scale
                for extent, dimension, full, current in zip(extents, dimensions, full_shape[::-1], selected_shape[::-1])
            )
            voxel_scale = tuple(full / current * factor for full, current in zip(full_shape[::-1], selected_shape[::-1]))

            names, colors, ranges = [], [], []
            default_colors = [(0.1, 1.0, 0.1), (1.0, 0.1, 0.1), (0.1, 0.8, 1.0), (1.0, 0.1, 1.0)]
            for index, channel in zip(channel_indices, channels):
                info = ims[f"DataSetInfo/Channel {index}"]
                names.append(_ims_text(info.attrs.get("Name", f"通道 {index + 1}")))
                try:
                    rgb = tuple(float(value) for value in _ims_text(info.attrs["Color"]).split())
                    colors.append(rgb if len(rgb) == 3 else default_colors[index % len(default_colors)])
                except (KeyError, TypeError, ValueError):
                    colors.append(default_colors[index % len(default_colors)])
                try:
                    low, high = (float(value) for value in _ims_text(info.attrs["ColorRange"]).split())
                    ranges.append((low, high) if high > low else _display_range(channel))
                except (KeyError, TypeError, ValueError):
                    ranges.append(_display_range(channel))
            view_state = read_view_state(ims, len(channels))
    except OSError as error:
        raise ValueError(f"无法读取 IMS/HDF5 文件：{error}") from error

    if factor > 1:
        channels = [np.ascontiguousarray(channel[::factor, ::factor, ::factor]) for channel in channels]
    return VolumeData(
        channels=channels,
        channel_names=names,
        voxel_size=voxel_size,
        source=source,
        original_axes=f"IMS ResolutionLevel {selected_level}",
        downsample_factor=factor,
        display_ranges=ranges,
        colors=colors,
        voxel_scale=voxel_scale,
        view_state=view_state,
    )


def load_volume(path: str | Path, max_voxels: int = 64_000_000, max_size: int = 1024) -> VolumeData:
    source = Path(path)
    if not source.is_file():
        raise ValueError(f"文件不存在：{source}")
    suffix = source.suffix.lower()
    if suffix == ".ims":
        return _load_ims(source, max_voxels, max_size)
    if suffix in (".tif", ".tiff"):
        return _load_tiff(source, max_voxels, max_size)
    raise ValueError("仅支持 .ims、.tif 和 .tiff 文件")
