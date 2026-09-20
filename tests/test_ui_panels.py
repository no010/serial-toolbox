"""UI 面板测试（offscreen Qt）：覆盖此前导致启动崩溃的 ScriptEditorPanel 重写。"""
import time

import pytest
from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class FakeSM:
    """最小串口管理器替身"""

    on_data_received = None

    def send(self, data):
        return True

    def send_text(self, data, fmt):
        return True


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    """在处理 Qt 事件的同时等待条件成立（跨线程信号需事件循环投递）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return predicate()


def test_script_panel_constructs_and_logs(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(None)  # 构造不得抛 AttributeError（output_text 提前引用已修复）
    p.script_log.connect(p.append_log)
    p.script_log.emit("hello")
    assert "hello" in p.output_text.toPlainText()
    p._clear_output()
    assert p.output_text.toPlainText() == ""


def test_script_panel_engine_on_log_wired(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    assert p.engine is not None and callable(p.engine.on_log)  # _on_engine_log 缺失已修复
    p.script_log.connect(p.append_log)
    p.engine.on_log("from-engine")
    assert "from-engine" in p.output_text.toPlainText()


def test_script_panel_prefills_example_code(qapp):
    """回归：启动时加载了不存在的示例名「发送递增字节」，代码区一直是空的。"""
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(None)
    assert p.code_edit.toPlainText().strip(), "示例脚本未预填到代码区"
    assert p.example_combo.currentText() in p.code_edit.toPlainText()


def test_script_panel_buttons_drive_engine(qapp, monkeypatch):
    """回归：引擎的 pause/resume/step_over/stop 此前在 GUI 里完全没有入口。

    禁用态的按钮 click() 不生效，因此这里按引擎上报的状态逐步点击，顺带验证状态门控。
    """
    from src.ui.extended_panels import ScriptEditorPanel

    calls = []

    p = ScriptEditorPanel(FakeSM())
    assert p.engine is not None
    for name in ("execute", "pause", "resume", "step_over", "stop"):
        monkeypatch.setattr(p.engine, name, lambda *a, n=name: calls.append(n))

    p.run_btn.click()
    assert calls == ["execute"]
    assert not p.pause_btn.isEnabled(), "空闲态不该能点暂停"

    p.script_state_changed.emit('running')
    assert not p.run_btn.isEnabled(), "运行中不该能重复启动"
    p.pause_btn.click()
    p.stop_btn.click()
    assert calls == ["execute", "pause", "stop"]

    p.script_state_changed.emit('breakpoint')
    p.resume_btn.click()
    p.step_btn.click()
    assert calls == ["execute", "pause", "stop", "resume", "step_over"]


def test_script_panel_without_engine_is_not_silent(qapp):
    """回归：没有串口管理器时点运行原本静默无反应，还会谎报"脚本执行完毕"。"""
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(None)
    assert p.engine is None
    p._run_script()

    text = p.output_text.toPlainText()
    assert "不可用" in text
    assert "脚本执行完毕" not in text


def test_script_panel_reports_completion_from_engine_thread(qapp):
    """运行是异步的：完成提示必须来自引擎线程经信号回主线程，而不是 execute 返回后立刻打印。"""
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.script_log.connect(p.append_log)
    p.code_edit.setPlainText('log_info("hi")')

    p._run_script()
    assert _wait_for(lambda: "脚本执行完毕" in p.output_text.toPlainText())
    assert "hi" in p.output_text.toPlainText()
    assert _wait_for(lambda: p.run_btn.isEnabled()), "结束后运行按钮应恢复可用"
    assert not p.pause_btn.isEnabled()
    assert "状态: 已结束" in p.state_label.text()


def test_script_panel_shows_failure_reason(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.script_finished.emit(False, "boom (第 2 行)")

    assert "脚本执行失败: boom (第 2 行)" in p.output_text.toPlainText()


def test_script_panel_pause_resume_through_ui(qapp):
    """UI 层端到端：真实引擎线程 + 跨线程状态信号 + 暂停/恢复按钮。"""
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.script_log.connect(p.append_log)
    p.code_edit.setPlainText('log_info("s1")\nsleep(0.5)\nlog_info("s2")')

    p._run_script()
    assert _wait_for(lambda: "s1" in p.output_text.toPlainText())
    assert _wait_for(lambda: p.pause_btn.isEnabled()), "未收到引擎的 running 状态"

    p.pause_btn.click()
    assert _wait_for(lambda: p.resume_btn.isEnabled()), "未停在语句边界"
    time.sleep(0.7)                        # 越过 sleep(0.5)
    assert "s2" not in p.output_text.toPlainText(), "暂停后脚本仍在往下跑"

    p.resume_btn.click()
    assert _wait_for(lambda: "s2" in p.output_text.toPlainText())
    assert _wait_for(lambda: "脚本执行完毕" in p.output_text.toPlainText())


def test_main_window_constructs(qapp):
    # 端到端：主窗口构造会触发 main_window 中 script_log → append_log 的连接
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    assert w is not None


def test_main_window_has_no_dead_chart_class(qapp):
    """RealtimeChart 从未被实例化，与 EnhancedChart 重叠，已删除"""
    from src.ui import main_window

    assert not hasattr(main_window, "RealtimeChart")


class _FakeFrame:
    def __init__(self, fields, raw=b'\x01\x02'):
        self.fields = fields
        self.protocol = 'demo'
        self.timestamp = '10:00:00'
        self.raw_data = raw


def _cell(table, row: int, col: int) -> str:
    item = table.item(row, col)
    assert item is not None
    return item.text()


def test_main_window_feeds_chart_from_all_sources(qapp, monkeypatch):
    """回归：图表原先只被喂 CH1 的原始字节，CH2-4 与解析出的字段/寄存器毫无来源"""
    import struct

    from src.core.chart_model import ChannelSpec, ChartSource
    from src.core.protocol_parser import CRC16
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    w.chart.add_channel(ChannelSpec(name="bytes", source=ChartSource.RAW))
    w.chart.add_channel(ChannelSpec(name="r0", source=ChartSource.REGISTER, key="0"))

    body = bytes([1, 0x03, 2]) + struct.pack('>H', 500)
    frame = body + struct.pack('<H', CRC16.calculate(body))
    w.on_serial_data_received(frame)

    raw = w.chart.store.channel("bytes")
    register = w.chart.store.channel("r0")
    assert raw is not None and register is not None
    assert [float(v) for v in raw.snapshot()[1]] == [float(b) for b in frame]
    assert [float(v) for v in register.snapshot()[1]] == [500.0]

    seen: list = []
    monkeypatch.setattr(w.stream_parser, "feed", lambda data: [_FakeFrame({'temp': 21.5})])
    monkeypatch.setattr(w.chart, "feed_fields", lambda frames: seen.extend(frames))

    w._parse_protocol_data(b'x')
    assert [received.fields for received in seen] == [{'temp': 21.5}]


def test_serial_read_thread_callback_is_marshalled(qapp, monkeypatch):
    """串口读线程回调必须经信号编组到 GUI 线程，不能在读线程里直接碰控件"""
    import threading

    from src.core.chart_model import ChannelSpec, ChartSource
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    w.chart.add_channel(ChannelSpec(name="bytes", source=ChartSource.RAW))
    threads: list[str] = []
    real_feed_raw = w.chart.feed_raw

    def spy(data: bytes):
        threads.append(threading.current_thread().name)
        real_feed_raw(data)

    monkeypatch.setattr(w.chart, "feed_raw", spy)
    on_data = w.serial_manager.on_data_received
    assert on_data is not None, "setup_connections 未挂上读线程回调"

    worker = threading.Thread(target=lambda: on_data(b'\x01'))
    worker.start()
    worker.join()

    assert threads == [], "回调在工作线程里就直接动了控件"
    QCoreApplication.processEvents()
    assert threads == ['MainThread'], f"回调未编组到主线程: {threads}"


def test_protocol_table_shows_every_field(qapp):
    """回归：一帧多字段时表格只显示第一个字段，其余值用户看不到"""
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    w.protocol_table.setRowCount(0)

    w._add_protocol_frame(_FakeFrame({'temp': 21.5, 'hum': 60}))

    assert w.protocol_table.rowCount() == 2
    assert [(_cell(w.protocol_table, r, 2), _cell(w.protocol_table, r, 3))
            for r in range(2)] == [('temp', '21.5'), ('hum', '60')]
    assert _cell(w.protocol_table, 1, 4) == ''      # 原始数据只在首行显示
