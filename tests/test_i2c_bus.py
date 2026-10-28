"""I2C 适配层与 EEPROM 逻辑测试（无硬件）。

适配器用假 CH347 对象验证帧构造与 ACK 判定；EEPROM 流程跑在仿真总线上。
"""

import sys
from pathlib import Path

import pytest

from src.core.eeprom import BUILTIN_EEPROM_MODELS, EEPROMConfig, EEPROMOperations
from src.core.i2c_bus import I2C_SPEEDS_KHZ, Ch347I2CAdapter, I2CError, SimulationAdapter


class FakeCh347:
    """最小 CH347 替身：只实现适配器用到的三个方法"""

    def __init__(self, present=(0x50,)):
        self.present = set(present)
        self.transfers: list[tuple[bytes, int]] = []
        self.speed_mode: int | None = None
        self.closed = False

    def stream_i2c_ret_ack(self, write_data, read_length):
        addr = write_data[0] >> 1
        if addr not in self.present:
            return True, None, 0  # 总线正常但器件不应答
        self.transfers.append((bytes(write_data), read_length))
        return True, bytes([0xA5]) * read_length, len(write_data)

    def open_device(self):
        return 1

    def i2c_set(self, interface_speed):
        self.speed_mode = interface_speed
        return True

    def close_device(self):
        self.closed = True


def _adapter_with_fake(present=(0x50,)) -> tuple[Ch347I2CAdapter, FakeCh347]:
    adapter = Ch347I2CAdapter()
    fake = FakeCh347(present)
    adapter._device = fake
    return adapter, fake


def test_scan_reports_only_responding_devices():
    adapter, _ = _adapter_with_fake(present=(0x50, 0x68))
    assert adapter.scan() == [0x50, 0x68]


def test_scan_skips_reserved_addresses():
    adapter, _ = _adapter_with_fake(present=(0x03,))  # 保留地址段
    assert adapter.scan() == []


def test_read_builds_read_direction_and_address_width():
    adapter, fake = _adapter_with_fake()
    data = adapter.read(0x50, 0x1234, 4, addr_width=2)
    assert data == b"\xa5" * 4
    write_data, read_length = fake.transfers[-1]
    assert write_data == bytes([0x50 << 1 | 1, 0x12, 0x34])
    assert read_length == 4


def test_write_builds_write_direction_and_payload():
    adapter, fake = _adapter_with_fake()
    adapter.write(0x50, 0x00FF, b"\x01\x02", addr_width=1)
    write_data, read_length = fake.transfers[-1]
    assert write_data == bytes([0x50 << 1, 0xFF, 0x01, 0x02])
    assert read_length == 0


def test_absent_device_raises_nack():
    adapter, _ = _adapter_with_fake(present=())
    with pytest.raises(I2CError, match="无应答"):
        adapter.read(0x50, 0, 1)


def test_operations_require_open_device():
    adapter = Ch347I2CAdapter()
    with pytest.raises(I2CError, match="未打开"):
        adapter.read(0x50, 0, 1)


def test_speed_maps_to_official_mode_index():
    adapter, fake = _adapter_with_fake()
    adapter.set_speed(400)
    assert fake.speed_mode == I2C_SPEEDS_KHZ.index(400) == 2
    with pytest.raises(I2CError, match="不支持"):
        adapter.set_speed(200)


def test_address_bounds_are_validated():
    adapter, _ = _adapter_with_fake()
    with pytest.raises(I2CError, match="7 位"):
        adapter.read(0x80, 0, 1)
    with pytest.raises(I2CError, match="超出 1 字节"):
        adapter.read(0x50, 0x100, 1, addr_width=1)
    with pytest.raises(I2CError, match="1 或 2 字节"):
        adapter.read(0x50, 0, 1, addr_width=3)


def test_close_releases_device():
    adapter, fake = _adapter_with_fake()
    adapter.close()
    assert fake.closed and not adapter.is_open


def test_platform_check_and_bundled_dll():
    assert Ch347I2CAdapter.unavailable_reason() == ""
    if sys.platform == "win32":
        import ch347

        expected = Path(ch347.__file__).parent / "lib" / "CH347DLLA64.DLL"
        resolved = Ch347I2CAdapter()._library_path()
        assert resolved is not None and Path(resolved).exists(), "打包/安装应带厂商 DLL"
        assert expected.exists()


# ─── EEPROM ─────────────────────────────────────────────────


def _ops(model_id="24c02", device=0x50):
    model = next(m for m in BUILTIN_EEPROM_MODELS if m.eeprom_id == model_id)
    adapter = SimulationAdapter()
    adapter.open()
    waits: list[float] = []
    return EEPROMOperations(adapter, model, delay=waits.append), adapter, waits, device


def test_eeprom_read_write_roundtrip_across_pages():
    ops, adapter, _, dev = _ops("24c02")  # 页 8 字节
    payload = bytes(range(20))
    ops.write_buffer(dev, 0, payload)
    assert ops.read_sequential(dev, 0, len(payload)) == payload
    assert adapter.read(dev, 0, len(payload)) == payload


def test_write_buffer_splits_by_page_and_waits_each_page():
    ops, _, waits, dev = _ops("24c02")
    ops.write_buffer(dev, 0, bytes(20))
    assert waits == [0.005, 0.005, 0.005]  # 8 + 8 + 4


def test_write_buffer_respects_mid_page_start():
    ops, _, waits, dev = _ops("24c02")
    ops.write_buffer(dev, 6, bytes(10))  # 6..15 → 2 字节补满首页，再 8 字节
    assert waits == [0.005, 0.005]


def test_write_page_rejects_cross_page():
    ops, _, _, dev = _ops("24c02")
    with pytest.raises(ValueError, match="跨页"):
        ops.write_page(dev, 6, bytes(4))
    with pytest.raises(ValueError, match="页大小"):
        ops.write_page(dev, 0, bytes(9))


def test_eeprom_range_is_enforced():
    ops, _, _, dev = _ops("24c02")
    with pytest.raises(ValueError, match="越界"):
        ops.read_random(dev, 250, 10)
    with pytest.raises(ValueError, match="越界"):
        ops.write_buffer(dev, 250, bytes(10))


def test_erase_and_verify():
    ops, _, _, dev = _ops("24c02")
    ops.write_buffer(dev, 0, b"\x00" * 16)
    ops.erase_chip(dev)
    assert ops.read_full(dev) == b"\xff" * 256
    assert ops.verify(dev, 0, b"\xff" * 16)
    assert not ops.verify(dev, 0, b"\x00" * 16)


def test_verify_returns_false_when_device_missing():
    ops, adapter, _, dev = _ops("24c02")
    adapter.close()  # 未打开 → 读抛错 → 校验按不一致处理
    assert ops.verify(dev, 0, b"\x00") is False


def test_two_byte_address_model_uses_full_size():
    ops, _, _, dev = _ops("24c256")
    ops.write_buffer(dev, 0x7FF0, b"\x11\x22")
    assert ops.read_random(dev, 0x7FF0, 2) == b"\x11\x22"
    assert ops.config.address_width == 2


def test_eeprom_config_validation():
    with pytest.raises(ValueError):
        EEPROMConfig("bad", "bad", 256, 3, 8)
    with pytest.raises(ValueError):
        EEPROMConfig("bad", "bad", 0, 1, 8)
