"""
I2C 调试面板（CH347 USB 桥）

总线操作全部在工作线程执行：CH347 的 ctypes 调用是阻塞的，放 UI 线程会假死。
结果经信号回到主线程更新控件，和脚本引擎的跨线程模式一致。
"""

from __future__ import annotations

import re
import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
)

from src.core.eeprom import EEPROMManager, EEPROMOperations
from src.core.i2c_bus import (
    I2C_SPEEDS_KHZ,
    Ch341I2CAdapter,
    Ch347I2CAdapter,
    I2CAdapter,
)
from src.ui.i18n import I18nManager


def parse_hex_bytes(text: str) -> bytes:
    """接受 '01 02 ff'、'0102FF'、'0x01,0x02' 这几种写法"""
    cleaned = re.sub(r"0[xX]", "", text)
    cleaned = re.sub(r"[\s,:;\-]", "", cleaned)
    if not cleaned:
        return b""
    try:
        return bytes.fromhex(cleaned)
    except ValueError as exc:
        raise ValueError("hex 数据格式不正确") from exc


def format_hex_dump(data: bytes, base_addr: int = 0) -> str:
    """16 字节一行的地址 + hex 转储"""
    lines = []
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"{base_addr + offset:04X}: {hex_part}")
    return "\n".join(lines)


