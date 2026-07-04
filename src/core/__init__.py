"""核心模块: 串口管理、协议解析、配置管理、日志轮转、脚本引擎、协议插件"""
from .serial_manager import SerialManager, SerialConfig, DataFormat
from .protocol_parser import ModbusRTU, CRC16, ProtocolParser
from .config_manager import ConfigManager, AppConfig
from .modbus_parser import ModbusResponseParser, ModbusResponse, RegisterValue
from .log_rotator import RotatingLogWriter, LogConfig, RotateMode
from .script_engine import ScriptEngine, ScriptState, EXAMPLE_SCRIPTS, ScriptContext
from .multi_serial_manager import MultiSerialManager, PortSlot
from .protocol_plugin import ProtocolRegistry, StreamProtocolParser, ParsedFrame, ProtocolParserBase
