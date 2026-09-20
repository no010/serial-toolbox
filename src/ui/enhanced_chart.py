"""
增强波形图组件（图表视图层）

通道定义、解码与采样缓冲由 src.core.chart_model 负责；本组件只做三件事：
按来源喂数据、按节拍节流重绘、以及光标测量与 CSV 导出等交互。
"""

import csv

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.chart_model import ChannelSpec, ChartSeriesStore, ChartSource, RawDtype
from src.ui.extended_panels import _retranslate_combo
from src.ui.i18n import I18nManager

SOURCE_BY_INDEX = {0: ChartSource.RAW, 1: ChartSource.FIELD, 2: ChartSource.REGISTER}
INDEX_BY_SOURCE = {source: index for index, source in SOURCE_BY_INDEX.items()}

# 下拉框顺序即枚举声明顺序，映射由枚举派生，避免两处真值走偏
DTYPE_BY_INDEX = {index: dtype for index, dtype in enumerate(RawDtype)}
INDEX_BY_DTYPE = {dtype: index for index, dtype in enumerate(RawDtype)}
DTYPE_KEYS = {
    RawDtype.UINT8: "dtype_uint8",
    RawDtype.INT16_BE: "dtype_int16",
    RawDtype.FLOAT32_BE: "dtype_float32",
}


class ChannelSpecDialog(QDialog):
    """通道属性：名称、来源、取数键、解码方式与工程量换算"""

    def __init__(
        self,
        parent=None,
        spec: ChannelSpec | None = None,
        field_names=(),
        register_keys=(),
        used_names=(),
        i18n: I18nManager | None = None,
    ):
        super().__init__(parent)
        self.i18n = i18n or I18nManager()
        self.used_names = set(used_names) - ({spec.name} if spec else set())
        self.field_names = sorted(field_names)
        self.register_keys = sorted(register_keys, key=lambda k: int(k) if k.isdigit() else 0)

        self.form = QFormLayout(self)

        self.name_edit = QLineEdit(spec.name if spec else "")
        self.name_label = QLabel()
        self.form.addRow(self.name_label, self.name_edit)

        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.source_label = QLabel()
        self.form.addRow(self.source_label, self.source_combo)

        self.dtype_combo = QComboBox()
        self.dtype_label = QLabel()
        self.form.addRow(self.dtype_label, self.dtype_combo)

        self.key_combo = QComboBox()
        self.key_combo.setEditable(True)
        self.key_label = QLabel()
        self.form.addRow(self.key_label, self.key_combo)

        self.unit_edit = QLineEdit(spec.unit if spec else "")
        self.unit_label = QLabel()
        self.form.addRow(self.unit_label, self.unit_edit)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1e6, 1e6)
        self.scale_spin.setDecimals(6)
        self.scale_spin.setValue(spec.scale if spec else 1.0)
        self.scale_label = QLabel()
        self.form.addRow(self.scale_label, self.scale_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e9, 1e9)
        self.offset_spin.setDecimals(4)
        self.offset_spin.setValue(spec.offset if spec else 0.0)
        self.offset_label = QLabel()
        self.form.addRow(self.offset_label, self.offset_spin)

        self.axis_combo = QComboBox()
        self.axis_label = QLabel()
        self.form.addRow(self.axis_label, self.axis_combo)

        self.retranslate_ui()

        if spec:
            self.source_combo.setCurrentIndex(INDEX_BY_SOURCE[spec.source])
            self.dtype_combo.setCurrentIndex(INDEX_BY_DTYPE[spec.dtype])
            self.axis_combo.setCurrentIndex(1 if spec.axis == "right" else 0)
        self._on_source_changed(self.source_combo.currentIndex())
        if spec:
            self.key_combo.setCurrentText(spec.key)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setWindowTitle(tr("dialog_channel_spec"))
        self.name_label.setText(tr("label_ch_name"))
        self.source_label.setText(tr("label_ch_source"))
        _retranslate_combo(self.source_combo, [tr("src_raw"), tr("src_field"), tr("src_register")])
        self.dtype_label.setText(tr("label_ch_dtype"))
        _retranslate_combo(self.dtype_combo, [tr(DTYPE_KEYS[d]) for d in RawDtype])
        self.key_label.setText(tr("label_ch_key"))
        self.unit_label.setText(tr("label_ch_unit"))
        self.scale_label.setText(tr("label_ch_scale"))
        self.offset_label.setText(tr("label_ch_offset"))
        self.axis_label.setText(tr("label_ch_axis"))
        _retranslate_combo(self.axis_combo, [tr("axis_left"), tr("axis_right")])

    def _on_source_changed(self, index: int):
        """不同来源只有各自的取数参数有意义"""
        source = SOURCE_BY_INDEX[index]
        self._set_row_visible(self.dtype_combo, source == ChartSource.RAW)
        self._set_row_visible(self.key_combo, source != ChartSource.RAW)
        if source == ChartSource.FIELD:
            self.key_combo.clear()
            self.key_combo.addItems(self.field_names)
        elif source == ChartSource.REGISTER:
            self.key_combo.clear()
            self.key_combo.addItems(self.register_keys)

    def _set_row_visible(self, widget: QWidget, visible: bool):
        """QFormLayout 的标签不随字段控件隐藏，要一起处理"""
        widget.setVisible(visible)
        label = self.form.labelForField(widget)
        if label:
            label.setVisible(visible)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self, self.i18n.tr("dialog_channel_spec"), self.i18n.tr("err_name_empty")
            )
            return
        if name in self.used_names:
            QMessageBox.warning(
                self, self.i18n.tr("dialog_channel_spec"), self.i18n.tr("err_name_dup", name)
            )
            return
        if (
            SOURCE_BY_INDEX[self.source_combo.currentIndex()] != ChartSource.RAW
            and not self.key_combo.currentText().strip()
        ):
            QMessageBox.warning(
                self, self.i18n.tr("dialog_channel_spec"), self.i18n.tr("err_key_empty")
            )
            return
        self.accept()

    def spec(self) -> ChannelSpec:
        source = SOURCE_BY_INDEX[self.source_combo.currentIndex()]
        return ChannelSpec(
            name=self.name_edit.text().strip(),
            source=source,
            key=self.key_combo.currentText().strip() if source != ChartSource.RAW else "",
            dtype=DTYPE_BY_INDEX[self.dtype_combo.currentIndex()],
            unit=self.unit_edit.text().strip(),
            scale=self.scale_spin.value(),
            offset=self.offset_spin.value(),
            axis="right" if self.axis_combo.currentIndex() == 1 else "left",
        )


