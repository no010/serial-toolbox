"""核心模块: 串口管理、协议解析、配置管理、日志轮转、脚本引擎、协议插件、数据导出"""
from .config_manager import AppConfig, ConfigManager
from .data_exporter import DataExporter, ExportData
from .log_rotator import LogConfig, RotateMode, RotatingLogWriter
from .modbus_parser import ModbusResponse, ModbusResponseParser, RegisterValue
from .multi_serial_manager import MultiSerialManager, PortSlot
from .protocol_parser import CRC16, ModbusRTU, ProtocolParser
from .protocol_plugin import ParsedFrame, ProtocolParserBase, ProtocolRegistry, StreamProtocolParser
from .script_engine import EXAMPLE_SCRIPTS, ScriptContext, ScriptEngine, ScriptState
from .serial_manager import DataFormat, SerialConfig, SerialManager

__all__ = [
    "AppConfig",
    "ConfigManager",
    "DataExporter",
    "ExportData",
    "LogConfig",
    "RotateMode",
    "RotatingLogWriter",
    "ModbusResponse",
    "ModbusResponseParser",
    "RegisterValue",
    "MultiSerialManager",
    "PortSlot",
    "CRC16",
    "ModbusRTU",
    "ProtocolParser",
    "ParsedFrame",
    "ProtocolParserBase",
    "ProtocolRegistry",
    "StreamProtocolParser",
    "EXAMPLE_SCRIPTS",
    "ScriptContext",
    "ScriptEngine",
    "ScriptState",
    "DataFormat",
    "SerialConfig",
    "SerialManager",
]
