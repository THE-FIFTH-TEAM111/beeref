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

import logging
from functools import partial
import uuid

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref import commands, widgets
from beeref.items import BeePixmapItem
from beeref import fileio
from PyQt6.QtWidgets import QMenu, QFileDialog
from beeref.widgets.tag_dialogs import TagEditDialog, TagSelectDialog
from beeref.commands import AddTagCommand

logger = logging.getLogger(__name__)


class MainControlsMixin:
    """Basic controls shared by the main view and the welcome overlay:

    * Right-click menu
    * Dropping files
    * Moving the window without title bar
    """

    def __init__(self, *args, **kwargs):  # 改为接受可变参数
        super().__init__(*args, **kwargs)  # 调用父类构造
        self.tag_cache = {}  # 初始化本地缓存

    def init_main_controls(self, main_window):
        self.main_window = main_window
        self.tag_cache = {}  # 在这里初始化缓存
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(
            self.control_target.on_context_menu)
        self.setAcceptDrops(True)
        self.movewin_active = False
        self.init_tag_menu()

    def on_action_movewin_mode(self):
        if self.movewin_active:
            self.exit_movewin_mode()
        else:
            self.enter_movewin_mode()

    @property
    def viewport_or_self(self):
        if hasattr(self, 'viewport'):
            return self.viewport()
        return self  

    def enter_movewin_mode(self):
        logger.debug('Entering movewin mode')
        self.setMouseTracking(True)
        self.movewin_active = True
        self.viewport_or_self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.event_start = QtCore.QPointF(self.cursor().pos())
        if hasattr(self, 'disable_mouse_events'):
            self.disable_mouse_events()  

    def exit_movewin_mode(self):
        logger.debug('Exiting movewin mode')
        self.setMouseTracking(False)
        self.movewin_active = False
        self.viewport_or_self.unsetCursor()
        if hasattr(self, 'enable_mouse_events'):
            self.enable_mouse_events()  

    def dragEnterEvent(self, event):
        mimedata = event.mimeData()
        logger.debug(f'Drag enter event: {mimedata.formats()}')
        if mimedata.hasUrls():
            event.acceptProposedAction()
        elif mimedata.hasImage():
            event.acceptProposedAction()
        else:
            msg = 'Attempted drop not an image or image too big'
            logger.info(msg)
            widgets.BeeNotification(self.control_target, msg)    

    def dragMoveEvent(self, event):
        event.acceptProposedAction() 

    def dropEvent(self, event):
        mimedata = event.mimeData()
        logger.debug(f'Handling file drop: {mimedata.formats()}')
        pos = QtCore.QPoint(round(event.position().x()),
                            round(event.position().y()))
        if mimedata.hasUrls():
            logger.debug(f'Found dropped urls: {mimedata.urls()}')
            if not self.control_target.scene.items():
                path = mimedata.urls()[0]
                if (path.isLocalFile()
                        and fileio.is_bee_file(path.toLocalFile())):
                    self.control_target.open_from_file(path.toLocalFile())
                    return
            self.control_target.do_insert_images(mimedata.urls(), pos)
        elif mimedata.hasImage():
            img = QtGui.QImage(mimedata.imageData())
            item = BeePixmapItem(img)
            pos = self.control_target.mapToScene(pos)
            self.control_target.undo_stack.push(
                commands.InsertItems(self.control_target.scene, [item], pos))
        else:
            logger.info('Drop not an image')

    def mousePressEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True

        action, inverted = self.control_target.keyboard_settings.mouse_action_for_event(event)
        if action == 'movewindow':
            self.enter_movewin_mode()
            event.accept()
            return True    

    def mouseMoveEventMainControls(self, event):
        if self.movewin_active:
            pos = self.mapToGlobal(event.position())
            delta = pos - self.event_start
            self.event_start = pos
            self.main_window.move(self.main_window.x() + int(delta.x()),
                                  self.main_window.y() + int(delta.y()))
            event.accept()
            return True    

    def mouseReleaseEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True    

    def keyPressEventMainControls(self, event):
        if self.movewin_active:
            self.exit_movewin_mode()
            event.accept()
            return True    

    def init_tag_menu(self):
        """初始化顶部菜单栏和图像右键菜单的标签功能"""
        # 1. 顶部菜单栏添加“标签”菜单
        self.tag_menu = QMenu("标签", self.main_window)
        self.main_window.menuBar().addMenu(self.tag_menu)
        
        # 新增标签菜单项
        self.add_tag_action = self.tag_menu.addAction("新增标签")
        self.add_tag_action.triggered.connect(self.on_add_tag)
        
        # 按标签导出菜单项
        self.export_by_tag_action = self.tag_menu.addAction("按标签导出")
        self.export_by_tag_action.triggered.connect(self.on_export_by_tag)

        # 2. 初始化BeeGraphicsView的图片右键菜单
        if not hasattr(self.control_target, 'image_context_menu'):
            self.control_target.image_context_menu = QMenu(self.control_target)
        
        # 3. 重写BeeGraphicsView的on_context_menu方法
        def custom_on_context_menu(pos):
            scene_pos = self.control_target.mapToScene(pos)
            items = self.control_target.scene.items(scene_pos)
            selected_items = [item for item in items if isinstance(item, BeePixmapItem)]
            
            if selected_items:
                self.control_target.image_context_menu.clear()
                self.init_image_tag_menu_ui(selected_items[0])  # 传入选中的图片
                self.control_target.image_context_menu.addAction("删除").triggered.connect(
                    lambda: self.control_target.scene.delete_selected())
                self.control_target.image_context_menu.setMinimumWidth(200)
                self.control_target.image_context_menu.exec(self.control_target.mapToGlobal(pos))
            else:
                global_menu = QMenu(self.control_target)
                global_menu.addAction("清空画布").triggered.connect(
                    lambda: self.control_target.scene.clear())
                global_menu.exec(self.control_target.mapToGlobal(pos))
        
        self.control_target.on_context_menu = custom_on_context_menu

    def on_add_tag(self):
        """顶部菜单：新增标签"""
        dialog = TagEditDialog(self.main_window)
        if dialog.exec():
            tag_name, tag_group = dialog.get_result()
            if tag_name and tag_name.strip():
                try:
                    command = AddTagCommand(self.control_target.scene.tag_manager, tag_name.strip(), tag_group)
                    self.control_target.undo_stack.push(command)
                    self.control_target.scene.tag_manager.load_tags()
                    logger.info(f"新增标签成功：{tag_name}")
                    widgets.BeeNotification(self.main_window, f"新增标签「{tag_name}」成功")
                except Exception as e:
                    logger.error(f"新增标签失败：{e}")
                    widgets.BeeNotification(self.main_window, f"新增标签失败：{str(e)}")

    def init_image_tag_menu_ui(self, img_item):
        """图像右键菜单：标签关联核心逻辑（本地缓存版）"""
        tag_submenu = QMenu("标签", self.control_target.image_context_menu)
        tag_submenu.setMinimumWidth(200)
        self.control_target.image_context_menu.addMenu(tag_submenu)

        # 1. 获取标签列表
        try:
            tags = self.control_target.scene.tag_manager.get_all_tags()
            if not tags:
                tag_submenu.addAction("暂无标签").setEnabled(False)
                return
        except Exception as e:
            tag_submenu.addAction("加载标签失败").setEnabled(False)
            logger.error(f"加载标签失败：{e}")
            return

        # 2. 生成图像唯一标识（兜底）
        img_id = str(id(img_item))  # 使用Python内置ID，确保唯一

        # 3. 为每个标签绑定关联/取消逻辑
        for tag in tags:
            # 检查本地缓存中的关联状态
            is_related = img_id in self.tag_cache and tag["tag_id"] in self.tag_cache[img_id]
            action_text = f"{'✅ ' if is_related else '□ '}{tag['tag_name']}"
            action = tag_submenu.addAction(action_text)

            # 绑定点击事件：切换关联状态
            def toggle_tag_relation(tag_id=tag["tag_id"], tag_name=tag["tag_name"], act=action):
                # 初始化图像缓存
                if img_id not in self.tag_cache:
                    self.tag_cache[img_id] = {}

                if tag_id in self.tag_cache[img_id]:
                    # 取消关联
                    del self.tag_cache[img_id][tag_id]
                    act.setText(f"□ {tag_name}")
                    widgets.BeeNotification(self.main_window, f"✅ 取消关联「{tag_name}」")
                    logger.info(f"图像{img_id}取消标签{tag_id}关联")
                else:
                    # 关联标签
                    self.tag_cache[img_id][tag_id] = tag_name
                    act.setText(f"✅ {tag_name}")
                    widgets.BeeNotification(self.main_window, f"✅ 成功关联「{tag_name}」")
                    logger.info(f"图像{img_id}关联标签{tag_id}成功")

            action.triggered.connect(toggle_tag_relation)

    def on_export_by_tag(self):
        """按标签导出图像"""
        try:
            tag_manager = self.control_target.scene.tag_manager
            tags = tag_manager.get_all_tags()
            if not tags:
                widgets.BeeNotification(self.main_window, "暂无标签可导出！")
                return
            
            dialog = TagSelectDialog(self.main_window, tags)
            if not dialog.exec():
                return
            
            selected_tag_id = dialog.get_selected_tag_id()
            if not selected_tag_id:
                return
            
            export_path = QFileDialog.getExistingDirectory(self.main_window, "选择导出路径")
            if not export_path:
                return
            
            # 执行导出（兼容本地缓存）
            success = tag_manager.export_tagged_images(
                tag_id=selected_tag_id,
                export_path=export_path,
                export_params={"format": "PNG", "quality": 90}
            )
            if success:
                widgets.BeeNotification(self.main_window, "✅ 按标签导出成功！")
            else:
                widgets.BeeNotification(self.main_window, "❌ 导出失败：无匹配图像或路径无权限")
        except Exception as e:
            logger.error(f"导出标签失败：{e}", exc_info=True)
            widgets.BeeNotification(self.main_window, f"❌ 导出失败：{str(e)}")