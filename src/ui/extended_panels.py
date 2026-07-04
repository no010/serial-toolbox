"""
扩展 UI 组件
v3.0 新增面板: Modbus解析、日志设置、脚本编辑器、多串口对比
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QTextEdit, QComboBox, QSpinBox, QCheckBox, QLineEdit,
    QDialog, QFormLayout, QDialogButtonBox, QTabWidget,
    QPlainTextEdit, QMessageBox, QFileDialog, QListWidget,
    QListWidgetItem, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat

from src.core.modbus_parser import ModbusResponseParser, ModbusResponse
from src.core.log_rotator import LogConfig, RotateMode
from src.core.script_engine import ScriptEngine, ScriptState, EXAMPLE_SCRIPTS


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
            max_size_mb=float(self.size_spin.value()),
            rotate_interval_min=self.interval_spin.value(),
            max_files=self.max_files_spin.value(),
        )


# ─── Python 语法高亮 ────────────────────────────────────────

class PythonHighlighter(QSyntaxHighlighter):
    """Python 语法高亮"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 关键字
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor('#569CD6'))
        keyword_format.setFontWeight(700)
        keywords = [
            'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
            'def', 'del', 'elif', 'else', 'except', 'False', 'finally', 'for',
            'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'None',
            'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'True', 'try',
            'while', 'with', 'yield'
        ]
        self.rules = [(r'\b' + kw + r'\b', keyword_format) for kw in keywords]
        
        # 字符串
        string_format = QTextCharFormat()
        string_format.setForeground(QColor('#CE9178'))
        self.rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', string_format))
        self.rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", string_format))
        
        # 注释
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor('#6A9955'))
        self.rules.append((r'#[^\n]*', comment_format))
        
        # 数字
        number_format = QTextCharFormat()
        number_format.setForeground(QColor('#B5CEA8'))
        self.rules.append((r'\b\d+\b', number_format))
    
    def highlightBlock(self, text: str):
        """高亮文本块"""
        for pattern, fmt in self.rules:
            import re
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


# ─── 脚本编辑器面板 ─────────────────────────────────────────

class ScriptEditorPanel(QGroupBox):
    """脚本编辑器面板"""
    
    script_log = pyqtSignal(str)
    
    def __init__(self, serial_manager):
        super().__init__('Python 脚本引擎')
        self.engine = ScriptEngine(serial_manager)
        self.init_ui()
        self.setup_engine_callbacks()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 工具栏
        toolbar = QHBoxLayout()
        
        # 示例脚本选择
        toolbar.addWidget(QLabel('示例:'))
        self.example_combo = QComboBox()
        self.example_combo.addItems(['自定义'] + list(EXAMPLE_SCRIPTS.keys()))
        self.example_combo.currentTextChanged.connect(self._load_example)
        toolbar.addWidget(self.example_combo)
        
        toolbar.addStretch()
        
        # 控制按钮
        self.run_btn = QPushButton('▶ 运行')
        self.run_btn.clicked.connect(self._run_script)
        toolbar.addWidget(self.run_btn)
        
        self.pause_btn = QPushButton('⏸ 暂停')
        self.pause_btn.clicked.connect(self._pause_script)
        self.pause_btn.setEnabled(False)
        toolbar.addWidget(self.pause_btn)
        
        self.stop_btn = QPushButton('⏹ 停止')
        self.stop_btn.clicked.connect(self._stop_script)
        self.stop_btn.setEnabled(False)
        toolbar.addWidget(self.stop_btn)
        
        layout.addLayout(toolbar)
        
        # 编辑器
        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont('Consolas', 10))
        self.editor.setPlaceholderText('# 在这里编写 Python 脚本\n# 可用 API: send(), sleep(), log_info(), log_error(), log_success()\n')
        self.highlighter = PythonHighlighter(self.editor.document())
        layout.addWidget(self.editor)
        
        # 输出日志
        layout.addWidget(QLabel('执行日志:'))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Consolas', 9))
        self.log_text.setMaximumHeight(120)
        layout.addWidget(self.log_text)
        
        # 状态标签
        self.status_label = QLabel('状态: 空闲')
        self.status_label.setStyleSheet('color: gray;')
        layout.addWidget(self.status_label)
    
    def setup_engine_callbacks(self):
        """设置引擎回调"""
        self.engine.on_log = lambda msg: self.script_log.emit(msg)
        self.engine.on_state_changed = self._on_state_changed
        self.engine.on_finished = self._on_finished
    
    def _load_example(self, name: str):
        """加载示例脚本"""
        if name in EXAMPLE_SCRIPTS:
            self.editor.setPlainText(EXAMPLE_SCRIPTS[name])
    
    def _run_script(self):
        """运行脚本"""
        script = self.editor.toPlainText()
        if not script.strip():
            QMessageBox.warning(self, '警告', '脚本为空')
            return
        self.log_text.clear()
        self.engine.execute(script)
    
    def _pause_script(self):
        """暂停/恢复脚本"""
        if self.engine.state == ScriptState.RUNNING:
            self.engine.pause()
            self.pause_btn.setText('▶ 恢复')
        elif self.engine.state == ScriptState.PAUSED:
            self.engine.resume()
            self.pause_btn.setText('⏸ 暂停')
    
    def _stop_script(self):
        """停止脚本"""
        self.engine.stop()
    
    @pyqtSlot(str)
    def append_log(self, msg: str):
        """追加日志"""
        self.log_text.append(msg)
    
    def _on_state_changed(self, state: ScriptState):
        """状态变化"""
        state_map = {
            ScriptState.IDLE: ('空闲', 'color: gray;'),
            ScriptState.RUNNING: ('运行中', 'color: green;'),
            ScriptState.PAUSED: ('已暂停', 'color: orange;'),
            ScriptState.STOPPED: ('已停止', 'color: gray;'),
            ScriptState.ERROR: ('错误', 'color: red;'),
        }
        text, style = state_map.get(state, ('未知', 'color: gray;'))
        self.status_label.setText(f'状态: {text}')
        self.status_label.setStyleSheet(style)
        
        # 更新按钮状态
        is_running = state == ScriptState.RUNNING
        is_paused = state == ScriptState.PAUSED
        self.run_btn.setEnabled(not is_running)
        self.pause_btn.setEnabled(is_running or is_paused)
        self.stop_btn.setEnabled(is_running or is_paused)
        
        if is_paused:
            self.pause_btn.setText('▶ 恢复')
        else:
            self.pause_btn.setText('⏸ 暂停')
    
    def _on_finished(self, success: bool, msg: str):
        """脚本完成"""
        if success:
            self.append_log(f"[完成] {msg}")
        else:
            self.append_log(f"[失败] {msg}")


# ─── 多串口对比面板 ──────────────────────────────────────────

class MultiSerialComparePanel(QGroupBox):
    """多串口对比面板"""
    
    def __init__(self, multi_manager):
        super().__init__('多串口对比 (最多4路)')
        self.multi_manager = multi_manager
        self.text_areas = {}
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 控制栏
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel('选择要对比的串口:'))
        
        # 为每个槽位创建控制
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
