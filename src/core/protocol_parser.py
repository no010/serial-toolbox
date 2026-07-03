"""
协议解析模块
支持 Modbus RTU/TCP、自定义协议框架
"""

import struct
from typing import Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum


class ModbusFunction(Enum):
    """Modbus 功能码"""
    READ_COILS = 0x01
    READ_DISCRETE_INPUTS = 0x02
    READ_HOLDING_REGISTERS = 0x03
    READ_INPUT_REGISTERS = 0x04
    WRITE_SINGLE_COIL = 0x05
    WRITE_SINGLE_REGISTER = 0x06
    WRITE_MULTIPLE_COILS = 0x0F
    WRITE_MULTIPLE_REGISTERS = 0x10


@dataclass
class ModbusFrame:
    """Modbus 帧"""
    slave_addr: int
    function: int
    data: bytes
    crc: Optional[int] = None
    is_valid: bool = True
    error_msg: str = ""


class CRC16:
    """CRC16 计算 (Modbus)"""
    
    @staticmethod
    def calculate(data: bytes) -> int:
        """计算 CRC16"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
    
    @staticmethod
    def check(data: bytes) -> bool:
        """校验 CRC"""
        if len(data) < 3:
            return False
        received_crc = struct.unpack('<H', data[-2:])[0]
        calculated_crc = CRC16.calculate(data[:-2])
        return received_crc == calculated_crc


class ModbusRTU:
    """Modbus RTU 协议"""
    
    @staticmethod
    def build_read_holding_registers(slave_addr: int, start_addr: int, quantity: int) -> bytes:
        """构建读取保持寄存器请求"""
        frame = struct.pack('>BBhh', slave_addr, ModbusFunction.READ_HOLDING_REGISTERS.value, 
                           start_addr, quantity)
        crc = CRC16.calculate(frame)
        return frame + struct.pack('<H', crc)
    
    @staticmethod
    def build_read_input_registers(slave_addr: int, start_addr: int, quantity: int) -> bytes:
        """构建读取输入寄存器请求"""
        frame = struct.pack('>BBhh', slave_addr, ModbusFunction.READ_INPUT_REGISTERS.value,
                           start_addr, quantity)
        crc = CRC16.calculate(frame)
        return frame + struct.pack('<H', crc)
    
    @staticmethod
    def build_write_single_register(slave_addr: int, reg_addr: int, value: int) -> bytes:
        """构建写单个寄存器请求"""
        frame = struct.pack('>BBhH', slave_addr, ModbusFunction.WRITE_SINGLE_REGISTER.value,
                           reg_addr, value)
        crc = CRC16.calculate(frame)
        return frame + struct.pack('<H', crc)
    
    @staticmethod
    def build_write_multiple_registers(slave_addr: int, start_addr: int, values: List[int]) -> bytes:
        """构建写多个寄存器请求"""
        quantity = len(values)
        byte_count = quantity * 2
        frame = struct.pack('>BBhhB', slave_addr, ModbusFunction.WRITE_MULTIPLE_REGISTERS.value,
                           start_addr, quantity, byte_count)
        for value in values:
            frame += struct.pack('>H', value)
        crc = CRC16.calculate(frame)
        return frame + struct.pack('<H', crc)
    
    @staticmethod
    def parse_response(data: bytes) -> ModbusFrame:
        """解析响应帧"""
        if len(data) < 4:
            return ModbusFrame(0, 0, b'', is_valid=False, error_msg="帧太短")
        
        # 校验 CRC
        if not CRC16.check(data):
            return ModbusFrame(0, 0, b'', is_valid=False, error_msg="CRC 校验失败")
        
        slave_addr = data[0]
        function = data[1]
        
        # 错误响应
        if function & 0x80:
            error_code = data[2]
            error_msgs = {
                1: "非法功能码",
                2: "非法数据地址",
                3: "非法数据值",
                4: "从机故障",
                5: "确认（长耗时操作）",
                6: "从机忙",
            }
            error_msg = error_msgs.get(error_code, f"未知错误: {error_code}")
            return ModbusFrame(slave_addr, function, b'', is_valid=False, error_msg=error_msg)
        
        # 正常响应
        if function in [0x03, 0x04]:  # 读寄存器响应
            byte_count = data[2]
            reg_data = data[3:-2]
            return ModbusFrame(slave_addr, function, reg_data, is_valid=True)
        elif function in [0x05, 0x06, 0x0F, 0x10]:  # 写响应
            return ModbusFrame(slave_addr, function, data[2:-2], is_valid=True)
        else:
            return ModbusFrame(slave_addr, function, data[2:-2], is_valid=True)
    
    @staticmethod
    def registers_to_values(data: bytes, signed: bool = False) -> List[int]:
        """寄存器数据转数值列表"""
        values = []
        for i in range(0, len(data), 2):
            if i + 1 < len(data):
                value = struct.unpack('>h' if signed else '>H', data[i:i+2])[0]
                values.append(value)
        return values


class ProtocolParser:
    """通用协议解析器"""
    
    def __init__(self):
        self.parsers = {
            'modbus_rtu': ModbusRTU(),
        }
        self.custom_parsers = {}
    
    def register_custom_parser(self, name: str, parser_func):
        """注册自定义协议解析器"""
        self.custom_parsers[name] = parser_func
    
    def parse(self, protocol: str, data: bytes):
        """解析数据"""
        if protocol in self.parsers:
            return self.parsers[protocol].parse_response(data)
        elif protocol in self.custom_parsers:
            return self.custom_parsers[protocol](data)
        else:
            raise ValueError(f"未知协议: {protocol}")
