"""
扩展 UI 组件
v3.0 新增面板: Modbus解析、日志设置、脚本编辑器、多串口对比
"""

import json

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.log_rotator import LogConfig, RotateMode
from src.core.modbus_parser import ModbusResponse, ModbusResponseParser
from src.core.script_engine import EXAMPLE_SCRIPTS, ScriptEngine
from src.protocols.template_parser import (
    ProtocolTemplate,
    ProtocolTemplateManager,
    create_sample_template,
)
from src.ui.i18n import I18nManager


def _retranslate_combo(combo: QComboBox, items: list[str]):
    """重填下拉框并保留当前选中项（切换语言时用）；空框选回第一项"""
    index = combo.currentIndex()
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(items)
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


# ─── Modbus 响应解析面板 ─────────────────────────────────────


class ModbusResponsePanel(QGroupBox):
    """Modbus 响应解析结果面板"""

    def __init__(self, i18n: I18nManager | None = None):
        self.i18n = i18n or I18nManager()
        super().__init__()
        self.parser = ModbusResponseParser()
        self.init_ui()
        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setTitle(tr("group_modbus_response"))
        self.auto_detect_label.setText(tr("label_auto_detect"))
        self.clear_btn.setText(tr("btn_clear"))
        self.response_table.setHorizontalHeaderLabels(
            [
                tr("col_time"),
                tr("col_slave"),
                tr("col_func"),
                tr("col_reg_addr"),
                tr("col_raw"),
                tr("col_signed"),
            ]
        )
        self.register_table.setHorizontalHeaderLabels(
            [tr("col_address"), tr("col_hex_value"), tr("col_dec"), tr("col_float")]
        )
        self.reg_detail_label.setText(tr("label_reg_detail"))

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 控制栏
        ctrl = QHBoxLayout()
        self.auto_detect_label = QLabel()
        ctrl.addWidget(self.auto_detect_label)
        ctrl.addStretch()

        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(self.clear_btn)

        layout.addLayout(ctrl)

        # 响应历史表格
        self.response_table = QTableWidget()
        self.response_table.setColumnCount(6)
        response_header = self.response_table.horizontalHeader()
        assert response_header is not None
        response_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.response_table.setMaximumHeight(200)
        layout.addWidget(self.response_table)

        # 寄存器值详情
        self.register_table = QTableWidget()
        self.register_table.setColumnCount(4)
        register_header = self.register_table.horizontalHeader()
        assert register_header is not None
        register_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.register_table.setMaximumHeight(150)
        self.reg_detail_label = QLabel()
        layout.addWidget(self.reg_detail_label)
        layout.addWidget(self.register_table)

    def feed_data(self, data: bytes) -> list[ModbusResponse]:
        """喂入数据，自动解析；返回解析出的响应供其他消费者（如图表寄存器通道）复用"""
        responses = self.parser.feed(data)
        for resp in responses:
            self._add_response(resp)
        return responses

    def _add_response(self, resp: ModbusResponse):
        """添加响应到表格"""
        row = self.response_table.rowCount()
        self.response_table.insertRow(row)

        # 时间
        self.response_table.setItem(row, 0, QTableWidgetItem(resp.timestamp))

        # 从机地址
        self.response_table.setItem(row, 1, QTableWidgetItem(f"0x{resp.slave_addr:02X}"))

        # 功能码
        func_name = self._get_func_name(resp.function_code)
        self.response_table.setItem(
            row, 2, QTableWidgetItem(f"0x{resp.function_code:02X} {func_name}")
        )

        if resp.is_error:
            # 错误响应
            error_text = f"{self.i18n.tr('text_error_prefix')} {resp.error_msg}"
            self.response_table.setItem(row, 3, QTableWidgetItem(error_text))
            self.response_table.setItem(row, 4, QTableWidgetItem(""))
            self.response_table.setItem(row, 5, QTableWidgetItem(""))
        else:
            # 正常响应
            if resp.registers:
                first_reg = resp.registers[0]
                self.response_table.setItem(row, 3, QTableWidgetItem(f"0x{first_reg.address:04X}"))
                self.response_table.setItem(
                    row, 4, QTableWidgetItem(f"0x{first_reg.raw_value:04X}")
                )
                self.response_table.setItem(row, 5, QTableWidgetItem(str(first_reg.signed_value)))

                # 更新寄存器详情表
                self._update_register_table(resp.registers)
            else:
                self.response_table.setItem(row, 3, QTableWidgetItem(self.i18n.tr("text_write_op")))
                self.response_table.setItem(row, 4, QTableWidgetItem(""))
                self.response_table.setItem(row, 5, QTableWidgetItem(""))

    def _get_func_name(self, func_code: int) -> str:
        """获取功能码名称"""
        key_by_code = {
            0x01: "func_01",
            0x02: "func_02",
            0x03: "func_03",
            0x04: "func_04",
            0x05: "func_05",
            0x06: "func_06",
            0x0F: "func_0f",
            0x10: "func_10",
        }
        if func_code & 0x80:
            return self.i18n.tr("func_error")
        return self.i18n.tr(key_by_code.get(func_code, "func_unknown"))

    def _update_register_table(self, registers):
        """更新寄存器详情表"""
        self.register_table.setRowCount(len(registers))
        for i, reg in enumerate(registers):
            self.register_table.setItem(i, 0, QTableWidgetItem(f"0x{reg.address:04X}"))
            self.register_table.setItem(i, 1, QTableWidgetItem(f"0x{reg.raw_value:04X}"))
            self.register_table.setItem(i, 2, QTableWidgetItem(str(reg.signed_value)))
            float_str = f"{reg.float_value:.4f}" if reg.float_value is not None else "-"
            self.register_table.setItem(i, 3, QTableWidgetItem(float_str))

    def clear(self):
        """清空"""
        self.response_table.setRowCount(0)
        self.register_table.setRowCount(0)
        self.parser.clear()


