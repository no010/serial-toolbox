"""
国际化模块
支持中英文切换
"""

from enum import Enum


class Language(Enum):
    """语言"""

    CHINESE = "zh"
    ENGLISH = "en"


# 翻译字典
TRANSLATIONS: dict[Language, dict[str, str]] = {
    Language.CHINESE: {
        # 主窗口
        "app_title": "串口调试助手 - Serial Toolbox v4.0",
        # 菜单
        "menu_file": "文件(&F)",
        "menu_export": "导出日志(&E)",
        "menu_exit": "退出(&X)",
        "menu_settings": "设置(&S)",
        "menu_clear": "清空显示(&C)",
        "menu_log_settings": "日志设置...",
        "menu_save_config": "保存配置",
        "menu_theme": "主题(&T)",
        "menu_theme_light": "亮色",
        "menu_theme_dark": "暗色",
        "menu_language": "语言(&L)",
        "menu_lang_zh": "中文",
        "menu_lang_en": "English",
        "menu_multi_port": "多串口管理器...",
        "menu_help": "帮助(&H)",
        "menu_about": "关于(&A)",
        # 串口配置
        "group_serial_config": "串口配置",
        "label_port": "串口:",
        "btn_refresh": "🔄 刷新",
        "label_baudrate": "波特率:",
        "label_databits": "数据位:",
        "label_stopbits": "停止位:",
        "label_parity": "校验:",
        "btn_connect": "连接",
        "btn_disconnect": "断开",
        # 信号线控制
        "group_signal_control": "信号线控制",
        "label_input_status": "输入状态:",
        # 接收区
        "tab_text": "📝 文本",
        "tab_chart": "📈 波形",
        "tab_modbus": "🔢 Modbus解析",
        "tab_protocol": "🔌 协议解析",
        "check_hex_display": "HEX 显示",
        "check_timestamp": "显示时间戳",
        "check_auto_scroll": "自动滚动",
        "btn_clear": "清空",
        # 协议解析
        "label_select_protocol": "选择协议:",
        "auto_detect": "自动检测",
        "btn_manage_templates": "📋 管理模板",
        "proto_col_time": "时间",
        "proto_col_protocol": "协议",
        "proto_col_field": "字段",
        "proto_col_value": "值",
        "proto_col_raw": "原始数据",
        # 发送区
        "group_send": "数据发送",
        "check_hex_send": "HEX 发送",
        "check_newline": "发送新行",
        "check_auto_send": "自动发送",
        "label_interval": "间隔(ms):",
        "label_history": "发送历史:",
        "placeholder_send": "输入要发送的数据...",
        "btn_send": "发送",
        # 预设指令
        "group_presets": "预设指令",
        "col_name": "名称",
        "col_data": "数据",
        "col_hex": "HEX",
        "btn_add": "➕ 添加",
        "btn_edit": "✏️ 编辑",
        "btn_delete": "🗑️ 删除",
        "btn_send_selected": "📤 发送选中",
        # Modbus 快捷操作
        "group_modbus": "Modbus RTU 快捷操作",
        "label_slave_addr": "从机地址:",
        "label_func_code": "功能码:",
        "label_start_addr": "起始地址:",
        "label_quantity": "数量/值:",
        "label_reg_values": "寄存器值 (逗号分隔):",
        "placeholder_reg_values": "例: 100, 200, 300",
        "btn_read": "📖 读取",
        "btn_write": "✏️ 写入",
        "btn_crc": "🔢 CRC 计算",
        "func_03_read_holding": "0x03 读保持寄存器",
        "func_04_read_input": "0x04 读输入寄存器",
        "func_06_write_single": "0x06 写单个寄存器",
        "func_10_write_multi": "0x10 写多个寄存器",
        "crc_frame_prefix": "帧:",
        "crc_label": "CRC:",
        # Modbus 响应解析
        "group_modbus_response": "Modbus 响应解析",
        "label_auto_detect": "自动检测 Modbus 帧并解析寄存器值",
        "col_time": "时间",
        "col_slave": "从机",
        "col_func": "功能码",
        "col_reg_addr": "寄存器地址",
        "col_raw": "原始值",
        "col_signed": "有符号值",
        "label_reg_detail": "寄存器详情:",
        "col_address": "地址",
        "col_hex_value": "HEX",
        "col_dec": "DEC (有符号)",
        "col_float": "Float (IEEE754)",
        "func_03": "读保持寄存器",
        "func_04": "读输入寄存器",
        "func_06": "写单个寄存器",
        "func_10": "写多个寄存器",
        "func_01": "读线圈",
        "func_02": "读离散输入",
        "func_05": "写单个线圈",
        "func_0f": "写多个线圈",
        "func_error": "错误",
        "func_unknown": "未知",
        "text_write_op": "写操作",
        "text_error_prefix": "错误:",
        # 脚本引擎
        "tab_script": "🐍 脚本引擎",
        "group_script": "Python 脚本引擎",
        "label_example": "示例脚本:",
        "btn_run": "▶️ 运行",
        "btn_pause": "⏸ 暂停",
        "btn_resume": "▶ 恢复",
        "btn_step": "⏭ 单步",
        "btn_stop": "⏹ 停止",
        "btn_clear_output": "清空输出",
        "label_output": "输出:",
        "label_status_prefix": "状态:",
        "status_idle": "空闲",
        "status_running": "运行中",
        "status_paused": "已暂停",
        "status_stopped": "已结束",
        "status_error": "出错",
        "status_breakpoint": "断点暂停",
        "script_finished_ok": "脚本执行完毕: {}",
        "script_finished_fail": "脚本执行失败: {}",
        "script_no_manager": "未提供串口管理器，脚本引擎不可用",
        # 多串口对比
        "tab_compare": "🔀 多串口对比",
        "group_compare": "多串口对比",
        "btn_clear_all": "清空全部",
        "btn_slot_connect": "连接",
        "slot_placeholder": "{} - 未连接",
        "title_hint": "提示",
        "msg_slot_hint": "请在主界面配置 {} 的串口参数\n多串口完整配置功能开发中...",
        # 波形图
        "label_mode": "模式:",
        "mode_yt": "YT (时域)",
        "mode_xy": "XY (李萨如)",
        "label_x_axis": "  X 轴:",
        "x_axis_index": "采样点",
        "x_axis_time": "时间 (s)",
        "xy_x_label": " X:",
        "xy_y_label": " Y:",
        "label_points": "  点数:",
        "check_autoscale": "自动缩放",
        "check_grid": "网格",
        "check_collect": "采集",
        "tip_collect": "关闭后不再采样；冻结只是暂停刷新，仍在采样",
        "btn_freeze": "⏸ 冻结",
        "btn_unfreeze": "▶ 继续",
        "btn_export_csv": "导出 CSV",
        "btn_clear_chart": "清空",
        "btn_add_channel": "＋ 通道",
        "label_channel": "通道:",
        "cursor_hint": "光标: 拖动竖线测量 ΔX / ΔY",
        "cursor_no_channel": "光标: 无可见通道",
        "cursor_fmt": "光标: ΔX={:.3f} {}   Δ{}={:+.4g}{}",
        "unit_point": "点",
        "unit_ms": "ms",
        "axis_value": "数值",
        "axis_sample": "采样点",
        "axis_time": "时间 (s)",
        "axis_y_channel": "Y 通道",
        "axis_x_channel": "X 通道",
        "dialog_export_csv": "导出曲线数据",
        "csv_filter": "CSV (*.csv)",
        "msg_exported": "已写出 {} 行\n{}",
        "msg_max_channels": "最多 {} 个通道",
        # 通道属性对话框
        "dialog_channel_spec": "通道属性",
        "label_ch_name": "名称",
        "label_ch_source": "来源",
        "src_raw": "原始字节流",
        "src_field": "协议字段",
        "src_register": "Modbus 寄存器",
        "label_ch_dtype": "解码",
        "dtype_uint8": "字节值 (0-255)",
        "dtype_int16": "整数 int16 (大端有符号)",
        "dtype_float32": "浮点 float32 (大端)",
        "label_ch_key": "字段/地址",
        "label_ch_unit": "单位",
        "label_ch_scale": "值 × 缩放",
        "label_ch_offset": "+ 偏移",
        "err_name_empty": "名称不能为空",
        "err_name_dup": "通道名 {} 已存在",
        "err_key_empty": "请填写字段名或寄存器地址",
        # 状态栏
        "status_disconnected": "未连接",
        "status_connected": "已连接: {}",
        "status_log_off": "日志: 关闭",
        "status_log_on": "日志: {}",
        "rx_bytes": "RX: {} bytes",
        "tx_bytes": "TX: {} bytes",
        # 通用对话框
        "title_warning": "警告",
        "title_error": "错误",
        "title_success": "成功",
        "title_serial_error": "串口错误",
        # 消息
        "msg_no_port": "没有可用的串口",
        "msg_connect_failed": "串口连接失败",
        "msg_not_connected": "串口未连接",
        "msg_please_connect": "请先连接串口",
        "msg_export_success": "日志已导出到:\n{}",
        "msg_config_saved": "配置已保存",
        # 预设编辑对话框
        "dialog_preset_edit": "编辑预设指令",
        "label_name": "名称:",
        "label_data_content": "数据:",
        "placeholder_name": "指令名称",
        "placeholder_data": "指令内容 (ASCII 或 HEX)",
        "check_hex_format": "HEX 格式",
        # 日志设置对话框
        "dialog_log_settings": "日志设置",
        "check_enable_log": "启用自动日志记录",
        "label_log_dir": "日志目录:",
        "btn_browse": "浏览...",
        "label_rotate_mode": "轮转模式:",
        "rotate_none": "不轮转",
        "rotate_size": "按大小",
        "rotate_time": "按时间",
        "rotate_day": "按天",
        "label_max_size": "最大文件大小:",
        "label_rotate_interval": "轮转间隔:",
        "label_max_files": "最多保留文件:",
        "title_browse_log_dir": "选择日志目录",
        "suffix_minutes": " 分钟",
        # 多串口管理器
        "dialog_multi_port": "多串口管理器",
        "title_multi_port": "🔀 多串口管理器 (最多4路)",
        "dialog_port_config_group": "串口参数",
        "label_parity_col": "校验位:",
        "label_flow_control": "流控:",
        "status_dot_disconnected": "● 未连接",
        "btn_configure": "⚙️ 配置",
        "btn_compare": "📊 对比",
        "btn_connect_all": "🔗 全部连接",
        "btn_disconnect_all": "⛓️‍💥 全部断开",
        "btn_close": "关闭",
        "dialog_port_config": "配置 {}",
        "title_port_config": "🔌 {} 串口配置",
        "msg_port_connected_fail": "{} 连接失败",
        "msg_connect_all_done": "已连接 {} 个串口",
        "msg_not_configured": '{} 未配置，请先点击"配置"按钮',
        "msg_config_saved_detail": "{} 配置已保存\n端口: {}\n波特率: {}",
        "msg_connected_count": "已连接 {} 个串口",
        # 协议模板管理
        "dialog_template_mgmt": "协议模板管理",
        "desc_templates": "通过 JSON 模板定义自定义协议帧格式，无需编写 Python 代码",
        "label_loaded_templates": "已加载模板:",
        "btn_new": "➕ 新建",
        "btn_sample": "📋 示例",
        "label_template_json": "模板 JSON:",
        "label_preview": "预览:",
        "title_confirm_delete": "确认删除",
        "msg_confirm_delete": '确定删除模板 "{}" 吗？',
        "msg_template_saved": '模板 "{}" 已保存',
        "title_save_success": "保存成功",
        "title_save_fail": "保存失败",
        "msg_json_error": "JSON 格式错误: {}",
        "err_template_name": "模板名称不能为空",
        "pv_name": "协议名称:",
        "pv_desc": "描述:",
        "pv_header": "帧头:",
        "pv_tail": "帧尾:",
        "pv_min_len": "最小长度:",
        "pv_fields": "字段列表:",
        "pv_none": "(无)",
        "pv_no_fields": "(无字段定义)",
        # 关于
        "about_title": "关于",
        "about_text": """串口调试助手 v4.0

功能:
• 串口通信 (HEX/ASCII 切换)
• 增强波形图 (数据通道 + XY 李萨如)
• Modbus RTU 响应自动解析
• 协议插件框架 (CAN/I2C/SPI/LIN/DMX512/UART-Packet)
• 预设指令管理
• DTR/RTS 信号线控制
• Modbus RTU 快捷操作
• 自动发送 (定时)
• 日志轮转 (按大小/时间/天)
• Python 脚本引擎 (断点/wait_response)
• 多串口对比 (最多4路)
• 多串口管理器 (独立配置)
• 数据导出 (CSV)
• 主题切换 (亮色/暗色)
• 界面语言 (中/英文)
• 配置保存/加载

基于 PyQt6 + pyqtgraph 开发""",
    },
    Language.ENGLISH: {
        # Main Window
        "app_title": "Serial Toolbox v4.0",
        # Menu
        "menu_file": "File(&F)",
        "menu_export": "Export Log(&E)",
        "menu_exit": "Exit(&X)",
        "menu_settings": "Settings(&S)",
        "menu_clear": "Clear Display(&C)",
        "menu_log_settings": "Log Settings...",
        "menu_save_config": "Save Config",
        "menu_theme": "Theme(&T)",
        "menu_theme_light": "Light",
        "menu_theme_dark": "Dark",
        "menu_language": "Language(&L)",
        "menu_lang_zh": "中文",
        "menu_lang_en": "English",
        "menu_multi_port": "Multi-Port Manager...",
        "menu_help": "Help(&H)",
        "menu_about": "About(&A)",
        # Serial Config
        "group_serial_config": "Serial Configuration",
        "label_port": "Port:",
        "btn_refresh": "🔄 Refresh",
        "label_baudrate": "Baudrate:",
        "label_databits": "Data Bits:",
        "label_stopbits": "Stop Bits:",
        "label_parity": "Parity:",
        "btn_connect": "Connect",
        "btn_disconnect": "Disconnect",
        # Signal Control
        "group_signal_control": "Signal Control",
        "label_input_status": "Input Status:",
        # Receive Area
        "tab_text": "📝 Text",
        "tab_chart": "📈 Chart",
        "tab_modbus": "🔢 Modbus",
        "tab_protocol": "🔌 Protocol",
        "check_hex_display": "HEX Display",
        "check_timestamp": "Timestamp",
        "check_auto_scroll": "Auto Scroll",
        "btn_clear": "Clear",
        # Protocol
        "label_select_protocol": "Protocol:",
        "auto_detect": "Auto Detect",
        "btn_manage_templates": "📋 Templates",
        "proto_col_time": "Time",
        "proto_col_protocol": "Protocol",
        "proto_col_field": "Field",
        "proto_col_value": "Value",
        "proto_col_raw": "Raw Data",
        # Send Area
        "group_send": "Data Send",
        "check_hex_send": "HEX Send",
        "check_newline": "New Line",
        "check_auto_send": "Auto Send",
        "label_interval": "Interval(ms):",
        "label_history": "History:",
        "placeholder_send": "Enter data to send...",
        "btn_send": "Send",
        # Presets
        "group_presets": "Presets",
        "col_name": "Name",
        "col_data": "Data",
        "col_hex": "HEX",
        "btn_add": "➕ Add",
        "btn_edit": "✏️ Edit",
        "btn_delete": "🗑️ Delete",
        "btn_send_selected": "📤 Send Selected",
        # Modbus Panel
        "group_modbus": "Modbus RTU Quick Actions",
        "label_slave_addr": "Slave Addr:",
        "label_func_code": "Function:",
        "label_start_addr": "Start Addr:",
        "label_quantity": "Quantity/Value:",
        "label_reg_values": "Register Values (comma separated):",
        "placeholder_reg_values": "E.g. 100, 200, 300",
        "btn_read": "📖 Read",
        "btn_write": "✏️ Write",
        "btn_crc": "🔢 CRC Calc",
        "func_03_read_holding": "0x03 Read Holding",
        "func_04_read_input": "0x04 Read Input",
        "func_06_write_single": "0x06 Write Single",
        "func_10_write_multi": "0x10 Write Multiple",
        "crc_frame_prefix": "Frame:",
        "crc_label": "CRC:",
        # Modbus Response
        "group_modbus_response": "Modbus Response Parser",
        "label_auto_detect": "Auto-detect Modbus frames and parse register values",
        "col_time": "Time",
        "col_slave": "Slave",
        "col_func": "Function",
        "col_reg_addr": "Reg Addr",
        "col_raw": "Raw",
        "col_signed": "Signed",
        "label_reg_detail": "Register Details:",
        "col_address": "Address",
        "col_hex_value": "HEX",
        "col_dec": "DEC (Signed)",
        "col_float": "Float (IEEE754)",
        "func_03": "Read Holding",
        "func_04": "Read Input",
        "func_06": "Write Single",
        "func_10": "Write Multiple",
        "func_01": "Read Coils",
        "func_02": "Read Discrete Inputs",
        "func_05": "Write Single Coil",
        "func_0f": "Write Multiple Coils",
        "func_error": "Error",
        "func_unknown": "Unknown",
        "text_write_op": "Write",
        "text_error_prefix": "Error:",
        # Script Engine
        "tab_script": "🐍 Script",
        "group_script": "Python Script Engine",
        "label_example": "Example:",
        "btn_run": "▶️ Run",
        "btn_pause": "⏸ Pause",
        "btn_resume": "▶ Resume",
        "btn_step": "⏭ Step",
        "btn_stop": "⏹ Stop",
        "btn_clear_output": "Clear Output",
        "label_output": "Output:",
        "label_status_prefix": "Status:",
        "status_idle": "Idle",
        "status_running": "Running",
        "status_paused": "Paused",
        "status_stopped": "Stopped",
        "status_error": "Error",
        "status_breakpoint": "Breakpoint",
        "script_finished_ok": "Script finished: {}",
        "script_finished_fail": "Script failed: {}",
        "script_no_manager": "Serial manager not provided, script engine unavailable",
        # Multi-port Compare
        "tab_compare": "🔀 Compare",
        "group_compare": "Multi-Port Compare",
        "btn_clear_all": "Clear All",
        "btn_slot_connect": "Connect",
        "slot_placeholder": "{} - Not Connected",
        "title_hint": "Hint",
        "msg_slot_hint": "Configure port {} in the main window first\nFull multi-port setup is under development...",
        # Chart
        "label_mode": "Mode:",
        "mode_yt": "YT (Time Domain)",
        "mode_xy": "XY (Lissajous)",
        "label_x_axis": "  X Axis:",
        "x_axis_index": "Sample",
        "x_axis_time": "Time (s)",
        "xy_x_label": " X:",
        "xy_y_label": " Y:",
        "label_points": "  Points:",
        "check_autoscale": "Auto Scale",
        "check_grid": "Grid",
        "check_collect": "Collect",
        "tip_collect": "Stops sampling when off; freeze only pauses redraw, sampling continues",
        "btn_freeze": "⏸ Freeze",
        "btn_unfreeze": "▶ Resume",
        "btn_export_csv": "Export CSV",
        "btn_clear_chart": "Clear",
        "btn_add_channel": "＋ Channel",
        "label_channel": "Channel:",
        "cursor_hint": "Cursor: drag vertical lines to measure ΔX / ΔY",
        "cursor_no_channel": "Cursor: no visible channel",
        "cursor_fmt": "Cursor: ΔX={:.3f} {}   Δ{}={:+.4g}{}",
        "unit_point": "pt",
        "unit_ms": "ms",
        "axis_value": "Value",
        "axis_sample": "Sample",
        "axis_time": "Time (s)",
        "axis_y_channel": "Y Channel",
        "axis_x_channel": "X Channel",
        "dialog_export_csv": "Export Chart Data",
        "csv_filter": "CSV (*.csv)",
        "msg_exported": "{} rows written\n{}",
        "msg_max_channels": "Max {} channels",
        # Channel Spec Dialog
        "dialog_channel_spec": "Channel Properties",
        "label_ch_name": "Name",
        "label_ch_source": "Source",
        "src_raw": "Raw Bytes",
        "src_field": "Protocol Field",
        "src_register": "Modbus Register",
        "label_ch_dtype": "Decode",
        "dtype_uint8": "Byte (0-255)",
        "dtype_int16": "int16 (BE, signed)",
        "dtype_float32": "float32 (BE)",
        "label_ch_key": "Field/Address",
        "label_ch_unit": "Unit",
        "label_ch_scale": "Value × Scale",
        "label_ch_offset": "+ Offset",
        "err_name_empty": "Name cannot be empty",
        "err_name_dup": "Channel name {} already exists",
        "err_key_empty": "Please enter a field name or register address",
        # Status Bar
        "status_disconnected": "Disconnected",
        "status_connected": "Connected: {}",
        "status_log_off": "Log: Off",
        "status_log_on": "Log: {}",
        "rx_bytes": "RX: {} bytes",
        "tx_bytes": "TX: {} bytes",
        # Common Dialogs
        "title_warning": "Warning",
        "title_error": "Error",
        "title_success": "Success",
        "title_serial_error": "Serial Error",
        # Messages
        "msg_no_port": "No available serial ports",
        "msg_connect_failed": "Serial connection failed",
        "msg_not_connected": "Serial port not connected",
        "msg_please_connect": "Please connect first",
        "msg_export_success": "Log exported to:\n{}",
        "msg_config_saved": "Configuration saved",
        # Preset Edit Dialog
        "dialog_preset_edit": "Edit Preset",
        "label_name": "Name:",
        "label_data_content": "Data:",
        "placeholder_name": "Preset name",
        "placeholder_data": "Data content (ASCII or HEX)",
        "check_hex_format": "HEX Format",
        # Log Settings Dialog
        "dialog_log_settings": "Log Settings",
        "check_enable_log": "Enable Auto Logging",
        "label_log_dir": "Log Directory:",
        "btn_browse": "Browse...",
        "label_rotate_mode": "Rotate Mode:",
        "rotate_none": "None",
        "rotate_size": "By Size",
        "rotate_time": "By Time",
        "rotate_day": "By Day",
        "label_max_size": "Max File Size:",
        "label_rotate_interval": "Rotate Interval:",
        "label_max_files": "Max Files:",
        "title_browse_log_dir": "Select Log Directory",
        "suffix_minutes": " min",
        # Multi-Port Manager
        "dialog_multi_port": "Multi-Port Manager",
        "title_multi_port": "🔀 Multi-Port Manager (Max 4)",
        "dialog_port_config_group": "Serial Parameters",
        "label_parity_col": "Parity:",
        "label_flow_control": "Flow Control:",
        "status_dot_disconnected": "● Disconnected",
        "btn_configure": "⚙️ Config",
        "btn_compare": "📊 Compare",
        "btn_connect_all": "🔗 Connect All",
        "btn_disconnect_all": "⛓️‍💥 Disconnect All",
        "btn_close": "Close",
        "dialog_port_config": "Configure {}",
        "title_port_config": "🔌 {} Serial Config",
        "msg_port_connected_fail": "{} connection failed",
        "msg_connect_all_done": "Connected {} ports",
        "msg_not_configured": "{} not configured, please click 'Config' first",
        "msg_config_saved_detail": "{} config saved\nPort: {}\nBaudrate: {}",
        "msg_connected_count": "Connected {} ports",
        # Protocol Template Management
        "dialog_template_mgmt": "Protocol Template Manager",
        "desc_templates": "Define custom protocol frames via JSON templates, no Python needed",
        "label_loaded_templates": "Loaded Templates:",
        "btn_new": "➕ New",
        "btn_sample": "📋 Sample",
        "label_template_json": "Template JSON:",
        "label_preview": "Preview:",
        "title_confirm_delete": "Confirm Delete",
        "msg_confirm_delete": 'Delete template "{}"?',
        "msg_template_saved": 'Template "{}" saved',
        "title_save_success": "Saved",
        "title_save_fail": "Save Failed",
        "msg_json_error": "JSON error: {}",
        "err_template_name": "Template name cannot be empty",
        "pv_name": "Name:",
        "pv_desc": "Description:",
        "pv_header": "Header:",
        "pv_tail": "Tail:",
        "pv_min_len": "Min Length:",
        "pv_fields": "Fields:",
        "pv_none": "(none)",
        "pv_no_fields": "(no fields defined)",
        # About
        "about_title": "About",
        "about_text": """Serial Toolbox v4.0

Features:
• Serial Communication (HEX/ASCII)
• Enhanced Chart (Data Channels + XY Lissajous)
• Modbus RTU Response Auto-Parse
• Protocol Plugin Framework (CAN/I2C/SPI/LIN/DMX512/UART-Packet)
• Preset Commands Management
• DTR/RTS Signal Control
• Modbus RTU Quick Actions
• Auto Send (Timer)
• Log Rotation (Size/Time/Day)
• Python Script Engine (Breakpoints/wait_response)
• Multi-Port Compare (Max 4)
• Multi-Port Manager (Independent Config)
• Data Export (CSV)
• Theme Switch (Light/Dark)
• UI Language (Chinese/English)
• Config Save/Load

Built with PyQt6 + pyqtgraph""",
    },
}


class I18nManager:
    """国际化管理器"""

    def __init__(self, language: Language | None = None):
        if language is None:
            language = Language.CHINESE
        self.current_language = language

    @classmethod
    def from_value(cls, value: str) -> "I18nManager":
        """从配置字符串创建，非法值回退中文"""
        try:
            return cls(Language(value))
        except ValueError:
            return cls(Language.CHINESE)

    def set_language(self, language: Language):
        """设置语言"""
        self.current_language = language

    def get_language(self) -> Language:
        """获取当前语言"""
        return self.current_language

    def tr(self, key: str, *args) -> str:
        """翻译文本"""
        translations = TRANSLATIONS.get(self.current_language, {})
        text = translations.get(key, key)

        # 格式化参数
        if args:
            try:
                text = text.format(*args)
            except (IndexError, KeyError):
                pass

        return text

    def toggle(self):
        """切换语言"""
        if self.current_language == Language.CHINESE:
            self.current_language = Language.ENGLISH
        else:
            self.current_language = Language.CHINESE
