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
- Python 3.11+
- PyQt6 (GUI)
- pyserial (串口通信)
- pyqtgraph (实时绘图，预留接口)

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 项目结构

```
serial-toolbox/
├── main.py                 # 主入口
├── requirements.txt        # 依赖
├── src/
│   ├── core/
│   │   ├── serial_manager.py      # 串口管理
│   │   └── protocol_parser.py     # 协议解析
│   └── ui/
│       └── main_window.py         # 主窗口 UI
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
