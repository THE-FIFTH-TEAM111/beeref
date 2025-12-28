from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QCheckBox, 
                             QPushButton, QLineEdit, QScrollArea, QSpacerItem,
                             QSizePolicy)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPalette, QColor  # 导入QFont类和颜色相关类
from typing import List, Dict

class TagPanel(QWidget):
    """左侧标签筛选面板：勾选标签筛选画布图像"""
    # 核心修改：将 List[int] 改为 list（PyQt6兼容的类型）
    tag_filter_changed = pyqtSignal(list)  # 筛选标签ID列表变化时触发
    add_tag_requested = pyqtSignal(str)    # 请求新增标签

    def __init__(self):
        super().__init__()
        self.current_tags: List[Dict] = []
        self.checked_tag_ids: List[int] = []
        # 统一字体大小设置
        self.font_size = 14
        self.init_ui()

    def init_ui(self):
        """初始化UI布局"""
        # 设置整体布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)  # 增加外间距
        layout.setSpacing(10)  # 增加元素间间距

        # 创建统一字体
        main_font = QFont()
        main_font.setPointSize(self.font_size)

        # 标签分组框
        self.tag_group = QGroupBox("标签筛选")
        self.tag_group.setFont(main_font)  # 设置分组框标题字体
        tag_layout = QVBoxLayout(self.tag_group)
        tag_layout.setContentsMargins(10, 15, 10, 10)  # 调整分组框内边距
        tag_layout.setSpacing(15)  # 增加分组框内元素间距

        # 新增标签输入框+按钮
        add_layout = QVBoxLayout()
        add_layout.setSpacing(8)  # 输入框和按钮间的间距
        
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("输入新标签名称...")
        self.tag_input.setFont(main_font)  # 统一输入框字体
        self.tag_input.setMinimumHeight(30)  # 设置最小高度
        add_layout.addWidget(self.tag_input)
        
        self.add_btn = QPushButton("添加标签")
        self.add_btn.setFont(main_font)  # 统一按钮字体
        self.add_btn.setMinimumHeight(32)  # 设置最小高度
        self.add_btn.clicked.connect(self.on_add_tag)
        add_layout.addWidget(self.add_btn)
        
        tag_layout.addLayout(add_layout)

        # 标签列表滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # 只显示垂直滚动条
        
        # 滚动区域内容
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll_layout.setSpacing(8)  # 标签间的间距
        
        self.scroll_area.setWidget(self.scroll_widget)
        tag_layout.addWidget(self.scroll_area)

        layout.addWidget(self.tag_group)

        # 添加伸缩项，将内容向上推
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def update_tags(self, tags: List[Dict]):
        """更新标签列表（清空旧复选框，添加新标签）"""
        self.current_tags = tags
        # 清空现有复选框
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.takeAt(i).widget()
            if widget:
                widget.deleteLater()
        
        # 创建统一字体
        tag_font = QFont()
        tag_font.setPointSize(self.font_size)
        
        # 添加新标签复选框
        for tag in tags:
            checkbox = QCheckBox(tag["tag_name"])
            checkbox.setFont(tag_font)  # 统一标签字体
            checkbox.setMinimumHeight(30)  # 设置最小高度，增加点击区域
            checkbox.setProperty("tag_id", tag["tag_id"])
            checkbox.stateChanged.connect(self.on_tag_check)
            self.scroll_layout.addWidget(checkbox)

    def on_tag_check(self, state: int):
        """标签勾选状态变化：收集选中的标签ID"""
        self.checked_tag_ids = []
        for i in range(self.scroll_layout.count()):
            checkbox = self.scroll_layout.itemAt(i).widget()
            if isinstance(checkbox, QCheckBox) and checkbox.isChecked():
                self.checked_tag_ids.append(checkbox.property("tag_id"))
        # 发送筛选信号（list类型，与修改后的signal匹配）
        self.tag_filter_changed.emit(self.checked_tag_ids)

    def on_add_tag(self):
        """点击添加标签：发送新增请求"""
        tag_name = self.tag_input.text().strip()
        if tag_name:
            self.add_tag_requested.emit(tag_name)
            self.tag_input.clear()