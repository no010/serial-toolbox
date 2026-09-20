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
from src.ui.i18n import I18nManager


class MultiPortConfigDialog(QDialog):
    """多串口配置对话框"""

    def __init__(self, parent=None, slot_name: str = "Port A", i18n: I18nManager | None = None):
        super().__init__(parent)
        self.i18n = i18n or I18nManager()
        self.slot_name = slot_name
        self.config: SerialConfig | None = None
        self.init_ui()
        self.retranslate_ui()
        self.scan_ports()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setWindowTitle(tr("dialog_port_config", self.slot_name))
        self.title_label.setText(tr("title_port_config", self.slot_name))
        self.config_group.setTitle(tr("dialog_port_config_group"))
        self.port_label.setText(tr("label_port"))
        self.refresh_btn.setText(tr("btn_refresh"))
        self.baudrate_label.setText(tr("label_baudrate"))
        self.databits_label.setText(tr("label_databits"))
        self.stopbits_label.setText(tr("label_stopbits"))
        self.parity_label.setText(tr("label_parity_col"))
        self.flow_label.setText(tr("label_flow_control"))

    def init_ui(self):
        """初始化 UI"""
        self.setFixedSize(450, 350)

        layout = QVBoxLayout(self)

        # 标题
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # 串口配置组
        self.config_group = QGroupBox()
        config_layout = QFormLayout()

        # 串口选择
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(200)
        self.port_label = QLabel()
        config_layout.addRow(self.port_label, self.port_combo)

        # 刷新按钮
        refresh_layout = QHBoxLayout()
        self.refresh_btn = QPushButton()
        self.refresh_btn.clicked.connect(self.scan_ports)
        refresh_layout.addWidget(self.refresh_btn)
        refresh_layout.addStretch()
        config_layout.addRow("", refresh_layout)

        # 波特率
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(
            ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
        )
        self.baudrate_combo.setCurrentText("115200")
        self.baudrate_label = QLabel()
        config_layout.addRow(self.baudrate_label, self.baudrate_combo)

        # 数据位
        self.databits_combo = QComboBox()
        self.databits_combo.addItems(["8", "7", "6", "5"])
        self.databits_label = QLabel()
        config_layout.addRow(self.databits_label, self.databits_combo)

        # 停止位
        self.stopbits_combo = QComboBox()
        self.stopbits_combo.addItems(["1", "1.5", "2"])
        self.stopbits_label = QLabel()
        config_layout.addRow(self.stopbits_label, self.stopbits_combo)

        # 校验位
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd", "Mark", "Space"])
        self.parity_label = QLabel()
        config_layout.addRow(self.parity_label, self.parity_combo)

        # 流控
        self.flow_combo = QComboBox()
        self.flow_combo.addItems(["None", "RTS/CTS", "XON/XOFF"])
        self.flow_label = QLabel()
        config_layout.addRow(self.flow_label, self.flow_combo)

        self.config_group.setLayout(config_layout)
        layout.addWidget(self.config_group)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
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
            self.port_combo.addItem(display_text, port["device"])

    def get_config(self) -> SerialConfig | None:
        """获取配置"""
        if self.port_combo.count() == 0:
            return None

        port = self.port_combo.currentData()
        baudrate = int(self.baudrate_combo.currentText())
        databits = int(self.databits_combo.currentText())
        stopbits = float(self.stopbits_combo.currentText())

        parity_map = {"None": "N", "Even": "E", "Odd": "O", "Mark": "M", "Space": "S"}
        parity = parity_map[self.parity_combo.currentText()]

        flow_map = {"None": "None", "RTS/CTS": "RTS/CTS", "XON/XOFF": "XON/XOFF"}
        flow_control = flow_map[self.flow_combo.currentText()]

        self.config = SerialConfig(
            port=port,
            baudrate=baudrate,
            data_bits=databits,
            stop_bits=stopbits,
            parity=parity,
            flow_control=flow_control,
        )

        return self.config


