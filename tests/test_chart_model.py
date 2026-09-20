"""图表通道模型测试：解码、环形缓冲、三类来源取数、导出结构。"""

import struct

import pytest

from src.core.chart_model import (
    ChannelSpec,
    ChartChannel,
    ChartSeriesStore,
    ChartSource,
    RawDtype,
    decode_raw_bytes,
    to_float,
)
from src.core.modbus_parser import ModbusResponse, RegisterValue


class FakeClock:
    """可控时钟，避免测试依赖真实时间"""

    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _store(max_points: int = 8) -> ChartSeriesStore:
    return ChartSeriesStore(max_points=max_points, clock=FakeClock())


# ─── 解码 ───────────────────────────────────────────────────


def test_decode_uint8():
    assert decode_raw_bytes(bytes([0, 1, 254, 255]), RawDtype.UINT8) == [0.0, 1.0, 254.0, 255.0]


def test_decode_int16_big_endian_signed():
    data = struct.pack(">hh", 1, -2)
    assert decode_raw_bytes(data, RawDtype.INT16_BE) == [1.0, -2.0]


def test_decode_float32_big_endian():
    data = struct.pack(">ff", 1.5, -0.25)
    values = decode_raw_bytes(data, RawDtype.FLOAT32_BE)
    assert values[0] == pytest.approx(1.5)
    assert values[1] == pytest.approx(-0.25)


@pytest.mark.parametrize("dtype,width", [(RawDtype.INT16_BE, 2), (RawDtype.FLOAT32_BE, 4)])
def test_decode_drops_incomplete_tail(dtype, width):
    """不足一帧的尾字节直接丢弃，不能拿半帧当数值"""
    full = b"\x00" * width
    assert len(decode_raw_bytes(full + b"\x01", dtype)) == 1


def test_to_float():
    assert to_float(3) == 3.0
    assert to_float(" 2.5 ") == 2.5
    assert to_float(True) == 1.0
    assert to_float("ABCD") is None
    assert to_float(b"\x01") is None


# ─── 环形缓冲 ───────────────────────────────────────────────


def test_channel_wraps_and_keeps_time_order():
    ch = ChartChannel(spec=ChannelSpec(name="a"), max_points=4)
    for i in range(6):
        ch.add_sample(float(i), float(i))

    times, values = ch.snapshot()
    assert list(values) == [2.0, 3.0, 4.0, 5.0]  # 最旧被覆盖，按时间顺序读出
    assert list(times) == [2.0, 3.0, 4.0, 5.0]


def test_channel_applies_scale_and_offset():
    spec = ChannelSpec(name="temp", scale=0.1, offset=-40.0, unit="℃")
    ch = ChartChannel(spec=spec, max_points=4)
    ch.add_sample(250.0, 0.0)

    _, values = ch.snapshot()
    assert values[0] == pytest.approx(250 * 0.1 - 40)


def test_channel_snapshot_empty_is_empty_arrays():
    ch = ChartChannel(spec=ChannelSpec(name="a"), max_points=4)
    times, values = ch.snapshot()
    assert len(times) == 0 and len(values) == 0


# ─── 通道管理 ───────────────────────────────────────────────


def test_store_add_rejects_duplicate_name():
    store = _store()
    store.add_channel(ChannelSpec(name="a"))
    with pytest.raises(ValueError):
        store.add_channel(ChannelSpec(name="a"))


def test_store_remove_and_lookup_by_source():
    store = _store()
    store.add_channel(ChannelSpec(name="raw1", source=ChartSource.RAW))
    store.add_channel(ChannelSpec(name="temp", source=ChartSource.FIELD, key="temp"))

    assert store.remove_channel("raw1") is True
    assert store.remove_channel("nope") is False
    assert [c.name for c in store.channels_for(ChartSource.FIELD)] == ["temp"]
    assert store.channel("temp") is store.channels[0]


def test_store_resizes_buffers_on_max_points_change():
    store = _store(max_points=8)
    ch = store.add_channel(ChannelSpec(name="a"))
    for i in range(8):
        ch.add_sample(float(i), float(i))

    store.set_max_points(4)
    times, values = ch.snapshot()
    assert store.max_points == 4
    assert len(values) == 0  # 改点数等于重开，不留半成品数据
    assert ch.max_points == 4


