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

from functools import partial  # 导入偏函数，用于固定函数参数创建新函数
import logging  # 导入日志模块，用于记录程序运行时的日志信息
import math  # 导入数学模块，用于数学计算（如三角函数、平方根等）
from queue import Queue  # 导入队列数据结构，用于线程间通信或任务排队

from PyQt6 import QtCore, QtWidgets, QtGui  # 导入PyQt6的核心模块、控件模块和GUI模块
from PyQt6.QtCore import Qt  # 导入Qt常量定义（如对齐方式、事件类型等）

import rpack  # 导入矩形打包库，用于高效排列矩形元素

from beeref import commands  # 导入beeref项目的命令模块，处理用户操作的命令实现
from beeref.config import BeeSettings  # 导入配置设置类，管理应用程序的用户配置
from beeref.items import item_registry, BeeErrorItem, sort_by_filename  # 导入项目项相关组件：注册表、错误项和文件名排序函数
from beeref.selection import MultiSelectItem, RubberbandItem  # 导入选择相关类：多选项和橡皮筋选择框


logger = logging.getLogger(__name__)  # 创建当前模块的日志记录器


class BeeGraphicsScene(QtWidgets.QGraphicsScene):  # 定义场景类，继承自QGraphicsScene
    cursor_changed = QtCore.pyqtSignal(QtGui.QCursor)  # 定义光标变化信号
    cursor_cleared = QtCore.pyqtSignal()  # 定义光标清除信号

    MOVE_MODE = 1  # 定义移动模式常量
    RUBBERBAND_MODE = 2  # 定义橡皮筋选择模式常量

    def __init__(self, undo_stack):  # 初始化方法，接收撤销栈参数
        super().__init__()  # 调用父类的初始化方法
        self.active_mode = None  # 初始化当前活动模式为None
        self.undo_stack = undo_stack  # 保存撤销栈引用
        self.max_z = 0  # 初始化最大Z轴值
        self.min_z = 0  # 初始化最小Z轴值
        self.Z_STEP = 0.001  # 设置Z轴步长
        self.selectionChanged.connect(self.on_selection_change)  # 连接选择变化信号到处理函数
        self.changed.connect(self.on_change)  # 连接场景变化信号到处理函数
        self.items_to_add = Queue()  # 初始化待添加项目队列
        self.edit_item = None  # 初始化当前编辑项目为None
        self.crop_item = None  # 初始化裁剪项目为None
        self.settings = BeeSettings()  # 初始化设置对象
        self.clear()  # 清除场景内容
        self._clear_ongoing = False  # 初始化清除操作标志为False

    def clear(self):
        self._clear_ongoing = True # 设置清理进行中标志，避免清理过程中触发其他依赖状态的逻辑
        super().clear() # 调用父类的清除方法，清除场景中的所有项目
        self.internal_clipboard = [] # 初始化内部剪贴板为空列表，用于存储复制到剪贴板的项目
        self.rubberband_item = RubberbandItem() # 重新创建橡皮筋选择框实例，重置选择框状态
        self.multi_select_item = MultiSelectItem() # 重新创建多选项实例，重置多选项状态
        self._clear_ongoing = False # 清除操作完成，重置清除进行中标志

    def addItem(self, item): # 添加项目到场景
        logger.debug(f'Adding item {item}') # 记录添加项目的调试日志
        super().addItem(item) # 调用父类的添加项目方法，将项目添加到场景中

    def removeItem(self, item): # 从场景中移除项目
        logger.debug(f'Removing item {item}') # 记录移除项目的调试日志
        super().removeItem(item) # 调用父类的移除项目方法，将项目从场景中移除

    def cancel_active_modes(self): # 取消所有活动模式
        """Cancels ongoing crop modes, rubberband modes etc, if there are
        any.
        """
        self.cancel_crop_mode() # 取消当前的裁剪模式
        self.end_rubberband_mode() # 结束当前的橡皮筋选择模式

    def end_rubberband_mode(self): # 结束橡皮筋选择模式
        if self.rubberband_item.scene(): # 如果橡皮筋选择框存在于场景中
            logger.debug('Ending rubberband selection') # 记录结束橡皮筋选择模式的调试日志
            self.removeItem(self.rubberband_item) # 从场景中移除橡皮筋选择框
        self.active_mode = None # 重置当前活动模式为None

    def cancel_crop_mode(self): # 取消当前的裁剪模式
        """Cancels an ongoing crop mode, if there is any.""" 
        if self.crop_item: # 如果存在裁剪项目
            self.crop_item.exit_crop_mode(confirm=False) # 退出裁剪模式，不确认裁剪

    def copy_selection_to_internal_clipboard(self): # 复制当前选择的项目到内部剪贴板
        self.internal_clipboard = [] # 清空内部剪贴板
        for item in self.selectedItems(user_only=True): # 遍历当前用户选择的项目
            self.internal_clipboard.append(item) # 将项目添加到内部剪贴板

    def paste_from_internal_clipboard(self, position): # 从内部剪贴板粘贴项目到指定位置
        copies = [] # 创建一个空列表，用于存储复制的项目
        for item in self.internal_clipboard:
            copy = item.create_copy() # 创建当前项目的副本
            copies.append(copy) # 将副本添加到复制列表中
        self.undo_stack.push(commands.InsertItems(self, copies, position)) # 将复制操作添加到撤销栈中

    def raise_to_top(self): # 将当前选择的项目提升到顶部
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        items = self.selectedItems(user_only=True) # 获取当前用户选择的项目
        z_values = map(lambda i: i.zValue(), items) # 提取项目的Z轴值
        delta = self.max_z + self.Z_STEP - min(z_values) # 计算需要提升的Z轴值增量
        logger.debug(f'Raise to top, delta: {delta}') # 记录提升到顶部的调试日志
        for item in items: # 遍历选择的项目
            item.setZValue(item.zValue() + delta) # 提升项目的Z轴值，将其提升到顶部

    def lower_to_bottom(self): # 将当前选择的项目降低到底部
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        items = self.selectedItems(user_only=True) # 获取当前用户选择的项目
        z_values = map(lambda i: i.zValue(), items) # 提取项目的Z轴值
        delta = self.min_z - self.Z_STEP - max(z_values) # 计算需要降低的Z轴值增量
        logger.debug(f'Lower to bottom, delta: {delta}') # 记录降低到底部的调试日志

        for item in items: # 遍历选择的项目
            item.setZValue(item.zValue() + delta) # 降低项目的Z轴值，将其降低到底部

    def normalize_width_or_height(self, mode): # 归一化选择项目的宽度或高度
        """Scale the selected images to have the same width or height, as
        specified by ``mode``.

        :param mode: "width" or "height".
        """

        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        values = [] # 创建一个空列表，用于存储选择项目的宽度或高度值
        items = self.selectedItems(user_only=True) # 获取当前用户选择的项目
        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            values.append(getattr(rect, mode)()) # 提取矩形的宽度或高度值，并添加到列表中
        if len(values) < 2: # 如果选择的项目数量小于2
            return # 直接返回，无需归一化
        avg = sum(values) / len(values) # 计算宽度或高度的平均值
        logger.debug(f'Calculated average {mode} {avg}') # 记录归一化的平均值调试日志

        scale_factors = [] # 创建一个空列表，用于存储每个项目的归一化缩放因子
        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            scale_factors.append(avg / getattr(rect, mode)()) # 计算项目的归一化缩放因子，并添加到列表中
        self.undo_stack.push(
            commands.NormalizeItems(items, scale_factors)) # 将归一化操作添加到撤销栈中

    def normalize_height(self): # 归一化选择项目的高度
        """Scale selected images to the same height."""
        return self.normalize_width_or_height('height') # 归一化选择项目的高度

    def normalize_width(self): # 归一化选择项目的宽度
        """Scale selected images to the same width."""
        return self.normalize_width_or_height('width') # 归一化选择项目的宽度

    def normalize_size(self): # 归一化选择项目的大小
        """Scale selected images to the same size.

        Size meaning the area = widh * height.
        """

        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        sizes = [] # 创建一个空列表，用于存储选择项目的面积值
        items = self.selectedItems(user_only=True) # 获取当前用户选择的项目
        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            sizes.append(rect.width() * rect.height()) # 计算项目的面积值，并添加到列表中

        if len(sizes) < 2: # 如果选择的项目数量小于2
            return # 直接返回，无需归一化

        avg = sum(sizes) / len(sizes) # 计算选择项目的面积平均值
        logger.debug(f'Calculated average size {avg}') # 记录归一化的平均值调试日志

        scale_factors = [] # 创建一个空列表，用于存储每个项目的归一化缩放因子
        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            scale_factors.append(math.sqrt(avg / rect.width() / rect.height())) # 计算项目的归一化缩放因子，并添加到列表中
        self.undo_stack.push(
            commands.NormalizeItems(items, scale_factors)) # 将归一化操作添加到撤销栈中



    def arrange_default(self): # 按默认方式排列选择的项目
        default = self.settings.valueOrDefault('Items/arrange_default') # 获取默认的排列方式
        MAPPING = {
            'optimal': self.arrange_optimal,  # 最优排列方式
            'horizontal': self.arrange,  # 水平排列方式
            'vertical': partial(self.arrange, vertical=True),  # 垂直排列方式
            'square': self.arrange_square,  # 正方形排列方式
        }

        MAPPING[default]() # 调用默认的排列方式

    def arrange(self, vertical=False): # 按指定方式排列选择的项目
        """Arrange items in a line (horizontally or vertically).""" # 按指定方式排列选择的项目

        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰

        items = sort_by_filename(self.selectedItems(user_only=True)) # 获取当前用户选择的项目，并按文件名排序
        if len(items) < 2:# 如果选择的项目数量小于2
            return # 直接返回，无需排列

        gap = self.settings.valueOrDefault('Items/arrange_gap') # 获取项目之间的间距
        center = self.get_selection_center() # 获取选择项目的中心位置
        positions = [] # 创建一个空列表，用于存储每个项目的新位置
        rects = [] # 创建一个空列表，用于存储每个项目的边界矩形和项目本身
        for item in items: # 遍历选择的项目
            rects.append({ # 为每个项目创建一个字典，包含项目的边界矩形和项目本身
                'rect': self.itemsBoundingRect(items=[item]), # 获取项目的边界矩形
                'item': item}) # 包含项目的边界矩形和项目本身

        if vertical: # 如果按垂直方向排列
            rects.sort(key=lambda r: r['rect'].topLeft().y()) # 按项目的顶部坐标排序
            sum_height = sum(map(lambda r: r['rect'].height(), rects)) # 计算所有项目的总高度
            y = round(center.y() - sum_height/2) # 计算垂直方向上的起始位置
            for rect in rects: # 遍历每个项目
                positions.append( # 为每个项目计算新的位置
                    QtCore.QPointF( # 计算每个项目的新位置
                        round(center.x() - rect['rect'].width()/2), y)) # 计算每个项目的新位置
                y += rect['rect'].height() + gap # 更新垂直方向上的位置，考虑项目高度和间距

        else: # 如果按水平方向排列
            rects.sort(key=lambda r: r['rect'].topLeft().x()) # 按项目的左侧坐标排序
            sum_width = sum(map(lambda r: r['rect'].width(), rects)) # 计算所有项目的总宽度
            x = round(center.x() - sum_width/2) # 计算水平方向上的起始位置
            for rect in rects: # 遍历每个项目
                positions.append( # 为每个项目计算新的位置
                    QtCore.QPointF( # 计算每个项目的新位置
                        x, round(center.y() - rect['rect'].height()/2))) # 计算每个项目的新位置
                x += rect['rect'].width() + gap # 更新水平方向上的位置，考虑项目宽度和间距

        self.undo_stack.push( # 将排列操作添加到撤销栈中
            commands.ArrangeItems(self, # 创建一个排列项目的命令对象
                                  [r['item'] for r in rects], # 包含所有要排列的项目
                                  positions)) # 包含所有项目的新位置

    def arrange_optimal(self): # 按最优方式排列选择的项目
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰

        items = self.selectedItems(user_only=True) # 获取当前用户选择的项目
        if len(items) < 2: # 如果选择的项目数量小于2
            return # 直接返回，无需排列

        gap = self.settings.valueOrDefault('Items/arrange_gap') # 获取项目之间的间距

        sizes = [] # 创建一个空列表，用于存储每个项目的宽度和高度
        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            sizes.append((round(rect.width() + gap), # 包含每个项目的宽度和高度
                          round(rect.height() + gap))) # 包含每个项目的宽度和高度

        # The minimal area the items need if they could be packed optimally;
        # we use this as a starting shape for the packing algorithm
        min_area = sum(map(lambda s: s[0] * s[1], sizes)) # 计算所有项目的最小面积
        width = math.ceil(math.sqrt(min_area)) # 计算最小面积的平方根，向上取整作为初始宽度

        positions = None # 初始化位置列表为None
        while not positions: # 循环直到成功打包项目
            try: # 尝试使用当前宽度打包项目
                positions = rpack.pack( 
                    sizes, max_width=width, max_height=width)
            except rpack.PackingImpossibleError:
                width = math.ceil(width * 1.2) # 如果打包失败，将宽度增加20%，并向上取整

        # We want the items to center around the selection's center,
        # not (0, 0)
        center = self.get_selection_center() # 获取选择项目的中心位置
        bounds = rpack.bbox_size(sizes, positions) # 计算打包后的边界矩形大小
        diff = center - QtCore.QPointF(bounds[0]/2, bounds[1]/2) # 计算中心位置与边界矩形中心位置的差值
        positions = [QtCore.QPointF(*pos) + diff for pos in positions] # 为每个项目计算新的位置，考虑中心位置的偏移

        self.undo_stack.push(commands.ArrangeItems(self, items, positions)) # 将排列操作添加到撤销栈中

    def arrange_square(self): # 按正方形方式排列选择的项目
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        max_width = 0 # 初始化最大宽度为0
        max_height = 0 # 初始化最大高度为0
        gap = self.settings.valueOrDefault('Items/arrange_gap') # 获取项目之间的间距
        items = sort_by_filename(self.selectedItems(user_only=True)) # 获取当前用户选择的项目，并按文件名排序

        if len(items) < 2: # 如果选择的项目数量小于2
            return # 直接返回，无需排列

        for item in items: # 遍历选择的项目
            rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
            max_width = max(max_width, rect.width() + gap) # 更新最大宽度，考虑项目宽度和间距
            max_height = max(max_height, rect.height() + gap) # 更新最大高度，考虑项目高度和间距

        # We want the items to center around the selection's center,
        # not (0, 0)
        num_rows = math.ceil(math.sqrt(len(items))) # 计算需要的行数，向上取整
        center = self.get_selection_center() # 获取选择项目的中心位置
        diff = center - num_rows/2 * QtCore.QPointF(max_width, max_height) # 计算中心位置与边界矩形中心位置的差值

        iter_items = iter(items) # 创建一个迭代器，用于遍历选择的项目
        positions = [] # 创建一个空列表，用于存储每个项目的新位置
        for j in range(num_rows):# 遍历行数
            for i in range(num_rows):# 遍历列数
                try:
                    item = next(iter_items) # 从迭代器中获取下一个项目
                    rect = self.itemsBoundingRect(items=[item]) # 获取项目的边界矩形
                    point = QtCore.QPointF( # 计算项目的新位置
                        i * max_width + (max_width - rect.width())/2, # 计算项目在当前行的水平位置
                        j * max_height + (max_height - rect.height())/2) # 计算项目在当前列的垂直位置
                    positions.append(point + diff) # 计算项目的新位置，考虑中心位置的偏移
                except StopIteration:# 当迭代器没有更多项目时，跳出循环
                    break # 跳出当前列的循环，继续下一行

        self.undo_stack.push(commands.ArrangeItems(self, items, positions)) # 将排列操作添加到撤销栈中

    def flip_items(self, vertical=False): # 垂直或水平翻转选择的项目
        """Flip selected items."""
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        self.undo_stack.push(
            commands.FlipItems(self.selectedItems(user_only=True),
                               self.get_selection_center(),
                               vertical=vertical)) # 将翻转操作添加到撤销栈中

    def crop_items(self): # 对选择的项目进行裁剪
        """Crop selected item."""

        if self.crop_item:## 如果当前有项目正在裁剪状态
            return
        if self.has_single_image_selection():# 如果选择的项目是单个图像
            item = self.selectedItems(user_only=True)[0]
            if item.is_image:
                item.enter_crop_mode() # 进入图像裁剪模式

    def sample_color_at(self, position): # 采样指定位置的颜色
        item_at_pos = self.itemAt(position, self.views()[0].transform()) # 获取指定位置上的项目
        if item_at_pos:
            return item_at_pos.sample_color_at(position) # 如果项目存在，采样该位置的颜色

    def select_all_items(self): # 选择所有项目
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        path = QtGui.QPainterPath() # 创建一个空的绘图路径
        path.addRect(self.itemsBoundingRect()) # 创建一个矩形路径，包含所有项目的边界矩形
        path.addRect(self.itemsBoundingRect())  
        path.addRect(self.itemsBoundingRect()) 
        # This is faster than looping through all items and calling setSelected
        self.setSelectionArea(path)# 设置选择区域为创建的路径，包含所有项目的边界矩形

    def deselect_all_items(self):# 取消所有项目的选择
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        self.clearSelection() # 清除所有项目的选择状态

    def has_selection(self):# 检查是否有项目被选择
        """Checks whether there are currently items selected."""

        return bool(self.selectedItems(user_only=True)) # 返回当前用户选择的项目是否为空

    def has_single_selection(self):# 检查是否有单个项目被选择
        """Checks whether there's currently exactly one item selected."""

        return len(self.selectedItems(user_only=True)) == 1 # 返回当前用户选择的项目是否只有一个

    def has_multi_selection(self):# 检查是否有多个项目被选择
        """Checks whether there are currently more than one items selected."""

        return len(self.selectedItems(user_only=True)) > 1 # 返回当前用户选择的项目是否有多个

    def has_single_image_selection(self):# 检查是否有单个图像项目被选择
        """Checks whether the current selection is a single image."""

        if self.has_single_selection(): # 如果只有一个项目被选择
            return self.selectedItems(user_only=True)[0].is_image # 检查该项目是否为图像
        return False # 如果不是图像或没有项目被选择，返回False

    def mousePressEvent(self, event):# 处理鼠标按下事件
        if event.button() == Qt.MouseButton.RightButton: # 如果是右键点击
            # Right-click invokes the context menu on the
            # GraphicsView. We don't need it here.
            return

        if event.button() == Qt.MouseButton.LeftButton: # 如果是左键点击
            self.event_start = event.scenePos() # 记录鼠标按下时的场景位置
            item_at_pos = self.itemAt(
                event.scenePos(), self.views()[0].transform()) # 获取当前鼠标位置上的项目

            if self.edit_item and item_at_pos != self.edit_item: # 如果当前有项目正在编辑状态，且点击的项目不是当前编辑项目
                self.edit_item.exit_edit_mode() # 退出当前编辑项目的编辑状态
            elif self.edit_item and item_at_pos == self.edit_item: # 如果当前有项目正在编辑状态，且点击的项目是当前编辑项目
                super().mousePressEvent(event) # 调用父类的鼠标按下事件处理方法，确保正常编辑操作
                return # 结束当前方法，避免后续重复处理
            if self.crop_item and item_at_pos != self.crop_item: # 如果当前有项目正在裁剪状态，且点击的项目不是当前裁剪项目
                self.cancel_crop_mode() # 取消当前裁剪项目的裁剪状态
            elif self.crop_item and item_at_pos == self.crop_item: # 如果当前有项目正在裁剪状态，且点击的项目是当前裁剪项目
                super().mousePressEvent(event) # 调用父类的鼠标按下事件处理方法，确保正常裁剪操作
                return # 结束当前方法，避免后续重复处理
            if item_at_pos: # 如果点击的项目存在
                self.active_mode = self.MOVE_MODE # 切换到移动模式
            elif self.items(): # 如果场景中存在其他项目
                self.active_mode = self.RUBBERBAND_MODE # 切换到橡皮筋选择模式

        super().mousePressEvent(event)# 调用父类的鼠标按下事件处理方法，确保正常处理

    def mouseDoubleClickEvent(self, event):# 处理鼠标双击事件
        self.cancel_active_modes() # 取消所有活动模式，确保没有正在进行的操作干扰
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) # 获取当前鼠标位置上的项目
        if item: # 如果点击的项目存在
            if not item.isSelected(): # 如果项目未被选择
                item.setSelected(True) # 选择该项目
            if item.is_editable: # 如果项目可编辑
                item.enter_edit_mode() # 进入编辑模式
                self.mousePressEvent(event) # 模拟鼠标按下事件，确保编辑模式正常启动
            else: # 如果项目不可编辑
                self.views()[0].fit_rect(
                    self.itemsBoundingRect(items=[item]),
                    toggle_item=item) # 调整场景视图，确保点击的项目在可见区域
            return
        super().mouseDoubleClickEvent(event) # 调用父类的鼠标双击事件处理方法，确保正常处理

    def mouseMoveEvent(self, event): # 处理鼠标移动事件
        if self.active_mode == self.RUBBERBAND_MODE: # 如果当前模式是橡皮筋选择模式
            if not self.rubberband_item.scene(): # 如果橡皮筋选择项目不在场景中
                logger.debug('Activating rubberband selection') # 记录调试信息，激活橡皮筋选择模式
                self.addItem(self.rubberband_item) # 将橡皮筋选择项目添加到场景中
                self.rubberband_item.bring_to_front() # 将橡皮筋选择项目 bring to front，确保可见
            self.rubberband_item.fit(self.event_start, event.scenePos()) # 调整橡皮筋选择项目的形状，以适应鼠标移动
            self.setSelectionArea(self.rubberband_item.shape()) # 设置场景的选择区域为橡皮筋选择项目的形状
            self.views()[0].reset_previous_transform() # 重置场景视图的前一个变换，确保正常显示
        super().mouseMoveEvent(event) # 调用父类的鼠标移动事件处理方法，确保正常处理

    def mouseReleaseEvent(self, event): # 处理鼠标释放事件
        if self.active_mode == self.RUBBERBAND_MODE: # 如果当前模式是橡皮筋选择模式
            self.end_rubberband_mode() # 结束橡皮筋选择模式
        if (self.active_mode == self.MOVE_MODE # 如果当前模式是移动模式
                and self.has_selection() # 如果场景中存在选择项目
                and self.multi_select_item.active_mode is None # 如果多选项目的活动模式为空
                and self.selectedItems()[0].active_mode is None): # 如果选择项目的活动模式为空
            delta = event.scenePos() - self.event_start # 计算鼠标移动的距离
            if not delta.isNull(): # 如果鼠标移动距离不为零
                self.undo_stack.push(
                    commands.MoveItemsBy(self.selectedItems(),
                                         delta,
                                         ignore_first_redo=True)) # 记录移动操作到撤销栈，忽略第一次重做
        self.active_mode = None # 切换到无活动模式
        super().mouseReleaseEvent(event) # 调用父类的鼠标释放事件处理方法，确保正常处理

    def selectedItems(self, user_only=False): # 返回场景中当前选择的项目
        """If ``user_only`` is set to ``True``, only return items added
        by the user (i.e. no multi select outlines and other UI items).

        User items are items that have a ``save_id`` attribute.
        """

        items = super().selectedItems() # 获取场景中当前选择的所有项目
        if user_only:
            return list(filter(lambda i: hasattr(i, 'save_id'), items)) # 如果只返回用户项目，过滤掉没有 save_id 属性的项目
        return items # 返回所有选择项目

    def items_by_type(self, itype): # 返回场景中所有指定类型的项目
        """Returns all items of the given type."""

        return filter(lambda i: getattr(i, 'TYPE', None) == itype,
                      self.items()) # 返回所有类型为 itype 的项目

    def items_for_save(self): # 返回场景中所有可保存的项目
        """Returns the items that are to be saved.

        Items to be saved are items that have a save_id attribute.
        """

        return filter(lambda i: hasattr(i, 'save_id'),
                      self.items(order=Qt.SortOrder.AscendingOrder)) # 返回所有有 save_id 属性的项目

    def clear_save_ids(self): # 清除场景中所有项目的 save_id 属性
        for item in self.items_for_save():# 遍历所有可保存项目
            item.save_id = None # 清除项目的 save_id 属性

    def on_view_scale_change(self): # 处理场景视图缩放变化事件
        for item in self.selectedItems(): # 遍历当前选择的项目
            item.on_view_scale_change() # 调用项目的视图缩放变化处理方法，确保正常显示

    def itemsBoundingRect(self, selection_only=False, items=None): # 返回场景中项目的边界矩形
        """Returns the bounding rect of the scene's items; either all of them
        or only selected ones, or the items givin in ``items``.

        Re-implemented to not include the items's selection handles.
        """

        def filter_user_items(ilist):# 过滤出场景中所有用户项目（有 save_id 属性的项目）
            return list(filter(lambda i: hasattr(i, 'save_id'), ilist)) # 过滤出场景中所有用户项目（有 save_id 属性的项目）



        if selection_only: # 如果只返回选择项目的边界矩形
            base = filter_user_items(self.selectedItems()) # 过滤出当前选择的用户项目
        elif items: # 如果指定了项目列表
            base = items # 使用指定的项目列表
        else: # 如果没有指定项目列表
            base = filter_user_items(self.items()) # 过滤出所有用户项目

        if not base: # 如果没有项目可计算边界矩形
            return QtCore.QRectF(0, 0, 0, 0) # 返回空矩形

        x = [] # 存储所有项目的 x 坐标
        y = [] # 存储所有项目的 y 坐标

        for item in base: # 遍历所有项目
            for corner in item.corners_scene_coords: # 遍历项目的所有场景坐标
                x.append(corner.x()) # 存储项目的 x 坐标
                y.append(corner.y()) # 存储项目的 y 坐标

        return QtCore.QRectF(
            QtCore.QPointF(min(x), min(y)),  # 计算所有项目的最小坐标点
            QtCore.QPointF(max(x), max(y))) # 计算所有项目的最大坐标点

    def get_selection_center(self): # 返回场景中当前选择项目的中心坐标
        rect = self.itemsBoundingRect(selection_only=True) # 获取当前选择项目的边界矩形
        return (rect.topLeft() + rect.bottomRight()) / 2 # 返回矩形的中心坐标

    def on_selection_change(self): # 处理场景选择变化事件
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if self.has_multi_selection():# 如果有多个项目被选择
            self.multi_select_item.fit_selection_area( 
                self.itemsBoundingRect(selection_only=True)) # 调整多选框的大小以适应选择项目的边界矩形
        if self.has_multi_selection() and not self.multi_select_item.scene(): # 如果有多个项目被选择且多选框不在场景中
            self.addItem(self.multi_select_item) # 将多选框添加到场景中
            self.multi_select_item.bring_to_front() # 将多选框 bring_to_front 到最前面
        if not self.has_multi_selection() and self.multi_select_item.scene(): # 如果没有项目被选择且多选框在场景中
            self.removeItem(self.multi_select_item) # 从场景中移除多选框

    def on_change(self, region): # 处理场景变化事件
        if self._clear_ongoing: # 如果场景正在清除中
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if (self.multi_select_item.scene() # 如果多选框在场景中
                and self.multi_select_item.active_mode is None): # 且多选框未激活任何模式
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True)) # 调整多选框的大小以适应选择项目的边界矩形

    def add_item_later(self, itemdata, selected=False): # 保持一个项目稍后添加，通过 ``add_queued_items`` 添加
        """Keep an item for adding later via ``add_queued_items``

        :param dict itemdata: Defines the item's data
        :param bool selected: Whether the item is initialised as selected
        """

        self.items_to_add.put((itemdata, selected)) # 将项目数据和选择状态添加到稍后添加队列中

    def add_queued_items(self): # 添加稍后添加队列中的项目
        """Adds items added via ``add_item_later``"""

        while not self.items_to_add.empty(): # 循环直到稍后添加队列为空
            data, selected = self.items_to_add.get() # 从稍后添加队列中获取项目数据和选择状态
            typ = data.pop('type') # 从项目数据中弹出项目类型
            cls = item_registry.get(typ) # 从项目类型中获取项目类
            if not cls: # 如果项目类型未知
                # Just in case we add new item types in future versions
                logger.warning(f'Encountered item of unknown type: {typ}') # 记录警告日志，提示未知项目类型
                cls = BeeErrorItem # 默认使用 BeeErrorItem 类
                data['data'] = {'text': f'Item of unknown type: {typ}'}  # 为未知项目类型添加默认文本数据
            item = cls.create_from_data(**data)  # 创建项目实例
            # Set the values common to all item types:
            item.update_from_data(**data)  # 更新项目实例的属性值
            self.addItem(item) # 将项目实例添加到场景中
            # Force recalculation of min/max z values:
            item.setZValue(item.zValue()) # 强制重新计算项目实例的 z 值
            if selected:
                item.setSelected(True) # 设置项目实例为选中状态
                item.bring_to_front() # 将项目实例 bring_to_front 到最前面
