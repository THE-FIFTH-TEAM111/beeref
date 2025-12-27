from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QCheckBox, 
                             QPushButton, QLineEdit, QScrollArea)
from PyQt6.QtCore import pyqtSignal, Qt
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
        self.init_ui()

    def init_ui(self):
        """初始化UI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # 标签分组框
        self.tag_group = QGroupBox("标签筛选")
        tag_layout = QVBoxLayout(self.tag_group)

        # 新增标签输入框+按钮
        add_layout = QVBoxLayout()
        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("输入新标签名称...")
        self.add_btn = QPushButton("添加标签")
        self.add_btn.clicked.connect(self.on_add_tag)
        add_layout.addWidget(self.tag_input)
        add_layout.addWidget(self.add_btn)
        tag_layout.addLayout(add_layout)

        # 标签列表滚动区域
        self.scroll_area = QScrollArea()
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_area.setWidget(self.scroll_widget)
        self.scroll_area.setWidgetResizable(True)
        tag_layout.addWidget(self.scroll_area)

        layout.addWidget(self.tag_group)

    def update_tags(self, tags: List[Dict]):
        """更新标签列表（清空旧复选框，添加新标签）"""
        self.current_tags = tags
        # 清空现有复选框
        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.takeAt(i).widget()
            if widget:
                widget.deleteLater()
        # 添加新标签复选框
        for tag in tags:
            checkbox = QCheckBox(tag["tag_name"])
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