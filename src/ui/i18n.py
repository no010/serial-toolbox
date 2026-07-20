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
        "menu_multi_port": "多串口管理器...",
        "menu_theme": "主题",
        "menu_theme_light": "亮色主题",
        "menu_theme_dark": "暗色主题",
        "menu_language": "语言",
        "menu_lang_zh": "中文",
        "menu_lang_en": "English",
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
        "btn_read": "📖 读取",
        "btn_write": "✏️ 写入",
        "btn_crc": "🔢 CRC 计算",

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
        "col_dec": "DEC (有符号)",
        "col_float": "Float (IEEE754)",

        # 协议解析
        "label_select_protocol": "选择协议:",
        "auto_detect": "自动检测",

        # 脚本引擎
        "tab_script": "🐍 脚本引擎",
        "group_script": "Python 脚本引擎",
        "label_example": "示例:",
        "btn_run": "▶ 运行",
        "btn_pause": "⏸ 暂停",
        "btn_resume": "▶ 恢复",
        "btn_stop": "⏹ 停止",
        "placeholder_script": "# 在这里编写 Python 脚本\n# 可用 API: send(), sleep(), log_info(), log_error(), log_success()\n",
        "label_exec_log": "执行日志:",
        "label_status": "状态:",
        "status_idle": "空闲",
        "status_running": "运行中",
        "status_paused": "已暂停",
        "status_stopped": "已停止",
        "status_error": "错误",

        # 多串口对比
        "tab_compare": "🔀 多串口对比",
        "group_compare": "多串口对比 (最多4路)",
        "label_select_ports": "选择要对比的串口:",
        "btn_clear_all": "清空全部",

        # 波形图
        "label_mode": "模式:",
        "mode_yt": "YT (时域)",
        "mode_xy": "XY (李萨如)",
        "label_data": "数据:",
        "data_byte": "字节值 (0-255)",
        "data_int": "整数 (大端)",
        "data_float": "浮点 (IEEE754)",
        "label_points": "点数:",
        "btn_clear_chart": "清空",
        "label_channel": "通道:",
        "check_grid": "网格",

        # 状态栏
        "status_disconnected": "未连接",
        "status_connected": "已连接: {}",
        "status_log_off": "日志: 关闭",

        # 对话框
        "dialog_preset_edit": "编辑预设指令",
        "label_name": "名称:",
        "label_data_content": "数据:",
        "placeholder_name": "指令名称",
        "placeholder_data": "指令内容 (ASCII 或 HEX)",
        "check_hex_format": "HEX 格式",

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

        "dialog_multi_port": "多串口管理器",
        "title_multi_port": "🔀 多串口管理器 (最多4路)",
        "btn_configure": "⚙️ 配置",
        "btn_compare": "📊 对比",
        "btn_connect_all": "🔗 全部连接",
        "btn_disconnect_all": "⛓️‍💥 全部断开",
        "btn_close": "关闭",

        "dialog_port_config": "配置 {}",
        "title_port_config": "🔌 {} 串口配置",
        "label_flow_control": "流控:",

        # 消息
        "msg_no_port": "没有可用的串口",
        "msg_connect_failed": "串口连接失败",
        "msg_not_connected": "串口未连接",
        "msg_please_connect": "请先连接串口",
        "msg_script_empty": "脚本为空",
        "msg_script_running": "脚本正在运行中",
        "msg_export_success": "日志已导出到:\n{}",
        "msg_config_saved": "配置已保存",
        "msg_connected_count": "已连接 {} 个串口",
        "msg_not_configured": "{} 未配置，请先点击\"配置\"按钮",
        "msg_config_saved_detail": "{} 配置已保存\n端口: {}\n波特率: {}",

        # 关于
        "about_title": "关于",
        "about_text": """串口调试助手 v4.0

功能:
• 串口通信 (HEX/ASCII 切换)
• 增强波形图 (多通道 + XY 李萨如)
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
• 数据导出 (CSV/JSON/TXT)
• 主题切换 (亮色/暗色)
• 国际化 (中/英文)
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
        "menu_multi_port": "Multi-Port Manager...",
        "menu_theme": "Theme",
        "menu_theme_light": "Light Theme",
        "menu_theme_dark": "Dark Theme",
        "menu_language": "Language",
        "menu_lang_zh": "中文",
        "menu_lang_en": "English",
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
        "btn_read": "📖 Read",
        "btn_write": "✏️ Write",
        "btn_crc": "🔢 CRC Calc",

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
        "col_dec": "DEC (Signed)",
        "col_float": "Float (IEEE754)",

        # Protocol
        "label_select_protocol": "Protocol:",
        "auto_detect": "Auto Detect",

        # Script Engine
        "tab_script": "🐍 Script",
        "group_script": "Python Script Engine",
        "label_example": "Example:",
        "btn_run": "▶ Run",
        "btn_pause": "⏸ Pause",
        "btn_resume": "▶ Resume",
        "btn_stop": "⏹ Stop",
        "placeholder_script": "# Write Python script here\n# Available API: send(), sleep(), log_info(), log_error(), log_success()\n",
        "label_exec_log": "Execution Log:",
        "label_status": "Status:",
        "status_idle": "Idle",
        "status_running": "Running",
        "status_paused": "Paused",
        "status_stopped": "Stopped",
        "status_error": "Error",

        # Multi-port Compare
        "tab_compare": "🔀 Compare",
        "group_compare": "Multi-Port Compare (Max 4)",
        "label_select_ports": "Select ports to compare:",
        "btn_clear_all": "Clear All",

        # Chart
        "label_mode": "Mode:",
        "mode_yt": "YT (Time Domain)",
        "mode_xy": "XY (Lissajous)",
        "label_data": "Data:",
        "data_byte": "Byte (0-255)",
        "data_int": "Integer (Big Endian)",
        "data_float": "Float (IEEE754)",
        "label_points": "Points:",
        "btn_clear_chart": "Clear",
        "label_channel": "Channel:",
        "check_grid": "Grid",

        # Status Bar
        "status_disconnected": "Disconnected",
        "status_connected": "Connected: {}",
        "status_log_off": "Log: Off",

        # Dialogs
        "dialog_preset_edit": "Edit Preset",
        "label_name": "Name:",
        "label_data_content": "Data:",
        "placeholder_name": "Preset name",
        "placeholder_data": "Data content (ASCII or HEX)",
        "check_hex_format": "HEX Format",

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

        "dialog_multi_port": "Multi-Port Manager",
        "title_multi_port": "🔀 Multi-Port Manager (Max 4)",
        "btn_configure": "⚙️ Config",
        "btn_compare": "📊 Compare",
        "btn_connect_all": "🔗 Connect All",
        "btn_disconnect_all": "⛓️‍💥 Disconnect All",
        "btn_close": "Close",

        "dialog_port_config": "Configure {}",
        "title_port_config": "🔌 {} Serial Config",
        "label_flow_control": "Flow Control:",

        # Messages
        "msg_no_port": "No available serial ports",
        "msg_connect_failed": "Serial connection failed",
        "msg_not_connected": "Serial port not connected",
        "msg_please_connect": "Please connect first",
        "msg_script_empty": "Script is empty",
        "msg_script_running": "Script is running",
        "msg_export_success": "Log exported to:\n{}",
        "msg_config_saved": "Configuration saved",
        "msg_connected_count": "Connected {} ports",
        "msg_not_configured": "{} not configured, please click 'Config' first",
        "msg_config_saved_detail": "{} config saved\nPort: {}\nBaudrate: {}",

        # About
        "about_title": "About",
        "about_text": """Serial Toolbox v4.0

Features:
• Serial Communication (HEX/ASCII)
• Enhanced Chart (Multi-channel + XY Lissajous)
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
• Data Export (CSV/JSON/TXT)
• Theme Switch (Light/Dark)
• Internationalization (Chinese/English)
• Config Save/Load

Built with PyQt6 + pyqtgraph""",
    },
}


class I18nManager:
    """国际化管理器"""

    def __init__(self):
        self.current_language = Language.CHINESE

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
