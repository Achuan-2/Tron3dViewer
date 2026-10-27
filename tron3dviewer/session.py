"""Versioned display settings stored inside an IMS file."""

import json
import math

from .i18n import tr

VIEW_STATE_PATH = "tron3dviewer/ViewState"
# Persisted schemas remain readable after package and executable renames.
LEGACY_VIEW_STATE_PATHS = ("tron3d/ViewState", "OpenImaris/ViewState")


def validate_view_state(state: dict, channel_count: int) -> None:
    """Reject invalid settings before any camera or display controls change."""

    def numbers(values, count, *, positive=False, unit=False):
        if not isinstance(values, (list, tuple)) or len(values) != count:
            raise ValueError(tr("显示设置中的数值数量不正确"))
        for value in values:
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                raise ValueError(tr("显示设置包含无效数值"))
            if (positive and value <= 0) or (unit and not 0 <= value <= 1):
                raise ValueError(tr("显示设置的数值超出范围"))

    try:
        if state["version"] != 1 or state["background"] not in ("black", "white"):
            raise ValueError(tr("不支持的显示设置版本或背景"))
        camera = state["camera"]
        numbers([camera[key] for key in ("elevation", "azimuth", "roll", "fov")], 4)
        if not 0 <= camera["fov"] < 180:
            raise ValueError(tr("视角参数超出范围"))
        numbers(camera["center"], 3)
        numbers([camera["scale_factor"], camera["distance"]], 2, positive=True)
        numbers(state["axes"]["spacing"], 3, positive=True)
        if any(
            type(state["axes"]["visibility"][key]) is not bool
            for key in ("box", "grid", "ticks", "labels")
        ):
            raise ValueError(tr("坐标轴显示设置不正确"))
        channels = state["channels"]
        if not isinstance(channels, list) or len(channels) != channel_count:
            raise ValueError(tr("显示设置与图像通道数不一致"))
        if "normalization_ranges" in state:
            ranges = state["normalization_ranges"]
            if not isinstance(ranges, list) or len(ranges) != channel_count:
                raise ValueError(tr("显示归一化范围与通道数不一致"))
            for bounds in ranges:
                numbers(bounds, 2)
                if bounds[1] <= bounds[0]:
                    raise ValueError(tr("显示归一化范围不正确"))
        for channel in channels:
            numbers(channel["color"], 3, unit=True)
            numbers(channel["range"], 2)
            numbers([channel["gamma"]], 1, positive=True)
            numbers([channel["opacity"]], 1, unit=True)
            if (
                channel["range"][1] <= channel["range"][0]
                or type(channel["visible"]) is not bool
            ):
                raise ValueError(tr("通道显示设置不正确"))
        selected = state["selected_channel"]
        if type(selected) is not int or not 0 <= selected < channel_count:
            raise ValueError(tr("当前通道编号不正确"))
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(tr("显示设置不完整")) from error


def read_view_state(ims, channel_count: int) -> dict | None:
    path = next((path for path in (VIEW_STATE_PATH, *LEGACY_VIEW_STATE_PATHS) if path in ims), None)
    if path is None:
        return None
    try:
        state = json.loads(ims[path].asstr()[()])
        validate_view_state(state, channel_count)
        return state
    except (ValueError, TypeError, AttributeError):
        # Invalid or newer application settings must not make image data unreadable.
        return None
