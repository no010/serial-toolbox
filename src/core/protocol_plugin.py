"""
协议插件框架
支持自定义协议解析器，插件化扩展
"""

from typing import Optional, Callable, Dict, Any, List
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from datetime import datetime


@dataclass
class ParsedFrame:
    """解析后的帧"""
    protocol: str  # 协议名称
    timestamp: str = ""
    raw_data: bytes = b''
    fields: Dict[str, Any] = field(default_factory=dict)
    is_valid: bool = True
    error_msg: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    
    def get_field(self, name: str, default=None):
        """获取字段值"""
        return self.fields.get(name, default)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'protocol': self.protocol,
            'timestamp': self.timestamp,
            'raw_hex': ' '.join(f'{b:02X}' for b in self.raw_data),
            'fields': self.fields,
            'is_valid': self.is_valid,
            'error_msg': self.error_msg,
        }


class ProtocolParserBase(ABC):
    """协议解析器基类"""
    
    name: str = "Unknown"
    description: str = ""
    
    @abstractmethod
    def parse(self, data: bytes) -> Optional[ParsedFrame]:
        """
        解析数据帧
        
        Args:
            data: 原始字节数据
        
        Returns:
            解析后的帧，如果数据不完整返回 None
        """
        pass
    
    @abstractmethod
    def detect_frame(self, data: bytes) -> tuple[bool, int]:
        """
        检测数据中是否包含完整帧
        
        Returns:
            (is_complete, frame_length) - 是否完整，帧长度
        """
        pass
    
    def build_frame(self, **kwargs) -> bytes:
        """构建帧 (可选实现)"""
        raise NotImplementedError(f"{self.name} 不支持构建帧")
    
    def get_fields_description(self) -> Dict[str, str]:
        """获取字段说明"""
        return {}


class ProtocolRegistry:
    """协议注册表"""
    
    def __init__(self):
        self.parsers: Dict[str, ProtocolParserBase] = {}
        self._register_built_in()
    
    def _register_built_in(self):
        """注册内置协议"""
        from src.protocols.can_parser import CANParser
        from src.protocols.i2c_parser import I2CParser
        from src.protocols.uart_packet_parser import UARTPacketParser
        
        self.register(CANParser())
        self.register(I2CParser())
        self.register(UARTPacketParser())
    
    def register(self, parser: ProtocolParserBase):
        """注册协议解析器"""
        self.parsers[parser.name] = parser
    
    def unregister(self, name: str):
        """注销协议解析器"""
        if name in self.parsers:
            del self.parsers[name]
    
    def get_parser(self, name: str) -> Optional[ProtocolParserBase]:
        """获取协议解析器"""
        return self.parsers.get(name)
    
    def list_protocols(self) -> List[str]:
        """列出所有协议"""
        return list(self.parsers.keys())
    
    def auto_detect(self, data: bytes) -> Optional[str]:
        """自动检测协议"""
        for name, parser in self.parsers.items():
            is_complete, _ = parser.detect_frame(data)
            if is_complete:
                return name
        return None


# ─── 协议流解析器 ────────────────────────────────────────────

class StreamProtocolParser:
    """流式协议解析器 - 从字节流中自动识别并解析帧"""
    
    def __init__(self, registry: ProtocolRegistry):
        self.registry = registry
        self.buffer = bytearray()
        self.active_protocol: Optional[str] = None
    
    def feed(self, data: bytes) -> List[ParsedFrame]:
        """喂入数据，返回解析到的帧列表"""
        self.buffer.extend(data)
        frames = []
        
        # 如果已确定协议，直接解析
        if self.active_protocol:
            parser = self.registry.get_parser(self.active_protocol)
            if parser:
                while True:
                    is_complete, frame_len = parser.detect_frame(bytes(self.buffer))
                    if is_complete and frame_len > 0:
                        frame_data = bytes(self.buffer[:frame_len])
                        parsed = parser.parse(frame_data)
                        if parsed:
                            frames.append(parsed)
                        del self.buffer[:frame_len]
                    else:
                        break
        else:
            # 自动检测
            for name in self.registry.list_protocols():
                parser = self.registry.get_parser(name)
                if parser:
                    is_complete, frame_len = parser.detect_frame(bytes(self.buffer))
                    if is_complete and frame_len > 0:
                        self.active_protocol = name
                        frame_data = bytes(self.buffer[:frame_len])
                        parsed = parser.parse(frame_data)
                        if parsed:
                            frames.append(parsed)
                        del self.buffer[:frame_len]
                        break
        
        return frames
    
    def set_protocol(self, name: str):
        """手动设置协议"""
        self.active_protocol = name
    
    def clear(self):
        """清空缓冲"""
        self.buffer.clear()
        self.active_protocol = None
