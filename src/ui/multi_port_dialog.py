"""
多串口配置对话框
为每个 Port 提供独立的配置界面
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.core.serial_manager import SerialConfig, SerialManager


class MultiPortConfigDialog(QDialog):
    """多串口配置对话框"""

    def __init__(self, parent=None, slot_name: str = "Port A"):
        super().__init__(parent)
        self.slot_name = slot_name
        self.config: SerialConfig = None
        self.init_ui()
        self.scan_ports()

    def init_ui(self):
        """初始化 UI"""
        self.setWindowTitle(f'配置 {self.slot_name}')
        self.setFixedSize(450, 350)

        layout = QVBoxLayout(self)

        # 标题
        title = QLabel(f'🔌 {self.slot_name} 串口配置')
        title.setFont(QFont('Arial', 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 串口配置组
        config_group = QGroupBox('串口参数')
        config_layout = QFormLayout()

        # 串口选择
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(200)
        config_layout.addRow('串口:', self.port_combo)

        # 刷新按钮
        refresh_layout = QHBoxLayout()
        self.refresh_btn = QPushButton('🔄 刷新')
        self.refresh_btn.clicked.connect(self.scan_ports)
        refresh_layout.addWidget(self.refresh_btn)
        refresh_layout.addStretch()
        config_layout.addRow('', refresh_layout)

        # 波特率
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems([
            '9600', '19200', '38400', '57600', '115200',
            '230400', '460800', '921600'
        ])
        self.baudrate_combo.setCurrentText('115200')
        config_layout.addRow('波特率:', self.baudrate_combo)

        # 数据位
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(['8', '7', '6', '5'])
        config_layout.addRow('数据位:', self.databits_combo)

        # 停止位
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(['1', '1.5', '2'])
        config_layout.addRow('停止位:', self.stopbits_combo)

        # 校验位
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(['None', 'Even', 'Odd', 'Mark', 'Space'])
        config_layout.addRow('校验位:', self.parity_combo)

        # 流控
        self.flow_combo = QComboBox()
        self.flow_combo.addItems(['None', 'RTS/CTS', 'XON/XOFF'])
        config_layout.addRow('流控:', self.flow_combo)

        config_group.setLayout(config_layout)
        layout.addWidget(config_group)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def scan_ports(self):
        """扫描可用串口"""
        self.port_combo.clear()
        ports = SerialManager.scan_ports()
        for port in ports:
            display_text = f"{port['device']} - {port['description']}"
            self.port_combo.addItem(display_text, port['device'])

    def get_config(self) -> SerialConfig:
        """获取配置"""
        if self.port_combo.count() == 0:
            return None

        port = self.port_combo.currentData()
        baudrate = int(self.baudrate_combo.currentText())
        databits = int(self.databits_combo.currentText())
        stopbits = float(self.stopbits_combo.currentText())

        parity_map = {
            'None': 'N', 'Even': 'E', 'Odd': 'O',
            'Mark': 'M', 'Space': 'S'
        }
        parity = parity_map[self.parity_combo.currentText()]

        flow_map = {
            'None': 'None',
            'RTS/CTS': 'RTS/CTS',
            'XON/XOFF': 'XON/XOFF'
        }
        flow_control = flow_map[self.flow_combo.currentText()]

        self.config = SerialConfig(
            port=port,
            baudrate=baudrate,
            data_bits=databits,
            stop_bits=stopbits,
            parity=parity,
            flow_control=flow_control
        )

        return self.config


class MultiPortManagerDialog(QDialog):
    """多串口管理器对话框 - 同时配置多个串口"""

    def __init__(self, parent=None, multi_manager=None):
        super().__init__(parent)
        self.multi_manager = multi_manager
        self.setWindowTitle('多串口管理器')
        self.setFixedSize(700, 500)
        self.init_ui()

    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # 标题
        title = QLabel('🔀 多串口管理器 (最多4路)')
        title.setFont(QFont('Arial', 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 为每个端口创建配置卡片
        for slot_name in ['Port A', 'Port B', 'Port C', 'Port D']:
            card = self._create_port_card(slot_name)
            layout.addWidget(card)

        # 按钮
        btn_layout = QHBoxLayout()

        connect_all_btn = QPushButton('🔗 全部连接')
        connect_all_btn.clicked.connect(self._connect_all)
        btn_layout.addWidget(connect_all_btn)

        disconnect_all_btn = QPushButton('⛓️‍💥 全部断开')
        disconnect_all_btn.clicked.connect(self._disconnect_all)
        btn_layout.addWidget(disconnect_all_btn)

        btn_layout.addStretch()

        close_btn = QPushButton('关闭')
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _create_port_card(self, slot_name: str) -> QGroupBox:
        """创建端口配置卡片"""
        card = QGroupBox(slot_name)
        layout = QHBoxLayout(card)

        # 状态标签
        self.status_label = QLabel('● 未连接')
        self.status_label.setStyleSheet('color: gray;')
        layout.addWidget(self.status_label)

        # 配置按钮
        config_btn = QPushButton('⚙️ 配置')
        config_btn.clicked.connect(lambda checked, name=slot_name: self._configure_port(name))
        layout.addWidget(config_btn)

        # 连接按钮
        connect_btn = QPushButton('连接')
        connect_btn.setCheckable(True)
        connect_btn.clicked.connect(lambda checked, name=slot_name: self._toggle_connection(name, checked))
        layout.addWidget(connect_btn)

        # 激活对比
        compare_check = QPushButton('📊 对比')
        compare_check.setCheckable(True)
        compare_check.clicked.connect(lambda checked, name=slot_name: self._toggle_compare(name, checked))
        layout.addWidget(compare_check)

        layout.addStretch()

        return card

    def _configure_port(self, slot_name: str):
        """配置端口"""
        dialog = MultiPortConfigDialog(self, slot_name)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            if config and self.multi_manager:
                slot = self.multi_manager.get_slot(slot_name)
                if slot:
                    slot.config = config
                    QMessageBox.information(
                        self, '成功',
                        f'{slot_name} 配置已保存\n'
                        f'端口: {config.port}\n'
                        f'波特率: {config.baudrate}'
                    )

    def _toggle_connection(self, slot_name: str, checked: bool):
        """切换连接状态"""
        if not self.multi_manager:
            return

        slot = self.multi_manager.get_slot(slot_name)
        if not slot:
            return

        if checked:
            # 连接
            if not slot.config:
                QMessageBox.warning(
                    self, '警告',
                    f'{slot_name} 未配置，请先点击"配置"按钮'
                )
                return

            if self.multi_manager.connect(slot_name, slot.config):
                self._update_status(slot_name, True)
            else:
                QMessageBox.critical(self, '错误', f'{slot_name} 连接失败')
        else:
            # 断开
            self.multi_manager.disconnect(slot_name)
            self._update_status(slot_name, False)

    def _toggle_compare(self, slot_name: str, checked: bool):
        """切换对比模式"""
        if self.multi_manager:
            self.multi_manager.set_active(slot_name, checked)

    def _connect_all(self):
        """连接所有已配置的端口"""
        if not self.multi_manager:
            return

        connected = 0
        for slot_name, slot in self.multi_manager.slots.items():
            if slot.config and not slot.manager.is_connected:
                if self.multi_manager.connect(slot_name, slot.config):
                    self._update_status(slot_name, True)
                    connected += 1

        QMessageBox.information(
            self, '完成',
            f'已连接 {connected} 个串口'
        )

    def _disconnect_all(self):
        """断开所有"""
        if self.multi_manager:
            self.multi_manager.disconnect_all()
            for slot_name in self.multi_manager.slots.keys():
                self._update_status(slot_name, False)

    def _update_status(self, slot_name: str, connected: bool):
        """更新状态显示"""
        # 这里简化处理，实际应该更新对应的卡片
        pass