class MultiPortManagerDialog(QDialog):
    """多串口管理器对话框 - 同时配置多个串口"""

    def __init__(self, parent=None, multi_manager=None, i18n: I18nManager | None = None):
        super().__init__(parent)
        self.i18n = i18n or I18nManager()
        self.multi_manager = multi_manager
        self.setFixedSize(700, 500)
        self.init_ui()
        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setWindowTitle(tr("dialog_multi_port"))
        self.title_label.setText(tr("title_multi_port"))
        self.status_label.setText(tr("status_dot_disconnected"))
        for button in self.config_buttons:
            button.setText(tr("btn_configure"))
        for button in self.connect_buttons:
            button.setText(tr("btn_connect"))
        for button in self.compare_buttons:
            button.setText(tr("btn_compare"))
        self.connect_all_btn.setText(tr("btn_connect_all"))
        self.disconnect_all_btn.setText(tr("btn_disconnect_all"))
        self.close_btn.setText(tr("btn_close"))

    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)

        # 标题
        self.title_label = QLabel()
        self.title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

        # 为每个端口创建配置卡片
        self.config_buttons: list[QPushButton] = []
        self.connect_buttons: list[QPushButton] = []
        self.compare_buttons: list[QPushButton] = []
        for slot_name in ["Port A", "Port B", "Port C", "Port D"]:
            card = self._create_port_card(slot_name)
            layout.addWidget(card)

        # 按钮
        btn_layout = QHBoxLayout()

        self.connect_all_btn = QPushButton()
        self.connect_all_btn.clicked.connect(self._connect_all)
        btn_layout.addWidget(self.connect_all_btn)

        self.disconnect_all_btn = QPushButton()
        self.disconnect_all_btn.clicked.connect(self._disconnect_all)
        btn_layout.addWidget(self.disconnect_all_btn)

        btn_layout.addStretch()

        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def _create_port_card(self, slot_name: str) -> QGroupBox:
        """创建端口配置卡片"""
        card = QGroupBox(slot_name)
        layout = QHBoxLayout(card)

        # 状态标签
        self.status_label = QLabel()
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        # 配置按钮
        config_btn = QPushButton()
        self.config_buttons.append(config_btn)
        config_btn.clicked.connect(lambda checked, name=slot_name: self._configure_port(name))
        layout.addWidget(config_btn)

        # 连接按钮
        connect_btn = QPushButton()
        self.connect_buttons.append(connect_btn)
        connect_btn.setCheckable(True)
        connect_btn.clicked.connect(
            lambda checked, name=slot_name: self._toggle_connection(name, checked)
        )
        layout.addWidget(connect_btn)

        # 激活对比
        compare_check = QPushButton()
        self.compare_buttons.append(compare_check)
        compare_check.setCheckable(True)
        compare_check.clicked.connect(
            lambda checked, name=slot_name: self._toggle_compare(name, checked)
        )
        layout.addWidget(compare_check)

        layout.addStretch()

        return card

    def _configure_port(self, slot_name: str):
        """配置端口"""
        dialog = MultiPortConfigDialog(self, slot_name, i18n=self.i18n)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_config()
            if config and self.multi_manager:
                slot = self.multi_manager.get_slot(slot_name)
                if slot:
                    slot.config = config
                    QMessageBox.information(
                        self,
                        self.i18n.tr("title_success"),
                        self.i18n.tr(
                            "msg_config_saved_detail", slot_name, config.port, config.baudrate
                        ),
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
                    self,
                    self.i18n.tr("title_warning"),
                    self.i18n.tr("msg_not_configured", slot_name),
                )
                return

            if self.multi_manager.connect(slot_name, slot.config):
                self._update_status(slot_name, True)
            else:
                QMessageBox.critical(
                    self,
                    self.i18n.tr("title_error"),
                    self.i18n.tr("msg_port_connected_fail", slot_name),
                )
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
            self, self.i18n.tr("title_success"), self.i18n.tr("msg_connect_all_done", connected)
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