# ─── 三类来源取数 ───────────────────────────────────────────


def test_feed_raw_decodes_per_channel_dtype():
    store = _store()
    u8 = store.add_channel(ChannelSpec(name="bytes", dtype=RawDtype.UINT8))
    i16 = store.add_channel(ChannelSpec(name="words", dtype=RawDtype.INT16_BE))

    store.feed_raw(bytes([0, 1]) + struct.pack(">h", -2))  # 00 01 FF FE

    assert [float(v) for v in u8.snapshot()[1]] == [0.0, 1.0, 255.0, 254.0]
    assert [float(v) for v in i16.snapshot()[1]] == [1.0, -2.0]


def test_feed_fields_uses_key_and_counts_non_numeric():
    store = _store()
    ok = store.add_channel(ChannelSpec(name="temp", source=ChartSource.FIELD, key="temp"))
    bad = store.add_channel(ChannelSpec(name="st", source=ChartSource.FIELD, key="status"))
    missing = store.add_channel(ChannelSpec(name="x", source=ChartSource.FIELD, key="absent"))

    store.feed_fields({"temp": 21.5, "status": "OK"})
    store.feed_fields({"temp": "22", "status": "ERR"})

    assert list(ok.snapshot()[1]) == [21.5, 22.0]
    assert bad.count() == 0 and bad.skipped == 2  # 非数值不写样本，只计数
    assert missing.count() == 0 and missing.skipped == 0  # 字段不存在不算跳过


def test_feed_registers_prefers_float_and_matches_address():
    store = _store()
    r0 = store.add_channel(ChannelSpec(name="r0", source=ChartSource.REGISTER, key="0"))
    r1 = store.add_channel(ChannelSpec(name="r1", source=ChartSource.REGISTER, key="1"))
    r9 = store.add_channel(ChannelSpec(name="r9", source=ChartSource.REGISTER, key="9"))

    response = ModbusResponse(
        slave_addr=1,
        function_code=3,
        is_error=False,
        registers=[
            RegisterValue(address=0, raw_value=2, signed_value=2, float_value=1.5),
            RegisterValue(address=1, raw_value=0xFFFE, signed_value=-2, float_value=None),
        ],
    )
    store.feed_registers([response])

    assert list(r0.snapshot()[1]) == [1.5]  # 有 Float 解释时用 Float
    assert list(r1.snapshot()[1]) == [-2.0]  # 否则回落到有符号值
    assert r9.count() == 0  # 不存在的地址不写入


def test_store_timestamps_are_relative_to_start():
    clock = FakeClock()
    store = ChartSeriesStore(max_points=8, clock=clock)
    ch = store.add_channel(ChannelSpec(name="a", source=ChartSource.FIELD, key="v"))

    store.feed_fields({"v": 1})
    clock.t = 2.5
    store.feed_fields({"v": 2})

    times, _ = ch.snapshot()
    assert list(times) == [0.0, 2.5]


# ─── 导出 ───────────────────────────────────────────────────


def test_export_rows_long_format():
    store = _store()
    a = store.add_channel(ChannelSpec(name="a", unit="℃"))
    b = store.add_channel(ChannelSpec(name="b"))
    a.add_sample(1.0, 0.0)
    b.add_sample(2.0, 0.0)
    b.add_sample(3.0, 1.0)

    rows = store.export_rows()
    assert store.headers() == ["channel", "unit", "index", "t", "value"]
    assert [(r["channel"], r["index"], r["value"]) for r in rows] == [
        ("a", 0, 1.0),
        ("b", 0, 2.0),
        ("b", 1, 3.0),
    ]
    assert rows[0]["unit"] == "℃"


def test_channel_spec_round_trip():
    spec = ChannelSpec(
        name="t",
        source=ChartSource.FIELD,
        key="temp",
        dtype=RawDtype.INT16_BE,
        unit="℃",
        scale=0.1,
        offset=-5,
    )
    assert ChannelSpec.from_dict(spec.to_dict()) == spec


def test_store_clear_resets_samples():
    store = _store()
    ch = store.add_channel(ChannelSpec(name="a"))
    ch.add_sample(1.0, 0.0)

    store.clear()
    assert ch.count() == 0
