"""
主窗口 UI
基于 PyQt6 的串口调试助手界面
v3.0 - 新增: Modbus解析、日志轮转、脚本引擎、多串口对比
"""

import sys
import json
import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QComboBox, QPushButton, QTextEdit,
    QLineEdit, QCheckBox, QStatusBar, QMenuBar, QMenu,
    QSplitter, QFrame, QMessageBox, QTabWidget, QSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog,
    QFormLayout, QDialogButtonBox, QToolTip
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QTextCursor, QColor

import pyqtgraph as pg
import numpy as np

from src.core.serial_manager import SerialManager, SerialConfig, DataFormat
from src.core.protocol_parser import ModbusRTU, CRC16
from src.core.config_manager import ConfigManager
from src.core.log_rotator import RotatingLogWriter, LogConfig
from src.core.multi_serial_manager import MultiSerialManager
from src.core.protocol_plugin import ProtocolRegistry, StreamProtocolParser

# 扩展面板
from src.ui.extended_panels import (
    ModbusResponsePanel, LogSettingsDialog, ScriptEditorPanel,
    MultiSerialComparePanel
)
from src.ui.multi_port_dialog import MultiPortManagerDialog
from src.ui.enhanced_chart import EnhancedChart


# ─── 波形图组件 ───────────────────────────────────────────────

class RealtimeChart(QWidget):
    """实时数据波形图 (pyqtgraph)"""
    
    def __init__(self, max_points=500):
        super().__init__()
        self.max_points = max_points
        self.data_buffer = np.zeros(max_points)
        self.ptr = 0
        
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 控制栏
        ctrl = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['字节值 (0-255)', '解析为整数 (大端)', '解析为浮点 (IEEE754)'])
        ctrl.addWidget(QLabel('数据模式:'))
        ctrl.addWidget(self.mode_combo)
        
        ctrl.addWidget(QLabel('  最大点数:'))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(50, 5000)
        self.points_spin.setValue(self.max_points)
        self.points_spin.setSingleStep(50)
        self.points_spin.valueChanged.connect(self.update_max_points)
        ctrl.addWidget(self.points_spin)
        
        clear_btn = QPushButton('清空波形')
        clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(clear_btn)
        
        ctrl.addStretch()
        layout.addLayout(ctrl)
        
        # pyqtgraph 绘图
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', '数值')
        self.plot_widget.setLabel('bottom', '采样点')
        
        self.curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#4FC3F7', width=2),
            connect='finite'
        )
        
        layout.addWidget(self.plot_widget)
    
    def append_data(self, raw_bytes: bytes):
        """追加原始数据到波形"""
        mode = self.mode_combo.currentIndex()
        
        if mode == 0:  # 字节值
            values = list(raw_bytes)
        elif mode == 1:  # 整数 (2字节大端)
            values = []
            for i in range(0, len(raw_bytes) - 1, 2):
                val = int.from_bytes(raw_bytes[i:i+2], 'big', signed=True)
                values.append(val)
        else:  # 浮点 (4字节 IEEE754)
            values = []
            for i in range(0, len(raw_bytes) - 3, 4):
                val = np.frombuffer(raw_bytes[i:i+4], dtype='>f4')[0]
                values.append(float(val))
        
        for val in values:
            self.data_buffer[self.ptr % self.max_points] = val
            self.ptr += 1
        
        self._update_plot()
    
    def _update_plot(self):
        """更新绘图"""
        if self.ptr <= self.max_points:
            self.curve.setData(self.data_buffer[:self.ptr])
        else:
            # 滚动显示
            start = self.ptr % self.max_points
            rolled = np.roll(self.data_buffer, -start)
            self.curve.setData(rolled)
    
    def update_max_points(self, value):
        """更新最大点数"""
        self.max_points = value
        self.data_buffer = np.zeros(value)
        self.ptr = 0
        self.curve.clear()
    
    def clear(self):
        """清空"""
        self.data_buffer = np.zeros(self.max_points)
        self.ptr = 0
        self.curve.clear()


# ─── 预设指令编辑对话框 ─────────────────────────────────────

class PresetEditDialog(QDialog):
    """预设指令编辑对话框"""
    
    def __init__(self, parent=None, name="", data="", is_hex=False):
        super().__init__(parent)
        self.setWindowTitle("编辑预设指令")
        self.setFixedSize(400, 200)
        
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("指令名称")
        layout.addRow("名称:", self.name_edit)
        
        self.data_edit = QLineEdit(data)
        self.data_edit.setPlaceholderText("指令内容 (ASCII 或 HEX)")
        self.data_edit.setFont(QFont('Consolas', 10))
        layout.addRow("数据:", self.data_edit)
        
        self.hex_check = QCheckBox("HEX 格式")
        self.hex_check.setChecked(is_hex)
        layout.addRow("", self.hex_check)
        
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_values(self):
        return (
            self.name_edit.text(),
            self.data_edit.text(),
            self.hex_check.isChecked()
        )


# ─── Modbus 快捷操作面板 ─────────────────────────────────────

