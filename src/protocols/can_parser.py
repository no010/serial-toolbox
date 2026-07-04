"""
CAN 总线协议解析器
支持标准帧 (11位ID) 和扩展帧 (29位ID)
"""

import struct
from typing import Optional
from src.core.protocol_plugin import ProtocolParserBase, ParsedFrame


class CANParser(ProtocolParserBase):
    """CAN 协议解析器"""
    
    name = "CAN"
    description = "CAN 总线协议 (标准帧/扩展帧)"
    
    # CAN 帧格式 (简化版，常见于 USB-CAN 适配器):
    # [帧头 0xAA] [ID长度 0x04/0x08] [ID...] [DLC] [DATA...] [帧尾 0x55]
    
    FRAME_HEADER = 0xAA
    FRAME_TAIL = 0x55
    
    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测 CAN 帧"""
        if len(data) < 4:
            return False, 0
        
        # 查找帧头
        start = -1
        for i in range(len(data)):
            if data[i] == self.FRAME_HEADER:
                start = i
                break
        
        if start < 0:
            return False, 0
        
        # 检查是否有足够数据
        remaining = data[start:]
        if len(remaining) < 4:
            return False, 0
        
        # 解析 ID 长度
        id_len = remaining[1]
        if id_len not in [4, 8]:  # 标准帧4字节ID，扩展帧8字节ID (含标志位)
            return False, 0
        
        # 计算帧长度: 帧头(1) + ID长度(1) + ID(N) + DLC(1) + DATA(DLC) + 帧尾(1)
        if len(remaining) < 3:
            return False, 0
        
        dlc = remaining[2 + id_len]
        if dlc > 8:
            return False, 0
        
        expected_len = 1 + 1 + id_len + 1 + dlc + 1
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len - 1] == self.FRAME_TAIL:
                return True, start + expected_len
        
        return False, 0
    
    def parse(self, data: bytes) -> Optional[ParsedFrame]:
        """解析 CAN 帧"""
        if len(data) < 4:
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
        
        id_len = data[1]
        if id_len not in [4, 8]:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg=f"ID长度无效: {id_len}"
            )
        
        # 解析 ID
        id_bytes = data[2:2+id_len]
        can_id = int.from_bytes(id_bytes, 'big')
        
        # 判断标准帧/扩展帧
        is_extended = id_len == 8
        if is_extended:
            can_id = can_id & 0x1FFFFFFF  # 29位ID
        else:
            can_id = can_id & 0x7FF  # 11位ID
        
        # 解析 DLC 和数据
        dlc_offset = 2 + id_len
        dlc = data[dlc_offset]
        
        data_offset = dlc_offset + 1
        payload = data[data_offset:data_offset+dlc]
        
        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'id': f"0x{can_id:03X}" if not is_extended else f"0x{can_id:08X}",
                'id_decimal': can_id,
                'is_extended': is_extended,
                'dlc': dlc,
                'data': ' '.join(f'{b:02X}' for b in payload),
                'data_bytes': list(payload),
            },
            is_valid=True
        )
    
    def build_frame(self, can_id: int, data: bytes, extended: bool = False) -> bytes:
        """构建 CAN 帧"""
        if len(data) > 8:
            raise ValueError("CAN 数据长度不能超过 8 字节")
        
        frame = bytearray()
        frame.append(self.FRAME_HEADER)
        
        if extended:
            frame.append(8)  # ID 长度
            frame.extend(can_id.to_bytes(4, 'big'))
        else:
            frame.append(4)  # ID 长度
            frame.extend(can_id.to_bytes(2, 'big'))
        
        frame.append(len(data))
        frame.extend(data)
        frame.append(self.FRAME_TAIL)
        
        return bytes(frame)
    
    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'id': 'CAN ID (十六进制)',
            'id_decimal': 'CAN ID (十进制)',
            'is_extended': '是否扩展帧 (29位ID)',
            'dlc': '数据长度 (0-8)',
            'data': '数据内容 (十六进制)',
            'data_bytes': '数据内容 (字节列表)',
        }