# ─── 日志设置对话框 ──────────────────────────────────────────


class LogSettingsDialog(QDialog):
    """日志设置对话框"""

    def __init__(
        self, parent=None, config: LogConfig | None = None, i18n: I18nManager | None = None
    ):
        super().__init__(parent)
        self.i18n = i18n or I18nManager()
        self.setFixedSize(450, 300)
        self.config = config or LogConfig()
        self.init_ui()
        self.retranslate_ui()
        self.load_config()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setWindowTitle(tr("dialog_log_settings"))
        self.enable_check.setText(tr("check_enable_log"))
        self.browse_btn.setText(tr("btn_browse"))
        self.dir_label.setText(tr("label_log_dir"))
        _retranslate_combo(
            self.mode_combo,
            [tr("rotate_none"), tr("rotate_size"), tr("rotate_time"), tr("rotate_day")],
        )
        self.mode_label.setText(tr("label_rotate_mode"))
        self.size_label.setText(tr("label_max_size"))
        self.interval_label.setText(tr("label_rotate_interval"))
        self.interval_spin.setSuffix(tr("suffix_minutes"))
        self.max_files_label.setText(tr("label_max_files"))

    def init_ui(self):
        layout = QFormLayout(self)

        # 启用日志
        self.enable_check = QCheckBox()
        layout.addRow(self.enable_check)

        # 日志目录
        dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        dir_layout.addWidget(self.dir_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(self.browse_btn)
        self.dir_label = QLabel()
        layout.addRow(self.dir_label, dir_layout)

        # 轮转模式
        self.mode_combo = QComboBox()
        self.mode_label = QLabel()
        layout.addRow(self.mode_label, self.mode_combo)

        # 最大大小 (MB)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 1000)
        self.size_spin.setValue(10)
        self.size_spin.setSuffix(" MB")
        self.size_label = QLabel()
        layout.addRow(self.size_label, self.size_spin)

        # 轮转间隔 (分钟)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(60)
        self.interval_label = QLabel()
        layout.addRow(self.interval_label, self.interval_spin)

        # 最大文件数
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 1000)
        self.max_files_spin.setValue(50)
        self.max_files_label = QLabel()
        layout.addRow(self.max_files_label, self.max_files_spin)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_dir(self):
        """浏览目录"""
        dir_path = QFileDialog.getExistingDirectory(self, self.i18n.tr("title_browse_log_dir"))
        if dir_path:
            self.dir_edit.setText(dir_path)

    def load_config(self):
        """加载配置到 UI"""
        self.enable_check.setChecked(self.config.enabled)
        self.dir_edit.setText(self.config.log_dir)

        mode_map = {
            RotateMode.NONE: 0,
            RotateMode.BY_SIZE: 1,
            RotateMode.BY_TIME: 2,
            RotateMode.BY_DAY: 3,
        }
        self.mode_combo.setCurrentIndex(mode_map.get(self.config.rotate_mode, 0))
        self.size_spin.setValue(int(self.config.max_size_mb))
        self.interval_spin.setValue(self.config.rotate_interval_min)
        self.max_files_spin.setValue(self.config.max_files)

    def get_config(self) -> LogConfig:
        """从 UI 获取配置"""
        mode_map = {
            0: RotateMode.NONE,
            1: RotateMode.BY_SIZE,
            2: RotateMode.BY_TIME,
            3: RotateMode.BY_DAY,
        }

        return LogConfig(
            enabled=self.enable_check.isChecked(),
            log_dir=self.dir_edit.text(),
            rotate_mode=mode_map.get(self.mode_combo.currentIndex(), RotateMode.NONE),
            max_size_mb=self.size_spin.value(),
            rotate_interval_min=self.interval_spin.value(),
            max_files=self.max_files_spin.value(),
        )


