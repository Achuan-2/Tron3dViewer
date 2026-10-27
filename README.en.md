<p align="center">
  <a href="README.md"><img src="https://img.shields.io/badge/语言-中文-lightgrey" alt="中文"></a>
  <a href="README.en.md"><img src="https://img.shields.io/badge/Language-English-blue" alt="English"></a>
</p>

<div align="center">
  <img src="openimaris/assets/icon.svg" alt="OpenImaris Logo" width="128">

  # OpenImaris

  **A lightweight, open-source 3D microscopy image viewer**

  Open IMS and TIFF volumes, interactively adjust channels and viewing angles, and export images for scientific publications.

  [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)](https://www.qt.io/qt-for-python)
  [![OpenGL](https://img.shields.io/badge/OpenGL-2.1%2B-5586A4)](https://www.opengl.org/)
</div>

## Features

- **3D volume rendering**: View IMS and multipage TIFF images using maximum intensity projection (MIP), with multichannel overlays.
- **Interactive views**: Rotate, pan, and zoom freely. Switch to XY, XZ, or YZ orthogonal views with one click, or set precise rotation angles.
- **Channel controls**: Independently adjust each channel's color, visibility, contrast, gamma, and opacity, with one-click automatic adjustment.
- **Spatial calibration**: Read voxel sizes from image metadata, or recalibrate using voxel sizes or overall physical dimensions without modifying the original file.
- **Customizable axes**: Show or hide the frame, grid, ticks, and labels independently, and customize tick spacing along X, Y, and Z.
- **High-quality exports**: Export PNG images at 1×, 2×, or 4× resolution, or PDFs with vector ticks and text for publication layouts.
- **Large-image previews**: Automatically downsample according to data size and adapt rendering quality during interaction to balance responsiveness and still-image quality.
- **Simple desktop interface**: A dark PySide6 interface displays image dimensions, channel count, voxel sizes, and physical dimensions in real time.

## Requirements

- Python **3.11 or later**
- A graphics card and driver supporting **OpenGL 2.1 or later**
- [uv](https://docs.astral.sh/uv/) is recommended for environment and dependency management

## Installation

### Using uv (recommended)

```bash
git clone https://github.com/Achuan-2/openimaris.git
cd openimaris
uv sync
```

### Using pip

Run the following in an existing Python 3.11+ environment:

```bash
git clone https://github.com/Achuan-2/openimaris.git
cd openimaris
python -m pip install .
```

## Usage

### Launch the application

With uv:

```bash
uv run openimaris
```

After installing with pip:

```bash
openimaris
```

You can also open an image directly at launch:

```bash
openimaris "path/to/image.ims"
openimaris "path/to/image.tif"
```

### View and adjust images

The interface currently uses Chinese labels; the relevant labels are included below for reference.

1. Click **Open 3D IMS / TIFF (打开三维 IMS / TIFF)**, or press `Ctrl+O` to select an image.
2. Select a channel in the **Channels (通道)** panel on the left and adjust its color, Min/Max, gamma, and opacity.
3. Use the **Spatial Calibration (空间校准)** and **Frame · Axes (Frame · 坐标轴)** panels to set physical dimensions, axis elements, and tick spacing.
4. Adjust the composition with the mouse or the **View and Rotation (视角与旋转)** panel.

| Action | Effect |
| --- | --- |
| Left-button drag | Rotate the 3D view |
| Right-button drag | Pan the image |
| Mouse wheel | Zoom in or out |

The View menu also provides a 3D view reset, XY/XZ/YZ orthogonal views, and Z-axis flipping.

### Export images

- **PNG**: Under **Export Current View (导出当前视角)**, select a 1×, 2×, or 4× scale, then click **Export PNG (导出 PNG)**.
- **PDF**: Click **Export PDF (Vector Text) (导出 PDF（矢量文字）)** and set the page width, page height, font size, and rendering scale. The 3D volume is embedded as a raster image, while axis ticks and text remain vector elements.
- Exports are also available from the File menu; `Ctrl+S` exports a PDF.

> Exports use the current view and display settings. Spatial calibration affects only display and export; it does not write changes back to the original image file.

## Supported Inputs

- **Imaris IMS**: Reads multichannel 3D data from the first time point and automatically selects a suitable resolution level.
- **TIFF**: Supports 3D stacks, multichannel data, and common ImageJ voxel-size metadata. Time series default to the first time point.

## Development

Set up the development environment and run the tests:

```bash
uv sync
uv run pytest
```
