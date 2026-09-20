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

SOURCE_BY_INDEX = {0: ChartSource.RAW, 1: ChartSource.FIELD, 2: ChartSource.REGISTER}
INDEX_BY_SOURCE = {source: index for index, source in SOURCE_BY_INDEX.items()}

# 下拉框顺序即枚举声明顺序，映射由枚举派生，避免两处真值走偏
DTYPE_BY_INDEX = {index: dtype for index, dtype in enumerate(RawDtype)}
INDEX_BY_DTYPE = {dtype: index for index, dtype in enumerate(RawDtype)}
DTYPE_LABELS = {
    RawDtype.UINT8: '字节值 (0-255)',
    RawDtype.INT16_BE: '整数 int16 (大端有符号)',
    RawDtype.FLOAT32_BE: '浮点 float32 (大端)',
}


class ChannelSpecDialog(QDialog):
    """通道属性：名称、来源、取数键、解码方式与工程量换算"""

    def __init__(self, parent=None, spec: ChannelSpec | None = None,
                 field_names=(), register_keys=(), used_names=()):
        super().__init__(parent)
        self.setWindowTitle('通道属性')
        self.used_names = set(used_names) - ({spec.name} if spec else set())
        self.field_names = sorted(field_names)
        self.register_keys = sorted(register_keys, key=lambda k: int(k) if k.isdigit() else 0)

        self.form = QFormLayout(self)

        self.name_edit = QLineEdit(spec.name if spec else '')
        self.form.addRow('名称', self.name_edit)

        self.source_combo = QComboBox()
        self.source_combo.addItems(['原始字节流', '协议字段', 'Modbus 寄存器'])
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        self.form.addRow('来源', self.source_combo)

        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems([DTYPE_LABELS[dtype] for dtype in RawDtype])
        self.form.addRow('解码', self.dtype_combo)

        self.key_combo = QComboBox()
        self.key_combo.setEditable(True)
        self.form.addRow('字段/地址', self.key_combo)

        self.unit_edit = QLineEdit(spec.unit if spec else '')
        self.form.addRow('单位', self.unit_edit)

        self.scale_spin = QDoubleSpinBox()
        self.scale_spin.setRange(-1e6, 1e6)
        self.scale_spin.setDecimals(6)
        self.scale_spin.setValue(spec.scale if spec else 1.0)
        self.form.addRow('值 × 缩放', self.scale_spin)

        self.offset_spin = QDoubleSpinBox()
        self.offset_spin.setRange(-1e9, 1e9)
        self.offset_spin.setDecimals(4)
        self.offset_spin.setValue(spec.offset if spec else 0.0)
        self.form.addRow('+ 偏移', self.offset_spin)

        if spec:
            self.source_combo.setCurrentIndex(INDEX_BY_SOURCE[spec.source])
            self.dtype_combo.setCurrentIndex(INDEX_BY_DTYPE[spec.dtype])
        self._on_source_changed(self.source_combo.currentIndex())
        if spec:
            self.key_combo.setCurrentText(spec.key)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        self.form.addRow(buttons)

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
            QMessageBox.warning(self, '通道属性', '名称不能为空')
            return
        if name in self.used_names:
            QMessageBox.warning(self, '通道属性', f'通道名 {name} 已存在')
            return
        if (SOURCE_BY_INDEX[self.source_combo.currentIndex()] != ChartSource.RAW
                and not self.key_combo.currentText().strip()):
            QMessageBox.warning(self, '通道属性', '请填写字段名或寄存器地址')
            return
        self.accept()

    def spec(self) -> ChannelSpec:
        source = SOURCE_BY_INDEX[self.source_combo.currentIndex()]
        return ChannelSpec(
            name=self.name_edit.text().strip(),
            source=source,
            key=self.key_combo.currentText().strip() if source != ChartSource.RAW else '',
            dtype=DTYPE_BY_INDEX[self.dtype_combo.currentIndex()],
            unit=self.unit_edit.text().strip(),
            scale=self.scale_spin.value(),
            offset=self.offset_spin.value(),
        )


