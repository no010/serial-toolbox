"""内置协议解析器测试：build → detect → parse 往返 + 噪声容错。"""
from src.protocols.can_parser import CANParser
from src.protocols.dmx512_parser import DMX512Parser
from src.protocols.i2c_parser import I2CParser
from src.protocols.lin_parser import LINParser
from src.protocols.spi_parser import SPIParser
from src.protocols.uart_packet_parser import UARTPacketParser


def _round_trip(parser, frame: bytes):
    """断言帧能被完整检测并成功解析，返回解析结果。"""
    ok, consumed = parser.detect_frame(frame)
    assert ok, f"{parser.name}: detect_frame 未识别完整帧"
    assert consumed == len(frame), f"{parser.name}: consumed={consumed} != {len(frame)}"
    parsed = parser.parse(frame)
    assert parsed is not None, f"{parser.name}: parse 返回 None"
    assert parsed.is_valid, f"{parser.name}: 解析无效 - {parsed.error_msg}"
    return parsed


# ── CAN ─────────────────────────────────────────────────────

def test_can_standard_round_trip():
    p = CANParser()
    parsed = _round_trip(p, p.build_frame(can_id=0x123, data=b"\x01\x02\x03"))
    assert parsed.fields["id_decimal"] == 0x123
    assert parsed.fields["is_extended"] is False


def test_can_extended_round_trip():
    p = CANParser()
    parsed = _round_trip(p, p.build_frame(can_id=0x1FFFFFFF, data=b"\xAA\xBB", extended=True))
    assert parsed.fields["is_extended"] is True


# ── I2C ─────────────────────────────────────────────────────

def test_i2c_round_trip():
    p = I2CParser()
    parsed = _round_trip(p, p.build_frame(address=0x50, data=b"\x01\x02"))
    assert parsed.fields["crc_valid"] is True
    assert parsed.fields["operation"] == "WRITE"


def test_i2c_read_round_trip():
    p = I2CParser()
    parsed = _round_trip(p, p.build_frame(address=0x68, data=b"\x00", read=True))
    assert parsed.fields["operation"] == "READ"


# ── SPI ─────────────────────────────────────────────────────

def test_spi_round_trip():
    p = SPIParser()
    _round_trip(p, p.build_frame(cs_pin=1, data=b"\xDE\xAD"))


# ── LIN ─────────────────────────────────────────────────────

def test_lin_round_trip():
    p = LINParser()
    parsed = _round_trip(p, p.build_frame(lin_id=0x10, data=b"\x01\x02\x03"))
    assert parsed.fields["checksum_valid"] is True


# ── DMX512 ──────────────────────────────────────────────────

def test_dmx512_round_trip():
    p = DMX512Parser()
    parsed = _round_trip(p, p.build_frame(universe=1, data=b"\x00\xFF\x80"))
    assert parsed.fields["universe"] == 1


# ── UART Packet ─────────────────────────────────────────────

def test_uart_packet_round_trip():
    p = UARTPacketParser()
    parsed = _round_trip(p, p.build_frame(data=b"\x01\x02\x03\x04"))
    assert parsed.fields["crc_valid"] is True
    assert parsed.fields["length"] == 4


def test_uart_packet_detect_in_noise():
    p = UARTPacketParser()
    frame = p.build_frame(data=b"\x01\x02")
    ok, consumed = p.detect_frame(b"\x00\x99\x88" + frame + b"\x7f")
    assert ok and consumed == 3 + len(frame)
