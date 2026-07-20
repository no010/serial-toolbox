"""ScriptEngine 执行路径测试（回归：_run_script 曾引用未定义的 script）。"""
from src.core.script_engine import ScriptEngine, ScriptState


class FakeSerial:
    on_data_received = None

    def send(self, data):
        return True

    def send_text(self, data, fmt):
        return True


def test_execute_runs_without_nameerror():
    eng = ScriptEngine(FakeSerial())
    result = {}
    eng.on_finished = lambda ok, msg: result.update(ok=ok, msg=msg)

    eng.execute("x = 1\ny = x + 1")
    eng.thread.join(timeout=5)

    # 旧 bug：_run_script 使用未定义的 `script` → NameError → on_finished(False, ...)
    assert result.get("ok") is True, f"脚本执行失败: {result}"
    assert eng.state in (ScriptState.STOPPED, ScriptState.IDLE)


def test_execute_reports_script_error():
    eng = ScriptEngine(FakeSerial())
    result = {}
    eng.on_finished = lambda ok, msg: result.update(ok=ok, msg=msg)

    eng.execute("raise ValueError('boom')")
    eng.thread.join(timeout=5)

    assert result.get("ok") is False
    assert eng.state == ScriptState.ERROR


def test_execute_empty_script_is_ok():
    eng = ScriptEngine(FakeSerial())
    result = {}
    eng.on_finished = lambda ok, msg: result.update(ok=ok, msg=msg)

    eng.execute("")
    eng.thread.join(timeout=5)
    assert result.get("ok") is True
