"""
脚本引擎 v2
支持 wait_response()、断点调试、更丰富的 API
"""

import ast
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ScriptState(Enum):
    """脚本状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    BREAKPOINT = "breakpoint"  # 断点暂停


@dataclass
class Breakpoint:
    """断点"""
    line: int
    enabled: bool = True
    condition: str = ""  # 可选条件表达式


@dataclass(frozen=True)
class _StatementUnit:
    """脚本中的一个顶层语句单元（连同其缩进块），exec 与断点的最小粒度"""
    start_line: int
    end_line: int
    source: str  # 语句源码，前面补齐空行使 compile 出的行号与脚本绝对行号一致


def _split_top_level_units(script: str) -> list[_StatementUnit]:
    """
    用 AST 按顶层语句切分脚本。

    缩进块（for/if/while/def/with）必须整体交给 exec 才能运行，块内单行单独 exec
    只会抛 IndentationError，因此顶层语句就是可行的最小执行与断点粒度。
    """
    lines = script.splitlines()
    units: list[_StatementUnit] = []
    for node in ast.parse(script, filename='<script>').body:
        start = node.lineno
        decorators = getattr(node, 'decorator_list', [])
        if decorators:
            start = min(start, min(d.lineno for d in decorators))
        end = node.end_lineno or start
        source = '\n' * (start - 1) + '\n'.join(lines[start - 1:end])
        units.append(_StatementUnit(start, end, source))
    return units


def _script_line_hint(exc: BaseException) -> str:
    """取脚本自身帧的行号拼进错误信息；行号已按脚本对齐，可直接对照编辑器"""
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == '<script>':
            return f" (第 {tb.tb_lineno} 行)"
        tb = tb.tb_next
    if isinstance(exc, SyntaxError) and exc.lineno:
        return f" (第 {exc.lineno} 行)"
    return ""


@dataclass
class ScriptContext:
    """脚本执行上下文 - 提供给脚本的 API"""
    serial_manager: Any
    log: Callable[[str], None]
    sleep: Callable[[float], None]
    stop_flag: threading.Event = field(default_factory=threading.Event)

    # 响应缓冲区
    response_buffer: bytearray = field(default_factory=bytearray)
    response_lock: threading.Lock = field(default_factory=threading.Lock)

    # 断点相关
    breakpoints: dict[int, Breakpoint] = field(default_factory=dict)
    current_line: int = 0
    pause_flag: threading.Event = field(default_factory=threading.Event)
    step_mode: bool = False

    def send(self, data: str, hex_mode: bool = False) -> bool:
        """发送数据"""
        from src.core.serial_manager import DataFormat
        fmt = DataFormat.HEX if hex_mode else DataFormat.ASCII
        return self.serial_manager.send_text(data, fmt)

    def send_bytes(self, data: bytes) -> bool:
        """发送原始字节"""
        return self.serial_manager.send(data)

    def feed_response(self, data: bytes):
        """喂入响应数据 (由外部调用)"""
        with self.response_lock:
            self.response_buffer.extend(data)

    def wait_response(self, timeout: float = 1.0, expected_length: int = 0,
                      terminator: bytes | None = None) -> bytes:
        """
        等待响应数据

        Args:
            timeout: 超时时间 (秒)
            expected_length: 期望接收的字节数 (0=任意)。满足时返回值恰好为该长度，
                多收到的字节留在缓冲区由下一次等待取走；仅超时时返回已收到的部分。
            terminator: 结束标志字节 (如 b'\\r\\n')

        Returns:
            接收到的数据
        """
        start_time = time.time()
        result = bytearray()

        while time.time() - start_time < timeout:
            if self.stop_flag.is_set():
                raise InterruptedError("脚本已停止")

            with self.response_lock:
                if self.response_buffer:
                    result.extend(self.response_buffer)
                    self.response_buffer.clear()

                    # 检查是否满足条件
                    if expected_length > 0 and len(result) >= expected_length:
                        # 多收的字节放回缓冲区交给下一次等待，避免帧尾被吞或混进后续帧
                        if len(result) > expected_length:
                            self.response_buffer.extend(result[expected_length:])
                            del result[expected_length:]
                        return bytes(result)
                    if terminator and terminator in result:
                        return bytes(result)
                    if expected_length == 0 and terminator is None:
                        # 没有指定条件，等待一小段时间看是否还有数据
                        time.sleep(0.05)
                        with self.response_lock:
                            if self.response_buffer:
                                continue
                        return bytes(result)

            time.sleep(0.01)

        # 超时返回已接收的数据
        return bytes(result)

    def clear_response_buffer(self):
        """清空响应缓冲区"""
        with self.response_lock:
            self.response_buffer.clear()

    def assert_equal(self, actual, expected, msg: str = ""):
        """断言相等"""
        if actual != expected:
            raise AssertionError(f"{msg}: 期望 {expected}, 实际 {actual}")

    def assert_contains(self, data: bytes, pattern: bytes, msg: str = ""):
        """断言包含"""
        if pattern not in data:
            raise AssertionError(f"{msg}: 数据中未找到 {pattern}")

    def log_info(self, msg: str):
        """输出信息"""
        self.log(f"[INFO] {msg}")

    def log_error(self, msg: str):
        """输出错误"""
        self.log(f"[ERROR] {msg}")

    def log_success(self, msg: str):
        """输出成功"""
        self.log(f"[OK] {msg}")

    def log_debug(self, msg: str):
        """输出调试信息"""
        self.log(f"[DEBUG] {msg}")

    # ─── 断点控制 ────────────────────────────────────────────

    def set_breakpoint(self, line: int, condition: str = ""):
        """设置断点"""
        self.breakpoints[line] = Breakpoint(line=line, condition=condition)
        self.log(f"[断点] 在第 {line} 行设置断点")

    def remove_breakpoint(self, line: int):
        """移除断点"""
        if line in self.breakpoints:
            del self.breakpoints[line]
            self.log(f"[断点] 移除第 {line} 行断点")

    def check_breakpoint(self, line: int, on_pause: Callable[[], None] | None = None):
        """
        检查是否命中断点，命中则阻塞到被唤醒。

        on_pause 在真正进入等待前回调（引擎据此切换状态），未命中时不会被调用。
        """
        if line in self.breakpoints:
            bp = self.breakpoints[line]
            if bp.enabled:
                # 检查条件
                if bp.condition:
                    try:
                        if not eval(bp.condition, {'ctx': self}):
                            return
                    except Exception:
                        pass

                self.pause_flag.clear()
                self.step_mode = True
                if on_pause:
                    on_pause()
                # clear 必须先于该日志：外部以这条日志为信号调用 resume()，
                # 若 set 落在 clear 之前会被抹掉，脚本将永久停在 wait()
                self.log(f"[断点] 命中第 {line} 行断点")
                self.pause_flag.wait()

    def step(self):
        """单步执行"""
        self.step_mode = True
        self.pause_flag.set()

    def continue_execution(self):
        """继续执行"""
        self.step_mode = False
        self.pause_flag.set()


class ScriptEngine:
    """Python 脚本引擎 v2"""

    def __init__(self, serial_manager):
        self.serial_manager = serial_manager
        self.state = ScriptState.IDLE
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        self.on_log: Callable[[str], None] | None = None
        self.on_state_changed: Callable[[ScriptState], None] | None = None
        self.on_finished: Callable[[bool, str], None] | None = None
        self.on_breakpoint: Callable[[int], None] | None = None
        self.on_line_executed: Callable[[int], None] | None = None

        self._current_script: str = ""
        self._result_msg: str = ""
        self._context: ScriptContext | None = None

    def _set_state(self, state: ScriptState):
        """设置状态"""
        self.state = state
        if self.on_state_changed:
            self.on_state_changed(state)

    def _log(self, msg: str):
        """输出日志"""
        ts = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        full_msg = f"[{ts}] {msg}"
        if self.on_log:
            self.on_log(full_msg)

    def execute(self, script: str):
        """执行脚本"""
        if self.state == ScriptState.RUNNING:
            self._log("脚本正在运行中")
            return

        self._current_script = script
        self.stop_event.clear()

        self.thread = threading.Thread(target=self._run_script, daemon=True)
        self.thread.start()

    def _run_script(self):
        """运行脚本线程"""
        self._set_state(ScriptState.RUNNING)
        self._log("脚本开始执行")

        success = False
        error_msg = ""
        original_callback = None  # 在 try 外初始化，保证 finally 中可安全引用

        try:
            # 创建脚本上下文
            context = ScriptContext(
                serial_manager=self.serial_manager,
                log=self._log,
                sleep=self._interruptible_sleep,
                stop_flag=self.stop_event
            )
            context.pause_flag.set()      # 未暂停是初态，闸门才不会一开始就挡住脚本
            self._context = context

            # 连接响应数据
            original_callback = self.serial_manager.on_data_received
            def data_callback(data):
                context.feed_response(data)
                if original_callback:
                    original_callback(data)
            self.serial_manager.on_data_received = data_callback

            # 构建脚本环境
            script_env = {
                'ctx': context,
                'send': context.send,
                'send_bytes': context.send_bytes,
                'sleep': context.sleep,
                'wait_response': context.wait_response,
                'clear_response': context.clear_response_buffer,
                'log': context.log_info,
                'log_info': context.log_info,
                'log_error': context.log_error,
                'log_success': context.log_success,
                'log_debug': context.log_debug,
                'assert_equal': context.assert_equal,
                'assert_contains': context.assert_contains,
                'set_breakpoint': context.set_breakpoint,
                'remove_breakpoint': context.remove_breakpoint,
                'stop': self.stop,
            }

            # 按顶层语句逐个执行：缩进块必须整体交给 exec，块内单行无法独立运行
            for unit in _split_top_level_units(self._current_script):
                if self.stop_event.is_set():
                    break

                context.current_line = unit.start_line
                self._wait_for_resume(context)
                self._hit_breakpoint(context, unit)

                if self.on_line_executed:
                    self.on_line_executed(unit.start_line)

                exec(compile(unit.source, '<script>', 'exec'), script_env)
                self._step_after_unit(context)

            # stop() 会让上面的循环 break 出来，不能随后又报"执行成功"
            if self.stop_event.is_set():
                raise InterruptedError("脚本已停止")

            success = True
            self._log("脚本执行完成")

        except InterruptedError:
            error_msg = "已被用户停止"
            self._log("脚本被用户停止")
        except Exception as e:
            error_msg = f"{e}{_script_line_hint(e)}"
            self._log(f"脚本执行错误: {error_msg}")
            logger.exception("脚本执行异常")
            self._set_state(ScriptState.ERROR)

        finally:
            # 恢复原始回调
            if original_callback:
                self.serial_manager.on_data_received = original_callback

        self._result_msg = error_msg if not success else "执行成功"

        if self.on_finished:
            self.on_finished(success, self._result_msg)

        if self.state != ScriptState.ERROR:
            self._set_state(ScriptState.STOPPED)

    def _wait_for_resume(self, context: ScriptContext):
        """手动暂停时停在语句边界，直到恢复或被停止"""
        while not context.pause_flag.wait(0.05):
            if self.stop_event.is_set():
                raise InterruptedError("脚本已停止")
            if self.state == ScriptState.RUNNING:
                self._set_state(ScriptState.PAUSED)

    def _step_after_unit(self, context: ScriptContext):
        """单步：本条顶层语句执行完就停在下一条之前"""
        if context.step_mode:
            context.step_mode = False
            context.pause_flag.clear()
            self._set_state(ScriptState.PAUSED)

    def _hit_breakpoint(self, context: ScriptContext, unit: _StatementUnit):
        """
        命中该顶层语句行号范围内的第一个断点。

        缩进块只能整体交给 exec，所以块内的断点是在整块开始执行前停下，而非逐行停下。
        """
        for line in range(unit.start_line, unit.end_line + 1):
            if line in context.breakpoints:
                context.current_line = line
                context.check_breakpoint(
                    line, lambda paused=line: self._pause_at_breakpoint(paused))
                if self.state == ScriptState.BREAKPOINT:
                    self._set_state(ScriptState.RUNNING)
                return

    def _pause_at_breakpoint(self, line: int):
        """进入断点等待前通知外部并把状态切出去，否则 resume() 认不出这是可恢复的暂停"""
        self._set_state(ScriptState.BREAKPOINT)
        if self.on_breakpoint:
            self.on_breakpoint(line)

    def _interruptible_sleep(self, seconds: float):
        """可中断的睡眠"""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self.stop_event.is_set():
                raise InterruptedError("脚本已停止")
            time.sleep(0.01)

    def stop(self):
        """停止脚本"""
        self.stop_event.set()
        if self._context:
            self._context.pause_flag.set()
        self._log("脚本已停止")

    def pause(self):
        """暂停脚本"""
        if self._context and self.state == ScriptState.RUNNING:
            self._context.pause_flag.clear()
            self._set_state(ScriptState.PAUSED)
            self._log("脚本已暂停")

    def resume(self):
        """恢复脚本（手动暂停、单步停下或停在断点上都可恢复）"""
        if self._context and self.state in (ScriptState.PAUSED, ScriptState.BREAKPOINT):
            self._context.continue_execution()   # 同时退出单步模式
            self._set_state(ScriptState.RUNNING)
            self._log("脚本已恢复")

    def step_over(self):
        """单步执行"""
        if self._context and self.state in (
            ScriptState.RUNNING, ScriptState.PAUSED, ScriptState.BREAKPOINT
        ):
            self._context.step()
            self._set_state(ScriptState.RUNNING)

    def is_running(self) -> bool:
        """是否正在运行"""
        return self.state == ScriptState.RUNNING

    def get_state(self) -> ScriptState:
        """获取状态"""
        return self.state

    def get_current_line(self) -> int:
        """获取当前执行行号"""
        if self._context:
            return self._context.current_line
        return 0


# ─── 示例脚本模板 ────────────────────────────────────────────

EXAMPLE_SCRIPTS = {
    "AT 指令测试": '''# AT 指令测试脚本
log_info("开始 AT 指令测试")

# 发送 AT 指令
send("AT")
resp = wait_response(timeout=0.5)
log_info(f"响应: {resp}")

# 发送查询版本
send("AT+VERSION")
resp = wait_response(timeout=0.5)
log_info(f"版本: {resp}")

# 发送查询信号
send("AT+CSQ")
resp = wait_response(timeout=0.5)
log_info(f"信号: {resp}")

log_success("AT 测试完成")
''',

    "Modbus 轮询": '''# Modbus 轮询脚本
from src.core.protocol_parser import ModbusFunction, ModbusRTU

SLAVE = 1
START_ADDR = 0
N_REGS = 10
EXC_LEN = 5  # 异常响应恒为 5 字节
# 正常响应长度 = 5 + 2N，用公式算出来，不要写死字面量
expected = ModbusRTU.expected_response_length(ModbusFunction.READ_HOLDING_REGISTERS.value, N_REGS)

log_info(f"开始 Modbus 轮询: 从机 {SLAVE}, {N_REGS} 个保持寄存器, 期望 {expected} 字节")

for i in range(5):
    # 丢弃上一轮的残帧，避免它的尾部污染这一轮的帧头
    clear_response()

    frame = ModbusRTU.build_read_holding_registers(SLAVE, START_ADDR, N_REGS)
    send_bytes(frame)

    # 等待响应：长度写足，超时压短，异常/失联设备不会白等
    resp = wait_response(timeout=0.3, expected_length=expected)

    if len(resp) == EXC_LEN and resp[1] & 0x80:
        log_error(f"轮询 #{i+1} 从机返回异常码 {resp[2]} (在线但拒绝)")
    elif len(resp) == expected and resp[0] == SLAVE:
        regs = ModbusRTU.registers_to_values(resp[3:-2])
        log_success(f"轮询 #{i+1} 正常: {regs}")
    else:
        log_error(f"轮询 #{i+1} 响应不完整 ({len(resp)}/{expected}), 从机可能失联")

    sleep(0.2)

log_success("Modbus 轮询完成")
''',

    "断点调试示例": '''# 断点调试示例
log_info("开始调试")

for i in range(10):
    send(f"DATA_{i}")
    log_info(f"发送 #{i}")

    # 在第5次循环时设置断点
    if i == 5:
        log_info("即将进入断点...")
        # 手动暂停，可以在这里检查变量
        ctx.pause_flag.clear()
        ctx.pause_flag.wait()

    sleep(0.3)

log_success("调试完成")
''',

    "响应解析": '''# 响应解析示例
log_info("开始响应解析测试")

# 发送查询命令
send("QUERY:TEMP?")
resp = wait_response(timeout=1.0)

if b"OK" in resp:
    log_success("设备响应正常")
    # 解析温度值
    try:
        temp_str = resp.decode().split(":")[1].strip()
        temp = float(temp_str)
        log_info(f"温度: {temp}°C")
    except:
        log_error("解析失败")
else:
    log_error("设备未响应或错误")

log_success("测试完成")
''',
}
