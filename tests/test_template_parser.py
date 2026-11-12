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
    create_nested_sample_template,
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
    assert parsed is not None
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
    assert parsed is not None
    assert not parsed.is_valid


def test_length_field_parse_regression():
    # 回归：含 length_field 的模板曾因 TemplateField 缺 type 而解析失败
    p = TemplateProtocolParser(create_sample_template())
    parsed = p.parse(p.build_frame(cmd=5, seq=6, payload="1122"))
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert "length" in parsed.fields


# ── from_dict 健壮性 ────────────────────────────────────────


def test_template_field_type_inferred_from_size():
    f = TemplateField.from_dict({"name": "x", "offset": 2, "size": 2, "bogus": 1})
    assert f.type == "uint16"  # size=2 → uint16，且忽略多余键


def test_template_field_size_inferred_from_type():
    assert TemplateField.from_dict({"name": "x", "type": "uint16", "offset": 0}).size == 2
    assert TemplateField.from_dict({"name": "x", "type": "uint32", "offset": 0}).size == 4
    assert TemplateField.from_dict({"name": "x", "type": "uint8", "offset": 0}).size == 1


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


# ── 嵌套子帧 / TLV ──────────────────────────────────────────


def test_nested_tlv_round_trip():
    p = TemplateProtocolParser(create_nested_sample_template())
    seg = [{"sub_cmd": 1, "sub_data": "AABBCC"}, {"sub_cmd": 2, "sub_data": "01020304"}]
    frame = p.build_frame(cmd=0x11, seq=0x22, data_segment=seg)
    ok, consumed = p.detect_frame(frame)
    assert ok and consumed == len(frame)
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert parsed.fields["cmd"] == 0x11
    blocks = parsed.fields["data_segment"]
    assert blocks[0] == {"sub_cmd": 1, "sub_len": 3, "sub_data": "AA BB CC"}
    assert blocks[1] == {"sub_cmd": 2, "sub_len": 4, "sub_data": "01 02 03 04"}


@pytest.mark.parametrize("payloads", [["AA"], ["AA", "BB", "CC"], ["0102030405"]])
def test_nested_variable_length_round_trip(payloads):
    # 变长帧 + auto CRC：不同载荷长度都能解析/构建往返
    p = TemplateProtocolParser(create_nested_sample_template())
    seg = [{"sub_cmd": i + 1, "sub_data": d} for i, d in enumerate(payloads)]
    frame = p.build_frame(cmd=1, seq=2, data_segment=seg)
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert len(parsed.fields["data_segment"]) == len(payloads)
    assert parsed.fields["length"] == len(frame) - 4


def test_recursive_subframe():
    tpl = ProtocolTemplate(
        name="R",
        header="EB 90",
        tail="0D 0A",
        min_length=6,
        length_field={"name": "length", "offset": 2, "size": 2, "endianness": "big"},
        fields=[
            {
                "name": "seg",
                "type": "subframe",
                "offset": 4,
                "repeat": True,
                "fields": [
                    {"name": "sub_cmd", "type": "uint8", "offset": 0},
                    {"name": "sub_len", "type": "uint8", "offset": 1},
                    {
                        "name": "sub_data",
                        "type": "subframe",
                        "offset": 2,
                        "size_from": "sub_len",
                        "fields": [
                            {"name": "in_cmd", "type": "uint8", "offset": 0},
                            {"name": "in_len", "type": "uint8", "offset": 1},
                            {
                                "name": "in_data",
                                "type": "bytes",
                                "offset": 2,
                                "size_from": "in_len",
                            },
                        ],
                    },
                ],
            }
        ],
        crc={"offset": "auto", "size": 2, "algorithm": "modbus", "coverage": "before_crc"},
    )
    p = TemplateProtocolParser(tpl)
    frame = p.build_frame(seg=[{"sub_cmd": 9, "sub_data": {"in_cmd": 5, "in_data": "FFEE"}}])
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    blk = parsed.fields["seg"][0]
    assert blk["sub_cmd"] == 9 and blk["sub_len"] == 4
    assert blk["sub_data"] == {"in_cmd": 5, "in_len": 2, "in_data": "FF EE"}


def test_single_subframe_fixed_size():
    tpl = ProtocolTemplate(
        name="S",
        header="AA",
        min_length=4,
        fields=[
            {
                "name": "hdr",
                "type": "subframe",
                "offset": 1,
                "size": 3,
                "fields": [
                    {"name": "a", "type": "uint8", "offset": 0},
                    {"name": "b", "type": "uint16", "offset": 1, "endianness": "big"},
                ],
            }
        ],
    )
    p = TemplateProtocolParser(tpl)
    frame = p.build_frame(hdr={"a": 1, "b": 0x0203})
    assert frame == bytes.fromhex("AA010203")
    parsed = p.parse(frame)
    assert parsed is not None and parsed.is_valid
    assert parsed.fields["hdr"] == {"a": 1, "b": 0x0203}


