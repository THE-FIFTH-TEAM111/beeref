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

    def on_action_movewin_mode(self): # 移动窗口模式槽函数，用于处理移动窗口模式的切换
        if self.movewin_active: # 如果移动窗口模式已激活
            # Pressing the same shortcut again should end the action
            self.exit_movewin_mode() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
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

    def keyPressEventMainControls(self, event): # 键盘按下事件槽函数，用于处理键盘按下事件
        if self.movewin_active: # 如果移动窗口模式激活
            self.exit_movewin_mode() # 退出移动窗口模式槽函数，用于处理移动窗口模式的切换
            event.accept() # 接受键盘按下事件的建议操作，用于处理键盘按下事件
            return True # 如果移动窗口模式激活，直接返回True，不进行其他操作    
