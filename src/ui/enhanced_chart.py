"""
增强波形图组件
支持多通道显示、XY 模式、光标测量
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QSpinBox, QCheckBox, QColorDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

import pyqtgraph as pg
import numpy as np
from typing import List, Optional


class EnhancedChart(QWidget):
    """增强波形图 - 多通道 + XY 模式"""
    
    # 通道颜色
    CHANNEL_COLORS = [
        '#4FC3F7',  # 蓝色
        '#81C784',  # 绿色
        '#FFB74D',  # 橙色
        '#BA68C8',  # 紫色
        '#E57373',  # 红色
        '#4DB6AC',  # 青色
    ]
    
    def __init__(self, max_points=500, max_channels=4):
        super().__init__()
        self.max_points = max_points
        self.max_channels = max_channels
        
        # 多通道数据缓冲
        self.channel_buffers: List[np.ndarray] = [
            np.zeros(max_points) for _ in range(max_channels)
        ]
        self.channel_ptrs = [0] * max_channels
        self.channel_enabled = [True] * max_channels
        self.channel_colors = self.CHANNEL_COLORS[:max_channels]
        
        # XY 模式数据
        self.xy_mode = False
        self.xy_x_channel = 0
        self.xy_y_channel = 1
        
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 控制栏
        ctrl = QHBoxLayout()
        
        # 显示模式
        ctrl.addWidget(QLabel('模式:'))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(['YT (时域)', 'XY (李萨如)'])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        ctrl.addWidget(self.mode_combo)
        
        # 数据解析模式
        ctrl.addWidget(QLabel('  数据:'))
        self.data_mode_combo = QComboBox()
        self.data_mode_combo.addItems(['字节值 (0-255)', '整数 (大端)', '浮点 (IEEE754)'])
        ctrl.addWidget(self.data_mode_combo)
        
        # 最大点数
        ctrl.addWidget(QLabel('  点数:'))
        self.points_spin = QSpinBox()
        self.points_spin.setRange(50, 5000)
        self.points_spin.setValue(self.max_points)
        self.points_spin.setSingleStep(50)
        self.points_spin.valueChanged.connect(self._update_max_points)
        ctrl.addWidget(self.points_spin)
        
        # XY 模式通道选择
        self.xy_x_combo = QComboBox()
        self.xy_x_combo.addItems(['通道1', '通道2', '通道3', '通道4'])
        self.xy_x_combo.setVisible(False)
        self.xy_x_combo.currentIndexChanged.connect(self._on_xy_channel_changed)
        ctrl.addWidget(QLabel(' X:'))
        ctrl.addWidget(self.xy_x_combo)
        
        self.xy_y_combo = QComboBox()
        self.xy_y_combo.addItems(['通道1', '通道2', '通道3', '通道4'])
        self.xy_y_combo.setCurrentIndex(1)
        self.xy_y_combo.setVisible(False)
        self.xy_y_combo.currentIndexChanged.connect(self._on_xy_channel_changed)
        ctrl.addWidget(QLabel(' Y:'))
        ctrl.addWidget(self.xy_y_combo)
        
        ctrl.addStretch()
        
        # 清空按钮
        clear_btn = QPushButton('清空')
        clear_btn.clicked.connect(self.clear)
        ctrl.addWidget(clear_btn)
        
        layout.addLayout(ctrl)
        
        # 通道控制栏
        channel_ctrl = QHBoxLayout()
        channel_ctrl.addWidget(QLabel('通道:'))
        
        self.channel_checks = []
        self.channel_color_btns = []
        
        for i in range(self.max_channels):
            check = QCheckBox(f'CH{i+1}')
            check.setChecked(True)
            check.stateChanged.connect(lambda state, ch=i: self._toggle_channel(ch, state))
            self.channel_checks.append(check)
            channel_ctrl.addWidget(check)
            
            color_btn = QPushButton('■')
            color_btn.setStyleSheet(f'color: {self.channel_colors[i]}; font-size: 16px;')
            color_btn.setFixedSize(25, 25)
            color_btn.clicked.connect(lambda checked, ch=i: self._change_channel_color(ch))
            self.channel_color_btns.append(color_btn)
            channel_ctrl.addWidget(color_btn)
        
        channel_ctrl.addStretch()
        
        # 网格开关
        self.grid_check = QCheckBox('网格')
        self.grid_check.setChecked(True)
        self.grid_check.stateChanged.connect(self._toggle_grid)
        channel_ctrl.addWidget(self.grid_check)
        
        layout.addLayout(channel_ctrl)
        
        # pyqtgraph 绘图
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('#1e1e1e')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', '数值')
        self.plot_widget.setLabel('bottom', '采样点')
        
        # 创建多通道曲线
        self.curves = []
        for i in range(self.max_channels):
            curve = self.plot_widget.plot(
                pen=pg.mkPen(color=self.channel_colors[i], width=2),
                connect='finite',
                name=f'CH{i+1}'
            )
            self.curves.append(curve)
        
        # XY 模式曲线
        self.xy_curve = self.plot_widget.plot(
            pen=pg.mkPen(color='#FFD700', width=2),
            connect='finite',
            name='XY'
        )
        self.xy_curve.setVisible(False)
        
        layout.addWidget(self.plot_widget)
    
    def _on_mode_changed(self, index):
        """切换显示模式"""
        self.xy_mode = (index == 1)
        
        # 显示/隐藏控件
        self.xy_x_combo.setVisible(self.xy_mode)
        self.xy_y_combo.setVisible(self.xy_mode)
        
        # 切换曲线可见性
        for curve in self.curves:
            curve.setVisible(not self.xy_mode)
        self.xy_curve.setVisible(self.xy_mode)
        
        # 更新坐标轴标签
        if self.xy_mode:
            self.plot_widget.setLabel('left', 'Y 通道')
            self.plot_widget.setLabel('bottom', 'X 通道')
        else:
            self.plot_widget.setLabel('left', '数值')
            self.plot_widget.setLabel('bottom', '采样点')
    
    def _on_xy_channel_changed(self, index):
        """XY 通道变化"""
        self.xy_x_channel = self.xy_x_combo.currentIndex()
        self.xy_y_channel = self.xy_y_combo.currentIndex()
    
    def _toggle_channel(self, channel: int, state: int):
        """切换通道显示"""
        self.channel_enabled[channel] = (state == Qt.CheckState.Checked.value)
        self.curves[channel].setVisible(self.channel_enabled[channel] and not self.xy_mode)
    
    def _change_channel_color(self, channel: int):
        """更改通道颜色"""
        color = QColorDialog.getColor()
        if color.isValid():
            self.channel_colors[channel] = color.name()
            self.curves[channel].setPen(pg.mkPen(color=color.name(), width=2))
            self.channel_color_btns[channel].setStyleSheet(
                f'color: {color.name()}; font-size: 16px;'
            )
    
    def _toggle_grid(self, state):
        """切换网格"""
        self.plot_widget.showGrid(
            x=state == Qt.CheckState.Checked.value,
            y=state == Qt.CheckState.Checked.value,
            alpha=0.3
        )
    
    def append_data(self, raw_bytes: bytes, channel: int = 0):
        """追加数据到指定通道"""
        if channel >= self.max_channels:
            return
        
        mode = self.data_mode_combo.currentIndex()
        
        if mode == 0:  # 字节值
            values = list(raw_bytes)
        elif mode == 1:  # 整数 (2字节大端)
            values = []
            for i in range(0, len(raw_bytes) - 1, 2):
                val = int.from_bytes(raw_bytes[i:i+2], 'big', signed=True)
                values.append(val)
        else:  # 浮点 (4字节 IEEE754)
            values = []
            for i in range(0, len(raw_bytes) - 3, 4):
                val = np.frombuffer(raw_bytes[i:i+4], dtype='>f4')[0]
                values.append(float(val))
        
        for val in values:
            self.channel_buffers[channel][self.channel_ptrs[channel] % self.max_points] = val
            self.channel_ptrs[channel] += 1
        
        self._update_plot()
    
    def _update_plot(self):
        """更新绘图"""
        if self.xy_mode:
            # XY 模式
            x_buf = self.channel_buffers[self.xy_x_channel]
            y_buf = self.channel_buffers[self.xy_y_channel]
            x_ptr = self.channel_ptrs[self.xy_x_channel]
            y_ptr = self.channel_ptrs[self.xy_y_channel]
            
            # 使用最小长度
            length = min(x_ptr, y_ptr, self.max_points)
            if length > 0:
                x_data = np.roll(x_buf, -(x_ptr % self.max_points))[:length]
                y_data = np.roll(y_buf, -(y_ptr % self.max_points))[:length]
                self.xy_curve.setData(x_data, y_data)
        else:
            # YT 模式 - 多通道
            for i in range(self.max_channels):
                if self.channel_enabled[i] and self.channel_ptrs[i] > 0:
                    ptr = self.channel_ptrs[i]
                    buf = self.channel_buffers[i]
                    
                    if ptr <= self.max_points:
                        self.curves[i].setData(buf[:ptr])
                    else:
                        start = ptr % self.max_points
                        rolled = np.roll(buf, -start)
                        self.curves[i].setData(rolled)
    
    def _update_max_points(self, value):
        """更新最大点数"""
        self.max_points = value
        self.channel_buffers = [np.zeros(value) for _ in range(self.max_channels)]
        self.channel_ptrs = [0] * self.max_channels
        self.clear()
    
    def clear(self):
        """清空"""
        self.channel_buffers = [np.zeros(self.max_points) for _ in range(self.max_channels)]
        self.channel_ptrs = [0] * self.max_channels
        for curve in self.curves:
            curve.clear()
        self.xy_curve.clear()
