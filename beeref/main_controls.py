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
from functools import partial

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

    def on_action_movewin_mode(self): # 移动窗口模式槽函数，用于处理移动窗口模式的切换
        if self.movewin_active: # 如果移动窗口模式已激活
            # Pressing the same shortcut again should end the action
            self.exit_movewin_mode() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
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

    def init_image_tag_menu_ui(self, img_item, menu):
        """图像右键菜单：标签关联核心逻辑（数据库版）"""
        # 先移除之前可能存在的标签子菜单
        for action in menu.actions():
            if action.text() == "标签":
                menu.removeAction(action)
        
        # 添加新的标签子菜单
        tag_submenu = QMenu("标签", menu)
        tag_submenu.setMinimumWidth(200)
        menu.addMenu(tag_submenu)

        # 1. 获取标签列表
        try:
            # 确保tag_manager存在
            if not hasattr(self.scene, 'tag_manager'):
                tag_submenu.addAction("标签管理器未初始化").setEnabled(False)
                return
                
            tags = self.scene.tag_manager.get_all_tags()
            if not tags:
                tag_submenu.addAction("暂无标签").setEnabled(False)
                return
        except Exception as e:
            tag_submenu.addAction("加载标签失败").setEnabled(False)
            logger.error(f"加载标签失败：{e}")
            return

        # 2. 获取图像的save_id（使用BeePixmapItem自带的save_id）
        image_id = str(img_item.save_id) if img_item.save_id else ""

        # 3. 获取图像已关联的标签列表
        try:
            image_tags = self.control_target.scene.tag_manager.get_image_tags(image_id)
            # 转换为标签ID集合，便于快速查找
            image_tag_ids = {tag["tag_id"] for tag in image_tags}
        except Exception as e:
            logger.error(f"获取图像标签失败：{e}")
            image_tag_ids = set()

        # 定义toggle_tag_relation函数
        def toggle_tag_relation(tag_id, tag_name, act):
            if not image_id:
                widgets.BeeNotification(self.main_window, "❌ 图像无有效ID，无法关联标签")
                return

            try:
                if tag_id in image_tag_ids:
                    # 取消关联
                    self.control_target.scene.tag_manager.remove_tag_from_image(img_item, tag_id)
                    image_tag_ids.remove(tag_id)
                    act.setText(f"□ {tag_name}")
                    widgets.BeeNotification(self.main_window, f"✅ 取消关联「{tag_name}」")
                    logger.info(f"图像{image_id}取消标签{tag_id}关联")
                else:
                    # 关联标签
                    self.control_target.scene.tag_manager.add_tags_to_image(img_item, [tag_id])
                    image_tag_ids.add(tag_id)
                    act.setText(f"✅ {tag_name}")
                    widgets.BeeNotification(self.main_window, f"✅ 成功关联「{tag_name}」")
                    logger.info(f"图像{image_id}关联标签{tag_id}成功")
            except Exception as e:
                logger.error(f"切换标签关联失败：{e}")
                widgets.BeeNotification(self.main_window, f"❌ 操作失败：{str(e)}")

        # 4. 为每个标签绑定关联/取消逻辑
        for tag in tags:
            is_related = tag["tag_id"] in image_tag_ids
            action_text = f"{'✅ ' if is_related else '□ '}{tag['tag_name']}"
            action = tag_submenu.addAction(action_text)

            # 使用functools.partial绑定参数
            action.triggered.connect(partial(toggle_tag_relation, tag["tag_id"], tag["tag_name"], action))

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
