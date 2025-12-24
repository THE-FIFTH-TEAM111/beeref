from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QComboBox, QListWidget)
from PyQt6.QtCore import Qt
from typing import List, Dict  # 新增Dict类型支持

class TagEditDialog(QDialog):
    """标签添加/编辑对话框（支持选择分组）"""
    def __init__(self, parent=None, tag_name: str = "", tag_group: str = "默认分组", groups: List[str] = None):
        super().__init__(parent)
        self.setWindowTitle("编辑标签")
        self.setModal(True)
        self.setFixedSize(300, 150)
        self.tag_name = tag_name
        self.tag_group = tag_group
        self.groups = groups or ["默认分组"]
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 标签名称输入
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("标签名称："))
        self.name_input = QLineEdit(self.tag_name)
        name_layout.addWidget(self.name_input)
        layout.addLayout(name_layout)

        # 分组选择
        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("所属分组："))
        self.group_combo = QComboBox()
        self.group_combo.addItems(self.groups)
        if self.tag_group in self.groups:
            self.group_combo.setCurrentText(self.tag_group)
        group_layout.addWidget(self.group_combo)
        layout.addLayout(group_layout)

        # 确认/取消按钮
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确认")
        self.cancel_btn = QPushButton("取消")
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def get_result(self) -> tuple[str, str]:
        """返回用户输入的标签名称和分组"""
        return self.name_input.text().strip(), self.group_combo.currentText()


class TagSelectDialog(QDialog):
    """标签选择对话框（用于按标签导出/筛选）"""
    def __init__(self, parent=None, tags: List[Dict] = None):
        super().__init__(parent)
        self.setWindowTitle("选择标签")
        self.setModal(True)
        self.setFixedSize(300, 200)
        self.tags = tags or []  # 标签列表：[{"tag_id": 1, "tag_name": "人像"}, ...]
        self.selected_tag_id = None  # 选中的标签ID
        self.init_ui()

    def init_ui(self):
        """初始化选择对话框UI"""
        layout = QVBoxLayout(self)

        # 标题提示
        layout.addWidget(QLabel("请选择要导出的标签："))

        # 标签列表
        self.tag_list = QListWidget()
        # 填充标签列表（显示标签名）
        for tag in self.tags:
            self.tag_list.addItem(tag.get("tag_name", "未知标签"))
        layout.addWidget(self.tag_list)

        # 按钮区域
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确认")
        self.cancel_btn = QPushButton("取消")
        
        # 绑定按钮事件
        self.ok_btn.clicked.connect(self.on_ok)
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def on_ok(self):
        """确认选择：根据选中的标签名匹配tag_id"""
        selected_item = self.tag_list.currentItem()
        if not selected_item:
            # 未选中标签时提示
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请先选择一个标签！")
            return
        
        selected_name = selected_item.text()
        # 遍历标签列表找到对应的tag_id
        for tag in self.tags:
            if tag.get("tag_name") == selected_name:
                self.selected_tag_id = tag.get("tag_id")
                break
        
        self.accept()  # 关闭对话框并返回成功

    def get_selected_tag_id(self) -> int | None:
        """返回选中的标签ID（无选中则返回None）"""
        return self.selected_tag_id