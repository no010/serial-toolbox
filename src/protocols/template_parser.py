"""
自定义协议模板解析器
通过 JSON/YAML 模板定义帧格式，无需编写 Python 代码即可新增协议
"""

import json
import logging
import os
import struct
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from typing import Any

from src.core.protocol_plugin import ParsedFrame, ProtocolParserBase

logger = logging.getLogger(__name__)

# ─── CRC 计算 ────────────────────────────────────────────────


def calculate_crc16_modbus(data: bytes) -> int:
    """计算 Modbus CRC16 (多项式 0xA001)"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def calculate_crc16_xmodem(data: bytes) -> int:
    """计算 XModem CRC16 (多项式 0x1021)"""
    crc = 0x0000
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc


# ─── 模板数据类 ──────────────────────────────────────────────


@dataclass
class TemplateField:
    """模板字段定义

    type 为 subframe 时表示嵌套子帧：fields 是相对子帧起点的子字段，
    size_from 引用同层已解析的整数字段作为本字段字节数，repeat=True 时
    把所在段按子帧块循环解析直到段尾（即 TLV：子命令/子长度/子数据）。
    """

    name: str
    type: str  # uint8, uint16, uint32, bytes, string, subframe
    offset: int
    size: int = 1
    endianness: str = "big"  # big, little
    description: str = ""
    size_from: str | None = None  # 引用 earlier 字段名，用其值作为本字段字节数
    fields: list[dict[str, Any]] = field(default_factory=list)  # subframe 子字段
    repeat: bool = False  # subframe 是否循环到段尾

    # size → 默认整数类型（供缺少 type 的字段，如 length_field 推断）
    _SIZE_TO_TYPE = {1: "uint8", 2: "uint16", 4: "uint32"}
    # type → 默认字节数（供缺少 size 的定宽整数字段推断）
    _TYPE_TO_SIZE = {"uint8": 1, "uint16": 2, "uint32": 4}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TemplateField":
        # 仅取已知字段，忽略用户 JSON 中的多余键；缺失 type 时按 size 推断
        known = {f.name for f in dataclass_fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        clean.setdefault("type", cls._SIZE_TO_TYPE.get(clean.get("size", 1), "bytes"))
        if "size" not in clean:
            # 省略 size：subframe 记 0（填充到段尾），定宽整数按类型推断，其余默认 1
            if clean["type"] == "subframe":
                clean["size"] = 0
            else:
                clean["size"] = cls._TYPE_TO_SIZE.get(clean["type"], 1)
        return cls(**clean)


@dataclass
class ProtocolTemplate:
    """协议模板定义"""

    name: str
    description: str = ""
    header: str = ""  # HEX 字符串，如 "EB 90"
    tail: str = ""  # HEX 字符串，如 "0D 0A"
    min_length: int = 1
    length_field: dict[str, Any] | None = None  # {name, offset, size, endianness}
    fields: list[dict[str, Any]] = field(default_factory=list)
    crc: dict[str, Any] | None = None  # {offset, size, endianness, algorithm, coverage}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ProtocolTemplate":
        # 忽略用户 JSON 中的多余键，避免未知字段导致整体加载失败
        known = {f.name for f in dataclass_fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)

    def get_header_bytes(self) -> bytes:
        """获取帧头字节"""
        if not self.header:
            return b""
        return bytes.fromhex(self.header.replace(" ", "").replace(":", ""))

    def get_tail_bytes(self) -> bytes:
        """获取帧尾字节"""
        if not self.tail:
            return b""
        return bytes.fromhex(self.tail.replace(" ", "").replace(":", ""))


# ─── 模板解析器 ──────────────────────────────────────────────


class TemplateProtocolParser(ProtocolParserBase):
    """基于模板的协议解析器"""

    def __init__(self, template: ProtocolTemplate):
        self.template = template
        self.name = template.name
        self.description = template.description
        self.header = template.get_header_bytes()
        self.tail = template.get_tail_bytes()

    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """检测是否包含完整帧"""
        if len(data) < self.template.min_length:
            return False, 0

        # 查找帧头
        start = 0
        if self.header:
            start = data.find(self.header)
            if start < 0:
                return False, 0
        else:
            start = 0

        remaining = data[start:]

        # 计算帧长度
        frame_len = self._calculate_frame_length(remaining)
        if frame_len <= 0:
            return False, 0

        # 检查是否有足够数据
        if len(remaining) < frame_len:
            return False, 0

        # 检查帧尾
        if self.tail and remaining[frame_len - len(self.tail) : frame_len] != self.tail:
            return False, 0

        return True, start + frame_len

    def parse(self, data: bytes) -> ParsedFrame | None:
        """解析数据帧"""
        if len(data) < self.template.min_length:
            return ParsedFrame(
                protocol=self.name, raw_data=data, is_valid=False, error_msg="帧太短"
            )

        # 检查帧头
        if self.header and data[: len(self.header)] != self.header:
            return ParsedFrame(
                protocol=self.name, raw_data=data, is_valid=False, error_msg="帧头错误"
            )

        # 检查帧尾
        if self.tail and data[-len(self.tail) :] != self.tail:
            return ParsedFrame(
                protocol=self.name, raw_data=data, is_valid=False, error_msg="帧尾错误"
            )

        # 解析字段
        fields: dict[str, Any] = {}
        is_valid = True
        error_msg = ""

        try:
            # 长度字段先解析，供后续字段的 size_from 引用
            if self.template.length_field:
                lf_copy = dict(self.template.length_field)
                lf_copy.setdefault("name", "length")
                length_field = TemplateField.from_dict(lf_copy)
                fields[length_field.name] = self._read_field(data, length_field, fields)

            # 子帧“填充到段尾”的边界：帧尾之前，且不越过 CRC
            fill_end = len(data) - len(self.tail)
            if self.template.crc:
                fill_end = min(fill_end, self._crc_offset(len(data)))

            for field_data in self.template.fields:
                field_def = TemplateField.from_dict(field_data)
                fields[field_def.name] = self._read_field(data, field_def, fields, fill_end)

            # CRC 校验
            if self.template.crc:
                crc_valid, crc_info = self._verify_crc(data)
                fields.update(crc_info)
                is_valid = crc_valid
                if not crc_valid:
                    error_msg = "CRC 校验失败"

            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                fields=fields,
                is_valid=is_valid,
                error_msg=error_msg,
            )

        except Exception as e:
            return ParsedFrame(
                protocol=self.name, raw_data=data, is_valid=False, error_msg=f"解析失败: {str(e)}"
            )

    def _calculate_frame_length(self, data: bytes) -> int:
        """计算帧长度"""
        if self.template.length_field:
            lf = self.template.length_field
            offset = lf.get("offset", 0)
            size = lf.get("size", 1)
            endianness = lf.get("endianness", "big")

            if len(data) < offset + size:
                return 0

            length_bytes = data[offset : offset + size]
            if endianness == "little":
                length = int.from_bytes(length_bytes, "little")
            else:
                length = int.from_bytes(length_bytes, "big")

            # length_field 的 offset 是相对于帧头的偏移
            # 返回从帧头开始的总长度
            return offset + size + length

        # 无长度字段，使用 min_length
        return self.template.min_length

    def _field_size(self, fd: TemplateField, values: dict[str, Any], fill_end: int) -> int:
        """解析字段实际字节数：size_from 引用 > 定长 size > subframe 填充到段尾"""
        if fd.size_from:
            ref = values.get(fd.size_from)
            if not isinstance(ref, int):
                raise ValueError(f"字段 {fd.name} 的 size_from 引用了非整数字段 {fd.size_from}")
            return ref
        if fd.type == "subframe" and fd.size <= 0:
            return max(0, fill_end - fd.offset)
        return fd.size

    def _read_field(
        self, data: bytes, fd: TemplateField, values: dict[str, Any], fill_end: int | None = None
    ) -> Any:
        """按偏移切出字段原始字节并解码（subframe 递归）"""
        end = len(data) if fill_end is None else fill_end
        size = self._field_size(fd, values, end)
        if fd.offset + size > len(data):
            raise ValueError(f"字段 {fd.name} 超出帧范围")
        raw = data[fd.offset : fd.offset + size]
        return self._decode_value(raw, fd, values)

    def _decode_value(self, raw: bytes, fd: TemplateField, values: dict[str, Any]) -> Any:
        """把原始字节解码为字段值；subframe 交给递归子帧解析"""
        field_type = fd.type.lower()
        if field_type == "subframe":
            return self._parse_subframe(raw, fd.fields, values, fd.repeat)

        endian = "<" if fd.endianness == "little" else ">"
        if field_type == "uint8":
            return raw[0]
        elif field_type == "uint16":
            return struct.unpack(endian + "H", raw)[0]
        elif field_type == "uint32":
            return struct.unpack(endian + "I", raw)[0]
        elif field_type == "bytes":
            return " ".join(f"{b:02X}" for b in raw)
        elif field_type == "string":
            return raw.decode("utf-8", errors="replace")
        else:
            return list(raw)

    def _parse_subframe(
        self, seg: bytes, fields: list[dict[str, Any]], parent_values: dict[str, Any], repeat: bool
    ) -> Any:
        """递归解析子帧。

        子字段偏移相对子帧（或当前块）起点；repeat=True 时按块循环到段尾，
        每块 consumed = 各子字段 (offset+实际size) 的最大值，返回块列表；
        否则返回单个块字典。无子字段定义时整段按原始 hex 输出。
        """
        if not fields:
            return " ".join(f"{b:02X}" for b in seg)
        n = len(seg)
        if n == 0:
            return [] if repeat else {}

        child_defs = [TemplateField.from_dict(c) for c in fields]
        results: list[dict[str, Any]] = []
        cursor = 0
        while cursor < n:
            block = seg[cursor:]
            remaining = n - cursor
            vals = dict(parent_values)  # 供 size_from 跨层引用，块间互不污染
            out: dict[str, Any] = {}
            consumed = 0
            for cfd in child_defs:
                csize = self._field_size(cfd, vals, remaining)
                if cfd.offset + csize > remaining:
                    raise ValueError(f"子字段 {cfd.name} 超出子帧范围")
                raw = block[cfd.offset : cfd.offset + csize]
                val = self._decode_value(raw, cfd, vals)
                vals[cfd.name] = val
                out[cfd.name] = val
                consumed = max(consumed, cfd.offset + csize)
            results.append(out)
            if not repeat:
                break
            if consumed <= 0:
                raise ValueError("子帧重复块长度为 0，无法继续解析")
            cursor += consumed
        return results if repeat else results[0]

    def _crc_offset(self, data_len: int) -> int:
        """CRC 字段偏移：offset 为 'auto' 时落在帧尾之前（变长帧用），否则用定值"""
        crc_cfg = self.template.crc or {}
        offset = crc_cfg.get("offset", 0)
        if offset == "auto":
            return data_len - len(self.tail) - crc_cfg.get("size", 2)
        return offset

    def _crc_coverage_data(self, data: bytes, crc_cfg: dict, offset: int) -> bytes:
        """按 coverage 配置切出参与 CRC 计算的数据（build 与 verify 共用）"""
        coverage = crc_cfg.get("coverage", "all")  # all, before_crc, after_header
        if coverage == "before_crc":
            return data[:offset]
        if coverage == "after_header":
            return data[len(self.header) : offset] if self.header else data[:offset]
        return data  # 'all' 及未知值

    def _verify_crc(self, data: bytes) -> tuple[bool, dict[str, Any]]:
        """校验 CRC"""
        crc_cfg = self.template.crc
        if crc_cfg is None:
            return True, {"crc_valid": True}

        offset = self._crc_offset(len(data))
        size = crc_cfg.get("size", 2)
        endianness = crc_cfg.get("endianness", "big")
        algorithm = crc_cfg.get("algorithm", "modbus")

        if len(data) < offset + size:
            return False, {"crc_valid": False, "error": "CRC 字段超出范围"}

        received_bytes = data[offset : offset + size]
        if endianness == "little":
            received_crc = int.from_bytes(received_bytes, "little")
        else:
            received_crc = int.from_bytes(received_bytes, "big")

        crc_data = self._crc_coverage_data(data, crc_cfg, offset)

        if algorithm == "xmodem":
            calculated_crc = calculate_crc16_xmodem(crc_data)
        else:
            calculated_crc = calculate_crc16_modbus(crc_data)

        return received_crc == calculated_crc, {
            "crc_valid": received_crc == calculated_crc,
            "crc_received": f"0x{received_crc:04X}",
            "crc_calculated": f"0x{calculated_crc:04X}",
        }

    def build_frame(self, **kwargs) -> bytes:
        """根据模板构建帧（自动填充长度字段与 CRC，支持 subframe 嵌套/变长）"""
        field_defs = [TemplateField.from_dict(fd) for fd in self.template.fields]
        raws = self._serialize_field_set(field_defs, kwargs)

        # 1) 帧总长：各字段实际字节数的最大 (offset+len)，CRC，再加帧尾
        end = len(self.header)
        for fd in field_defs:
            end = max(end, fd.offset + len(raws[fd.name]))
        crc_cfg = self.template.crc
        crc_off = end
        if crc_cfg:
            # 'auto'：CRC 紧跟字段之后（变长帧）；否则用模板定值
            crc_off = end if crc_cfg.get("offset", 0) == "auto" else crc_cfg.get("offset", 0)
            end = max(end, crc_off + crc_cfg.get("size", 2))
        total = end + len(self.tail)

        frame = bytearray(total)
        # 2) 帧头
        if self.header:
            frame[: len(self.header)] = self.header
        # 3) 字段按 offset 放置
        for fd in field_defs:
            raw = raws[fd.name]
            if fd.offset + len(raw) > total:
                raise ValueError(f"字段 {fd.name} 超出帧范围")
            frame[fd.offset : fd.offset + len(raw)] = raw
        # 4) 长度字段：值 = 长度字段之后的字节数（与 _calculate_frame_length 约定一致）
        lf = self.template.length_field
        if lf:
            off = lf.get("offset", 0)
            size = lf.get("size", 1)
            endian = "little" if lf.get("endianness", "big") == "little" else "big"
            length_val = total - (off + size)
            frame[off : off + size] = length_val.to_bytes(size, endian)
        # 5) 帧尾
        if self.tail:
            frame[total - len(self.tail) :] = self.tail
        # 6) CRC（'before_crc'/'after_header' 可往返；'all' 含 CRC 自身，不可往返）
        if crc_cfg:
            size = crc_cfg.get("size", 2)
            endian = "little" if crc_cfg.get("endianness", "big") == "little" else "big"
            algorithm = crc_cfg.get("algorithm", "modbus")
            crc_data = self._crc_coverage_data(bytes(frame), crc_cfg, crc_off)
            calc = (
                calculate_crc16_xmodem(crc_data)
                if algorithm == "xmodem"
                else calculate_crc16_modbus(crc_data)
            )
            frame[crc_off : crc_off + size] = calc.to_bytes(size, endian)
        return bytes(frame)

    def _serialize_field_set(
        self, children: list[TemplateField], values: dict[str, Any]
    ) -> dict[str, bytes]:
        """序列化一组同层字段；size_from 引用的长度字段按依赖字段实际字节数自动回填"""
        names = {c.name for c in children}
        targets = {c.size_from for c in children if c.size_from and c.size_from in names}
        raws: dict[str, bytes] = {}
        for cfd in children:
            if cfd.name in targets:
                continue  # 长度字段稍后按依赖字段实际长度回填
            value = values.get(cfd.name)
            if value is None:
                raise ValueError(f"缺少字段值: {cfd.name}")
            if cfd.type == "subframe":
                raws[cfd.name] = self._build_subframe(value, cfd)
            else:
                raws[cfd.name] = self._serialize_field(value, cfd)
        for cfd in children:
            if cfd.size_from and cfd.size_from in targets:
                target = next(c for c in children if c.name == cfd.size_from)
                raws[target.name] = self._serialize_field(len(raws[cfd.name]), target)
        return raws

    def _build_subframe(self, value: Any, fd: TemplateField) -> bytes:
        """构建子帧：repeat 时 value 是块列表，否则单块字典；无子字段时按原始字节"""
        if not fd.fields:
            if isinstance(value, str):
                return bytes.fromhex(value.replace(" ", ""))
            return bytes(value)
        child_defs = [TemplateField.from_dict(c) for c in fd.fields]
        blocks = value if fd.repeat else [value]
        out = bytearray()
        for block in blocks:
            if not isinstance(block, dict):
                raise ValueError(f"子帧 {fd.name} 的块必须是字典")
            raws = self._serialize_field_set(child_defs, block)
            end = 0
            for cfd in child_defs:
                end = max(end, cfd.offset + len(raws[cfd.name]))
            buf = bytearray(end)
            for cfd in child_defs:
                raw = raws[cfd.name]
                buf[cfd.offset : cfd.offset + len(raw)] = raw
            out += buf
        return bytes(out)

    def _serialize_field(self, value: Any, field_def: TemplateField) -> bytes:
        """序列化字段值"""
        field_type = field_def.type.lower()
        endian = "<" if field_def.endianness == "little" else ">"

        if field_type == "uint8":
            return bytes([int(value) & 0xFF])
        elif field_type == "uint16":
            return struct.pack(endian + "H", int(value))
        elif field_type == "uint32":
            return struct.pack(endian + "I", int(value))
        elif field_type == "bytes":
            if isinstance(value, str):
                return bytes.fromhex(value.replace(" ", ""))
            return bytes(value)
        elif field_type == "string":
            return str(value).encode("utf-8")
        else:
            return bytes(value)

    def get_fields_description(self) -> dict[str, str]:
        """获取字段说明"""
        return {
            f["name"]: f.get("description", f"类型: {f.get('type')}") for f in self.template.fields
        }


# ─── 模板管理器 ──────────────────────────────────────────────


class ProtocolTemplateManager:
    """协议模板管理器"""

    def __init__(self, template_dir: str | None = None):
        self.template_dir = template_dir or os.path.join(
            os.path.expanduser("~"), ".serial-toolbox", "templates"
        )
        self.templates: dict[str, ProtocolTemplate] = {}
        self._ensure_dir()
        self.load_all()

    def _ensure_dir(self):
        """确保模板目录存在"""
        os.makedirs(self.template_dir, exist_ok=True)

    def load_all(self):
        """加载所有模板"""
        self.templates.clear()
        if not os.path.exists(self.template_dir):
            return

        for filename in os.listdir(self.template_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.template_dir, filename)
                template = self.load_from_file(filepath)
                if template and template.name:
                    self.templates[template.name] = template

    def load_from_file(self, filepath: str) -> ProtocolTemplate | None:
        """从文件加载模板"""
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            template = ProtocolTemplate.from_dict(data)
            self.templates[template.name] = template
            return template
        except Exception:
            logger.exception("加载模板失败 %s", filepath)
            return None

    # Windows 保留设备名，不能作为文件名
    _RESERVED_NAMES = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    def _template_path(self, name: str) -> str:
        """由模板名生成安全的文件路径（拒绝路径穿越 / 非法文件名）"""
        if not name or not name.strip():
            raise ValueError("模板名称不能为空")
        # 拒绝路径分隔符与 ..，防止路径穿越
        if "/" in name or "\\" in name or ".." in name or os.sep in name:
            raise ValueError("模板名称包含非法字符")
        safe = name.strip()
        if safe.split(".")[0].upper() in self._RESERVED_NAMES:
            raise ValueError("模板名称为系统保留名")
        base = os.path.realpath(self.template_dir)
        filepath = os.path.realpath(os.path.join(base, f"{safe}.json"))
        # 防御性校验：解析后必须仍落在模板目录内
        if os.path.dirname(filepath) != base:
            raise ValueError("非法模板名称")
        return filepath

    def save_template(self, template: ProtocolTemplate) -> str:
        """保存模板到文件"""
        filepath = self._template_path(template.name)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(template.to_dict(), f, ensure_ascii=False, indent=2)
        self.templates[template.name] = template
        return filepath

    def delete_template(self, name: str) -> bool:
        """删除模板"""
        if name not in self.templates:
            return False
        try:
            filepath = self._template_path(name)
        except ValueError:
            filepath = None
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        del self.templates[name]
        return True

    def get_template(self, name: str) -> ProtocolTemplate | None:
        """获取模板"""
        return self.templates.get(name)

    def list_templates(self) -> list[str]:
        """列出所有模板名称"""
        return list(self.templates.keys())

    def create_parser(self, name: str) -> TemplateProtocolParser | None:
        """根据模板名称创建解析器"""
        template = self.templates.get(name)
        if template:
            return TemplateProtocolParser(template)
        return None

    def create_all_parsers(self) -> list[TemplateProtocolParser]:
        """创建所有模板解析器"""
        return [TemplateProtocolParser(t) for t in self.templates.values()]


# ─── 示例模板 ────────────────────────────────────────────────


def create_sample_template() -> ProtocolTemplate:
    """创建示例模板（UART 数据包格式）"""
    return ProtocolTemplate(
        name="Custom-UART-Packet",
        description="示例: 自定义 UART 数据包 (帧头+长度+数据+CRC+帧尾)",
        header="EB 90",
        tail="0D 0A",
        min_length=8,
        length_field={"name": "length", "offset": 2, "size": 2, "endianness": "big"},
        fields=[
            {"name": "cmd", "type": "uint8", "offset": 4, "description": "命令字"},
            {"name": "seq", "type": "uint8", "offset": 5, "description": "序列号"},
            {
                "name": "payload",
                "type": "bytes",
                "offset": 6,
                "size": 2,
                "description": "数据载荷 (示例固定 2 字节)",
            },
        ],
        crc={
            "offset": 8,
            "size": 2,
            "endianness": "big",
            "algorithm": "modbus",
            "coverage": "before_crc",
        },
    )


def create_nested_sample_template() -> ProtocolTemplate:
    """创建嵌套子帧示例（数据段 = 重复的 子命令/子长度/子数据，即 TLV）

    帧布局: EB 90 | 长度(2) | cmd | seq | [数据段: 若干 TLV 块] | CRC(2) | 0D 0A
    数据段填充到 CRC 之前；每块 = sub_cmd(1) + sub_len(1) + sub_data(sub_len 字节)。
    把 sub_data 的 type 改成 subframe 并给它 fields，即可继续往里递归嵌套。
    """
    return ProtocolTemplate(
        name="Nested-TLV-Packet",
        description="示例: 数据段嵌套子帧 (子命令+子数据长度+子数据段, 可重复/递归)",
        header="EB 90",
        tail="0D 0A",
        min_length=8,
        length_field={"name": "length", "offset": 2, "size": 2, "endianness": "big"},
        fields=[
            {"name": "cmd", "type": "uint8", "offset": 4, "description": "外层命令字"},
            {"name": "seq", "type": "uint8", "offset": 5, "description": "序列号"},
            {
                "name": "data_segment",
                "type": "subframe",
                "offset": 6,
                "repeat": True,
                "description": "数据段: 重复 TLV 块, 填充到 CRC 之前",
                "fields": [
                    {"name": "sub_cmd", "type": "uint8", "offset": 0, "description": "子命令"},
                    {"name": "sub_len", "type": "uint8", "offset": 1, "description": "子数据长度"},
                    {
                        "name": "sub_data",
                        "type": "bytes",
                        "offset": 2,
                        "size_from": "sub_len",
                        "description": "子数据段 (长度由 sub_len 驱动)",
                    },
                ],
            },
        ],
        crc={
            "offset": "auto",
            "size": 2,
            "endianness": "big",
            "algorithm": "modbus",
            "coverage": "before_crc",
        },
    )
