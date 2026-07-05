"""
LIN 协议解析器
支持 LIN 总线帧解析 (Local Interconnect Network)
"""

import struct
from typing import Optional
from src.core.protocol_plugin import ProtocolParserBase, ParsedFrame


class LINParser(ProtocolParserBase):
    """LIN 协议解析器"""
    
    name = "LIN"
    description = "LIN 总线协议 (Local Interconnect Network)"
    
    # LIN 帧格式 (简化版，常见于 USB-LIN 适配器):
    # [帧头 0x4C ('L')] [ID] [长度] [数据...] [校验和] [帧尾 0x4E ('N')]
    
    FRAME_HEADER = 0x4C  # 'L'
    FRAME_TAIL = 0x4E    # 'N'
    
    # LIN ID 类型
    ID_TYPES = {
        0x00: "诊断请求 (0x00)",
        0x3C: "诊断请求 (0x3C)",
        0x3D: "诊断响应 (0x3D)",
        0x3E: "用户自定义 (0x3E)",
        0x3F: "保留 (0x3F)",
    }
    
    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测 LIN 帧"""
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
        length = remaining[2]
        
        # 计算帧长度: 帧头(1) + ID(1) + 长度(1) + 数据(N) + 校验和(1) + 帧尾(1)
        expected_len = 1 + 1 + 1 + length + 1 + 1
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len - 1] == self.FRAME_TAIL:
                return True, start + expected_len
        
        return False, 0
    
    def parse(self, data: bytes) -> Optional[ParsedFrame]:
        """解析 LIN 帧"""
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
        lin_id = data[1]
        length = data[2]
        
        # 解析数据
        data_offset = 3
        payload = data[data_offset:data_offset+length]
        
        # 校验和
        checksum = data[data_offset + length]
        
        # 计算校验和 (增强校验)
        calculated_checksum = self._calculate_checksum(lin_id, payload)
        checksum_valid = (checksum == calculated_checksum)
        
        # ID 类型
        id_type = self.ID_TYPES.get(lin_id, f"用户自定义 (0x{lin_id:02X})")
        
        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'id': f"0x{lin_id:02X}",
                'id_type': id_type,
                'length': length,
                'data': ' '.join(f'{b:02X}' for b in payload),
                'data_bytes': list(payload),
                'checksum': f"0x{checksum:02X}",
                'checksum_valid': checksum_valid,
            },
            is_valid=checksum_valid
        )
    
    def build_frame(self, lin_id: int, data: bytes) -> bytes:
        """构建 LIN 帧"""
        if len(data) > 8:
            raise ValueError("LIN 数据长度不能超过 8 字节")
        
        frame = bytearray()
        frame.append(self.FRAME_HEADER)
        frame.append(lin_id & 0x3F)  # 6位 ID
        frame.append(len(data))
        frame.extend(data)
        
        # 计算校验和
        checksum = self._calculate_checksum(lin_id, data)
        frame.append(checksum)
        
        frame.append(self.FRAME_TAIL)
        
        return bytes(frame)
    
    def _calculate_checksum(self, lin_id: int, data: bytes) -> int:
        """计算 LIN 校验和 (增强型)"""
        # 增强校验和包含 ID
        checksum = lin_id
        for byte in data:
            checksum += byte
            if checksum > 0xFF:
                checksum -= 0xFF
        return checksum & 0xFF
    
    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'id': 'LIN ID (6位, 0x00-0x3F)',
            'id_type': 'ID 类型 (诊断/用户自定义)',
            'length': '数据长度 (1-8)',
            'data': '数据内容 (十六进制)',
            'data_bytes': '数据内容 (字节列表)',
            'checksum': '校验和',
            'checksum_valid': '校验和是否有效',
        }
