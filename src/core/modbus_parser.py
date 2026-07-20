"""
Modbus 响应解析器
自动检测并解析 Modbus RTU 响应帧
"""

import struct
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RegisterValue:
    """寄存器值"""
    address: int
    raw_value: int  # 16位原始值
    signed_value: int  # 有符号值
    float_value: float | None = None  # IEEE754 浮点 (需要2个寄存器)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]


@dataclass
class ModbusResponse:
    """Modbus 响应解析结果"""
    slave_addr: int
    function_code: int
    is_error: bool
    error_code: int | None = None
    error_msg: str = ""
    registers: list[RegisterValue] = field(default_factory=list)
    raw_frame: bytes = b''
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]


class ModbusResponseParser:
    """Modbus 响应解析器"""

    ERROR_CODES = {
        1: "非法功能码",
        2: "非法数据地址",
        3: "非法数据值",
        4: "从机故障",
        5: "确认（长耗时操作）",
        6: "从机忙",
    }

    def __init__(self):
        self.buffer = bytearray()
        self.last_request_func: int | None = None
        self.last_request_addr: int | None = None
        self.last_request_start: int | None = None
        self.last_request_quantity: int | None = None

    def set_last_request(self, func_code: int, slave_addr: int, start_addr: int, quantity: int):
        """记录最后一次请求，用于解析响应"""
        self.last_request_func = func_code
        self.last_request_addr = start_addr
        self.last_request_quantity = quantity

    def feed(self, data: bytes) -> list[ModbusResponse]:
        """喂入数据，返回解析到的完整响应列表"""
        self.buffer.extend(data)
        responses = []

        # 尝试从 buffer 中解析尽可能多的帧
        while len(self.buffer) >= 5:  # 最小 Modbus 帧长度
            response = self._try_parse_frame()
            if response:
                responses.append(response)
            else:
                break

        return responses

    def _try_parse_frame(self) -> ModbusResponse | None:
        """尝试从 buffer 解析一帧"""
        if len(self.buffer) < 5:
            return None

        slave_addr = self.buffer[0]
        func_code = self.buffer[1]

        # 错误响应
        if func_code & 0x80:
            if len(self.buffer) < 5:
                return None
            error_code = self.buffer[2]
            crc = struct.unpack('<H', bytes(self.buffer[3:5]))[0]

            # 校验 CRC
            from src.core.protocol_parser import CRC16
            calc_crc = CRC16.calculate(bytes(self.buffer[:3]))
            if crc != calc_crc:
                # CRC 错误，丢弃第一个字节，继续尝试
                self.buffer.pop(0)
                return None

            # 成功解析
            frame = bytes(self.buffer[:5])
            del self.buffer[:5]

            return ModbusResponse(
                slave_addr=slave_addr,
                function_code=func_code,
                is_error=True,
                error_code=error_code,
                error_msg=self.ERROR_CODES.get(error_code, f"未知错误: {error_code}"),
                raw_frame=frame
            )

        # 正常响应
        if func_code in [0x03, 0x04]:  # 读寄存器响应
            if len(self.buffer) < 3:
                return None
            byte_count = self.buffer[2]
            total_len = 3 + byte_count + 2  # header + data + crc

            if len(self.buffer) < total_len:
                return None

            # 提取数据
            reg_data = bytes(self.buffer[3:3+byte_count])
            crc = struct.unpack('<H', bytes(self.buffer[3+byte_count:3+byte_count+2]))[0]

            # 校验 CRC
            from src.core.protocol_parser import CRC16
            calc_crc = CRC16.calculate(bytes(self.buffer[:3+byte_count]))
            if crc != calc_crc:
                self.buffer.pop(0)
                return None

            # 解析寄存器值
            frame = bytes(self.buffer[:total_len])
            del self.buffer[:total_len]

            registers = self._parse_registers(reg_data)

            return ModbusResponse(
                slave_addr=slave_addr,
                function_code=func_code,
                is_error=False,
                registers=registers,
                raw_frame=frame
            )

        elif func_code in [0x05, 0x06, 0x0F, 0x10]:  # 写响应
            if len(self.buffer) < 8:
                return None

            # 写响应固定 8 字节
            frame = bytes(self.buffer[:8])
            crc = struct.unpack('<H', bytes(self.buffer[6:8]))[0]

            from src.core.protocol_parser import CRC16
            calc_crc = CRC16.calculate(bytes(self.buffer[:6]))
            if crc != calc_crc:
                self.buffer.pop(0)
                return None

            del self.buffer[:8]

            return ModbusResponse(
                slave_addr=slave_addr,
                function_code=func_code,
                is_error=False,
                raw_frame=frame
            )

        else:
            # 未知功能码，丢弃
            self.buffer.pop(0)
            return None

    def _parse_registers(self, data: bytes) -> list[RegisterValue]:
        """解析寄存器数据"""
        registers = []
        start_addr = self.last_request_addr or 0

        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                raw = struct.unpack('>H', data[i:i+2])[0]
                signed = struct.unpack('>h', data[i:i+2])[0]

                reg = RegisterValue(
                    address=start_addr + i // 2,
                    raw_value=raw,
                    signed_value=signed
                )
                registers.append(reg)

        # 计算浮点值 (每2个寄存器组成一个32位浮点)
        for i in range(0, len(registers) - 1, 2):
            raw_bytes = struct.pack('>HH', registers[i].raw_value, registers[i+1].raw_value)
            float_val = struct.unpack('>f', raw_bytes)[0]
            registers[i].float_value = float_val

        return registers

    def clear(self):
        """清空缓冲"""
        self.buffer.clear()