# ─── 脚本编辑器面板 ─────────────────────────────────────────


class ScriptEditorPanel(QGroupBox):
    """Python 脚本编辑器面板"""

    send_data = pyqtSignal(bytes)
    script_log = pyqtSignal(str)
    script_finished = pyqtSignal(bool, str)
    script_state_changed = pyqtSignal(str)

    _STATE_KEYS = {
        "idle": "status_idle",
        "running": "status_running",
        "paused": "status_paused",
        "stopped": "status_stopped",
        "error": "status_error",
        "breakpoint": "status_breakpoint",
    }
    _RUNNING_STATES = ("running", "paused", "breakpoint")

    def __init__(self, serial_manager=None, i18n: I18nManager | None = None):
        self.i18n = i18n or I18nManager()
        super().__init__()
        self.serial_manager = serial_manager
        self.engine = ScriptEngine(serial_manager) if serial_manager else None
        if self.engine:
            # 引擎在工作线程中回调，经信号跨线程安全地更新 UI；
            # 主窗口将 script_log 连接到 append_log（见 main_window._connect_signals）
            self.engine.on_log = self.script_log.emit
            self.engine.on_finished = self.script_finished.emit
            self.engine.on_state_changed = lambda state: self.script_state_changed.emit(state.value)
        self.init_ui()
        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setTitle(tr("group_script"))
        self.example_label.setText(tr("label_example"))
        self.run_btn.setText(tr("btn_run"))
        self.pause_btn.setText(tr("btn_pause"))
        self.resume_btn.setText(tr("btn_resume"))
        self.step_btn.setText(tr("btn_step"))
        self.stop_btn.setText(tr("btn_stop"))
        self.clear_output_btn.setText(tr("btn_clear_output"))
        self.output_label.setText(tr("label_output"))
        self._update_controls(self._last_state)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 示例选择
        ctrl = QHBoxLayout()
        self.example_label = QLabel()
        ctrl.addWidget(self.example_label)
        self.example_combo = QComboBox()
        self.example_combo.addItems(list(EXAMPLE_SCRIPTS.keys()))
        self.example_combo.currentTextChanged.connect(self._load_example)
        ctrl.addWidget(self.example_combo)

        self.run_btn = QPushButton()
        self.run_btn.clicked.connect(self._run_script)
        ctrl.addWidget(self.run_btn)

        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self._pause_script)
        ctrl.addWidget(self.pause_btn)

        self.resume_btn = QPushButton()
        self.resume_btn.clicked.connect(self._resume_script)
        ctrl.addWidget(self.resume_btn)

        self.step_btn = QPushButton()
        self.step_btn.clicked.connect(self._step_script)
        ctrl.addWidget(self.step_btn)

        self.stop_btn = QPushButton()
        self.stop_btn.clicked.connect(self._stop_script)
        ctrl.addWidget(self.stop_btn)

        self.clear_output_btn = QPushButton()
        self.clear_output_btn.clicked.connect(self._clear_output)
        ctrl.addWidget(self.clear_output_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 代码编辑区
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFont(QFont("Consolas", 10))
        layout.addWidget(self.code_edit)

        # 输出区
        head = QHBoxLayout()
        self.output_label = QLabel()
        head.addWidget(self.output_label)
        self.state_label = QLabel()
        head.addWidget(self.state_label)
        head.addStretch()
        layout.addLayout(head)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont("Consolas", 9))
        self.output_text.setMaximumHeight(150)
        layout.addWidget(self.output_text)

        self.script_finished.connect(self._on_engine_finished)
        self.script_state_changed.connect(self._on_engine_state)

        # 加载下拉框当前选中的示例（此前写死了一个不存在的示例名，代码区一直是空的）
        self._load_example(self.example_combo.currentText())
        self._last_state = "idle"
        self._update_controls("idle")

    def _load_example(self, name: str):
        """加载示例脚本"""
        if name in EXAMPLE_SCRIPTS:
            self.code_edit.setPlainText(EXAMPLE_SCRIPTS[name])

    def _run_script(self):
        """运行脚本"""
        if not self.engine:
            self.output_text.append(self.i18n.tr("script_no_manager"))
            return
        self.engine.execute(self.code_edit.toPlainText())

    def _pause_script(self):
        """暂停脚本"""
        if self.engine:
            self.engine.pause()

    def _resume_script(self):
        """恢复脚本"""
        if self.engine:
            self.engine.resume()

    def _step_script(self):
        """单步执行脚本"""
        if self.engine:
            self.engine.step_over()

    def _stop_script(self):
        """停止脚本"""
        if self.engine:
            self.engine.stop()

    def _on_engine_state(self, state: str):
        """引擎状态变化（由 script_state_changed 跨线程触发）"""
        self._update_controls(state)

    def _update_controls(self, state: str):
        """按引擎状态切换按钮可用性，避免运行结束后按钮失真"""
        self._last_state = state
        state_text = self.i18n.tr(self._STATE_KEYS.get(state, "status_error"))
        self.state_label.setText(f"{self.i18n.tr('label_status_prefix')} {state_text}")
        running = state in self._RUNNING_STATES
        self.run_btn.setEnabled(self.engine is not None and not running)
        self.pause_btn.setEnabled(state == "running")
        self.resume_btn.setEnabled(state in ("paused", "breakpoint"))
        self.step_btn.setEnabled(state in ("paused", "breakpoint"))
        self.stop_btn.setEnabled(running)

    def _on_engine_finished(self, success: bool, msg: str):
        """脚本结束（由 script_finished 跨线程触发）"""
        key = "script_finished_ok" if success else "script_finished_fail"
        self.output_text.append(self.i18n.tr(key, msg))

    @pyqtSlot(str)
    def append_log(self, msg: str):
        """追加日志（由 script_log 信号跨线程触发）"""
        self.output_text.append(msg)

    def _clear_output(self):
        """清空输出区"""
        self.output_text.clear()


