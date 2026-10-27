<div align="center">
  <img src="openimaris/assets/icon.svg" alt="OpenImaris Logo" width="128">

  # OpenImaris

  **轻量级、开源的三维显微图像查看器**

  读取 IMS 与 TIFF 体数据，交互式调整通道和视角，导出适合论文排版的图像。

  [![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![PySide6](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)](https://www.qt.io/qt-for-python)
  [![OpenGL](https://img.shields.io/badge/OpenGL-2.1%2B-5586A4)](https://www.opengl.org/)
</div>

## 功能特性

- **三维体渲染**：以最大强度投影（MIP）显示 IMS 和多页 TIFF 图像，支持多通道叠加。
- **交互式视角**：自由旋转、平移和缩放，一键切换 XY、XZ、YZ 正交视图，也可精确设置旋转角度。
- **通道显示调整**：独立控制每个通道的颜色、可见性、对比度、Gamma 和不透明度，支持一键自动调整。
- **空间校准**：读取图像元数据中的体素尺寸，也可按体素大小或整体物理尺寸重新校准，不修改原始文件。
- **可定制坐标轴**：分别显示或隐藏边框、网格、刻度和标签，支持自定义 X/Y/Z 刻度间距。
- **高质量导出**：导出 1×、2× 或 4× PNG，以及带矢量刻度与文字的 PDF，便于后续论文排版。
- **大图像预览**：根据数据规模自动降采样，交互时动态调整渲染质量，兼顾流畅度与静止画面质量。
- **简洁桌面界面**：基于 PySide6 的深色界面，实时显示图像尺寸、通道数、体素大小和物理尺寸。

## 环境要求

- Python **3.11 或更高版本**
- 支持 **OpenGL 2.1 或更高版本**的显卡及驱动
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理环境和依赖

## 安装

### 使用 uv（推荐）

```bash
git clone https://github.com/Achuan-2/openimaris.git
cd openimaris
uv sync
```

### 使用 pip

在已有的 Python 3.11+ 环境中执行：

```bash
git clone https://github.com/Achuan-2/openimaris.git
cd openimaris
python -m pip install .
```

## 如何使用

### 启动应用

使用 uv：

```bash
uv run openimaris
```

使用 pip 安装后：

```bash
openimaris
```

也可以在启动时直接打开图像：

```bash
openimaris "path/to/image.ims"
openimaris "path/to/image.tif"
```

### 查看与调整图像

1. 点击 **打开三维 IMS / TIFF**，或使用 `Ctrl+O` 选择图像。
2. 在左侧 **通道** 面板中选择通道，调整颜色、Min/Max、Gamma 和不透明度。
3. 使用 **空间校准** 和 **Frame · 坐标轴** 面板设置物理尺寸、坐标轴元素与刻度间距。
4. 通过鼠标或 **视角与旋转** 面板调整构图。

| 操作 | 效果 |
| --- | --- |
| 左键拖动 | 旋转三维视角 |
| 右键拖动 | 平移图像 |
| 鼠标滚轮 | 缩放图像 |

视图菜单还提供三维视角重置、XY/XZ/YZ 正交视图和 Z 轴翻转。

### 导出图像

- **PNG**：在 **导出当前视角** 中选择 1×、2× 或 4× 倍率，然后点击 **导出 PNG**。
- **PDF**：点击 **导出 PDF（矢量文字）**，设置页面宽高、字体大小和渲染倍率。三维体数据以图像嵌入，坐标轴刻度与文字保持矢量。
- 也可通过文件菜单导出；`Ctrl+S` 对应 PDF 导出。

> 导出内容基于当前视角和显示设置。空间校准仅影响显示与导出，不会写回原始图像文件。

## 支持的输入

- **Imaris IMS**：读取第一时间点的多通道三维数据，自动选择合适的分辨率层级。
- **TIFF**：支持三维堆栈、多通道数据及常见 ImageJ 体素尺寸元数据；时间序列默认读取第一时间点。

## 开发

安装开发环境并运行测试：

```bash
uv sync
uv run pytest
```
