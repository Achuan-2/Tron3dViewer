"""Save native image data and tron3dviewer display settings in one IMS file."""

import json
import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import h5py
import numpy as np
import tifffile
from PIL import Image

from .data import VolumeData, _as_channels, _ims_number, _ims_text
from .i18n import tr
from .session import VIEW_STATE_PATH, validate_view_state


def _attributes(group, **values) -> None:
    for key, value in values.items():
        # IMS metadata is stored as arrays of single-byte characters.
        group.attrs[key] = np.frombuffer(str(value).encode("utf-8"), dtype="S1")


def _write_channel(group, pixels: np.ndarray) -> None:
    supported = {("u", 1), ("u", 2), ("u", 4), ("f", 4)}
    if (pixels.dtype.kind, pixels.dtype.itemsize) not in supported:
        raise ValueError(
            tr(
                "IMS 不支持 {dtype}，请先转换为 uint8、uint16、uint32 或 float32",
                dtype=pixels.dtype,
            )
        )
    chunks = tuple(
        min(size, block) for size, block in zip(pixels.shape, (16, 128, 128))
    )
    group.create_dataset(
        "Data", data=pixels, chunks=chunks, compression="gzip", compression_opts=3
    )
    low, high = float(np.nanmin(pixels)), float(np.nanmax(pixels))
    if not np.isfinite((low, high)).all():
        raise ValueError(tr("图像没有可保存的有限像素值"))
    histogram = np.zeros(256, dtype=np.uint64)
    for start in range(0, pixels.shape[0], chunks[0]):
        counts, _ = np.histogram(
            pixels[start : start + chunks[0]],
            bins=256,
            range=(low, high if high > low else low + 1),
        )
        histogram += counts.astype(np.uint64)
    group.create_dataset("Histogram", data=histogram)
    _attributes(
        group,
        ImageSizeX=pixels.shape[2],
        ImageSizeY=pixels.shape[1],
        ImageSizeZ=pixels.shape[0],
        HistogramMin=low,
        HistogramMax=high if high > low else low + 1,
    )


def _write_tiff_data(ims, source: Path) -> None:
    # Re-read native pixels instead of serialising the potentially decimated preview.
    with tifffile.TiffFile(source) as tif:
        series = tif.series[0]
        pixels, axes = series.asarray(), series.axes
    count = pixels.shape[axes.index("T")] if "T" in axes else 1
    now = datetime.now()
    time_info = ims.require_group("DataSetInfo/TimeInfo")
    _attributes(time_info, DatasetTimePoints=count, FileTimePoints=count)
    for time in range(count):
        frame = np.take(pixels, time, axis=axes.index("T")) if "T" in axes else pixels
        channels, _ = _as_channels(frame, axes.replace("T", ""))
        for index, channel in enumerate(channels):
            group = ims.require_group(
                f"DataSet/ResolutionLevel 0/TimePoint {time}/Channel {index}"
            )
            _write_channel(group, channel)
        _attributes(
            time_info,
            **{
                f"TimePoint{time + 1}": (now + timedelta(seconds=time)).strftime(
                    "%Y-%m-%d %H:%M:%S.000"
                )
            },
        )
    _attributes(
        ims,
        ImarisDataSet="ImarisDataSet",
        ImarisVersion="5.5.0",
        DataSetDirectoryName="DataSet",
        DataSetInfoDirectoryName="DataSetInfo",
        ThumbnailDirectoryName="Thumbnail",
    )
    _attributes(
        ims.require_group("DataSetInfo/ImarisDataSet"),
        Creator="tron3dviewer",
        NumberOfImages=1,
        Version="5.5",
    )
    _attributes(
        ims.require_group("DataSetInfo/Image"),
        X=channels[0].shape[2],
        Y=channels[0].shape[1],
        Z=channels[0].shape[0],
        Noc=len(channels),
        Name=source.name,
    )


