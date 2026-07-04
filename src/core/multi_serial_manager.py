"""
多串口管理器
支持同时管理多个串口连接
"""

import threading
from typing import Dict, Optional, Callable, List
from dataclasses import dataclass
from src.core.serial_manager import SerialManager, SerialConfig


@dataclass
class PortSlot:
    """串口槽位"""
    name: str  # 槽位名称 (如 "Port A", "Port B")
    manager: SerialManager
    config: Optional[SerialConfig] = None
    is_active: bool = False  # 是否激活用于对比


class MultiSerialManager:
    """多串口管理器"""
    
    MAX_PORTS = 4  # 最多支持4个串口
    
    def __init__(self):
        self.slots: Dict[str, PortSlot] = {}
        self.on_data_received: Optional[Callable[[str, bytes], None]] = None
        self.on_error: Optional[Callable[[str, str], None]] = None
        self.on_connection_changed: Optional[Callable[[str, bool], None]] = None
        
        # 初始化默认槽位
        for i in range(self.MAX_PORTS):
            name = f"Port {chr(65 + i)}"  # Port A, Port B, Port C, Port D
            manager = SerialManager()
            self.slots[name] = PortSlot(name=name, manager=manager)
    
    def get_slot(self, name: str) -> Optional[PortSlot]:
        """获取槽位"""
        return self.slots.get(name)
    
    def connect(self, slot_name: str, config: SerialConfig) -> bool:
        """连接指定槽位的串口"""
        slot = self.slots.get(slot_name)
        if not slot:
            return False
        
        # 设置回调
        slot.manager.on_data_received = lambda data, sn=slot_name: self._on_data(sn, data)
        slot.manager.on_error = lambda err, sn=slot_name: self._on_error(sn, err)
        slot.manager.on_connection_changed = lambda conn, sn=slot_name: self._on_connection(sn, conn)
        
        slot.config = config
        result = slot.manager.connect(config)
        return result
    
    def disconnect(self, slot_name: str):
        """断开指定槽位"""
        slot = self.slots.get(slot_name)
        if slot:
            slot.manager.disconnect()
    
    def disconnect_all(self):
        """断开所有"""
        for slot in self.slots.values():
            slot.manager.disconnect()
    
    def send(self, slot_name: str, data: bytes) -> bool:
        """发送数据到指定槽位"""
        slot = self.slots.get(slot_name)
        if slot and slot.manager.is_connected:
            return slot.manager.send(data)
        return False
    
    def send_to_all(self, data: bytes) -> Dict[str, bool]:
        """发送数据到所有激活槽位"""
        results = {}
        for name, slot in self.slots.items():
            if slot.is_active and slot.manager.is_connected:
                results[name] = slot.manager.send(data)
        return results
    
    def set_active(self, slot_name: str, active: bool):
        """设置槽位是否激活 (用于对比)"""
        slot = self.slots.get(slot_name)
        if slot:
            slot.is_active = active
    
    def get_connected_slots(self) -> List[str]:
        """获取已连接的槽位名称"""
        return [name for name, slot in self.slots.items() if slot.manager.is_connected]
    
    def get_active_slots(self) -> List[str]:
        """获取激活的槽位名称"""
        return [name for name, slot in self.slots.items() if slot.is_active]
    
    def _on_data(self, slot_name: str, data: bytes):
        """数据接收回调"""
        if self.on_data_received:
            self.on_data_received(slot_name, data)
    
    def _on_error(self, slot_name: str, error: str):
        """错误回调"""
        if self.on_error:
            self.on_error(slot_name, error)
    
    def _on_connection(self, slot_name: str, connected: bool):
        """连接状态变化回调"""
        if self.on_connection_changed:
            self.on_connection_changed(slot_name, connected)
