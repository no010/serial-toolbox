"""UI 面板测试（offscreen Qt）：覆盖此前导致启动崩溃的 ScriptEditorPanel 重写。"""
import pytest
from PyQt6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


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

    class FakeSM:
        on_data_received = None

    p = ScriptEditorPanel(FakeSM())
    assert p.engine is not None and callable(p.engine.on_log)  # _on_engine_log 缺失已修复
    p.script_log.connect(p.append_log)
    p.engine.on_log("from-engine")
    assert "from-engine" in p.output_text.toPlainText()


def test_main_window_constructs(qapp):
    # 端到端：主窗口构造会触发 main_window 中 script_log → append_log 的连接
    from src.ui.main_window import SerialToolboxMainWindow

    w = SerialToolboxMainWindow()
    assert w is not None
