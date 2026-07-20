"""
自定义协议模板解析器
通过 JSON/YAML 模板定义帧格式，无需编写 Python 代码即可新增协议
"""

import json
import os
import struct
from dataclasses import asdict, dataclass, field
from dataclasses import fields as dataclass_fields
from typing import Any

from src.core.protocol_plugin import ParsedFrame, ProtocolParserBase

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
    """模板字段定义"""
    name: str
    type: str  # uint8, uint16, uint32, bytes, string
    offset: int
    size: int = 1
    endianness: str = 'big'  # big, little
    description: str = ""

    # size → 默认整数类型（供缺少 type 的字段，如 length_field 推断）
    _SIZE_TO_TYPE = {1: 'uint8', 2: 'uint16', 4: 'uint32'}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'TemplateField':
        # 仅取已知字段，忽略用户 JSON 中的多余键；缺失 type 时按 size 推断
        known = {f.name for f in dataclass_fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        clean.setdefault('type', cls._SIZE_TO_TYPE.get(clean.get('size', 1), 'bytes'))
        return cls(**clean)


@dataclass
class ProtocolTemplate:
    """协议模板定义"""
    name: str
    description: str = ""
    header: str = ""  # HEX 字符串，如 "EB 90"
    tail: str = ""    # HEX 字符串，如 "0D 0A"
    min_length: int = 1
    length_field: dict[str, Any] | None = None  # {name, offset, size, endianness}
    fields: list[dict[str, Any]] = field(default_factory=list)
    crc: dict[str, Any] | None = None  # {offset, size, endianness, algorithm, coverage}

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ProtocolTemplate':
        # 忽略用户 JSON 中的多余键，避免未知字段导致整体加载失败
        known = {f.name for f in dataclass_fields(cls)}
        clean = {k: v for k, v in data.items() if k in known}
        return cls(**clean)

    def get_header_bytes(self) -> bytes:
        """获取帧头字节"""
        if not self.header:
            return b''
        return bytes.fromhex(self.header.replace(' ', '').replace(':', ''))

    def get_tail_bytes(self) -> bytes:
        """获取帧尾字节"""
        if not self.tail:
            return b''
        return bytes.fromhex(self.tail.replace(' ', '').replace(':', ''))


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
        if self.tail and remaining[frame_len - len(self.tail):frame_len] != self.tail:
            return False, 0

        return True, start + frame_len

    def parse(self, data: bytes) -> ParsedFrame | None:
        """解析数据帧"""
        if len(data) < self.template.min_length:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧太短"
            )

        # 检查帧头
        if self.header and data[:len(self.header)] != self.header:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧头错误"
            )

        # 检查帧尾
        if self.tail and data[-len(self.tail):] != self.tail:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg="帧尾错误"
            )

        # 解析字段
        fields: dict[str, Any] = {}
        is_valid = True
        error_msg = ""

        try:
            for field_data in self.template.fields:
                field_def = TemplateField.from_dict(field_data)
                value = self._parse_field(data, field_def)
                fields[field_def.name] = value

            # 如果有长度字段，加入字段列表
            if self.template.length_field:
                lf_copy = dict(self.template.length_field)
                lf_copy.setdefault('name', 'length')
                length_field = TemplateField.from_dict(lf_copy)
                fields[length_field.name] = self._parse_field(data, length_field)

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
                error_msg=error_msg
            )

        except Exception as e:
            return ParsedFrame(
                protocol=self.name,
                raw_data=data,
                is_valid=False,
                error_msg=f"解析失败: {str(e)}"
            )

    def _calculate_frame_length(self, data: bytes) -> int:
        """计算帧长度"""
        if self.template.length_field:
            lf = self.template.length_field
            offset = lf.get('offset', 0)
            size = lf.get('size', 1)
            endianness = lf.get('endianness', 'big')

            if len(data) < offset + size:
                return 0

            length_bytes = data[offset:offset + size]
            if endianness == 'little':
                length = int.from_bytes(length_bytes, 'little')
            else:
                length = int.from_bytes(length_bytes, 'big')

            # length_field 的 offset 是相对于帧头的偏移
            # 返回从帧头开始的总长度
            return offset + size + length

        # 无长度字段，使用 min_length
        return self.template.min_length

    def _parse_field(self, data: bytes, field_def: TemplateField) -> Any:
        """解析单个字段"""
        if len(data) < field_def.offset + field_def.size:
            raise ValueError(f"字段 {field_def.name} 超出帧范围")

        raw = data[field_def.offset:field_def.offset + field_def.size]
        field_type = field_def.type.lower()

        if field_type == 'uint8':
            return raw[0]
        elif field_type == 'uint16':
            endian = '<' if field_def.endianness == 'little' else '>'
            return struct.unpack(endian + 'H', raw)[0]
        elif field_type == 'uint32':
            endian = '<' if field_def.endianness == 'little' else '>'
            return struct.unpack(endian + 'I', raw)[0]
        elif field_type == 'bytes':
            return ' '.join(f'{b:02X}' for b in raw)
        elif field_type == 'string':
            return raw.decode('utf-8', errors='replace')
        else:
            return list(raw)

    def _crc_coverage_data(self, data: bytes, crc_cfg: dict, offset: int) -> bytes:
        """按 coverage 配置切出参与 CRC 计算的数据（build 与 verify 共用）"""
        coverage = crc_cfg.get('coverage', 'all')  # all, before_crc, after_header
        if coverage == 'before_crc':
            return data[:offset]
        if coverage == 'after_header':
            return data[len(self.header):offset] if self.header else data[:offset]
        return data  # 'all' 及未知值

    def _verify_crc(self, data: bytes) -> tuple[bool, dict[str, Any]]:
        """校验 CRC"""
        crc_cfg = self.template.crc
        if crc_cfg is None:
            return True, {'crc_valid': True}

        offset = crc_cfg.get('offset', 0)
        size = crc_cfg.get('size', 2)
        endianness = crc_cfg.get('endianness', 'big')
        algorithm = crc_cfg.get('algorithm', 'modbus')

        if len(data) < offset + size:
            return False, {'crc_valid': False, 'error': 'CRC 字段超出范围'}

        received_bytes = data[offset:offset + size]
        if endianness == 'little':
            received_crc = int.from_bytes(received_bytes, 'little')
        else:
            received_crc = int.from_bytes(received_bytes, 'big')

        crc_data = self._crc_coverage_data(data, crc_cfg, offset)

        if algorithm == 'xmodem':
            calculated_crc = calculate_crc16_xmodem(crc_data)
        else:
            calculated_crc = calculate_crc16_modbus(crc_data)

        return received_crc == calculated_crc, {
            'crc_valid': received_crc == calculated_crc,
            'crc_received': f"0x{received_crc:04X}",
            'crc_calculated': f"0x{calculated_crc:04X}",
        }

    def build_frame(self, **kwargs) -> bytes:
        """根据模板按 offset 布局构建帧（自动填充长度字段与 CRC）"""
        field_defs = [TemplateField.from_dict(fd) for fd in self.template.fields]

        # 1) 计算帧总长：各字段/CRC 的最大 (offset+size)，再加帧尾
        end = len(self.header)
        for fd in field_defs:
            end = max(end, fd.offset + fd.size)
        crc_cfg = self.template.crc
        if crc_cfg:
            end = max(end, crc_cfg.get('offset', 0) + crc_cfg.get('size', 2))
        total = end + len(self.tail)

        frame = bytearray(total)
        # 2) 帧头
        if self.header:
            frame[:len(self.header)] = self.header
        # 3) 字段按 offset 放置
        for fd in field_defs:
            value = kwargs.get(fd.name)
            if value is None:
                raise ValueError(f"缺少字段值: {fd.name}")
            raw = self._serialize_field(value, fd)
            if fd.offset + len(raw) > total:
                raise ValueError(f"字段 {fd.name} 超出帧范围")
            frame[fd.offset:fd.offset + len(raw)] = raw
        # 4) 长度字段：值 = 长度字段之后的字节数（与 _calculate_frame_length 约定一致）
        lf = self.template.length_field
        if lf:
            off = lf.get('offset', 0)
            size = lf.get('size', 1)
            endian = 'little' if lf.get('endianness', 'big') == 'little' else 'big'
            length_val = total - (off + size)
            frame[off:off + size] = length_val.to_bytes(size, endian)
        # 5) 帧尾
        if self.tail:
            frame[total - len(self.tail):] = self.tail
        # 6) CRC（'before_crc'/'after_header' 可往返；'all' 含 CRC 自身，不可往返）
        if crc_cfg:
            off = crc_cfg.get('offset', 0)
            size = crc_cfg.get('size', 2)
            endian = 'little' if crc_cfg.get('endianness', 'big') == 'little' else 'big'
            algorithm = crc_cfg.get('algorithm', 'modbus')
            crc_data = self._crc_coverage_data(bytes(frame), crc_cfg, off)
            calc = (calculate_crc16_xmodem(crc_data) if algorithm == 'xmodem'
                    else calculate_crc16_modbus(crc_data))
            frame[off:off + size] = calc.to_bytes(size, endian)
        return bytes(frame)

    def _serialize_field(self, value: Any, field_def: TemplateField) -> bytes:
        """序列化字段值"""
        field_type = field_def.type.lower()
        endian = '<' if field_def.endianness == 'little' else '>'

        if field_type == 'uint8':
            return bytes([int(value) & 0xFF])
        elif field_type == 'uint16':
            return struct.pack(endian + 'H', int(value))
        elif field_type == 'uint32':
            return struct.pack(endian + 'I', int(value))
        elif field_type == 'bytes':
            if isinstance(value, str):
                return bytes.fromhex(value.replace(' ', ''))
            return bytes(value)
        elif field_type == 'string':
            return str(value).encode('utf-8')
        else:
            return bytes(value)

    def get_fields_description(self) -> dict[str, str]:
        """获取字段说明"""
        return {
            f['name']: f.get('description', f"类型: {f.get('type')}")
            for f in self.template.fields
        }


