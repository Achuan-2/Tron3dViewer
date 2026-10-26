from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication

from .volume_view import VolumeView


def render_image(view: VolumeView, scale: int = 1) -> Image.Image:
    if view.data is None:
        raise ValueError("请先打开一幅三维图像")
    if scale not in (1, 2, 4):
        raise ValueError("导出倍率必须是 1、2 或 4")

    original_size = view.canvas.size
    width, height = original_size
    target = width * scale, height * scale
    if max(target) > 8192:
        raise ValueError(f"导出尺寸 {target[0]} × {target[1]} 过大，请选择较低倍率")

    try:
        view.canvas.size = target
        view.canvas.update()
        QApplication.processEvents()
        pixels = view.canvas.render()
    finally:
        view.canvas.size = original_size
        view.canvas.update()
        QApplication.processEvents()

    array = np.asarray(pixels)
    if array.ndim != 3 or array.shape[0] < 1 or array.shape[1] < 1:
        raise RuntimeError("三维画面捕获失败")
    return Image.fromarray(array, mode="RGBA")


def export_image(view: VolumeView, path: str | Path, scale: int = 1) -> tuple[int, int]:
    destination = Path(path)
    image = render_image(view, scale)
    suffix = destination.suffix.lower()
    if suffix == ".png":
        image.save(destination, format="PNG", dpi=(144 * scale, 144 * scale))
    elif suffix == ".pdf":
        resolution = 144 * scale
        image.convert("RGB").save(
            destination,
            format="PDF",
            resolution=resolution,
            title=view.data.source.name if view.data else "OpenImaris rendering",
            author="OpenImaris",
            subject="3D microscopy volume rendering",
            quality=95,
            subsampling=0,
        )
    else:
        raise ValueError("导出格式必须是 .pdf 或 .png")
    return image.size