def _write_thumbnail(ims, data: VolumeData, state: dict) -> None:
    rgb = np.zeros((*data.shape[1:], 3), dtype=np.float32)
    for pixels, channel in zip(data.channels, state["channels"]):
        if not channel["visible"]:
            continue
        low, high = channel["range"]
        projection = np.nanmax(pixels, axis=0).astype(np.float32)
        intensity = np.clip((projection - low) / (high - low), 0, 1) ** (
            1 / channel["gamma"]
        )
        rgb += intensity[..., None] * np.asarray(channel["color"]) * channel["opacity"]
    image = Image.fromarray((rgb.clip(0, 1) * 255).astype(np.uint8))
    image.thumbnail((256, 256))
    thumbnail = Image.new("RGBA", (256, 256), "black")
    thumbnail.paste(image, ((256 - image.width) // 2, (256 - image.height) // 2))
    group = ims.require_group("Thumbnail")
    if "Data" in group:
        del group["Data"]
    group.create_dataset("Data", data=np.asarray(thumbnail).reshape(256, 1024))


def _write_settings(ims, data: VolumeData, state: dict, destination: Path) -> None:
    image = ims.require_group("DataSetInfo/Image")
    full = ims["DataSet/ResolutionLevel 0/TimePoint 0/Channel 0/Data"]
    dimensions = [
        _ims_number(image, key, size) for key, size in zip("XYZ", full.shape[::-1])
    ]
    unit = _ims_text(image.attrs.get("Unit", "um")).lower()
    unit_scale = {"um": 1, "µm": 1, "nm": 0.001, "mm": 1000, "cm": 10000, "m": 1e6}.get(
        unit, 1
    )
    for axis, (size, voxel, scale) in enumerate(
        zip(dimensions, data.voxel_size, data.voxel_scale)
    ):
        low = (_ims_number(image, f"ExtMin{axis}", 0) or 0) * unit_scale
        _attributes(
            image, **{f"ExtMin{axis}": low, f"ExtMax{axis}": low + size * voxel / scale}
        )
    _attributes(image, Unit="um")
    for index, channel in enumerate(state["channels"]):
        _attributes(
            ims.require_group(f"DataSetInfo/Channel {index}"),
            Name=data.channel_names[index],
            Color=" ".join(str(value) for value in channel["color"]),
            ColorMode="BaseColor",
            ColorRange=" ".join(str(value) for value in channel["range"]),
            ColorOpacity=channel["opacity"],
        )
    _attributes(
        ims.require_group("DataSetInfo/Imaris"),
        Filename=destination.name,
        Version="5.5",
        ThumbnailMode="thumbnailMIP",
    )
    if VIEW_STATE_PATH in ims:
        del ims[VIEW_STATE_PATH]
    ims.require_group("tron3dviewer").create_dataset(
        "ViewState",
        data=json.dumps(state, ensure_ascii=False, allow_nan=False),
        dtype=h5py.string_dtype("utf-8"),
    )
    _write_thumbnail(ims, data, state)


def save_ims(data: VolumeData, path: str | Path, state: dict) -> None:
    """Save atomically; preserve all resolutions, times and objects of an IMS source."""
    destination = Path(path)
    if destination.suffix.lower() != ".ims":
        raise ValueError(tr("保存文件的扩展名必须为 .ims"))
    if not data.source.is_file():
        raise ValueError(tr("原始图像文件不存在，无法保存完整分辨率数据"))
    validate_view_state(state, len(data.channels))
    if not all(
        np.isfinite(value) and value > 0
        for value in (*data.voxel_size, *data.voxel_scale)
    ):
        raise ValueError(tr("体素大小必须为大于 0 的有限数值"))
    handle, name = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".ims", dir=destination.parent
    )
    os.close(handle)
    temporary = Path(name)
    try:
        if data.source.suffix.lower() == ".ims":
            shutil.copyfile(data.source, temporary)
            mode = "r+"
        elif data.source.suffix.lower() in (".tif", ".tiff"):
            mode = "w"
        else:
            raise ValueError(tr("仅支持将 IMS 或 TIFF 图像保存为 IMS"))
        with h5py.File(temporary, mode) as ims:
            if mode == "w":
                _write_tiff_data(ims, data.source)
            _write_settings(ims, data, state, destination)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
