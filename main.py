#!/usr/bin/env python3
"""
串口调试助手 - Serial Toolbox
主入口文件
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.logging_config import setup_logging
from src.ui.main_window import main

if __name__ == '__main__':
    setup_logging()
    main()
