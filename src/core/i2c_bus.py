"""
I2C 总线适配层

把"怎么跟硬件说话"收敛到统一接口：面板只认 scan/read/write，
具体是 CH347 USB 桥还是仿真后端由适配器决定。地址一律用 7 位语义，
适配器内部再拼成 ch347-py 需要的 (地址 << 1 | 方向) 字节流。

接口形状参考 I2CTool（MIT）的 i2ctool_core/interfaces.py，见 THIRD_PARTY.md。
"""

from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable

# CH347 硬件支持的 SCL 档位，值对应官方库 i2c_set 的 0..3
I2C_SPEEDS_KHZ = (20, 100, 400, 750)

_SCAN_ADDRESSES = range(0x08, 0x78)  # 7 位地址的保留段之外


class I2CError(Exception):
    """I2C 总线操作失败"""


@runtime_checkable
class _Ch347Device(Protocol):
    """适配器实际用到的 ch347-py 接口（测试用替身按此实现即可）"""

    def open_device(self) -> int | None: ...

    def close_device(self) -> bool: ...

    def i2c_set(self, interface_speed: int) -> bool: ...

    def stream_i2c_ret_ack(self, write_data: bytes, read_length: int) -> tuple: ...


@runtime_checkable
class I2CAdapter(Protocol):
    """总线适配器契约"""

    def open(self) -> None: ...

    def close(self) -> None: ...

    @property
    def is_open(self) -> bool: ...

    def scan(self) -> list[int]: ...

    def read(self, device_addr: int, mem_addr: int, length: int, addr_width: int = 1) -> bytes: ...

    def write(self, device_addr: int, mem_addr: int, data: bytes, addr_width: int = 1) -> None: ...

    def set_speed(self, khz: int) -> None: ...


class Ch347I2CAdapter:
    """
    CH347 USB 桥的 I2C 适配器。

    ch347-py 是沁恒官方库的 ctypes 封装：Windows 用包内自带的 CH347DLLA64.DLL，
    Linux 用系统里的 libch347.so（需先装 WCH 的 ch34x_pis 驱动，见 THIRD_PARTY.md）。
    macOS 没有官方库，打开时直接报不可用。
    """

    def __init__(self, device_index: int = 0, dll_path: str | None = None):
        self._device: _Ch347Device | None = None
        self._device_index = device_index
        self._dll_path = dll_path
        self._speed_khz = 100

    @staticmethod
    def unavailable_reason() -> str:
        """不可用原因；可用时返回空串（面板据此决定是否禁用）"""
        if not (sys.platform == "win32" or sys.platform.startswith("linux")):
            return f"CH347 官方库仅支持 Windows/Linux，当前平台是 {sys.platform}"
        try:
            import ch347  # noqa: F401
        except Exception as exc:
            return f"ch347-py 无法加载: {exc}"
        return ""

    def _library_path(self) -> str | None:
        if self._dll_path:
            return self._dll_path
        if not sys.platform == "win32":
            return None  # Linux 交给系统搜索 libch347.so
        import ch347

        lib_dir = Path(ch347.__file__).resolve().parent / "lib"
        name = "CH347DLLA64.DLL" if ctypes.sizeof(ctypes.c_void_p) == 8 else "CH347DLL.DLL"
        candidate = lib_dir / name
        # 显式给路径：onefile 打包后包内 DLL 在 _MEIPASS 下，默认搜索路径找不到
        return str(candidate) if candidate.exists() else None

    def _require_device(self):
        if self._device is None:
            raise I2CError("设备未打开")
        return self._device

    @property
    def is_open(self) -> bool:
        return self._device is not None

    def open(self) -> None:
        reason = self.unavailable_reason()
        if reason:
            raise I2CError(reason)
        from ch347 import CH347

        device = CH347(self._device_index, dll_path=self._library_path())
        if device.open_device() is None:
            raise I2CError(f"打开 CH347 失败（设备编号 {self._device_index}），检查 USB 连接与驱动")
        self._device = device
        try:
            self.set_speed(self._speed_khz)
        except I2CError:
            self.close()
            raise

    def close(self) -> None:
        if self._device is not None:
            self._device.close_device()
            self._device = None

    def set_speed(self, khz: int) -> None:
        if khz not in I2C_SPEEDS_KHZ:
            raise I2CError(f"CH347 不支持 {khz} kHz，可选: {I2C_SPEEDS_KHZ}")
        if self._device is not None and not self._device.i2c_set(I2C_SPEEDS_KHZ.index(khz)):
            raise I2CError(f"设置 I2C 速率 {khz} kHz 失败")
        self._speed_khz = khz

    def _stream(self, write_data: bytes, read_length: int = 0) -> bytes:
        """一次完整传输；无应答（NACK）时抛错，避免把空数据当成功"""
        device = self._require_device()
        ok, data, acks = device.stream_i2c_ret_ack(bytes(write_data), read_length)
        if not ok:
            raise I2CError("I2C 传输失败（总线错误或设备忙）")
        if acks < 1:
            raise I2CError(f"设备 {write_data[0] >> 1:#04x} 无应答")
        return data or b""

    @staticmethod
    def _address_bytes(device_addr: int, mem_addr: int, addr_width: int, write: bool) -> bytes:
        if not 0 <= device_addr <= 0x7F:
            raise I2CError(f"设备地址超出 7 位范围: {device_addr:#04x}")
        if addr_width not in (1, 2):
            raise I2CError(f"内部地址宽度只能是 1 或 2 字节: {addr_width}")
        if not 0 <= mem_addr < 1 << (8 * addr_width):
            raise I2CError(f"内部地址 {mem_addr:#x} 超出 {addr_width} 字节范围")
        first = device_addr << 1 | (0 if write else 1)
        return bytes([first]) + mem_addr.to_bytes(addr_width, "big")

    def scan(self) -> list[int]:
        device = self._require_device()
        found: list[int] = []
        for addr in _SCAN_ADDRESSES:
            ok, _data, acks = device.stream_i2c_ret_ack(bytes([addr << 1]), 0)
            if ok and acks >= 1:
                found.append(addr)
        return found

    def read(self, device_addr: int, mem_addr: int, length: int, addr_width: int = 1) -> bytes:
        if length < 0:
            raise I2CError(f"读取长度不能为负: {length}")
        if length == 0:
            return b""
        write_data = self._address_bytes(device_addr, mem_addr, addr_width, write=False)
        data = self._stream(write_data, length)
        if len(data) != length:
            raise I2CError(f"读取长度不足: 期望 {length}, 实际 {len(data)}")
        return data

    def write(self, device_addr: int, mem_addr: int, data: bytes, addr_width: int = 1) -> None:
        if not data:
            return
        write_data = self._address_bytes(device_addr, mem_addr, addr_width, write=True) + bytes(
            data
        )
        self._stream(write_data, 0)

    def info(self) -> str:
        if self._device is None:
            return "CH347 (未打开)"
        return f"CH347 #{self._device_index} @ {self._speed_khz} kHz"


