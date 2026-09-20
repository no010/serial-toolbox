"""数据导出 / 配置管理 / 日志配置 测试。"""

import json
import logging

from src.core.config_manager import AppConfig, ConfigManager
from src.core.data_exporter import DataExporter
from src.core.logging_config import setup_logging

# ── DataExporter ────────────────────────────────────────────


def _sample_exporter() -> DataExporter:
    ex = DataExporter()
    ex.add_record("10:00:00", "RX", "Modbus", b"\x01\x03", {"reg": 1}, True)
    ex.add_record("10:00:01", "TX", "CAN", b"\xaa\x55", {"id": 1}, False, "CRC 错误")
    return ex


def test_exporter_stats():
    ex = _sample_exporter()
    stats = ex.get_stats()
    assert stats["count"] == 2
    assert stats["valid_count"] == 1
    assert stats["invalid_count"] == 1
    assert stats["directions"]["RX"] == 1


def test_exporter_csv(tmp_path):
    ex = _sample_exporter()
    fp = tmp_path / "out.csv"
    assert ex.export_csv(str(fp)) is True
    content = fp.read_text(encoding="utf-8")
    assert "时间戳" in content and "Modbus" in content


def test_exporter_json(tmp_path):
    ex = _sample_exporter()
    fp = tmp_path / "out.json"
    assert ex.export_json(str(fp)) is True
    data = json.loads(fp.read_text(encoding="utf-8"))
    assert data["record_count"] == 2
    assert len(data["records"]) == 2


def test_exporter_text(tmp_path):
    ex = _sample_exporter()
    fp = tmp_path / "out.txt"
    assert ex.export_text(str(fp)) is True
    assert "串口调试助手" in fp.read_text(encoding="utf-8")


def test_exporter_empty_returns_false(tmp_path):
    ex = DataExporter()
    assert ex.export_csv(str(tmp_path / "e.csv")) is False


# ── ConfigManager ───────────────────────────────────────────


def test_config_save_load_round_trip(tmp_path, monkeypatch):
    cm = ConfigManager()
    monkeypatch.setattr(cm, "CONFIG_FILE", str(tmp_path / "cfg.json"))
    cfg = AppConfig()
    cfg.baudrate = 9600
    cm.save(cfg)

    cm2 = ConfigManager()
    monkeypatch.setattr(cm2, "CONFIG_FILE", str(tmp_path / "cfg.json"))
    loaded = cm2.load()
    assert loaded.baudrate == 9600


def test_config_load_missing_returns_default(tmp_path, monkeypatch):
    cm = ConfigManager()
    monkeypatch.setattr(cm, "CONFIG_FILE", str(tmp_path / "nope.json"))
    cfg = cm.load()
    assert isinstance(cfg, AppConfig)


def test_chart_config_round_trip(tmp_path, monkeypatch):
    cm = ConfigManager()
    monkeypatch.setattr(cm, "CONFIG_FILE", str(tmp_path / "cfg.json"))
    cfg = cm.config
    cfg.chart_max_points = 1200
    cfg.chart_collect = False
    cfg.chart_x_axis = "time"
    cfg.chart_channels = [{"name": "temp", "source": "field", "key": "temp", "unit": "℃"}]
    cm.save(cfg)

    cm2 = ConfigManager()
    monkeypatch.setattr(cm2, "CONFIG_FILE", str(tmp_path / "cfg.json"))
    loaded = cm2.load()
    assert loaded.chart_max_points == 1200
    assert loaded.chart_collect is False
    assert loaded.chart_x_axis == "time"
    assert loaded.chart_channels[0]["key"] == "temp"


def test_legacy_chart_enabled_key_is_ignored(tmp_path, monkeypatch):
    """旧配置里 chart_enabled 定义了却从没人读，删除后加载不得报错，采样默认为开"""
    config_file = tmp_path / "cfg.json"
    config_file.write_text('{"chart_enabled": false, "baudrate": 9600}', encoding="utf-8")

    cm = ConfigManager()
    monkeypatch.setattr(cm, "CONFIG_FILE", str(config_file))
    cfg = cm.load()

    assert cfg.baudrate == 9600
    assert cfg.chart_collect is True


# ── logging_config ──────────────────────────────────────────


def test_setup_logging_idempotent():
    setup_logging()
    root = logging.getLogger()
    n_handlers = len(root.handlers)
    setup_logging()  # 再次调用不应叠加 handler
    assert len(root.handlers) == n_handlers


def test_setup_logging_file_handler(tmp_path):
    import src.core.logging_config as lc

    lc._initialized = False  # 重置以测试文件 handler 分支
    try:
        setup_logging(log_dir=str(tmp_path))
        names = [type(h).__name__ for h in logging.getLogger().handlers]
        assert "RotatingFileHandler" in names
    finally:
        lc._initialized = False
        setup_logging()  # 恢复为仅控制台
