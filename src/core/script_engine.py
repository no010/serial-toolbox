"""
脚本引擎
支持 Python 脚本自动化测试序列
"""

import sys
import io
import threading
import traceback
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime


class ScriptState(Enum):
    """脚本状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class ScriptContext:
    """脚本执行上下文 - 提供给脚本的 API"""
    serial_manager: Any  # SerialManager 实例
    log: Callable[[str], None]  # 日志输出回调
    sleep: Callable[[float], None]  # 睡眠函数
    stop_flag: threading.Event = field(default_factory=threading.Event)
    
    def send(self, data: str, hex_mode: bool = False) -> bool:
        """发送数据"""
        from src.core.serial_manager import DataFormat
        fmt = DataFormat.HEX if hex_mode else DataFormat.ASCII
        return self.serial_manager.send_text(data, fmt)
    
    def send_bytes(self, data: bytes) -> bool:
        """发送原始字节"""
        return self.serial_manager.send(data)
    
    def wait_response(self, timeout: float = 1.0) -> bytes:
        """等待响应 (简单实现)"""
        import time
        received = bytearray()
        start = time.time()
        while time.time() - start < timeout:
            if self.stop_flag.is_set():
                break
            time.sleep(0.01)
        # 注意: 实际实现需要在 SerialManager 中添加响应缓冲
        return bytes(received)
    
    def assert_equal(self, actual, expected, msg: str = ""):
        """断言相等"""
        if actual != expected:
            raise AssertionError(f"{msg}: 期望 {expected}, 实际 {actual}")
    
    def log_info(self, msg: str):
        """输出信息"""
        self.log(f"[INFO] {msg}")
    
    def log_error(self, msg: str):
        """输出错误"""
        self.log(f"[ERROR] {msg}")
    
    def log_success(self, msg: str):
        """输出成功"""
        self.log(f"[OK] {msg}")


class ScriptEngine:
    """Python 脚本引擎"""
    
    def __init__(self, serial_manager):
        self.serial_manager = serial_manager
        self.state = ScriptState.IDLE
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初始非暂停状态
        
        self.on_log: Optional[Callable[[str], None]] = None
        self.on_state_changed: Optional[Callable[[ScriptState], None]] = None
        self.on_finished: Optional[Callable[[bool, str], None]] = None
        
        self._current_script: str = ""
        self._result_msg: str = ""
    
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
        self.pause_event.set()
        
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
            ctx = ScriptContext(
                serial_manager=self.serial_manager,
                log=self._log,
                sleep=self._interruptible_sleep,
                stop_flag=self.stop_event
            )
            
            # 构建脚本环境
            script_env = {
                'ctx': ctx,
                'send': ctx.send,
                'send_bytes': ctx.send_bytes,
                'sleep': ctx.sleep,
                'log': ctx.log_info,
                'log_info': ctx.log_info,
                'log_error': ctx.log_error,
                'log_success': ctx.log_success,
                'assert_equal': ctx.assert_equal,
                'stop': self.stop,
            }
            
            # 执行脚本
            exec(self._current_script, script_env)
            
            success = True
            self._log("脚本执行完成")
            
        except Exception as e:
            error_msg = str(e)
            self._log(f"脚本执行错误: {e}")
            traceback.print_exc()
            self._set_state(ScriptState.ERROR)
        
        self._result_msg = error_msg if not success else "执行成功"
        
        if self.on_finished:
            self.on_finished(success, self._result_msg)
        
        if self.state != ScriptState.ERROR:
            self._set_state(ScriptState.STOPPED)
    
    def _interruptible_sleep(self, seconds: float):
        """可中断的睡眠"""
        import time
        end_time = time.time() + seconds
        while time.time() < end_time:
            if self.stop_event.is_set():
                raise InterruptedError("脚本已停止")
            if not self.pause_event.is_set():
                # 暂停中，等待恢复
                self.pause_event.wait(timeout=0.1)
            else:
                time.sleep(0.01)
    
    def stop(self):
        """停止脚本"""
        self.stop_event.set()
        self.pause_event.set()  # 确保不会卡在暂停
        self._log("脚本已停止")
    
    def pause(self):
        """暂停脚本"""
        if self.state == ScriptState.RUNNING:
            self.pause_event.clear()
            self._set_state(ScriptState.PAUSED)
            self._log("脚本已暂停")
    
    def resume(self):
        """恢复脚本"""
        if self.state == ScriptState.PAUSED:
            self.pause_event.set()
            self._set_state(ScriptState.RUNNING)
            self._log("脚本已恢复")
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.state == ScriptState.RUNNING
    
    def get_state(self) -> ScriptState:
        """获取状态"""
        return self.state


# ─── 示例脚本模板 ────────────────────────────────────────────

EXAMPLE_SCRIPTS = {
    "AT 指令测试": '''# AT 指令测试脚本
log_info("开始 AT 指令测试")

# 发送 AT 指令
send("AT")
sleep(0.5)

# 发送查询版本
send("AT+VERSION")
sleep(0.5)

# 发送查询信号
send("AT+CSQ")
sleep(0.5)

log_success("AT 测试完成")
''',
    
    "Modbus 轮询": '''# Modbus 轮询脚本
log_info("开始 Modbus 轮询")

# 构建 Modbus 读寄存器请求 (从机1, 地址0, 数量10)
import struct
from src.core.protocol_parser import ModbusRTU

for i in range(5):
    # 发送读请求
    frame = ModbusRTU.build_read_holding_registers(1, 0, 10)
    send_bytes(frame)
    log_info(f"发送轮询请求 #{i+1}")
    
    # 等待响应
    sleep(1.0)

log_success("Modbus 轮询完成")
''',
    
    "循环测试": '''# 循环测试脚本
log_info("开始循环测试")

for i in range(10):
    send(f"TEST_{i}")
    log_info(f"发送测试数据 #{i}")
    sleep(0.5)
    
    # 检查停止标志
    if stop.is_set():
        log_info("用户停止")
        break

log_success("循环测试完成")
''',
}
