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
- Python 脚本引擎（`send` / `wait_response` / 断点：编辑器行号槽点击打/撤，暂停、单步、跨运行存活）
- 多串口对比、数据导出、日志轮转、主题切换（亮/暗，持久化）、国际化（中/英，运行时切换并持久化）
- I2C 调试（CH347 USB 桥）：总线扫描、寄存器读写、24 系列 EEPROM 整片读写与校验

---

## 2. 交付物清单

| 交付物 | 说明 |
|--------|------|
| 源代码仓库 | `src/`（core / protocols / ui）+ `main.py` |
| 项目管理 | `pyproject.toml` + `uv.lock`（锁定依赖，可复现） |
| 可执行文件 | `dist/serial-toolbox.exe`（Windows x64，PyInstaller onefile，约 52 MB） |
| 打包配方 | `serial-toolbox.spec`（PyInstaller 构建脚本） |
| 测试套件 | `tests/`（174 用例，pytest） |
| CI 流水线 | `.github/workflows/ci.yml`（ruff + ty 类型检查 + pytest + Windows 打包冒烟） |
| 文档 | `README.md`、本文件 |

> `dist/`、`build/` 为构建产物，已在 `.gitignore` 中忽略，不入库。

---

## 3. 环境要求

- 运行 exe：**Windows 10/11 x64**，无需安装 Python。
- 从源码运行 / 构建：[Python 3.10+](https://www.python.org/downloads/) + [uv](https://docs.astral.sh/uv/)。
- I2C 功能（可选）：CH347 USB 桥 + **WCH 官方驱动**。Windows 装厂商驱动即可（`ch347-py`
  已随包带 `CH347DLLA64.DLL`）；Linux 需 `ch34x_pis` 驱动与 `libch347.so`；macOS 无官方库。

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
- `collect_data_files('ch347', includes=['lib/*.DLL', ...])` 把厂商 DLL 原样放进
  `ch347/lib/`；适配器用 `dll_path=` 显式指定路径，不依赖 onefile 的默认 DLL 搜索路径。
- `--onefile --windowed`：单文件、无控制台窗口的 GUI 程序。
- 已验证：headless（offscreen）启动后事件循环正常存活，无缺失依赖。

## 6. 质量保障

| 项 | 状态 |
|----|------|
| 自动化测试 | `uv run pytest` → **174 passed**（协议解析器往返 / 导出 / 配置 / 日志 / 脚本引擎长度与残帧与缩进块与暂停单步与断点 / 图表通道模型与视图 / I2C 适配层与 EEPROM 分页读写 / UI 面板与行号槽与 I2C 面板与线程编组 / pyserial 传输端到端） |
| 静态检查 | `uv run ruff check src/ tests/` → **All checks passed** |
| 代码格式 | `uv run ruff format --check .` → **已统一**（ruff 默认风格；CI 与 pre-commit 均已锁定） |
| 类型检查 | `uv run ty check src/ tests/` → **All checks passed**（51 处诊断已全部修复；门禁范围含 tests/）；交叉验证 `pyright src/ tests/` → **0 error** |
| 本地钩子 | `.pre-commit-config.yaml`（ruff format + ruff check + ty，复用 uv 锁定版本） |
| CI | push/PR 自动跑 ruff format --check + ruff + ty + pytest（offscreen Qt）+ Windows 打包冒烟与产物上传 |
| 依赖锁定 | `uv.lock`（`uv lock --check` 通过） |

```bash
uv run pytest -q                 # 运行测试
uv run ruff check src/ tests/    # 静态检查
uv run ruff format .             # 就地格式化（CI 里跑的是 --check，不改文件）
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
8. **断点行号槽**：代码区左侧行号上点击出现红点断点 → 「▶ 运行」停在断点行（行号槽黄色高亮、
   状态「断点暂停」）→ 「▶ 恢复」继续；再点红点撤销断点；断点在下一次运行仍有效。
9. **数据曲线图**：「📈 波形」→「＋ 通道」各建一条 Modbus 寄存器通道与一条协议字段通道 →
   真机数据进来后两条曲线出点且数值与表格一致；X 轴切「时间 (s)」后横轴变成秒；
   点「⏸ 冻结」画面不再刷新但「▶ 继续」后能看到期间累积的新点；取消「采集」后曲线停止增长；
   「导出 CSV」行数与通道采样数一致，拖动两条竖线能看到 ΔX / ΔY 读数；重启程序后通道与轴设置还在。
10. **主题**：设置 → 主题 → 暗色/亮色即时切换，标签、菜单、分组标题在两种系统配色（OS 亮/暗）
    下都清晰可读（不再白字白底）；重启后保持上次选择。
11. **语言**：设置 → 语言 → 中文/English 即时切换，菜单、面板、对话框与状态栏整体换语言；
    重启后保持上次选择。
12. **I2C（需 CH347 硬件）**：插上 CH347 → I2C 调试页「打开设备」→「扫描总线」列出从机地址 →
    点地址回填设备地址 → 对 24C02 读一个寄存器、写几个字节后读回一致；选 24C02「读取整片」
    显示 256 字节 → 把 256 字节 hex 填入数据框「写入整片」→「校验」通过；未接从机时应报
    「无应答」而不是静默成功。在 `~/.serial-toolbox/eeprom/` 放一个 `24c64.json` 重启后，
    型号下拉应出现 24C64。

---

## 8. 已知限制与后续建议

非阻断，属进一步完善项：

- **代码签名**：exe 未签名，Windows SmartScreen 可能提示；正式发布建议代码签名。
- **测试覆盖**：已覆盖核心解析器往返、导出、配置、日志、脚本引擎（含断点跨运行存活）、图表通道、
  I2C 适配层与 EEPROM 分页读写（仿真总线）、i18n 与 UI 构造（174 用例），
  含 pyserial socket 传输的真实收发端到端测试；CH347 只验到适配器的帧构造层，真机路径需人工确认。
- **断点粒度**：脚本按顶层语句切分执行（缩进块必须整体交给 `exec`），块内断点是在整块开始
  执行前停下，做不到逐行停下；需要更细粒度得改用 `sys.settrace`。
- **断点不随会话持久化**：行号槽断点存在引擎内存里，重启程序后需重新点击设置。
- **图表 Y 轴**：通道可分属左/右两条 Y 轴（通道属性里选择），但每条轴仍只有一条量程，
  同轴上量级差大的通道混画仍会互相压平；右轴通道暂不进图例（通道栏有色块可辨认）。通道上限 8 条。
- **跨平台打包**：当前仅构建 Windows exe；macOS/Linux 需在对应平台分别打包。
- **I2C 仅 CH347**：面板只支持 CH347 USB 桥（ch347-py 的厂商库只发 Windows/Linux），
  macOS 不可用；SPI/GPIO 尚未接入面板。CH341 后端待上游 i2ctool 实现推送后再移植。
- **EEPROM 型号**：内置 24C02/24C08/24C256，可在 `~/.serial-toolbox/eeprom/` 放 JSON
  追加新型号或按 `id` 覆盖内置（字段同 I2CTool：`id/name/size_bytes/address_width/
  page_size/write_cycle_ms/notes`），改完重启生效。
- **I2C 操作不可中断**：整片写入期间按钮禁用但无法中途取消（32 KB 全片写约数秒）。

---

## 9. 目录结构

```
serial-toolbox/
├── pyproject.toml          # 项目元数据 & 依赖（uv 管理）
├── uv.lock                 # 锁定依赖版本
├── .python-version         # 固定 Python 版本
├── serial-toolbox.spec     # PyInstaller 打包配方
├── LICENSE                 # MIT
├── THIRD_PARTY.md          # ch347-py / I2CTool 的 MIT 许可与出处
├── main.py                 # 主入口
├── src/
│   ├── core/               # 串口 / 协议框架 / 脚本引擎 / 导出 / 日志 / I2C 总线与 EEPROM
│   ├── protocols/          # 内置协议解析器 + 自定义模板解析
│   └── ui/                 # PyQt6 界面
├── tests/                  # pytest 测试套件
├── .github/workflows/      # CI（ruff + pytest）
└── dist/                   # 打包产物（gitignore）
```