class I2CPanel(QGroupBox):
    """I2C 调试：扫描、寄存器读写、EEPROM 整片读写校验"""

    operation_done = pyqtSignal(str, object)
    operation_failed = pyqtSignal(str, str)

    def __init__(
        self,
        i18n: I18nManager | None = None,
        adapter: I2CAdapter | None = None,
        eeprom_dir: str | None = None,
    ):
        self.i18n = i18n or I18nManager()
        super().__init__()
        self._adapter: I2CAdapter | None = adapter
        self._busy = False
        self._last_read_base = 0
        self._eeprom_manager = EEPROMManager(eeprom_dir)
        self.init_ui()
        self.retranslate_ui()
        self._sync_controls()

    # ─── UI 构建 ─────────────────────────────────────────

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # 设备栏
        device_row = QHBoxLayout()
        self.backend_label = QLabel()
        device_row.addWidget(self.backend_label)
        self.backend_combo = QComboBox()
        self.backend_combo.addItem("CH347", "ch347")
        self.backend_combo.addItem("CH341", "ch341")
        device_row.addWidget(self.backend_combo)
        self.device_label = QLabel()
        device_row.addWidget(self.device_label)
        self.device_spin = QSpinBox()
        self.device_spin.setRange(0, 7)
        device_row.addWidget(self.device_spin)
        self.speed_label = QLabel()
        device_row.addWidget(self.speed_label)
        self.speed_combo = QComboBox()
        for khz in I2C_SPEEDS_KHZ:
            self.speed_combo.addItem("", khz)
        self.speed_combo.setCurrentIndex(I2C_SPEEDS_KHZ.index(100))
        device_row.addWidget(self.speed_combo)
        self.open_btn = QPushButton()
        self.open_btn.clicked.connect(self._open_device)
        device_row.addWidget(self.open_btn)
        self.close_btn = QPushButton()
        self.close_btn.clicked.connect(self._close_device)
        device_row.addWidget(self.close_btn)
        self.status_label = QLabel()
        device_row.addWidget(self.status_label)
        device_row.addStretch()
        layout.addLayout(device_row)

        # 扫描 + 操作区
        body = QHBoxLayout()
        scan_box = QVBoxLayout()
        self.scan_btn = QPushButton()
        self.scan_btn.clicked.connect(self._scan_bus)
        scan_box.addWidget(self.scan_btn)
        self.address_list = QListWidget()
        self.address_list.setFont(QFont("Consolas", 9))
        self.address_list.setMaximumWidth(120)
        self.address_list.itemClicked.connect(self._pick_address)
        scan_box.addWidget(self.address_list, 1)
        body.addLayout(scan_box)

        operations = QVBoxLayout()

        # 寄存器读写
        self.register_group = QGroupBox()
        register_layout = QFormLayout(self.register_group)
        register_layout.setContentsMargins(6, 2, 6, 2)
        register_row = QHBoxLayout()
        self.device_addr_edit = QLineEdit("50")
        self.device_addr_edit.setMaximumWidth(70)
        register_row.addWidget(self.device_addr_edit)
        self.mem_addr_edit = QLineEdit("0000")
        self.mem_addr_edit.setMaximumWidth(90)
        register_row.addWidget(self.mem_addr_edit)
        self.length_spin = QSpinBox()
        self.length_spin.setRange(1, 4096)
        self.length_spin.setValue(16)
        register_row.addWidget(self.length_spin)
        self.read_btn = QPushButton()
        self.read_btn.clicked.connect(self._read_registers)
        register_row.addWidget(self.read_btn)
        register_row.addStretch()
        register_layout.addRow(register_row)
        write_row = QHBoxLayout()
        self.write_data_edit = QLineEdit()
        self.write_data_edit.setFont(QFont("Consolas", 9))
        write_row.addWidget(self.write_data_edit, 1)
        self.write_btn = QPushButton()
        self.write_btn.clicked.connect(self._write_registers)
        write_row.addWidget(self.write_btn)
        register_layout.addRow(write_row)
        operations.addWidget(self.register_group)

        # EEPROM
        self.eeprom_group = QGroupBox()
        eeprom_layout = QHBoxLayout(self.eeprom_group)
        eeprom_layout.setContentsMargins(6, 2, 6, 2)
        self.model_combo = QComboBox()
        for model in self._eeprom_manager.models():
            self.model_combo.addItem(model.name, model.id)
        eeprom_layout.addWidget(self.model_combo)
        self.read_full_btn = QPushButton()
        self.read_full_btn.clicked.connect(self._read_full)
        eeprom_layout.addWidget(self.read_full_btn)
        self.write_full_btn = QPushButton()
        self.write_full_btn.clicked.connect(self._write_full)
        eeprom_layout.addWidget(self.write_full_btn)
        self.verify_btn = QPushButton()
        self.verify_btn.clicked.connect(self._verify)
        eeprom_layout.addWidget(self.verify_btn)
        eeprom_layout.addStretch()
        operations.addWidget(self.eeprom_group)

        # 结果
        self.result_label = QLabel()
        operations.addWidget(self.result_label)
        self.result_text = QPlainTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFont(QFont("Consolas", 9))
        # 允许随窗口缩小到 40px：否则这页的最小高度会把主窗口顶出 1366×768 一类屏幕
        self.result_text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.result_text.setMinimumHeight(40)
        operations.addWidget(self.result_text, 1)
        body.addLayout(operations, 1)
        layout.addLayout(body, 1)

        self.operation_done.connect(self._on_done)
        self.operation_failed.connect(self._on_failed)

    def retranslate_ui(self):
        tr = self.i18n.tr
        self.setTitle(tr("group_i2c"))
        self.backend_label.setText(tr("i2c_backend"))
        self.device_label.setText(tr("i2c_device_index"))
        self.speed_label.setText(tr("i2c_speed"))
        for index, khz in enumerate(I2C_SPEEDS_KHZ):
            self.speed_combo.setItemText(index, f"{khz} kHz")
        self.open_btn.setText(tr("i2c_open"))
        self.close_btn.setText(tr("i2c_close"))
        self.scan_btn.setText(tr("i2c_scan"))
        self.register_group.setTitle(tr("i2c_register_group"))
        self.eeprom_group.setTitle(tr("i2c_eeprom_group"))
        self.device_addr_edit.setPlaceholderText(tr("i2c_device_addr"))
        self.mem_addr_edit.setPlaceholderText(tr("i2c_mem_addr"))
        self.write_data_edit.setPlaceholderText(tr("i2c_write_placeholder"))
        self.read_btn.setText(tr("i2c_read"))
        self.write_btn.setText(tr("i2c_write"))
        self.read_full_btn.setText(tr("i2c_read_full"))
        self.write_full_btn.setText(tr("i2c_write_full"))
        self.verify_btn.setText(tr("i2c_verify"))
        self.result_label.setText(tr("i2c_result"))
        self._show_status()

    # ─── 状态 ───────────────────────────────────────────

    def _selected_backend(self) -> str:
        return self.backend_combo.currentData() or "ch347"

    def _backend_reason(self) -> str:
        """所选后端的不可用原因；注入了适配器（测试/仿真）时视为可用"""
        if self._adapter is not None:
            return ""
        backend = self._selected_backend()
        adapter_cls = Ch347I2CAdapter if backend == "ch347" else Ch341I2CAdapter
        return adapter_cls.unavailable_reason()

    def _show_status(self, extra: str = ""):
        tr = self.i18n.tr
        reason = self._backend_reason()
        if self._busy:
            text = tr("i2c_status_busy")
        elif self._adapter is not None and self._adapter.is_connected():
            text = f"{tr('i2c_status_open')} | {self._adapter.get_info()}"
        elif reason:
            text = tr("i2c_unavailable") + reason
        else:
            text = tr("i2c_status_closed")
        if extra:
            text = f"{text} | {extra}"
        self.status_label.setText(text)

    def _sync_controls(self):
        connected = self._adapter is not None and self._adapter.is_connected()
        can_open = not self._busy and not self._backend_reason() and not connected
        self.open_btn.setEnabled(can_open)
        self.close_btn.setEnabled(connected and not self._busy)
        self.device_spin.setEnabled(not connected and not self._busy)
        self.backend_combo.setEnabled(not connected and not self._busy)
        # 档位只在连接前选：CH347 的 i2c_set 在传输中切换会打断时序
        self.speed_combo.setEnabled(not connected and not self._busy)
        page_write = (
            connected and self._adapter is not None and (self._adapter.supports_eeprom_page_write())
        )
        for widget in (self.scan_btn, self.read_btn, self.write_btn):
            widget.setEnabled(connected and not self._busy)
        for widget in (self.read_full_btn, self.write_full_btn, self.verify_btn):
            widget.setEnabled(page_write and not self._busy)

    def _set_busy(self, busy: bool):
        self._busy = busy
        self._sync_controls()
        self._show_status()

    # ─── 线程调度 ───────────────────────────────────────

    def _run(self, op: str, fn):
        if self._busy:
            return
        self._set_busy(True)

        def target():
            try:
                result = fn()
            except Exception as exc:  # 工作线程里任何异常都要回到 UI 线程报告
                self.operation_failed.emit(op, str(exc))
            else:
                self.operation_done.emit(op, result)

        threading.Thread(target=target, daemon=True).start()

    def _on_done(self, op: str, result):
        tr = self.i18n.tr
        self._set_busy(False)
        if op == "open":
            self._show_status(tr("i2c_msg_opened"))
        elif op == "scan":
            addresses = list(result)
            self.address_list.clear()
            for addr in addresses:
                self.address_list.addItem(f"0x{addr:02X}")
            self._show_status(tr("i2c_msg_scan_found", len(addresses)))
        elif op == "read":
            data = bytes(result)
            self.result_text.setPlainText(format_hex_dump(data, self._last_read_base))
            self._show_status(tr("i2c_msg_read", len(data)))
        elif op == "write":
            self._show_status(tr("i2c_msg_written"))
        elif op == "read_full":
            self.result_text.setPlainText(format_hex_dump(bytes(result)))
            self._show_status(tr("i2c_msg_read", len(result)))
        elif op == "write_full":
            self._show_status(tr("i2c_msg_write_full"))
        elif op == "verify":
            key = "i2c_msg_verified_ok" if result else "i2c_msg_verified_fail"
            self._show_status(tr(key))

    def _on_failed(self, op: str, message: str):
        self._set_busy(False)
        self._show_status(self.i18n.tr("i2c_msg_failed", message))

    # ─── 地址/数据解析 ──────────────────────────────────

    @staticmethod
    def _parse_hex(text: str) -> int:
        try:
            return int(text.strip().lower().removeprefix("0x"), 16)
        except ValueError as exc:
            raise ValueError(f"无效的十六进制地址: {text}") from exc

    def _addresses(self) -> tuple[int, int]:
        device = self._parse_hex(self.device_addr_edit.text())
        mem = self._parse_hex(self.mem_addr_edit.text())
        return device, mem

    def _selected_model(self):
        model_id = self.model_combo.currentData()
        model = self._eeprom_manager.get(model_id) if model_id else None
        if model is None:
            raise ValueError(f"未知的 EEPROM 型号: {model_id}")
        return model

    def _eeprom_context(self) -> tuple[EEPROMOperations, int] | None:
        if self._adapter is None:
            self._show_status(self.i18n.tr("i2c_msg_failed", "设备未打开"))
            return None
        try:
            device = self._parse_hex(self.device_addr_edit.text())
            model = self._selected_model()
        except ValueError as exc:
            self._show_status(self.i18n.tr("i2c_msg_failed", str(exc)))
            return None
        return EEPROMOperations(self._adapter, model), device

    def _read_full(self):
        context = self._eeprom_context()
        if context is None:
            return
        ops, device = context
        self._run("read_full", lambda: ops.read_full(device))

    def _write_full(self):
        payload = self._payload_or_status()
        if not payload:
            return
        context = self._eeprom_context()
        if context is None:
            return
        ops, device = context
        model = ops.config
        if len(payload) != model.size_bytes:
            self._show_status(self.i18n.tr("i2c_msg_size_mismatch", len(payload), model.size_bytes))
            return
        self._run("write_full", lambda: ops.write_buffer(device, 0, payload))

    def _verify(self):
        payload = self._payload_or_status()
        if not payload:
            return
        context = self._eeprom_context()
        if context is None:
            return
        ops, device = context
        self._run("verify", lambda: ops.verify(device, 0, payload))

    def _open_device(self):
        backend = self._selected_backend()
        if self._adapter is None:
            index = self.device_spin.value()
            self._adapter = Ch347I2CAdapter(index) if backend == "ch347" else Ch341I2CAdapter(index)
        adapter = self._adapter
        speed = I2C_SPEEDS_KHZ[self.speed_combo.currentIndex()]

        def work():
            adapter.set_speed(speed)
            adapter.open()
            return True

        self._run("open", work)

    def _close_device(self):
        if self._adapter is not None:
            self._adapter.close()
        self._show_status()
        self._sync_controls()

    def _scan_bus(self):
        adapter = self._adapter
        if adapter is None:
            return
        self._run("scan", adapter.scan)

    def _pick_address(self, item):
        self.device_addr_edit.setText(item.text().removeprefix("0x"))

    def _read_registers(self):
        adapter = self._adapter
        if adapter is None:
            return
        try:
            device, mem = self._addresses()
        except ValueError as exc:
            self._show_status(self.i18n.tr("i2c_msg_failed", str(exc)))
            return
        length = self.length_spin.value()
        self._last_read_base = mem
        self._run("read", lambda: adapter.read(device, mem, length))

    def _write_registers(self):
        adapter = self._adapter
        if adapter is None:
            return
        payload = self._payload_or_status()
        if not payload:
            return
        try:
            device, mem = self._addresses()
        except ValueError as exc:
            self._show_status(self.i18n.tr("i2c_msg_failed", str(exc)))
            return
        self._run("write", lambda: adapter.write(device, mem, payload))

    def _payload_or_status(self) -> bytes | None:
        try:
            return parse_hex_bytes(self.write_data_edit.text())
        except ValueError as exc:
            self._show_status(self.i18n.tr("i2c_msg_failed", str(exc)))
            return None
