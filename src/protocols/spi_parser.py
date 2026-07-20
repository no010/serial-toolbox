"""
SPI 协议解析器
支持 SPI 主设备帧解析 (常见 USB-SPI 适配器格式)
"""

from src.core.protocol_plugin import ParsedFrame, ProtocolParserBase


class SPIParser(ProtocolParserBase):
    """SPI 协议解析器"""

    name = "SPI"
    description = "SPI 总线协议 (主设备帧)"

    # SPI 帧格式 (简化版，常见于 USB-SPI 适配器):
    # [帧头 0x53 ('S')] [CS引脚] [模式 CPOL/CPHA] [长度] [数据...] [帧尾 0x45 ('E')]

    FRAME_HEADER = 0x53  # 'S'
    FRAME_TAIL = 0x45    # 'E'

    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测 SPI 帧"""
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

        # 计算帧长度: 帧头(1) + CS(1) + 模式(1) + 长度(1) + 数据(N) + 帧尾(1)
        expected_len = 1 + 1 + 1 + 1 + length + 1
        if len(remaining) >= expected_len:
            # 检查帧尾
            if remaining[expected_len - 1] == self.FRAME_TAIL:
                return True, start + expected_len

        return False, 0

    def parse(self, data: bytes) -> ParsedFrame | None:
        """解析 SPI 帧"""
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
        cs_pin = data[1]
        mode = data[2]
        length = data[3]

        # CPOL/CPHA
        cpol = (mode >> 1) & 0x01
        cpha = mode & 0x01

        # 解析数据
        data_offset = 4
        payload = data[data_offset:data_offset+length]

        return ParsedFrame(
            protocol=self.name,
            raw_data=data,
            fields={
                'cs_pin': f"CS{cs_pin}",
                'mode': f"Mode {mode} (CPOL={cpol}, CPHA={cpha})",
                'cpol': cpol,
                'cpha': cpha,
                'length': length,
                'data': ' '.join(f'{b:02X}' for b in payload),
                'data_bytes': list(payload),
            },
            is_valid=True
        )

    def build_frame(self, cs_pin: int, data: bytes, mode: int = 0) -> bytes:
        """构建 SPI 帧"""
        if len(data) > 255:
            raise ValueError("SPI 数据长度不能超过 255 字节")

        frame = bytearray()
        frame.append(self.FRAME_HEADER)
        frame.append(cs_pin & 0x0F)  # CS0-CS15
        frame.append(mode & 0x03)    # Mode 0-3
        frame.append(len(data))
        frame.extend(data)
        frame.append(self.FRAME_TAIL)

        return bytes(frame)

    def get_fields_description(self) -> dict:
        """获取字段说明"""
        return {
            'cs_pin': '片选引脚 (CS0-CS15)',
            'mode': 'SPI 模式 (Mode 0-3)',
            'cpol': '时钟极性 (0=低电平空闲, 1=高电平空闲)',
            'cpha': '时钟相位 (0=第一边沿采样, 1=第二边沿采样)',
            'length': '数据长度',
            'data': '数据内容 (十六进制)',
            'data_bytes': '数据内容 (字节列表)',
        }