def test_top_level_size_from_bytes():
    tpl = ProtocolTemplate(
        name="D",
        header="BB",
        min_length=3,
        length_field={"name": "length", "offset": 1, "size": 1, "endianness": "big"},
        fields=[{"name": "payload", "type": "bytes", "offset": 2, "size_from": "length"}],
    )
    p = TemplateProtocolParser(tpl)
    frame = p.build_frame(payload="010203")
    assert frame == bytes.fromhex("BB03010203")
    parsed = p.parse(frame)
    assert parsed is not None and parsed.is_valid
    assert parsed.fields["payload"] == "01 02 03"
    assert parsed.fields["length"] == 3


def test_subframe_fill_to_tail():
    tpl = ProtocolTemplate(
        name="F",
        header="CC",
        tail="DD",
        min_length=3,
        fields=[
            {
                "name": "seg",
                "type": "subframe",
                "offset": 1,
                "repeat": True,
                "fields": [
                    {"name": "t", "type": "uint8", "offset": 0},
                    {"name": "l", "type": "uint8", "offset": 1},
                    {"name": "v", "type": "bytes", "offset": 2, "size_from": "l"},
                ],
            }
        ],
    )
    p = TemplateProtocolParser(tpl)
    frame = p.build_frame(seg=[{"t": 1, "v": "AA"}, {"t": 2, "v": "BBCC"}])
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert len(parsed.fields["seg"]) == 2


def test_subframe_size_from_outer_field():
    tpl = ProtocolTemplate(
        name="L",
        header="AB",
        min_length=3,
        fields=[
            {"name": "seglen", "type": "uint8", "offset": 1},
            {
                "name": "seg",
                "type": "subframe",
                "offset": 2,
                "size_from": "seglen",
                "repeat": True,
                "fields": [
                    {"name": "t", "type": "uint8", "offset": 0},
                    {"name": "l", "type": "uint8", "offset": 1},
                    {"name": "v", "type": "bytes", "offset": 2, "size_from": "l"},
                ],
            },
        ],
    )
    p = TemplateProtocolParser(tpl)
    frame = p.build_frame(seg=[{"t": 1, "v": "AA"}])
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert parsed.fields["seglen"] == 3  # 构建时按子帧实际长度自动回填
    assert parsed.fields["seg"] == [{"t": 1, "l": 1, "v": "AA"}]


def test_nested_empty_segment():
    p = TemplateProtocolParser(create_nested_sample_template())
    frame = p.build_frame(cmd=1, seq=2, data_segment=[])
    parsed = p.parse(frame)
    assert parsed is not None
    assert parsed.is_valid, parsed.error_msg
    assert parsed.fields["data_segment"] == []


def test_repeat_zero_length_block_guard():
    tpl = ProtocolTemplate(
        name="Z",
        min_length=2,
        fields=[
            {"name": "n", "type": "uint8", "offset": 0},
            {
                "name": "seg",
                "type": "subframe",
                "offset": 1,
                "repeat": True,
                "fields": [{"name": "v", "type": "bytes", "offset": 0, "size_from": "n"}],
            },
        ],
    )
    p = TemplateProtocolParser(tpl)
    parsed = p.parse(bytes([0x00, 0xAA]))  # n=0 但段非空 → 每块消费 0
    assert parsed is not None and not parsed.is_valid
    assert "长度为 0" in parsed.error_msg


def test_opaque_subframe_hex():
    tpl = ProtocolTemplate(
        name="O",
        header="EE",
        min_length=2,
        fields=[{"name": "blob", "type": "subframe", "offset": 1, "size": 3}],
    )
    p = TemplateProtocolParser(tpl)
    parsed = p.parse(bytes.fromhex("EE010203"))
    assert parsed is not None and parsed.is_valid
    assert parsed.fields["blob"] == "01 02 03"


def test_subframe_size_omitted_means_fill():
    assert TemplateField.from_dict({"name": "s", "type": "subframe", "offset": 2}).size == 0
    assert (
        TemplateField.from_dict({"name": "s", "type": "subframe", "offset": 2, "size": 5}).size == 5
    )


def test_build_missing_subframe_raises():
    p = TemplateProtocolParser(create_nested_sample_template())
    with pytest.raises(ValueError):
        p.build_frame(cmd=1, seq=2)  # 缺 data_segment


def test_nested_detect_in_noise():
    p = TemplateProtocolParser(create_nested_sample_template())
    frame = p.build_frame(cmd=1, seq=2, data_segment=[{"sub_cmd": 1, "sub_data": "AA"}])
    ok, consumed = p.detect_frame(b"\x00\x99" + frame + b"\x7f")
    assert ok and consumed == 2 + len(frame)
