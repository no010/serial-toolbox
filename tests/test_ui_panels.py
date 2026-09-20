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

    p.script_state_changed.emit("running")
    assert not p.run_btn.isEnabled(), "运行中不该能重复启动"
    p.pause_btn.click()
    p.stop_btn.click()
    assert calls == ["execute", "pause", "stop"]

    p.script_state_changed.emit("breakpoint")
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


# ─── 断点行号槽 ──────────────────────────────────────────────


def _press_gutter_at_line(gutter, edit, line: int):
    """在行号槽上指定行的位置合成一次鼠标点击"""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    block = edit.document().findBlockByNumber(line - 1)
    top = edit.blockBoundingGeometry(block).translated(edit.contentOffset()).top()
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(gutter.width() / 2, top + 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    gutter.mousePressEvent(event)


def test_gutter_click_toggles_engine_breakpoint(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    assert p.gutter.isVisibleTo(p), "有引擎时应显示行号槽"

    _press_gutter_at_line(p.gutter, p.code_edit, 3)
    assert p.engine is not None and p.engine.has_breakpoint(3)

    _press_gutter_at_line(p.gutter, p.code_edit, 3)
    assert not p.engine.has_breakpoint(3)


def test_gutter_click_outside_text_does_nothing(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.code_edit.setPlainText("x = 1")  # 只有 1 行

    _press_gutter_at_line(p.gutter, p.code_edit, 1)
    assert p.engine is not None and p.engine.has_breakpoint(1)

    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    # 点在最后一行之下（文档外空白），不得新增断点
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(p.gutter.width() / 2, p.gutter.height() - 1),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    p.gutter.mousePressEvent(event)
    assert p.engine.breakpoints == {1: p.engine.breakpoints[1]}


def test_gutter_hidden_and_inert_without_engine(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(None)
    assert not p.gutter.isVisibleTo(p), "无引擎时不应显示行号槽"
    _press_gutter_at_line(p.gutter, p.code_edit, 2)  # engine 为 None，不得抛错


def test_gutter_hit_line_follows_breakpoint_signal(qapp):
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.breakpoint_hit.emit(4)
    assert p.gutter.hit_line == 4

    p.script_state_changed.emit("running")
    assert p.gutter.hit_line == 0, "离开断点状态后高亮应清除"


def test_gutter_paints_dot_and_keeps_line_numbers(qapp):
    """断点行画红点但行号不能被顶掉；无断点时只有行号。"""
    from PyQt6.QtGui import QImage

    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.resize(600, 300)
    p.code_edit.setPlainText("a = 1\nb = 2\nc = 3\n")
    p.show()
    QCoreApplication.processEvents()

    def ink():
        """返回槽内与背景不同的像素分类集合：'dot' = 红点，'ink' = 行号笔画"""
        img = p.gutter.grab().toImage().convertToFormat(QImage.Format.Format_RGB32)
        bg = img.pixelColor(0, img.height() - 2)
        kinds = set()
        for y in range(img.height() - 2):
            for x in range(img.width()):
                c = img.pixelColor(x, y)
                if (
                    abs(c.red() - bg.red())
                    + abs(c.green() - bg.green())
                    + abs(c.blue() - bg.blue())
                    < 60
                ):
                    continue
                kinds.add("dot" if c.red() > 150 and c.green() < 90 and c.blue() < 90 else "ink")
        return kinds

    assert ink() == {"ink"}, "无断点时应当只画行号"

    assert p.engine is not None
    p.engine.set_breakpoint(2)
    p.gutter.repaint()
    QCoreApplication.processEvents()
    kinds = ink()
    assert "dot" in kinds, "断点行未画出红点"
    assert "ink" in kinds, "行号数字被红点顶掉了"


def test_gutter_breakpoint_pauses_script_run(qapp):
    """行号槽点击 → 引擎断点 → 真实运行停在该行并高亮。"""
    from src.ui.extended_panels import ScriptEditorPanel

    p = ScriptEditorPanel(FakeSM())
    p.script_log.connect(p.append_log)
    p.code_edit.setPlainText('log_info("a")\nlog_info("b")')

    _press_gutter_at_line(p.gutter, p.code_edit, 2)
    p._run_script()

    assert p.engine is not None
    engine = p.engine
    assert _wait_for(lambda: engine.state.name == "BREAKPOINT"), "断点未命中"
    assert _wait_for(lambda: p.gutter.hit_line == 2), "命中行未高亮"

    p._resume_script()
    assert _wait_for(lambda: "脚本执行完毕" in p.output_text.toPlainText())


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
    time.sleep(0.7)  # 越过 sleep(0.5)
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
    def __init__(self, fields, raw=b"\x01\x02"):
        self.fields = fields
        self.protocol = "demo"
        self.timestamp = "10:00:00"
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

    body = bytes([1, 0x03, 2]) + struct.pack(">H", 500)
    frame = body + struct.pack("<H", CRC16.calculate(body))
    w.on_serial_data_received(frame)

    raw = w.chart.store.channel("bytes")
    register = w.chart.store.channel("r0")
    assert raw is not None and register is not None
    assert [float(v) for v in raw.snapshot()[1]] == [float(b) for b in frame]
    assert [float(v) for v in register.snapshot()[1]] == [500.0]

    seen: list = []
    monkeypatch.setattr(w.stream_parser, "feed", lambda data: [_FakeFrame({"temp": 21.5})])
    monkeypatch.setattr(w.chart, "feed_fields", lambda frames: seen.extend(frames))

    w._parse_protocol_data(b"x")
    assert [received.fields for received in seen] == [{"temp": 21.5}]


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

    worker = threading.Thread(target=lambda: on_data(b"\x01"))
    worker.start()
    worker.join()

    assert threads == [], "回调在工作线程里就直接动了控件"
    QCoreApplication.processEvents()
    assert threads == ["MainThread"], f"回调未编组到主线程: {threads}"


def test_theme_menu_switches_palette_and_stylesheet(qapp, monkeypatch, tmp_path):
    """回归：ThemeManager 曾是死代码，主窗口硬编码浅色 QSS，深色系统下标签白字白底"""
    from PyQt6.QtGui import QPalette

    from src.ui.main_window import SerialToolboxMainWindow
    from src.ui.theme_manager import ThemeMode

    w = SerialToolboxMainWindow()
    monkeypatch.setattr(w.config_mgr, "CONFIG_FILE", str(tmp_path / "cfg.json"))
    dark = w.theme_mgr.themes[ThemeMode.DARK]
    light = w.theme_mgr.themes[ThemeMode.LIGHT]

    def window_color():
        return w.palette().color(QPalette.ColorRole.Window).name().lower()

    def text_color():
        return w.palette().color(QPalette.ColorRole.WindowText).name().lower()

    w._select_theme(ThemeMode.DARK)
    assert window_color() == dark.background
    assert dark.text_primary in w.styleSheet()  # QSS 与调色板成套
    assert text_color() != window_color(), "文字与背景同色会不可见"

    w._select_theme(ThemeMode.LIGHT)
    assert window_color() == light.background
    assert light.text_primary in w.styleSheet()
    assert text_color() != window_color()

    checked = [m for m, a in w._theme_actions.items() if a.isChecked()]
    assert checked == [ThemeMode.LIGHT]


def test_theme_choice_is_persisted(qapp, monkeypatch, tmp_path):
    import json

    from src.ui.main_window import SerialToolboxMainWindow
    from src.ui.theme_manager import ThemeMode

    w = SerialToolboxMainWindow()
    monkeypatch.setattr(w.config_mgr, "CONFIG_FILE", str(tmp_path / "cfg.json"))

    w._select_theme(ThemeMode.LIGHT)
    saved = json.load(open(tmp_path / "cfg.json", encoding="utf-8"))
    assert saved["theme"] == "light"

    w._select_theme(ThemeMode.DARK)
    saved = json.load(open(tmp_path / "cfg.json", encoding="utf-8"))
    assert saved["theme"] == "dark"


def test_default_theme_is_dark(qapp):
    from src.core.config_manager import AppConfig

    assert AppConfig().theme == "dark"


def test_protocol_table_shows_every_field(qapp):
    """回归：一帧多字段时表格只显示第一个字段，其余值用户看不到"""
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    w.protocol_table.setRowCount(0)

    w._add_protocol_frame(_FakeFrame({"temp": 21.5, "hum": 60}))

    assert w.protocol_table.rowCount() == 2
    assert [(_cell(w.protocol_table, r, 2), _cell(w.protocol_table, r, 3)) for r in range(2)] == [
        ("temp", "21.5"),
        ("hum", "60"),
    ]
    assert _cell(w.protocol_table, 1, 4) == ""  # 原始数据只在首行显示


# ─── i18n ────────────────────────────────────────────────────


def test_translation_tables_have_identical_keys():
    """两张语言表键集合必须一致，否则切语言会漏译/串键"""
    from src.ui.i18n import TRANSLATIONS, Language

    zh_keys = set(TRANSLATIONS[Language.CHINESE])
    en_keys = set(TRANSLATIONS[Language.ENGLISH])
    assert zh_keys == en_keys


def test_i18n_tr_fallback_and_formatting():
    from src.ui.i18n import I18nManager, Language

    i18n = I18nManager()
    assert i18n.tr("menu_file") == "文件(&F)"
    assert i18n.tr("no_such_key") == "no_such_key"  # 缺键回退键名本身
    assert i18n.tr("status_connected", "COM3") == "已连接: COM3"

    i18n.set_language(Language.ENGLISH)
    assert i18n.tr("menu_file") == "File(&F)"
    assert i18n.tr("status_connected", "COM3") == "Connected: COM3"


def test_i18n_from_value_falls_back_to_chinese():
    from src.core.config_manager import AppConfig
    from src.ui.i18n import I18nManager, Language

    assert I18nManager.from_value("en").get_language() == Language.ENGLISH
    assert I18nManager.from_value("fr").get_language() == Language.CHINESE
    assert AppConfig().language == "zh"


def test_main_window_defaults_to_chinese(qapp):
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    assert w.file_menu is not None and w.settings_menu is not None
    assert w.windowTitle() == "串口调试助手 - Serial Toolbox v4.0"
    assert w.file_menu.title() == "文件(&F)"
    assert w.chart.collect_check.text() == "采集"
    assert w.script_panel.example_label.text() == "示例脚本:"


def test_main_window_english_from_config(qapp, monkeypatch, tmp_path):
    """配置里写 language=en 时，主窗口与常驻面板整体英文"""
    import json

    from src.ui.i18n import Language
    from src.ui.main_window import SerialToolboxMainWindow

    cfg_path = tmp_path / "cfg.json"
    cfg_path.write_text(json.dumps({"language": "en"}), encoding="utf-8")
    monkeypatch.setattr("src.core.config_manager.ConfigManager.CONFIG_FILE", str(cfg_path))

    w = SerialToolboxMainWindow()
    assert w.file_menu is not None and w.settings_menu is not None
    assert w.windowTitle() == "Serial Toolbox v4.0"
    assert w.file_menu.title() == "File(&F)"
    assert w.settings_menu.title() == "Settings(&S)"
    assert w.serial_group.title() == "Serial Configuration"
    assert w.receive_tabs.tabText(0) == "📝 Text"
    assert w.chart.collect_check.text() == "Collect"
    assert w.modbus_response_panel.auto_detect_label.text().startswith("Auto-detect")
    assert w.script_panel.run_btn.text().endswith("Run")
    assert w.compare_panel.clear_all_btn.text() == "Clear All"
    checked = [lang for lang, a in w._language_actions.items() if a.isChecked()]
    assert checked == [Language.ENGLISH]


def test_language_switch_retranslates_and_persists(qapp, monkeypatch, tmp_path):
    """回归：i18n 模块曾是死代码，UI 全文硬编码中文且无语言入口"""
    import json

    from src.ui.i18n import Language
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    monkeypatch.setattr(w.config_mgr, "CONFIG_FILE", str(tmp_path / "cfg.json"))

    w._select_language(Language.ENGLISH)
    assert w.windowTitle() == "Serial Toolbox v4.0"
    assert w.connect_btn.text() == "Connect"
    assert w.send_btn.text() == "Send"
    assert w.connection_label.text() == "Disconnected"
    saved = json.load(open(tmp_path / "cfg.json", encoding="utf-8"))
    assert saved["language"] == "en"

    w._select_language(Language.CHINESE)
    assert w.connect_btn.text() == "连接"
    assert w.send_btn.text() == "发送"
    saved = json.load(open(tmp_path / "cfg.json", encoding="utf-8"))
    assert saved["language"] == "zh"


def test_modbus_panel_func_combo_keeps_selection_on_retranslate(qapp):
    """切换语言重填下拉框时不能丢当前功能码"""
    from src.ui.i18n import I18nManager, Language
    from src.ui.main_window import ModbusPanel

    panel = ModbusPanel()
    panel.func_combo.setCurrentIndex(3)  # 0x10 写多个
    panel.retranslate_ui()
    assert panel.func_combo.currentIndex() == 3

    en = I18nManager(Language.ENGLISH)
    panel.i18n = en
    panel.retranslate_ui()
    assert panel.func_combo.currentIndex() == 3
    assert "Write Multiple" in panel.func_combo.currentText()