class EnhancedChart(QWidget):
    """增强波形图 - 通道可绑定原始字节流、协议字段与 Modbus 寄存器"""

    channel_count_changed = pyqtSignal(int)

    CHANNEL_COLORS = [
        "#4FC3F7",
        "#81C784",
        "#FFB74D",
        "#BA68C8",
        "#E57373",
        "#4DB6AC",
        "#F06292",
        "#AED581",
    ]

    def __init__(
        self, max_points=500, max_channels=8, refresh_ms=60, i18n: I18nManager | None = None
    ):
        super().__init__()
        self.i18n = i18n or I18nManager()
        self.max_channels = max_channels
        self.store = ChartSeriesStore(max_points=max_points)
        self.frozen = False
        self.x_axis_time = False
        self.xy_mode = False
        self.collect_enabled = True
        self._dirty = False
        self._seen_fields: set[str] = set()
        self._seen_registers: set[str] = set()
        self._right_curve_names: set[str] = set()

        self.init_ui()
        self.retranslate_ui()

        # 数据只写缓冲，重绘按固定节拍合并，避免高波特率下每包重绘
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(refresh_ms)
        self.refresh_timer.timeout.connect(self._repaint_if_dirty)
        self.refresh_timer.start()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.mode_label.setText(tr("label_mode"))
        _retranslate_combo(self.mode_combo, [tr("mode_yt"), tr("mode_xy")])
        self.axis_label.setText(tr("label_x_axis"))
        _retranslate_combo(self.axis_combo, [tr("x_axis_index"), tr("x_axis_time")])
        self.xy_x_label.setText(tr("xy_x_label"))
        self.xy_y_label.setText(tr("xy_y_label"))
        self.points_label.setText(tr("label_points"))
        self.autoscale_check.setText(tr("check_autoscale"))
        self.grid_check.setText(tr("check_grid"))
        self.collect_check.setText(tr("check_collect"))
        self.collect_check.setToolTip(tr("tip_collect"))
        self.freeze_btn.setText(tr("btn_unfreeze") if self.frozen else tr("btn_freeze"))
        self.export_btn.setText(tr("btn_export_csv"))
        self.clear_btn.setText(tr("btn_clear_chart"))
        self.add_channel_btn.setText(tr("btn_add_channel"))
        self.channel_bar_label.setText(tr("label_channel"))
        self._refresh_axis_labels()
        self._refresh_cursor_hint()

    def _refresh_cursor_hint(self):
        if not self.store.channels:
            self.cursor_label.setText(self.i18n.tr("cursor_hint"))

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        ctrl = QHBoxLayout()
        self.mode_label = QLabel()
        ctrl.addWidget(self.mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ctrl.addWidget(self.mode_combo)

        self.axis_label = QLabel()
        ctrl.addWidget(self.axis_label)
        self.axis_combo = QComboBox()
        self.axis_combo.currentIndexChanged.connect(self._on_axis_changed)
        ctrl.addWidget(self.axis_combo)

        self.xy_x_combo = QComboBox()
        self.xy_y_combo = QComboBox()
        self.xy_x_label = QLabel()
        self.xy_y_label = QLabel()
        for combo in (self.xy_x_combo, self.xy_y_combo):
            combo.setVisible(False)
            combo.currentIndexChanged.connect(self._mark_dirty)
        for label, combo in (
            (self.xy_x_label, self.xy_x_combo),
            (self.xy_y_label, self.xy_y_combo),
        ):
            label.setVisible(False)
            ctrl.addWidget(label)
            ctrl.addWidget(combo)

        self.points_label = QLabel()
        ctrl.addWidget(self.points_label)
        self.points_spin = QSpinBox()
        self.points_spin.setRange(50, 5000)
        self.points_spin.setValue(self.store.max_points)
        self.points_spin.setSingleStep(50)
        self.points_spin.valueChanged.connect(self._on_max_points_changed)
        ctrl.addWidget(self.points_spin)

        ctrl.addStretch()

        self.autoscale_check = QCheckBox()
        self.autoscale_check.setChecked(True)
        self.autoscale_check.stateChanged.connect(self._toggle_autoscale)
        ctrl.addWidget(self.autoscale_check)

        self.grid_check = QCheckBox()
        self.grid_check.setChecked(True)
        self.grid_check.stateChanged.connect(self._toggle_grid)
        ctrl.addWidget(self.grid_check)

        self.collect_check = QCheckBox()
        self.collect_check.setChecked(True)
        self.collect_check.toggled.connect(self.set_collect_enabled)
        ctrl.addWidget(self.collect_check)

        self.freeze_btn = QPushButton()
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.toggled.connect(self._on_frozen)
        ctrl.addWidget(self.freeze_btn)

        self.export_btn = QPushButton()
        self.export_btn.clicked.connect(self._export_via_dialog)
        ctrl.addWidget(self.export_btn)

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(self.clear_btn)

        self.add_channel_btn = QPushButton()
        self.add_channel_btn.clicked.connect(self._add_channel_interactive)
        ctrl.addWidget(self.add_channel_btn)

        layout.addLayout(ctrl)

        self.channel_bar = QHBoxLayout()
        self.channel_bar_label = QLabel()
        self.channel_bar.addWidget(self.channel_bar_label)
        self.channel_bar.addStretch()
        layout.addLayout(self.channel_bar)

        self.cursor_label = QLabel()
        layout.addWidget(self.cursor_label)

        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#1e1e1e")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()

        # 右轴：独立 ViewBox 与左轴 X 联动，量级差大的通道各占一条 Y 轴
        plot_item = self.plot_widget.plotItem
        scene = self.plot_widget.scene()
        left_vb = plot_item.vb if plot_item is not None else None
        assert plot_item is not None and scene is not None and left_vb is not None
        self.plot_item: pg.PlotItem = plot_item
        self.left_viewbox: pg.ViewBox = left_vb

        self.right_viewbox = pg.ViewBox()
        scene.addItem(self.right_viewbox)
        self.right_axis = self.plot_widget.getAxis("right")
        self.right_axis.linkToView(self.right_viewbox)
        self.right_viewbox.setXLink(self.left_viewbox)
        self.right_axis.setVisible(False)
        layout.addWidget(self.plot_widget)

        self.curves: dict[str, pg.PlotDataItem] = {}
        self.xy_curve = self.plot_widget.plot(
            pen=pg.mkPen(color="#FFD700", width=2), connect="finite", name="XY"
        )
        self.xy_curve.setVisible(False)

        # 光标测量：两条可拖动竖线 + ΔX/ΔY 读数
        self.cursor_a = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#FFD700"))
        self.cursor_b = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen("#FFD700"))
        for cursor in (self.cursor_a, self.cursor_b):
            cursor.sigPositionChanged.connect(self._on_cursor_moved)
            self.plot_widget.addItem(cursor)
        self.cursor_a.setPos(0)
        self.cursor_b.setPos(1)

        self._rebuild_channel_bar()
        self._update_right_axis_geometry()

    def resizeEvent(self, a0):
        super().resizeEvent(a0)
        self._update_right_axis_geometry()

    def _update_right_axis_geometry(self):
        """右轴 ViewBox 的几何要跟随左轴的绘图区"""
        if not hasattr(self, "right_viewbox"):
            return
        self.right_viewbox.setGeometry(self.left_viewbox.sceneBoundingRect())
        self.right_viewbox.linkedViewChanged(self.left_viewbox, self.right_viewbox.XAxis)

    # ─── 通道管理 ───────────────────────────────────────────

    def add_channel(self, spec: ChannelSpec) -> str | None:
        """添加通道；返回错误描述，None 表示成功"""
        if len(self.store.channels) >= self.max_channels:
            return self.i18n.tr("msg_max_channels", self.max_channels)
        color = self.CHANNEL_COLORS[len(self.store.channels) % len(self.CHANNEL_COLORS)]
        try:
            self.store.add_channel(spec, color=color)
        except ValueError as exc:
            return str(exc)
        self._sync_curves()
        self._rebuild_channel_bar()
        return None

    def remove_channel(self, name: str):
        if self.store.remove_channel(name):
            self._sync_curves()
            self._rebuild_channel_bar()

    def channel_names(self) -> list[str]:
        return [c.name for c in self.store.channels]

    def channel_specs(self) -> list[dict]:
        return [c.spec.to_dict() for c in self.store.channels]

    def apply_channel_specs(self, specs: list[dict]):
        """从配置恢复通道定义，非法项跳过"""
        for item in specs:
            try:
                spec = ChannelSpec.from_dict(item)
            except (KeyError, ValueError):
                continue
            self.add_channel(spec)

    def _edit_channel(self, name: str):
        channel = self.store.channel(name)
        if not channel:
            return
        dialog = ChannelSpecDialog(
            self,
            spec=channel.spec,
            field_names=self._seen_fields,
            register_keys=self._seen_registers,
            used_names=self.channel_names(),
            i18n=self.i18n,
        )
        if not dialog.exec():
            return
        # 换绑来源后旧样本口径已不对，直接以新通道从头采
        color = channel.color
        self.store.remove_channel(name)
        self.store.add_channel(dialog.spec(), color=color)
        self._sync_curves()
        self._rebuild_channel_bar()

    def _add_channel_interactive(self):
        if len(self.store.channels) >= self.max_channels:
            QMessageBox.information(
                self,
                self.i18n.tr("label_channel").rstrip(":"),
                self.i18n.tr("msg_max_channels", self.max_channels),
            )
            return
        dialog = ChannelSpecDialog(
            self,
            field_names=self._seen_fields,
            register_keys=self._seen_registers,
            used_names=self.channel_names(),
            i18n=self.i18n,
        )
        if dialog.exec():
            error = self.add_channel(dialog.spec())
            if error:
                QMessageBox.warning(self, self.i18n.tr("label_channel").rstrip(":"), error)

    def _sync_curves(self):
        """让曲线集合与通道集合保持一致；右轴通道挂到独立 ViewBox"""
        alive = {c.name for c in self.store.channels}
        for name in [n for n in self.curves if n not in alive]:
            curve = self.curves.pop(name)
            self.plot_widget.removeItem(curve)
            self.right_viewbox.removeItem(curve)
            if self.plot_item.legend is not None:
                self.plot_item.legend.removeItem(curve)
            self._right_curve_names.discard(name)

        for channel in self.store.channels:
            want_right = channel.spec.axis == "right"
            curve = self.curves.get(channel.name)
            if curve is None:
                curve = pg.PlotDataItem(
                    pen=pg.mkPen(channel.color, width=2), connect="finite", name=channel.name
                )
                self.curves[channel.name] = curve
                self._place_curve(curve, channel.name, want_right)
            elif (channel.name in self._right_curve_names) != want_right:
                # 编辑通道换了轴，把曲线挪到对应的 ViewBox
                self.plot_widget.removeItem(curve)
                self.right_viewbox.removeItem(curve)
                self._place_curve(curve, channel.name, want_right)
            curve.setVisible(channel.visible and not self.xy_mode)

        has_right = any(c.spec.axis == "right" for c in self.store.channels)
        self.right_axis.setVisible(has_right)
        self.right_viewbox.setVisible(has_right)

    def _place_curve(self, curve: pg.PlotDataItem, name: str, right: bool):
        if right:
            self.right_viewbox.addItem(curve)
            self._right_curve_names.add(name)
        else:
            self.left_viewbox.addItem(curve)
            if self.plot_item.legend is not None:
                self.plot_item.legend.addItem(curve, name)
            self._right_curve_names.discard(name)

    def _rebuild_channel_bar(self):
        # 索引 0 是常驻的"通道:"标签，其余控件全部重建
        while self.channel_bar.count() > 1:
            item = self.channel_bar.takeAt(1)
            if item is None:
                break
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for channel in self.store.channels:
            name = channel.name
            check = QCheckBox(name)
            check.setChecked(channel.visible)
            check.setToolTip(f"{channel.spec.source.value} {channel.spec.key}".strip())
            check.stateChanged.connect(lambda state, n=name: self._toggle_channel(n, state))
            self.channel_bar.addWidget(check)

            color_btn = QPushButton("■")
            color_btn.setStyleSheet(f"color: {channel.color}; font-size: 16px;")
            color_btn.setFixedSize(25, 25)
            color_btn.clicked.connect(lambda checked=False, n=name: self._change_channel_color(n))
            self.channel_bar.addWidget(color_btn)

            edit_btn = QPushButton("✎")
            edit_btn.setFixedWidth(26)
            edit_btn.clicked.connect(lambda checked=False, n=name: self._edit_channel(n))
            self.channel_bar.addWidget(edit_btn)

            del_btn = QPushButton("✕")
            del_btn.setFixedWidth(26)
            del_btn.clicked.connect(lambda checked=False, n=name: self.remove_channel(n))
            self.channel_bar.addWidget(del_btn)

        self.channel_bar.addStretch()
        self._refresh_xy_combos()
        self.channel_count_changed.emit(len(self.store.channels))

    def _refresh_xy_combos(self):
        names = self.channel_names()
        for combo in (self.xy_x_combo, self.xy_y_combo):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            if current in names:
                combo.setCurrentText(current)
            combo.blockSignals(False)
        if self.xy_y_combo.count() > 1 and self.xy_y_combo.currentIndex() == 0:
            self.xy_y_combo.setCurrentIndex(1)

    # ─── 数据入口 ───────────────────────────────────────────

    def feed_raw(self, data: bytes):
        """原始字节流通道按各自 dtype 解码取数"""
        if self.collect_enabled:
            self.store.feed_raw(data)
            self._dirty = True

    def feed_fields(self, frames):
        """喂入协议帧列表；顺带记录见过的字段名，供通道下拉直接选"""
        for frame in frames:
            fields = getattr(frame, "fields", None) or {}
            self._seen_fields.update(fields)
            if self.collect_enabled:
                self.store.feed_fields(fields)
        if self.collect_enabled:
            self._dirty = True

    def feed_registers(self, responses):
        """喂入 Modbus 响应；顺带记录见过的寄存器地址"""
        responses = list(responses)
        for response in responses:
            for reg in getattr(response, "registers", []):
                self._seen_registers.add(str(reg.address))
        if self.collect_enabled:
            self.store.feed_registers(responses)
            self._dirty = True

    def is_collect_enabled(self) -> bool:
        return self.collect_enabled

    def set_collect_enabled(self, enabled: bool):
        """采集总开关：关闭后新数据不入缓冲也不重绘，已采数据与通道定义保留"""
        self.collect_enabled = enabled
        if enabled:
            self.refresh_timer.start()
            self._mark_dirty()
        else:
            self.refresh_timer.stop()

    def clear(self):
        self.store.clear()
        self._update_plot()

    # ─── 重绘 ───────────────────────────────────────────────

    def _mark_dirty(self, *args):
        self._dirty = True

    def _on_max_points_changed(self, value: int):
        self.store.set_max_points(value)
        self._dirty = True

    def _repaint_if_dirty(self):
        if self.frozen or not self._dirty:
            return
        self._update_plot()

    def _update_plot(self):
        self._dirty = False
        if self.xy_mode:
            self._update_xy()
            return

        for channel in self.store.channels:
            curve = self.curves.get(channel.name)
            if curve is None:
                continue
            times, values = channel.snapshot()
            if self.x_axis_time:
                curve.setData(times, values)
            else:
                curve.setData(np.arange(values.size, dtype=np.float64), values)

        if self.autoscale_check.isChecked():
            self.plot_widget.enableAutoRange(axis="x")
            self.plot_widget.enableAutoRange(axis="y")
            self.right_viewbox.enableAutoRange(axis="y")
        self._on_cursor_moved()  # 数据在长，读数也要跟着刷新

    def _update_xy(self):
        x_channel = self.store.channel(self.xy_x_combo.currentText())
        y_channel = self.store.channel(self.xy_y_combo.currentText())
        if not x_channel or not y_channel:
            self.xy_curve.clear()
            return

        x_values = x_channel.snapshot()[1]
        y_values = y_channel.snapshot()[1]
        length = min(x_values.size, y_values.size)
        if length:
            self.xy_curve.setData(x_values[:length], y_values[:length])
        else:
            self.xy_curve.clear()

    # ─── 交互 ───────────────────────────────────────────────

    def _on_mode_changed(self, index: int):
        self.xy_mode = index == 1
        for combo, label in (
            (self.xy_x_combo, self.xy_x_label),
            (self.xy_y_combo, self.xy_y_label),
        ):
            combo.setVisible(self.xy_mode)
            label.setVisible(self.xy_mode)
        self.axis_combo.setVisible(not self.xy_mode)
        for cursor in (self.cursor_a, self.cursor_b):
            cursor.setVisible(not self.xy_mode)
        for curve in self.curves.values():
            curve.setVisible(not self.xy_mode)
        self.xy_curve.setVisible(self.xy_mode)
        self._refresh_axis_labels()
        self._mark_dirty()

    def _on_axis_changed(self, index: int):
        self.x_axis_time = index == 1
        self._refresh_axis_labels()
        self._mark_dirty()

    def _refresh_axis_labels(self):
        tr = self.i18n.tr
        self.plot_widget.setLabel(
            "left", tr("axis_y_channel") if self.xy_mode else tr("axis_value")
        )
        self.plot_widget.setLabel(
            "bottom",
            tr("axis_x_channel")
            if self.xy_mode
            else (tr("axis_time") if self.x_axis_time else tr("axis_sample")),
        )

    def _toggle_channel(self, name: str, state: int):
        channel = self.store.channel(name)
        curve = self.curves.get(name)
        if not channel:
            return
        channel.visible = state == Qt.CheckState.Checked.value
        if curve:
            curve.setVisible(channel.visible and not self.xy_mode)

    def _change_channel_color(self, name: str):
        channel = self.store.channel(name)
        curve = self.curves.get(name)
        if not channel or not curve:
            return
        color = QColorDialog.getColor(QColor(channel.color), self)
        if not color.isValid():
            return
        channel.color = color.name()
        curve.setPen(pg.mkPen(color=color.name(), width=2))
        self._rebuild_channel_bar()

    def _toggle_grid(self, state):
        checked = state == Qt.CheckState.Checked.value
        self.plot_widget.showGrid(x=checked, y=checked, alpha=0.3)

    def _toggle_autoscale(self, state):
        enabled = state == Qt.CheckState.Checked.value
        self.plot_widget.enableAutoRange(axis="x", enabled=enabled)
        self.plot_widget.enableAutoRange(axis="y", enabled=enabled)
        self.right_viewbox.enableAutoRange(axis="y", enable=enabled)
        self._mark_dirty()

    def _on_frozen(self, checked: bool):
        self.frozen = checked
        tr = self.i18n.tr
        self.freeze_btn.setText(tr("btn_unfreeze") if checked else tr("btn_freeze"))
        if not checked:
            self._mark_dirty()

    def _on_cursor_moved(self, *_):
        """读数：两条竖线间的 ΔX 与首个可见通道的 ΔY"""
        tr = self.i18n.tr
        if self.xy_mode:
            return
        if not self.store.channels:
            return  # 构造期光标初始化，尚无通道，别覆盖提示文案
        channel = next((c for c in self.store.channels if c.visible), None)
        if channel is None or channel.count() == 0:
            self.cursor_label.setText(tr("cursor_no_channel"))
            return

        x_a = self._cursor_x(self.cursor_a)
        x_b = self._cursor_x(self.cursor_b)
        unit = tr("unit_ms") if self.x_axis_time else tr("unit_point")
        scale = 1000.0 if self.x_axis_time else 1.0
        y_a = self._value_at(channel, x_a)
        y_b = self._value_at(channel, x_b)
        suffix = f" {channel.spec.unit}" if channel.spec.unit else ""
        self.cursor_label.setText(
            tr("cursor_fmt", (x_b - x_a) * scale, unit, channel.name, y_b - y_a, suffix)
        )

    @staticmethod
    def _cursor_x(cursor) -> float:
        """竖线角度固定 90 度，value() 即其位置；类型上仍可能是多轴三元组"""
        value = cursor.value()
        return float(value) if isinstance(value, (int, float)) else 0.0

    def _value_at(self, channel, x: float) -> float:
        """按当前 X 轴含义取值：时间轴按时间戳找最近点，否则按索引"""
        times, values = channel.snapshot()
        if values.size == 0:
            return 0.0
        if self.x_axis_time:
            index = int(np.argmin(np.abs(times - x)))
        else:
            index = min(max(int(round(x)), 0), values.size - 1)
        return float(values[index])

    # ─── 导出与配置 ─────────────────────────────────────────

    def export_csv(self, path: str) -> int:
        """把当前所有通道的样本写出 CSV，返回数据行数"""
        rows = self.store.export_rows()
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=ChartSeriesStore.headers())
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def _export_via_dialog(self):
        tr = self.i18n.tr
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog_export_csv"), "chart.csv", tr("csv_filter")
        )
        if not path:
            return
        count = self.export_csv(path)
        QMessageBox.information(self, tr("dialog_export_csv"), tr("msg_exported", count, path))

    def x_axis_mode(self) -> str:
        return "time" if self.x_axis_time else "index"

    def set_x_axis_mode(self, mode: str):
        self.axis_combo.setCurrentIndex(1 if mode == "time" else 0)
