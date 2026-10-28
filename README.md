<p align="center">
  <a href="README.md">中文</a> |
  <a href="README.en.md">English</a>
</p>

<div align="center">
  <img src="tron3dviewer/assets/icon.svg" alt="Tron 3D viewer Logo" width="128">

  # Tron 3D viewer

  **轻量级、开源的三维显微图像查看器**

  读取 IMS 与 TIFF 体数据，交互式调整通道和视角，导出适合论文排版的图像。

  [![DOI](https://zenodo.org/badge/1434662977.svg)](https://doi.org/10.5281/zenodo.23724954)
  [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)](https://www.qt.io/qt-for-python)
  [![OpenGL](https://img.shields.io/badge/OpenGL-2.1%2B-5586A4)](https://www.opengl.org/)
</div>

## 功能特性

- **三维体渲染**：支持渲染Zstack数据为三维体，支持多通道叠加，支持Tiff格式和Ims格式
- **高质量导出**：支持导出带有矢量文字的 PDF，便于后续论文排版。
- **数据兼容**：可打开ims文件以及保存文件为ims文件，便于与Imaris软件进行联动。


## 界面与导出效果

以下示例使用 retina 数据，叠加显示 CollagenIV（红色）和 GFAP（绿色）通道。

**软件界面**：在“通道与显示”面板中选择通道并调整显示参数。

![Tron 3D viewer 加载 retina 数据的软件界面](docs/images/retina-ui.png)

**PNG 导出效果**：保留黑色背景、三维边框和坐标轴。

![retina 数据的 PNG 导出效果](docs/images/retina-3d.png)

**PDF 导出效果**：下图由实际导出的 PDF 渲染，Frame 外部透明，在白色页面上预览；原 PDF 中的边框、网格、刻度与文字均为矢量。

![retina 数据的 PDF 导出效果，Frame 外部透明，白色页面预览](docs/images/retina-pdf.png)

## 安装

前往 [Releases](https://github.com/Achuan-2/tron3dviewer/releases/latest) 下载对应系统的安装包：

- **Windows**：下载 `.exe` 安装包并运行。
- **macOS**：下载 `.dmg` 安装包，打开后将应用拖入“应用程序”。

安装包已包含运行环境，无需单独安装 Python。

## 如何使用

启动应用后，即可打开 IMS 或 TIFF 图像。

### 查看与调整图像

1. 将 IMS / TIFF 文件直接拖入窗口，或点击 **打开三维 IMS / TIFF**、使用 `Ctrl+O` 选择图像。
2. 在左侧 **通道与显示** 面板中选择通道，调整颜色、Min/Max、Gamma 和不透明度。
3. 使用 **空间校准** 和 **Frame · 坐标轴** 面板设置物理尺寸、坐标轴元素与刻度间距。
4. 通过鼠标或 **视角与旋转** 面板调整构图。

X/Y/Z 刻度间距以整数显示，微调按钮每次增加或减少 50 µm。

| 操作 | 效果 |
| --- | --- |
| 左键拖动 | 旋转三维视角 |
| 右键拖动 | 平移图像 |
| 鼠标滚轮 | 缩放图像 |

视图菜单还提供三维视角重置、XY/XZ/YZ 正交视图和 Z 轴翻转。

### 保存 IMS

使用 **文件 → 保存 IMS**（`Ctrl+S`）或 **保存与导出 → 保存 IMS（含显示设置）**。打开 TIFF 时会提示另存为 IMS；打开 IMS 时直接保存到当前文件，也可用 `Ctrl+Shift+S` 另存一份。

保存保留原始分辨率数据，不会用降采样预览替代原图；已有 IMS 的分辨率层级、时间点和其他对象会一并保留。体素校准写入 IMS 图像元数据，视角和 Frame 等显示设置由 Tron 3D viewer 在重开时恢复。

Box、Grid、Ticks、Labels 的显示开关优先沿用软件记住的上次选择，无需保存 IMS 即可记忆。

### 导出图像

- **PNG**：在 **保存与导出** 中选择 1×、2× 或 4× 倍率，然后点击 **导出 PNG**。
- **PDF**：点击 **导出 PDF（矢量文字）**，设置成图宽高、字体大小和渲染倍率。宽高包含完整的坐标文字，自动去除外围留白；修改任一尺寸或字号，另一尺寸会按当前视角联动，保持三维图像比例。三维体数据以图像嵌入，坐标轴刻度与文字保持矢量。
- 也可通过文件菜单导出；`Ctrl+Shift+E` 对应 PDF 导出。

> 调整参数和导出图像不会改写源文件；执行“保存 IMS”时才将设置写入 IMS。

## 支持的输入

- **Imaris IMS**：读取第一时间点的多通道三维数据，自动选择合适的分辨率层级。
- **TIFF**：支持三维堆栈、多通道数据及常见 ImageJ 体素尺寸元数据；时间序列默认读取第一时间点。

## 开发

开发环境需要 Python **3.11 或更高版本**、支持 **OpenGL 2.1 或更高版本**的显卡及驱动，并使用 [uv](https://docs.astral.sh/uv/) 安装依赖和启动应用。

### 安装与启动

```bash
git clone https://github.com/Achuan-2/tron3dviewer.git
cd tron3dviewer
uv sync
uv run tron3dviewer
```

也可以在启动时直接打开图像：

```bash
uv run tron3dviewer "path/to/image.ims"
uv run tron3dviewer "path/to/image.tif"
```

### 运行测试

```bash
uv run pytest
```

## 用爱发电

欢迎给我买杯咖啡。

<img width="592" height="592" alt="赞助二维码" src="https://github.com/user-attachments/assets/7927f505-0b11-428c-906a-5a98a9e7d1ca" />

Non-Chinese users can use this link to [buy me a coffee](https://pancake.waffo.ai/store/achuan-2-fdbho4ye/product/PROD_3F7Aa7c2NQlz9KmxcgxjQ7?type=onetime&currency=USD).

## 许可证

本项目采用 [GNU Affero General Public License v3.0](LICENSE)（AGPL-3.0-only）开源。
