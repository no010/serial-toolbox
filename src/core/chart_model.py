"""
图表数据通道模型

把"数据怎么来的、怎么解码"从绘图组件里拆出来：绘图只认 (时间, 数值) 序列，
来源、字节序、缩放等都归这里管，方便单测也方便持久化通道定义。
"""

import struct
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class ChartSource(Enum):
    """通道数据来源"""

    RAW = "raw"  # 原始接收字节流
    FIELD = "field"  # 协议帧解析出的命名字段
    REGISTER = "register"  # Modbus 寄存器值


class RawDtype(Enum):
    """原始字节的解码方式"""

    UINT8 = "uint8"
    INT16_BE = "int16_be"
    FLOAT32_BE = "float32_be"


@dataclass
class ChannelSpec:
    """一条通道的定义（可 JSON 序列化，供配置持久化）"""

    name: str
    source: ChartSource = ChartSource.RAW
    key: str = ""  # FIELD: 字段名；REGISTER: 寄存器地址字符串；RAW: 忽略
    dtype: RawDtype = RawDtype.UINT8  # 仅 RAW 使用
    unit: str = ""
    scale: float = 1.0
    offset: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source.value,
            "key": self.key,
            "dtype": self.dtype.value,
            "unit": self.unit,
            "scale": self.scale,
            "offset": self.offset,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelSpec":
        return cls(
            name=data["name"],
            source=ChartSource(data.get("source", ChartSource.RAW.value)),
            key=data.get("key", ""),
            dtype=RawDtype(data.get("dtype", RawDtype.UINT8.value)),
            unit=data.get("unit", ""),
            scale=float(data.get("scale", 1.0)),
            offset=float(data.get("offset", 0.0)),
        )


def decode_raw_bytes(data: bytes, dtype: RawDtype) -> list[float]:
    """按指定方式把字节流解码成数值序列，不足一帧的尾字节丢弃"""
    if dtype == RawDtype.UINT8:
        return [float(b) for b in data]

    if dtype == RawDtype.INT16_BE:
        count = len(data) // 2
        return [float(struct.unpack(">h", data[i * 2 : i * 2 + 2])[0]) for i in range(count)]

    count = len(data) // 4
    return [float(struct.unpack(">f", data[i * 4 : i * 4 + 4])[0]) for i in range(count)]


def to_float(value) -> float | None:
    """尽力把字段值转成 float，转不了返回 None（ASCII 字段等）"""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


@dataclass
class ChartChannel:
    """一条通道的定义 + 环形缓冲样本"""

    spec: ChannelSpec
    max_points: int
    color: str = "#4FC3F7"
    visible: bool = True
    values: np.ndarray = field(default_factory=lambda: np.zeros(0), repr=False)
    times: np.ndarray = field(default_factory=lambda: np.zeros(0), repr=False)
    ptr: int = 0
    skipped: int = 0  # 非数值/取不到而跳过的采样数

    def __post_init__(self):
        self._allocate(self.max_points)

    def _allocate(self, max_points: int):
        self.max_points = max_points
        self.values = np.zeros(max_points, dtype=np.float64)
        self.times = np.zeros(max_points, dtype=np.float64)
        self.ptr = 0

    @property
    def name(self) -> str:
        return self.spec.name

    def add_sample(self, value: float, t: float):
        """写入一个采样点（应用缩放与偏移），环形覆盖最旧数据"""
        self.values[self.ptr % self.max_points] = value * self.spec.scale + self.spec.offset
        self.times[self.ptr % self.max_points] = t
        self.ptr += 1

    def count(self) -> int:
        return min(self.ptr, self.max_points)

    def snapshot(self) -> tuple[np.ndarray, np.ndarray]:
        """按时间顺序返回可见的 (时间, 数值)，未写满时不带尾部的零填充"""
        n = self.count()
        if n == 0:
            return np.empty(0), np.empty(0)
        start = self.ptr - n
        idx = (np.arange(start, start + n)) % self.max_points
        return self.times[idx], self.values[idx]

    def clear(self):
        self._allocate(self.max_points)


