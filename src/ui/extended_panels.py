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

# ─── Modbus 响应解析面板 ─────────────────────────────────────

class ModbusResponsePanel(QGroupBox):
    """Modbus 响应解析结果面板"""

    def __init__(self):
        super().__init__('Modbus 响应解析')
        self.parser = ModbusResponseParser()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 控制栏
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel('自动检测 Modbus 帧并解析寄存器值'))
        ctrl.addStretch()

        clear_btn = QPushButton('清空')
        clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(clear_btn)

        layout.addLayout(ctrl)

        # 响应历史表格
        self.response_table = QTableWidget()
        self.response_table.setColumnCount(6)
        self.response_table.setHorizontalHeaderLabels([
            '时间', '从机', '功能码', '寄存器地址', '原始值', '有符号值'
        ])
        self.response_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.response_table.setMaximumHeight(200)
        layout.addWidget(self.response_table)

        # 寄存器值详情
        self.register_table = QTableWidget()
        self.register_table.setColumnCount(4)
        self.register_table.setHorizontalHeaderLabels([
            '地址', 'HEX', 'DEC (有符号)', 'Float (IEEE754)'
        ])
        self.register_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.register_table.setMaximumHeight(150)
        layout.addWidget(QLabel('寄存器详情:'))
        layout.addWidget(self.register_table)

    def feed_data(self, data: bytes):
        """喂入数据，自动解析"""
        responses = self.parser.feed(data)
        for resp in responses:
            self._add_response(resp)

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
        self.response_table.setItem(row, 2, QTableWidgetItem(f"0x{resp.function_code:02X} {func_name}"))

        if resp.is_error:
            # 错误响应
            self.response_table.setItem(row, 3, QTableWidgetItem(f"错误: {resp.error_msg}"))
            self.response_table.setItem(row, 4, QTableWidgetItem(""))
            self.response_table.setItem(row, 5, QTableWidgetItem(""))
        else:
            # 正常响应
            if resp.registers:
                first_reg = resp.registers[0]
                self.response_table.setItem(row, 3, QTableWidgetItem(f"0x{first_reg.address:04X}"))
                self.response_table.setItem(row, 4, QTableWidgetItem(f"0x{first_reg.raw_value:04X}"))
                self.response_table.setItem(row, 5, QTableWidgetItem(str(first_reg.signed_value)))

                # 更新寄存器详情表
                self._update_register_table(resp.registers)
            else:
                self.response_table.setItem(row, 3, QTableWidgetItem("写操作"))
                self.response_table.setItem(row, 4, QTableWidgetItem(""))
                self.response_table.setItem(row, 5, QTableWidgetItem(""))

    def _get_func_name(self, func_code: int) -> str:
        """获取功能码名称"""
        names = {
            0x01: "读线圈",
            0x02: "读离散输入",
            0x03: "读保持寄存器",
            0x04: "读输入寄存器",
            0x05: "写单个线圈",
            0x06: "写单个寄存器",
            0x0F: "写多个线圈",
            0x10: "写多个寄存器",
        }
        if func_code & 0x80:
            return "错误"
        return names.get(func_code, "未知")

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

    def __init__(self, parent=None, config: LogConfig = None):
        super().__init__(parent)
        self.setWindowTitle("日志设置")
        self.setFixedSize(450, 300)
        self.config = config or LogConfig()
        self.init_ui()
        self.load_config()

    def init_ui(self):
        layout = QFormLayout(self)

        # 启用日志
        self.enable_check = QCheckBox("启用自动日志记录")
        layout.addRow(self.enable_check)

        # 日志目录
        dir_layout = QHBoxLayout()
        self.dir_edit = QLineEdit()
        dir_layout.addWidget(self.dir_edit)
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(browse_btn)
        layout.addRow("日志目录:", dir_layout)

        # 轮转模式
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "不轮转",
            "按大小",
            "按时间",
            "按天"
        ])
        layout.addRow("轮转模式:", self.mode_combo)

        # 最大大小 (MB)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 1000)
        self.size_spin.setValue(10)
        self.size_spin.setSuffix(" MB")
        layout.addRow("最大文件大小:", self.size_spin)

        # 轮转间隔 (分钟)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(60)
        self.interval_spin.setSuffix(" 分钟")
        layout.addRow("轮转间隔:", self.interval_spin)

        # 最大文件数
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 1000)
        self.max_files_spin.setValue(50)
        layout.addRow("最多保留文件:", self.max_files_spin)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _browse_dir(self):
        """浏览目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择日志目录")
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

    def __init__(self, serial_manager=None):
        super().__init__('Python 脚本引擎')
        self.serial_manager = serial_manager
        self.engine = ScriptEngine(serial_manager) if serial_manager else None
        if self.engine:
            # 引擎在工作线程中回调，经信号跨线程安全地更新 UI；
            # 主窗口将 script_log 连接到 append_log（见 main_window._connect_signals）
            self.engine.on_log = self.script_log.emit
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 示例选择
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel('示例脚本:'))
        self.example_combo = QComboBox()
        self.example_combo.addItems(list(EXAMPLE_SCRIPTS.keys()))
        self.example_combo.currentTextChanged.connect(self._load_example)
        ctrl.addWidget(self.example_combo)

        run_btn = QPushButton('▶️ 运行')
        run_btn.clicked.connect(self._run_script)
        ctrl.addWidget(run_btn)

        clear_btn = QPushButton('清空输出')
        clear_btn.clicked.connect(self._clear_output)
        ctrl.addWidget(clear_btn)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # 代码编辑区
        self.code_edit = QPlainTextEdit()
        self.code_edit.setFont(QFont('Consolas', 10))
        layout.addWidget(self.code_edit)

        # 输出区
        layout.addWidget(QLabel('输出:'))
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFont(QFont('Consolas', 9))
        self.output_text.setMaximumHeight(150)
        layout.addWidget(self.output_text)

        # 加载默认示例
        self._load_example('发送递增字节')

    def _load_example(self, name: str):
        """加载示例脚本"""
        if name in EXAMPLE_SCRIPTS:
            self.code_edit.setPlainText(EXAMPLE_SCRIPTS[name])

    def _run_script(self):
        """运行脚本"""
        code = self.code_edit.toPlainText()
        if self.engine:
            self.engine.execute(code)
        self.output_text.append("脚本执行完毕")

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

    def __init__(self, manager):
        super().__init__('多串口对比')
        self.multi_manager = manager
        self.text_areas = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 控制栏
        ctrl = QHBoxLayout()
        for name in ['Port A', 'Port B', 'Port C', 'Port D']:
            slot_widget = self._create_slot_widget(name)
            ctrl.addWidget(slot_widget)

        ctrl.addStretch()

        clear_btn = QPushButton('清空全部')
        clear_btn.clicked.connect(self.clear_all)
        ctrl.addWidget(clear_btn)

        layout.addLayout(ctrl)

        # 显示区域 (2x2 网格)
        grid_layout = QVBoxLayout()

        row1 = QHBoxLayout()
        self.text_areas['Port A'] = self._create_text_area('Port A')
        self.text_areas['Port B'] = self._create_text_area('Port B')
        row1.addWidget(self.text_areas['Port A'])
        row1.addWidget(self.text_areas['Port B'])
        grid_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.text_areas['Port C'] = self._create_text_area('Port C')
        self.text_areas['Port D'] = self._create_text_area('Port D')
        row2.addWidget(self.text_areas['Port C'])
        row2.addWidget(self.text_areas['Port D'])
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

        connect_btn = QPushButton('连接')
        connect_btn.clicked.connect(lambda checked, n=name: self._connect_slot(n))
        layout.addWidget(connect_btn)

        return widget

    def _create_text_area(self, name: str) -> QTextEdit:
        """创建文本显示区域"""
        text = QTextEdit()
        text.setReadOnly(True)
        text.setFont(QFont('Consolas', 9))
        text.setPlaceholderText(f'{name} - 未连接')
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
            self, '提示',
            f'请在主界面配置 {name} 的串口参数\n'
            '多串口完整配置功能开发中...'
        )

    def append_data(self, slot_name: str, data: bytes, hex_mode: bool = False):
        """追加数据到指定槽位"""
        if slot_name in self.text_areas:
            text_area = self.text_areas[slot_name]
            if hex_mode:
                text = ' '.join(f'{b:02X}' for b in data)
            else:
                text = data.decode('utf-8', errors='replace')
            text_area.append(text)

    def clear_all(self):
        """清空全部"""
        for text_area in self.text_areas.values():
            text_area.clear()


# ─── 协议模板管理对话框 ─────────────────────────────────────

class ProtocolTemplateDialog(QDialog):
    """自定义协议模板管理对话框"""

    def __init__(self, parent=None, template_manager=None):
        super().__init__(parent)
        self.setWindowTitle("协议模板管理")
        self.setFixedSize(800, 600)
        self.template_manager: ProtocolTemplateManager = template_manager or ProtocolTemplateManager()
        self.init_ui()
        self.refresh_template_list()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 顶部说明
        desc = QLabel("通过 JSON 模板定义自定义协议帧格式，无需编写 Python 代码")
        layout.addWidget(desc)

        # 主体分割
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：模板列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("已加载模板:"))

        self.template_list = QListWidget()
        self.template_list.currentItemChanged.connect(self._on_template_selected)
        left_layout.addWidget(self.template_list)

        # 左侧按钮
        btn_layout = QHBoxLayout()
        new_btn = QPushButton("➕ 新建")
        new_btn.clicked.connect(self._create_new_template)
        btn_layout.addWidget(new_btn)

        sample_btn = QPushButton("📋 示例")
        sample_btn.clicked.connect(self._load_sample_template)
        btn_layout.addWidget(sample_btn)

        del_btn = QPushButton("🗑️ 删除")
        del_btn.clicked.connect(self._delete_template)
        btn_layout.addWidget(del_btn)

        left_layout.addLayout(btn_layout)
        splitter.addWidget(left_widget)

        # 右侧：JSON 编辑区
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.addWidget(QLabel("模板 JSON:"))

        self.json_edit = QPlainTextEdit()
        self.json_edit.setFont(QFont('Consolas', 10))
        right_layout.addWidget(self.json_edit)

        # 预览区
        right_layout.addWidget(QLabel("预览:"))
        self.preview_text = QTextBrowser()
        self.preview_text.setFont(QFont('Consolas', 9))
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
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save_template)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.reject)
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
            self.json_edit.setPlainText(json.dumps(template.to_dict(), ensure_ascii=False, indent=2))
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
            self, '确认删除',
            f'确定删除模板 "{name}" 吗？',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
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
                raise ValueError("模板名称不能为空")
            self.template_manager.save_template(template)
            self.refresh_template_list()
            QMessageBox.information(self, '保存成功', f'模板 "{template.name}" 已保存')
        except Exception as e:
            QMessageBox.critical(self, '保存失败', f'JSON 格式错误: {str(e)}')

    def _update_preview(self, template: ProtocolTemplate):
        """更新预览信息"""
        fields = template.fields
        field_lines = []
        for f in fields:
            field_lines.append(f"  - {f.get('name')}: {f.get('type')} @ offset {f.get('offset')}")

        preview = [
            f"协议名称: {template.name}",
            f"描述: {template.description}",
            f"帧头: {template.header or '(无)'}",
            f"帧尾: {template.tail or '(无)'}",
            f"最小长度: {template.min_length}",
            "",
            "字段列表:",
        ]
        if field_lines:
            preview.extend(field_lines)
        else:
            preview.append("  (无字段定义)")

        self.preview_text.setPlainText('\n'.join(preview))