class SimulationAdapter:
    """
    内存仿真后端：无硬件时跑 UI、跑测试用。

    内部地址空间按 64 KB 字节数组模拟，写入立即生效；
    scan 返回固定的一组地址，read/write 越界抛 I2CError。
    """

    DEVICES = (0x50, 0x51, 0x68)

    def __init__(self, speeds_khz: tuple[int, ...] = I2C_SPEEDS_KHZ):
        self._open = False
        self._memory = bytearray(0x10000)
        self._speed_khz = 100
        self._speeds = speeds_khz

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def set_speed(self, khz: int) -> None:
        if khz not in self._speeds:
            raise I2CError(f"不支持 {khz} kHz，可选: {self._speeds}")
        self._speed_khz = khz

    def _require_open(self):
        if not self._open:
            raise I2CError("设备未打开")

    def scan(self) -> list[int]:
        self._require_open()
        return list(self.DEVICES)

    def read(self, device_addr: int, mem_addr: int, length: int, addr_width: int = 1) -> bytes:
        self._require_open()
        if device_addr not in self.DEVICES:
            raise I2CError(f"设备 {device_addr:#04x} 无应答")
        end = mem_addr + length
        if mem_addr < 0 or end > len(self._memory):
            raise I2CError(f"内部地址越界: {mem_addr:#x}+{length}")
        return bytes(self._memory[mem_addr:end])

    def write(self, device_addr: int, mem_addr: int, data: bytes, addr_width: int = 1) -> None:
        self._require_open()
        if device_addr not in self.DEVICES:
            raise I2CError(f"设备 {device_addr:#04x} 无应答")
        end = mem_addr + len(data)
        if mem_addr < 0 or end > len(self._memory):
            raise I2CError(f"内部地址越界: {mem_addr:#x}+{len(data)}")
        self._memory[mem_addr:end] = data

    def info(self) -> str:
        return f"仿真 I2C @ {self._speed_khz} kHz"
