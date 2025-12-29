# This file is part of BeeRef.
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.
import math
from functools import partial
import logging
import os
import os.path
import json

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPixmap, QKeySequence, QUndoStack, QImageReader
from PyQt6.QtWidgets import (
    QAbstractSpinBox, QApplication, QDialog, QFileDialog, QFrame,
    QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QDoubleSpinBox, QVBoxLayout,
    QWidget, QColorDialog, QFontComboBox, QComboBox, QCheckBox, QSlider
)

from beeref.actions import ActionsMixin, actions
from beeref.actions.actions import Action  # 添加这一行导入Action类
from beeref import commands
from beeref.config import CommandlineArgs, BeeSettings, KeyboardSettings
from beeref import constants
from beeref import fileio
from beeref.fileio.errors import IMG_LOADING_ERROR_MSG
from beeref.fileio.export import exporter_registry, ImagesToDirectoryExporter
from beeref import widgets
from beeref.items import BeePixmapItem, BeeTextItem
from beeref.main_controls import MainControlsMixin
from beeref.scene import BeeGraphicsScene
from beeref.utils import get_file_extension_from_format, qcolor_to_hex


# 全局命令行参数
commandline_args = CommandlineArgs()
logger = logging.getLogger(__name__)

# 水印模板保存路径
WATERMARK_TEMPLATE_PATH = os.path.join(os.path.expanduser("~"), "BeeRef_Watermark_Templates.json")