class ChartSeriesStore:
    """通道集合：负责增删通道、按来源取数、维护采样时间"""

    def __init__(self, max_points: int = 500, clock=time.monotonic):
        self.max_points = max_points
        self.channels: list[ChartChannel] = []
        self.clock = clock
        self.start_time = clock()

    def now(self) -> float:
        """相对起点的秒数，作为曲线的 X 值"""
        return self.clock() - self.start_time

    def set_max_points(self, max_points: int):
        self.max_points = max_points
        for channel in self.channels:
            channel._allocate(max_points)

    def add_channel(self, spec: ChannelSpec, color: str = "#4FC3F7") -> ChartChannel:
        if any(c.spec.name == spec.name for c in self.channels):
            raise ValueError(f"通道名重复: {spec.name}")
        channel = ChartChannel(spec=spec, max_points=self.max_points, color=color)
        self.channels.append(channel)
        return channel

    def remove_channel(self, name: str) -> bool:
        before = len(self.channels)
        self.channels = [c for c in self.channels if c.spec.name != name]
        return len(self.channels) < before

    def channel(self, name: str) -> ChartChannel | None:
        return next((c for c in self.channels if c.spec.name == name), None)

    def channels_for(self, source: ChartSource) -> list[ChartChannel]:
        return [c for c in self.channels if c.spec.source == source]

    def clear(self):
        for channel in self.channels:
            channel.clear()

    # ─── 按来源取数 ────────────────────────────────────────

    def feed_raw(self, data: bytes):
        """原始字节流通道：每种 dtype 各解一次，喂给绑定了该 dtype 的通道"""
        channels = self.channels_for(ChartSource.RAW)
        if not channels:
            return
        t = self.now()
        decoded: dict[RawDtype, list[float]] = {}
        for channel in channels:
            dtype = channel.spec.dtype
            if dtype not in decoded:
                decoded[dtype] = decode_raw_bytes(data, dtype)
            for value in decoded[dtype]:
                channel.add_sample(value, t)

    def feed_fields(self, fields: dict, t: float | None = None):
        """协议帧字段通道：按字段名取值，非数值字段计入 skipped"""
        channels = self.channels_for(ChartSource.FIELD)
        if not channels:
            return
        stamp = self.now() if t is None else t
        for channel in channels:
            if channel.spec.key not in fields:
                continue
            value = to_float(fields[channel.spec.key])
            if value is None:
                channel.skipped += 1
                continue
            channel.add_sample(value, stamp)

    def feed_registers(self, responses: Iterable, t: float | None = None):
        """Modbus 寄存器通道：按寄存器地址取值，优先用解析出的 Float"""
        channels = self.channels_for(ChartSource.REGISTER)
        if not channels:
            return
        stamp = self.now() if t is None else t
        wanted = {c.spec.key for c in channels}
        values: dict[str, float] = {}
        for response in responses:
            for reg in getattr(response, "registers", []):
                key = str(reg.address)
                if key not in wanted:
                    continue
                value = reg.float_value if reg.float_value is not None else reg.signed_value
                values[key] = float(value)
        for channel in channels:
            if channel.spec.key in values:
                channel.add_sample(values[channel.spec.key], stamp)

    # ─── 导出 ─────────────────────────────────────────────

    def export_rows(self) -> list[dict]:
        """长表导出：不同来源的通道采样密度差很多，横向对齐会留大片空格"""
        rows: list[dict] = []
        for channel in self.channels:
            times, values = channel.snapshot()
            for i, (t, value) in enumerate(zip(times, values, strict=True)):
                rows.append(
                    {
                        "channel": channel.spec.name,
                        "unit": channel.spec.unit,
                        "index": i,
                        "t": round(t, 6),
                        "value": value,
                    }
                )
        return rows

    @staticmethod
    def headers() -> list[str]:
        return ["channel", "unit", "index", "t", "value"]
