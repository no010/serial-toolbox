"""ScriptEngine 执行路径测试。

回归覆盖：_run_script 曾引用未定义的 script；wait_response 曾整仓倒出导致残帧污染；
逐行 exec 曾让任何含缩进块的脚本以 unexpected indent 报错结束。
"""

import struct
import threading
import time

import pytest

from src.core.protocol_parser import CRC16, ModbusRTU
from src.core.script_engine import EXAMPLE_SCRIPTS, ScriptContext, ScriptEngine, ScriptState


class FakeSerial:
    on_data_received = None

    def send(self, data):
        return True

    def send_text(self, data, fmt):
        return True


def _run(
    script: str, serial: FakeSerial | None = None, *, join: bool = True, timeout: float = 30
) -> tuple[ScriptEngine, dict, list[str], threading.Thread]:
    """在脚本引擎线程里跑一段脚本，返回 (engine, on_finished 结果, 日志行, 脚本线程)。"""
    eng = ScriptEngine(serial or FakeSerial())
    logs: list[str] = []
    result: dict = {}
    eng.on_log = logs.append
    eng.on_finished = lambda ok, msg: result.update(ok=ok, msg=msg)

    eng.execute(script)
    assert eng.thread is not None, "execute() 应已启动脚本线程"
    if join:
        eng.thread.join(timeout=timeout)
    return eng, result, logs, eng.thread


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    """轮询等待引擎状态变化，返回最终是否满足。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _read_response(slave_addr: int, quantity: int, value: int = 0x1234) -> bytes:
    """组一帧功能码 0x03 的正常响应：地址 1 + 功能码 1 + 字节数 1 + 数据 2N + CRC16 2。"""
    body = bytes([slave_addr, 0x03, quantity * 2])
    body += struct.pack(f">{quantity}H", *([value] * quantity))
    return body + struct.pack("<H", CRC16.calculate(body))


def test_execute_runs_without_nameerror():
    eng, result, _, _ = _run("x = 1\ny = x + 1")

    # 旧 bug：_run_script 使用未定义的 `script` → NameError → on_finished(False, ...)
    assert result.get("ok") is True, f"脚本执行失败: {result}"
    assert eng.state in (ScriptState.STOPPED, ScriptState.IDLE)


def test_execute_reports_script_error():
    eng, result, _, _ = _run("raise ValueError('boom')")

    assert result.get("ok") is False
    assert eng.state == ScriptState.ERROR


def test_execute_empty_script_is_ok():
    _, result, _, _ = _run("")

    assert result.get("ok") is True


# ─── wait_response 长度语义（残帧污染回归）────────────────────


def _context():
    return ScriptContext(serial_manager=FakeSerial(), log=lambda m: None, sleep=lambda s: None)


def test_wait_response_returns_exact_length_and_keeps_remainder():
    """期望长度写小时，多收的帧尾必须留在缓冲区，而不是被混进返回值或静默吞掉。"""
    ctx = _context()
    frame = _read_response(1, 10)
    assert len(frame) == 25

    ctx.feed_response(frame)
    resp = ctx.wait_response(timeout=1.0, expected_length=23)

    assert resp == frame[:23]
    assert bytes(ctx.response_buffer) == frame[23:]


def test_residual_tail_survives_until_next_round():
    """写小的期望长度只会把帧尾推迟到下一轮，不会丢字节；clear_response 后帧头干净。"""
    ctx = _context()
    frame_a = _read_response(1, 10)
    frame_b = _read_response(2, 10)

    ctx.feed_response(frame_a)
    assert ctx.wait_response(timeout=1.0, expected_length=23) == frame_a[:23]
    assert bytes(ctx.response_buffer) == frame_a[23:]

    ctx.clear_response_buffer()  # 示例里每轮发送前的防御
    ctx.feed_response(frame_b)
    resp = ctx.wait_response(timeout=1.0, expected_length=25)

    assert resp == frame_b
    assert resp[0] == 2


def test_wait_response_keeps_extra_bytes_for_next_round():
    """超过期望长度的字节留给下一次等待，不能被静默吞掉。"""
    ctx = _context()
    ctx.feed_response(b"0123456789")

    assert ctx.wait_response(timeout=1.0, expected_length=4) == b"0123"
    assert ctx.wait_response(timeout=1.0, expected_length=6) == b"456789"


def test_wait_response_assembles_fragmented_frame():
    """帧分两片到达（USB 转串分片）时，仍返回完整帧且不留下残帧。"""
    ctx = _context()
    frame = _read_response(1, 10)

    ctx.feed_response(frame[:23])
    ctx.feed_response(frame[23:])
    resp = ctx.wait_response(timeout=1.0, expected_length=len(frame))

    assert resp == frame
    assert not ctx.response_buffer


def test_wait_response_timeout_returns_partial_data():
    ctx = _context()
    ctx.feed_response(b"12")

    assert ctx.wait_response(timeout=0.2, expected_length=10) == b"12"


def test_clear_response_buffer_drops_stale_bytes_before_next_send():
    ctx = _context()
    ctx.feed_response(b"\xaa\xbb")
    ctx.clear_response_buffer()

    assert ctx.wait_response(timeout=0.1, expected_length=2) == b""


# ─── 响应长度真值来源 ────────────────────────────────────────


def test_expected_response_length_matches_real_frames():
    for quantity in (1, 8, 10, 125):
        assert ModbusRTU.expected_response_length(0x03, quantity) == len(
            _read_response(1, quantity)
        )
        assert ModbusRTU.expected_response_length(0x04, quantity) == 5 + 2 * quantity


def test_expected_response_length_for_bit_and_write_functions():
    assert ModbusRTU.expected_response_length(0x01, 16) == 7  # 16 位 = 2 字节数据
    assert ModbusRTU.expected_response_length(0x02, 9) == 7  # 9 位按字节向上取整
    for write_fc in (0x05, 0x06, 0x0F, 0x10):
        assert ModbusRTU.expected_response_length(write_fc) == 8  # 写响应固定回显 8 字节


def test_expected_response_length_rejects_unknown_function_code():
    with pytest.raises(ValueError):
        ModbusRTU.expected_response_length(0x40)


# ─── 内置示例端到端回归 ──────────────────────────────────────


class _FragmentingSlaveSerial(FakeSerial):
    """从机模拟器：应答分两片写回，尾片延迟到达，复现串口分片边界。"""

    def __init__(self, tail_delay: float = 0.03):
        self.on_data_received = None
        self.tail_delay = tail_delay

    def send(self, data):
        frame = _read_response(data[0], data[5] | (data[4] << 8))
        self._emit(frame[:23])
        threading.Timer(self.tail_delay, self._emit, args=(frame[23:],)).start()
        return True

    def _emit(self, chunk: bytes):
        if self.on_data_received:
            self.on_data_received(chunk)


def test_builtin_modbus_polling_example_survives_fragmented_frames():
    """回归：内置示例的期望长度写死成 23 时，尾片串到下一轮会把好设备判成失联。"""
    _, result, logs, _ = _run(EXAMPLE_SCRIPTS["Modbus 轮询"], _FragmentingSlaveSerial())

    assert result.get("ok") is True, f"示例未能正常结束: {result}"
    assert len([line for line in logs if "正常:" in line]) == 5, f"轮询日志异常: {logs}"
    assert not [line for line in logs if "失联" in line or "异常码" in line]


@pytest.mark.parametrize("name", ["AT 指令测试", "响应解析"])
def test_builtin_examples_finish_cleanly(name):
    """「断点调试示例」等待人工恢复，不在自动回归范围内。"""
    _, result, logs, _ = _run(EXAMPLE_SCRIPTS[name])

    assert result.get("ok") is True, f"{name} 失败: {result} {logs}"


# ─── 顶层语句切分（缩进块执行回归）───────────────────────────


def test_for_loop_body_executes_once_and_script_finishes_ok():
    """回归：逐行 exec 回退收集块后，外层循环会重复处理块内缩进行，脚本以 unexpected indent 收尾。"""
    script = 'counter = 0\nfor i in range(3):\n    counter += 1\n    log_info("tick")\nlog_success("done")'
    _, result, logs, _ = _run(script)

    assert result.get("ok") is True, f"脚本失败: {result}"
    assert len([line for line in logs if "tick" in line]) == 3
    assert any("done" in line for line in logs)


def test_script_can_define_and_call_function():
    script = 'def double(x):\n    return x * 2\n\nlog_info(f"result={double(21)}")'
    _, result, logs, _ = _run(script)

    assert result.get("ok") is True, f"脚本失败: {result}"
    assert any("result=42" in line for line in logs)


def test_multiline_expression_statement():
    script = 'log_info(\n    "wrapped"\n)\nlog_info("after")'
    _, result, logs, _ = _run(script)

    assert result.get("ok") is True, f"脚本失败: {result}"
    assert any("wrapped" in line for line in logs)
    assert any("after" in line for line in logs)


def test_runtime_error_reports_absolute_script_line():
    """单元源码补齐了前导空行，报错行号应能直接对照脚本编辑器。"""
    script = 'x = 1\nfor i in range(2):\n    raise ValueError("boom")\n'
    _, result, _, _ = _run(script)

    assert result.get("ok") is False
    assert "第 3 行" in result.get("msg", ""), f"错误信息缺少行号: {result}"


def test_breakpoint_inside_block_hits_and_resumes():
    """回归：断点命中后状态未切换，resume() 只认 PAUSED 而拒绝唤醒，脚本永久卡在块前。"""
    eng, result, logs, thread = _run(
        'set_breakpoint(3)\nfor i in range(2):\n    log_info("tick")', join=False
    )

    assert _wait_until(lambda: eng.state == ScriptState.BREAKPOINT), f"块内断点未命中: {logs}"

    eng.resume()
    thread.join(timeout=5)

    assert result.get("ok") is True, f"恢复后执行失败: {result}"
    assert len([line for line in logs if "tick" in line]) == 2


def test_stop_releases_script_paused_at_breakpoint():
    """回归：脚本停在断点上时 stop() 必须能解除阻塞，否则线程永不退出。"""
    eng, result, logs, thread = _run('set_breakpoint(2)\nlog_info("never")', join=False)

    assert _wait_until(lambda: eng.state == ScriptState.BREAKPOINT), f"断点未命中: {logs}"

    eng.stop()
    thread.join(timeout=5)

    assert not eng.is_running(), "stop() 未能解除断点阻塞"
    assert result.get("ok") is False, f"被停止的脚本不该报成功: {result}"
    assert "已被用户停止" in result.get("msg", ""), f"停止原因未回传: {result}"


def test_stop_mid_script_is_not_reported_as_success():
    script = 'for i in range(200):\n    log_info(f"tick {i}")\n    sleep(0.02)'
    eng, result, logs, thread = _run(script, join=False)

    assert _wait_until(lambda: len([line for line in logs if "tick" in line]) >= 2)
    eng.stop()
    thread.join(timeout=5)

    assert not eng.is_running(), "stop() 未能终止循环脚本"
    assert result.get("ok") is False, f"被停止的脚本不该报成功: {result}"
    assert "已被用户停止" in result.get("msg", ""), f"停止原因未回传: {result}"


# ─── 手动暂停与单步 ──────────────────────────────────────────

# 拆成多条顶层语句，中间用 sleep 留出可观测的时间窗
STEPPABLE_SCRIPT = 'log_info("s1")\nsleep(0.2)\nlog_info("s2")\nsleep(0.2)\nlog_info("s3")\n'


def test_pause_holds_script_at_statement_boundary():
    """回归：pause() 此前只清标志位、执行循环从不等待，脚本照跑到底。"""
    eng, result, logs, thread = _run(STEPPABLE_SCRIPT, join=False)
    assert _wait_until(lambda: any("s1" in line for line in logs))

    eng.pause()
    time.sleep(0.5)  # 足以跨过 s2 前的 sleep(0.2)
    assert not any("s2" in line for line in logs), f"pause() 未生效: {logs}"
    assert eng.state == ScriptState.PAUSED

    eng.resume()
    thread.join(timeout=5)

    assert result.get("ok") is True, f"恢复后执行失败: {result}"
    assert all(any(k in line for line in logs) for k in ("s1", "s2", "s3"))


def test_step_over_runs_one_statement_then_pauses():
    eng, result, logs, thread = _run(STEPPABLE_SCRIPT, join=False)
    assert _wait_until(lambda: eng.get_current_line() > 0)

    eng.step_over()
    assert _wait_until(lambda: eng.state == ScriptState.PAUSED), "单步后未停在语句边界"
    assert any("s1" in line for line in logs), f"单步应至少执行完当前语句: {logs}"
    assert not any("s2" in line for line in logs), f"单步多跑了: {logs}"

    eng.step_over()
    assert _wait_until(lambda: any("s2" in line for line in logs))
    assert _wait_until(lambda: eng.state == ScriptState.PAUSED)

    eng.resume()
    thread.join(timeout=5)

    assert result.get("ok") is True, f"恢复后执行失败: {result}"
