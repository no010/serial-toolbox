"""
EEPROM 型号描述与读写流程

移植自 I2CTool（MIT，Copyright (c) 2025 Peter）的 i2ctool_core/eeprom_config.py
与 eeprom_operations.py，见 THIRD_PARTY.md。型号用配置描述（地址宽度、页大小、
写周期），读写逻辑与具体 24 系列芯片解耦，加型号只需加一条 EEPROMConfig。
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.core.i2c_bus import I2CAdapter, I2CError


@dataclass(frozen=True)
class EEPROMConfig:
    """一颗 EEPROM 的寻址与写入参数"""

    eeprom_id: str
    name: str
    size_bytes: int
    address_width: int  # 内部地址字节数：1 或 2
    page_size: int  # 单次页写入上限（字节）
    write_cycle_ms: int = 5  # 写周期，期间器件不响应

    def __post_init__(self):
        if self.address_width not in (1, 2):
            raise ValueError("address_width 只能是 1 或 2")
        if self.size_bytes <= 0 or self.page_size <= 0:
            raise ValueError("容量与页大小必须为正数")


BUILTIN_EEPROM_MODELS: tuple[EEPROMConfig, ...] = (
    EEPROMConfig("24c02", "24C02 (256 B)", 256, 1, 8, 5),
    EEPROMConfig("24c08", "24C08 (1 KB)", 1024, 1, 16, 5),
    EEPROMConfig("24c256", "24C256 (32 KB)", 32768, 2, 64, 5),
)


class EEPROMOperations:
    """按型号描述做分页读写；所有地址都是 EEPROM 内部地址"""

    def __init__(self, adapter: I2CAdapter, config: EEPROMConfig, delay=time.sleep):
        self.adapter = adapter
        self.config = config
        self._delay = delay

    def _check_range(self, mem_addr: int, length: int):
        if mem_addr < 0 or length < 0 or mem_addr + length > self.config.size_bytes:
            raise ValueError(
                f"地址越界: {mem_addr:#x}+{length} 超出 {self.config.name} 的 "
                f"{self.config.size_bytes} 字节"
            )

    def read_random(self, device_addr: int, mem_addr: int, length: int) -> bytes:
        """从任意内部地址读 length 字节"""
        self._check_range(mem_addr, length)
        return self.adapter.read(device_addr, mem_addr, length, self.config.address_width)

    def read_sequential(self, device_addr: int, start_addr: int, length: int) -> bytes:
        """
        分段顺序读。

        24 系列顺序读在跨页边界时部分器件会回卷，按页切分每次重发内部地址，
        读任意区间都按同一套逻辑走。
        """
        self._check_range(start_addr, length)
        result = bytearray()
        addr = start_addr
        while len(result) < length:
            chunk = min(self.config.page_size, start_addr + length - addr)
            result.extend(self.read_random(device_addr, addr, chunk))
            addr += chunk
        return bytes(result)

    def write_page(self, device_addr: int, mem_addr: int, data: bytes):
        """写一页；调用方保证不跨页"""
        if len(data) > self.config.page_size:
            raise ValueError(f"写入 {len(data)} 字节超过页大小 {self.config.page_size}")
        if (mem_addr % self.config.page_size) + len(data) > self.config.page_size:
            raise ValueError(f"起始地址 {mem_addr:#x} 起写 {len(data)} 字节会跨页")
        self._check_range(mem_addr, len(data))
        self.adapter.write(device_addr, mem_addr, data, self.config.address_width)
        self._wait_write_cycle()

    def write_buffer(self, device_addr: int, start_addr: int, data: bytes):
        """按页切分写入，逐页等待写周期"""
        self._check_range(start_addr, len(data))
        addr = start_addr
        offset = 0
        while offset < len(data):
            room = self.config.page_size - addr % self.config.page_size
            chunk = data[offset : offset + room]
            self.adapter.write(device_addr, addr, chunk, self.config.address_width)
            self._wait_write_cycle()
            addr += len(chunk)
            offset += len(chunk)

    def read_full(self, device_addr: int) -> bytes:
        return self.read_sequential(device_addr, 0, self.config.size_bytes)

    def erase_chip(self, device_addr: int, fill_value: int = 0xFF):
        self.write_buffer(device_addr, 0, bytes([fill_value]) * self.config.size_bytes)

    def verify(self, device_addr: int, mem_addr: int, expected: bytes) -> bool:
        """回读比对；读不回来按不一致处理"""
        try:
            actual = self.read_sequential(device_addr, mem_addr, len(expected))
        except I2CError:
            return False
        return actual == expected

    def _wait_write_cycle(self):
        # 器件在写周期内对地址不应答；固定等待比忙轮询简单且时间可预期
        if self.config.write_cycle_ms > 0:
            self._delay(self.config.write_cycle_ms / 1000)
