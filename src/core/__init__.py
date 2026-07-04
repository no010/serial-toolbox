"""核心模块: 串口管理、协议解析、配置管理"""
from .serial_manager import SerialManager, SerialConfig, DataFormat
from .protocol_parser import ModbusRTU, CRC16, ProtocolParser
from .config_manager import ConfigManager, AppConfig
