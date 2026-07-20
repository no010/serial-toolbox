"""
日志轮转管理器
按时间/大小自动切分日志文件
"""

import os
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class RotateMode(Enum):
    """轮转模式"""
    NONE = "none"          # 不轮转
    BY_SIZE = "size"       # 按大小
    BY_TIME = "time"       # 按时间
    BY_DAY = "day"         # 按天


@dataclass
class LogConfig:
    """日志配置"""
    enabled: bool = True
    log_dir: str = ""
    rotate_mode: RotateMode = RotateMode.BY_SIZE
    max_size_mb: float = 10.0      # 按大小时: 最大 MB
    rotate_interval_min: int = 60  # 按时间时: 间隔分钟
    max_files: int = 50            # 最多保留文件数
    prefix: str = "serial_log"     # 文件名前缀


class RotatingLogWriter:
    """轮转日志写入器"""

    def __init__(self, config: LogConfig | None = None):
        self.config = config or LogConfig()
        self._file = None
        self._current_path: str = ""
        self._current_size: int = 0
        self._rotate_time: float = 0
        self._total_written: int = 0

        if not self.config.log_dir:
            self.config.log_dir = os.path.join(
                os.path.expanduser("~"), ".serial-toolbox", "logs"
            )

        os.makedirs(self.config.log_dir, exist_ok=True)

        if self.config.enabled:
            self._open_new_file()

    def _generate_filename(self) -> str:
        """生成日志文件名"""
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        return os.path.join(
            self.config.log_dir,
            f"{self.config.prefix}_{ts}.log"
        )

    def _open_new_file(self):
        """打开新日志文件"""
        if self._file:
            self._file.close()

        self._current_path = self._generate_filename()
        self._file = open(self._current_path, 'a', encoding='utf-8')
        self._current_size = 0
        self._rotate_time = time.time()

        # 清理旧文件
        self._cleanup_old_files()

    def _should_rotate(self) -> bool:
        """判断是否需要轮转"""
        if self.config.rotate_mode == RotateMode.NONE:
            return False
        elif self.config.rotate_mode == RotateMode.BY_SIZE:
            max_bytes = self.config.max_size_mb * 1024 * 1024
            return self._current_size >= max_bytes
        elif self.config.rotate_mode == RotateMode.BY_TIME:
            elapsed = time.time() - self._rotate_time
            return elapsed >= self.config.rotate_interval_min * 60
        elif self.config.rotate_mode == RotateMode.BY_DAY:
            # 检查是否跨天
            file_date = datetime.fromtimestamp(self._rotate_time).date()
            now_date = datetime.now().date()
            return file_date < now_date
        return False

    def _cleanup_old_files(self):
        """清理超出数量限制的旧文件"""
        try:
            files = []
            prefix = self.config.prefix
            for f in os.listdir(self.config.log_dir):
                if f.startswith(prefix) and f.endswith('.log'):
                    full_path = os.path.join(self.config.log_dir, f)
                    files.append((full_path, os.path.getmtime(full_path)))

            # 按修改时间排序
            files.sort(key=lambda x: x[1], reverse=True)

            # 删除超出限制的
            for old_file, _ in files[self.config.max_files:]:
                os.remove(old_file)
        except Exception:
            pass

    def write(self, data: str):
        """写入日志"""
        if not self.config.enabled:
            return

        if self._should_rotate():
            self._open_new_file()

        if self._file:
            self._file.write(data)
            self._file.flush()
            self._current_size += len(data.encode('utf-8'))
            self._total_written += len(data.encode('utf-8'))

    def write_rx(self, data: bytes, hex_mode: bool = False):
        """写入接收数据"""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        if hex_mode:
            content = ' '.join(f'{b:02X}' for b in data)
        else:
            content = data.decode('utf-8', errors='replace')
        self.write(f"[{ts}] RX: {content}\n")

    def write_tx(self, data: bytes, hex_mode: bool = False):
        """写入发送数据"""
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        if hex_mode:
            content = ' '.join(f'{b:02X}' for b in data)
        else:
            content = data.decode('utf-8', errors='replace')
        self.write(f"[{ts}] TX: {content}\n")

    def get_current_path(self) -> str:
        """获取当前日志文件路径"""
        return self._current_path

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'current_file': self._current_path,
            'current_size': self._current_size,
            'total_written': self._total_written,
        }

    def flush(self):
        """刷新缓冲区"""
        if self._file:
            self._file.flush()

    def close(self):
        """关闭"""
        if self._file:
            self._file.close()
            self._file = None

    def __del__(self):
        self.close()