class ModbusPanel(QGroupBox):
    """Modbus RTU 快捷操作面板"""
    
    send_frame = pyqtSignal(bytes)
    
    def __init__(self):
        super().__init__('Modbus RTU 快捷操作')
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 第一行: 从机地址 + 功能码
        row1 = QHBoxLayout()
        row1.addWidget(QLabel('从机地址:'))
        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)
        row1.addWidget(self.slave_spin)
        
        row1.addWidget(QLabel('功能码:'))
        self.func_combo = QComboBox()
        self.func_combo.addItems([
            '0x03 读保持寄存器',
            '0x04 读输入寄存器',
            '0x06 写单个寄存器',
            '0x10 写多个寄存器',
        ])
        self.func_combo.currentIndexChanged.connect(self._on_func_changed)
        row1.addWidget(self.func_combo)
        row1.addStretch()
        layout.addLayout(row1)
        
        # 第二行: 寄存器地址 + 数量/值
        row2 = QHBoxLayout()
        row2.addWidget(QLabel('起始地址:'))
        self.reg_addr_spin = QSpinBox()
        self.reg_addr_spin.setRange(0, 65535)
        self.reg_addr_spin.setValue(0)
        self.reg_addr_spin.setDisplayIntegerBase(16)
        self.reg_addr_spin.setPrefix('0x')
        row2.addWidget(self.reg_addr_spin)
        
        row2.addWidget(QLabel('数量/值:'))
        self.quantity_spin = QSpinBox()
        self.quantity_spin.setRange(1, 125)
        self.quantity_spin.setValue(1)
        row2.addWidget(self.quantity_spin)
        
        row2.addStretch()
        layout.addLayout(row2)
        
        # 写多个寄存器的值输入
        self.values_row = QHBoxLayout()
        self.values_row.addWidget(QLabel('寄存器值 (逗号分隔):'))
        self.values_edit = QLineEdit()
        self.values_edit.setPlaceholderText("例: 100, 200, 300")
        self.values_edit.setFont(QFont('Consolas', 10))
        self.values_row.addWidget(self.values_edit)
        self.values_row_widget = QWidget()
        self.values_row_widget.setLayout(self.values_row)
        self.values_row_widget.setVisible(False)
        layout.addWidget(self.values_row_widget)
        
        # 操作按钮
        btn_row = QHBoxLayout()
        
        self.read_btn = QPushButton('📖 读取')
        self.read_btn.clicked.connect(self._do_read)
        btn_row.addWidget(self.read_btn)
        
        self.write_btn = QPushButton('✏️ 写入')
        self.write_btn.clicked.connect(self._do_write)
        btn_row.addWidget(self.write_btn)
        
        # CRC 计算按钮
        self.crc_btn = QPushButton('🔢 CRC 计算')
        self.crc_btn.clicked.connect(self._calc_crc)
        btn_row.addWidget(self.crc_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        # CRC 结果显示
        self.crc_label = QLabel('')
        self.crc_label.setFont(QFont('Consolas', 9))
        self.crc_label.setStyleSheet('color: #4FC3F7;')
        layout.addWidget(self.crc_label)
    
    def _on_func_changed(self, index):
        """功能码变化时切换 UI"""
        is_write_multi = (index == 3)  # 0x10
        self.values_row_widget.setVisible(is_write_multi)
        self.quantity_spin.setVisible(not is_write_multi)
    
    def _build_frame(self) -> bytes:
        """根据当前设置构建 Modbus 帧"""
        slave = self.slave_spin.value()
        func_idx = self.func_combo.currentIndex()
        addr = self.reg_addr_spin.value()
        
        if func_idx == 0:  # 0x03 读保持
            return ModbusRTU.build_read_holding_registers(slave, addr, self.quantity_spin.value())
        elif func_idx == 1:  # 0x04 读输入
            return ModbusRTU.build_read_input_registers(slave, addr, self.quantity_spin.value())
        elif func_idx == 2:  # 0x06 写单个
            return ModbusRTU.build_write_single_register(slave, addr, self.quantity_spin.value())
        elif func_idx == 3:  # 0x10 写多个
            values_text = self.values_edit.text().strip()
            if not values_text:
                return b''
            try:
                values = [int(v.strip()) for v in values_text.split(',') if v.strip()]
                return ModbusRTU.build_write_multiple_registers(slave, addr, values)
            except ValueError:
                return b''
        return b''
    
    def _do_read(self):
        """执行读取"""
        frame = self._build_frame()
        if frame:
            self.send_frame.emit(frame)
    
    def _do_write(self):
        """执行写入"""
        frame = self._build_frame()
        if frame:
            self.send_frame.emit(frame)
    
    def _calc_crc(self):
        """仅计算并显示 CRC"""
        frame = self._build_frame()
        if frame and len(frame) >= 4:
            crc = CRC16.calculate(frame[:-2])
            hex_str = ' '.join(f'{b:02X}' for b in frame)
            self.crc_label.setText(f'帧: {hex_str}  |  CRC: 0x{crc:04X}')


# ─── 主窗口 ──────────────────────────────────────────────────

class SerialToolboxMainWindow(QMainWindow):
    """串口调试助手主窗口 v3.0"""
    
    # 信号
    data_received = pyqtSignal(bytes)
    data_sent = pyqtSignal(bytes)
    
    def __init__(self):
        super().__init__()
        
        # 配置管理
        self.config_mgr = ConfigManager()
        self.app_config = self.config_mgr.load()
        
        # 串口管理器
        self.serial_manager = SerialManager()
        
        # 多串口管理器
        self.multi_manager = MultiSerialManager()
        
        # 协议注册表
        self.protocol_registry = ProtocolRegistry()
        self.stream_parser = StreamProtocolParser(self.protocol_registry)
        
        # 日志写入器
        self.log_writer = RotatingLogWriter(LogConfig(enabled=False))
        
        self.send_history = []
        self.received_bytes = 0
        self.sent_bytes = 0
        
        # 自动发送定时器
        self.auto_send_timer = QTimer()
        self.auto_send_timer.timeout.connect(self._auto_send_tick)
        
        self.init_ui()
        self.setup_connections()
        self.load_config_to_ui()
        self.scan_ports()
        
        # 状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)
    
    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle('串口调试助手 - Serial Toolbox v4.0')
        self.setGeometry(
            self.app_config.window_x, self.app_config.window_y,
            self.app_config.window_w, self.app_config.window_h
        )
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部: 串口配置
        main_layout.addWidget(self.create_serial_config_group())
        
        # 信号线控制栏
        main_layout.addWidget(self.create_signal_control_group())
        
        # 主内容区 - 使用分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧: 接收区 (文本 + 波形图 + Modbus解析 Tab)
        splitter.addWidget(self.create_receive_tabs())
        
        # 右侧: 发送区 + 预设 + Modbus
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(self.create_send_group())
        right_layout.addWidget(self.create_presets_group())
        right_layout.addWidget(ModbusPanel())
        right_layout.addStretch()
        
        splitter.addWidget(right_panel)
        splitter.setSizes([600, 400])
        main_layout.addWidget(splitter, 1)
        
        # 底部: 脚本编辑器 + 多串口对比 (Tab)
        bottom_tabs = QTabWidget()
        
        # 脚本编辑器
        self.script_panel = ScriptEditorPanel(self.serial_manager)
        bottom_tabs.addTab(self.script_panel, '🐍 脚本引擎')
        
        # 多串口对比
        self.compare_panel = MultiSerialComparePanel(self.multi_manager)
        bottom_tabs.addTab(self.compare_panel, '🔀 多串口对比')
        
        main_layout.addWidget(bottom_tabs)
        
        # 状态栏
        self.create_status_bar()
        
        # 设置样式
        self.apply_styles()
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件(&F)')
        
        export_action = QAction('导出日志(&E)', self)
        export_action.setShortcut('Ctrl+E')
        export_action.triggered.connect(self.export_log)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('退出(&X)', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 设置菜单
        settings_menu = menubar.addMenu('设置(&S)')
        
        clear_action = QAction('清空显示(&C)', self)
        clear_action.setShortcut('Ctrl+L')
        clear_action.triggered.connect(self.clear_display)
        settings_menu.addAction(clear_action)
        
        log_settings_action = QAction('日志设置...')
        log_settings_action.triggered.connect(self._show_log_settings)
        settings_menu.addAction(log_settings_action)
        
        save_config_action = QAction('保存配置', self)
        save_config_action.triggered.connect(self.save_config)
        settings_menu.addAction(save_config_action)
        
        multi_port_action = QAction('多串口管理器...')
        multi_port_action.triggered.connect(self._show_multi_port_manager)
        settings_menu.addAction(multi_port_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助(&H)')
        
        about_action = QAction('关于(&A)', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def create_serial_config_group(self) -> QGroupBox:
        """创建串口配置组"""
        group = QGroupBox('串口配置')
        layout = QHBoxLayout()
        
        # 串口选择
        layout.addWidget(QLabel('串口:'))
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(150)
        layout.addWidget(self.port_combo)
        
        # 刷新按钮
        self.refresh_btn = QPushButton('🔄 刷新')
        self.refresh_btn.clicked.connect(self.scan_ports)
        layout.addWidget(self.refresh_btn)
        
        # 波特率
        layout.addWidget(QLabel('波特率:'))
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600'])
        self.baudrate_combo.setCurrentText('115200')
        layout.addWidget(self.baudrate_combo)
        
        # 数据位
        layout.addWidget(QLabel('数据位:'))
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(['8', '7', '6', '5'])
        layout.addWidget(self.databits_combo)
        
        # 停止位
        layout.addWidget(QLabel('停止位:'))
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(['1', '1.5', '2'])
        layout.addWidget(self.stopbits_combo)
        
        # 校验位
        layout.addWidget(QLabel('校验:'))
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(['None', 'Even', 'Odd', 'Mark', 'Space'])
        layout.addWidget(self.parity_combo)
        
        # 连接按钮
        self.connect_btn = QPushButton('连接')
        self.connect_btn.setCheckable(True)
        self.connect_btn.setMinimumWidth(80)
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn)
        
        layout.addStretch()
        group.setLayout(layout)
        return group
    
    def create_signal_control_group(self) -> QGroupBox:
        """创建信号线控制组"""
        group = QGroupBox('信号线控制')
        layout = QHBoxLayout()
        
        # DTR
        self.dtr_check = QCheckBox('DTR')
        self.dtr_check.stateChanged.connect(self._on_dtr_changed)
        layout.addWidget(self.dtr_check)
        
        # RTS
        self.rts_check = QCheckBox('RTS')
        self.rts_check.stateChanged.connect(self._on_rts_changed)
        layout.addWidget(self.rts_check)
        
        layout.addWidget(QLabel('  │  输入状态:'))
        
        # 输入信号指示
        self.cts_label = QLabel('CTS: --')
        self.cts_label.setStyleSheet('color: gray;')
        layout.addWidget(self.cts_label)
        
        self.dsr_label = QLabel('DSR: --')
        self.dsr_label.setStyleSheet('color: gray;')
        layout.addWidget(self.dsr_label)
        
        self.cd_label = QLabel('CD: --')
        self.cd_label.setStyleSheet('color: gray;')
        layout.addWidget(self.cd_label)
        
        layout.addStretch()
        group.setLayout(layout)
        return group
    
    def create_receive_tabs(self) -> QTabWidget:
        """创建接收区 (文本 + 波形图 + Modbus解析)"""
        tabs = QTabWidget()
        
        # Tab 1: 文本接收
        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        
        # 控制栏
        control_layout = QHBoxLayout()
        
        self.hex_receive_check = QCheckBox('HEX 显示')
        control_layout.addWidget(self.hex_receive_check)
        
        self.timestamp_check = QCheckBox('显示时间戳')
        self.timestamp_check.setChecked(True)
        control_layout.addWidget(self.timestamp_check)
        
        self.auto_scroll_check = QCheckBox('自动滚动')
        self.auto_scroll_check.setChecked(True)
        control_layout.addWidget(self.auto_scroll_check)
        
        control_layout.addStretch()
        
        clear_btn = QPushButton('清空')
        clear_btn.clicked.connect(self.clear_receive)
        control_layout.addWidget(clear_btn)
        
        text_layout.addLayout(control_layout)
        
        # 接收文本框
        self.receive_text = QTextEdit()
        self.receive_text.setReadOnly(True)
        self.receive_text.setFont(QFont('Consolas', 10))
        text_layout.addWidget(self.receive_text)
        
        tabs.addTab(text_widget, '📝 文本')
        
        # Tab 2: 增强波形图 (多通道 + XY)
        self.chart = EnhancedChart(max_points=self.app_config.chart_max_points, max_channels=4)
        tabs.addTab(self.chart, '📈 波形')
        
        # Tab 3: Modbus 响应解析
        self.modbus_response_panel = ModbusResponsePanel()
        tabs.addTab(self.modbus_response_panel, '🔢 Modbus解析')
        
        # Tab 4: 协议插件解析
        protocol_widget = QWidget()
        protocol_layout = QVBoxLayout(protocol_widget)
        
        proto_ctrl = QHBoxLayout()
        proto_ctrl.addWidget(QLabel('选择协议:'))
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(['自动检测'] + self.protocol_registry.list_protocols())
        self.protocol_combo.currentTextChanged.connect(self._on_protocol_changed)
        proto_ctrl.addWidget(self.protocol_combo)
        
        proto_ctrl.addStretch()
        
        proto_clear_btn = QPushButton('清空')
        proto_clear_btn.clicked.connect(self._clear_protocol_table)
        proto_ctrl.addWidget(proto_clear_btn)
        
        protocol_layout.addLayout(proto_ctrl)
        
        # 协议解析结果表格
        self.protocol_table = QTableWidget()
        self.protocol_table.setColumnCount(5)
        self.protocol_table.setHorizontalHeaderLabels(['时间', '协议', '字段', '值', '原始数据'])
        self.protocol_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        protocol_layout.addWidget(self.protocol_table)
        
        tabs.addTab(protocol_widget, '🔌 协议解析')
        
        return tabs
    
    def create_send_group(self) -> QGroupBox:
        """创建发送区"""
        group = QGroupBox('数据发送')
        layout = QVBoxLayout()
        
        # 控制栏
        control_layout = QHBoxLayout()
        
        self.hex_send_check = QCheckBox('HEX 发送')
        control_layout.addWidget(self.hex_send_check)
        
        self.newline_check = QCheckBox('发送新行')
        self.newline_check.setChecked(True)
        control_layout.addWidget(self.newline_check)
        
        control_layout.addStretch()
        
        # 自动发送
        self.auto_send_check = QCheckBox('自动发送')
        self.auto_send_check.stateChanged.connect(self._on_auto_send_toggled)
        control_layout.addWidget(self.auto_send_check)
        
        control_layout.addWidget(QLabel('间隔(ms):'))
        self.auto_send_interval = QLineEdit('1000')
        self.auto_send_interval.setMaximumWidth(60)
        control_layout.addWidget(self.auto_send_interval)
        
        layout.addLayout(control_layout)
        
        # 发送历史
        layout.addWidget(QLabel('发送历史:'))
        self.history_combo = QComboBox()
        self.history_combo.setEditable(False)
        self.history_combo.activated.connect(self.load_history)
        layout.addWidget(self.history_combo)
        
        # 发送输入框
        self.send_input = QLineEdit()
        self.send_input.setFont(QFont('Consolas', 10))
        self.send_input.setPlaceholderText('输入要发送的数据...')
        self.send_input.returnPressed.connect(self.send_data)
        layout.addWidget(self.send_input)
        
        # 发送按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        send_btn = QPushButton('发送')
        send_btn.setMinimumWidth(80)
        send_btn.clicked.connect(self.send_data)
        btn_layout.addWidget(send_btn)
        
        layout.addLayout(btn_layout)
        
        group.setLayout(layout)
        return group
    
    def create_presets_group(self) -> QGroupBox:
        """创建预设指令面板"""
        group = QGroupBox('预设指令')
        layout = QVBoxLayout()
        
        # 预设表格
        self.presets_table = QTableWidget()
        self.presets_table.setColumnCount(3)
        self.presets_table.setHorizontalHeaderLabels(['名称', '数据', 'HEX'])
        self.presets_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.presets_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.presets_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.presets_table.setMaximumHeight(150)
        self.presets_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.presets_table.doubleClicked.connect(self._send_preset)
        layout.addWidget(self.presets_table)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton('➕ 添加')
        add_btn.clicked.connect(self._add_preset)
        btn_layout.addWidget(add_btn)
        
        edit_btn = QPushButton('✏️ 编辑')
        edit_btn.clicked.connect(self._edit_preset)
        btn_layout.addWidget(edit_btn)
        
        del_btn = QPushButton('🗑️ 删除')
        del_btn.clicked.connect(self._delete_preset)
        btn_layout.addWidget(del_btn)
        
        send_preset_btn = QPushButton('📤 发送选中')
        send_preset_btn.clicked.connect(self._send_selected_preset)
        btn_layout.addWidget(send_preset_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        # 加载预设
        self._load_presets_to_table()
        
        group.setLayout(layout)
        return group
    
    def create_status_bar(self):
        """创建状态栏"""
        self.status_bar = self.statusBar()
        
        self.connection_label = QLabel('未连接')
        self.connection_label.setStyleSheet('color: red;')
        self.status_bar.addWidget(self.connection_label)
        
        self.status_bar.addPermanentWidget(QLabel('|'))
        
        self.rx_label = QLabel('RX: 0 bytes')
        self.status_bar.addPermanentWidget(self.rx_label)
        
        self.status_bar.addPermanentWidget(QLabel('|'))
        
        self.tx_label = QLabel('TX: 0 bytes')
        self.status_bar.addPermanentWidget(self.tx_label)
        
        self.status_bar.addPermanentWidget(QLabel('|'))
        
        self.log_label = QLabel('日志: 关闭')
        self.status_bar.addPermanentWidget(self.log_label)
    
    def setup_connections(self):
        """设置信号槽连接"""
        self.serial_manager.on_data_received = self.on_serial_data_received
        self.serial_manager.on_error = self.on_serial_error
        self.serial_manager.on_connection_changed = self.on_connection_changed
        self.serial_manager.on_signal_changed = self._on_signals_changed
        
        # Modbus 面板信号
        modbus_panel = self.findChild(ModbusPanel)
        if modbus_panel:
            modbus_panel.send_frame.connect(self._send_modbus_frame)
        
        # 脚本引擎日志
        self.script_panel.script_log.connect(self.script_panel.append_log)
        
        # 多串口管理器回调
        self.multi_manager.on_data_received = self._on_multi_data_received
    
    # ─── 串口操作 ────────────────────────────────────────────
    
    def scan_ports(self):
        """扫描可用串口"""
        self.port_combo.clear()
        ports = SerialManager.scan_ports()
        for port in ports:
            display_text = f"{port['device']} - {port['description']}"
            self.port_combo.addItem(display_text, port['device'])
    
    def toggle_connection(self):
        """切换连接状态"""
        if self.serial_manager.is_connected:
            self.serial_manager.disconnect()
        else:
            self.connect_serial()
    
    def connect_serial(self):
        """连接串口"""
        if self.port_combo.count() == 0:
            QMessageBox.warning(self, '警告', '没有可用的串口')
            return
        
        port = self.port_combo.currentData()
        baudrate = int(self.baudrate_combo.currentText())
        databits = int(self.databits_combo.currentText())
        stopbits = float(self.stopbits_combo.currentText())
        parity_map = {'None': 'N', 'Even': 'E', 'Odd': 'O', 'Mark': 'M', 'Space': 'S'}
        parity = parity_map[self.parity_combo.currentText()]
        
        config = SerialConfig(
            port=port,
            baudrate=baudrate,
            data_bits=databits,
            stop_bits=stopbits,
            parity=parity
        )
        
        if not self.serial_manager.connect(config):
            QMessageBox.critical(self, '错误', '串口连接失败')
    
    @pyqtSlot(bytes)
    def on_serial_data_received(self, data: bytes):
        """串口数据接收回调"""
        self.received_bytes += len(data)
        self.data_received.emit(data)
        
        # 文本显示
        self.display_received_data(data)
        
        # 波形图显示 (多通道)
        self.chart.append_data(data, channel=0)
        
        # Modbus 解析
        self.modbus_response_panel.feed_data(data)
        
        # 协议插件解析
        self._parse_protocol_data(data)
        
        # 日志记录
        self.log_writer.write_rx(data, self.hex_receive_check.isChecked())
    
    def display_received_data(self, data: bytes):
        """显示接收的数据"""
        if self.hex_receive_check.isChecked():
            text = ' '.join(f'{b:02X}' for b in data)
        else:
            text = data.decode('utf-8', errors='replace')
        
        if self.timestamp_check.isChecked():
            timestamp = datetime.now().strftime('[%H:%M:%S.%f]')[:-3]
            text = f'{timestamp} {text}'
        
        self.receive_text.append(text)
        
        if self.auto_scroll_check.isChecked():
            self.receive_text.moveCursor(QTextCursor.MoveOperation.End)
    
    def send_data(self):
        """发送数据"""
        if not self.serial_manager.is_connected:
            QMessageBox.warning(self, '警告', '串口未连接')
            return
        
        text = self.send_input.text()
        if not text:
            return
        
        # 添加到历史
        if text not in self.send_history:
            self.send_history.insert(0, text)
            self.history_combo.insertItem(0, text)
            if len(self.send_history) > 20:
                self.send_history.pop()
                self.history_combo.removeItem(20)
        
        # 发送
        if self.hex_send_check.isChecked():
            fmt = DataFormat.HEX
        else:
            fmt = DataFormat.ASCII
        
        if self.newline_check.isChecked() and fmt == DataFormat.ASCII:
            text += '\n'
        
        if self.serial_manager.send_text(text, fmt):
            self.sent_bytes += len(text.encode('utf-8'))
            self.send_input.clear()
            
            # 日志记录
            self.log_writer.write_tx(text.encode('utf-8'), self.hex_send_check.isChecked())
    
    def _send_modbus_frame(self, frame: bytes):
        """发送 Modbus 帧"""
        if not self.serial_manager.is_connected:
            QMessageBox.warning(self, '警告', '请先连接串口')
            return
        if self.serial_manager.send(frame):
            self.sent_bytes += len(frame)
            hex_str = ' '.join(f'{b:02X}' for b in frame)
            timestamp = datetime.now().strftime('[%H:%M:%S.%f]')[:-3]
            self.receive_text.append(f'{timestamp} [TX Modbus] {hex_str}')
            
            # 日志记录
            self.log_writer.write_tx(frame, hex_mode=True)
    
    def load_history(self, index):
        """加载历史记录"""
        if index >= 0:
            self.send_input.setText(self.history_combo.itemText(index))
    
    # ─── 自动发送 ────────────────────────────────────────────
    
    def _on_auto_send_toggled(self, state):
        """自动发送开关"""
        if state == Qt.CheckState.Checked.value:
            try:
                interval = int(self.auto_send_interval.text())
                if interval < 10:
                    interval = 10
            except ValueError:
                interval = 1000
            self.auto_send_timer.start(interval)
        else:
            self.auto_send_timer.stop()
    
    def _auto_send_tick(self):
        """自动发送定时器回调"""
        if self.serial_manager.is_connected and self.send_input.text():
            self.send_data()
    
    # ─── 信号线控制 ──────────────────────────────────────────
    
    def _on_dtr_changed(self, state):
        """DTR 状态变化"""
        if self.serial_manager.is_connected:
            self.serial_manager.set_dtr(state == Qt.CheckState.Checked.value)
    
    def _on_rts_changed(self, state):
        """RTS 状态变化"""
        if self.serial_manager.is_connected:
            self.serial_manager.set_rts(state == Qt.CheckState.Checked.value)
    
    def _on_signals_changed(self, signals: dict):
        """信号线状态变化回调"""
        def _update(label, name, value):
            if value:
                label.setText(f'{name}: ●')
                label.setStyleSheet('color: #4CAF50;')
            else:
                label.setText(f'{name}: ○')
                label.setStyleSheet('color: gray;')
        
        _update(self.cts_label, 'CTS', signals.get('cts', False))
        _update(self.dsr_label, 'DSR', signals.get('dsr', False))
        _update(self.cd_label, 'CD', signals.get('cd', False))
    
    # ─── 预设指令管理 ────────────────────────────────────────
    
    def _load_presets_to_table(self):
        """加载预设到表格"""
        presets = self.app_config.presets
        self.presets_table.setRowCount(len(presets))
        for i, preset in enumerate(presets):
            self.presets_table.setItem(i, 0, QTableWidgetItem(preset.get('name', '')))
            self.presets_table.setItem(i, 1, QTableWidgetItem(preset.get('data', '')))
            self.presets_table.setItem(i, 2, QTableWidgetItem('✓' if preset.get('is_hex') else ''))
    
    def _save_presets_from_table(self):
        """从表格保存预设"""
        presets = []
        for i in range(self.presets_table.rowCount()):
            name_item = self.presets_table.item(i, 0)
            data_item = self.presets_table.item(i, 1)
            hex_item = self.presets_table.item(i, 2)
            if name_item and data_item:
                presets.append({
                    'name': name_item.text(),
                    'data': data_item.text(),
                    'is_hex': hex_item.text() == '✓' if hex_item else False,
                })
        self.app_config.presets = presets
        self.config_mgr.save()
    
    def _add_preset(self):
        """添加预设"""
        dialog = PresetEditDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, data, is_hex = dialog.get_values()
            if name and data:
                row = self.presets_table.rowCount()
                self.presets_table.insertRow(row)
                self.presets_table.setItem(row, 0, QTableWidgetItem(name))
                self.presets_table.setItem(row, 1, QTableWidgetItem(data))
                self.presets_table.setItem(row, 2, QTableWidgetItem('✓' if is_hex else ''))
                self._save_presets_from_table()
    
    def _edit_preset(self):
        """编辑预设"""
        row = self.presets_table.currentRow()
        if row < 0:
            return
        name = self.presets_table.item(row, 0).text()
        data = self.presets_table.item(row, 1).text()
        is_hex = self.presets_table.item(row, 2).text() == '✓'
        
        dialog = PresetEditDialog(self, name, data, is_hex)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name, new_data, new_is_hex = dialog.get_values()
            self.presets_table.setItem(row, 0, QTableWidgetItem(new_name))
            self.presets_table.setItem(row, 1, QTableWidgetItem(new_data))
            self.presets_table.setItem(row, 2, QTableWidgetItem('✓' if new_is_hex else ''))
            self._save_presets_from_table()
    
    def _delete_preset(self):
        """删除预设"""
        row = self.presets_table.currentRow()
        if row >= 0:
            self.presets_table.removeRow(row)
            self._save_presets_from_table()
    
    def _send_preset(self, index):
        """双击发送预设"""
        self._send_selected_preset()
    
    def _send_selected_preset(self):
        """发送选中的预设指令"""
        row = self.presets_table.currentRow()
        if row < 0:
            return
        if not self.serial_manager.is_connected:
            QMessageBox.warning(self, '警告', '串口未连接')
            return
        
        data_text = self.presets_table.item(row, 1).text()
        is_hex = self.presets_table.item(row, 2).text() == '✓'
        
        fmt = DataFormat.HEX if is_hex else DataFormat.ASCII
        if self.serial_manager.send_text(data_text, fmt):
            self.sent_bytes += len(data_text.encode('utf-8'))
    
    # ─── 日志设置 ────────────────────────────────────────────
    
    def _show_log_settings(self):
        """显示日志设置对话框"""
        dialog = LogSettingsDialog(self, self.log_writer.config)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_config = dialog.get_config()
            self.log_writer.close()
            self.log_writer = RotatingLogWriter(new_config)
            
            if new_config.enabled:
                self.log_label.setText(f'日志: {new_config.log_dir}')
                self.log_label.setStyleSheet('color: green;')
            else:
                self.log_label.setText('日志: 关闭')
                self.log_label.setStyleSheet('color: gray;')
    
    # ─── 多串口回调 ──────────────────────────────────────────
    
    def _on_multi_data_received(self, slot_name: str, data: bytes):
        """多串口数据接收回调"""
        self.compare_panel.append_data(slot_name, data, self.hex_receive_check.isChecked())
    
    # ─── 协议插件 ────────────────────────────────────────────
    
    def _on_protocol_changed(self, protocol_name: str):
        """协议选择变化"""
        if protocol_name == '自动检测':
            self.stream_parser.set_protocol(None)
        else:
            self.stream_parser.set_protocol(protocol_name)
    
    def _parse_protocol_data(self, data: bytes):
        """解析协议数据"""
        frames = self.stream_parser.feed(data)
        for frame in frames:
            self._add_protocol_frame(frame)
    
    def _add_protocol_frame(self, frame):
        """添加协议帧到表格"""
        row = self.protocol_table.rowCount()
        self.protocol_table.insertRow(row)
        
        self.protocol_table.setItem(row, 0, QTableWidgetItem(frame.timestamp))
        self.protocol_table.setItem(row, 1, QTableWidgetItem(frame.protocol))
        
        # 显示第一个字段
        if frame.fields:
            first_key = list(frame.fields.keys())[0]
            self.protocol_table.setItem(row, 2, QTableWidgetItem(first_key))
            self.protocol_table.setItem(row, 3, QTableWidgetItem(str(frame.fields[first_key])))
        else:
            self.protocol_table.setItem(row, 2, QTableWidgetItem('-'))
            self.protocol_table.setItem(row, 3, QTableWidgetItem('-'))
        
        # 原始数据
        raw_hex = ' '.join(f'{b:02X}' for b in frame.raw_data[:20])
        if len(frame.raw_data) > 20:
            raw_hex += '...'
        self.protocol_table.setItem(row, 4, QTableWidgetItem(raw_hex))
    
    def _clear_protocol_table(self):
        """清空协议表格"""
        self.protocol_table.setRowCount(0)
        self.stream_parser.clear()
    
    # ─── 多串口管理器对话框 ──────────────────────────────────
    
    def _show_multi_port_manager(self):
        """显示多串口管理器对话框"""
        dialog = MultiPortManagerDialog(self, self.multi_manager)
        dialog.exec()
    
    # ─── 连接状态 ────────────────────────────────────────────
    
    @pyqtSlot(str)
    def on_serial_error(self, error_msg: str):
        """串口错误回调"""
        QMessageBox.critical(self, '串口错误', error_msg)
    
    @pyqtSlot(bool)
    def on_connection_changed(self, connected: bool):
        """连接状态变化回调"""
        if connected:
            self.connect_btn.setText('断开')
            self.connect_btn.setChecked(True)
            self.connection_label.setText(f'已连接: {self.serial_manager.config.port}')
            self.connection_label.setStyleSheet('color: green;')
            self.set_controls_enabled(False)
        else:
            self.connect_btn.setText('连接')
            self.connect_btn.setChecked(False)
            self.connection_label.setText('未连接')
            self.connection_label.setStyleSheet('color: red;')
            self.set_controls_enabled(True)
            # 停止自动发送
            self.auto_send_check.setChecked(False)
            self.auto_send_timer.stop()
    
    def set_controls_enabled(self, enabled: bool):
        """启用/禁用串口配置控件"""
        self.port_combo.setEnabled(enabled)
        self.baudrate_combo.setEnabled(enabled)
        self.databits_combo.setEnabled(enabled)
        self.stopbits_combo.setEnabled(enabled)
        self.parity_combo.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
    
    # ─── 状态栏 ──────────────────────────────────────────────
    
    def update_status(self):
        """更新状态栏"""
        self.rx_label.setText(f'RX: {self.received_bytes} bytes')
        self.tx_label.setText(f'TX: {self.sent_bytes} bytes')
    
    # ─── 配置管理 ────────────────────────────────────────────
    
    def load_config_to_ui(self):
        """从配置加载到 UI"""
        cfg = self.app_config
        self.baudrate_combo.setCurrentText(str(cfg.baudrate))
        self.hex_receive_check.setChecked(cfg.hex_receive)
        self.hex_send_check.setChecked(cfg.hex_send)
        self.timestamp_check.setChecked(cfg.show_timestamp)
        self.auto_scroll_check.setChecked(cfg.auto_scroll)
        self.newline_check.setChecked(cfg.send_newline)
        self.auto_send_interval.setText(str(cfg.auto_send_interval))
    
    def save_config(self):
        """保存当前配置"""
        cfg = self.app_config
        cfg.baudrate = int(self.baudrate_combo.currentText())
        cfg.data_bits = int(self.databits_combo.currentText())
        cfg.stop_bits = float(self.stopbits_combo.currentText())
        cfg.parity = self.parity_combo.currentText()
        cfg.hex_receive = self.hex_receive_check.isChecked()
        cfg.hex_send = self.hex_send_check.isChecked()
        cfg.show_timestamp = self.timestamp_check.isChecked()
        cfg.auto_scroll = self.auto_scroll_check.isChecked()
        cfg.send_newline = self.newline_check.isChecked()
        try:
            cfg.auto_send_interval = int(self.auto_send_interval.text())
        except ValueError:
            pass
        
        # 窗口位置
        geo = self.geometry()
        cfg.window_x = geo.x()
        cfg.window_y = geo.y()
        cfg.window_w = geo.width()
        cfg.window_h = geo.height()
        
        self.config_mgr.save(cfg)
        self.status_bar.showMessage('配置已保存', 2000)
    
    # ─── 其他 ────────────────────────────────────────────────
    
    def clear_receive(self):
        """清空接收区"""
        self.receive_text.clear()
        self.chart.clear()
        self.modbus_response_panel.clear()
        self.received_bytes = 0
    
    def clear_display(self):
        """清空显示"""
        self.clear_receive()
        self.sent_bytes = 0
    
    def export_log(self):
        """导出日志"""
        from PyQt6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, '导出日志', '', 'Text Files (*.txt);;CSV Files (*.csv);;All Files (*)'
        )
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.receive_text.toPlainText())
            QMessageBox.information(self, '成功', f'日志已导出到:\n{filename}')
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, '关于',
            '串口调试助手 v4.0\n\n'
            '功能:\n'
            '• 串口通信 (HEX/ASCII 切换)\n'
            '• 增强波形图 (多通道 + XY 李萨如)\n'
            '• Modbus RTU 响应自动解析\n'
            '• 协议插件框架 (CAN/I2C/UART-Packet)\n'
            '• 预设指令管理\n'
            '• DTR/RTS 信号线控制\n'
            '• Modbus RTU 快捷操作\n'
            '• 自动发送 (定时)\n'
            '• 日志轮转 (按大小/时间/天)\n'
            '• Python 脚本引擎 (断点/wait_response)\n'
            '• 多串口对比 (最多4路)\n'
            '• 多串口管理器 (独立配置)\n'
            '• 配置保存/加载\n\n'
            '基于 PyQt6 + pyqtgraph 开发'
        )
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 断开连接
        if self.serial_manager.is_connected:
            self.serial_manager.disconnect()
        self.multi_manager.disconnect_all()
        
        # 停止定时器
        self.auto_send_timer.stop()
        
        # 关闭日志
        self.log_writer.close()
        
        # 保存配置
        self.save_config()
        event.accept()
    
    def apply_styles(self):
        """应用样式"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:checked {
                background-color: #f44336;
            }
            QPushButton:checked:hover {
                background-color: #da190b;
            }
            QTextEdit, QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #cccccc;
            }
            QLineEdit {
                border: 1px solid #cccccc;
                padding: 5px;
                border-radius: 3px;
            }
            QComboBox {
                border: 1px solid #cccccc;
                padding: 3px;
                border-radius: 3px;
                min-width: 60px;
            }
            QTabWidget::pane {
                border: 1px solid #cccccc;
            }
            QTabBar::tab {
                padding: 8px 20px;
                margin: 2px;
            }
            QTabBar::tab:selected {
                background-color: #4CAF50;
                color: white;
                border-radius: 3px;
            }
            QTableWidget {
                border: 1px solid #cccccc;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item:selected {
                background-color: #C8E6C9;
                color: black;
            }
            QStatusBar {
                background-color: #e8e8e8;
            }
        """)


def main():
    """应用入口"""
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName('Serial Toolbox')
    
    window = SerialToolboxMainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
