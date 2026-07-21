"""
配置管理模块
保存/加载用户设置 (JSON)
"""

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """应用配置"""
    # 串口默认配置
    last_port: str = ""
    baudrate: int = 115200
    data_bits: int = 8
    stop_bits: float = 1
    parity: str = "None"

    # 显示配置
    hex_receive: bool = False
    hex_send: bool = False
    show_timestamp: bool = True
    auto_scroll: bool = True
    send_newline: bool = True

    # 自动发送
    auto_send_interval: int = 1000

    # 预设指令列表 [{name, data, is_hex}]
    presets: list = field(default_factory=lambda: [
        {"name": "AT 测试", "data": "AT\r\n", "is_hex": False},
        {"name": "Modbus 读寄存器", "data": "01 03 00 00 00 01", "is_hex": True},
    ])

    # 窗口几何
    window_x: int = 100
    window_y: int = 100
    window_w: int = 1000
    window_h: int = 700

    # 波形图配置
    chart_max_points: int = 500
    chart_enabled: bool = False


class ConfigManager:
    """配置管理器"""

    CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".serial-toolbox")
    CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

    def __init__(self):
        self.config = AppConfig()
        self._ensure_dir()

    def _ensure_dir(self):
        """确保配置目录存在"""
        os.makedirs(self.CONFIG_DIR, exist_ok=True)

    def load(self) -> AppConfig:
        """加载配置"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, encoding='utf-8') as f:
                    data = json.load(f)
                # 用加载的数据更新默认配置（保留新增字段的默认值）
                for key, value in data.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
        except Exception:
            logger.exception("加载配置失败")
        return self.config

    def save(self, config: AppConfig | None = None):
        """保存配置"""
        if config:
            self.config = config
        try:
            with open(self.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(asdict(self.config), f, ensure_ascii=False, indent=2)
        except Exception:
            logger.exception("保存配置失败")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return getattr(self.config, key, default)

    def set(self, key: str, value: Any):
        """设置配置项"""
        if hasattr(self.config, key):
            setattr(self.config, key, value)
