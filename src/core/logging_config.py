"""
统一日志配置

各模块使用标准库 ``logging.getLogger(__name__)`` 记录日志；
应用在入口处调用 :func:`setup_logging` 一次性配置根 logger。
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False


def setup_logging(
    level: int = logging.INFO,
    log_dir: str | None = None,
    log_file: str = "serial-toolbox.log",
) -> None:
    """初始化应用日志（幂等，重复调用不会叠加 handler）。

    - 控制台：输出到 stderr
    - 文件：传入 ``log_dir`` 时启用滚动文件日志（1MB × 3 份）

    Args:
        level: 根 logger 级别
        log_dir: 日志目录；为 None 时仅输出到控制台
        log_file: 日志文件名
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):  # 清理已有 handler，避免重复输出
        root.removeHandler(handler)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    root.addHandler(console)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, log_file),
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
