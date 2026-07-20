"""
主题管理模块
支持亮色/暗色主题切换
"""

from dataclasses import dataclass
from enum import Enum


class ThemeMode(Enum):
    """主题模式"""
    LIGHT = "light"
    DARK = "dark"


@dataclass
class ThemeColors:
    """主题颜色"""
    # 背景色
    background: str
    surface: str
    surface_variant: str

    # 文本色
    text_primary: str
    text_secondary: str
    text_disabled: str

    # 边框色
    border: str
    border_light: str

    # 按钮色
    button_primary: str
    button_primary_hover: str
    button_primary_pressed: str
    button_checked: str
    button_checked_hover: str

    # 输入框
    input_background: str
    input_border: str
    input_text: str

    # 表格
    table_grid: str
    table_selected_bg: str
    table_selected_text: str

    # 状态栏
    status_bar_bg: str

    # 终端/日志
    terminal_bg: str
    terminal_text: str

    # 标签页
    tab_selected_bg: str
    tab_selected_text: str


# 暗色主题
DARK_THEME = ThemeColors(
    background="#2b2b2b",
    surface="#3c3c3c",
    surface_variant="#4a4a4a",
    text_primary="#d4d4d4",
    text_secondary="#a0a0a0",
    text_disabled="#666666",
    border="#555555",
    border_light="#444444",
    button_primary="#4CAF50",
    button_primary_hover="#45a049",
    button_primary_pressed="#3d8b40",
    button_checked="#f44336",
    button_checked_hover="#da190b",
    input_background="#1e1e1e",
    input_border="#555555",
    input_text="#d4d4d4",
    table_grid="#444444",
    table_selected_bg="#2d4a2d",
    table_selected_text="#d4d4d4",
    status_bar_bg="#1e1e1e",
    terminal_bg="#1e1e1e",
    terminal_text="#d4d4d4",
    tab_selected_bg="#4CAF50",
    tab_selected_text="#ffffff",
)

# 亮色主题
LIGHT_THEME = ThemeColors(
    background="#f5f5f5",
    surface="#ffffff",
    surface_variant="#e8e8e8",
    text_primary="#333333",
    text_secondary="#666666",
    text_disabled="#999999",
    border="#cccccc",
    border_light="#dddddd",
    button_primary="#4CAF50",
    button_primary_hover="#45a049",
    button_primary_pressed="#3d8b40",
    button_checked="#f44336",
    button_checked_hover="#da190b",
    input_background="#ffffff",
    input_border="#cccccc",
    input_text="#333333",
    table_grid="#e0e0e0",
    table_selected_bg="#C8E6C9",
    table_selected_text="#333333",
    status_bar_bg="#e8e8e8",
    terminal_bg="#1e1e1e",
    terminal_text="#d4d4d4",
    tab_selected_bg="#4CAF50",
    tab_selected_text="#ffffff",
)


class ThemeManager:
    """主题管理器"""

    def __init__(self):
        self.current_mode = ThemeMode.LIGHT
        self.themes: dict[ThemeMode, ThemeColors] = {
            ThemeMode.LIGHT: LIGHT_THEME,
            ThemeMode.DARK: DARK_THEME,
        }

    def get_theme(self, mode: ThemeMode = None) -> ThemeColors:
        """获取主题"""
        if mode is None:
            mode = self.current_mode
        return self.themes.get(mode, LIGHT_THEME)

    def set_mode(self, mode: ThemeMode):
        """设置主题模式"""
        self.current_mode = mode

    def toggle(self):
        """切换主题"""
        if self.current_mode == ThemeMode.LIGHT:
            self.current_mode = ThemeMode.DARK
        else:
            self.current_mode = ThemeMode.LIGHT

    def generate_stylesheet(self, theme: ThemeColors = None) -> str:
        """生成 QSS 样式表"""
        if theme is None:
            theme = self.get_theme()

        return f"""
            QMainWindow {{
                background-color: {theme.background};
            }}
            QGroupBox {{
                font-weight: bold;
                border: 1px solid {theme.border};
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
                color: {theme.text_primary};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QLabel {{
                color: {theme.text_primary};
            }}
            QPushButton {{
                background-color: {theme.button_primary};
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
            }}
            QPushButton:hover {{
                background-color: {theme.button_primary_hover};
            }}
            QPushButton:pressed {{
                background-color: {theme.button_primary_pressed};
            }}
            QPushButton:checked {{
                background-color: {theme.button_checked};
            }}
            QPushButton:checked:hover {{
                background-color: {theme.button_checked_hover};
            }}
            QPushButton:disabled {{
                background-color: {theme.text_disabled};
            }}
            QTextEdit, QPlainTextEdit {{
                background-color: {theme.terminal_bg};
                color: {theme.terminal_text};
                border: 1px solid {theme.border};
            }}
            QLineEdit {{
                background-color: {theme.input_background};
                color: {theme.input_text};
                border: 1px solid {theme.input_border};
                padding: 5px;
                border-radius: 3px;
            }}
            QComboBox {{
                background-color: {theme.input_background};
                color: {theme.input_text};
                border: 1px solid {theme.input_border};
                padding: 3px;
                border-radius: 3px;
                min-width: 60px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {theme.surface};
                color: {theme.text_primary};
                selection-background-color: {theme.table_selected_bg};
            }}
            QSpinBox {{
                background-color: {theme.input_background};
                color: {theme.input_text};
                border: 1px solid {theme.input_border};
                padding: 3px;
            }}
            QCheckBox {{
                color: {theme.text_primary};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
            }}
            QTabWidget::pane {{
                border: 1px solid {theme.border};
                background-color: {theme.surface};
            }}
            QTabBar::tab {{
                background-color: {theme.surface_variant};
                color: {theme.text_primary};
                padding: 8px 20px;
                margin: 2px;
                border-radius: 3px;
            }}
            QTabBar::tab:selected {{
                background-color: {theme.tab_selected_bg};
                color: {theme.tab_selected_text};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {theme.border_light};
            }}
            QTableWidget {{
                background-color: {theme.input_background};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                gridline-color: {theme.table_grid};
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background-color: {theme.table_selected_bg};
                color: {theme.table_selected_text};
            }}
            QHeaderView::section {{
                background-color: {theme.surface_variant};
                color: {theme.text_primary};
                padding: 5px;
                border: 1px solid {theme.border};
            }}
            QStatusBar {{
                background-color: {theme.status_bar_bg};
                color: {theme.text_primary};
            }}
            QMenuBar {{
                background-color: {theme.surface};
                color: {theme.text_primary};
            }}
            QMenuBar::item:selected {{
                background-color: {theme.surface_variant};
            }}
            QMenu {{
                background-color: {theme.surface};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
            }}
            QMenu::item:selected {{
                background-color: {theme.table_selected_bg};
            }}
            QScrollBar:vertical {{
                background-color: {theme.surface};
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {theme.border};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {theme.text_secondary};
            }}
            QSplitter::handle {{
                background-color: {theme.border_light};
            }}
            QDialog {{
                background-color: {theme.background};
            }}
        """

    def get_current_mode(self) -> ThemeMode:
        """获取当前模式"""
        return self.current_mode
