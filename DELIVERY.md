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
| 测试套件 | `tests/`（21 用例，pytest） |
| CI 流水线 | `.github/workflows/ci.yml`（ruff + pytest） |
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
| 自动化测试 | `uv run pytest` → **21 passed** |
| 静态检查 | `uv run ruff check src/ tests/` → **All checks passed** |
| 类型检查 | `uv run ty check src/` → **All checks passed**（51 处诊断已全部修复） |
| CI | push/PR 自动跑 ruff + ty + pytest（offscreen Qt） |
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
6. **Modbus**：发送读保持寄存器命令，解析面板显示寄存器值。

---

## 8. 已知限制与后续建议

非阻断，属进一步完善项：

- **代码签名**：exe 未签名，Windows SmartScreen 可能提示；正式发布建议代码签名。
- **日志系统**：仍以 `print` 输出为主，建议迁移到 `logging`（分级、落盘）。
- **测试覆盖**：当前聚焦核心解析/脚本/UI 构造，建议扩充各协议解析器与导出/配置模块的测试。
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
