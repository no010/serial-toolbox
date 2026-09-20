"""图表视图层测试（offscreen Qt）：通道增删、节流与冻结、光标读数、CSV 导出、配置往返。"""

import csv

import pytest
from PyQt6.QtWidgets import QApplication

from src.core.chart_model import ChannelSpec, ChartSource, RawDtype
from src.core.modbus_parser import ModbusResponse, RegisterValue
from src.ui.enhanced_chart import (
    DTYPE_BY_INDEX,
    DTYPE_KEYS,
    INDEX_BY_DTYPE,
    ChannelSpecDialog,
    EnhancedChart,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeFrame:
    """最小协议帧替身"""

    def __init__(self, fields):
        self.fields = fields


@pytest.fixture
def chart(qapp):
    widget = EnhancedChart(max_points=16, max_channels=3, refresh_ms=1000)
    widget.refresh_timer.stop()  # 关掉自动节拍，由测试显式触发重绘
    yield widget
    widget.refresh_timer.stop()


def _raw(name="bytes", dtype=RawDtype.UINT8, **kw):
    return ChannelSpec(name=name, source=ChartSource.RAW, dtype=dtype, **kw)


def _samples(widget: EnhancedChart, name: str) -> list[float]:
    """取某通道当前样本（同时收窄 channel() 的 Optional）"""
    channel = widget.store.channel(name)
    assert channel is not None, f"通道不存在: {name}"
    return [float(v) for v in channel.snapshot()[1]]


def _count(widget: EnhancedChart, name: str) -> int:
    channel = widget.store.channel(name)
    assert channel is not None, f"通道不存在: {name}"
    return channel.count()


# ─── 通道 ───────────────────────────────────────────────────


def test_add_and_remove_channel(chart):
    assert chart.add_channel(_raw()) is None
    assert chart.channel_names() == ["bytes"]
    assert "bytes" in chart.curves

    chart.remove_channel("bytes")
    assert chart.channel_names() == []
    assert chart.curves == {}


def test_duplicate_channel_name_is_reported(chart):
    assert chart.add_channel(_raw("a")) is None
    assert "a" in str(chart.add_channel(_raw("a")))


def test_channel_limit(chart):
    for i in range(3):
        assert chart.add_channel(_raw(f"c{i}")) is None
    assert "最多 3 个通道" in chart.add_channel(_raw("overflow"))


def test_curves_match_channels(chart):
    chart.add_channel(_raw("a"))
    chart.add_channel(_raw("b"))
    chart.remove_channel("a")
    assert set(chart.curves) == {"b"}


# ─── 取数 ───────────────────────────────────────────────────


def test_feed_raw_only_reaches_raw_channels(chart):
    chart.add_channel(_raw("bytes"))
    chart.add_channel(ChannelSpec(name="temp", source=ChartSource.FIELD, key="temp"))

    chart.feed_raw(b"\x01\x02")
    chart.feed_fields([FakeFrame({"temp": 30})])

    assert _samples(chart, "bytes") == [1.0, 2.0]
    assert _samples(chart, "temp") == [30.0]


def test_feed_registers_uses_seen_addresses(chart):
    chart.add_channel(ChannelSpec(name="r0", source=ChartSource.REGISTER, key="0"))
    response = ModbusResponse(
        slave_addr=1,
        function_code=3,
        is_error=False,
        registers=[RegisterValue(address=0, raw_value=7, signed_value=7)],
    )

    chart.feed_registers([response])

    assert "0" in chart._seen_registers  # 见过的地址供通道下拉选择
    assert _samples(chart, "r0") == [7.0]


def test_collect_disabled_stops_sampling(chart):
    chart.add_channel(_raw())
    chart.collect_check.setChecked(False)

    chart.feed_raw(b"\x01\x02")

    assert _count(chart, "bytes") == 0
    assert chart.is_collect_enabled() is False
    assert not chart.refresh_timer.isActive(), "关闭采集后不该继续空转重绘"


def test_freeze_keeps_sampling_but_stops_repaint(chart):
    chart.add_channel(_raw())
    chart.freeze_btn.setChecked(True)

    painted = []
    chart._update_plot = lambda: painted.append(1)  # type: ignore[method-assign]
    chart.feed_raw(b"\x01")
    chart._repaint_if_dirty()
    assert painted == []

    chart.freeze_btn.setChecked(False)
    chart._repaint_if_dirty()
    assert painted == [1]
    assert _count(chart, "bytes") == 1  # 冻结期间数据没丢


def test_repaint_is_throttled_to_timer_tick(chart):
    chart.add_channel(_raw())
    painted = []
    real_update = chart._update_plot

    def spy():
        painted.append(1)
        real_update()

    chart._update_plot = spy  # type: ignore[method-assign]

    chart.feed_raw(b"\x01")
    chart.feed_raw(b"\x02")
    assert painted == []  # 喂数据本身不重绘

    chart._repaint_if_dirty()
    assert painted == [1]
    chart._repaint_if_dirty()
    assert painted == [1]  # 无新数据不重复重绘


def test_time_axis_plots_timestamps(chart):
    chart.add_channel(ChannelSpec(name="temp", source=ChartSource.FIELD, key="t"))
    chart.store.start_time = 0.0
    chart.set_x_axis_mode("time")
    assert chart.x_axis_mode() == "time"

    seen = {}
    curve = chart.curves["temp"]
    curve.setData = lambda x, y=None: seen.update(x=x, y=y)  # type: ignore[method-assign]
    chart.store.feed_fields({"t": 1.0}, t=3.5)
    chart._update_plot()

    assert float(seen["x"][0]) == pytest.approx(3.5)


# ─── 光标与导出 ─────────────────────────────────────────────


def test_cursor_readout_reports_deltas(chart):
    chart.add_channel(_raw("bytes"))
    channel = chart.store.channel("bytes")
    assert channel is not None
    for i in range(6):
        channel.add_sample(float(i), float(i))
    chart.cursor_a.setPos(1)
    chart.cursor_b.setPos(4)

    text = chart.cursor_label.text()
    assert "ΔX=3.000 点" in text
    assert "Δbytes=+3" in text


def test_xy_mode_uses_two_channels(qapp):
    widget = EnhancedChart(max_points=16, max_channels=3, refresh_ms=1000)
    widget.refresh_timer.stop()
    widget.add_channel(_raw("x"))
    widget.add_channel(ChannelSpec(name="y", source=ChartSource.FIELD, key="y"))
    widget.xy_x_combo.setCurrentText("x")
    widget.xy_y_combo.setCurrentText("y")

    widget.mode_combo.setCurrentIndex(1)  # XY (李萨如)
    seen = {}
    widget.xy_curve.setData = lambda x, y: seen.update(x=x, y=y)  # type: ignore[method-assign]
    widget.store.feed_raw(b"\x01\x02")
    widget.store.feed_fields({"y": 9.0}, t=0.0)
    widget._repaint_if_dirty()

    assert widget.xy_mode is True
    assert list(seen["y"]) == [9.0]
    widget.plot_widget.close()


def test_cursor_readout_refreshes_with_new_data(qapp):
    widget = EnhancedChart(max_points=16, max_channels=2, refresh_ms=1000)
    widget.refresh_timer.stop()
    assert "拖动竖线" in widget.cursor_label.text(), "构造期不该把提示文案覆盖成无可见通道"

    widget.add_channel(_raw("bytes"))
    widget.cursor_a.setPos(0)
    widget.cursor_b.setPos(2)
    assert "无可见通道" in widget.cursor_label.text()  # 光标就位但还没数据

    widget.store.feed_raw(b"\x00\x0a\x14")
    widget._update_plot()  # 只长数据，不移动光标
    assert "Δbytes=+20" in widget.cursor_label.text(), widget.cursor_label.text()
    widget.plot_widget.close()


def test_cursor_label_without_visible_channel(qapp):
    widget = EnhancedChart(max_points=8, max_channels=2)
    widget.refresh_timer.stop()
    widget.add_channel(_raw("bytes"))
    hidden = widget.store.channel("bytes")
    assert hidden is not None
    hidden.visible = False

    widget._update_plot()
    assert "无可见通道" in widget.cursor_label.text()
    widget.plot_widget.close()


def test_export_csv_writes_long_rows(chart, tmp_path):
    chart.add_channel(ChannelSpec(name="temp", source=ChartSource.FIELD, key="t", unit="℃"))
    chart.store.feed_fields({"t": 21.5}, t=0.0)
    chart.store.feed_fields({"t": 22.0}, t=1.0)

    path = tmp_path / "chart.csv"
    count = chart.export_csv(str(path))

    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert count == 2 == len(rows)
    assert rows[0]["channel"] == "temp" and rows[0]["unit"] == "℃"
    assert float(rows[1]["value"]) == 22.0


# ─── 配置与对话框 ───────────────────────────────────────────


def test_channel_specs_round_trip(chart):
    chart.add_channel(_raw("bytes", dtype=RawDtype.INT16_BE))
    chart.add_channel(
        ChannelSpec(
            name="temp", source=ChartSource.FIELD, key="temp", unit="℃", scale=0.1, offset=-40
        )
    )

    other = EnhancedChart(max_points=16, max_channels=3)
    other.refresh_timer.stop()
    other.apply_channel_specs(chart.channel_specs())

    assert other.channel_names() == ["bytes", "temp"]
    temp = other.store.channel("temp")
    raw = other.store.channel("bytes")
    assert temp is not None and raw is not None
    assert temp.spec.scale == 0.1
    assert raw.spec.dtype == RawDtype.INT16_BE
    other.apply_channel_specs([{"bogus": 1}])  # 非法项应被跳过而不是抛出
    assert other.channel_names() == ["bytes", "temp"]


def test_dtype_index_maps_follow_the_enum():
    """回归：映射曾按显示字符串建键，用 RawDtype 查会 KeyError"""
    assert {i: d for i, d in enumerate(RawDtype)} == DTYPE_BY_INDEX
    assert {d: i for i, d in enumerate(RawDtype)} == INDEX_BY_DTYPE
    assert set(DTYPE_KEYS) == set(RawDtype)


def test_channel_dialog_spec_reflects_source(qapp):
    dialog = ChannelSpecDialog(field_names=["temp", "hum"], register_keys=["0", "3"])
    dialog.name_edit.setText("温度")
    dialog.source_combo.setCurrentIndex(1)
    dialog.key_combo.setCurrentText("temp")
    dialog.unit_edit.setText("℃")

    spec = dialog.spec()
    assert spec == ChannelSpec(name="温度", source=ChartSource.FIELD, key="temp", unit="℃")

    dialog.source_combo.setCurrentIndex(2)
    assert [dialog.key_combo.itemText(i) for i in range(dialog.key_combo.count())] == ["0", "3"]
    assert dialog.key_combo.currentText() == "0"  # 候选重建后落在首项
    assert dialog.dtype_combo.isHidden() or not dialog.dtype_combo.isVisibleTo(dialog)


def test_right_axis_channels_live_in_own_viewbox(qapp):
    """回归：所有通道共用一个 Y 轴，量级差大时小幅曲线被压平"""
    chart = EnhancedChart(max_points=16)
    chart.refresh_timer.stop()
    assert chart.add_channel(ChannelSpec(name="big")) is None
    assert chart.add_channel(ChannelSpec(name="small", axis="right")) is None

    big_curve = chart.curves["big"]
    small_curve = chart.curves["small"]
    assert big_curve in chart.left_viewbox.addedItems
    assert small_curve in chart.right_viewbox.addedItems
    assert chart.right_axis.isVisible()

    # 删掉唯一的右轴通道后右轴隐藏
    chart.remove_channel("small")
    assert not chart.right_axis.isVisible()
    assert small_curve not in chart.right_viewbox.addedItems


def test_channel_axis_survives_edit_and_config_round_trip(qapp):
    chart = EnhancedChart(max_points=16)
    chart.refresh_timer.stop()
    chart.add_channel(ChannelSpec(name="t", source=ChartSource.FIELD, key="temp", axis="right"))
    specs = chart.channel_specs()
    assert specs[0]["axis"] == "right"

    # 编辑通道改轴：曲线在两个 ViewBox 之间迁移，且不重复
    channel = chart.store.channel("t")
    assert channel is not None
    chart.store.remove_channel("t")
    chart.store.add_channel(
        ChannelSpec(name="t", source=ChartSource.FIELD, key="temp", axis="left"),
        color=channel.color,
    )
    chart._sync_curves()
    curve = chart.curves["t"]
    assert curve in chart.left_viewbox.addedItems
    assert curve not in chart.right_viewbox.addedItems
    assert not chart.right_axis.isVisible()


def test_channel_dialog_axis_round_trip(qapp):
    spec = ChannelSpec(name="t", axis="right")
    dialog = ChannelSpecDialog(spec=spec)
    assert dialog.axis_combo.currentIndex() == 1
    assert dialog.spec().axis == "right"

    dialog.axis_combo.setCurrentIndex(0)
    assert dialog.spec().axis == "left"
