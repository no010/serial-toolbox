"""应用图标路径：源码运行与 PyInstaller onefile（_MEIPASS）都能解析"""

import sys
from pathlib import Path


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ".")) / "assets" / "icons"
    return Path(__file__).resolve().parents[2] / "assets" / "icons"


def icon_file(name: str) -> Path:
    return _assets_dir() / name
