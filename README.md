# 串口调试助手 (Serial Toolbox)

基于 Python + PyQt6 的多功能串口调试工具，适用于嵌入式开发。

## 功能特性

### 核心功能
- **串口管理**: 自动扫描、连接配置（波特率、数据位、停止位、校验位）
- **数据收发**: 支持 HEX/ASCII 格式切换
- **协议解析**: 内置 Modbus RTU 协议支持
- **实时显示**: 时间戳、自动滚动、字节统计
- **发送历史**: 记录最近 20 条发送数据
- **数据导出**: 日志导出为文本文件

### 技术栈
- Python 3.10+
- PyQt6 (GUI)
- pyserial (串口通信)
- pyqtgraph (实时绘图，预留接口)

## 环境要求

- [Python 3.10+](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/)（推荐的包/项目管理工具）

```bash
# 安装 uv（Windows PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 安装

本项目使用 **uv** 进行项目管理，依赖在 `pyproject.toml` 中声明，并由 `uv.lock` 锁定版本。

```bash
# 同步运行时依赖（自动创建 .venv 并安装锁定版本）
uv sync

# 同时安装开发依赖（ruff / pytest）
uv sync --group dev
```

> 如不使用 uv，也可回退到传统方式：`pip install -r requirements.txt`

## 运行

```bash
# 方式一：直接运行入口脚本
uv run main.py

# 方式二：使用已注册的控制台命令
uv run serial-toolbox
```

## 开发与构建

```bash
# 代码检查
uv run ruff check src/

# 类型检查（ty，Astral 出品的 Rust 类型检查器）
uv run ty check src/

# 运行测试
uv run pytest

# 构建发布包（wheel / sdist）
uv build

# 安装 pre-commit 钩子（提交前自动跑 ruff + ty）
pip install pre-commit && pre-commit install
```

## 打包为可执行文件

```bash
uv sync --group build
uv run pyinstaller serial-toolbox.spec --noconfirm --clean
# 产物：dist/serial-toolbox.exe（Windows 单文件 GUI，无需安装 Python）
```

> 完整的交付说明、端到端验证清单与已知限制见 [DELIVERY.md](DELIVERY.md)。

## 项目结构

```
serial-toolbox/
├── pyproject.toml          # 项目元数据 & 依赖（uv 管理）
├── uv.lock                 # 锁定依赖版本（提交到仓库）
├── .python-version         # 固定 Python 版本
├── main.py                 # 主入口
├── requirements.txt        # 依赖（非 uv 用户的回退方案）
├── src/
│   ├── core/                      # 核心：串口/协议/脚本/导出
│   ├── protocols/                 # 内置协议解析器 & 模板解析
│   └── ui/                        # PyQt6 界面
└── scripts/                # 脚本工具
```

## 使用说明

### 基本操作
1. 选择串口、配置参数（波特率等）
2. 点击"连接"按钮
3. 在发送区输入数据，选择格式（HEX/ASCII）
4. 点击"发送"或按回车
5. 接收区显示返回数据

### HEX 模式
- **HEX 发送**: 输入十六进制字符串（如 `01 02 03` 或 `010203`）
- **HEX 显示**: 接收数据以十六进制格式显示

### Modbus RTU
内置 Modbus RTU 协议支持，可发送标准 Modbus 命令：

```python
from src.core.protocol_parser import ModbusRTU

# 读取保持寄存器（从机地址 1，起始地址 0，数量 10）
frame = ModbusRTU.build_read_holding_registers(1, 0, 10)
# 发送 frame
```

## 开发计划

- [ ] 实时数据可视化（波形图）
- [ ] 自定义协议解析框架
- [ ] 脚本自动化（Python 脚本引擎）
- [ ] 多串口同时监控
- [ ] 数据回放功能

## License

MIT
