"""
DMX512 协议解析器
支持 DMX512 舞台灯光控制协议帧解析
"""

import struct

from src.core.protocol_plugin import ParsedFrame, ProtocolParserBase


class DMX512Parser(ProtocolParserBase):
    """DMX512 协议解析器"""

    name = "DMX512"
    description = "DMX512 舞台灯光控制协议"

    # DMX512 帧格式 (简化版，常见于 USB-DMX 适配器):
    # [帧头 0x44 ('D')] [宇宙号] [起始码] [长度 2字节] [数据...] [帧尾 0x58 ('X')]

    FRAME_HEADER = 0x44  # 'D'
    FRAME_TAIL = 0x58    # 'X'

    # DMX512 起始码
    START_CODE_DMX = 0x00      # 标准 DMX512 数据
    START_CODE_RDM = 0xCC      # RDM (Remote Device Management)
    START_CODE_TEXT = 0x17     # 文本协议
    START_CODE_SIP = 0xCF      # 系统信息包

    START_CODE_NAMES = {
        0x00: "标准 DMX512 数据",
        0xCC: "RDM (远程设备管理)",
        0x17: "文本协议",
        0xCF: "系统信息包 (SIP)",
    }

    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测 DMX512 帧"""
        if len(data) < 6:
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
        if len(remaining) < 6:
            return False, 0

        # 解析长度 (2字节大端)
        length = struct.unpack('>H', remaining[3:5])[0]

        # 计算帧长度: 帧头(1) + 宇宙号(1) + 起始码(1) + 长度(2) + 数据(N) + 帧尾(1)
        expected_len = 1 + 1 + 1 + 2 + length + 1
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len - 1] == self.FRAME_TAIL:
                return True, start + expected_len

        return False, 0

    def parse(self, data: bytes) -> ParsedFrame | None:
        """解析 DMX512 帧"""
        if len(data) < 6:
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
        universe = data[1]
        start_code = data[2]
        length = struct.unpack('>H', data[3:5])[0]

        # 解析数据 (通道值)
        data_offset = 5
        payload = data[data_offset:data_offset+length]

        # 起始码类型
        start_code_name = self.START_CODE_NAMES.get(start_code, f"未知 (0x{start_code:02X})")

        # 通道值统计
        if start_code == 0x00 and length > 0:
            # 标准 DMX: 通道 1-512
            channels = {f"CH{i+1}": payload[i] for i in range(min(length, 16))}  # 只显示前16通道
            non_zero_count = sum(1 for b in payload if b > 0)
        else:
            channels = {}
            non_zero_count = 0

        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'universe': universe,
                'start_code': f"0x{start_code:02X} - {start_code_name}",
                'length': length,
                'data': ' '.join(f'{b:02X}' for b in payload[:32]) + ('...' if length > 32 else ''),
                'data_bytes': list(payload),
                'non_zero_channels': non_zero_count,
                **channels,
            },
            is_valid=True
        )

    def build_frame(self, universe: int, data: bytes, start_code: int = 0x00) -> bytes:  # type: ignore
        """构建 DMX512 帧"""
        if len(data) > 512:
            raise ValueError("DMX512 数据长度不能超过 512 字节")

        frame = bytearray()
        frame.append(self.FRAME_HEADER)
        frame.append(universe & 0x0F)  # 宇宙号 0-15
        frame.append(start_code)
        frame.extend(struct.pack('>H', len(data)))
        frame.extend(data)
        frame.append(self.FRAME_TAIL)

        return bytes(frame)

    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'universe': 'DMX 宇宙号 (0-15)',
            'start_code': '起始码 (0x00=标准DMX, 0xCC=RDM)',
            'length': '通道数量 (1-512)',
            'data': '通道值 (十六进制, 0x00-0xFF)',
            'data_bytes': '通道值 (字节列表)',
            'non_zero_channels': '非零通道数',
        }