# ─── 模板管理器 ──────────────────────────────────────────────

class ProtocolTemplateManager:
    """协议模板管理器"""

    def __init__(self, template_dir: str = None):
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
            if filename.endswith('.json'):
                filepath = os.path.join(self.template_dir, filename)
                template = self.load_from_file(filepath)
                if template and template.name:
                    self.templates[template.name] = template

    def load_from_file(self, filepath: str) -> ProtocolTemplate | None:
        """从文件加载模板"""
        try:
            with open(filepath, encoding='utf-8') as f:
                data = json.load(f)
            template = ProtocolTemplate.from_dict(data)
            self.templates[template.name] = template
            return template
        except Exception as e:
            print(f"加载模板失败 {filepath}: {e}")
            return None

    # Windows 保留设备名，不能作为文件名
    _RESERVED_NAMES = {
        "CON", "PRN", "AUX", "NUL",
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
        with open(filepath, 'w', encoding='utf-8') as f:
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
        length_field={
            "name": "length",
            "offset": 2,
            "size": 2,
            "endianness": "big"
        },
        fields=[
            {"name": "cmd", "type": "uint8", "offset": 4, "description": "命令字"},
            {"name": "seq", "type": "uint8", "offset": 5, "description": "序列号"},
            {
                "name": "payload",
                "type": "bytes",
                "offset": 6,
                "size": 2,
                "description": "数据载荷 (示例固定 2 字节)"
            },
        ],
        crc={
            "offset": 8,
            "size": 2,
            "endianness": "big",
            "algorithm": "modbus",
            "coverage": "before_crc"
        }
    )
