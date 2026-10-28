"""I2C 调试面板测试（offscreen）：全部跑在仿真总线上，不碰硬件。"""

import time

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication

from src.core.i2c_bus import SimulationAdapter
from src.ui.i2c_panel import I2CPanel, format_hex_dump, parse_hex_bytes
from src.ui.i18n import Language


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


@pytest.fixture
def panel(qapp, tmp_path):
    adapter = SimulationAdapter()
    p = I2CPanel(adapter=adapter, eeprom_dir=tmp_path)
    yield p, adapter
    adapter.close()
    p.deleteLater()


def _open(p: I2CPanel):
    p._open_device()
    assert _wait_for(lambda: not p._busy), "打开设备超时"
    assert p._adapter is not None and p._adapter.is_connected()


# ─── 解析工具 ───────────────────────────────────────────────


def test_parse_hex_accepts_common_notations():
    assert parse_hex_bytes("01 02 ff") == b"\x01\x02\xff"
    assert parse_hex_bytes("0x01,0x02,0xFF") == b"\x01\x02\xff"
    assert parse_hex_bytes("0102FF") == b"\x01\x02\xff"
    assert parse_hex_bytes("") == b""
    with pytest.raises(ValueError):
        parse_hex_bytes("0G")
    with pytest.raises(ValueError):
        parse_hex_bytes("123")


def test_hex_dump_layout():
    dump = format_hex_dump(bytes(range(20)), base_addr=0x10)
    lines = dump.splitlines()
    assert lines[0] == "0010: 00 01 02 03 04 05 06 07 08 09 0A 0B 0C 0D 0E 0F"
    assert lines[1] == "0020: 10 11 12 13"


# ─── 连接与扫描 ─────────────────────────────────────────────


def test_scan_lists_addresses_and_click_fills_field(panel):
    p, _ = panel
    _open(p)
    p._scan_bus()
    assert _wait_for(lambda: not p._busy)
    items = [p.address_list.item(i).text() for i in range(p.address_list.count())]
    assert items == ["0x50", "0x51", "0x68"]

    p._pick_address(p.address_list.item(2))
    assert p.device_addr_edit.text() == "68"


def test_close_disables_bus_actions(panel):
    p, _ = panel
    _open(p)
    assert p.scan_btn.isEnabled()
    p._close_device()
    assert not p.scan_btn.isEnabled()
    assert p.open_btn.isEnabled()


# ─── 寄存器读写 ─────────────────────────────────────────────


def test_register_write_then_read_roundtrip(panel):
    p, _ = panel
    _open(p)
    p.device_addr_edit.setText("50")
    p.mem_addr_edit.setText("0010")
    p.write_data_edit.setText("DE AD BE EF")
    p._write_registers()
    assert _wait_for(lambda: not p._busy)

    p.length_spin.setValue(4)
    p._read_registers()
    assert _wait_for(lambda: not p._busy)
    assert "0010: DE AD BE EF" in p.result_text.toPlainText()


def test_absent_device_reports_failure(panel):
    p, _ = panel
    _open(p)
    p.device_addr_edit.setText("33")
    p.mem_addr_edit.setText("0000")
    p._read_registers()
    assert _wait_for(lambda: "失败" in p.status_label.text())


def test_bad_hex_is_rejected_before_io(panel):
    p, _ = panel
    _open(p)
    p.write_data_edit.setText("XYZ")
    p._write_registers()
    assert "hex" in p.status_label.text()
    assert not p._busy


# ─── EEPROM ─────────────────────────────────────────────────


def test_eeprom_read_full_shows_whole_chip(panel):
    p, _ = panel
    _open(p)
    p.device_addr_edit.setText("50")
    p._read_full()
    assert _wait_for(lambda: not p._busy)
    lines = p.result_text.toPlainText().splitlines()
    assert len(lines) == 256 // 16
    assert lines[0].startswith("0000: ")


def test_eeprom_write_full_requires_exact_size(panel):
    p, _ = panel
    _open(p)
    p.device_addr_edit.setText("50")
    p.write_data_edit.setText("00 11 22")  # 24C02 需要 256 字节
    p._write_full()
    assert "不一致" in p.status_label.text()


