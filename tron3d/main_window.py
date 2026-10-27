from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSettings, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .data import VolumeData, load_volume
from .exporter import export_pdf, export_png
from .i18n import LANGUAGES, current_language, set_language, tr
from .ims import save_ims
from .volume_view import CHANNEL_COLORS, VolumeView
from .widgets import (
    ChannelGradientBar, NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSlider, PdfExportDialog,
)


class MainWindow(QMainWindow):
    def __init__(self, initial_path: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Tron 3D viewer — 三维显微图像查看器")
        self.resize(1440, 900)
        self.data: VolumeData | None = None
        self.channel_settings: list[dict] = []
        self.updating_controls = False
        self.settings = QSettings("Tron 3D viewer", "Tron 3D viewer")
        saved_language = self.settings.value("language", current_language())
        if saved_language in LANGUAGES:
            set_language(saved_language)

        self.volume_view = VolumeView()
        self._create_menu()
        self._create_sidebar()
        self._bind_static_text()
        self.retranslate_ui()
        self.statusBar().showMessage(tr("打开 IMS / TIFF 图像开始三维查看；左键旋转，右键平移，滚轮缩放"))
        if initial_path:
            QTimer.singleShot(0, lambda: self.open_volume(initial_path))

    def _create_menu(self) -> None:
        menu = self.menuBar().addMenu("文件(&F)")
        open_action = QAction("打开 IMS / TIFF…", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.choose_file)
        menu.addAction(open_action)
        self.save_action = QAction("保存 IMS", self)
        self.save_action.setShortcut(QKeySequence.StandardKey.Save)
        self.save_action.setEnabled(False)
        self.save_action.triggered.connect(self.save_current)
        menu.addAction(self.save_action)
        self.save_as_action = QAction("另存为 IMS…", self)
        self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.save_as_action.setEnabled(False)
        self.save_as_action.triggered.connect(self.save_as_ims)
        menu.addAction(self.save_as_action)
        menu.addSeparator()
        export_pdf_action = QAction("导出矢量文字 PDF…", self)
        export_pdf_action.setShortcut(QKeySequence("Ctrl+Shift+E"))
        export_pdf_action.triggered.connect(self.export_pdf_current)
        menu.addAction(export_pdf_action)
        export_png_action = QAction("导出 PNG…", self)
        export_png_action.triggered.connect(self.export_png_current)
        menu.addAction(export_png_action)
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
            ("Z 翻转 180°", self.volume_view.flip_z),
        ]:
            action = QAction(label, self)
            action.triggered.connect(callback)
            view_menu.addAction(action)

        language_menu = self.menuBar().addMenu("语言(&L)")
        language_group = QActionGroup(self)
        self.language_actions = {}
        for language, label in LANGUAGES.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(language == current_language())
            action.triggered.connect(lambda checked=False, value=language: self.set_language(value))
            language_group.addAction(action)
            language_menu.addAction(action)
            self.language_actions[language] = action

    def _bind_static_text(self) -> None:
        self._text_bindings = []
        language_actions = set(self.language_actions.values())
        for action in self.findChildren(QAction):
            if action not in language_actions and action.text():
                self._text_bindings.append((action.setText, action.text()))
        for widget in self.findChildren(QWidget):
            if widget is not self.file_label and isinstance(widget, (QAbstractButton, QLabel)) and widget.text():
                self._text_bindings.append((widget.setText, widget.text()))
            if isinstance(widget, QGroupBox) and widget.title():
                self._text_bindings.append((widget.setTitle, widget.title()))
            if widget.toolTip():
                self._text_bindings.append((widget.setToolTip, widget.toolTip()))
        for menu in self.menuBar().findChildren(type(self.menuBar().actions()[0].menu())):
            self._text_bindings.append((menu.setTitle, menu.title()))
        self._combo_bindings = [
            (combo, index, combo.itemText(index))
            for combo in self.findChildren(NoWheelComboBox)
            for index in range(combo.count())
        ]
        self._tab_keys = [self.tabs.tabText(index) for index in range(self.tabs.count())]

    def retranslate_ui(self) -> None:
        for setter, text in self._text_bindings:
            setter(tr(text))
        for combo, index, text in self._combo_bindings:
            with QSignalBlocker(combo):
                combo.setItemText(index, tr(text))
        for index, text in enumerate(self._tab_keys):
            self.tabs.setTabText(index, tr(text))
        self.setWindowTitle(f"Tron 3D viewer — {self.data.source.name}" if self.data else tr("Tron 3D viewer — 三维显微图像查看器"))
        if self.data is not None:
            self._update_file_info()
        else:
            self.file_label.setText(tr("尚未加载图像"))

    def set_language(self, language: str) -> None:
        set_language(language)
        self.settings.setValue("language", language)
        self.language_actions[language].setChecked(True)
        self.retranslate_ui()
        self.statusBar().showMessage(tr("打开 IMS / TIFF 图像开始三维查看；左键旋转，右键平移，滚轮缩放"), 5000)

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
        self.gamma_spin = NoWheelDoubleSpinBox()
        self.gamma_spin.setRange(0.1, 5.0)
        self.gamma_spin.setSingleStep(0.05)
        self.gamma_spin.setValue(1.0)
        self.gamma_spin.valueChanged.connect(self._gamma_changed)
        form.addRow("Gamma", self.gamma_spin)
        self.opacity_slider = NoWheelSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(1, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self._opacity_changed)
        form.addRow("不透明度", self.opacity_slider)
        self.background_combo = NoWheelComboBox()
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
        self.spatial_mode = NoWheelComboBox()
        self.spatial_mode.addItems(["体素大小 (µm/voxel)", "整体尺寸 (µm)"])
        self.spatial_mode.setCurrentIndex(1)
        self.spatial_mode.currentIndexChanged.connect(self._spatial_mode_changed)
        spatial_form.addRow("输入方式", self.spatial_mode)
        self.spatial_spins = []
        for axis in "XYZ":
            spin = NoWheelDoubleSpinBox()
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
            spin = NoWheelDoubleSpinBox()
            spin.setDecimals(0)
            spin.setRange(1, 1e9)
            spin.setSingleStep(50)
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._axis_spacing_changed)
            self.axis_spacing_spins.append(spin)
            spacing_form.addRow(f"{axis} 刻度间距 (µm)", spin)
        axis_layout.addLayout(spacing_form)
        reset_spacing = QPushButton("自动刻度间距")
        reset_spacing.clicked.connect(self.reset_axis_spacing)
        axis_layout.addWidget(reset_spacing)
        layout.addWidget(axis_group)

        view_group = QGroupBox("视角与旋转")
        view_layout = QVBoxLayout(view_group)
        view_buttons = QHBoxLayout()
        for label, name in [("三维", "iso"), ("XY", "xy"), ("XZ", "xz"), ("YZ", "yz")]:
            button = QPushButton(label)
            if name == "iso":
                button.clicked.connect(self.volume_view.reset_view)
            else:
                button.clicked.connect(lambda checked=False, value=name: self.volume_view.set_view(value))
            view_buttons.addWidget(button)
        flip_button = QPushButton("Z 翻转")
        flip_button.clicked.connect(self.volume_view.flip_z)
        view_buttons.addWidget(flip_button)
        view_layout.addLayout(view_buttons)
        rotation_form = QFormLayout()
        self.rotation_spins = []
        for axis, tooltip in [("X（俯仰）", "左键上下拖动可连续旋转，越过顶部或底部即可翻转 Z"), ("Y（滚转）", "绕视线滚转，180° 可翻转 Z"), ("Z（方位）", "绕 Z 轴旋转")]:
            spin = NoWheelDoubleSpinBox()
            spin.setRange(-360.0, 360.0)
            spin.setDecimals(1)
            spin.setSingleStep(5.0)
            spin.setSuffix("°")
            spin.setToolTip(tooltip)
            spin.setKeyboardTracking(True)
            spin.valueChanged.connect(self._rotation_changed)
            self.rotation_spins.append(spin)
            rotation_form.addRow(f"{axis} 角度", spin)
        view_layout.addLayout(rotation_form)
        self.volume_view.view_changed_callback = self._refresh_rotation_controls
        self._refresh_rotation_controls()
        layout.addWidget(view_group)

        export_group = QGroupBox("保存与导出")
        export_layout = QVBoxLayout(export_group)
        self.save_ims_button = QPushButton("保存 IMS（含显示设置）")
        self.save_ims_button.setEnabled(False)
        self.save_ims_button.clicked.connect(self.save_current)
        export_layout.addWidget(self.save_ims_button)
        self.export_pdf_button = QPushButton("导出 PDF（矢量文字）")
        self.export_pdf_button.setEnabled(False)
        self.export_pdf_button.clicked.connect(self.export_pdf_current)
        export_layout.addWidget(self.export_pdf_button)
        png_row = QHBoxLayout()
        self.scale_combo = NoWheelComboBox()
        self.scale_combo.addItems(["1×", "2×（高清）", "4×（超清）"])
        self.scale_combo.setCurrentIndex(1)
        self.export_png_button = QPushButton("导出 PNG")
        self.export_png_button.setEnabled(False)
        self.export_png_button.clicked.connect(self.export_png_current)
        png_row.addWidget(self.export_png_button)
        png_row.addWidget(self.scale_combo)
        export_layout.addLayout(png_row)
        layout.addWidget(export_group)

        self.tabs = QTabWidget()
        for label, group in [
            ("空间校准", spatial_group),
            ("通道", channel_group),
            ("显示", display_group),
            ("坐标轴", axis_group),
            ("视角", view_group),
            ("导出", export_group),
        ]:
            layout.removeWidget(group)
            tab_page = QWidget()
            tab_layout = QVBoxLayout(tab_page)
            tab_layout.setContentsMargins(0, 0, 0, 0)
            tab_layout.addWidget(group)
            tab_layout.addStretch(1)
            self.tabs.addTab(tab_page, label)
        layout.addWidget(self.tabs, 1)
        panel.setFixedWidth(360)

        central = QWidget()
        central_layout = QHBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(panel)
        central_layout.addWidget(self.volume_view.native, 1)
        self.setCentralWidget(central)

    @staticmethod
    def _range_spinbox() -> NoWheelDoubleSpinBox:
        spin = NoWheelDoubleSpinBox()
        spin.setRange(-1e12, 1e12)
        spin.setDecimals(2)
        spin.setKeyboardTracking(False)
        return spin

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("打开三维显微图像"),
            str(self.data.source.parent if self.data else Path.cwd()),
            tr("显微图像 (*.ims *.tif *.tiff);;Imaris 图像 (*.ims);;TIFF 图像 (*.tif *.tiff);;所有文件 (*)"),
        )
        if path:
            self.open_volume(path)

    def open_volume(self, path: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(tr("正在读取三维图像…"))
        QApplication.processEvents()
        try:
            data = load_volume(path)
            self.volume_view.set_volume(data)
        except Exception as error:
            QMessageBox.critical(self, tr("无法打开图像"), str(error))
            self.statusBar().showMessage(tr("图像加载失败"))
            return
        finally:
            QApplication.restoreOverrideCursor()

        self.data = data
        self.original_voxel_size = data.voxel_size
        self._initialize_channels()
        self._update_file_info()
        self._refresh_spatial_controls()
        self._refresh_axis_controls()
        self.export_png_button.setEnabled(True)
        self.export_pdf_button.setEnabled(True)
        self.save_action.setEnabled(True)
        self.save_as_action.setEnabled(True)
        self.save_ims_button.setEnabled(True)
        with QSignalBlocker(self.background_combo):
            self.background_combo.setCurrentIndex(int(self.volume_view.background == "white"))
        self.setWindowTitle(f"Tron 3D viewer — {data.source.name}")
        message = tr("加载完成，已恢复保存的显示设置") if data.view_state else tr("加载完成；左键旋转，右键平移，滚轮缩放")
        self.statusBar().showMessage(message, 8000)

    def _update_file_info(self) -> None:
        assert self.data is not None
        z, y, x = self.data.shape
        sx, sy, sz = self.data.voxel_size
        width, height, depth = self.data.physical_size
        details = tr("{name}\n{x} × {y} × {z} px，{channels} 个通道", name=self.data.source.name, x=x, y=y, z=z, channels=len(self.data.channels))
        details += tr("\n体素：{x} × {y} × {z} µm", x=f"{sx:.6g}", y=f"{sy:.6g}", z=f"{sz:.6g}")
        details += tr("\n尺寸：{x} × {y} × {z} µm", x=f"{width:.6g}", y=f"{height:.6g}", z=f"{depth:.6g}")
        if self.data.downsample_factor > 1:
            details += tr("\n预览降采样：{factor}×", factor=self.data.downsample_factor)
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
        for kind, check in self.axis_checks.items():
            with QSignalBlocker(check):
                check.setChecked(self.volume_view.axes.visibility[kind])

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
        if self.data.view_state:
            self.channel_settings = [dict(settings) for settings in self.data.view_state["channels"]]
        selected = self.data.view_state["selected_channel"] if self.data.view_state else 0
        self.channel_list.setCurrentRow(selected)
        self._select_channel(selected)

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
        color = QColorDialog.getColor(current, self, tr("选择通道颜色"))
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
        self.statusBar().showMessage(tr("已按 99.8% 百分位自动调整所有通道"), 5000)

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
        self.statusBar().showMessage(tr("已恢复所有通道的原始显示设置"), 5000)

    def _spatial_mode_changed(self) -> None:
        if self.data is not None and not self.updating_controls:
            self._refresh_spatial_controls()

    def apply_spatial_calibration(self) -> None:
        if self.data is None:
            return
        values = tuple(spin.value() for spin in self.spatial_spins)
        if not all(math.isfinite(value) and value > 0 for value in values):
            QMessageBox.warning(self, tr("空间校准"), tr("X/Y/Z 尺寸必须是大于 0 的有限数值"))
            return
        if self.spatial_mode.currentIndex() == 1:
            z, y, x = self.data.shape
            values = tuple(value / pixels for value, pixels in zip(values, (x, y, z)))
        self.volume_view.update_spatial_calibration(values)
        self._update_file_info()
        self._refresh_spatial_controls()
        self.reset_axis_spacing()
        self.statusBar().showMessage(tr("空间尺寸已更新；原始文件未被修改"), 5000)

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

    def _refresh_rotation_controls(self) -> None:
        if not hasattr(self, "rotation_spins"):
            return
        self.updating_controls = True
        values = (self.volume_view.camera.elevation, self.volume_view.camera.roll, self.volume_view.camera.azimuth)
        for spin, value in zip(self.rotation_spins, values):
            # Preserve text and cursor position while typing the current angle.
            if spin.value() != round(value, spin.decimals()):
                spin.setValue(value)
        self.updating_controls = False

    def _rotation_changed(self) -> None:
        if self.updating_controls:
            return
        x_angle, y_angle, z_angle = (spin.value() for spin in self.rotation_spins)
        self.volume_view.set_rotation(x_angle, y_angle, z_angle)

    def save_current(self) -> None:
        if self.data is None:
            return
        if self.data.source.suffix.lower() == ".ims":
            self._save_ims_to(self.data.source)
        else:
            self.save_as_ims()

    def save_as_ims(self) -> None:
        if self.data is None:
            return
        default = self.data.source.with_suffix(".ims")
        path, _ = QFileDialog.getSaveFileName(self, tr("另存为 IMS"), str(default), tr("Imaris 图像 (*.ims)"))
        if path:
            self._save_ims_to(Path(path).with_suffix(".ims"))

    def _save_ims_to(self, destination: Path) -> None:
        assert self.data is not None
        state = self.volume_view.capture_view_state(self.channel_settings, self.channel_list.currentRow())
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(tr("正在保存 IMS 图像和显示设置…"))
        QApplication.processEvents()
        try:
            save_ims(self.data, destination, state)
        except Exception as error:
            QMessageBox.critical(self, tr("保存失败"), str(error))
            self.statusBar().showMessage(tr("IMS 保存失败"))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.data.source = destination
        self.data.view_state = state
        self._update_file_info()
        self.setWindowTitle(f"Tron 3D viewer — {destination.name}")
        self.statusBar().showMessage(tr("已保存 {name}；再次打开将恢复显示设置", name=destination.name), 10000)

    def export_png_current(self) -> None:
        if self.data is None:
            return
        default_path = self.data.source.with_name(self.data.source.stem + "_3D.png")
        path, _ = QFileDialog.getSaveFileName(self, tr("导出 PNG"), str(default_path), tr("PNG 图像 (*.png)"))
        if not path:
            return
        destination = Path(path).with_suffix(".png")
        scale = (1, 2, 4)[self.scale_combo.currentIndex()]
        self._perform_export(destination, lambda: export_png(self.volume_view, destination, scale))

    def export_pdf_current(self) -> None:
        if self.data is None:
            return
        width, height = self.volume_view.canvas.size
        dialog = PdfExportDialog(
            self, width / height, show_grid=self.axis_checks["grid"].isChecked(), settings=self.settings,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.save_settings(self.settings)
        width_cm, height_cm, font_size, scale, frame_width_pt, grid_width_pt = dialog.values()
        transparent_outside_frame = dialog.transparent_outside_frame_check.isChecked()
        default_path = self.data.source.with_name(self.data.source.stem + "_3D.pdf")
        path, _ = QFileDialog.getSaveFileName(self, tr("导出矢量文字 PDF"), str(default_path), tr("PDF 文档 (*.pdf)"))
        if not path:
            return
        destination = Path(path).with_suffix(".pdf")
        self._perform_export(
            destination,
            lambda: export_pdf(
                self.volume_view, destination, scale, width_cm, height_cm, font_size,
                transparent_outside_frame=transparent_outside_frame,
                frame_width_pt=frame_width_pt, grid_width_pt=grid_width_pt,
            ),
        )

    def _perform_export(self, destination: Path, exporter) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        self.statusBar().showMessage(tr("正在渲染并导出…"))
        QApplication.processEvents()
        try:
            size = exporter()
        except Exception as error:
            QMessageBox.critical(self, tr("导出失败"), str(error))
            self.statusBar().showMessage(tr("导出失败"))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(tr("已导出 {name}（{width} × {height}）", name=destination.name, width=size[0], height=size[1]), 10000)
        QMessageBox.information(self, tr("导出完成"), tr("已保存：\n{path}\n\n图像尺寸：{width} × {height}", path=destination, width=size[0], height=size[1]))
