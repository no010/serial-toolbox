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

### I2C 硬件扩展（CH347 / CH341）
- 基于 [ch347-py](https://github.com/pengwon/ch347-py)（MIT）调用沁恒官方库：CH347 支持
  总线扫描、寄存器读写、24C02/24C08/24C256 EEPROM 整片读写与校验；CH341 后端移植自
  [I2CTool](https://github.com/no010/I2CTool)（MIT），走 WCH 的 `CH341DLL.dll`
- 在 `~/.serial-toolbox/eeprom/` 放 JSON 可追加/覆盖 EEPROM 型号（字段同 I2CTool）
- **CH347**：Windows 需装 WCH 的 CH347 驱动（DLL 随 ch347-py 分发）；Linux 需 `ch34x_pis`
  驱动与 `libch347.so`；macOS 无官方库
- **CH341**：仅 Windows。`CH341DLL.dll` 不由本仓库分发，放到程序目录，或用环境变量
  `I2CTOOL_CH341_DLL` 指定完整路径
- 第三方许可见 [THIRD_PARTY.md](THIRD_PARTY.md)

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
# 代码格式化（pre-commit / CI 跑的是 --check，不写文件）
uv run ruff format .

# 代码检查
uv run ruff check src/ tests/

# 类型检查（ty，Astral 出品的 Rust 类型检查器）
uv run ty check src/ tests/

# 运行测试
uv run pytest

# 构建发布包（wheel / sdist）
uv build

# 安装 pre-commit 钩子（提交前自动跑 ruff format + ruff + ty）
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
6. 设置 → 主题：暗色/亮色即时切换，选择会记住

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

# 正常响应长度 = 5 + 2N（异常响应恒为 5 字节）
expected = ModbusRTU.expected_response_length(0x03, 10)  # 25
# 脚本里：resp = wait_response(timeout=0.3, expected_length=expected)
```

`expected_length` 请由 `expected_response_length()` 算出，不要写死字面量：长度小于实际帧长时，多出来的字节会留到下一次等待里，把下一帧的帧头串掉。

### Python 脚本引擎
「🐍 脚本引擎」标签页可运行 Python 脚本，注入的 API 有 `send` / `send_bytes` / `wait_response` /
`clear_response` / `sleep` / `log_info` / `log_error` / `log_success` / `assert_equal` /
`assert_contains` / `set_breakpoint`，并支持**运行 / 暂停 / 恢复 / 单步 / 停止**。

脚本按顶层语句切分执行，`for` / `if` / `def` 等缩进块作为整体运行；因此暂停、单步与断点都停在
**顶层语句边界**，块内部的断点是在整块开始执行前停下。

### 数据曲线图
「📈 波形」标签页是数据曲线图，每条**通道绑定一个数据来源**（最多 8 条）：

| 来源 | 取数方式 |
|------|----------|
| 原始字节流 | 按字节值 / int16(大端) / float32(大端) 解码接收到的每一块数据 |
| 协议字段 | 自定义 JSON 模板或内置协议解析出的字段名（下拉会列出见过的字段） |
| Modbus 寄存器 | 按寄存器地址取解析出的值（有 Float 解释时用 Float） |

配套：X 轴可切「采样点 / 时间(s)」、⏸ 冻结（只停刷新，仍在采样）与「采集」开关（停采样）、
自动缩放、XY 李萨如模式、通道配色与显隐、两条光标的 ΔX/ΔY 读数、导出 CSV。
非数值字段不会被画成假点，只累计跳过计数；通道定义与 X 轴模式随配置持久化。

### 自定义协议模板（含嵌套子帧）

「协议模板管理」用 JSON 定义帧格式，无需写 Python。基础字段按 `offset` + `size` 平铺解析，
类型有 `uint8/uint16/uint32/bytes/string`；`length_field` 让外层帧变长，`crc` 支持
`modbus/xmodem` 与 `before_crc/after_header/all` 覆盖范围。

**数据段里再套子命令 / 子数据长度 / 子数据段（TLV / 子帧）** 用 `subframe` 字段表达：

- `type: "subframe"` + `fields`：子字段偏移**相对子帧起点**，可任意深度递归；
- `size_from: "<字段名>"`：本字段字节数由同层先前解析的整数字段驱动（如子数据长度 → 子数据段）；
- `repeat: true`：把所在段按子帧块循环解析直到段尾，返回块列表（即重复 TLV）；
- 省略 `size` 的 subframe 默认**填充到 CRC/帧尾之前**；`crc.offset: "auto"` 让 CRC 紧跟字段，变长帧可往返。

```json
{
  "name": "Nested-TLV-Packet", "header": "EB 90", "tail": "0D 0A",
  "length_field": {"name": "length", "offset": 2, "size": 2, "endianness": "big"},
  "fields": [
    {"name": "cmd", "type": "uint8", "offset": 4},
    {"name": "seq", "type": "uint8", "offset": 5},
    {"name": "data_segment", "type": "subframe", "offset": 6, "repeat": true,
     "fields": [
       {"name": "sub_cmd", "type": "uint8", "offset": 0},
       {"name": "sub_len", "type": "uint8", "offset": 1},
       {"name": "sub_data", "type": "bytes", "offset": 2, "size_from": "sub_len"}
     ]}
  ],
  "crc": {"offset": "auto", "size": 2, "algorithm": "modbus", "coverage": "before_crc"}
}
```

对话框「🧩 嵌套示例」按钮可直接载入上例。把 `sub_data` 的 `type` 改成 `subframe` 并给它自己的
`fields`，就能继续往里递归。`build_frame` 会按子块实际长度自动回填 `sub_len` 与外层 `length`，
解析/构建可往返。模板表达不了的协议，仍可写 `ProtocolParserBase` 插件注册进 `ProtocolRegistry`。

> 变长嵌套帧请配外层 `length_field`：「自动检测」与流式接收靠它定界，没有长度字段时只能按
> `min_length` 当定长帧处理。截断帧、子长度谎报、`size_from` 引用缺失/非整数字段都会判为无效帧而非崩溃。

## 开发计划

- [x] 实时数据可视化（波形图）
- [x] 自定义协议解析框架（插件 + JSON 模板）
- [x] 脚本自动化（Python 脚本引擎）
- [x] 多串口同时监控
- [ ] 数据回放功能

## License

MIT
