# 串口调试助手 — 交付说明 (Delivery Notes)

版本：**0.1.0**　|　分支：`feat/production-grade-delivery`　|　许可：MIT

---

## 1. 交付概述

基于 Python + PyQt6 的多功能串口调试工具，面向嵌入式开发。本次交付达到**生产级可交付基础**：
核心功能可靠、缺陷已修复、具备自动化测试、静态检查与 CI，并可打包为独立 Windows 可执行文件。

### 主要功能
- 串口管理（自动扫描、波特率/数据位/停止位/校验位配置）
- HEX / ASCII 收发、时间戳、自动滚动、字节统计、发送历史
- 协议解析：Modbus RTU + CAN / I²C / SPI / LIN / DMX512 / UART 包，以及**自定义 JSON 模板协议**
- 数据曲线图：通道可绑定原始字节流 / 协议字段 / Modbus 寄存器，支持时间轴、XY 李萨如、冻结、光标测量、CSV 导出
- Python 脚本引擎（`send` / `wait_response` / 断点）
- 多串口对比、数据导出、日志轮转、主题切换、国际化（中/英）

---

## 2. 交付物清单

| 交付物 | 说明 |
|--------|------|
| 源代码仓库 | `src/`（core / protocols / ui）+ `main.py` |
| 项目管理 | `pyproject.toml` + `uv.lock`（锁定依赖，可复现） |
| 可执行文件 | `dist/serial-toolbox.exe`（Windows x64，PyInstaller onefile，约 52 MB） |
| 打包配方 | `serial-toolbox.spec`（PyInstaller 构建脚本） |
| 测试套件 | `tests/`（111 用例，pytest） |
| CI 流水线 | `.github/workflows/ci.yml`（ruff + ty 类型检查 + pytest + Windows 打包冒烟） |
| 文档 | `README.md`、本文件 |

> `dist/`、`build/` 为构建产物，已在 `.gitignore` 中忽略，不入库。

---

## 3. 环境要求

