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

from functools import partial
import logging
import os
import os.path

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt

from beeref.actions import ActionsMixin, actions
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

# 主视图类，继承自QGraphicsView并混入自定义功能
# 负责处理用户界面交互、图形渲染和场景管理
class BeeGraphicsView(MainControlsMixin,
                      QtWidgets.QGraphicsView,
                      ActionsMixin):
 
    # 视图模式常量
    PAN_MODE = 1  # 平移模式
    ZOOM_MODE = 2   # 缩放模式 
    SAMPLE_COLOR_MODE = 3  # 取色模式

    def __init__(self, app, parent=None):
      
        super().__init__(parent)# 初始化父类
        self.app = app# 应用程序对象
        self.parent = parent # 父窗口部件
        self.settings = BeeSettings()   # 应用程序设置
        self.keyboard_settings = KeyboardSettings() # 键盘设置
        self.welcome_overlay = widgets.welcome_overlay.WelcomeOverlay(self) # 欢迎 overlay 层

        self.setBackgroundBrush(
            QtGui.QBrush(QtGui.QColor(*constants.COLORS['Scene:Canvas']))) # 设置场景背景为画布颜色
        self.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)  # 开启反锯齿渲染
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame) # 移除边框
          
        self.undo_stack = QtGui.QUndoStack(self) # 初始化撤销栈
        self.undo_stack.setUndoLimit(100) # 设置撤销栈最大操作数为 100
        self.undo_stack.canRedoChanged.connect(self.on_can_redo_changed) 
        # 连接撤销栈的 canRedoChanged 信号到 on_can_redo_changed 槽函数
        self.undo_stack.canUndoChanged.connect(self.on_can_undo_changed)
        # 连接撤销栈的 canUndoChanged 信号到 on_can_undo_changed 槽函数
        self.undo_stack.cleanChanged.connect(self.on_undo_clean_changed)
        # 连接撤销栈的 cleanChanged 信号到 on_undo_clean_changed 槽函数

        self.filename = None# 当前打开的文件名
        self.previous_transform = None # 上一次的变换矩阵
        self.active_mode = None # 当前激活的模式

        self.scene = BeeGraphicsScene(self.undo_stack) # 初始化场景
        self.scene.changed.connect(self.on_scene_changed) 
        # 连接场景的 changed 信号到 on_scene_changed 槽函数
        self.scene.selectionChanged.connect(self.on_selection_changed) 
        # 连接场景的 selectionChanged 信号到 on_selection_changed 槽函数
        self.scene.cursor_changed.connect(self.on_cursor_changed) 
        # 连接场景的 cursor_changed 信号到 on_cursor_changed 槽函数
        self.scene.cursor_cleared.connect(self.on_cursor_cleared) 
        # 连接场景的 cursor_cleared 信号到 on_cursor_cleared 槽函数
        self.setScene(self.scene) # 设置场景    

        # Context menu and actions
        self.build_menu_and_actions() # 构建菜单和操作 
        self.control_target = self # 设置控制目标为自身
        self.init_main_controls(main_window=parent)# 初始化主控件

        # Load files given via command line
        if commandline_args.filenames: # 如果命令行参数有文件名
            fn = commandline_args.filenames[0] # 获取第一个文件名
            if os.path.splitext(fn)[1] == '.bee': # 如果文件扩展名是 .bee
                self.open_from_file(fn) # 从文件打开
            else:
                self.do_insert_images(commandline_args.filenames) # 否则插入图像

        self.update_window_title() # 更新窗口标题

    @property # 文件名属性
    def filename(self): # 获取当前打开的文件名
        return self._filename # 返回当前打开的文件名

    @filename.setter # 文件名属性设置器
    def filename(self, value): # 设置当前打开的文件名
        self._filename = value # 设置当前打开的文件名
        self.update_window_title() # 更新窗口标题
        if value:
            self.settings.update_recent_files(value) # 更新最近打开的文件列表
            self.update_menu_and_actions() # 更新菜单和操作

    def cancel_active_modes(self): # 取消所有激活的模式
        self.scene.cancel_active_modes() # 取消场景中所有激活的模式
        self.cancel_sample_color_mode() # 取消取色模式
        self.active_mode = None # 重置当前激活的模式为 None

    def cancel_sample_color_mode(self): # 取消取色模式
        logger.debug('Cancel sample color mode') # 调试日志：取消取色模式
        self.active_mode = None # 重置当前激活的模式为 None
        self.viewport().unsetCursor() # 取消设置视口光标
        if hasattr(self, 'sample_color_widget'):
            self.sample_color_widget.hide() # 隐藏取色小部件
            del self.sample_color_widget # 删除取色小部件
        if self.scene.has_multi_selection():
            self.scene.multi_select_item.bring_to_front()# 将多选项 bring to front

    def update_window_title(self): # 更新窗口标题
        clean = self.undo_stack.isClean() # 获取撤销栈是否为干净状态
        if clean and not self.filename: # 如果撤销栈为干净状态且没有文件名
            title = constants.APPNAME # 窗口标题为应用程序名称
        else:
            name = os.path.basename(self.filename or '[Untitled]') # 获取文件名（如果有），否则为 '[Untitled]'
            clean = '' if clean else '*' # 如果撤销栈为干净状态，则不显示 '*'，否则显示 '*'
            title = f'{name}{clean} - {constants.APPNAME}' 
            # 窗口标题为文件名（如果有），否则为 '[Untitled]'，后跟 '*'（如果撤销栈为不干净状态），最后为应用程序名称
        self.parent.setWindowTitle(title) # 设置父窗口标题为更新后的标题

    def on_scene_changed(self, region): # 场景变化槽函数
        if not self.scene.items(): # 如果场景中没有物品
            logger.debug('No items in scene') # 调试日志：场景中没有物品
            self.setTransform(QtGui.QTransform()) # 重置变换矩阵为单位矩阵
            self.welcome_overlay.setFocus() # 设置欢迎叠加层为焦点
            self.clearFocus() # 清除当前焦点
            self.welcome_overlay.show() # 显示欢迎叠加层
            self.actiongroup_set_enabled('active_when_items_in_scene', False) # 禁用场景中物品相关操作
        else:
            self.setFocus(QtCore.Qt.PopupFocusReason) # 设置场景为焦点，使用 PopupFocusReason 原因
            self.welcome_overlay.clearFocus()# 清除欢迎叠加层焦点
            self.welcome_overlay.hide() # 隐藏欢迎叠加层
            self.actiongroup_set_enabled('active_when_items_in_scene', True) # 启用场景中物品相关操作
        self.recalc_scene_rect() # 重新计算场景矩形

    def on_can_redo_changed(self, can_redo): # 可以重做变化槽函数
        self.actiongroup_set_enabled('active_when_can_redo', can_redo) # 根据 can_redo 启用或禁用 'active_when_can_redo' 操作组

    def on_can_undo_changed(self, can_undo): # 可以撤销变化槽函数
        self.actiongroup_set_enabled('active_when_can_undo', can_undo) # 根据 can_undo 启用或禁用 'active_when_can_undo' 操作组

    def on_undo_clean_changed(self, clean): # 撤销栈干净状态变化槽函数
        self.update_window_title() # 更新窗口标题

    def on_context_menu(self, point): # 上下文菜单槽函数
        self.context_menu.exec(self.mapToGlobal(point)) # 在全局坐标中执行上下文菜单

    def get_supported_image_formats(self, cls): # 获取支持的图像格式
        formats = []

        for f in cls.supportedImageFormats(): # 遍历支持的图像格式
            string = f'*.{f.data().decode()}' # 转换为字符串格式
            formats.extend((string, string.upper())) # 扩展格式列表，包含小写和大写格式
        return ' '.join(formats) # 返回空格分隔的格式字符串 

    def get_view_center(self): # 获取视图中心坐标
        return QtCore.QPoint(round(self.size().width() / 2),
                             round(self.size().height() / 2)) # 返回视图中心坐标

    def clear_scene(self): # 清除场景
        logging.debug('Clearing scene...') # 调试日志：清除场景
        self.cancel_active_modes() # 取消所有激活的模式
        self.scene.clear() # 清除场景中的所有物品
        self.undo_stack.clear() # 清除撤销栈 
        self.filename = None # 重置文件名为 None
        self.setTransform(QtGui.QTransform()) # 重置变换矩阵为单位矩阵

    def reset_previous_transform(self, toggle_item=None): # 重置之前的变换
        if (self.previous_transform # 如果有之前的变换
                and self.previous_transform['toggle_item'] != toggle_item): # 如果之前的变换与当前物品不同
            self.previous_transform = None # 重置之前的变换为 None  
        # 如果之前的变换与当前物品不同，将之前的变换重置为 None 

    def fit_rect(self, rect, toggle_item=None): # 适合矩形
        if toggle_item and self.previous_transform: # 如果有之前的变换且与当前物品不同
            logger.debug('Fit view: Reset to previous') # 调试日志：重置到之前的变换
            self.setTransform(self.previous_transform['transform']) # 设置变换矩阵为之前的变换矩阵
            self.centerOn(self.previous_transform['center']) # 中心视图到之前的变换中心
            self.previous_transform = None # 重置之前的变换为 None  
            return
        if toggle_item: # 如果有物品
            self.previous_transform = { # 存储当前变换
                'toggle_item': toggle_item, # 存储当前物品
                'transform': QtGui.QTransform(self.transform()), # 存储当前变换矩阵
                'center': self.mapToScene(self.get_view_center()), # 存储当前视图中心坐标
            }
        else:
            self.previous_transform = None # 重置之前的变换为 None  

        logger.debug(f'Fit view: {rect}') # 调试日志：适合矩形
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio) # 适合矩形，保持纵横比
        self.recalc_scene_rect() # 重新计算场景矩形
        # It seems to be more reliable when we fit a second time
        # Sometimes a changing scene rect can mess up the fitting
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio) # 适合矩形，保持纵横比
        self.recalc_scene_rect() # 重新计算场景矩形
        logger.trace('Fit view done')

    def get_confirmation_unsaved_changes(self, msg): # 获取未保存更改确认
        confirm = self.settings.valueOrDefault('Save/confirm_close_unsaved')# 获取是否确认关闭未保存更改
        if confirm and not self.undo_stack.isClean(): # 如果确认关闭未保存更改且撤销栈不为干净状态
            answer = QtWidgets.QMessageBox.question( # 获取未保存更改确认
                self,
                'Discard unsaved changes?', # 确认关闭未保存更改标题
                msg,
                QtWidgets.QMessageBox.StandardButton.Yes | 
                QtWidgets.QMessageBox.StandardButton.Cancel) 
            return answer == QtWidgets.QMessageBox.StandardButton.Yes

        return True

    def on_action_new_scene(self): # 新建场景槽函数
        confirm = self.get_confirmation_unsaved_changes( # 获取新建场景确认
            'There are unsaved changes. ' # 确认关闭未保存更改消息
            'Are you sure you want to open a new scene?') # 确认新建场景消息
        if confirm: # 如果确认新建场景
            self.clear_scene() # 清除场景

    def on_action_fit_scene(self): # 适合场景槽函数
        self.fit_rect(self.scene.itemsBoundingRect()) # 适合场景矩形

    def on_action_fit_selection(self): # 适合选择槽函数
        self.fit_rect(self.scene.itemsBoundingRect(selection_only=True)) # 适合选择矩形 

    def on_action_fullscreen(self, checked): # 全屏槽函数
        if checked: # 如果选中全屏
            self.parent.showFullScreen() # 显示全屏
        else:
            self.parent.showNormal() # 显示正常 

    def on_action_always_on_top(self, checked): # 总是置顶槽函数
        self.parent.setWindowFlag( # 设置窗口标志
            Qt.WindowType.WindowStaysOnTopHint, on=checked) # 设置窗口置顶标志
        self.parent.destroy() # 销毁窗口
        self.parent.create() # 创建窗口
        self.parent.show() # 显示窗口

    def on_action_show_scrollbars(self, checked): # 显示滚动条槽函数
        if checked: # 如果选中显示滚动条
            self.setHorizontalScrollBarPolicy( # 设置水平滚动条策略
                Qt.ScrollBarPolicy.ScrollBarAsNeeded) # 设置水平滚动条为按需显示
            self.setVerticalScrollBarPolicy( # 设置垂直滚动条策略
                Qt.ScrollBarPolicy.ScrollBarAsNeeded) # 设置垂直滚动条为按需显示
        else: # 如果未选中显示滚动条
            self.setHorizontalScrollBarPolicy( # 设置水平滚动条策略
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 设置水平滚动条为始终关闭
            self.setVerticalScrollBarPolicy( # 设置垂直滚动条策略
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff) # 设置垂直滚动条为始终关闭

    def on_action_show_menubar(self, checked): # 显示菜单条槽函数
        if checked: # 如果选中显示菜单条
            self.parent.setMenuBar(self.create_menubar()) # 设置菜单条为创建的菜单条
        else: # 如果未选中显示菜单条
            self.parent.setMenuBar(None) # 设置菜单条为 None

    def on_action_show_titlebar(self, checked): # 显示标题栏槽函数
        self.parent.setWindowFlag( # 设置窗口标志
            Qt.WindowType.FramelessWindowHint, on=not checked) # 设置窗口无框架标志
        self.parent.destroy() # 销毁窗口
        self.parent.create() # 创建窗口
        self.parent.show() # 显示窗口   

    def on_action_move_window(self): # 移动窗口槽函数
        if self.welcome_overlay.isHidden(): # 如果欢迎覆盖层隐藏
            self.on_action_movewin_mode() # 执行移动窗口模式
        else: # 如果欢迎覆盖层显示
            self.welcome_overlay.on_action_movewin_mode() # 执行欢迎覆盖层移动窗口模式  

    def on_action_undo(self): # 撤销槽函数
        logger.debug('Undo: %s' % self.undo_stack.undoText()) # 调试输出撤销文本
        self.cancel_active_modes()
        self.undo_stack.undo()

    def on_action_redo(self): # 重做槽函数
        logger.debug('Redo: %s' % self.undo_stack.redoText()) # 调试输出重做文本
        self.cancel_active_modes()
        self.undo_stack.redo()

    def on_action_select_all(self): # 选择所有槽函数
        self.scene.select_all_items() # 选择所有项

    def on_action_deselect_all(self): # 取消选择所有槽函数
        self.scene.deselect_all_items() # 取消选择所有项

    def on_action_delete_items(self): # 删除项槽函数
        logger.debug('Deleting items...') # 调试输出删除项消息
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push( # 推送撤销栈
            commands.DeleteItems( # 删除项命令
                self.scene, self.scene.selectedItems(user_only=True))) # 删除用户选择的项

    def on_action_cut(self): # 剪切槽函数
        logger.debug('Cutting items...') # 调试输出剪切项消息
        self.on_action_copy() # 执行复制操作
        self.undo_stack.push( # 推送撤销栈
            commands.DeleteItems( # 删除项命令
                self.scene, self.scene.selectedItems(user_only=True))) # 删除用户选择的项

    def on_action_raise_to_top(self): #  Bring to Front槽函数
        self.scene.raise_to_top() #  Bring to Front项

    def on_action_lower_to_bottom(self): #  Send to Back槽函数
        self.scene.lower_to_bottom() #  Send to Back项

    def on_action_normalize_height(self): # 归一化高度槽函数
        self.scene.normalize_height() # 归一化高度

    def on_action_normalize_width(self): # 归一化宽度槽函数
        self.scene.normalize_width() # 归一化宽度

    def on_action_normalize_size(self): # 归一化大小槽函数
        self.scene.normalize_size() # 归一化大小    

    def on_action_arrange_horizontal(self): # 水平排列槽函数
        self.scene.arrange() # 水平排列项

    def on_action_arrange_vertical(self): # 垂直排列槽函数
        self.scene.arrange(vertical=True) # 垂直排列项

    def on_action_arrange_optimal(self): # 最优排列槽函数
        self.scene.arrange_optimal() # 最优排列项

    def on_action_arrange_square(self): # 方排列槽函数
        self.scene.arrange_square() # 方排列项

    def on_action_change_opacity(self): # 改变不透明度槽函数        
        images = list(filter( # 过滤出用户选择的图像项
            lambda item: item.is_image, # 过滤出图像项
            self.scene.selectedItems(user_only=True))) # 过滤出用户选择的图像项
        widgets.ChangeOpacityDialog(self, images, self.undo_stack) # 显示改变不透明度对话框 

    def on_action_grayscale(self, checked): # 灰度槽函数
        images = list(filter( # 过滤出用户选择的图像项
            lambda item: item.is_image, # 过滤出图像项
            self.scene.selectedItems(user_only=True))) # 过滤出用户选择的图像项
        if images:
            self.undo_stack.push(
                commands.ToggleGrayscale(images, checked)) # 推送撤销栈，执行切换灰度命令

    def on_action_crop(self): # 裁剪槽函数
        self.scene.crop_items() # 裁剪项        

    def on_action_flip_horizontally(self): # 水平翻转槽函数
        self.scene.flip_items(vertical=False) # 水平翻转项  

    def on_action_flip_vertically(self): # 垂直翻转槽函数
        self.scene.flip_items(vertical=True) # 垂直翻转项  

    def on_action_reset_scale(self): # 重置缩放槽函数
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push(commands.ResetScale( # 推送撤销栈，执行重置缩放命令   
            self.scene.selectedItems(user_only=True))) # 推送撤销栈，执行重置缩放命令   
    def on_action_reset_rotation(self): # 重置旋转槽函数
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push(commands.ResetRotation( # 推送撤销栈，执行重置旋转命令   
            self.scene.selectedItems(user_only=True))) # 推送撤销栈，执行重置旋转命令   

    def on_action_reset_flip(self): # 重置翻转槽函数
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push(commands.ResetFlip( # 推送撤销栈，执行重置翻转命令   
            self.scene.selectedItems(user_only=True))) # 推送撤销栈，执行重置翻转命令   
    def on_action_reset_crop(self): # 重置裁剪槽函数
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push(commands.ResetCrop( # 推送撤销栈，执行重置裁剪命令   
            self.scene.selectedItems(user_only=True))) # 推送撤销栈，执行重置裁剪命令   

    def on_action_reset_transforms(self):
        self.cancel_active_modes() # 取消活动模式
        self.undo_stack.push(commands.ResetTransforms( # 推送撤销栈，执行重置变换命令   
            self.scene.selectedItems(user_only=True))) # 推送撤销栈，执行重置变换命令       

    def on_action_show_color_gamut(self): # 显示颜色 gamut 槽函数
        widgets.color_gamut.GamutDialog(self, self.scene.selectedItems()[0]) # 显示颜色 gamut 对话框    

    def on_action_sample_color(self): # 采样颜色槽函数
        self.cancel_active_modes() # 取消活动模式
        logger.debug('Entering sample color mode') # 调试输出采样颜色消息
        self.viewport().setCursor(Qt.CursorShape.CrossCursor) # 设置鼠标光标为十字光标
        self.active_mode = self.SAMPLE_COLOR_MODE # 设置活动模式为采样颜色模式  

        if self.scene.has_multi_selection(): # 如果有多个选择项
            # We don't want to sample the multi select item, so
            # temporarily send it to the back:
            self.scene.multi_select_item.lower_behind_selection() # 临时将多选项发送到后台

        pos = self.mapFromGlobal(self.cursor().pos()) # 获取鼠标光标在场景中的位置
        self.sample_color_widget = widgets.SampleColorWidget(
            self,
            pos,
            self.scene.sample_color_at(self.mapToScene(pos))) # 创建采样颜色小部件  

    def on_items_loaded(self, value): # 加载项槽函数
        logger.debug('On items loaded: add queued items') # 调试输出加载项消息
        self.scene.add_queued_items() # 添加队列中的项

    def on_loading_finished(self, filename, errors): # 加载完成槽函数
        if errors: # 如果有错误
            QtWidgets.QMessageBox.warning( # 显示警告对话框
                self,
                'Problem loading file',
                ('<p>Problem loading file %s</p>'
                 '<p>Not accessible or not a proper bee file</p>') % filename) # 显示警告对话框，提示文件不可访问或不是 proper bee 文件
        else:
            self.filename = filename # 设置文件名
            self.scene.add_queued_items() # 添加队列中的项
            self.on_action_fit_scene() # 拟合场景   

    def on_action_open_recent_file(self, filename):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
        if confirm:
            self.open_from_file(filename)

    def open_from_file(self, filename):
        logger.info(f'Opening file {filename}')
        self.clear_scene()
        self.worker = fileio.ThreadedIO(
            fileio.load_bee, filename, self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(self.on_loading_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Loading {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_open(self):
        confirm = self.get_confirmation_unsaved_changes(
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
        if not confirm:
            return

        self.cancel_active_modes()
        filename, f = QtWidgets.QFileDialog.getOpenFileName(
            parent=self,
            caption='Open file',
            filter=f'{constants.APPNAME} File (*.bee)')
        if filename:
            filename = os.path.normpath(filename)
            self.open_from_file(filename)
            self.filename = filename

    def on_saving_finished(self, filename, errors):
        if errors:
            QtWidgets.QMessageBox.warning(
                self,
                'Problem saving file',
                ('<p>Problem saving file %s</p>'
                 '<p>File/directory not accessible</p>') % filename)
        else:
            self.filename = filename
            self.undo_stack.setClean()

    def do_save(self, filename, create_new):
        if not fileio.is_bee_file(filename):
            filename = f'{filename}.bee'
        self.worker = fileio.ThreadedIO(
            fileio.save_bee, filename, self.scene, create_new=create_new)
        self.worker.finished.connect(self.on_saving_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Saving {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_save_as(self):
        self.cancel_active_modes()
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, f = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption='Save file',
            directory=directory,
            filter=f'{constants.APPNAME} File (*.bee)')
        if filename:
            self.do_save(filename, create_new=True)

    def on_action_save(self):
        self.cancel_active_modes()
        if not self.filename:
            self.on_action_save_as()
        else:
            self.do_save(self.filename, create_new=False)

    def on_action_export_scene(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        filename, formatstr = QtWidgets.QFileDialog.getSaveFileName(
            parent=self,
            caption='Export Scene to Image',
            directory=directory,
            filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg)',
                              'PNG (*.png)',
                              'JPEG (*.jpg *.jpeg)',
                              'SVG (*.svg)')))

        if not filename:
            return

        name, ext = os.path.splitext(filename)
        if not ext:
            ext = get_file_extension_from_format(formatstr)
            filename = f'{filename}.{ext}'
        logger.debug(f'Got export filename {filename}')

        exporter_cls = exporter_registry[ext]
        exporter = exporter_cls(self.scene)
        if not exporter.get_user_input(self):
            return

        self.worker = fileio.ThreadedIO(exporter.export, filename)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Exporting {filename}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_finished(self, filename, errors):
        if errors:
            err_msg = '</br>'.join(str(errors))
            QtWidgets.QMessageBox.warning(
                self,
                'Problem writing file',
                f'<p>Problem writing file {filename}</p><p>{err_msg}</p>')

    def on_action_export_images(self):
        directory = os.path.dirname(self.filename) if self.filename else None
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent=self,
            caption='Export Images',
            directory=directory)

        if not directory:
            return

        logger.debug(f'Got export directory {directory}')
        self.exporter = ImagesToDirectoryExporter(self.scene, directory)
        self.worker = fileio.ThreadedIO(self.exporter.export)
        self.worker.user_input_required.connect(
            self.on_export_images_file_exists)
        self.worker.finished.connect(self.on_export_finished)
        self.progress = widgets.BeeProgressDialog(
            f'Exporting to {directory}',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_export_images_file_exists(self, filename):
        dlg = widgets.ExportImagesFileExistsDialog(self, filename)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.exporter.handle_existing = dlg.get_answer()
            directory = self.exporter.dirname
            self.progress = widgets.BeeProgressDialog(
                f'Exporting to {directory}',
                worker=self.worker,
                parent=self)
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
        QtWidgets.QMessageBox.about(
            self,
            f'About {constants.APPNAME}',
            (f'<h2>{constants.APPNAME} {constants.VERSION}</h2>'
             f'<p>{constants.APPNAME_FULL}</p>'
             f'<p>{constants.COPYRIGHT}</p>'
             f'<p><a href="{constants.WEBSITE}">'
             f'Visit the {constants.APPNAME} website</a></p>'))

    def on_action_debuglog(self):
        widgets.DebugLogDialog(self)

    def on_insert_images_finished(self, new_scene, filename, errors):
        """Callback for when loading of images is finished.

        :param new_scene: True if the scene was empty before, else False
        :param filename: Not used, for compatibility only
        :param errors: List of filenames that couldn't be loaded
        """

        logger.debug('Insert images finished')
        if errors:
            errornames = [
                f'<li>{fn}</li>' for fn in errors]
            errornames = '<ul>%s</ul>' % '\n'.join(errornames)
            num = len(errors)
            msg = f'{num} image(s) could not be opened.<br/>'
            QtWidgets.QMessageBox.warning(
                self,
                'Problem loading images',
                msg + IMG_LOADING_ERROR_MSG + errornames)
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
            fileio.load_images,
            filenames,
            self.mapToScene(pos),
            self.scene)
        self.worker.progress.connect(self.on_items_loaded)
        self.worker.finished.connect(
            partial(self.on_insert_images_finished,
                    not self.scene.items()))
        self.progress = widgets.BeeProgressDialog(
            'Loading images',
            worker=self.worker,
            parent=self)
        self.worker.start()

    def on_action_insert_images(self):
        self.cancel_active_modes()
        formats = self.get_supported_image_formats(QtGui.QImageReader)
        logger.debug(f'Supported image types for reading: {formats}')
        filenames, f = QtWidgets.QFileDialog.getOpenFileNames(
            parent=self,
            caption='Select one or more images to open',
            filter=f'Images ({formats})')
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
        clipboard = QtWidgets.QApplication.clipboard()
        items = self.scene.selectedItems(user_only=True)

        # At the moment, we can only copy one image to the global
        # clipboard. (Later, we might create an image of the whole
        # selection for external copying.)
        items[0].copy_to_clipboard(clipboard)

        # However, we can copy all items to the internal clipboard:
        self.scene.copy_selection_to_internal_clipboard()

        # We set a marker for ourselves in the global clipboard so
        # that we know to look up the internal clipboard when pasting:
        clipboard.mimeData().setData(
            'beeref/items', QtCore.QByteArray.number(len(items)))

    def on_action_paste(self):
        self.cancel_active_modes()
        logger.debug('Pasting from clipboard...')
        clipboard = QtWidgets.QApplication.clipboard()
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))

        # See if we need to look up the internal clipboard:
        data = clipboard.mimeData().data('beeref/items')
        logger.debug(f'Custom data in clipboard: {data}')
        if data and self.scene.internal_clipboard:
            # Checking that internal clipboard exists since the user
            # may have opened a new scene since copying.
            self.scene.paste_from_internal_clipboard(pos)
            return

        img = clipboard.image()
        if not img.isNull():
            item = BeePixmapItem(img)
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos))
            if len(self.scene.items()) == 1:
                # This is the first image in the scene
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
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(dirname))

    def on_selection_changed(self):
        logger.debug('Currently selected items: %s',
                     len(self.scene.selectedItems(user_only=True)))
        self.actiongroup_set_enabled('active_when_selection',
                                     self.scene.has_selection())
        self.actiongroup_set_enabled('active_when_single_image',
                                     self.scene.has_single_image_selection())

        if self.scene.has_selection():
            item = self.scene.selectedItems(user_only=True)[0]
            grayscale = getattr(item, 'grayscale', False)
            actions.actions['grayscale'].qaction.setChecked(grayscale)
        self.viewport().repaint()

    def on_cursor_changed(self, cursor):
        if self.active_mode is None:
            self.viewport().setCursor(cursor)

    def on_cursor_cleared(self):
        if self.active_mode is None:
            self.viewport().unsetCursor()

    def recalc_scene_rect(self):
        """Resize the scene rectangle so that it is always one view width
        wider than all items' bounding box at each side and one view
        width higher on top and bottom. This gives the impression of
        an infinite canvas."""

        if self.previous_transform:
            return
        logger.trace('Recalculating scene rectangle...')
        try:
            topleft = self.mapFromScene(
                self.scene.itemsBoundingRect().topLeft())
            topleft = self.mapToScene(QtCore.QPoint(
                topleft.x() - self.size().width(),
                topleft.y() - self.size().height()))
            bottomright = self.mapFromScene(
                self.scene.itemsBoundingRect().bottomRight())
            bottomright = self.mapToScene(QtCore.QPoint(
                bottomright.x() + self.size().width(),
                bottomright.y() + self.size().height()))
            self.setSceneRect(QtCore.QRectF(topleft, bottomright))
        except OverflowError:
            logger.info('Maximum scene size reached')
        logger.trace('Done recalculating scene rectangle')

    def get_zoom_size(self, func):
        """Calculates the size of all items' bounding box in the view's
        coordinates.

        This helps ensure that we never zoom out too much (scene
        becomes so tiny that items become invisible) or zoom in too
        much (causing overflow errors).

        :param func: Function which takes the width and height as
            arguments and turns it into a number, for ex. ``min`` or ``max``.
        """

        topleft = self.mapFromScene(
            self.scene.itemsBoundingRect().topLeft())
        bottomright = self.mapFromScene(
            self.scene.itemsBoundingRect().bottomRight())
        return func(bottomright.x() - topleft.x(),
                    bottomright.y() - topleft.y())

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

        # We calculate where the anchor is before and after the zoom
        # and then move the view accordingly to keep the anchor fixed
        # We can't use QGraphicsView's AnchorUnderMouse since it
        # uses the current cursor position while we need the initial mouse
        # press position for zooming with Ctrl + Middle Drag
        anchor = QtCore.QPoint(round(anchor.x()),
                               round(anchor.y()))
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
        action, inverted\
            = self.keyboard_settings.mousewheel_action_for_event(event)

        delta = event.angleDelta().y()
        if inverted:
            delta = delta * -1

        if action == 'zoom':
            self.zoom(delta, event.position())
            event.accept()
            return
        if action == 'pan_horizontal':
            self.pan(QtCore.QPointF(0, 0.5 * delta))
            event.accept()
            return
        if action == 'pan_vertical':
            self.pan(QtCore.QPointF(0.5 * delta, 0))
            event.accept()
            return

    def mousePressEvent(self, event):
        if self.mousePressEventMainControls(event):
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            if (event.button() == Qt.MouseButton.LeftButton):
                color = self.scene.sample_color_at(
                    self.mapToScene(event.pos()))
                if color:
                    name = qcolor_to_hex(color)
                    clipboard = QtWidgets.QApplication.clipboard()
                    clipboard.setText(name)
                    self.scene.internal_clipboard = []
                    msg = f'Copied color to clipboard: {name}'
                    logger.debug(msg)
                    widgets.BeeNotification(self, msg)
                else:
                    logger.debug('No color found')
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
            # ClosedHandCursor and OpenHandCursor don't work, but I
            # don't know if that's only on my system or a general
            # problem. It works with other cursors.
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.PAN_MODE:
            self.reset_previous_transform()
            pos = event.position()
            self.pan(self.event_start - pos)
            self.event_start = pos
            event.accept()
            return

        if self.active_mode == self.ZOOM_MODE:
            self.reset_previous_transform()
            pos = event.position()
            delta = (self.event_start - pos).y()
            if self.event_inverted:
                delta *= -1
            self.event_start = pos
            self.zoom(delta * 20, self.event_anchor)
            event.accept()
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE:
            self.sample_color_widget.update(
                event.position(),
                self.scene.sample_color_at(self.mapToScene(event.pos())))
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
