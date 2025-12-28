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

from PyQt6 import QtCore, QtGui
from PyQt6.QtCore import Qt

from beeref import commands, widgets
from beeref.items import BeePixmapItem
from beeref import fileio


logger = logging.getLogger(__name__) # 主控件日志记录器，用于记录主控件的日志信息


class MainControlsMixin: # 主控件混合类，用于处理主窗口和欢迎叠加层的基本控件
    """Basic controls shared by the main view and the welcome overlay:

    * Right-click menu
    * Dropping files
    * Moving the window without title bar
    """

    def init_main_controls(self, main_window): # 初始化主控件，用于处理主窗口和欢迎叠加层的基本控件
        self.main_window = main_window # 主窗口引用，用于访问主窗口的属性和方法
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu) # 设置上下文菜单策略为自定义上下文菜单，用于处理右键点击事件
        self.customContextMenuRequested.connect( # 自定义上下文菜单请求信号槽函数，用于处理右键点击事件 
            self.control_target.on_context_menu) # 自定义上下文菜单请求信号槽函数，用于处理右键点击事件，调用控制目标的上下文菜单槽函数
        self.setAcceptDrops(True) # 设置接受拖放事件，用于处理文件拖放事件
        self.movewin_active = False  

    def init_main_controls(self, main_window):
        self.main_window = main_window
        self.tag_cache = {}  # 在这里初始化缓存
        #self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        #self.customContextMenuRequested.connect(
        #    self.control_target.on_context_menu)
        self.setAcceptDrops(True)
        self.movewin_active = False
        self.init_tag_menu()

    def on_action_movewin_mode(self):
        if self.movewin_active:
            self.exit_movewin_mode()
        else:
            self.enter_movewin_mode() # 进入移动窗口模式槽函数，用于处理移动窗口模式的切换

    @property # viewport_or_self属性，用于返回视口或自身，用于处理移动窗口模式的切换
    def viewport_or_self(self): # viewport_or_self属性，用于返回视口或自身，用于处理移动窗口模式的切换
        if hasattr(self, 'viewport'): # 如果主控件有视口属性
            return self.viewport() # 返回视口
        return self # 返回自身  

    def enter_movewin_mode(self): # 进入移动窗口模式槽函数，用于处理移动窗口模式的切换
        logger.debug('Entering movewin mode') # 进入移动窗口模式槽函数，用于处理移动窗口模式的切换
        self.setMouseTracking(True) # 设置鼠标跟踪，用于处理移动窗口模式的切换
        self.movewin_active = True # 移动窗口模式已激活
        self.viewport_or_self.setCursor(Qt.CursorShape.SizeAllCursor) # 设置视口或自身的光标为大小调整光标，用于处理移动窗口模式的切换
        self.event_start = QtCore.QPointF(self.cursor().pos()) # 记录鼠标点击位置，用于处理移动窗口模式的切换
        if hasattr(self, 'disable_mouse_events'): # 如果主控件有禁用鼠标事件属性
            self.disable_mouse_events() # 禁用鼠标事件，用于处理移动窗口模式的切换  

    def exit_movewin_mode(self): # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
        logger.debug('Exiting movewin mode') # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
        self.setMouseTracking(False) # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
        self.movewin_active = False # 移动窗口模式未激活
        self.viewport_or_self.unsetCursor() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
        if hasattr(self, 'enable_mouse_events'): # 如果主控件有启用鼠标事件属性
            self.enable_mouse_events() # 启用鼠标事件，用于处理移动窗口模式的切换  

    def dragEnterEvent(self, event): # 拖入事件槽函数，用于处理拖入事件
        mimedata = event.mimeData() # 获取拖入事件的MIME数据，用于处理拖入事件
        logger.debug(f'Drag enter event: {mimedata.formats()}') # 拖入事件槽函数，用于处理拖入事件，记录拖入事件的MIME数据格式
        if mimedata.hasUrls(): # 如果拖入事件的MIME数据包含URL
            event.acceptProposedAction() # 接受拖入事件的建议操作，用于处理拖入事件
        elif mimedata.hasImage(): # 如果拖入事件的MIME数据包含图像
            event.acceptProposedAction() # 接受拖入事件的建议操作，用于处理拖入事件 
        else:
            msg = 'Attempted drop not an image or image too big' # 拖入事件槽函数，用于处理拖入事件，记录拖入事件的MIME数据格式
            logger.info(msg) # 拖入事件槽函数，用于处理拖入事件，记录拖入事件的MIME数据格式
            widgets.BeeNotification(self.control_target, msg) # 拖入事件槽函数，用于处理拖入事件，显示拖入事件的MIME数据格式    

    def dragMoveEvent(self, event): # 拖动移动事件槽函数，用于处理拖动移动事件
        event.acceptProposedAction() # 接受拖动移动事件的建议操作，用于处理拖动移动事件 

    def dropEvent(self, event): # 拖放事件槽函数，用于处理拖放事件
        mimedata = event.mimeData() # 获取拖放事件的MIME数据，用于处理拖放事件
        logger.debug(f'Handling file drop: {mimedata.formats()}') # 拖放事件槽函数，用于处理拖放事件，记录拖放事件的MIME数据格式
        pos = QtCore.QPoint(round(event.position().x()), # 记录拖放事件的位置，用于处理拖放事件 
                            round(event.position().y())) # 记录拖放事件的位置，用于处理拖放事件 
        if mimedata.hasUrls(): # 如果拖放事件的MIME数据包含URL
            logger.debug(f'Found dropped urls: {mimedata.urls()}') # 拖放事件槽函数，用于处理拖放事件，记录拖放事件的URL
            if not self.control_target.scene.items(): # 如果场景中没有项目（即没有插入的图片项）
                # Check if we have a bee file we can open directly
                path = mimedata.urls()[0] # 获取拖放事件的URL，用于处理拖放事件
                if (path.isLocalFile() # 如果拖放事件的URL是本地文件
                        and fileio.is_bee_file(path.toLocalFile())): # 如果拖放事件的URL是本地文件，且是BeeRef文件
                    self.control_target.open_from_file(path.toLocalFile()) # 打开拖放事件的URL，用于处理拖放事件
                    return # 如果拖放事件的URL是本地文件，且是BeeRef文件，直接打开文件，不进行插入图片项操作
            self.control_target.do_insert_images(mimedata.urls(), pos)  # 插入图片项槽函数，用于处理拖放事件，插入拖放事件的URL对应的图片项
        elif mimedata.hasImage(): # 如果拖放事件的MIME数据包含图像
            img = QtGui.QImage(mimedata.imageData()) # 获取拖放事件的图像数据，用于处理拖放事件
            item = BeePixmapItem(img) # 创建图片项，用于处理拖放事件
            pos = self.control_target.mapToScene(pos) # 记录拖放事件的位置，用于处理拖放事件
            self.control_target.undo_stack.push(
                commands.InsertItems(self.control_target.scene, [item], pos)) # 插入图片项槽函数，用于处理拖放事件，插入拖放事件的URL对应的图片项   
        else:
            logger.info('Drop not an image') # 拖放事件槽函数，用于处理拖放事件，记录拖放事件的MIME数据格式

    def mousePressEventMainControls(self, event): # 鼠标按下事件槽函数，用于处理鼠标按下事件
        if self.movewin_active: # 如果移动窗口模式激活
            self.exit_movewin_mode() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
            event.accept() # 接受鼠标按下事件的建议操作，用于处理鼠标按下事件
            return True # 如果移动窗口模式激活，直接返回True，不进行其他操作

        action, inverted =\
            self.control_target.keyboard_settings.mouse_action_for_event(event) # 获取鼠标按下事件对应的操作，用于处理鼠标按下事件
        if action == 'movewindow':
            self.enter_movewin_mode() # 进入移动窗口模式槽函数，用于处理移动窗口模式的切换
            event.accept() # 接受鼠标按下事件的建议操作，用于处理鼠标按下事件
            return True # 如果移动窗口模式激活，直接返回True，不进行其他操作    

    def mouseMoveEventMainControls(self, event): # 鼠标移动事件槽函数，用于处理鼠标移动事件
        if self.movewin_active: # 如果移动窗口模式激活
            pos = self.mapToGlobal(event.position()) # 获取鼠标移动事件的全局位置，用于处理鼠标移动事件
            delta = pos - self.event_start # 计算鼠标移动事件的 delta 向量，用于处理鼠标移动事件
            self.event_start = pos # 更新鼠标移动事件的起始位置，用于处理鼠标移动事件
            self.main_window.move(self.main_window.x() + int(delta.x()), # 移动主窗口槽函数，用于处理移动窗口模式的切换
                                  self.main_window.y() + int(delta.y())) # 移动主窗口槽函数，用于处理移动窗口模式的切换
            event.accept() # 接受鼠标移动事件的建议操作，用于处理鼠标移动事件 
            return True # 如果移动窗口模式激活，直接返回True，不进行其他操作    

    def mouseReleaseEventMainControls(self, event): # 鼠标释放事件槽函数，用于处理鼠标释放事件
        if self.movewin_active: # 如果移动窗口模式激活
            self.exit_movewin_mode() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
            event.accept() # 接受鼠标释放事件的建议操作，用于处理鼠标释放事件
            return True # 如果移动窗口模式激活，直接返回True，不进行其他操作    

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
