"""真机回环替身：pyserial 传输 + SerialManager 读线程 + 脚本引擎的端到端集成测试。

没有硬件时用 socket:// 传输代替 UART：应答由 TCP 服务端分两片写出，
配合 SerialManager._read_loop 的轮询，帧会以非整帧的碎片到达 wait_response，
正是"USB 转串分片 + 期望长度写错"引发残帧串台的现实条件。
"""
import socket
import struct
import threading

import pytest
import serial

from src.core.protocol_parser import CRC16
from src.core.script_engine import EXAMPLE_SCRIPTS, ScriptEngine
from src.core.serial_manager import SerialManager

TAIL_DELAY = 0.03           # 尾片延迟：模拟波特率造成的分片间隔
QUANTITY = 10


def _frame(slave_addr: int, quantity: int, value: int = 0x1234) -> bytes:
    """功能码 0x03 的正常响应：5 + 2N 字节"""
    body = bytes([slave_addr, 0x03, quantity * 2])
    body += struct.pack(f'>{quantity}H', *([value] * quantity))
    return body + struct.pack('<H', CRC16.calculate(body))


class _RtuSlaveServer:
    """TCP 上的 Modbus RTU 从机替身：收到请求后把 25 字节应答分两片写回。"""

    def __init__(self):
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(('127.0.0.1', 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        try:
            conn, _ = self._listener.accept()
        except OSError:
            return
        buf = bytearray()
        with conn:
            conn.settimeout(0.5)
            while not self._stop.is_set():
                try:
                    chunk = conn.recv(64)
                except TimeoutError:
                    continue
                except OSError:
                    return
                if not chunk:
                    return
                buf.extend(chunk)
                while len(buf) >= 8:                    # 读请求固定 8 字节
                    request, buf = bytes(buf[:8]), buf[8:]
                    self._reply(conn, request)

    def _reply(self, conn: socket.socket, request: bytes):
        quantity = struct.unpack('>H', request[4:6])[0]
        response = _frame(request[0], quantity)
        conn.sendall(response[:len(response) - 2])      # 先吐前 23 字节
        if not self._stop.wait(TAIL_DELAY):
            conn.sendall(response[len(response) - 2:])  # 尾片留到下一轮之前才到

    def close(self):
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=2)


@pytest.fixture
def rtu_link():
    """返回接好从机的 SerialManager（复用真实读线程，不经 connect()）。"""
    server = _RtuSlaveServer()
    manager = SerialManager()
    # connect() 只认物理串口名，这里直接注入 pyserial 的 socket 传输后起跑读线程
    manager.serial = serial.serial_for_url(f'socket://127.0.0.1:{server.port}', timeout=0.05)
    manager.is_connected = True
    manager.stop_event.clear()
    manager.read_thread = threading.Thread(target=manager._read_loop, daemon=True)
    manager.read_thread.start()
    try:
        yield manager
    finally:
        manager.stop_event.set()
        manager.read_thread.join(timeout=2)
        manager.serial.close()
        server.close()


def _run(script: str, manager: SerialManager, timeout: float = 30):
    engine = ScriptEngine(manager)
    logs: list[str] = []
    result: dict = {}
    engine.on_log = logs.append
    engine.on_finished = lambda ok, msg: result.update(ok=ok, msg=msg)

    engine.execute(script)
    assert engine.thread is not None
    engine.thread.join(timeout=timeout)
    return result, logs


def test_builtin_polling_example_over_real_transport(rtu_link):
    """内置轮询示例跑在真实传输上：分片应答必须被拼成完整帧并校验通过。"""
    result, logs = _run(EXAMPLE_SCRIPTS["Modbus 轮询"], rtu_link)

    assert result.get("ok") is True, f"脚本失败: {result} {logs}"
    assert len([line for line in logs if "正常:" in line]) == 5, f"轮询日志异常: {logs}"
    assert not [line for line in logs if "失联" in line or "异常码" in line]


def test_wait_response_reassembles_frames_over_transport(rtu_link):
    """SerialManager 读线程 + wait_response：每轮拿到的都应是完整且 CRC 有效的帧。"""
    script = f'''from src.core.protocol_parser import CRC16, ModbusRTU

expected = ModbusRTU.expected_response_length(0x03, {QUANTITY})
for i in range(3):
    clear_response()
    send_bytes(ModbusRTU.build_read_holding_registers(1, 0, {QUANTITY}))
    resp = wait_response(timeout=0.5, expected_length=expected)
    log_info(f"len={{len(resp)}} crc={{CRC16.check(resp)}} regs={{ModbusRTU.registers_to_values(resp[3:-2])}}")
'''
    result, logs = _run(script, rtu_link)

    assert result.get("ok") is True, f"脚本失败: {result} {logs}"
    rounds = [line for line in logs if "len=" in line]
    assert len(rounds) == 3, f"轮次日志异常: {logs}"
    for line in rounds:
        assert f"len={5 + 2 * QUANTITY}" in line, f"帧长不对: {line}"
        assert "crc=True" in line, f"CRC 校验失败: {line}"
