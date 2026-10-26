from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .data import VolumeData, load_volume
from .exporter import export_image
from .volume_view import CHANNEL_COLORS, VolumeView
from .widgets import ChannelGradientBar


class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("OpenImaris — 三维显微图像查看器")
        self.resize(1440, 900)
        self.data: VolumeData | None = None
        self.channel_settings: list[dict] = []
        self.updating_controls = False

        self.volume_view = VolumeView()
        self._create_menu()
        self._create_sidebar()
        self.statusBar().showMessage("打开 IMS / TIFF 图像开始三维查看；左键旋转，右键平移，滚轮缩放")
        if initial_path:
            QTimer.singleShot(0, lambda: self.open_volume(initial_path))

    def _create_menu(self) -> None:
        menu = self.menuBar().addMenu("文件(&F)")
        open_action = QAction("打开 IMS / TIFF…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.choose_file)
        menu.addAction(open_action)
        export_action = QAction("导出当前视角…", self)
        export_action.setShortcut(QKeySequence.StandardKey.Save)
        export_action.triggered.connect(self.export_current)
        menu.addAction(export_action)
        menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("视图(&V)")
        for label, callback in [
            ("重置三维视角", self.volume_view.reset_view),
            ("XY 顶视图", lambda: self.volume_view.set_view("xy")),
            ("XZ 侧视图", lambda: self.volume_view.set_view("xz")),
            ("YZ 侧视图", lambda: self.volume_view.set_view("yz")),
        ]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            view_menu.addAction(action)

    def _create_sidebar(self) -> None:
        panel = QWidget()
        panel.setMinimumWidth(325)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        open_button = QPushButton("打开三维 IMS / TIFF")
        open_button.setMinimumHeight(38)
        open_button.clicked.connect(self.choose_file)
        layout.addWidget(open_button)

        self.file_label = QLabel("尚未加载图像")
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.file_label)

        channel_group = QGroupBox("Display Adjustment · 通道")
        channel_layout = QVBoxLayout(channel_group)
        self.channel_list = QListWidget()
        self.channel_list.setMaximumHeight(86)
        self.channel_list.currentRowChanged.connect(self._select_channel)
        channel_layout.addWidget(self.channel_list)
        self.gradient_bar = ChannelGradientBar()
        channel_layout.addWidget(self.gradient_bar)
        channel_row = QHBoxLayout()
        self.visible_check = QCheckBox("显示通道")
        self.visible_check.toggled.connect(self._visibility_changed)
        self.color_button = QPushButton("通道颜色")
        self.color_button.clicked.connect(self._choose_color)
        channel_row.addWidget(self.visible_check)
        channel_row.addWidget(self.color_button)
        channel_layout.addLayout(channel_row)
        layout.addWidget(channel_group)

        display_group = QGroupBox("显示参数")
        form = QFormLayout(display_group)
        self.low_spin = self._range_spinbox()
        self.high_spin = self._range_spinbox()
        self.low_spin.valueChanged.connect(self._contrast_changed)
        self.high_spin.valueChanged.connect(self._contrast_changed)
        form.addRow("Min", self.low_spin)
        form.addRow("Max", self.high_spin)
        self.gamma_spin = QDoubleSpinBox()
        self.gamma_spin.setRange(0.1, 5.0)
        self.gamma_spin.setSingleStep(0.05)
        self.gamma_spin.setValue(1.0)
        self.gamma_spin.valueChanged.connect(self._gamma_changed)
        form.addRow("Gamma", self.gamma_spin)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        form.addRow("不透明度", self.opacity_slider)
        self.background_combo = QComboBox()
        self.background_combo.addItems(["黑色背景", "白色背景"])
        self.background_combo.currentIndexChanged.connect(
            lambda index: self.volume_view.set_background("black" if index == 0 else "white")
        )
        form.addRow("背景", self.background_combo)
        auto_button = QPushButton("自动调整所有通道")
        auto_button.clicked.connect(self.auto_adjust_channels)
        reset_channels_button = QPushButton("重置所有通道")
        reset_channels_button.clicked.connect(self.reset_channels)
        form.addRow(auto_button)
        form.addRow(reset_channels_button)
        layout.addWidget(display_group)

        spatial_group = QGroupBox("空间校准")
        spatial_form = QFormLayout(spatial_group)
        self.spatial_mode = QComboBox()
        self.spatial_mode.addItems(["体素大小 (µm/voxel)", "整体尺寸 (µm)"])
        self.spatial_mode.currentIndexChanged.connect(self._spatial_mode_changed)
        spatial_form.addRow("输入方式", self.spatial_mode)
        self.spatial_spins = []
        for axis in "XYZ":
            spin = QDoubleSpinBox()
            spin.setRange(1e-6, 1e9)
            spin.setDecimals(6)
            spin.setSingleStep(0.1)
            spin.setKeyboardTracking(False)
            self.spatial_spins.append(spin)
            spatial_form.addRow(f"{axis} 大小", spin)
        spatial_buttons = QHBoxLayout()
        apply_spatial = QPushButton("应用")
        apply_spatial.clicked.connect(self.apply_spatial_calibration)
        reset_spatial = QPushButton("恢复元数据")
        reset_spatial.clicked.connect(self.reset_spatial_calibration)
        spatial_buttons.addWidget(apply_spatial)
        spatial_buttons.addWidget(reset_spatial)
        spatial_form.addRow(spatial_buttons)
        layout.addWidget(spatial_group)

        axis_group = QGroupBox("Frame · 坐标轴")
        axis_layout = QVBoxLayout(axis_group)
        axis_checks = QHBoxLayout()
        self.axis_checks = {}
        for kind, label in [("box", "Box"), ("grid", "Grid"), ("ticks", "Ticks"), ("labels", "Labels")]:
            check = QCheckBox(label)
            check.setChecked(True)
            check.toggled.connect(lambda visible, name=kind: self.volume_view.set_axis_visible(name, visible))
            self.axis_checks[kind] = check
            axis_checks.addWidget(check)
        axis_layout.addLayout(axis_checks)
        spacing_form = QFormLayout()
        self.axis_spacing_spins = []
        for axis in "XYZ":
            spin = QDoubleSpinBox()
            spin.setRange(1e-6, 1e9)
            spin.setDecimals(3)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._axis_spacing_changed)
            self.axis_spacing_spins.append(spin)
            spacing_form.addRow(f"{axis} 刻度间距 (µm)", spin)
        axis_layout.addLayout(spacing_form)
        reset_spacing = QPushButton("自动刻度间距")
        reset_spacing.clicked.connect(self.reset_axis_spacing)
        axis_layout.addWidget(reset_spacing)
        layout.addWidget(axis_group)

        view_group = QGroupBox("视角")
        view_layout = QHBoxLayout(view_group)
        for label, name in [("三维", "iso"), ("XY", "xy"), ("XZ", "xz"), ("YZ", "yz")]:
            button = QPushButton(label)
            if name == "iso":
                button.clicked.connect(self.volume_view.reset_view)
            else:
                button.clicked.connect(lambda checked=False, value=name: self.volume_view.set_view(value))
            view_layout.addWidget(button)
        layout.addWidget(view_group)

        export_group = QGroupBox("导出当前视角")
        export_layout = QHBoxLayout(export_group)
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["1×", "2×（高清）", "4×（超清）"])
        self.scale_combo.setCurrentIndex(1)
        self.export_button = QPushButton("导出 PDF / PNG")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_current)
        export_layout.addWidget(self.scale_combo)
        export_layout.addWidget(self.export_button)
        layout.addWidget(export_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(360)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(panel)
        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(scroll)
        central_layout.addWidget(self.volume_view.native, 1)
        self.setCentralWidget(central)

    @staticmethod
    def _range_spinbox() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1e12, 1e12)
        spin.setDecimals(2)
        spin.setKeyboardTracking(False)
        return spin

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开三维显微图像",
            str(self.data.source.parent if self.data else Path.cwd()),
            "显微图像 (*.ims *.tif *.tiff);;Imaris 图像 (*.ims);;TIFF 图像 (*.tif *.tiff);;所有文件 (*)",
        )
        if path:
            self.open_volume(path)

    def open_volume(self, path: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("正在读取三维图像…")
        QApplication.processEvents()
        try:
            data = load_volume(path)
            self.volume_view.set_volume(data)
        except Exception as error:
            QMessageBox.critical(self, "无法打开图像", str(error))
            self.statusBar().showMessage("图像加载失败")
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.data = data
        self.original_voxel_size = data.voxel_size
        self._initialize_channels()
        self._update_file_info()
        self._refresh_spatial_controls()
        self._refresh_axis_controls()
        self.export_button.setEnabled(True)
        self.setWindowTitle(f"OpenImaris — {data.source.name}")
        self.statusBar().showMessage("加载完成；左键旋转，右键平移，滚轮缩放", 8000)

    def _update_file_info(self) -> None:
        assert self.data is not None
        z, y, x = self.data.shape
        sx, sy, sz = self.data.voxel_size
        width, height, depth = self.data.physical_size
        details = f"{self.data.source.name}\n{x} × {y} × {z} px，{len(self.data.channels)} 个通道"
        details += f"\n体素：{sx:.6g} × {sy:.6g} × {sz:.6g} µm"
        details += f"\n尺寸：{width:.6g} × {height:.6g} × {depth:.6g} µm"
        if self.data.downsample_factor > 1:
            details += f"\n预览降采样：{self.data.downsample_factor}×"
        self.file_label.setText(details)

    def _refresh_spatial_controls(self) -> None:
        assert self.data is not None
        values = self.data.voxel_size if self.spatial_mode.currentIndex() == 0 else self.data.physical_size
        self.updating_controls = True
        for spin, value in zip(self.spatial_spins, values):
            spin.setValue(value)
        self.updating_controls = False

    def _refresh_axis_controls(self) -> None:
        if self.volume_view.axis_spacing is None:
            return
        self.updating_controls = True
        for spin, value in zip(self.axis_spacing_spins, self.volume_view.axis_spacing):
            spin.setValue(value)
        self.updating_controls = False

    def _initialize_channels(self) -> None:
        assert self.data is not None
        self.channel_settings = []
        self.channel_list.clear()
        for index, name in enumerate(self.data.channel_names):
            rgb = self.data.colors[index] if self.data.colors else CHANNEL_COLORS[index % len(CHANNEL_COLORS)]
            self.channel_settings.append(
                {
                    "visible": True,
                    "color": rgb,
                    "opacity": 1.0,
                    "gamma": 1.0,
                    "range": self.data.display_ranges[index],
                }
            )
            self.channel_list.addItem(name)
        self.original_channel_settings = [dict(settings) for settings in self.channel_settings]
        self.channel_list.setCurrentRow(0)
        self._select_channel(0)

    def _select_channel(self, index: int) -> None:
        if not 0 <= index < len(self.channel_settings):
            return
        settings = self.channel_settings[index]
        self.updating_controls = True
        self.visible_check.setChecked(settings["visible"])
        self.opacity_slider.setValue(round(settings["opacity"] * 100))
        self.gamma_spin.setValue(settings["gamma"])
        low, high = settings["range"]
        self.low_spin.setValue(low)
        self.high_spin.setValue(high)
        color = QColor.fromRgbF(*settings["color"])
        self.color_button.setStyleSheet(f"background-color: {color.name()}; color: white;")
        self.updating_controls = False
        self._update_gradient()

    def _update_gradient(self) -> None:
        index = self.channel_list.currentRow()
        if self.data is None or index < 0:
            return
        settings = self.channel_settings[index]
        low, high = settings["range"]
        self.gradient_bar.set_display(
            self.data.channel_names[index], settings["color"], low, high, self.data.display_ranges[index], settings["gamma"]
        )

    def _visibility_changed(self, visible: bool) -> None:
        index = self.channel_list.currentRow()
        if self.updating_controls or index < 0:
            return
        self.channel_settings[index]["visible"] = visible
        self.volume_view.set_visible(index, visible)

    def _opacity_changed(self, value: int) -> None:
        index = self.channel_list.currentRow()
        if self.updating_controls or index < 0:
            return
        self.channel_settings[index]["opacity"] = value / 100
        self.volume_view.set_opacity(index, value / 100)

    def _choose_color(self) -> None:
        index = self.channel_list.currentRow()
        if index < 0:
            return
        current = QColor.fromRgbF(*self.channel_settings[index]["color"])
        color = QColorDialog.getColor(current, self, "选择通道颜色")
        if color.isValid():
            rgb = color.redF(), color.greenF(), color.blueF()
            self.channel_settings[index]["color"] = rgb
            self.volume_view.set_color(index, rgb)
            self.color_button.setStyleSheet(f"background-color: {color.name()}; color: white;")
            self._update_gradient()

    def _contrast_changed(self) -> None:
        index = self.channel_list.currentRow()
        if self.updating_controls or index < 0:
            return
        low, high = self.low_spin.value(), self.high_spin.value()
        if high <= low:
            return
        self.channel_settings[index]["range"] = (low, high)
        self.volume_view.set_contrast(index, low, high)
        self._update_gradient()

    def _gamma_changed(self, gamma: float) -> None:
        index = self.channel_list.currentRow()
        if self.updating_controls or index < 0:
            return
        self.channel_settings[index]["gamma"] = gamma
        self.volume_view.set_gamma(index, gamma)
        self._update_gradient()

    def auto_adjust_channels(self) -> None:
        if self.data is None:
            return
        for index, channel in enumerate(self.data.channels):
            sample = channel[:: max(1, channel.shape[0] // 64)]
            low = float(np.min(sample))
            high = float(np.percentile(sample, 99.8))
            if high <= low:
                high = float(np.max(sample))
            if high <= low:
                high = low + 1.0
            self.channel_settings[index]["range"] = (low, high)
            self.volume_view.set_contrast(index, low, high)
        self._select_channel(self.channel_list.currentRow())
        self.statusBar().showMessage("已按 99.8% 百分位自动调整所有通道", 5000)

    def reset_channels(self) -> None:
        if self.data is None:
            return
        self.channel_settings = [dict(settings) for settings in self.original_channel_settings]
        for index, settings in enumerate(self.channel_settings):
            low, high = settings["range"]
            self.volume_view.set_visible(index, settings["visible"])
            self.volume_view.set_opacity(index, settings["opacity"])
            self.volume_view.set_gamma(index, settings["gamma"])
            self.volume_view.set_color(index, settings["color"])
            self.volume_view.set_contrast(index, low, high)
        self._select_channel(self.channel_list.currentRow())
        self.statusBar().showMessage("已恢复所有通道的原始显示设置", 5000)

    def _spatial_mode_changed(self) -> None:
        if self.data is not None and not self.updating_controls:
            self._refresh_spatial_controls()

    def apply_spatial_calibration(self) -> None:
        if self.data is None:
            return
        values = tuple(spin.value() for spin in self.spatial_spins)
        if not all(math.isfinite(value) and value > 0 for value in values):
            QMessageBox.warning(self, "空间校准", "X/Y/Z 尺寸必须是大于 0 的有限数值")
            return
        if self.spatial_mode.currentIndex() == 1:
            z, y, x = self.data.shape
            values = tuple(value / pixels for value, pixels in zip(values, (x, y, z)))
        self.volume_view.update_spatial_calibration(values)
        self._update_file_info()
        self._refresh_spatial_controls()
        self.reset_axis_spacing()
        self.statusBar().showMessage("空间尺寸已更新；原始文件未被修改", 5000)

    def reset_spatial_calibration(self) -> None:
        if self.data is None:
            return
        self.volume_view.update_spatial_calibration(self.original_voxel_size)
        self._update_file_info()
        self._refresh_spatial_controls()
        self.reset_axis_spacing()

    def _axis_spacing_changed(self) -> None:
        if self.data is None or self.updating_controls:
            return
        spacing = tuple(spin.value() for spin in self.axis_spacing_spins)
        self.volume_view.set_axis_spacing(spacing)

    def reset_axis_spacing(self) -> None:
        self.volume_view.reset_axis_spacing()
        self._refresh_axis_controls()

    def export_current(self) -> None:
        if self.data is None:
            return
        default_path = self.data.source.with_name(self.data.source.stem + "_3D.pdf")
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出当前三维视角",
            str(default_path),
            "PDF 文档 (*.pdf);;PNG 图像 (*.png)",
        )
        if not path:
            return
        destination = Path(path)
        if not destination.suffix:
            destination = destination.with_suffix(".png" if "PNG" in selected_filter else ".pdf")
        scale = (1, 2, 4)[self.scale_combo.currentIndex()]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage("正在渲染并导出…")
        QApplication.processEvents()
        try:
            size = export_image(self.volume_view, destination, scale)
        except Exception as error:
            QMessageBox.critical(self, "导出失败", str(error))
            self.statusBar().showMessage("导出失败")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"已导出 {destination.name}（{size[0]} × {size[1]}）", 10000)
        QMessageBox.information(self, "导出完成", f"已保存：\n{destination}\n\n图像尺寸：{size[0]} × {size[1]}")
