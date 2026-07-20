"""template_parser 核心逻辑测试：CRC、帧检测/解析往返、模板存取安全。"""
import os

import pytest

from src.protocols.template_parser import (
    ProtocolTemplate,
    ProtocolTemplateManager,
    TemplateField,
    TemplateProtocolParser,
    calculate_crc16_modbus,
    calculate_crc16_xmodem,
    create_sample_template,
)

# ── CRC 已知向量 ────────────────────────────────────────────

def test_crc16_modbus_known_vector():
    # 标准校验输入 "123456789" 的 Modbus CRC16 = 0x4B37
    assert calculate_crc16_modbus(b"123456789") == 0x4B37


def test_crc16_xmodem_known_vector():
    # 标准校验输入 "123456789" 的 XModem CRC16 = 0x31C3
    assert calculate_crc16_xmodem(b"123456789") == 0x31C3


# ── 帧检测 / 解析往返 ───────────────────────────────────────

def test_sample_round_trip():
    p = TemplateProtocolParser(create_sample_template())
    frame = p.build_frame(cmd=0x11, seq=0x22, payload="AABB")
    ok, consumed = p.detect_frame(frame)
    assert ok and consumed == len(frame)
    parsed = p.parse(frame)
    assert parsed.is_valid, parsed.error_msg
    assert parsed.fields["cmd"] == 0x11
    assert parsed.fields["seq"] == 0x22
    # 长度字段约定：值 = 长度字段之后的字节数
    assert parsed.fields["length"] == len(frame) - 4


def test_detect_in_noise():
    p = TemplateProtocolParser(create_sample_template())
    frame = p.build_frame(cmd=1, seq=2, payload="0000")
    ok, consumed = p.detect_frame(b"\x00\x99" + frame + b"\x7f")
    assert ok and consumed == 2 + len(frame)


def test_corrupt_crc_invalid():
    p = TemplateProtocolParser(create_sample_template())
    frame = bytearray(p.build_frame(cmd=1, seq=2, payload="AABB"))
    frame[8] ^= 0xFF  # 破坏 CRC 字段
    parsed = p.parse(bytes(frame))
    assert not parsed.is_valid


def test_length_field_parse_regression():
    # 回归：含 length_field 的模板曾因 TemplateField 缺 type 而解析失败
    p = TemplateProtocolParser(create_sample_template())
    parsed = p.parse(p.build_frame(cmd=5, seq=6, payload="1122"))
    assert parsed.is_valid, parsed.error_msg
    assert "length" in parsed.fields


# ── from_dict 健壮性 ────────────────────────────────────────

def test_template_field_type_inferred_from_size():
    f = TemplateField.from_dict({"name": "x", "offset": 2, "size": 2, "bogus": 1})
    assert f.type == "uint16"  # size=2 → uint16，且忽略多余键


def test_protocol_template_ignores_extra_keys():
    t = ProtocolTemplate.from_dict({"name": "t", "whatever": 1, "fields": []})
    assert t.name == "t"


# ── 模板存取安全 ────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["../evil", "a/b", "..\\x", "COM1", "  "])
def test_save_rejects_illegal_name(tmp_path, bad):
    m = ProtocolTemplateManager(template_dir=str(tmp_path))
    tpl = create_sample_template()
    tpl.name = bad
    with pytest.raises(ValueError):
        m.save_template(tpl)


def test_save_never_escapes_template_dir(tmp_path):
    m = ProtocolTemplateManager(template_dir=str(tmp_path))
    tpl = create_sample_template()
    tpl.name = "../evil"
    with pytest.raises(ValueError):
        m.save_template(tpl)
    parent = os.path.dirname(str(tmp_path))
    assert not os.path.exists(os.path.join(parent, "evil.json"))


def test_save_load_delete_cycle(tmp_path):
    m = ProtocolTemplateManager(template_dir=str(tmp_path))
    tpl = create_sample_template()
    tpl.name = "My-Proto_v1"
    fp = m.save_template(tpl)
    assert os.path.exists(fp)

    # 新管理器能从磁盘重新加载
    m2 = ProtocolTemplateManager(template_dir=str(tmp_path))
    assert "My-Proto_v1" in m2.list_templates()

    assert m.delete_template("My-Proto_v1")
    assert not os.path.exists(fp)
