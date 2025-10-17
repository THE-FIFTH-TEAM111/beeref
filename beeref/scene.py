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
        center = self.get_selection_center()
        bounds = rpack.bbox_size(sizes, positions)
        diff = center - QtCore.QPointF(bounds[0]/2, bounds[1]/2)
        positions = [QtCore.QPointF(*pos) + diff for pos in positions]

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def arrange_square(self):
        self.cancel_active_modes()
        max_width = 0
        max_height = 0
        gap = self.settings.valueOrDefault('Items/arrange_gap')
        items = sort_by_filename(self.selectedItems(user_only=True))

        if len(items) < 2:
            return

        for item in items:
            rect = self.itemsBoundingRect(items=[item])
            max_width = max(max_width, rect.width() + gap)
            max_height = max(max_height, rect.height() + gap)

        # We want the items to center around the selection's center,
        # not (0, 0)
        num_rows = math.ceil(math.sqrt(len(items)))
        center = self.get_selection_center()
        diff = center - num_rows/2 * QtCore.QPointF(max_width, max_height)

        iter_items = iter(items)
        positions = []
        for j in range(num_rows):
            for i in range(num_rows):
                try:
                    item = next(iter_items)
                    rect = self.itemsBoundingRect(items=[item])
                    point = QtCore.QPointF(
                        i * max_width + (max_width - rect.width())/2,
                        j * max_height + (max_height - rect.height())/2)
                    positions.append(point + diff)
                except StopIteration:
                    break

        self.undo_stack.push(commands.ArrangeItems(self, items, positions))

    def flip_items(self, vertical=False):
        """Flip selected items."""
        self.cancel_active_modes()
        self.undo_stack.push(
            commands.FlipItems(self.selectedItems(user_only=True),
                               self.get_selection_center(),
                               vertical=vertical))

    def crop_items(self):
        """Crop selected item."""

        if self.crop_item:
            return
        if self.has_single_image_selection():
            item = self.selectedItems(user_only=True)[0]
            if item.is_image:
                item.enter_crop_mode()

    def sample_color_at(self, position):
        item_at_pos = self.itemAt(position, self.views()[0].transform())
        if item_at_pos:
            return item_at_pos.sample_color_at(position)

    def select_all_items(self):
        self.cancel_active_modes()
        path = QtGui.QPainterPath()
        path.addRect(self.itemsBoundingRect())
        # This is faster than looping through all items and calling setSelected
        self.setSelectionArea(path)

    def deselect_all_items(self):
        self.cancel_active_modes()
        self.clearSelection()

    def has_selection(self):
        """Checks whether there are currently items selected."""

        return bool(self.selectedItems(user_only=True))

    def has_single_selection(self):
        """Checks whether there's currently exactly one item selected."""

        return len(self.selectedItems(user_only=True)) == 1

    def has_multi_selection(self):
        """Checks whether there are currently more than one items selected."""

        return len(self.selectedItems(user_only=True)) > 1

    def has_single_image_selection(self):
        """Checks whether the current selection is a single image."""

        if self.has_single_selection():
            return self.selectedItems(user_only=True)[0].is_image
        return False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click invokes the context menu on the
            # GraphicsView. We don't need it here.
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.event_start = event.scenePos()
            item_at_pos = self.itemAt(
                event.scenePos(), self.views()[0].transform())

            if self.edit_item:
                if item_at_pos != self.edit_item:
                    self.edit_item.exit_edit_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if self.crop_item:
                if item_at_pos != self.crop_item:
                    self.cancel_crop_mode()
                else:
                    super().mousePressEvent(event)
                    return
            if item_at_pos:
                self.active_mode = self.MOVE_MODE
            elif self.items():
                self.active_mode = self.RUBBERBAND_MODE

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.cancel_active_modes()
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if item:
            if not item.isSelected():
                item.setSelected(True)
            if item.is_editable:
                item.enter_edit_mode()
                self.mousePressEvent(event)
            else:
                self.views()[0].fit_rect(
                    self.itemsBoundingRect(items=[item]),
                    toggle_item=item)
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            if not self.rubberband_item.scene():
                logger.debug('Activating rubberband selection')
                self.addItem(self.rubberband_item)
                self.rubberband_item.bring_to_front()
            self.rubberband_item.fit(self.event_start, event.scenePos())
            self.setSelectionArea(self.rubberband_item.shape())
            self.views()[0].reset_previous_transform()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.active_mode == self.RUBBERBAND_MODE:
            self.end_rubberband_mode()
        if (self.active_mode == self.MOVE_MODE
                and self.has_selection()
                and self.multi_select_item.active_mode is None
                and self.selectedItems()[0].active_mode is None):
            delta = event.scenePos() - self.event_start
            if not delta.isNull():
                self.undo_stack.push(
                    commands.MoveItemsBy(self.selectedItems(),
                                         delta,
                                         ignore_first_redo=True))
        self.active_mode = None
        super().mouseReleaseEvent(event)

    def selectedItems(self, user_only=False):
        """If ``user_only`` is set to ``True``, only return items added
        by the user (i.e. no multi select outlines and other UI items).

        User items are items that have a ``save_id`` attribute.
        """

        items = super().selectedItems()
        if user_only:
            return list(filter(lambda i: hasattr(i, 'save_id'), items))
        return items

    def items_by_type(self, itype):
        """Returns all items of the given type."""

        return filter(lambda i: getattr(i, 'TYPE', None) == itype,
                      self.items())

    def items_for_save(self):

        """Returns the items that are to be saved.

        Items to be saved are items that have a save_id attribute.
        """

        return filter(lambda i: hasattr(i, 'save_id'),
                      self.items(order=Qt.SortOrder.AscendingOrder))

    def clear_save_ids(self):
        for item in self.items_for_save():
            item.save_id = None

    def on_view_scale_change(self):
        for item in self.selectedItems():
            item.on_view_scale_change()

    def itemsBoundingRect(self, selection_only=False, items=None):
        """Returns the bounding rect of the scene's items; either all of them
        or only selected ones, or the items givin in ``items``.

        Re-implemented to not include the items's selection handles.
        """

        def filter_user_items(ilist):
            return list(filter(lambda i: hasattr(i, 'save_id'), ilist))

        if selection_only:
            base = filter_user_items(self.selectedItems())
        elif items:
            base = items
        else:
            base = filter_user_items(self.items())

        if not base:
            return QtCore.QRectF(0, 0, 0, 0)

        x = []
        y = []

        for item in base:
            for corner in item.corners_scene_coords:
                x.append(corner.x())
                y.append(corner.y())

        return QtCore.QRectF(
            QtCore.QPointF(min(x), min(y)),
            QtCore.QPointF(max(x), max(y)))

    def get_selection_center(self):
        rect = self.itemsBoundingRect(selection_only=True)
        return (rect.topLeft() + rect.bottomRight()) / 2

    def on_selection_change(self):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if self.has_multi_selection():
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))
        if self.has_multi_selection() and not self.multi_select_item.scene():
            self.addItem(self.multi_select_item)
            self.multi_select_item.bring_to_front()
        if not self.has_multi_selection() and self.multi_select_item.scene():
            self.removeItem(self.multi_select_item)

    def on_change(self, region):
        if self._clear_ongoing:
            # Ignore events while clearing the scene since the
            # multiselect item will get cleared, too
            return
        if (self.multi_select_item.scene()
                and self.multi_select_item.active_mode is None):
            self.multi_select_item.fit_selection_area(
                self.itemsBoundingRect(selection_only=True))

    def add_item_later(self, itemdata, selected=False):
        """Keep an item for adding later via ``add_queued_items``

        :param dict itemdata: Defines the item's data
        :param bool selected: Whether the item is initialised as selected
        """

        self.items_to_add.put((itemdata, selected))

    def add_queued_items(self):
        """Adds items added via ``add_item_later``"""

        while not self.items_to_add.empty():
            data, selected = self.items_to_add.get()
            typ = data.pop('type')
            cls = item_registry.get(typ)
            if not cls:
                # Just in case we add new item types in future versions
                logger.warning(f'Encountered item of unknown type: {typ}')
                cls = BeeErrorItem
                data['data'] = {'text': f'Item of unknown type: {typ}'}
            item = cls.create_from_data(**data)
            # Set the values common to all item types:
            item.update_from_data(**data)
            self.addItem(item)
            # Force recalculation of min/max z values:
            item.setZValue(item.zValue())
            if selected:
                item.setSelected(True)
                item.bring_to_front()