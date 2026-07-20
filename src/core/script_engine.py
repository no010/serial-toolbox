"""
脚本引擎 v2
支持 wait_response()、断点调试、更丰富的 API
"""

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


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
                      terminator: bytes = None) -> bytes:
        """
        等待响应数据

        Args:
            timeout: 超时时间 (秒)
            expected_length: 期望接收的字节数 (0=任意)
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

    def check_breakpoint(self, line: int):
        """检查是否命中断点"""
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

                self.log(f"[断点] 命中第 {line} 行断点")
                self.pause_flag.clear()
                self.step_mode = True
                # 进入断点暂停状态
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

        try:
            # 创建脚本上下文
            self._context = ScriptContext(
                serial_manager=self.serial_manager,
                log=self._log,
                sleep=self._interruptible_sleep,
                stop_flag=self.stop_event
            )

            # 连接响应数据
            original_callback = self.serial_manager.on_data_received
            def data_callback(data):
                self._context.feed_response(data)
                if original_callback:
                    original_callback(data)
            self.serial_manager.on_data_received = data_callback

            # 构建脚本环境
            script_env = {
                'ctx': self._context,
                'send': self._context.send,
                'send_bytes': self._context.send_bytes,
                'sleep': self._context.sleep,
                'wait_response': self._context.wait_response,
                'clear_response': self._context.clear_response_buffer,
                'log': self._context.log_info,
                'log_info': self._context.log_info,
                'log_error': self._context.log_error,
                'log_success': self._context.log_success,
                'log_debug': self._context.log_debug,
                'assert_equal': self._context.assert_equal,
                'assert_contains': self._context.assert_contains,
                'set_breakpoint': self._context.set_breakpoint,
                'remove_breakpoint': self._context.remove_breakpoint,
                'stop': self.stop,
            }

            # 逐行执行以支持断点
            lines = self._current_script.split('\n')
            for line_num, line in enumerate(lines, 1):
                if self.stop_event.is_set():
                    break

                # 检查断点
                self._context.current_line = line_num
                self._context.check_breakpoint(line_num)

                if self.on_line_executed:
                    self.on_line_executed(line_num)

                # 跳过空行和注释
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue

                # 执行当前行
                try:
                    exec(line, script_env)
                except IndentationError:
                    # 多行语句，收集完整块
                    block = line
                    while line_num < len(lines):
                        line_num += 1
                        line = lines[line_num - 1]
                        block += '\n' + line
                        # 简单判断块结束
                        if line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                            break
                    exec(block, script_env)

            success = True
            self._log("脚本执行完成")

        except InterruptedError:
            self._log("脚本被用户停止")
        except Exception as e:
            error_msg = str(e)
            self._log(f"脚本执行错误: {e}")
            traceback.print_exc()
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
        """恢复脚本"""
        if self._context and self.state == ScriptState.PAUSED:
            self._context.pause_flag.set()
            self._set_state(ScriptState.RUNNING)
            self._log("脚本已恢复")

    def step_over(self):
        """单步执行"""
        if self._context:
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
log_info("开始 Modbus 轮询")

from src.core.protocol_parser import ModbusRTU

for i in range(5):
    # 发送读请求
    frame = ModbusRTU.build_read_holding_registers(1, 0, 10)
    send_bytes(frame)
    log_info(f"发送轮询请求 #{i+1}")

    # 等待响应
    resp = wait_response(timeout=1.0, expected_length=23)
    if resp:
        log_success(f"收到响应: {len(resp)} 字节")
    else:
        log_error("响应超时")

    sleep(0.5)

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
