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

    def on_action_open_recent_file(self, filename):# 打开最近文件槽函数
        confirm = self.get_confirmation_unsaved_changes( # 获取确认未保存更改消息
            'There are unsaved changes. '
            'Are you sure you want to open a new scene?')
        if confirm: # 如果确认
            self.open_from_file(filename) # 从文件打开场景  

    def open_from_file(self, filename): # 从文件打开场景槽函数
        logger.info(f'Opening file {filename}') # 调试输出打开文件消息
        self.clear_scene() # 清除场景   
        self.worker = fileio.ThreadedIO( # 创建线程化 IO 工作器 
            fileio.load_bee, filename, self.scene) # 加载 bee 文件，将项添加到场景中
        self.worker.progress.connect(self.on_items_loaded) # 连接进度信号到加载项槽函数
        self.worker.finished.connect(self.on_loading_finished) # 连接完成信号到加载完成槽函数   
        self.progress = widgets.BeeProgressDialog( # 创建进度对话框
            f'Loading {filename}', # 进度对话框标题
            worker=self.worker, # 关联线程化 IO 工作器
            parent=self)  # 设置进度对话框父窗口为主窗口
        self.worker.start() # 启动线程化 IO 工作器，开始加载文件    

    def on_action_open(self): # 打开文件槽函数
        confirm = self.get_confirmation_unsaved_changes( # 获取确认未保存更改消息   
            'There are unsaved changes. ' # 提示有未保存更改
            'Are you sure you want to open a new scene?') # 提示确认打开新场景  
        if not confirm: # 如果取消
            return # 如果取消，返回

        self.cancel_active_modes() # 取消活动模式
        filename, f = QtWidgets.QFileDialog.getOpenFileName( # 获取打开文件对话框
            parent=self, # 设置进度对话框父窗口为主窗口
            caption='Open file', # 打开文件对话框标题 
            filter=f'{constants.APPNAME} File (*.bee)') # 打开文件对话框筛选器，仅显示 bee 文件
        if filename: # 如果选择了文件
            filename = os.path.normpath(filename) # 规范文件名路径
            self.open_from_file(filename) # 从文件打开场景
            self.filename = filename # 设置文件名

    def on_saving_finished(self, filename, errors): # 保存完成槽函数
        if errors: # 如果有错误
            QtWidgets.QMessageBox.warning( # 显示警告对话框
                self, # 警告对话框父窗口为主窗口
                'Problem saving file', # 警告对话框标题 
                ('<p>Problem saving file %s</p>' # 警告对话框内容，提示保存文件时出现问题
                 '<p>File/directory not accessible</p>') % filename) # 警告对话框内容，提示文件或目录不可访问
        else:
            self.filename = filename # 设置文件名
            self.undo_stack.setClean() # 设置撤销栈为干净状态   

    def do_save(self, filename, create_new): # 保存场景槽函数
        if not fileio.is_bee_file(filename): # 如果不是 bee 文件
            filename = f'{filename}.bee' # 添加 bee 文件扩展名  
        self.worker = fileio.ThreadedIO( # 创建线程化 IO 工作器
            fileio.save_bee, filename, self.scene, create_new=create_new) # 保存 bee 文件，将场景项保存到文件中
        self.worker.finished.connect(self.on_saving_finished) # 连接完成信号到保存完成槽函数
        self.progress = widgets.BeeProgressDialog( # 创建进度对话框
            f'Saving {filename}', # 进度对话框标题
            worker=self.worker, # 关联线程化 IO 工作器
            parent=self) # 设置进度对话框父窗口为主窗口
        self.worker.start() # 启动线程化 IO 工作器，开始保存文件    

    def on_action_save_as(self): # 保存为槽函数
        self.cancel_active_modes() # 取消活动模式
        directory = os.path.dirname(self.filename) if self.filename else None # 如果有文件名，获取文件名所在目录，否则为 None
        filename, f = QtWidgets.QFileDialog.getSaveFileName( # 获取保存文件对话框
            parent=self, # 设置进度对话框父窗口为主窗口
            caption='Save file', # 保存文件对话框标题
            directory=directory, # 保存文件对话框默认目录为当前文件名所在目录
            filter=f'{constants.APPNAME} File (*.bee)') # 保存文件对话框筛选器，仅显示 bee 文件
        if filename: # 如果选择了文件   
            self.do_save(filename, create_new=True) # 保存场景为新文件

    def on_action_save(self): # 保存槽函数
        self.cancel_active_modes() # 取消活动模式
        if not self.filename: # 如果没有文件名
            self.on_action_save_as() # 调用保存为槽函数
        else:
            self.do_save(self.filename, create_new=False) # 保存场景到当前文件名，不创建新文件

    def on_action_export_scene(self): # 导出场景槽函数
        directory = os.path.dirname(self.filename) if self.filename else None # 如果有文件名，获取文件名所在目录，否则为 None
        filename, formatstr = QtWidgets.QFileDialog.getSaveFileName( # 获取保存文件对话框
            parent=self, # 设置进度对话框父窗口为主窗口
            caption='Export Scene to Image', # 导出场景对话框标题
            directory=directory, # 导出场景对话框默认目录为当前文件名所在目录       
            filter=';;'.join(('Image Files (*.png *.jpg *.jpeg *.svg)',
                              'PNG (*.png)',
                              'JPEG (*.jpg *.jpeg)',
                              'SVG (*.svg)')))

        if not filename: # 如果没有文件名
            return # 如果没有文件名，返回   

        name, ext = os.path.splitext(filename) # 从文件名中分离出文件名和扩展名
        if not ext: # 如果没有扩展名
            ext = get_file_extension_from_format(formatstr) # 从格式字符串中获取文件扩展名
            filename = f'{filename}.{ext}' # 添加文件扩展名
        logger.debug(f'Got export filename {filename}') # 调试日志，提示导出文件名  

        exporter_cls = exporter_registry[ext] # 从导出器注册表中获取导出器类
        exporter = exporter_cls(self.scene) # 创建导出器实例，将场景项传递给导出器
        if not exporter.get_user_input(self): # 如果导出器需要用户输入
            return # 如果导出器需要用户输入，返回

        self.worker = fileio.ThreadedIO(exporter.export, filename) # 创建线程化 IO 工作器，将导出函数和文件名传递给工作器   
        self.worker.finished.connect(self.on_export_finished) # 连接完成信号到导出完成槽函数
        self.progress = widgets.BeeProgressDialog( # 创建进度对话框
            f'Exporting {filename}', # 进度对话框标题
            worker=self.worker, # 关联线程化 IO 工作器
            parent=self) # 设置进度对话框父窗口为主窗口
        self.worker.start() # 启动线程化 IO 工作器，开始导出文件        

    def on_export_finished(self, filename, errors): # 导出完成槽函数
        if errors: # 如果有错误
            err_msg = '</br>'.join(str(errors)) # 将错误列表转换为字符串，每个错误之间用换行符分隔
            QtWidgets.QMessageBox.warning( # 显示警告对话框
                self, # 警告对话框父窗口为主窗口
                'Problem writing file', # 警告对话框标题
                f'<p>Problem writing file {filename}</p><p>{err_msg}</p>') # 警告对话框内容，提示导出文件时出现问题，包含文件名和错误信息   

    def on_action_export_images(self): # 导出图像槽函数
        directory = os.path.dirname(self.filename) if self.filename else None # 如果有文件名，获取文件名所在目录，否则为 None
        directory = QtWidgets.QFileDialog.getExistingDirectory( # 获取导出图像对话框
            parent=self, # 设置进度对话框父窗口为主窗口
            caption='Export Images', # 导出图像对话框标题
            directory=directory) # 获取导出图像对话框默认目录为当前文件名所在目录

        if not directory: # 如果没有目录
            return # 如果没有目录，返回 

        logger.debug(f'Got export directory {directory}') # 调试日志，提示导出目录
        self.exporter = ImagesToDirectoryExporter(self.scene, directory) # 创建导出器实例，将场景项和目录传递给导出器
        self.worker = fileio.ThreadedIO(self.exporter.export) # 创建线程化 IO 工作器，将导出函数传递给工作器
        self.worker.user_input_required.connect( # 连接用户输入信号到导出图像文件存在槽函数
            self.on_export_images_file_exists) # 连接用户输入信号到导出图像文件存在槽函数
        self.worker.finished.connect(self.on_export_finished) # 连接完成信号到导出完成槽函数
        self.progress = widgets.BeeProgressDialog( # 创建进度对话框
            f'Exporting to {directory}', # 进度对话框标题
            worker=self.worker, # 关联线程化 IO 工作器
            parent=self) # 设置进度对话框父窗口为主窗口
        self.worker.start() # 启动线程化 IO 工作器，开始导出文件        

    def on_export_images_file_exists(self, filename): # 导出图像文件存在槽函数
        dlg = widgets.ExportImagesFileExistsDialog(self, filename) # 创建导出图像文件存在对话框，将主窗口和文件名传递给对话框
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Accepted: # 如果用户点击了接受按钮
            self.exporter.handle_existing = dlg.get_answer() # 获取用户选择的处理方式，将其赋值给导出器的 handle_existing 属性
            directory = self.exporter.dirname # 获取导出器的目录名，将其赋值给 directory 变量   
            self.progress = widgets.BeeProgressDialog( # 创建进度对话框
                f'Exporting to {directory}', # 进度对话框标题
                worker=self.worker, # 关联线程化 IO 工作器
                parent=self) # 设置进度对话框父窗口为主窗口
            self.worker.start() # 启动线程化 IO 工作器，开始导出文件        

    def on_action_quit(self): # 退出槽函数
        confirm = self.get_confirmation_unsaved_changes( # 获取确认未保存更改对话框
            'There are unsaved changes. Are you sure you want to quit?') # 获取确认未保存更改对话框，将提示信息传递给对话框
        if confirm: # 如果用户点击了接受按钮
            logger.info('User quit. Exiting...') # 调试日志，提示用户退出
            self.app.quit() # 退出应用程序

    def on_action_settings(self): # 设置槽函数
        widgets.settings.SettingsDialog(self) # 创建设置对话框，将主窗口传递给对话框

    def on_action_keyboard_settings(self): # 键盘设置槽函数
        widgets.controls.ControlsDialog(self) # 创建键盘设置对话框，将主窗口传递给对话框

    def on_action_help(self): # 帮助槽函数
        widgets.HelpDialog(self) # 创建帮助对话框，将主窗口传递给对话框

    def on_action_about(self): # 关于槽函数
        QtWidgets.QMessageBox.about( # 显示关于对话框
            self, # 关于对话框父窗口为主窗口
            f'About {constants.APPNAME}', # 关于对话框标题  
            (f'<h2>{constants.APPNAME} {constants.VERSION}</h2>' # 关于对话框内容，包含应用程序名称、版本、完整名称、版权信息和网站链接
             f'<p>{constants.APPNAME_FULL}</p>' # 关于对话框内容，包含应用程序完整名称
             f'<p>{constants.COPYRIGHT}</p>' # 关于对话框内容，包含应用程序版权信息
             f'<p><a href="{constants.WEBSITE}">' # 关于对话框内容，包含应用程序网站链接
             f'Visit the {constants.APPNAME} website</a></p>')) # 关于对话框内容，包含应用程序网站链接

    def on_action_debuglog(self): # 调试日志槽函数
        widgets.DebugLogDialog(self) # 创建设置对话框，将主窗口传递给对话框

    def on_insert_images_finished(self, new_scene, filename, errors): # 插入图像完成槽函数  
        """Callback for when loading of images is finished. # 

        :param new_scene: True if the scene was empty before, else False
        :param filename: Not used, for compatibility only
        :param errors: List of filenames that couldn't be loaded
        """
 
        logger.debug('Insert images finished. Errors: %s', errors) # 调试日志，提示插入图像完成，包含错误文件名列表 
        if errors: # 如果有错误文件名
            errornames = [ # 生成错误文件名列表，每个文件名前添加 <li> 标签
                f'<li>{fn}</li>' for fn in errors] # 生成错误文件名列表，每个文件名前添加 <li> 标签
            errornames = '<ul>%s</ul>' % '\n'.join(errornames) # 生成错误文件名列表，每个文件名前添加 <li> 标签，并用 <ul> 标签包裹起来
            num = len(errors) # 计算错误文件名列表的长度，即错误文件名的数量
            msg = f'{num} image(s) could not be opened.<br/>' # 提示信息，包含错误文件名数量    
            QtWidgets.QMessageBox.warning( # 显示警告对话框
                self, # 关于对话框父窗口为主窗口
                'Problem loading images', # 关于对话框标题，提示加载图像时出现问题
                msg + IMG_LOADING_ERROR_MSG + errornames) # 关于对话框内容，包含错误文件名列表，提示加载图像时出现问题
        self.scene.add_queued_items() # 添加队列中的项目到场景中
        self.scene.arrange_default() # 对场景中的项目进行默认布局
        self.undo_stack.endMacro() # 结束宏操作，将所有操作合并为一个操作
        if new_scene: # 如果场景为空
            self.on_action_fit_scene() # 调用拟合场景槽函数，将场景中的项目调整到合适的大小和位置   

    def do_insert_images(self, filenames, pos=None): # 插入图像槽函数
        """Insert images into the scene. # 插入图像槽函数，将图像插入场景中

        :param filenames: List of filenames to insert
        :param pos: Position to insert the images at, or None for center
        """
        if not pos: # 如果未指定插入位置
            pos = self.get_view_center() # 获取视图中心位置
        self.scene.deselect_all_items() # 取消选择场景中的所有项目
        self.undo_stack.beginMacro('Insert Images') # 开始宏操作，将所有操作合并为一个操作
        self.worker = fileio.ThreadedIO( # 创建线程化 IO 工作器，用于加载图像
            fileio.load_images, # 加载图像函数
            filenames, # 图像文件名列表
            self.mapToScene(pos), # 将插入位置映射到场景坐标
            self.scene) # 场景对象  
        self.worker.progress.connect(self.on_items_loaded) # 连接线程化 IO 工作器的 progress 信号到 on_items_loaded 槽函数，用于更新进度条
        self.worker.finished.connect( # 连接线程化 IO 工作器的 finished 信号到 on_insert_images_finished 槽函数
            partial(self.on_insert_images_finished, # 插入图像完成槽函数，将图像插入场景中
                    not self.scene.items())) # 插入图像完成槽函数，将图像插入场景中，参数为场景是否为空
        self.progress = widgets.BeeProgressDialog( # 创建进度对话框，用于显示加载图像进度
            'Loading images', # 进度对话框标题，提示加载图像进度
            worker=self.worker, # 线程化 IO 工作器，用于加载图像
            parent=self) # 进度对话框父窗口为主窗口 
        self.worker.start() # 启动线程化 IO 工作器，开始加载图像

    def on_action_insert_images(self): # 插入图像槽函数，将图像插入场景中
        self.cancel_active_modes() # 取消激活模式槽函数，将所有激活模式取消激活
        formats = self.get_supported_image_formats(QtGui.QImageReader) # 获取支持的图像格式列表，用于文件对话框筛选
        logger.debug(f'Supported image types for reading: {formats}') # 调试日志，提示支持的图像格式列表
        filenames, f = QtWidgets.QFileDialog.getOpenFileNames( # 获取打开的图像文件名列表，用于插入场景中
            parent=self, # 插入图像槽函数，将图像插入场景中，参数为主窗口
            caption='Select one or more images to open',  # 插入图像槽函数，将图像插入场景中，参数为打开图像文件对话框标题
            filter=f'Images ({formats})') # 插入图像槽函数，将图像插入场景中，参数为打开图像文件对话框筛选器，包含支持的图像格式列表 
        self.do_insert_images(filenames) # 插入图像槽函数，将图像插入场景中，参数为图像文件名列表

    def on_action_insert_text(self): # 插入文本槽函数，将文本插入场景中
        self.cancel_active_modes() # 取消激活模式槽函数，将所有激活模式取消激活
        item = BeeTextItem() # 创建文本项对象，用于插入场景中
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos())) # 获取当前光标位置映射到场景坐标，作为文本项插入位置
        item.setScale(1 / self.get_scale()) # 设置文本项缩放比例，根据当前缩放比例计算得到
        self.undo_stack.push(commands.InsertItems(self.scene, [item], pos)) # 插入文本项到场景中，参数为场景对象、文本项列表、插入位置  

    def on_action_copy(self): # 复制槽函数，将选中的项目复制到剪贴板中
        logger.debug('Copying to clipboard...') # 调试日志，提示复制到剪贴板
        self.cancel_active_modes() # 取消激活模式槽函数，将所有激活模式取消激活
        clipboard = QtWidgets.QApplication.clipboard() # 获取应用程序剪贴板对象，用于复制项目到剪贴板中
        items = self.scene.selectedItems(user_only=True) # 获取场景中选中的项目列表，参数为仅包含用户选择的项目  

        # At the moment, we can only copy one image to the global
        # clipboard. (Later, we might create an image of the whole
        # selection for external copying.)
        items[0].copy_to_clipboard(clipboard) # 复制选中的项目到剪贴板中，参数为应用程序剪贴板对象

        # However, we can copy all items to the internal clipboard:
        self.scene.copy_selection_to_internal_clipboard() # 复制选中的项目到内部剪贴板中，参数为场景对象

        # We set a marker for ourselves in the global clipboard so
        # that we know to look up the internal clipboard when pasting:
        clipboard.mimeData().setData( # 设置应用程序剪贴板对象的自定义数据，用于标识复制的项目数量
            'beeref/items', QtCore.QByteArray.number(len(items))) # 设置自定义数据，参数为数据类型（'beeref/items'）和数据值（项目数量的字节数组表示）  

    def on_action_paste(self): # 粘贴槽函数，将剪贴板中的项目粘贴到场景中
        self.cancel_active_modes() # 取消激活模式槽函数，将所有激活模式取消激活
        logger.debug('Pasting from clipboard...') # 调试日志，提示从剪贴板粘贴
        clipboard = QtWidgets.QApplication.clipboard() # 获取应用程序剪贴板对象，用于粘贴项目到场景中
        pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos())) # 获取当前光标位置映射到场景坐标，作为粘贴位置   

        # See if we need to look up the internal clipboard:
        data = clipboard.mimeData().data('beeref/items') # 获取应用程序剪贴板对象的自定义数据，用于标识复制的项目数量
        logger.debug(f'Custom data in clipboard: {data}') # 调试日志，提示自定义数据在剪贴板中      
        if data and self.scene.internal_clipboard: # 如果自定义数据在剪贴板中且场景对象有内部剪贴板
            # Checking that internal clipboard exists since the user
            # may have opened a new scene since copying.
            self.scene.paste_from_internal_clipboard(pos) # 从内部剪贴板中粘贴项目到场景中，参数为粘贴位置  
            return

        img = clipboard.image() # 获取应用程序剪贴板对象的图像数据
        if not img.isNull(): # 如果图像数据不是空的
            item = BeePixmapItem(img) # 创建图片项对象，参数为图像数据
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos)) # 插入图片项到场景中，参数为场景对象、图片项列表、插入位置
            if len(self.scene.items()) == 1: # 如果场景中只有一个项目（即插入的图片项） 
             if len(self.scene.items()) == 1: # 
                # This is the first image in the scene
                self.on_action_fit_scene() # 缩放场景槽函数，将场景缩放以适应所有项目
            return
        text = clipboard.text() # 获取应用程序剪贴板对象的文本数据
        if text: # 如果文本数据不是空的
            item = BeeTextItem(text) # 创建文本项对象，参数为文本数据 
            item.setScale(1 / self.get_scale()) # 设置文本项缩放比例，根据当前缩放比例计算得到
            self.undo_stack.push(commands.InsertItems(self.scene, [item], pos)) # 插入文本项到场景中，参数为场景对象、文本项列表、插入位置  
            return

        msg = 'No image data or text in clipboard or image too big'
        logger.info(msg) # 信息日志，提示没有图像数据或文本数据在剪贴板中或图像太大
        widgets.BeeNotification(self, msg) # 显示通知槽函数，参数为父窗口对象（self）和通知消息（msg）

    def on_action_open_settings_dir(self): # 打开设置目录槽函数，用于打开应用程序的设置目录 
        dirname = os.path.dirname(self.settings.fileName()) # 获取应用程序设置文件的目录路径
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(dirname)) # 打开目录路径对应的本地文件资源    

    def on_selection_changed(self): # 选择项改变槽函数，用于处理场景中选中项的变化
        logger.debug('Currently selected items: %s',
                     len(self.scene.selectedItems(user_only=True))) # 调试日志，提示当前选中的项目数量  
        self.actiongroup_set_enabled('active_when_selection', # 启用/禁用操作组槽函数，根据场景是否有选中项来启用/禁用操作组
                                     self.scene.has_selection()) # 启用/禁用操作组槽函数，根据场景是否有选中项来启用/禁用操作组
        self.actiongroup_set_enabled('active_when_single_image', # 启用/禁用操作组槽函数，根据场景是否有单个图片选中项来启用/禁用操作组
                                     self.scene.has_single_image_selection()) # 启用/禁用操作组槽函数，根据场景是否有单个图片选中项来启用/禁用操作组

        if self.scene.has_selection(): # 如果场景有选中项
            item = self.scene.selectedItems(user_only=True)[0] # 获取场景中第一个选中项，参数为用户仅选择项 
            grayscale = getattr(item, 'grayscale', False) # 获取选中项的灰度属性，默认值为False
            actions.actions['grayscale'].qaction.setChecked(grayscale) # 设置灰度操作项的复选框状态，根据选中项的灰度属性来设置
        self.viewport().repaint() # 重绘视口槽函数，用于刷新视口显示，确保选中项的灰度属性复选框状态正确显示

    def on_cursor_changed(self, cursor): # 光标改变槽函数，用于处理场景中光标位置的变化
        if self.active_mode is None: # 如果当前激活模式为None
            self.viewport().setCursor(cursor) # 设置视口光标为参数cursor

    def on_cursor_cleared(self): # 光标清除槽函数，用于处理场景中光标位置的清除
        if self.active_mode is None: # 如果当前激活模式为None
            self.viewport().unsetCursor() # 清除视口光标    

    def recalc_scene_rect(self): # 重新计算场景矩形槽函数，用于调整场景矩形以适应所有项目
        """Resize the scene rectangle so that it is always one view width
        wider than all items' bounding box at each side and one view
        width higher on top and bottom. This gives the impression of
        an infinite canvas."""

        if self.previous_transform: # 如果之前有变换矩阵
            return
        logger.trace('Recalculating scene rectangle...') # 跟踪日志，提示重新计算场景矩形
        try:
            topleft = self.mapFromScene( # 映射场景矩形的左上角到视口坐标
                self.scene.itemsBoundingRect().topLeft()) # 映射场景矩形的左上角到视口坐标
            topleft = self.mapToScene(QtCore.QPoint( # 映射视口坐标的左上角到场景坐标
                topleft.x() - self.size().width() / 2, # 减去视口宽度的一半，确保场景矩形在视口宽度的一半宽度内 
                topleft.y() - self.size().height() / 2)) # 减去视口高度的一半，确保场景矩形在视口高度的一半高度内
            bottomright = self.mapFromScene( # 映射场景矩形的右下角到视口坐标
                self.scene.itemsBoundingRect().bottomRight()) # 映射场景矩形的右下角到视口坐标 
            bottomright = self.mapToScene(QtCore.QPoint( # 映射视口坐标的右下角到场景坐标
                bottomright.x() + self.size().width() / 2, # 加上视口宽度的一半，确保场景矩形在视口宽度的一半宽度内
                bottomright.y() + self.size().height() / 2)) # 加上视口高度的一半，确保场景矩形在视口高度的一半高度内   
            self.setSceneRect(QtCore.QRectF(topleft, bottomright)) # 设置场景矩形为新计算的矩形
        except OverflowError: # 处理溢出错误，当场景矩形超出最大尺寸时触发
            logger.info('Maximum scene size reached') # 信息日志，提示最大场景尺寸已达到
        logger.trace('Done recalculating scene rectangle') # 跟踪日志，提示完成重新计算场景矩形 

    def get_zoom_size(self, func): # 获取缩放尺寸槽函数，用于计算场景中所有项目的边界框尺寸
        """Calculates the size of all items' bounding box in the view's
        coordinates.

        This helps ensure that we never zoom out too much (scene
        becomes so tiny that items become invisible) or zoom in too
        much (causing overflow errors).

        :param func: Function which takes the width and height as
            arguments and turns it into a number, for ex. ``min`` or ``max``.
        """

        topleft = self.mapFromScene( # 映射场景矩形的左上角到视口坐标
            self.scene.itemsBoundingRect().topLeft()) # 映射场景矩形的左上角到视口坐标
        bottomright = self.mapFromScene( # 映射场景矩形的右下角到视口坐标
            self.scene.itemsBoundingRect().bottomRight()) # 映射场景矩形的右下角到视口坐标   
        return func(bottomright.x() - topleft.x(), # 计算场景中所有项目的边界框宽度
                    bottomright.y() - topleft.y()) # 计算场景中所有项目的边界框高度 

    def scale(self, *args, **kwargs): # 缩放槽函数，用于处理场景中项目的缩放
        super().scale(*args, **kwargs) # 调用父类的缩放槽函数，用于处理场景中项目的缩放
        self.scene.on_view_scale_change() # 调用场景中的视图缩放变化槽函数，用于处理场景中项目的缩放变化
        self.recalc_scene_rect() # 重新计算场景矩形槽函数，用于调整场景矩形以适应所有项目

    def get_scale(self):
        return self.transform().m11() # 返回当前变换矩阵的缩放比例因子  

    def pan(self, delta): # 平移槽函数，用于处理场景中项目的平移
        if not self.scene.items(): # 如果场景中没有项目
            logger.debug('No items in scene; ignore pan') # 调试日志，提示场景中没有项目，忽略平移
            return

        hscroll = self.horizontalScrollBar() # 获取水平滚动条
        hscroll.setValue(int(hscroll.value() + delta.x())) # 设置水平滚动条的值为当前值加上平移量的整数部分
        vscroll = self.verticalScrollBar() # 获取垂直滚动条
        vscroll.setValue(int(vscroll.value() + delta.y())) # 设置垂直滚动条的值为当前值加上平移量的整数部分 

    def zoom(self, delta, anchor): # 缩放槽函数，用于处理场景中项目的缩放
        if not self.scene.items(): # 如果场景中没有项目
            logger.debug('No items in scene; ignore zoom') # 调试日志，提示场景中没有项目，忽略缩放 
            return

        # We calculate where the anchor is before and after the zoom
        # and then move the view accordingly to keep the anchor fixed
        # We can't use QGraphicsView's AnchorUnderMouse since it
        # uses the current cursor position while we need the initial mouse
        # press position for zooming with Ctrl + Middle Drag
        anchor = QtCore.QPoint(round(anchor.x()), # 四舍五入 anchor 的 x 坐标
                               round(anchor.y())) # 四舍五入 anchor 的 y 坐标
        ref_point = self.mapToScene(anchor) # 映射 anchor 到场景坐标
        if delta == 0: # 如果缩放量为 0
            return  # 如果缩放量为 0，忽略缩放
        factor = 1 + abs(delta / 1000) # 计算缩放因子
        if delta > 0: # 如果缩放量大于 0
            if self.get_zoom_size(max) < 10000000: # 如果缩放后场景中所有项目的边界框宽度和高度都小于 10000000
                self.scale(factor, factor) # 缩放场景中所有项目的边界框宽度和高度
            else:  # 如果缩放后场景中所有项目的边界框宽度和高度都大于等于 10000000
                logger.debug('Maximum zoom size reached') # 调试日志，提示最大缩放尺寸已达到
                return # 如果缩放后场景中所有项目的边界框宽度和高度都大于等于 10000000，忽略缩放
        else:
            if self.get_zoom_size(min) > 50: # 如果缩放后场景中所有项目的边界框宽度和高度都大于 50
                self.scale(1/factor, 1/factor) # 缩放场景中所有项目的边界框宽度和高度
            else:
                logger.debug('Minimum zoom size reached') # 调试日志，提示最小缩放尺寸已达到
                return # 如果缩放后场景中所有项目的边界框宽度和高度都大于 50，忽略缩放  

        self.pan(self.mapFromScene(ref_point) - anchor) # 平移场景中所有项目的边界框宽度和高度
        self.reset_previous_transform() # 重置前一个变换矩阵，用于处理场景中项目的缩放变化

    def wheelEvent(self, event): # 滚轮事件槽函数，用于处理场景中项目的缩放和平移
        action, inverted\
            = self.keyboard_settings.mousewheel_action_for_event(event) # 获取滚轮事件的缩放和平移操作

        delta = event.angleDelta().y() # 获取滚轮事件的缩放增量
        if inverted: # 如果滚轮事件的缩放增量为负数
            delta = delta * -1 # 取反缩放增量   

        if action == 'zoom': # 如果滚轮事件的缩放操作
            self.zoom(delta, event.position()) # 调用缩放槽函数，用于处理场景中项目的缩放
            event.accept() # 接受滚轮事件，防止事件冒泡到父类
            return 
        if action == 'pan_horizontal': # 如果滚轮事件的水平平移操作
            self.pan(QtCore.QPointF(0, 0.5 * delta)) # 调用平移槽函数，用于处理场景中项目的水平平移
            event.accept() # 接受滚轮事件，防止事件冒泡到父类
            return
        if action == 'pan_vertical': # 如果滚轮事件的垂直平移操作
            self.pan(QtCore.QPointF(0.5 * delta, 0)) # 调用平移槽函数，用于处理场景中项目的垂直平移
            event.accept() # 接受滚轮事件，防止事件冒泡到父类   
            return

    def mousePressEvent(self, event): # 鼠标按下事件槽函数，用于处理场景中项目的缩放和平移
        if self.mousePressEventMainControls(event): # 如果鼠标按下事件是主控件的事件
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE: # 如果当前模式是采样颜色模式
            if (event.button() == Qt.MouseButton.LeftButton): # 如果鼠标按下事件是左键
                color = self.scene.sample_color_at( # 调用场景中的采样颜色函数，用于获取场景中指定位置的颜色
                    self.mapToScene(event.pos())) # 映射鼠标按下事件的位置到场景坐标
                if color: # 如果获取到颜色
                    name = qcolor_to_hex(color) # 将颜色转换为十六进制字符串
                    clipboard = QtWidgets.QApplication.clipboard() # 获取应用程序的剪贴板对象
                    clipboard.setText(name) # 将颜色的十六进制字符串复制到剪贴板
                    self.scene.internal_clipboard = [] # 清空场景中的内部剪贴板
                    msg = f'Copied color to clipboard: {name}' 
                    logger.debug(msg) # 调试日志，提示复制颜色到剪贴板
                    widgets.BeeNotification(self, msg) # 显示通知消息，提示复制颜色到剪贴板
                else:
                    logger.debug('No color found at %s', event.pos()) # 调试日志，提示未找到颜色
            self.cancel_sample_color_mode() # 取消采样颜色模式
            event.accept() # 接受鼠标按下事件，防止事件冒泡到父类
            return

        action, inverted = self.keyboard_settings.mouse_action_for_event(event) # 获取鼠标按下事件的缩放和平移操作

        if action == 'zoom': # 如果鼠标按下事件的缩放操作
            self.active_mode = self.ZOOM_MODE # 设置当前模式为缩放模式
            self.event_start = event.position() # 记录鼠标按下事件的位置
            self.event_anchor = event.position() # 记录鼠标按下事件的位置
            self.event_inverted = inverted # 记录鼠标按下事件的缩放增量是否为负数
            event.accept() # 接受鼠标按下事件，防止事件冒泡到父类
            return

        if action == 'pan': # 如果鼠标按下事件的平移操作
            logger.trace('Begin pan')
            self.active_mode = self.PAN_MODE # 设置当前模式为平移模式
            self.event_start = event.position() # 记录鼠标按下事件的位置    
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor) # 设置视口的光标为关闭手型光标
            # ClosedHandCursor and OpenHandCursor don't work, but I
            # don't know if that's only on my system or a general
            # problem. It works with other cursors.
            event.accept() # 接受鼠标按下事件，防止事件冒泡到父类
            return

        super().mousePressEvent(event) # 调用父类的鼠标按下事件槽函数，用于处理其他鼠标按下事件

    def mouseMoveEvent(self, event): # 鼠标移动事件槽函数，用于处理场景中项目的缩放和平移
        if self.active_mode == self.PAN_MODE: # 如果当前模式是平移模式
            self.reset_previous_transform() # 重置前一次变换，用于处理场景中项目的缩放和平移
            pos = event.position() # 获取鼠标移动事件的位置
            self.pan(self.event_start - pos) # 调用平移槽函数，用于处理场景中项目的平移
            self.event_start = pos # 更新鼠标按下事件的位置
            event.accept() # 接受鼠标移动事件，防止事件冒泡到父类   
            return

        if self.active_mode == self.ZOOM_MODE: # 如果当前模式是缩放模式
            self.reset_previous_transform() # 重置前一次变换，用于处理场景中项目的缩放和平移
            pos = event.position() # 获取鼠标移动事件的位置
            delta = (self.event_start - pos).y() # 计算鼠标移动事件的垂直增量
            if self.event_inverted: # 如果鼠标移动事件的缩放增量为负数
                delta *= -1 # 取反，用于处理场景中项目的缩放
            self.event_start = pos # 更新鼠标按下事件的位置 
            self.zoom(delta * 20, self.event_anchor) # 调用缩放槽函数，用于处理场景中项目的缩放
            event.accept() # 接受鼠标移动事件，防止事件冒泡到父类   
            return

        if self.active_mode == self.SAMPLE_COLOR_MODE: # 如果当前模式是采样颜色模式
            self.sample_color_widget.update( # 更新采样颜色小部件的显示
                event.position(), # 更新采样颜色小部件的显示位置
                self.scene.sample_color_at(self.mapToScene(event.pos()))) # 更新采样颜色小部件的显示颜色
            event.accept() # 接受鼠标移动事件，防止事件冒泡到父类   
            return

        if self.mouseMoveEventMainControls(event): # 如果主控件处理了鼠标移动事件
            return
        super().mouseMoveEvent(event) # 调用父类的鼠标移动事件槽函数，用于处理其他鼠标移动事件

    def mouseReleaseEvent(self, event): # 鼠标释放事件槽函数，用于处理场景中项目的缩放和平移 
        if self.active_mode == self.PAN_MODE: # 如果当前模式是平移模式
            logger.trace('End pan') # 调试日志，提示结束平移
            self.viewport().unsetCursor() # 重置视口的光标为默认光标
            self.active_mode = None # 重置当前模式为 None
            event.accept() # 接受鼠标释放事件，防止事件冒泡到父类   
            return
        if self.active_mode == self.ZOOM_MODE: # 如果当前模式是缩放模式
            self.active_mode = None # 重置当前模式为 None
            event.accept() # 接受鼠标释放事件，防止事件冒泡到父类   
            return
        if self.mouseReleaseEventMainControls(event): # 如果主控件处理了鼠标释放事件
            return
        super().mouseReleaseEvent(event) # 调用父类的鼠标释放事件槽函数，用于处理其他鼠标释放事件   

    def resizeEvent(self, event): # 场景视图的大小调整事件槽函数，用于处理场景视图的大小调整
        super().resizeEvent(event) # 调用父类的大小调整事件槽函数，用于处理其他大小调整事件
        self.recalc_scene_rect() # 重新计算场景矩形，用于处理场景中项目的缩放和平移
        self.welcome_overlay.resize(self.size()) # 调整欢迎叠加层的大小，用于处理场景视图的大小调整

    def keyPressEvent(self, event): # 键盘按下事件槽函数，用于处理场景中项目的缩放和平移
        if self.keyPressEventMainControls(event): # 如果主控件处理了键盘按下事件
            return
        if self.active_mode == self.SAMPLE_COLOR_MODE: # 如果当前模式是采样颜色模式
            self.cancel_sample_color_mode() # 取消采样颜色模式
            event.accept() # 接受键盘按下事件，防止事件冒泡到父类   
            return
        super().keyPressEvent(event) # 调用父类的键盘按下事件槽函数，用于处理其他键盘按下事件