# ------------------------------
# 水印预览组件（支持旋转/缩放/实时预览）
# ------------------------------
class WatermarkPreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 200)
        # 默认参数
        self.watermark_text = "小金毛"
        self.font = QFont("Arial", 20)
        self.color = QColor(51, 51, 51, 128)
        self.position = "平铺"
        self.is_tiled = True
        self.tile_spacing = 20
        self.rotation_angle = 45  # 默认旋转45°
        self.layer = "上方"  # 水印层级
        self.scale = 3  # 新增：水印缩放比例（默认3倍）

    def update_preview(self, text, font, color, position, is_tiled, tile_spacing, rotation_angle, layer, scale):
        self.watermark_text = text
        self.font = font
        self.color = color
        self.position = position
        self.is_tiled = is_tiled
        self.tile_spacing = tile_spacing
        self.rotation_angle = rotation_angle
        self.layer = layer
        self.scale = scale  # 新增：接收缩放比例
        self.update()  # 实时刷新预览

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制背景（模拟图片）
        bg_rect = self.rect()
        painter.fillRect(bg_rect, QColor(230, 230, 230))
        
        # 新增：设置水印缩放（核心修改）
        painter.save()
        painter.scale(self.scale, self.scale)
        
        # 绘制水印
        painter.setFont(self.font)
        painter.setPen(self.color)
        text_rect = painter.boundingRect(QtCore.QRectF(), Qt.AlignmentFlag.AlignLeft, self.watermark_text)

        if self.is_tiled:
            # 平铺+旋转模式
            text_width = text_rect.width() + self.tile_spacing
            text_height = text_rect.height() + self.tile_spacing
            cols = int(self.width()//self.scale // text_width + 2)
            rows = int(self.height()//self.scale // text_height + 2)
            
            for i in range(cols):
                for j in range(rows):
                    x = i * text_width
                    y = j * text_height
                    # 保存当前画家状态
                    painter.save()
                    # 旋转水印（以文字中心为旋转点）
                    painter.translate(
                        int(x + text_rect.width()/2),
                        int(y + text_rect.height()/2)
                    )
                    painter.rotate(self.rotation_angle)
                    painter.translate(
                        -int(text_rect.width()/2),
                        -int(text_rect.height()/2)
                    )
                    # 绘制文字（确保坐标为int）
                    painter.drawText(0, int(text_rect.height()), self.watermark_text)
                    # 恢复画家状态
                    painter.restore()
        else:
            # 固定位置模式
            pos_map = {
                "左上角": (10, text_rect.height() + 10),
                "右上角": (self.width()//self.scale - text_rect.width() - 10, text_rect.height() + 10),
                "左下角": (10, self.height()//self.scale - 10),
                "右下角": (self.width()//self.scale - text_rect.width() - 10, self.height()//self.scale - 10),
                "居中": (
                    (self.width()//self.scale - text_rect.width()) // 2,
                    (self.height()//self.scale + text_rect.height()) // 2
                )
            }
            x, y = pos_map.get(self.position, (10, 10))
            painter.save()
            painter.translate(
                int(x + text_rect.width()/2),
                int(y - text_rect.height()/2)
            )
            painter.rotate(self.rotation_angle)
            painter.translate(
                -int(text_rect.width()/2),
                -int(text_rect.height()/2)
            )
            painter.drawText(0, int(text_rect.height()), self.watermark_text)
            painter.restore()
        
        # 恢复缩放状态
        painter.restore()


# ------------------------------
# 水印设置对话框（紧凑布局+修复所有问题）
# ------------------------------
class WatermarkDialog(QDialog):
    def __init__(self, parent=None, template_data=None):
        super().__init__(parent)
        self.setWindowTitle("高级批量水印设置")
        self.setMinimumWidth(750)  # 加宽窗口
        self.result = None
        # 模板数据（新增scale参数）
        self.template_data = template_data if template_data else {
            "text": "小金毛",
            "font": "Arial",
            "font_size": 20,
            "opacity": 0.5,
            "color": "#333333",
            "is_tiled": True,
            "tile_spacing": 20,
            "rotation": 45,
            "position": "左上角",
            "layer": "上方",
            "scale": 3  # 新增：水印缩放比例（默认3倍）
        }
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)  # 增加布局间距

        # 1. 模板管理区
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("模板管理："))
        self.template_name = QLineEdit()
        self.template_name.setPlaceholderText("输入模板名称（如：小金毛水印）")
        self.template_name.setMinimumWidth(200)  # 加宽模板名称输入框
        self.save_template_btn = QPushButton("保存模板")
        self.save_template_btn.clicked.connect(self._save_template)
        self.load_template_btn = QPushButton("加载模板")
        self.load_template_btn.clicked.connect(self._load_template)
        template_layout.addWidget(self.template_name)
        template_layout.addWidget(self.save_template_btn)
        template_layout.addWidget(self.load_template_btn)
        template_layout.addStretch()  # 右对齐按钮
        main_layout.addLayout(template_layout)

        # 2. 基础设置区（标签与控件严格对齐）
        basic_layout = QVBoxLayout()  # 垂直布局，标签在上，控件在下

        # 行1：水印文字 + 字体/字号 + 颜色/透明度 + 水印层级
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(15)

        # 列1：水印文字（标签+控件）
        text_col = QVBoxLayout()
        text_col.addWidget(QLabel("水印文字："))
        self.text_input = QLineEdit(self.template_data["text"])
        self.text_input.setMinimumWidth(120)
        text_col.addWidget(self.text_input)
        row1_layout.addLayout(text_col)

        # 列2：字体/字号（标签+控件）
        font_col = QVBoxLayout()
        font_col.addWidget(QLabel("字体/字号："))
        font_h_layout = QHBoxLayout()
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(self.template_data["font"]))
        self.font_combo.setMinimumWidth(150)
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 72)
        self.font_size.setValue(self.template_data["font_size"])
        self.font_size.setMinimumWidth(80)
        font_h_layout.addWidget(self.font_combo)
        font_h_layout.addWidget(self.font_size)
        font_col.addLayout(font_h_layout)
        row1_layout.addLayout(font_col)

        # 列3：颜色/透明度（标签+控件，严格对齐）
        color_opacity_col = QVBoxLayout()
        color_opacity_col.addWidget(QLabel("颜色/透明度："))  # 标签在正上方
        color_opacity_h = QHBoxLayout()
        self.color_btn = QPushButton()
        self.color_btn.setStyleSheet(f"background-color: {self.template_data['color']}; color: white;")
        self.color_btn.setFixedSize(40, 25)  # 固定颜色按钮大小
        self.color_btn.clicked.connect(self._choose_color)  # 修复颜色按钮点击事件
        self.opacity = QDoubleSpinBox()
        self.opacity.setRange(0.1, 1.0)
        self.opacity.setSingleStep(0.1)
        self.opacity.setValue(self.template_data["opacity"])
        self.opacity.setMinimumWidth(100)  # 加宽透明度输入框
        color_opacity_h.addWidget(self.color_btn)
        color_opacity_h.addWidget(self.opacity)
        color_opacity_col.addLayout(color_opacity_h)
        row1_layout.addLayout(color_opacity_col)

        # 列4：水印层级（标签+控件）
        layer_col = QVBoxLayout()
        layer_col.addWidget(QLabel("水印层级："))
        self.layer_combo = QComboBox()
        self.layer_combo.addItems(["上方", "下方"])
        self.layer_combo.setCurrentText(self.template_data["layer"])
        self.layer_combo.setMinimumWidth(80)
        layer_col.addWidget(self.layer_combo)
        row1_layout.addLayout(layer_col)

        row1_layout.addStretch()
        basic_layout.addLayout(row1_layout)
        main_layout.addLayout(basic_layout)

        # 3. 高级设置区（紧凑布局：平铺间距+缩放同行）
        advanced_layout = QHBoxLayout()
        advanced_layout.setSpacing(10)  # 缩小控件间距

        # 左半区：平铺/位置 + 水印缩放（紧凑布局核心修改）
        mode_scale_layout = QVBoxLayout()
        mode_scale_layout.setSpacing(5)

        # 平铺相关控件
        self.tiled_check = QCheckBox("平铺水印")
        self.tiled_check.setChecked(self.template_data["is_tiled"])
        self.tiled_check.stateChanged.connect(self._toggle_tile_mode)
        mode_scale_layout.addWidget(self.tiled_check)

        # 平铺间距 + 水印缩放（放在同一行）
        tile_scale_layout = QHBoxLayout()
        tile_scale_layout.setSpacing(15)

        # 平铺间距
        self.tile_spacing_label = QLabel("平铺间距：")
        self.tile_spacing = QSpinBox()
        self.tile_spacing.setRange(5, 50)
        self.tile_spacing.setValue(self.template_data["tile_spacing"])
        self.tile_spacing.setMinimumWidth(80)
        tile_scale_layout.addWidget(self.tile_spacing_label)
        tile_scale_layout.addWidget(self.tile_spacing)
        tile_scale_layout.addStretch(1)

        # 水印缩放（移到平铺间距右侧）
        self.scale_label = QLabel("水印缩放：")
        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(1, 10)
        self.scale_spin.setValue(self.template_data["scale"])
        self.scale_spin.setSuffix(" 倍")
        self.scale_spin.setMinimumWidth(100)
        tile_scale_layout.addWidget(self.scale_label)
        tile_scale_layout.addWidget(self.scale_spin)
        mode_scale_layout.addLayout(tile_scale_layout)

        # 固定位置
        self.position_label = QLabel("固定位置：")
        position_layout = QHBoxLayout()
        position_layout.addWidget(self.position_label)
        self.position_combo = QComboBox()
        self.position_combo.addItems(["左上角", "右上角", "左下角", "右下角", "居中"])
        self.position_combo.setCurrentText(self.template_data["position"])
        self.position_combo.setMinimumWidth(100)
        position_layout.addWidget(self.position_combo)
        mode_scale_layout.addLayout(position_layout)
        advanced_layout.addLayout(mode_scale_layout)

        # 右半区：旋转角度
        rotation_layout = QVBoxLayout()
        rotation_layout.addWidget(QLabel("旋转角度："))
        self.rotation_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_slider.setRange(0, 360)
        self.rotation_slider.setValue(self.template_data["rotation"])
        self.rotation_slider.setMinimumWidth(200)
        self.rotation_label = QLabel(f"当前角度：{self.template_data['rotation']}°")
        self.rotation_slider.valueChanged.connect(lambda v: self.rotation_label.setText(f"当前角度：{v}°"))
        rotation_layout.addWidget(self.rotation_slider)
        rotation_layout.addWidget(self.rotation_label)
        advanced_layout.addLayout(rotation_layout)

        advanced_layout.addStretch()
        main_layout.addLayout(advanced_layout)

        # 4. 预览区域
        main_layout.addWidget(QLabel("实时预览："))
        self.preview = WatermarkPreviewWidget()
        self.preview.setStyleSheet("border: 1px solid #ccc;")
        self.preview.setMinimumHeight(150)  # 加高预览区
        main_layout.addWidget(self.preview)

        # 5. 批量操作区
        batch_layout = QHBoxLayout()
        self.apply_all_btn = QCheckBox("应用到所有图片（忽略选中）")
        self.replace_watermark = QCheckBox("覆盖已有水印（无需撤销）")
        batch_layout.addWidget(self.apply_all_btn)
        batch_layout.addWidget(self.replace_watermark)
        batch_layout.addStretch()
        main_layout.addLayout(batch_layout)

        # 6. 按钮区（修复确认按钮点击事件）
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton("确认应用")
        self.ok_btn.setMinimumWidth(80)
        self.ok_btn.clicked.connect(self._on_ok)  # 绑定确认按钮事件
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setMinimumWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        self.reset_btn = QPushButton("重置参数")
        self.reset_btn.setMinimumWidth(80)
        self.reset_btn.clicked.connect(self._reset_params)
        btn_layout.addStretch()
        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        main_layout.addLayout(btn_layout)

        # 初始化模式显示
        self._toggle_tile_mode()
        # 绑定实时预览（所有参数变化都触发预览）
        self.text_input.textChanged.connect(self._update_preview)
        self.font_combo.currentFontChanged.connect(self._update_preview)
        self.font_size.valueChanged.connect(self._update_preview)
        self.opacity.valueChanged.connect(self._update_preview)
        self.tiled_check.stateChanged.connect(self._update_preview)
        self.tile_spacing.valueChanged.connect(self._update_preview)
        self.position_combo.currentTextChanged.connect(self._update_preview)
        self.rotation_slider.valueChanged.connect(self._update_preview)
        self.layer_combo.currentTextChanged.connect(self._update_preview)
        self.scale_spin.valueChanged.connect(self._update_preview)  # 绑定缩放预览
        # 初始预览
        self._update_preview()

    def _toggle_tile_mode(self):
        """切换平铺/固定位置模式（修复属性名错误）"""
        is_tiled = self.tiled_check.isChecked()
        self.tile_spacing_label.setVisible(is_tiled)
        self.tile_spacing.setVisible(is_tiled)
        self.scale_label.setVisible(is_tiled)  # 缩放和间距同步显示/隐藏
        self.scale_spin.setVisible(is_tiled)
        self.position_label.setVisible(not is_tiled)
        self.position_combo.setVisible(not is_tiled)

    def _choose_color(self):
        """选择水印颜色（修复点击无响应）"""
        current_color = QColor(self.color_btn.styleSheet().split(":")[1].split(";")[0].strip())
        color = QColorDialog.getColor(current_color, self, "选择水印颜色")
        if color.isValid():
            self.color_btn.setStyleSheet(f"background-color: {color.name()}; color: white;")
            self._update_preview()

    def _save_template(self):
        """保存水印模板（包含缩放参数）"""
        template_name = self.template_name.text().strip()
        if not template_name:
            QMessageBox.warning(self, "提示", "请输入模板名称！")
            return
        # 收集当前参数
        template_data = {
            "text": self.text_input.text(),
            "font": self.font_combo.currentFont().family(),
            "font_size": self.font_size.value(),
            "opacity": self.opacity.value(),
            "color": self.color_btn.styleSheet().split(":")[1].split(";")[0].strip(),
            "is_tiled": self.tiled_check.isChecked(),
            "tile_spacing": self.tile_spacing.value(),
            "rotation": self.rotation_slider.value(),
            "position": self.position_combo.currentText(),
            "layer": self.layer_combo.currentText(),
            "scale": self.scale_spin.value()  # 新增：保存缩放参数
        }
        # 读取已有模板
        templates = {}
        if os.path.exists(WATERMARK_TEMPLATE_PATH):
            with open(WATERMARK_TEMPLATE_PATH, "r", encoding="utf-8") as f:
                templates = json.load(f)
        # 保存新模板
        templates[template_name] = template_data
        with open(WATERMARK_TEMPLATE_PATH, "w", encoding="utf-8") as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "成功", f"模板「{template_name}」保存成功！")

    def _load_template(self):
        """加载水印模板（包含缩放参数）"""
        if not os.path.exists(WATERMARK_TEMPLATE_PATH):
            QMessageBox.warning(self, "提示", "暂无保存的模板！")
            return
        # 读取模板
        with open(WATERMARK_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            templates = json.load(f)
        if not templates:
            QMessageBox.warning(self, "提示", "暂无保存的模板！")
            return
        # 选择模板
        template_names = list(templates.keys())
        selected_name, ok = QtWidgets.QInputDialog.getItem(self, "加载模板", "选择模板：", template_names, 0, False)
        if ok and selected_name:
            template_data = templates[selected_name]
            # 填充参数
            self.text_input.setText(template_data["text"])
            self.font_combo.setCurrentFont(QFont(template_data["font"]))
            self.font_size.setValue(template_data["font_size"])
            self.opacity.setValue(template_data["opacity"])
            self.color_btn.setStyleSheet(f"background-color: {template_data['color']}; color: white;")
            self.tiled_check.setChecked(template_data["is_tiled"])
            self.tile_spacing.setValue(template_data["tile_spacing"])
            self.rotation_slider.setValue(template_data["rotation"])
            self.position_combo.setCurrentText(template_data["position"])
            self.layer_combo.setCurrentText(template_data["layer"])
            self.scale_spin.setValue(template_data.get("scale", 3))  # 加载缩放参数
            self.template_name.setText(selected_name)
            # 更新预览
            self._toggle_tile_mode()
            self._update_preview()

    def _reset_params(self):
        """重置参数为默认值（包含缩放）"""
        self.text_input.setText("小金毛")
        self.font_combo.setCurrentFont(QFont("Arial"))
        self.font_size.setValue(20)
        self.opacity.setValue(0.5)
        self.color_btn.setStyleSheet("background-color: #333333; color: white;")
        self.tiled_check.setChecked(True)
        self.tile_spacing.setValue(20)
        self.rotation_slider.setValue(45)
        self.position_combo.setCurrentText("左上角")
        self.layer_combo.setCurrentText("上方")
        self.scale_spin.setValue(3)  # 重置缩放为3倍
        self.apply_all_btn.setChecked(False)
        self.replace_watermark.setChecked(False)
        self._toggle_tile_mode()
        self._update_preview()

    def _update_preview(self):
        """实时更新预览（包含缩放）"""
        text = self.text_input.text()
        font = self.font_combo.currentFont()
        font.setPointSize(self.font_size.value())
        # 获取颜色（包含透明度）
        color = QColor(self.color_btn.styleSheet().split(":")[1].split(";")[0].strip())
        color.setAlpha(int(self.opacity.value() * 255))
        position = self.position_combo.currentText()
        is_tiled = self.tiled_check.isChecked()
        tile_spacing = self.tile_spacing.value()
        rotation_angle = self.rotation_slider.value()
        layer = self.layer_combo.currentText()
        scale = self.scale_spin.value()  # 获取缩放比例
        # 更新预览
        self.preview.update_preview(text, font, color, position, is_tiled, tile_spacing, rotation_angle, layer, scale)

    def _on_ok(self):
        """确认应用水印（包含缩放参数）"""
        # 收集所有参数
        self.result = {
            "text": self.text_input.text(),
            "font": self.font_combo.currentFont(),
            "color": QColor(self.color_btn.styleSheet().split(":")[1].split(";")[0].strip()),
            "opacity": self.opacity.value(),
            "is_tiled": self.tiled_check.isChecked(),
            "tile_spacing": self.tile_spacing.value(),
            "rotation_angle": self.rotation_slider.value(),
            "position": self.position_combo.currentText(),
            "layer": self.layer_combo.currentText(),
            "apply_all": self.apply_all_btn.isChecked(),
            "replace_watermark": self.replace_watermark.isChecked(),
            "scale": self.scale_spin.value()  # 新增：传递缩放参数
        }
        # 补全颜色透明度
        self.result["color"].setAlpha(int(self.result["opacity"] * 255))
        self.accept()  # 触发对话框关闭并返回结果


# ------------------------------
# 主视图类
# ------------------------------
class BeeGraphicsView(QGraphicsView, MainControlsMixin, ActionsMixin):
    PAN_MODE = 1
    ZOOM_MODE = 2
    SAMPLE_COLOR_MODE = 3

    def on_context_menu(self, position):
        """处理右键菜单事件"""
        # 创建临时菜单
        menu = QtWidgets.QMenu(self)

        # 直接添加标签菜单，不依赖任何条件判断
        print("直接添加标签菜单到右键菜单")
    
        # 获取用户右键点击位置的图像项
        scene_pos = self.mapToScene(position)
        items_at_pos = self.items(scene_pos)
        img_item = None
    
        # 查找点击位置的图像项
        for item in items_at_pos:
            if hasattr(item, 'is_image') and item.is_image:
                img_item = item
                break
    
        # 如果直接点击位置没有找到图像项，检查是否点击了图像项的选择框或其他部分
        if not img_item:
            # 检查是否有选中的图像项
            selected_items = [item for item in self.scene.selectedItems() 
                             if hasattr(item, 'is_image') and item.is_image]
            if selected_items:
                img_item = selected_items[0]
    
        if img_item:
            self.init_image_tag_menu_ui(img_item, menu)
        else:
            # 如果没有找到图像项，添加一个测试标签菜单
            tag_submenu = QMenu("标签", menu)
            tag_submenu.addAction("测试标签项")
            menu.addMenu(tag_submenu)

        # 显示菜单
        menu.exec(self.viewport().mapToGlobal(position))

    def __init__(self, app, window, parent=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = app
        self.parent = window
        self.settings = BeeSettings()
        self.keyboard_settings = KeyboardSettings()
        self.welcome_overlay = widgets.welcome_overlay.WelcomeOverlay(self)

        self.setBackgroundBrush(QBrush(QColor(*constants.COLORS['Scene:Canvas'])))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setFrameShape(QFrame.Shape.NoFrame)
        
        # 确保上下文菜单策略正确设置
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.on_context_menu)
        
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        self.undo_stack.canRedoChanged.connect(self.on_can_redo_changed)
        self.undo_stack.canUndoChanged.connect(self.on_can_undo_changed)
        self.undo_stack.cleanChanged.connect(self.on_undo_clean_changed)

        self.filename = None
        self.previous_transform = None
        self.active_mode = None

        self.scene = BeeGraphicsScene(self.undo_stack)
        self.scene.changed.connect(self.on_scene_changed)
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.scene.cursor_changed.connect(self.on_cursor_changed)
        self.scene.cursor_cleared.connect(self.on_cursor_cleared)
        self.setScene(self.scene)  
        # 初始化主控制器
        self.init_main_controls(window)  

        self.build_menu_and_actions()
        self.control_target = self
        self.init_main_controls(main_window=window)
        self.compare_mode = False 
        self.setup_compare_mode()
        
        # 确保所有标签相关初始化完成
        print("BeeGraphicsView初始化完成")

        if commandline_args.filenames:
            fn = commandline_args.filenames[0]
            if os.path.splitext(fn)[1] == '.bee':
                self.open_from_file(fn)
            else:
                self.do_insert_images(commandline_args.filenames)

        self.update_window_title()

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value
        self.update_window_title()
        if value:
            self.settings.update_recent_files(value)
            self.update_menu_and_actions()

    def setup_compare_mode(self):
        """设置对比模式。"""
        # 添加对比模式快捷键
        self.compare_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence('Ctrl+Shift+C'), self)
        self.compare_shortcut.activated.connect(self.toggle_compare_mode)
    def toggle_compare_mode(self):
        """切换对比模式。"""
        self.compare_mode = not self.compare_mode
        self.update()
        
    def draw_comparison_grid(self):
        """在对比模式下绘制网格以显示收藏项。"""
        import math
        import os

        # 获取所有收藏项
        all_items = [item for item in self.scene.items() 
                        if hasattr(item, 'pixmap')]

        if not all_items:
            return

        # 计算网格布局
        num_items = len(all_items)
        cols = int(math.ceil(math.sqrt(num_items)))
        rows = int(math.ceil(num_items / cols))

        # 计算单元格大小
        width = self.viewport().width()
        height = self.viewport().height()
        cell_width = width / cols
        cell_height = height / rows

        painter = QtGui.QPainter(self.viewport())
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)

        # 获取当前视图的缩放比例
        scale_factor = self.get_scale()

        # 绘制网格背景
        painter.fillRect(0, 0, width, height, QtGui.QColor(50, 50, 50))

        # 绘制所有收藏项
        for i, item in enumerate(all_items):
            row = i // cols
            col = i % cols
    
            x = col * cell_width
            y = row * cell_height
    
            # 缩放图像以适应网格单元格，并考虑当前视图的缩放比例
            pixmap = item.pixmap()

             # 计算图像在单元格内的最佳缩放比例
            pixmap_ratio = pixmap.width() / pixmap.height()
            cell_ratio = cell_width / cell_height
        
            if pixmap_ratio > cell_ratio:
                # 图像更宽，按宽度缩放
                scaled_width = cell_width
                scaled_height = scaled_width / pixmap_ratio
            else:
                # 图像更高，按高度缩放
                scaled_height = cell_height
                scaled_width = scaled_height * pixmap_ratio

            # 应用当前视图的缩放比例
            scaled_width *= scale_factor
            scaled_height *= scale_factor
            
            # 缩放图像以适应网格单元格，并考虑当前视图的缩放比例
            scaled_pixmap = pixmap.scaled(
                int(scaled_width), 
                int(scaled_height),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
    
            # 居中绘制
            dx = (cell_width - scaled_width ) // 2
            dy = (cell_height - scaled_height ) // 2
        
            # 绘制图像
            painter.drawPixmap(int(x + dx), int(y + dy), scaled_pixmap)
        
            # 绘制边框
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 223, 0), 2))
            painter.drawRect(int(x), int(y), int(cell_width), int(cell_height))
        
            # 绘制文件名
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
    
            filename = os.path.basename(item.filename) if item.filename else f'Item {i+1}'
            painter.drawText(int(x + 5), int(y + 20), filename)

        painter.end()
    def cancel_active_modes(self):
        self.scene.cancel_active_modes()
        self.cancel_sample_color_mode()
        self.active_mode = None

    def cancel_sample_color_mode(self):
        logger.debug('Cancel sample color mode')
        self.active_mode = None
        self.viewport().unsetCursor()
        if hasattr(self, 'sample_color_widget'):
            self.sample_color_widget.hide()
            del self.sample_color_widget
        if self.scene.has_multi_selection():
            self.scene.multi_select_item.lower_behind_selection()

    def update_window_title(self):
        clean = self.undo_stack.isClean()
        if clean and not self.filename:
            title = constants.APPNAME
        else:
            name = os.path.basename(self.filename or '[Untitled]')
            clean = '' if clean else '*'
            title = f'{name}{clean} - {constants.APPNAME}'
        self.parent.setWindowTitle(title)

    def on_scene_changed(self, region):
        if not self.scene.items():
            logger.debug('No items in scene')
            self.setTransform(QtGui.QTransform())
            self.welcome_overlay.setFocus()
            self.clearFocus()
            self.welcome_overlay.show()
            self.actiongroup_set_enabled('active_when_items_in_scene', False)
        else:
            self.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)
            self.welcome_overlay.clearFocus()
            self.welcome_overlay.hide()
            self.actiongroup_set_enabled('active_when_items_in_scene', True)
        self.recalc_scene_rect()

    def on_can_redo_changed(self, can_redo):
        self.actiongroup_set_enabled('active_when_can_redo', can_redo)

    def on_can_undo_changed(self, can_undo):
        self.actiongroup_set_enabled('active_when_can_undo', can_undo)

    def on_undo_clean_changed(self, clean):
        self.update_window_title()

    def on_context_menu(self, point):
        self.context_menu.exec(self.mapToGlobal(point))

    def get_supported_image_formats(self, cls):
        formats = []
        for f in cls.supportedImageFormats():
            string = f'*.{f.data().decode()}'
            formats.extend((string, string.upper()))
        return ' '.join(formats)

    def get_view_center(self):
        return QtCore.QPoint(round(self.size().width() / 2), round(self.size().height() / 2))

    def clear_scene(self):
        logging.debug('Clearing scene...')
        self.cancel_active_modes()
        self.scene.clear()
        self.undo_stack.clear()
        self.filename = None
        self.setTransform(QtGui.QTransform())

    def reset_previous_transform(self, toggle_item=None):
        if (self.previous_transform and self.previous_transform['toggle_item'] != toggle_item):
            self.previous_transform = None

    def fit_rect(self, rect, toggle_item=None):
        if toggle_item and self.previous_transform:
            logger.debug('Fit view: Reset to previous')
            self.setTransform(self.previous_transform['transform'])
            self.centerOn(self.previous_transform['center'])
            self.previous_transform = None
            return
        if toggle_item:
            self.previous_transform = {
                'toggle_item': toggle_item,
                'transform': QtGui.QTransform(self.transform()),
                'center': self.mapToScene(self.get_view_center()),
            }
        else:
            self.previous_transform = None  

        logger.debug(f'Fit view: {rect}')
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.recalc_scene_rect()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.recalc_scene_rect()
        logger.trace('Fit view done')

    def get_confirmation_unsaved_changes(self, msg):
        confirm = self.settings.valueOrDefault('Save/confirm_close_unsaved')
        if confirm and not self.undo_stack.isClean():
            answer = QMessageBox.question(
                self, 'Discard unsaved changes?', msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            return answer == QMessageBox.StandardButton.Yes
        return True

    def on_action_new_scene(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. Are you sure you want to open a new scene?')
        if confirm:
            self.clear_scene()

    def on_action_fit_scene(self):
        self.fit_rect(self.scene.itemsBoundingRect())

    def on_action_fit_selection(self):
        self.fit_rect(self.scene.itemsBoundingRect(selection_only=True))

    def on_action_fullscreen(self, checked):
        if checked:
            self.parent.showFullScreen()
        else:
            self.parent.showNormal()

    def on_action_always_on_top(self, checked):
        self.parent.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on=checked)
        self.parent.destroy()
        self.parent.create()
        self.parent.show()

    def on_action_show_scrollbars(self, checked):
        if checked:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        else:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def on_action_show_menubar(self, checked):
        if checked:
            self.parent.setMenuBar(self.create_menubar())
        else:
            self.parent.setMenuBar(None)

    def on_action_show_titlebar(self, checked):
        self.parent.setWindowFlag(Qt.WindowType.FramelessWindowHint, on=not checked)
        self.parent.destroy()
        self.parent.create()
        self.parent.show()

    def on_action_move_window(self):
        if self.welcome_overlay.isHidden():
            self.on_action_movewin_mode()
        else:
            self.welcome_overlay.on_action_movewin_mode()

    def on_action_undo(self):
        logger.debug('Undo: %s' % self.undo_stack.undoText())
        self.cancel_active_modes()
        self.undo_stack.undo()

    def on_action_redo(self):
        logger.debug('Redo: %s' % self.undo_stack.redoText())
        self.cancel_active_modes()
        self.undo_stack.redo()

    def on_action_select_all(self):
        self.scene.select_all_items()
    def toggle_compare_mode(self):
        """切换对比模式。"""
        self.compare_mode = not self.compare_mode
        self.viewport().update()# 确保视图内容立即重绘
        self.update()

    def on_action_deselect_all(self):
        self.scene.deselect_all_items()

    def on_action_delete_items(self):
        logger.debug('Deleting items...')
        self.cancel_active_modes()
        self.undo_stack.push(commands.DeleteItems(self.scene, self.scene.selectedItems(user_only=True), self))

    def on_action_cut(self):
        logger.debug('Cutting items...')
        self.on_action_copy()
        self.undo_stack.push(commands.DeleteItems(self.scene, self.scene.selectedItems(user_only=True), self))

    def on_action_toggle_favorite(self):
        """切换选中项的收藏状态。"""
        items = self.scene.selectedItems(user_only=True)
        if items:
            self.undo_stack.push(commands.ToggleFavorite(items, self.scene))
            self.update_menu_and_actions()
    def on_action_jump_to_favorite(self, item): 
        """跳转到指定的收藏项。""" 
        # 检查项目是否仍然在场景中
        if item.scene() != self.scene:
            # 如果项目不在场景中，更新收藏菜单并返回
            self.update_menu_and_actions()
            return
    
        # 清除当前选择 
        self.scene.clearSelection() 
        # 选择目标项 
        item.setSelected(True) 
        # 将项目移到最前面
        item.bring_to_front()
        # 重置视图变换
        self.resetTransform()
        # 确保项目完整显示在视图中，保持纵横比
        self.fitInView(item.boundingRect(),Qt.AspectRatioMode.KeepAspectRatio)
        # 稍微缩小一点，留一些边距
        self.scale(0.9, 0.9)
        # 确保视图更新 
        self.viewport().update()    
    def on_action_raise_to_top(self):
        self.scene.raise_to_top()

    def on_action_lower_to_bottom(self):
        self.scene.lower_to_bottom()

    def on_action_normalize_height(self):
        self.scene.normalize_height()

    def on_action_normalize_width(self):
        self.scene.normalize_width()

    def on_action_normalize_size(self):
        self.scene.normalize_size()

    def on_action_arrange_horizontal(self):
        self.scene.arrange()

    def on_action_arrange_vertical(self):
        self.scene.arrange(vertical=True)

    def on_action_arrange_optimal(self):
        self.scene.arrange_optimal()

    def on_action_arrange_square(self):
        self.scene.arrange_square()

    def on_action_change_opacity(self):
        images = list(filter(lambda item: item.is_image, self.scene.selectedItems(user_only=True)))
        widgets.ChangeOpacityDialog(self, images, self.undo_stack)

    def on_action_grayscale(self, checked):
        images = list(filter(lambda item: item.is_image, self.scene.selectedItems(user_only=True)))
        if images:
            self.undo_stack.push(commands.ToggleGrayscale(images, checked))

    def on_action_crop(self):
        self.scene.crop_items()

    def on_action_flip_horizontally(self):
        self.scene.flip_items(vertical=False)

    def on_action_flip_vertically(self):
        self.scene.flip_items(vertical=True)

    def on_action_reset_scale(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetScale(self.scene.selectedItems(user_only=True)))

    def on_action_reset_rotation(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetRotation(self.scene.selectedItems(user_only=True)))

    def on_action_reset_flip(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetFlip(self.scene.selectedItems(user_only=True)))

    def on_action_reset_crop(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetCrop(self.scene.selectedItems(user_only=True)))

    def on_action_reset_transforms(self):
        self.cancel_active_modes()
        self.undo_stack.push(commands.ResetTransforms(self.scene.selectedItems(user_only=True)))

    def on_action_show_color_gamut(self):
        widgets.color_gamut.GamutDialog(self, self.scene.selectedItems()[0])

    def on_action_sample_color(self):
        self.cancel_active_modes()
        logger.debug('Entering sample color mode')
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self.active_mode = self.SAMPLE_COLOR_MODE

        if self.scene.has_multi_selection():
            self.scene.multi_select_item.lower_behind_selection()

        pos = self.mapFromGlobal(self.cursor().pos())
        self.sample_color_widget = widgets.SampleColorWidget(
            self, pos, self.scene.sample_color_at(self.mapToScene(pos)))

    def on_items_loaded(self, value):
        logger.debug('On items loaded: add queued items')
        self.scene.add_queued_items()

    def on_loading_finished(self, filename, errors):
        if errors:
            QMessageBox.warning(
                self, 'Problem loading file',
                ('<p>Problem loading file %s</p><p>Not accessible or not a proper bee file</p>') % filename)
        else:
            self.filename = filename
            self.scene.add_queued_items()
            self.on_action_fit_scene()

    def on_action_open_recent_file(self, filename):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. Are you sure you want to open a new scene?')
        if confirm:
            self.open_from_file(filename)

    def open_from_file(self, filename):
        logger.info(f'Opening file {filename}')
        self.clear_scene()
        self.worker = fileio.ThreadedIO(fileio.load_bee, filename, self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.progress = widgets.BeeProgressDialog(f'Loading {filename}', worker=self.worker, parent=self)
        self.worker.start()

    def on_action_open(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. Are you sure you want to open a new scene?')
        if not confirm:
            return

        self.cancel_active_modes()
        filename, f = QFileDialog.getOpenFileName(
            parent=self, caption='Open file', filter=f'{constants.APPNAME} File (*.bee)')
        if filename:
            filename = os.path.normpath(filename)
            self.open_from_file(filename)
            self.filename = filename

    def on_saving_finished(self, filename, errors):
        if errors:
            QMessageBox.warning(
                self, 'Problem saving file',
                ('<p>Problem saving file %s</p><p>File/directory not accessible</p>') % filename)
        else:
            self.filename = filename
            self.undo_stack.setClean()

    def do_save(self, filename, create_new):
        if not fileio.is_bee_file(filename):
            filename = f'{filename}.bee'
        self.worker = fileio.ThreadedIO(fileio.save_bee, filename, self.scene, create_new=create_new)
        self.worker.finished.connect(self.on_saving_finished)
        self.progress = widgets.BeeProgressDialog(f'Saving {filename}', worker=self.worker, parent=self)
        self.worker.start()

    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QFileDialog.getSaveFileName(
            parent=self, caption='Save file', directory=directory, filter=";;".join((f"{constants.APPNAME} File (*.bee)", "PDF (*.pdf)")))
        if filename:
            name, ext = os.path.splitext(filename)
            if not ext:
                ext = get_file_extension_from_format(formatstr)
                filename = f"{filename}.{ext}"
            if ext.lower() == ".pdf":
                self.on_action_export_scene(filename=filename)
                return
            self.do_save(filename, create_new=True)

    def on_action_save(self):
        self.cancel_active_modes()
        if not self.filename:
            self.on_action_save_as()
        else:
            self.do_save(self.filename, create_new=False)

    def on_action_export_scene(self, filename=None):
        directory = os.path.dirname(self.filename) if self.filename else None
        if not filename:
            filename, formatstr = QFileDialog.getSaveFileName(
                parent=self, caption='Export Scene to Image', directory=directory,
                filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg *.pdf)', 'PNG (*.png)', 'JPEG (*.jpg *.jpeg)', 'SVG (*.svg)', 'PDF (*.pdf)')))

        if not filename:
            return

        name, ext = os.path.splitext(filename)
        if not ext:
            ext = get_file_extension_from_format(formatstr)
            filename = f'{filename}.{ext}'
        logger.debug(f'Got export filename {filename}')

        exporter_cls = exporter_registry[ext.lstrip(".")]
        exporter = exporter_cls(self.scene)
        if not exporter.get_user_input(self, ext):
            return

        self.worker = fileio.ThreadedIO(exporter.export, filename)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(f'Exporting {filename}', worker=self.worker, parent=self)
        self.worker.start()

    def on_export_finished(self, filename, errors):
        if errors:
            err_msg = '</br>'.join(str(errors))
            QMessageBox.warning(
                self, 'Problem writing file',
                f'<p>Problem writing file {filename}</p><p>{err_msg}</p>')

    def on_action_export_images(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        directory = QFileDialog.getExistingDirectory(parent=self, caption='Export Images', directory=directory)
        if not directory:
            return

        logger.debug(f'Got export directory {directory}')
        self.exporter = ImagesToDirectoryExporter(self.scene, directory)
        self.worker = fileio.ThreadedIO(self.exporter.export)
        self.worker.user_input_required.connect(self.on_export_images_file_exists)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(f'Exporting to {directory}', worker=self.worker, parent=self)
        self.worker.start()

    def on_action_export_favorites(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        directory = QFileDialog.getExistingDirectory(parent=self, caption='Export Favorite Images', directory=directory)
        if not directory:
            return

        logger.debug(f'Got export directory {directory} for favorites')
        self.exporter = ImagesToDirectoryExporter(self.scene, directory, only_favorites=True)
        self.worker = fileio.ThreadedIO(self.exporter.export)
        self.worker.user_input_required.connect(self.on_export_images_file_exists)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(f'Exporting favorites to {directory}', worker=self.worker, parent=self)
        self.worker.start()

    def on_export_images_file_exists(self, filename):
        dlg = widgets.ExportImagesFileExistsDialog(self, filename)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.exporter.handle_existing = dlg.get_answer()
            directory = self.exporter.dirname
            self.progress = widgets.BeeProgressDialog(f'Exporting to {directory}', worker=self.worker, parent=self)
            self.worker.start()

    def on_action_quit(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. Are you sure you want to quit?')
        if confirm:
            logger.info('User quit. Exiting...')
            self.app.quit()

    def on_action_settings(self):
        widgets.settings.SettingsDialog(self)

    def on_action_keyboard_settings(self):
        widgets.controls.ControlsDialog(self)

    def on_action_help(self):
        widgets.HelpDialog(self)

    def on_action_about(self):
        QMessageBox.about(
            self, f'About {constants.APPNAME}',
            (f'<h2>{constants.APPNAME} {constants.VERSION}</h2>'
             f'<p>{constants.APPNAME_FULL}</p>'
             f'<p>{constants.COPYRIGHT}</p>'
             f'<p><a href="{constants.WEBSITE}">Visit the {constants.APPNAME} website</a></p>'))

    def on_action_debuglog(self):
        widgets.DebugLogDialog(self)

    def on_insert_images_finished(self, new_scene, filename, errors):
        logger.debug('Insert images finished. Errors: %s', errors)
        if errors:
            errornames = [f'<li>{fn}</li>' for fn in errors]
            errornames = '<ul>%s</ul>' % '\n'.join(errornames)
            num = len(errors)
            msg = f'{num} image(s) could not be opened.<br/>'
            QMessageBox.warning(
                self, 'Problem loading images', msg + IMG_LOADING_ERROR_MSG + errornames)
        self.scene.add_queued_items()
        self.scene.arrange_default()
        self.undo_stack.endMacro()
        if new_scene:
            self.on_action_fit_scene()

    def do_insert_images(self, filenames, pos=None):
        if not pos:
            pos = self.get_view_center()
        self.scene.deselect_all_items()
        self.undo_stack.beginMacro('Insert Images')
        self.worker = fileio.ThreadedIO(
            fileio.load_images, filenames, self.mapToScene(pos), self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(partial(self.on_insert_images_finished, not self.scene.items()))
        self.progress = widgets.BeeProgressDialog('Loading images', worker=self.worker, parent=self)
        self.worker.start()

    def on_action_insert_images(self):
        self.cancel_active_modes()
        formats = self.get_supported_image_formats(QImageReader)
        logger.debug(f'Supported image types for reading: {formats}')
        filenames, f = QFileDialog.getOpenFileNames(
            parent=self, caption='Select one or more images to open', filter=f'Images ({formats})')
        self.do_insert_images(filenames)

    def on_action_insert_text(self):
        self.cancel_active_modes()
        item = BeeTextItem()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        item.setScale(1 / self.get_scale())
        self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))

    def on_action_copy(self):
        logger.debug('Copying to clipboard...')
        self.cancel_active_modes()
        clipboard = QApplication.clipboard()
        items = self.scene.selectedItems(user_only=True)

        if items:
            items[0].copy_to_clipboard(clipboard)
            self.scene.copy_selection_to_internal_clipboard()
            clipboard.mimeData().setData('beeref/items', QtCore.QByteArray.number(len(items)))

    def on_action_paste(self):
        self.cancel_active_modes()
        logger.debug('Pasting from clipboard...')
        clipboard = QApplication.clipboard()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))

        data = clipboard.mimeData().data('beeref/items')
        logger.debug(f'Custom data in clipboard: {data}')
        if data and self.scene.internal_clipboard:
            self.scene.paste_from_internal_clipboard(pos)
            return

        img = clipboard.image()
        if not img.isNull():
            item = BeePixmapItem(img)
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            if len(self.scene.items()) == 1:
                self.on_action_fit_scene()
            return
        text = clipboard.text()
        if text:
            item = BeeTextItem(text)
            item.setScale(1 / self.get_scale())
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            return

        msg = 'No image data or text in clipboard or image too big'
        logger.info(msg)
        widgets.BeeNotification(self, msg)

    def on_action_open_settings_dir(self):
        dirname = os.path.dirname(self.settings.fileName())
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(dirname))

    def on_selection_changed(self):
        # 检查场景是否已被删除
        if not self.scene:
            return
    
        try:
            logger.debug('Currently selected items: %s', len(self.scene.selectedItems(user_only=True)))
            self.actiongroup_set_enabled('active_when_selection', self.scene.has_selection())
            self.actiongroup_set_enabled('active_when_single_image', self.scene.has_single_image_selection())

            # 初始化grayscale为默认值
            grayscale = False
            if self.scene.has_selection():
                item = self.scene.selectedItems(user_only=True)[0]
                grayscale = getattr(item, 'grayscale', False)
            actions.actions['grayscale'].qaction.setChecked(grayscale)
        except RuntimeError:
        # 捕获场景已被删除的异常
            logger.debug('Scene has been deleted, skipping selection update')
        finally:
            self.viewport().repaint()

    def on_cursor_changed(self, cursor):
        if self.active_mode is None:
            self.viewport().setCursor(cursor)

    def on_cursor_cleared(self):
        if self.active_mode is None:
            self.viewport().unsetCursor()

    def recalc_scene_rect(self):
        if self.previous_transform:
            return
        logger.trace('Recalculating scene rectangle...')
        try:
            topleft = self.mapFromScene(self.scene.itemsBoundingRect().topLeft())
            topleft = self.mapToScene(QtCore.QPoint(
                int(topleft.x() - self.size().width() / 2),
                int(topleft.y() - self.size().height() / 2)))
            bottomright = self.mapFromScene(self.scene.itemsBoundingRect().bottomRight())
            bottomright = self.mapToScene(QtCore.QPoint(
                int(bottomright.x() + self.size().width() / 2),
                int(bottomright.y() + self.size().height() / 2)))
            self.setSceneRect(QtCore.QRectF(topleft, bottomright))
        except OverflowError:
            logger.info('Maximum scene size reached')
        logger.trace('Done recalculating scene rectangle')

    def get_zoom_size(self, func):
        topleft = self.mapFromScene(self.scene.itemsBoundingRect().topLeft())
        bottomright = self.mapFromScene(self.scene.itemsBoundingRect().bottomRight())
        return func(bottomright.x() - topleft.x(), bottomright.y() - topleft.y())

    def scale(self, *args, **kwargs):
        super().scale(*args, **kwargs)
        self.scene.on_view_scale_change()
        self.recalc_scene_rect()

    def get_scale(self):
        return self.transform().m11()

    def pan(self, delta):
        if not self.scene.items():
            logger.debug('No items in scene; ignore pan')
            return

        hscroll = self.horizontalScrollBar()
        hscroll.setValue(int(hscroll.value() + delta.x()))
        vscroll = self.verticalScrollBar()
        vscroll.setValue(int(vscroll.value() + delta.y()))

    def zoom(self, delta, anchor):
        if not self.scene.items():
            logger.debug('No items in scene; ignore zoom')
            return

        anchor = QtCore.QPoint(round(anchor.x()), round(anchor.y()))
        ref_point = self.mapToScene(anchor)
        if delta == 0:
            return
        factor = 1 + abs(delta / 1000)
        if delta > 0:
            if self.get_zoom_size(max) < 10000000:
                self.scale(factor, factor)
            else:
                logger.debug('Maximum zoom size reached')
                return
        else:
            if self.get_zoom_size(min) > 50:
                self.scale(1/factor, 1/factor)
            else:
                logger.debug('Minimum zoom size reached')
                return

        self.pan(self.mapFromScene(ref_point) - anchor)
        self.reset_previous_transform()

    def wheelEvent(self, event):
        action, inverted = self.keyboard_settings.mousewheel_action_for_event(event)
        delta = event.angleDelta().y()
        if inverted:
            delta = delta * -1

        if action == 'zoom':
            self.zoom(delta, event.position())
            event.accept()
            return
        if action == 'pan_horizontal':
            self.pan(QtCore.QPointF(delta * 0.1, 0))
            event.accept()
            return
        if action == 'pan_vertical':
            self.pan(QtCore.QPointF(0, delta * 0.1))
            event.accept()
            return
        super().wheelEvent(event)
    def mousePressEvent(self, event):
        if self.mousePressEventMainControls(event):
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            if (event.button() == Qt.MouseButton.LeftButton):
                color = self.scene.sample_color_at(self.mapToScene(event.pos()))
                if color:
                    name = qcolor_to_hex(color)
                    clipboard = QApplication.clipboard()
                    clipboard.setText(name)
                    self.scene.internal_clipboard = []
                    msg = f'Copied color to clipboard: {name}'
                    logger.debug(msg)
                    widgets.BeeNotification(self, msg)
                else:
                    logger.debug('No color found at %s', event.pos())
            self.cancel_sample_color_mode()
            event.accept()
            return

        action, inverted = self.keyboard_settings.mouse_action_for_event(event)
        if action == 'zoom':
            self.active_mode = self.ZOOM_MODE
            self.event_start = event.position()
            self.event_anchor = event.position()
            self.event_inverted = inverted
            event.accept()
            return
        if action == 'pan':
            logger.trace('Begin pan')
            self.active_mode = self.PAN_MODE
            self.event_start = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.PAN_MODE:
            self.reset_previous_transform()
            delta = event.position() - self.event_start
            self.event_start = event.position()
            self.pan(-delta)
            event.accept()
            return
        if self.active_mode == self.ZOOM_MODE:
            self.reset_previous_transform()
            delta = event.position().y() - self.event_start.y()
            self.event_start = event.position()
            if self.event_inverted:
                delta = -delta
            self.zoom(delta * 10, self.event_anchor)
            event.accept()
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.sample_color_widget.update(event.position(), self.scene.sample_color_at(self.mapToScene(event.pos())))
            event.accept()
            return

        if self.mouseMoveEventMainControls(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_mode == self.PAN_MODE:
            logger.trace('End pan')
            self.viewport().unsetCursor()
            self.active_mode = None
            event.accept()
            return
        if self.active_mode == self.ZOOM_MODE:
            self.active_mode = None
            event.accept()
            return
        if self.mouseReleaseEventMainControls(event):
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.recalc_scene_rect()
        self.welcome_overlay.resize(self.size())

    def keyPressEvent(self, event):
        if self.keyPressEventMainControls(event):
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.cancel_sample_color_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------
    # 高级批量水印方法（支持缩放）
    # ------------------------------
    def on_action_add_watermark(self):
        """高级批量水印功能：模板/旋转/层级/缩放/批量应用"""
        # 打开高级水印对话框
        dialog = WatermarkDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        params = dialog.result

        # 确定要处理的图片（全部/选中）
        if params["apply_all"]:
            image_items = [item for item in self.scene.items() if isinstance(item, BeePixmapItem)]
        else:
            selected_items = self.scene.selectedItems(user_only=True)
            image_items = [item for item in selected_items if isinstance(item, BeePixmapItem)]

        if not image_items:
            QMessageBox.warning(self, "提示", "没有可处理的图片！")
            return

        # 批量应用水印
        self.undo_stack.beginMacro(f"高级批量添加水印（{len(image_items)}张）")
        for item in image_items:
            # 如果选择覆盖水印，先恢复原图（简单实现：重新复制原图）
            if params["replace_watermark"]:
                original_pixmap = item.pixmap().copy()  # 重新获取原图（避免叠加水印）
            else:
                original_pixmap = item.pixmap()

            if original_pixmap.isNull():
                continue

            # 创建新图片（根据层级决定绘制顺序）
            new_pixmap = QPixmap(original_pixmap.size())
            new_pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter()
            painter.begin(new_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            # 绘制层级：水印在下方/上方
            if params["layer"] == "下方":
                # 先绘水印，再绘原图（水印被遮挡）
                self._draw_watermark(painter, original_pixmap.size(), params)
                painter.drawPixmap(0, 0, original_pixmap)
            else:
                # 先绘原图，再绘水印（水印在上方）
                painter.drawPixmap(0, 0, original_pixmap)
                self._draw_watermark(painter, original_pixmap.size(), params)

            painter.end()  # 确保画笔关闭

            # 应用水印
            self.undo_stack.push(commands.UpdatePixmap(item, new_pixmap))
        self.undo_stack.endMacro()

        # 提示完成
        QMessageBox.information(self, "成功", f"已为 {len(image_items)} 张图片添加水印！")

    def _draw_watermark(self, painter, pixmap_size, params):
        """独立的水印绘制函数（支持缩放）"""
        # 新增：设置水印缩放（核心修改）
        painter.save()
        painter.scale(params["scale"], params["scale"])
        
        # 设置水印样式
        painter.setFont(params["font"])
        painter.setPen(params["color"])

        text = params["text"]
        text_rect = painter.boundingRect(QtCore.QRectF(), Qt.AlignmentFlag.AlignLeft, text)

        if params["is_tiled"]:
            # 平铺+旋转水印（适配缩放）
            text_width = text_rect.width() + params["tile_spacing"]
            text_height = text_rect.height() + params["tile_spacing"]
            cols = int(pixmap_size.width()//params["scale"] // text_width + 2)
            rows = int(pixmap_size.height()//params["scale"] // text_height + 2)

            for i in range(cols):
                for j in range(rows):
                    x = i * text_width
                    y = j * text_height
                    # 旋转水印
                    painter.save()
                    painter.translate(
                        int(x + text_rect.width()/2),
                        int(y + text_rect.height()/2)
                    )
                    painter.rotate(params["rotation_angle"])
                    painter.translate(
                        -int(text_rect.width()/2),
                        -int(text_rect.height()/2)
                    )
                    # 绘制文字（确保坐标为int）
                    painter.drawText(0, int(text_rect.height()), text)
                    painter.restore()
        else:
            # 固定位置水印（适配缩放）
            pos_map = {
                "左上角": (10, text_rect.height() + 10),
                "右上角": (pixmap_size.width()//params["scale"] - text_rect.width() - 10, text_rect.height() + 10),
                "左下角": (10, pixmap_size.height()//params["scale"] - 10),
                "右下角": (pixmap_size.width()//params["scale"] - text_rect.width() - 10, pixmap_size.height()//params["scale"] - 10),
                "居中": (
                    (pixmap_size.width()//params["scale"] - text_rect.width()) // 2,
                    (pixmap_size.height()//params["scale"] + text_rect.height()) // 2
                )
            }
            x, y = pos_map.get(params["position"], (10, 10))
            # 旋转水印
            painter.save()
            painter.translate(
                int(x + text_rect.width()/2),
                int(y - text_rect.height()/2)
            )
            painter.rotate(params["rotation_angle"])
            painter.translate(
                -int(text_rect.width()/2),
                -int(text_rect.height()/2)
            )
            painter.drawText(0, int(text_rect.height()), text)
            painter.restore()
        
        # 恢复缩放状态
        painter.restore()
    def paintEvent(self, event):
        """重写绘制事件以处理对比模式。"""
        if self.compare_mode:
            self.draw_comparison_grid()
        else:
            super().paintEvent(event)

    def on_action_add_tag(self):
        """为选中的图像添加标签"""
        # 获取当前选中的图像项
        selected_items = self.scene.selectedItems()
        pixmap_items = [item for item in selected_items if hasattr(item, 'save_id') and item.save_id is not None]
    
        if not pixmap_items:
            QtWidgets.QMessageBox.information(self, "添加标签", "请先选择一个或多个图像")
            return
    
        # 获取所有标签
        all_tags = self.scene.tag_manager.get_all_tags()
    
        if not all_tags:
            QtWidgets.QMessageBox.information(self, "添加标签", "当前没有可用的标签，请先创建标签")
            return
    
        # 弹出标签选择对话框
        from beeref.widgets.tag_dialogs import TagSelectDialog
        dialog = TagSelectDialog(self, all_tags)
    
        if dialog.exec():
            selected_tag_id = dialog.get_selected_tag_id()
            if selected_tag_id:
                # 为所有选中的图像项添加标签
                self.scene.tag_manager.add_tags_to_images(pixmap_items, [selected_tag_id])
                QtWidgets.QMessageBox.information(self, "添加标签", f"已成功为{len(pixmap_items)}个图像添加标签")

    def on_action_export_by_tag(self):
        """按标签导出图像"""
        # 获取所有标签
        all_tags = self.scene.tag_manager.get_all_tags()
    
        if not all_tags:
            QtWidgets.QMessageBox.information(self, "按标签导出", "当前没有可用的标签，请先创建标签")
            return
    
        # 弹出标签选择对话框，指定 purpose="export"
        from beeref.widgets.tag_dialogs import TagSelectDialog
        dialog = TagSelectDialog(self, all_tags, purpose="export")  # 这里添加 purpose 参数
    
        if dialog.exec():
            selected_tag_id = dialog.get_selected_tag_id()
            if selected_tag_id:
                # 选择导出目录
                export_path = QtWidgets.QFileDialog.getExistingDirectory(
                    self, "选择导出目录", "", QtWidgets.QFileDialog.Option.ShowDirsOnly
                )
            
                if export_path:
                    # 设置导出参数
                    export_params = {
                        "tag_id": selected_tag_id,
                        "export_path": export_path,
                        "format": "PNG",  # 默认导出为PNG格式
                        "quality": 90,  # 默认质量90%
                        "grayscale": False,  # 默认不转为灰度图
                        "crop": False  # 默认不裁剪
                    }
                
                    # 执行导出
                    success = self.scene.tag_manager.export_tagged_images(
                        export_params['tag_id'],
                        export_params['export_path'],
                        export_params
                    )
                
                    if success:
                        QtWidgets.QMessageBox.information(self, "导出成功", f"按标签导出完成，已导出到 {export_path}")
                    else:
                        QtWidgets.QMessageBox.warning(self, "导出失败", "没有找到符合条件的图像或导出过程中发生错误")

class BeeView(QtWidgets.QGraphicsView):   
    def __init__(self, *args, **kwargs):
        self.compare_mode = False
        self.compare_items = []
        self.setupCompareMode()
        
    def setupCompareMode(self):
        """设置对比模式快捷键和菜单。"""
        self.compare_action = QtWidgets.QAction(_('Toggle Compare Mode'), self)
        self.compare_action.setShortcut('Ctrl+Shift+C')
        self.compare_action.triggered.connect(self.toggleCompareMode)
        self.addAction(self.compare_action)
        
    def toggleCompareMode(self):
        """切换对比模式。"""
        self.compare_mode = not self.compare_mode
        self.scene().update()
        
    def paintEvent(self, event):
        """重写绘制事件以处理对比模式。"""
        super().paintEvent(event)
        
        if self.compare_mode:
            self.drawComparisonGrid()
            
    
    def drawComparisonGrid(self):
        """在对比模式下绘制网格以显示收藏项。"""
        # 获取所有图像项目（移除收藏项筛选条件）
        all_items = [item for item in self.scene().items() 
                    if hasattr(item, 'pixmap')]  # 确保是有pixmap属性的图像项目

        if not all_items:
            return
        
        # 计算网格布局
        num_items = len(all_items)
        cols = int(math.ceil(math.sqrt(num_items)))
        rows = int(math.ceil(num_items / cols))
    
        width = self.viewport().width()
        height = self.viewport().height()
        cell_width = width / cols
        cell_height = height / rows
    
        painter = QtGui.QPainter(self.viewport())
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)
    
        # 获取当前视图的缩放比例
        scale_factor = self.get_scale()
    
        # 绘制网格背景
        painter.fillRect(0, 0, width, height, QtGui.QColor(50, 50, 50))
    
        # 绘制所有收藏项
        for i, item in enumerate(all_items):
            row = i // cols
            col = i % cols
        
            x = col * cell_width
            y = row * cell_height
        
            # 缩放图像以适应网格单元格，并考虑当前视图的缩放比例
            pixmap = item.pixmap()
            scaled_pixmap = pixmap.scaled(
                int(cell_width / scale_factor), 
                int(cell_height / scale_factor),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
        
            # 居中绘制
            dx = (cell_width - scaled_pixmap.width() * scale_factor) // 2
            dy = (cell_height - scaled_pixmap.height() * scale_factor) // 2
        
            # 保存当前绘制状态
            painter.save()
        
            # 应用缩放变换
            painter.translate(x + dx, y + dy)
            painter.scale(scale_factor, scale_factor)
        
            # 绘制缩放后的图像
            painter.drawPixmap(0, 0, scaled_pixmap)
        
            # 恢复绘制状态
            painter.restore()
        
            # 绘制边框
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 223, 0), 2))
            painter.drawRect(x, y, cell_width, cell_height)
        
            # 绘制文件名
            font = painter.font()
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255)))
            
            filename = os.path.basename(item.filename) if item.filename else f'Item {i+1}'
            painter.drawText(int(x + 5), int(y + 20), filename)
    
        painter.end()

    def _build_favorites_menu(self, menu=None):
        """
        构建收藏夹菜单项

        参数:
            menu: 收藏夹子菜单对象（可选）
        """
        # 如果提供了菜单，则保存为收藏夹子菜单
        if menu:
            self._favorites_submenu = menu
        # 清除现有收藏夹菜单内容
        self._clear_favorites_menu()

        # 获取所有收藏项 
        favorite_items = [item for item in self.scene.items(user_only=True)
                        if hasattr(item, 'favorite') and item.favorite]

        # 为每个收藏项创建动作
        for i, item in enumerate(favorite_items):
            action_id = f'favorites_item_{i}'
            # 创建动作定义
            action = Action(id=action_id,
                            menu_id='_build_favorites_menu',
                            text=f'Item {i + 1}')
            # 将动作添加到actions字典
            self.actions[action_id] = action

            # 创建动作对象，显示文件名（不含路径）
            filename = os.path.basename(item.filename) if item.filename else f'Item {i+1}'
            qaction = QtGui.QAction(filename, self)
            # 连接触发信号到跳转到收藏项的方法（绑定当前收藏项）
            qaction.triggered.connect(
                partial(self.on_action_jump_to_favorite, item))
            # 将动作添加到窗口
            self.addAction(qaction)
            # 保存QAction到动作定义
            action.qaction = qaction
            # 将动作添加到收藏夹子菜单
            self._favorites_submenu.addAction(qaction)

    def _clear_favorites_menu(self):
        """清除收藏夹菜单中的所有动作"""
        if hasattr(self, '_favorites_submenu'):
            # 移除子菜单中所有动作的关联
            for action in self._favorites_submenu.actions():
                self.removeAction(action)
            # 清空子菜单
            self._favorites_submenu.clear()
            # 从actions字典中移除收藏夹相关的动作
            for key in list(self.actions.keys()):
                if key.startswith('favorites_item_'):
                    self.actions[key].qaction = None
                    del self.actions[key]