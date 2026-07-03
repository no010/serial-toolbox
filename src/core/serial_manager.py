"""
串口管理核心模块
负责串口扫描、连接、数据收发
"""

import serial
import serial.tools.list_ports
import threading
import time
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum


class DataFormat(Enum):
    """数据格式"""
    ASCII = "ASCII"
    HEX = "HEX"


@dataclass
class SerialConfig:
    """串口配置"""
    port: str
    baudrate: int = 115200
    data_bits: int = 8
    stop_bits: int = 1
    parity: str = 'N'  # N, E, O, M, S
    flow_control: str = 'None'  # None, RTS/CTS, XON/XOFF
    timeout: float = 0.1


class SerialManager:
    """串口管理器"""
    
    def __init__(self):
        self.serial: Optional[serial.Serial] = None
        self.config: Optional[SerialConfig] = None
        self.is_connected = False
        self.read_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # 回调函数
        self.on_data_received: Optional[Callable[[bytes], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None
        self.on_connection_changed: Optional[Callable[[bool], None]] = None
    
    @staticmethod
    def scan_ports() -> List[dict]:
        """扫描可用串口"""
        ports = serial.tools.list_ports.comports()
        result = []
        for port in ports:
            result.append({
                'device': port.device,
                'name': port.name,
                'description': port.description,
                'hwid': port.hwid,
                'vid': port.vid,
                'pid': port.pid,
                'serial_number': port.serial_number,
            })
        return result
    
    def connect(self, config: SerialConfig) -> bool:
        """连接串口"""
        try:
            if self.is_connected:
                self.disconnect()
            
            self.config = config
            
            # 映射参数
            parity_map = {
                'N': serial.PARITY_NONE,
                'E': serial.PARITY_EVEN,
                'O': serial.PARITY_ODD,
                'M': serial.PARITY_MARK,
                'S': serial.PARITY_SPACE,
            }
            stop_bits_map = {
                1: serial.STOPBITS_ONE,
                1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2: serial.STOPBITS_TWO,
            }
            
            self.serial = serial.Serial(
                port=config.port,
                baudrate=config.baudrate,
                bytesize=config.data_bits,
                stopbits=stop_bits_map.get(config.stop_bits, serial.STOPBITS_ONE),
                parity=parity_map.get(config.parity, serial.PARITY_NONE),
                timeout=config.timeout,
            )
            
            # 流控
            if config.flow_control == 'RTS/CTS':
                self.serial.rtscts = True
            elif config.flow_control == 'XON/XOFF':
                self.serial.xonxoff = True
            
            self.is_connected = True
            self.stop_event.clear()
            
            # 启动接收线程
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            
            if self.on_connection_changed:
                self.on_connection_changed(True)
            
            return True
            
        except Exception as e:
            self.is_connected = False
            if self.on_error:
                self.on_error(str(e))
            return False
    
    def disconnect(self):
        """断开连接"""
        self.stop_event.set()
        
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        
        if self.serial and self.serial.is_open:
            self.serial.close()
        
        self.serial = None
        self.is_connected = False
        
        if self.on_connection_changed:
            self.on_connection_changed(False)
    
    def send(self, data: bytes) -> bool:
        """发送数据"""
        if not self.is_connected or not self.serial:
            return False
        
        try:
            self.serial.write(data)
            return True
        except Exception as e:
            if self.on_error:
                self.on_error(str(e))
            return False
    
    def send_text(self, text: str, format: DataFormat = DataFormat.ASCII) -> bool:
        """发送文本"""
        try:
            if format == DataFormat.ASCII:
                data = text.encode('utf-8')
            else:  # HEX
                # 解析十六进制字符串，支持空格分隔
                hex_str = text.replace(' ', '').replace('\n', '').replace('\r', '')
                data = bytes.fromhex(hex_str)
            return self.send(data)
        except Exception as e:
            if self.on_error:
                self.on_error(f"发送失败: {e}")
            return False
    
    def _read_loop(self):
        """接收数据循环"""
        while not self.stop_event.is_set():
            try:
                if self.serial and self.serial.is_open and self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    if data and self.on_data_received:
                        self.on_data_received(data)
                else:
                    time.sleep(0.01)
            except Exception as e:
                if self.on_error:
                    self.on_error(str(e))
                break
    
    def get_port_info(self) -> dict:
        """获取当前串口信息"""
        if not self.serial or not self.is_connected:
            return {}
        
        return {
            'port': self.serial.port,
            'baudrate': self.serial.baudrate,
            'bytesize': self.serial.bytesize,
            'stopbits': self.serial.stopbits,
            'parity': self.serial.parity,
            'rts': self.serial.rts,
            'cts': self.serial.cts,
            'dtr': self.serial.dtr,
            'dsr': self.serial.dsr,
        }
