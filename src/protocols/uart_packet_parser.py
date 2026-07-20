"""
UART 数据包协议解析器
通用 UART 数据包格式，支持自定义帧头帧尾
"""

import struct

from src.core.protocol_plugin import ParsedFrame, ProtocolParserBase


class UARTPacketParser(ProtocolParserBase):
    """UART 数据包协议解析器"""

    name = "UART-Packet"
    description = "通用 UART 数据包 (帧头+长度+数据+CRC+帧尾)"

    # 默认帧格式:
    # [帧头 0xEB 0x90] [长度 2字节] [数据...] [CRC16 2字节] [帧尾 0x0D 0x0A]

    FRAME_HEADER = b'\xEB\x90'
    FRAME_TAIL = b'\x0D\x0A'

    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测数据包"""
        if len(data) < 6:  # 最小帧: 帧头(2) + 长度(2) + CRC(2)
            return False, 0

        # 查找帧头
        start = data.find(self.FRAME_HEADER)
        if start < 0:
            return False, 0

        remaining = data[start:]
        if len(remaining) < 6:
            return False, 0

        # 解析长度
        length = struct.unpack('>H', remaining[2:4])[0]

        # 计算帧长度: 帧头(2) + 长度(2) + 数据(N) + CRC(2) + 帧尾(2)
        expected_len = 2 + 2 + length + 2 + 2
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len-2:expected_len] == self.FRAME_TAIL:
                return True, start + expected_len

        return False, 0

    def parse(self, data: bytes) -> ParsedFrame | None:
        """解析数据包"""
        if len(data) < 6:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧太短"
            )

        # 检查帧头
        if data[:2] != self.FRAME_HEADER:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧头错误"
            )

        # 检查帧尾
        if data[-2:] != self.FRAME_TAIL:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧尾错误"
            )

        # 解析长度
        length = struct.unpack('>H', data[2:4])[0]

        # 解析数据
        payload = data[4:4+length]

        # CRC 校验
        received_crc = struct.unpack('>H', data[4+length:4+length+2])[0]
        calculated_crc = self._calculate_crc16(data[2:4+length])

        crc_valid = (received_crc == calculated_crc)

        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'length': length,
                'data': ' '.join(f'{b:02X}' for b in payload),
                'data_bytes': list(payload),
                'data_ascii': payload.decode('utf-8', errors='replace'),
                'crc_valid': crc_valid,
                'crc_received': f"0x{received_crc:04X}",
                'crc_calculated': f"0x{calculated_crc:04X}",
            },
            is_valid=crc_valid
        )

    def build_frame(self, data: bytes) -> bytes:
        """构建数据包"""
        if len(data) > 65535:
            raise ValueError("数据长度不能超过 65535 字节")

        frame = bytearray()
        frame.extend(self.FRAME_HEADER)
        frame.extend(struct.pack('>H', len(data)))
        frame.extend(data)

        # 计算 CRC
        crc = self._calculate_crc16(bytes(frame[2:]))
        frame.extend(struct.pack('>H', crc))

        frame.extend(self.FRAME_TAIL)

        return bytes(frame)

    def _calculate_crc16(self, data: bytes) -> int:
        """计算 CRC16 (Modbus)"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'length': '数据长度',
            'data': '数据内容 (十六进制)',
            'data_bytes': '数据内容 (字节列表)',
            'data_ascii': '数据内容 (ASCII)',
            'crc_valid': 'CRC 校验是否通过',
            'crc_received': '接收到的 CRC',
            'crc_calculated': '计算出的 CRC',
        }
