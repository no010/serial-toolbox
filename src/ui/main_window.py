"""
主窗口 UI
基于 PyQt6 的串口调试助手界面
"""

import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QGroupBox, QLabel, QComboBox, QPushButton, QTextEdit,
    QLineEdit, QCheckBox, QStatusBar, QMenuBar, QMenu,
    QSplitter, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QAction, QFont, QTextCursor

from src.core.serial_manager import SerialManager, SerialConfig, DataFormat


class SerialToolboxMainWindow(QMainWindow):
    """串口调试助手主窗口"""
    
    # 信号
    data_received = pyqtSignal(bytes)
    data_sent = pyqtSignal(bytes)
    
    def __init__(self):
        super().__init__()
        self.serial_manager = SerialManager()
        self.send_history = []
        self.received_bytes = 0
        self.sent_bytes = 0
        
        self.init_ui()
        self.setup_connections()
        self.scan_ports()
        
        # 状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)
    
    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle('串口调试助手 - Serial Toolbox')
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部工具栏 - 串口配置
        main_layout.addWidget(self.create_serial_config_group())
        
        # 主内容区 - 使用分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 左侧：接收区
        splitter.addWidget(self.create_receive_group())
        
        # 右侧：发送区
        splitter.addWidget(self.create_send_group())
        
        splitter.setSizes([600, 400])
        main_layout.addWidget(splitter, 1)
        
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
        self.refresh_btn = QPushButton('刷新')
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
    
    def create_receive_group(self) -> QGroupBox:
        """创建接收区"""
        group = QGroupBox('数据接收')
        layout = QVBoxLayout()
        
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
        
        layout.addLayout(control_layout)
        
        # 接收文本框
        self.receive_text = QTextEdit()
        self.receive_text.setReadOnly(True)
        self.receive_text.setFont(QFont('Consolas', 10))
        layout.addWidget(self.receive_text)
        
        group.setLayout(layout)
        return group
    
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
        
        layout.addStretch()
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
    
    def setup_connections(self):
        """设置信号槽连接"""
        # SerialManager 回调
        self.serial_manager.on_data_received = self.on_serial_data_received
        self.serial_manager.on_error = self.on_serial_error
        self.serial_manager.on_connection_changed = self.on_connection_changed
    
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
        
        # 显示数据
        self.display_received_data(data)
    
    def display_received_data(self, data: bytes):
        """显示接收的数据"""
        if self.hex_receive_check.isChecked():
            text = ' '.join(f'{b:02X}' for b in data)
        else:
            text = data.decode('utf-8', errors='replace')
        
        if self.timestamp_check.isChecked():
            from datetime import datetime
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
            format = DataFormat.HEX
        else:
            format = DataFormat.ASCII
        
        if self.newline_check.isChecked() and format == DataFormat.ASCII:
            text += '\n'
        
        if self.serial_manager.send_text(text, format):
            self.sent_bytes += len(text.encode('utf-8'))
            self.send_input.clear()
    
    def load_history(self, index):
        """加载历史记录"""
        if index >= 0:
            self.send_input.setText(self.history_combo.itemText(index))
    
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
    
    def set_controls_enabled(self, enabled: bool):
        """启用/禁用串口配置控件"""
        self.port_combo.setEnabled(enabled)
        self.baudrate_combo.setEnabled(enabled)
        self.databits_combo.setEnabled(enabled)
        self.stopbits_combo.setEnabled(enabled)
        self.parity_combo.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
    
    def update_status(self):
        """更新状态栏"""
        self.rx_label.setText(f'RX: {self.received_bytes} bytes')
        self.tx_label.setText(f'TX: {self.sent_bytes} bytes')
    
    def clear_receive(self):
        """清空接收区"""
        self.receive_text.clear()
        self.received_bytes = 0
    
    def clear_display(self):
        """清空显示"""
        self.clear_receive()
        self.sent_bytes = 0
    
    def export_log(self):
        """导出日志"""
        from PyQt6.QtWidgets import QFileDialog
        filename, _ = QFileDialog.getSaveFileName(
            self, '导出日志', '', 'Text Files (*.txt);;All Files (*)'
        )
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.receive_text.toPlainText())
            QMessageBox.information(self, '成功', '日志已导出')
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, '关于',
            '串口调试助手 v1.0\n\n'
            '功能:\n'
            '- 串口通信\n'
            '- HEX/ASCII 切换\n'
            '- 时间戳显示\n'
            '- 发送历史\n'
            '- 数据导出\n\n'
            '基于 PyQt6 开发'
        )
    
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
            QTextEdit {
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
            }
        """)
    
    def closeEvent(self, event):
        """关闭窗口事件"""
        if self.serial_manager.is_connected:
            self.serial_manager.disconnect()
        event.accept()


def main():
    """主函数"""
    app = QApplication(sys.argv)
    window = SerialToolboxMainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
