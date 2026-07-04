"""
I2C 协议解析器
支持 I2C 读写帧解析
"""

import struct
from typing import Optional
from src.core.protocol_plugin import ProtocolParserBase, ParsedFrame


class I2CParser(ProtocolParserBase):
    """I2C 协议解析器"""
    
    name = "I2C"
    description = "I2C 总线协议 (主设备帧)"
    
    # I2C 帧格式 (简化版，常见于 USB-I2C 适配器):
    # [帧头 0xA5] [地址] [读写标志 R/W] [长度] [数据...] [CRC] [帧尾 0x5A]
    
    FRAME_HEADER = 0xA5
    FRAME_TAIL = 0x5A
    
    FLAG_WRITE = 0x00
    FLAG_READ = 0x01
    
    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测 I2C 帧"""
        if len(data) < 5:
            return False, 0
        
        # 查找帧头
        start = -1
        for i in range(len(data)):
            if data[i] == self.FRAME_HEADER:
                start = i
                break
        
        if start < 0:
            return False, 0
        
        remaining = data[start:]
        if len(remaining) < 5:
            return False, 0
        
        # 解析长度
        length = remaining[3]
        
        # 计算帧长度: 帧头(1) + 地址(1) + 标志(1) + 长度(1) + 数据(N) + CRC(1) + 帧尾(1)
        expected_len = 1 + 1 + 1 + 1 + length + 1 + 1
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len - 1] == self.FRAME_TAIL:
                return True, start + expected_len
        
        return False, 0
    
    def parse(self, data: bytes) -> Optional[ParsedFrame]:
        """解析 I2C 帧"""
        if len(data) < 5:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧太短"
            )
        
        # 检查帧头帧尾
        if data[0] != self.FRAME_HEADER:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧头错误"
            )
        
        if data[-1] != self.FRAME_TAIL:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧尾错误"
            )
        
        # 解析字段
        addr = data[1]
        rw_flag = data[2]
        length = data[3]
        
        is_read = (rw_flag == self.FLAG_READ)
        
        # 解析数据
        data_offset = 4
        payload = data[data_offset:data_offset+length]
        
        # CRC 校验
        received_crc = data[data_offset + length]
        calculated_crc = self._calculate_crc(data[1:data_offset+length])
        
        crc_valid = (received_crc == calculated_crc)
        
        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'address': f"0x{addr:02X}",
                'address_decimal': addr,
                'operation': 'READ' if is_read else 'WRITE',
                'length': length,
                'data': ' '.join(f'{b:02X}' for b in payload),
                'data_bytes': list(payload),
                'crc_valid': crc_valid,
                'crc_received': f"0x{received_crc:02X}",
                'crc_calculated': f"0x{calculated_crc:02X}",
            },
            is_valid=crc_valid
        )
    
    def build_frame(self, address: int, data: bytes, read: bool = False) -> bytes:
        """构建 I2C 帧"""
        if len(data) > 255:
            raise ValueError("I2C 数据长度不能超过 255 字节")
        
        frame = bytearray()
        frame.append(self.FRAME_HEADER)
        frame.append(address & 0x7F)
        frame.append(self.FLAG_READ if read else self.FLAG_WRITE)
        frame.append(len(data))
        frame.extend(data)
        
        # 计算 CRC
        crc = self._calculate_crc(bytes(frame[1:]))
        frame.append(crc)
        
        frame.append(self.FRAME_TAIL)
        
        return bytes(frame)
    
    def _calculate_crc(self, data: bytes) -> int:
        """计算 CRC8"""
        crc = 0x00
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x07
                else:
                    crc <<= 1
                crc &= 0xFF
        return crc
    
    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'address': 'I2C 设备地址 (7位, 十六进制)',
            'address_decimal': 'I2C 设备地址 (十进制)',
            'operation': '操作类型 (READ/WRITE)',
            'length': '数据长度',
            'data': '数据内容 (十六进制)',
            'data_bytes': '数据内容 (字节列表)',
            'crc_valid': 'CRC 校验是否通过',
            'crc_received': '接收到的 CRC',
            'crc_calculated': '计算出的 CRC',
        }