# ─── 多串口对比面板 ─────────────────────────────────────────


class MultiSerialComparePanel(QGroupBox):
    """多串口对比面板"""

    def __init__(self, manager, i18n: I18nManager | None = None):
        self.i18n = i18n or I18nManager()
        super().__init__()
        self.multi_manager = manager
        self.text_areas = {}
        self.slot_connect_buttons: list[QPushButton] = []
        self.init_ui()
        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setTitle(tr("group_compare"))
        self.clear_all_btn.setText(tr("btn_clear_all"))
        for button in self.slot_connect_buttons:
            button.setText(tr("btn_slot_connect"))
        for name, text_area in self.text_areas.items():
            text_area.setPlaceholderText(tr("slot_placeholder", name))

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 控制栏
        ctrl = QHBoxLayout()
        for name in ["Port A", "Port B", "Port C", "Port D"]:
            slot_widget = self._create_slot_widget(name)
            ctrl.addWidget(slot_widget)

        ctrl.addStretch()

        self.clear_all_btn = QPushButton()
        self.clear_all_btn.clicked.connect(self.clear_all)
        ctrl.addWidget(self.clear_all_btn)

        layout.addLayout(ctrl)

        # 显示区域 (2x2 网格)
        grid_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.text_areas["Port A"] = self._create_text_area("Port A")
        self.text_areas["Port B"] = self._create_text_area("Port B")
        row1.addWidget(self.text_areas["Port A"])
        row1.addWidget(self.text_areas["Port B"])
        grid_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.text_areas["Port C"] = self._create_text_area("Port C")
        self.text_areas["Port D"] = self._create_text_area("Port D")
        row2.addWidget(self.text_areas["Port C"])
        row2.addWidget(self.text_areas["Port D"])
        grid_layout.addLayout(row2)

        layout.addLayout(grid_layout)

    def _create_slot_widget(self, name: str) -> QWidget:
        """创建槽位控制组件"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        check = QCheckBox(name)
        check.stateChanged.connect(lambda state, n=name: self._on_slot_toggled(n, state))
        layout.addWidget(check)

        connect_btn = QPushButton()
        self.slot_connect_buttons.append(connect_btn)
        connect_btn.clicked.connect(lambda checked, n=name: self._connect_slot(n))
        layout.addWidget(connect_btn)

        return widget

    def _create_text_area(self, name: str) -> QTextEdit:
        """创建文本显示区域"""
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont("Consolas", 9))
        text.setMaximumHeight(150)
        return text

    def _on_slot_toggled(self, name: str, state: int):
        """槽位激活切换"""
        active = state == Qt.CheckState.Checked.value
        self.multi_manager.set_active(name, active)

    def _connect_slot(self, name: str):
        """连接槽位 (简化版，实际需要弹出配置对话框)"""
        # 这里简化处理，实际应该弹出配置对话框
        QMessageBox.information(
            self, self.i18n.tr("title_hint"), self.i18n.tr("msg_slot_hint", name)
        )

    def append_data(self, slot_name: str, data: bytes, hex_mode: bool = False):
        """追加数据到指定槽位"""
        if slot_name in self.text_areas:
            text_area = self.text_areas[slot_name]
            if hex_mode:
                text = " ".join(f"{b:02X}" for b in data)
            else:
                text = data.decode("utf-8", errors="replace")
            text_area.append(text)

    def clear_all(self):
        """清空全部"""
        for text_area in self.text_areas.values():
            text_area.clear()


# ─── 协议模板管理对话框 ─────────────────────────────────────


class ProtocolTemplateDialog(QDialog):
    """自定义协议模板管理对话框"""

    def __init__(self, parent=None, template_manager=None, i18n: I18nManager | None = None):
        super().__init__(parent)
        self.i18n = i18n or I18nManager()
        self.setFixedSize(800, 600)
        self.template_manager: ProtocolTemplateManager = (
            template_manager or ProtocolTemplateManager()
        )
        self.init_ui()
        self.retranslate_ui()
        self.refresh_template_list()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setWindowTitle(tr("dialog_template_mgmt"))
        self.desc_label.setText(tr("desc_templates"))
        self.loaded_label.setText(tr("label_loaded_templates"))
        self.new_btn.setText(tr("btn_new"))
        self.sample_btn.setText(tr("btn_sample"))
        self.del_btn.setText(tr("btn_delete"))
        self.json_label.setText(tr("label_template_json"))
        self.preview_label.setText(tr("label_preview"))

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部说明
        self.desc_label = QLabel()
        layout.addWidget(self.desc_label)

        # 主体分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：模板列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        self.loaded_label = QLabel()
        left_layout.addWidget(self.loaded_label)

        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        left_layout.addWidget(self.template_list)

        # 左侧按钮
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton()
        self.new_btn.clicked.connect(self._create_new_template)
        btn_layout.addWidget(self.new_btn)

        self.sample_btn = QPushButton()
        self.sample_btn.clicked.connect(self._load_sample_template)
        btn_layout.addWidget(self.sample_btn)

        self.del_btn = QPushButton()
        self.del_btn.clicked.connect(self._delete_template)
        btn_layout.addWidget(self.del_btn)

        left_layout.addLayout(btn_layout)
        splitter.addWidget(left_widget)

        # 右侧：JSON 编辑区
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        self.json_label = QLabel()
        right_layout.addWidget(self.json_label)

        self.json_edit = QPlainTextEdit()
        self.json_edit.setFont(QFont("Consolas", 10))
        right_layout.addWidget(self.json_edit)

        # 预览区
        self.preview_label = QLabel()
        right_layout.addWidget(self.preview_label)
        self.preview_text = QTextBrowser()
        self.preview_text.setFont(QFont("Consolas", 9))
        self.preview_text.setMaximumHeight(120)
        right_layout.addWidget(self.preview_text)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

        # 底部按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        assert save_btn is not None and close_btn is not None
        save_btn.clicked.connect(self._save_template)
        close_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

    def refresh_template_list(self):
        """刷新模板列表"""
        self.template_list.clear()
        for name in sorted(self.template_manager.list_templates()):
            self.template_list.addItem(name)

    def _on_template_selected(self, current, previous):
        """模板选择变化"""
        if not current:
            return
        name = current.text()
        template = self.template_manager.get_template(name)
        if template:
            self.json_edit.setPlainText(
                json.dumps(template.to_dict(), ensure_ascii=False, indent=2)
            )
            self._update_preview(template)

    def _create_new_template(self):
        """创建新模板"""
        template = create_sample_template()
        template.name = "My-Custom-Protocol"
        self.json_edit.setPlainText(json.dumps(template.to_dict(), ensure_ascii=False, indent=2))
        self._update_preview(template)

    def _load_sample_template(self):
        """加载示例模板"""
        template = create_sample_template()
        self.json_edit.setPlainText(json.dumps(template.to_dict(), ensure_ascii=False, indent=2))
        self._update_preview(template)

    def _delete_template(self):
        """删除模板"""
        current = self.template_list.currentItem()
        if not current:
            return
        name = current.text()
        reply = QMessageBox.question(
            self,
            self.i18n.tr("title_confirm_delete"),
            self.i18n.tr("msg_confirm_delete", name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.template_manager.delete_template(name)
            self.refresh_template_list()

    def _save_template(self):
        """保存模板"""
        try:
            data = json.loads(self.json_edit.toPlainText())
            template = ProtocolTemplate.from_dict(data)
            if not template.name:
                raise ValueError(self.i18n.tr("err_template_name"))
            self.template_manager.save_template(template)
            self.refresh_template_list()
            QMessageBox.information(
                self,
                self.i18n.tr("title_save_success"),
                self.i18n.tr("msg_template_saved", template.name),
            )
        except Exception as e:
            QMessageBox.critical(
                self, self.i18n.tr("title_save_fail"), self.i18n.tr("msg_json_error", str(e))
            )

    def _update_preview(self, template: ProtocolTemplate):
        """更新预览信息"""
        tr = self.i18n.tr
        fields = template.fields
        field_lines = []
        for f in fields:
            field_lines.append(f"  - {f.get('name')}: {f.get('type')} @ offset {f.get('offset')}")

        preview = [
            f"{tr('pv_name')} {template.name}",
            f"{tr('pv_desc')} {template.description}",
            f"{tr('pv_header')} {template.header or tr('pv_none')}",
            f"{tr('pv_tail')} {template.tail or tr('pv_none')}",
            f"{tr('pv_min_len')} {template.min_length}",
            "",
            tr("pv_fields"),
        ]
        if field_lines:
            preview.extend(field_lines)
        else:
            preview.append(f"  {tr('pv_no_fields')}")

        self.preview_text.setPlainText("\n".join(preview))