def test_eeprom_write_then_verify(panel):
    p, _ = panel
    _open(p)
    p.device_addr_edit.setText("50")
    payload = bytes(range(256))
    p.write_data_edit.setText(payload.hex(" "))
    p._write_full()
    assert _wait_for(lambda: not p._busy)
    assert "整片写入完成" in p.status_label.text()

    p._verify()
    assert _wait_for(lambda: not p._busy)
    assert "校验通过" in p.status_label.text()

    p.write_data_edit.setText("00" * 256)
    p._verify()
    assert _wait_for(lambda: not p._busy)
    assert "校验不一致" in p.status_label.text()


# ─── i18n 与不可用状态 ──────────────────────────────────────


def test_panel_retranslates(qapp, tmp_path):
    p = I2CPanel(adapter=SimulationAdapter(), i18n=None, eeprom_dir=tmp_path)
    p.i18n.set_language(Language.ENGLISH)
    p.retranslate_ui()
    assert p.open_btn.text() == "Open Device"
    assert p.scan_btn.text() == "Scan Bus"
    p.i18n.set_language(Language.CHINESE)
    p.retranslate_ui()
    assert p.open_btn.text() == "打开设备"
    p.deleteLater()


def test_unavailable_platform_disables_open(qapp, monkeypatch):
    from src.ui import i2c_panel

    monkeypatch.setattr(
        i2c_panel.Ch347I2CAdapter,
        "unavailable_reason",
        staticmethod(lambda: "官方库不支持当前平台"),
    )
    p = I2CPanel()
    assert "不可用" in p.status_label.text()
    assert not p.open_btn.isEnabled()
    p.deleteLater()


# ─── EEPROM 型号配置与能力门控 ──────────────────────────────


def test_custom_model_from_json_appears_in_combo(qapp, tmp_path):
    (tmp_path / "24c64.json").write_text(
        '{"id": "24c64", "name": "24C64", "size_bytes": 8192, '
        '"address_width": 2, "page_size": 32, "write_cycle_ms": 5}',
        encoding="utf-8",
    )
    p = I2CPanel(adapter=SimulationAdapter(), eeprom_dir=tmp_path)
    names = [p.model_combo.itemText(i) for i in range(p.model_combo.count())]
    assert "24C64" in names
    assert len(names) == 4
    p.deleteLater()


def test_eeprom_buttons_require_page_write_support(qapp, tmp_path):
    class NoPageWrite(SimulationAdapter):
        def supports_eeprom_page_write(self):
            return False

    p = I2CPanel(adapter=NoPageWrite(), eeprom_dir=tmp_path)
    _open(p)
    assert p.scan_btn.isEnabled()
    assert not p.read_full_btn.isEnabled()
    assert not p.write_full_btn.isEnabled()
    assert not p.verify_btn.isEnabled()
    p.deleteLater()


# ─── CH347 / CH341 后端切换 ─────────────────────────────────


def test_ch341_backend_opens_and_scans(qapp, tmp_path, monkeypatch, stub_ch341):
    from src.core import i2c_bus

    dll = stub_ch341(present=(0x50,))
    monkeypatch.setattr(i2c_bus, "load_ch341_dll", lambda path=None: dll)

    p = I2CPanel(eeprom_dir=tmp_path)
    p.backend_combo.setCurrentIndex(1)
    assert p.backend_combo.currentData() == "ch341"
    _open(p)
    assert p._adapter is not None and "CH341" in p._adapter.get_info()

    p._scan_bus()
    assert _wait_for(lambda: not p._busy)
    items = []
    for i in range(p.address_list.count()):
        item = p.address_list.item(i)
        assert item is not None
        items.append(item.text())
    assert items == ["0x50"]
    p._close_device()
    p.deleteLater()


def test_ch341_unavailable_disables_open(qapp, tmp_path, monkeypatch):
    from src.core import i2c_bus

    monkeypatch.setattr(i2c_bus, "load_ch341_dll", lambda path=None: None)
    p = I2CPanel(eeprom_dir=tmp_path)
    p.backend_combo.setCurrentIndex(1)
    p._show_status()
    p._sync_controls()

    assert not p.open_btn.isEnabled()
    assert "不可用" in p.status_label.text()


def test_backend_combo_locked_while_connected(qapp, tmp_path):
    p = I2CPanel(adapter=SimulationAdapter(), eeprom_dir=tmp_path)
    assert p.backend_combo.isEnabled()
    _open(p)
    assert not p.backend_combo.isEnabled()
    p.deleteLater()