class EnhancedChart(QWidget):
    """增强波形图 - 通道可绑定原始字节流、协议字段与 Modbus 寄存器"""

    channel_count_changed = pyqtSignal(int)

    CHANNEL_COLORS = [
        '#4FC3F7', '#81C784', '#FFB74D', '#BA68C8',
        '#E57373', '#4DB6AC', '#F06292', '#AED581',
    ]

    def __init__(self, max_points=500, max_channels=8, refresh_ms=60):
        super().__init__()
        self.max_channels = max_channels
        self.store = ChartSeriesStore(max_points=max_points)
        self.frozen = False
        self.x_axis_time = False
        self.xy_mode = False
        self.collect_enabled = True
        self._dirty = False
        self._seen_fields: set[str] = set()
        self._seen_registers: set[str] = set()

        self.init_ui()

        # 数据只写缓冲，重绘按固定节拍合并，避免高波特率下每包重绘
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(refresh_ms)
        self.refresh_timer.timeout.connect(self._repaint_if_dirty)
        self.refresh_timer.start()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel('模式:'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['YT (时域)', 'XY (李萨如)'])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ctrl.addWidget(self.mode_combo)

        ctrl.addWidget(QLabel('  X 轴:'))
        self.axis_combo = QComboBox()
        self.axis_combo.addItems(['采样点', '时间 (s)'])
        self.axis_combo.currentIndexChanged.connect(self._on_axis_changed)
        ctrl.addWidget(self.axis_combo)

        self.xy_x_combo = QComboBox()
        self.xy_y_combo = QComboBox()
        self.xy_x_label = QLabel(' X:')
        self.xy_y_label = QLabel(' Y:')
        for combo in (self.xy_x_combo, self.xy_y_combo):
            combo.setVisible(False)
            combo.currentIndexChanged.connect(self._mark_dirty)
        for label, combo in ((self.xy_x_label, self.xy_x_combo), (self.xy_y_label, self.xy_y_combo)):
            label.setVisible(False)
            ctrl.addWidget(label)
            ctrl.addWidget(combo)

        ctrl.addWidget(QLabel('  点数:'))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(50, 5000)
        self.points_spin.setValue(self.store.max_points)
        self.points_spin.setSingleStep(50)
        self.points_spin.valueChanged.connect(self._on_max_points_changed)
        ctrl.addWidget(self.points_spin)

        ctrl.addStretch()

        self.autoscale_check = QCheckBox('自动缩放')
        self.autoscale_check.setChecked(True)
        self.autoscale_check.stateChanged.connect(self._toggle_autoscale)
        ctrl.addWidget(self.autoscale_check)

        self.grid_check = QCheckBox('网格')
        self.grid_check.setChecked(True)
        self.grid_check.stateChanged.connect(self._toggle_grid)
        ctrl.addWidget(self.grid_check)

        self.collect_check = QCheckBox('采集')
        self.collect_check.setChecked(True)
        self.collect_check.setToolTip('关闭后不再采样；冻结只是暂停刷新，仍在采样')
        self.collect_check.toggled.connect(self.set_collect_enabled)
        ctrl.addWidget(self.collect_check)

        self.freeze_btn = QPushButton('⏸ 冻结')
        self.freeze_btn.setCheckable(True)
        self.freeze_btn.toggled.connect(self._on_frozen)
        ctrl.addWidget(self.freeze_btn)

        export_btn = QPushButton('导出 CSV')
        export_btn.clicked.connect(self._export_via_dialog)
        ctrl.addWidget(export_btn)

        clear_btn = QPushButton('清空')
        clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(clear_btn)

        add_btn = QPushButton('＋ 通道')
        add_btn.clicked.connect(self._add_channel_interactive)
        ctrl.addWidget(add_btn)

        layout.addLayout(ctrl)

        self.channel_bar = QHBoxLayout()
        self.channel_bar.addWidget(QLabel('通道:'))
        self.channel_bar.addStretch()
        layout.addLayout(self.channel_bar)

        self.cursor_label = QLabel('光标: 拖动竖线测量 ΔX / ΔY')
        layout.addWidget(self.cursor_label)

        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', '数值')
        self.plot_widget.setLabel('bottom', '采样点')
        self.plot_widget.addLegend()
        layout.addWidget(self.plot_widget)

        self.curves: dict[str, pg.PlotDataItem] = {}
        self.xy_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#FFD700', width=2), connect='finite', name='XY')
        self.xy_curve.setVisible(False)

        # 光标测量：两条可拖动竖线 + ΔX/ΔY 读数
        self.cursor_a = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen('#FFD700'))
        self.cursor_b = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen('#FFD700'))
        for cursor in (self.cursor_a, self.cursor_b):
            cursor.sigPositionChanged.connect(self._on_cursor_moved)
            self.plot_widget.addItem(cursor)
        self.cursor_a.setPos(0)
        self.cursor_b.setPos(1)

        self._rebuild_channel_bar()

    # ─── 通道管理 ───────────────────────────────────────────

    def add_channel(self, spec: ChannelSpec) -> str | None:
        """添加通道；返回错误描述，None 表示成功"""
        if len(self.store.channels) >= self.max_channels:
            return f'最多 {self.max_channels} 个通道'
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
            self, spec=channel.spec, field_names=self._seen_fields,
            register_keys=self._seen_registers, used_names=self.channel_names())
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
            QMessageBox.information(self, '通道', f'最多 {self.max_channels} 个通道')
            return
        dialog = ChannelSpecDialog(
            self, field_names=self._seen_fields, register_keys=self._seen_registers,
            used_names=self.channel_names())
        if dialog.exec():
            error = self.add_channel(dialog.spec())
            if error:
                QMessageBox.warning(self, '通道', error)

    def _sync_curves(self):
        """让曲线集合与通道集合保持一致"""
        alive = {c.name for c in self.store.channels}
        for name in [n for n in self.curves if n not in alive]:
            self.plot_widget.removeItem(self.curves.pop(name))
        for channel in self.store.channels:
            curve = self.curves.get(channel.name)
            if curve is None:
                curve = self.plot_widget.plot(
                    pen=pg.mkPen(channel.color, width=2), connect='finite', name=channel.name)
                self.curves[channel.name] = curve
            curve.setVisible(channel.visible and not self.xy_mode)

    def _rebuild_channel_bar(self):
        while self.channel_bar.count():
            item = self.channel_bar.takeAt(0)
            if item is None:
                break
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.channel_bar.addWidget(QLabel('通道:'))
        for channel in self.store.channels:
            name = channel.name
            check = QCheckBox(name)
            check.setChecked(channel.visible)
            check.setToolTip(f'{channel.spec.source.value} {channel.spec.key}'.strip())
            check.stateChanged.connect(lambda state, n=name: self._toggle_channel(n, state))
            self.channel_bar.addWidget(check)

            color_btn = QPushButton('■')
            color_btn.setStyleSheet(f'color: {channel.color}; font-size: 16px;')
            color_btn.setFixedSize(25, 25)
            color_btn.clicked.connect(lambda checked=False, n=name: self._change_channel_color(n))
            self.channel_bar.addWidget(color_btn)

            edit_btn = QPushButton('✎')
            edit_btn.setFixedWidth(26)
            edit_btn.clicked.connect(lambda checked=False, n=name: self._edit_channel(n))
            self.channel_bar.addWidget(edit_btn)

            del_btn = QPushButton('✕')
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
            fields = getattr(frame, 'fields', None) or {}
            self._seen_fields.update(fields)
            if self.collect_enabled:
                self.store.feed_fields(fields)
        if self.collect_enabled:
            self._dirty = True

    def feed_registers(self, responses):
        """喂入 Modbus 响应；顺带记录见过的寄存器地址"""
        responses = list(responses)
        for response in responses:
            for reg in getattr(response, 'registers', []):
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
            self.plot_widget.enableAutoRange(axis='x')
            self.plot_widget.enableAutoRange(axis='y')
        self._on_cursor_moved()      # 数据在长，读数也要跟着刷新

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
        self.xy_mode = (index == 1)
        for combo, label in ((self.xy_x_combo, self.xy_x_label),
                             (self.xy_y_combo, self.xy_y_label)):
            combo.setVisible(self.xy_mode)
            label.setVisible(self.xy_mode)
        self.axis_combo.setVisible(not self.xy_mode)
        for cursor in (self.cursor_a, self.cursor_b):
            cursor.setVisible(not self.xy_mode)
        for curve in self.curves.values():
            curve.setVisible(not self.xy_mode)
        self.xy_curve.setVisible(self.xy_mode)
        self.plot_widget.setLabel('left', 'Y 通道' if self.xy_mode else '数值')
        self._update_axis_label()
        self._mark_dirty()

    def _on_axis_changed(self, index: int):
        self.x_axis_time = (index == 1)
        self._update_axis_label()
        self._mark_dirty()

    def _update_axis_label(self):
        self.plot_widget.setLabel(
            'bottom',
            'X 通道' if self.xy_mode else ('时间 (s)' if self.x_axis_time else '采样点'))

    def _toggle_channel(self, name: str, state: int):
        channel = self.store.channel(name)
        curve = self.curves.get(name)
        if not channel:
            return
        channel.visible = (state == Qt.CheckState.Checked.value)
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
        self.plot_widget.enableAutoRange(axis='x', enabled=enabled)
        self.plot_widget.enableAutoRange(axis='y', enabled=enabled)
        self._mark_dirty()

    def _on_frozen(self, checked: bool):
        self.frozen = checked
        self.freeze_btn.setText('▶ 继续' if checked else '⏸ 冻结')
        if not checked:
            self._mark_dirty()

    def _on_cursor_moved(self, *_):
        """读数：两条竖线间的 ΔX 与首个可见通道的 ΔY"""
        if self.xy_mode:
            return
        if not self.store.channels:
            return                              # 构造期光标初始化，尚无通道，别覆盖提示文案
        channel = next((c for c in self.store.channels if c.visible), None)
        if channel is None or channel.count() == 0:
            self.cursor_label.setText('光标: 无可见通道')
            return

        x_a = self._cursor_x(self.cursor_a)
        x_b = self._cursor_x(self.cursor_b)
        unit = 'ms' if self.x_axis_time else '点'
        scale = 1000.0 if self.x_axis_time else 1.0
        y_a = self._value_at(channel, x_a)
        y_b = self._value_at(channel, x_b)
        suffix = f' {channel.spec.unit}' if channel.spec.unit else ''
        self.cursor_label.setText(
            f'光标: ΔX={(x_b - x_a) * scale:.3f} {unit}   Δ{channel.name}={y_b - y_a:+.4g}{suffix}')

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
        with open(path, 'w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=ChartSeriesStore.headers())
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def _export_via_dialog(self):
        path, _ = QFileDialog.getSaveFileName(self, '导出曲线数据', 'chart.csv', 'CSV (*.csv)')
        if not path:
            return
        count = self.export_csv(path)
        QMessageBox.information(self, '导出曲线数据', f'已写出 {count} 行\n{path}')

    def x_axis_mode(self) -> str:
        return 'time' if self.x_axis_time else 'index'

    def set_x_axis_mode(self, mode: str):
        self.axis_combo.setCurrentIndex(1 if mode == 'time' else 0)