- 运行 exe：**Windows 10/11 x64**，无需安装 Python。
- 从源码运行 / 构建：[Python 3.10+](https://www.python.org/downloads/) + [uv](https://docs.astral.sh/uv/)。

---

## 4. 安装与运行（源码）

```bash
uv sync                 # 同步运行时依赖（含 .venv）
uv sync --group dev     # 含开发依赖（ruff / pytest）

uv run serial-toolbox   # 或 uv run main.py
```

## 5. 打包构建

```bash
uv sync --group build                       # 安装 PyInstaller
uv run pyinstaller serial-toolbox.spec --noconfirm --clean
# 产物：dist/serial-toolbox.exe
```

构建要点：
- `serial-toolbox.spec` 通过 `collect_submodules('src')` 与 `collect_submodules('pyqtgraph')`
  收集运行时动态导入的模块，避免方法内 `import` 被静态分析遗漏。
- `--onefile --windowed`：单文件、无控制台窗口的 GUI 程序。
- 已验证：headless（offscreen）启动后事件循环正常存活，无缺失依赖。

## 6. 质量保障

| 项 | 状态 |
|----|------|
| 自动化测试 | `uv run pytest` → **111 passed**（协议解析器往返 / 导出 / 配置 / 日志 / 脚本引擎长度与残帧与缩进块与暂停单步 / 图表通道模型与视图 / UI 面板与线程编组 / pyserial 传输端到端） |
| 静态检查 | `uv run ruff check src/ tests/` → **All checks passed** |
| 类型检查 | `uv run ty check src/ tests/` → **All checks passed**（51 处诊断已全部修复；门禁范围含 tests/）；交叉验证 `pyright src/ tests/` → **0 error** |
| 本地钩子 | `.pre-commit-config.yaml`（ruff + ty，复用 uv 锁定版本） |
| CI | push/PR 自动跑 ruff + ty + pytest（offscreen Qt）+ Windows 打包冒烟与产物上传 |
| 依赖锁定 | `uv.lock`（`uv lock --check` 通过） |

```bash
uv run pytest -q                 # 运行测试
uv run ruff check src/ tests/    # 静态检查
```

---

## 7. 人工端到端验证清单

自动测试覆盖逻辑层；以下需在真实 GUI + 硬件上人工确认：

1. **启动**：双击 `serial-toolbox.exe`（或 `uv run serial-toolbox`）→ 主窗口正常打开，无报错弹窗。
2. **脚本引擎**：打开「Python 脚本引擎」→ 选示例「AT 指令测试」→「▶️ 运行」→ 输出区出现带时间戳日志。
3. **协议模板**：「📋 管理模板」→「示例」→「保存」→ 协议下拉出现该模板；用非法名（如 `../x`）保存应弹「保存失败」。
4. **串口收发**：连接真实串口 → HEX/ASCII 收发正常；「自动检测」喂入模板帧能解析出字段与 CRC。
5. **多串口对比**：多串口管理器 → 双口同时收发，对比面板分别显示。
6. **Modbus**：发送读保持寄存器命令，解析面板显示寄存器值。脚本引擎选示例「Modbus 轮询」→
   首行日志应为「期望 25 字节」（5 + 2×10），5 轮全部显示「轮询 #N 正常」，不出现「失联」。
7. **脚本调试控件**：运行一段多条语句的脚本 → 状态显示「运行中」→ 点「⏸ 暂停」→ 状态转
   「已暂停」且输出不再增长 → 「▶ 恢复」跑完 → 输出区末尾按实际结果打印「脚本执行完毕: 执行成功」；
   「⏭ 单步」每按一次前进一条顶层语句，「⏹ 停止」能让停在断点上的脚本退出。
8. **数据曲线图**：「📈 波形」→「＋ 通道」各建一条 Modbus 寄存器通道与一条协议字段通道 →
   真机数据进来后两条曲线出点且数值与表格一致；X 轴切「时间 (s)」后横轴变成秒；
   点「⏸ 冻结」画面不再刷新但「▶ 继续」后能看到期间累积的新点；取消「采集」后曲线停止增长；
   「导出 CSV」行数与通道采样数一致，拖动两条竖线能看到 ΔX / ΔY 读数；重启程序后通道与轴设置还在。

---

## 8. 已知限制与后续建议

非阻断，属进一步完善项：

- **代码签名**：exe 未签名，Windows SmartScreen 可能提示；正式发布建议代码签名。
- **测试覆盖**：已覆盖核心解析器往返、导出、配置、日志、脚本引擎、图表通道与 UI 构造（111 用例），
  含 pyserial socket 传输的真实收发端到端测试；可进一步补充各模块边界/异常路径与 UI 交互测试。
- **断点粒度**：脚本按顶层语句切分执行（缩进块必须整体交给 `exec`），块内断点是在整块开始
  执行前停下，做不到逐行停下；需要更细粒度得改用 `sys.settrace`。
- **断点设置入口**：断点目前只能由脚本自身 `set_breakpoint(n)` 设置，代码编辑器缺
  点击行号槽打/撤断点的交互。
- **图表单 Y 轴**：所有通道共用一条 Y 轴，量级差大的通道（如 0-255 字节值与浮点温度）混画时
  小幅度曲线会被压平；要缓解需给通道加左右轴归属（`ChannelSpec` 目前没有该字段）。通道上限 8 条。
- **跨平台打包**：当前仅构建 Windows exe；macOS/Linux 需在对应平台分别打包。

---

## 9. 目录结构

```
serial-toolbox/
├── pyproject.toml          # 项目元数据 & 依赖（uv 管理）
├── uv.lock                 # 锁定依赖版本
├── .python-version         # 固定 Python 版本
├── serial-toolbox.spec     # PyInstaller 打包配方
├── main.py                 # 主入口
├── src/
│   ├── core/               # 串口 / 协议框架 / 脚本引擎 / 导出 / 日志
│   ├── protocols/          # 内置协议解析器 + 自定义模板解析
│   └── ui/                 # PyQt6 界面
├── tests/                  # pytest 测试套件
├── .github/workflows/      # CI（ruff + pytest）
└── dist/                   # 打包产物（gitignore）
```
