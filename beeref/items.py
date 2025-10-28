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

"""Classes for items that are added to the scene by the user (images,
text).
"""

from collections import defaultdict # 导入collections模块中的defaultdict类，用于创建默认值的字典
from functools import cached_property # 导入functools模块中的cached_property类，用于缓存属性的计算结果
import logging # 导入logging模块，用于记录日志
import os.path # 导入os.path模块，用于处理文件路径

from PyQt6 import QtCore, QtGui, QtWidgets # 导入PyQt6模块中的QtCore、QtGui、QtWidgets类，用于处理Qt的核心功能、图形界面和小部件
from PyQt6.QtCore import Qt # 导入PyQt6.QtCore模块中的Qt类，用于处理Qt的核心功能

from beeref import commands # 导入beeref模块中的commands类，用于处理用户命令
from beeref.config import BeeSettings # 导入beeref模块中的BeeSettings类，用于处理应用程序的配置
from beeref.constants import COLORS # 导入beeref模块中的COLORS常量，用于定义颜色
from beeref.selection import SelectableMixin # 导入beeref模块中的SelectableMixin类，用于处理可选择的项


logger = logging.getLogger(__name__) # 创建一个日志记录器，用于记录当前模块的日志信息

item_registry = {} # 创建一个空字典，用于存储注册的项类型和对应的类


def register_item(cls): # 定义一个函数，用于注册项类型和对应的类
    item_registry[cls.TYPE] = cls # 将项类型作为键，对应的类作为值，存储到item_registry字典中
    return cls # 返回注册的类，用于支持链式调用


def sort_by_filename(items): # 定义一个函数，用于根据文件名对项进行排序
    """Order items by filename.

    Items with a filename (ordered by filename) first, then items
    without a filename but with a save_id follow (ordered by
    save_id), then remaining items in the order that they have
    been inserted into the scene.
    """

    items_by_filename = [] # 创建一个空列表，用于存储有文件名的项
    items_by_save_id = [] # 创建一个空列表，用于存储有save_id的项
    items_remaining = [] # 创建一个空列表，用于存储剩余的项

    for item in items: # 遍历所有项
        if getattr(item, 'filename', None): # 如果项有文件名属性
            items_by_filename.append(item) # 将项添加到有文件名的项列表中
        elif getattr(item, 'save_id', None): # 如果项有save_id属性
            items_by_save_id.append(item) # 将项添加到有save_id的项列表中
        else:
            items_remaining.append(item) # 将项添加到剩余的项列表中

    items_by_filename.sort(key=lambda x: x.filename) # 对有文件名的项列表进行排序，根据文件名属性进行排序
    items_by_save_id.sort(key=lambda x: x.save_id) # 对有save_id的项列表进行排序，根据save_id属性进行排序
    return items_by_filename + items_by_save_id + items_remaining # 返回排序后的项列表，先有文件名的项，然后有save_id的项，最后是剩余的项


class BeeItemMixin(SelectableMixin): # 定义一个基类，用于所有用户添加的项
    """Base for all items added by the user."""

    def set_pos_center(self, pos): # 定义一个方法，用于设置项的位置，使用项的中心作为原点
        """Sets the position using the item's center as the origin point."""

        self.setPos(pos - self.center_scene_coords) # 将项的位置设置为传入的位置减去项的中心场景坐标

    def has_selection_outline(self):
        return self.isSelected() # 返回项是否被选中

    def has_selection_handles(self): # 定义一个方法，用于判断项是否有选择句柄
        return (self.isSelected() # 返回项是否被选中
                and self.scene() # 返回项所属的场景
                and self.scene().has_single_selection()) # 返回场景是否只有一个项被选中

    def selection_action_items(self): # 定义一个方法，用于返回项受选择操作影响的项列表
        """The items affected by selection actions like scaling and rotating.
        """
        return [self] # 返回项受选择操作影响的项列表，这里只有项本身

    def on_selected_change(self, value): # 定义一个方法，用于处理项的选中状态变化
        if (value and self.scene() # 如果项被选中，并且项所属的场景存在
                and not self.scene().has_selection() # 场景没有其他项被选中
                and not self.scene().active_mode is None): # 场景没有活动模式
            self.bring_to_front() # 将项 bring to front

    def update_from_data(self, **kwargs): # 定义一个方法，用于从数据更新项的属性
        self.save_id = kwargs.get('save_id', self.save_id) # 更新项的save_id属性，使用传入的save_id值或当前值
        self.setPos(kwargs.get('x', self.pos().x()), 
                    kwargs.get('y', self.pos().y())) # 更新项的位置属性，使用传入的x、y值或当前值
        self.setZValue(kwargs.get('z', self.zValue())) # 更新项的z值属性，使用传入的z值或当前值
        self.setScale(kwargs.get('scale', self.scale())) # 更新项的缩放属性，使用传入的scale值或当前值
        self.setRotation(kwargs.get('rotation', self.rotation())) # 更新项的旋转属性，使用传入的rotation值或当前值
        if kwargs.get('flip', 1) != self.flip(): # 如果传入的flip值与当前值不同
            self.do_flip() # 执行项的翻转操作


@register_item
class BeePixmapItem(BeeItemMixin, QtWidgets.QGraphicsPixmapItem): # 定义一个类，用于表示用户添加的图像项
    """Class for images added by the user."""

    TYPE = 'pixmap' # 定义项的类型为'pixmap'
    CROP_HANDLE_SIZE = 15 # 定义项的裁剪句柄大小为15

    def __init__(self, image, filename=None, **kwargs): # 定义类的初始化方法，用于创建图像项
        super().__init__(QtGui.QPixmap.fromImage(image)) # 调用父类的初始化方法，传入图像项的QPixmap对象
        self.save_id = None # 初始化项的save_id属性为None
        self.filename = filename # 初始化项的filename属性为传入的filename值
        self.reset_crop() # 调用项的reset_crop方法，重置项的裁剪区域
        logger.debug(f'Initialized {self}') # 记录项的初始化信息
        self.is_image = True # 初始化项的is_image属性为True
        self.crop_mode = False # 初始化项的crop_mode属性为False
        self.init_selectable() # 调用项的init_selectable方法，初始化项的选择状态
        self.settings = BeeSettings() # 初始化项的settings属性为BeeSettings()对象
        self.grayscale = False # 初始化项的grayscale属性为False

    @classmethod
    def create_from_data(self, **kwargs): # 定义一个类方法，用于从数据创建图像项
        item = kwargs.pop('item') # 从kwargs中弹出项对象，赋值给item变量
        data = kwargs.pop('data', {}) # 从kwargs中弹出数据字典，赋值给data变量，默认值为空字典
        item.filename = item.filename or data.get('filename') # 如果项的filename属性为None，或者数据字典中没有'filename'键，将项的filename属性设置为数据字典中的'filename'值
        if 'crop' in data: # 如果数据字典中包含'crop'键
            item.crop = QtCore.QRectF(*data['crop']) # 将项的crop属性设置为数据字典中'crop'键对应的值，使用QRectF对象表示裁剪区域
        item.setOpacity(data.get('opacity', 1)) # 将项的不透明度属性设置为数据字典中'opacity'键对应的值，默认值为1
        item.grayscale = data.get('grayscale', False) # 将项的grayscale属性设置为数据字典中'grayscale'键对应的值，默认值为False
        return item # 返回创建的项对象

    def __str__(self): # 定义项的字符串表示方法
        size = self.pixmap().size() # 获取项的QPixmap对象的大小
        return (f'Image "{self.filename}" {size.width()} x {size.height()}') # 返回项的字符串表示，包含文件名和图像大小

    @property
    def crop(self): # 定义项的裁剪区域属性的getter方法
        return self._crop # 返回项的裁剪区域属性值

    @crop.setter
    def crop(self, value): # 定义项的裁剪区域属性的setter方法 
        logger.debug(f'Setting crop for {self} to {value}') # 记录项的裁剪区域属性设置信息
        self.prepareGeometryChange() # 准备项的几何变化，通知场景项的位置、大小或旋转等属性已改变
        self._crop = value # 更新项的裁剪区域属性值为传入的value值
        self.update() # 更新项的显示，触发项的重绘操作

    @property
    def grayscale(self): # 定义项的灰度属性的getter方法
        return self._grayscale # 返回项的灰度属性值

    @grayscale.setter
    def grayscale(self, value): # 定义项的灰度属性的setter方法
        logger.debug('Setting grayscale for {self} to {value}') # 记录项的灰度属性设置信息
        self._grayscale = value # 更新项的灰度属性值为传入的value值
        if value is True:
            # Using the grayscale image format to convert to grayscale
            # loses an image's tranparency. So the straightworward
            # following method gives us an ugly black replacement:
            # img = img.convertToFormat(QtGui.QImage.Format.Format_Grayscale8)

            # Instead, we will fill the background with the current
            # canvas colour, so the issue is only visible if the image
            # overlaps other images. The way we do it here only works
            # as long as the canvas colour is itself grayscale,
            # though.
            img = QtGui.QImage( # 创建一个QImage对象，用于存储转换后的灰度图像
                self.pixmap().size(), QtGui.QImage.Format.Format_Grayscale8)
            img.fill(QtGui.QColor(*COLORS['Scene:Canvas'])) # 用当前场景的画布颜色填充图像的背景
            painter = QtGui.QPainter(img) # 创建一个QPainter对象，用于绘制图像
            painter.drawPixmap(0, 0, self.pixmap()) # 绘制项的QPixmap对象到图像上
            painter.end() # 结束绘制操作
            self._grayscale_pixmap = QtGui.QPixmap.fromImage(img)

            # Alternative methods that have their own issues:
            #
            # 1. Use setAlphaChannel of the resulting grayscale
            # image. How do we get the original alpha channel? Using
            # the whole original image also takes color values into
            # account, not just their alpha values.
            #
            # 2. QtWidgets.QGraphicsColorizeEffect() with black colour
            # on the GraphicsItem. This applys to everything the paint
            # method does, so the selection outline/handles will also
            # be gray. setGraphicsEffect is only available on some
            # widgets, so we can't apply it selectively.
            #
            # 3. Going through every pixel and doing it manually — bad
            # performance.
        else: # 如果灰度属性为False
            self._grayscale_pixmap = None # 将项的灰度Pixmap属性设置为None

        self.update() # 更新项的显示，触发项的重绘操作

    def sample_color_at(self, pos): # 定义项的采样颜色方法，用于获取项在指定位置的颜色值
        ipos = self.mapFromScene(pos) # 将场景坐标转换为项坐标
        if self.grayscale: # 如果项的灰度属性为True
            pm = self._grayscale_pixmap # 将项的灰度Pixmap赋值给pm变量
        else: # 如果项的灰度属性为False
            pm = self.pixmap() # 将项的QPixmap对象赋值给pm变量
        img = pm.toImage() # 将项的Pixmap对象转换为QImage对象

        color = img.pixelColor(int(ipos.x()), int(ipos.y())) # 获取图像中指定位置的颜色值
        if color.alpha() > 0: # 如果颜色的alpha值大于0，即颜色不是完全透明的
            return color # 返回颜色值

    def bounding_rect_unselected(self):
        if self.crop_mode:
            return QtWidgets.QGraphicsPixmapItem.boundingRect(self)
        else:
            return self.crop

    def get_extra_save_data(self):
        return {'filename': self.filename,
                'opacity': self.opacity(),
                'grayscale': self.grayscale,
                'crop': [self.crop.topLeft().x(),
                         self.crop.topLeft().y(),
                         self.crop.width(),
                         self.crop.height()]}

    def get_filename_for_export(self, imgformat, save_id_default=None):
        save_id = self.save_id or save_id_default
        assert save_id is not None

        if self.filename:
            basename = os.path.splitext(os.path.basename(self.filename))[0]
            return f'{save_id:04}-{basename}.{imgformat}'
        else:
            return f'{save_id:04}.{imgformat}'

    def get_imgformat(self, img):
        """Determines the format for storing this image."""

        formt = self.settings.valueOrDefault('Items/image_storage_format')

        if formt == 'best':
            # Images with alpha channel and small images are stored as png
            if (img.hasAlphaChannel()
                    or (img.height() < 500 and img.width() < 500)):
                formt = 'png'
            else:
                formt = 'jpg'

        logger.debug(f'Found format {formt} for {self}')
        return formt

    def pixmap_to_bytes(self, apply_grayscale=False, apply_crop=False):
        """Convert the pixmap data to PNG bytestring."""
        barray = QtCore.QByteArray()
        buffer = QtCore.QBuffer(barray)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        if apply_grayscale and self.grayscale:
            pm = self._grayscale_pixmap
        else:
            pm = self.pixmap()

        if apply_crop:
            pm = pm.copy(self.crop.toRect())

        img = pm.toImage()
        imgformat = self.get_imgformat(img)
        img.save(buffer, imgformat.upper(), quality=90)
        return (barray.data(), imgformat)

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        self.reset_crop()

    def pixmap_from_bytes(self, data):
        """Set image pimap from a bytestring."""
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(data)
        self.setPixmap(pixmap)

    def create_copy(self):
        item = BeePixmapItem(QtGui.QImage(), self.filename)
        item.setPixmap(self.pixmap())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        item.setOpacity(self.opacity())
        item.grayscale = self.grayscale
        if self.flip() == -1:
            item.do_flip()
        item.crop = self.crop
        return item

    @cached_property
    def color_gamut(self):
        logger.debug(f'Calculating color gamut for {self}')
        gamut = defaultdict(int)
        img = self.pixmap().toImage()
        # Don't evaluate every pixel for larger images:
        step = max(1, int(max(img.width(), img.height()) / 1000))
        logger.debug(f'Considering every {step}. row/column')

        # Not actually faster than solution below :(
        # ptr = img.bits()
        # size = img.sizeInBytes()
        # pixelsize = int(img.sizeInBytes() / img.width() / img.height())
        # ptr.setsize(size)
        # for pixel in batched(ptr, n=pixelsize):
        #     r, g, b, alpha = tuple(map(ord, pixel))
        #     if 5 < alpha and 5 < r < 250 and 5 < g < 250 and 5 < b < 250:
        #         # Only consider pixels that aren't close to
        #         # transparent, white or black
        #         rgb = QtGui.QColor(r, g, b)
        #         gamut[rgb.hue(), rgb.saturation()] += 1

        for i in range(0, img.width(), step):
            for j in range(0, img.height(), step):
                rgb = img.pixelColor(i, j)
                rgbtuple = (rgb.red(), rgb.blue(), rgb.green())
                if (5 < rgb.alpha()
                        and min(rgbtuple) < 250 and max(rgbtuple) > 5):
                    # Only consider pixels that aren't close to
                    # transparent, white or black
                    gamut[rgb.hue(), rgb.saturation()] += 1

        logger.debug(f'Got {len(gamut)} color gamut values')
        return gamut

    def copy_to_clipboard(self, clipboard):
        clipboard.setPixmap(self.pixmap())

    def reset_crop(self):
        self.crop = QtCore.QRectF(
            0, 0, self.pixmap().size().width(), self.pixmap().size().height())

    @property
    def crop_handle_size(self):
        return self.fixed_length_for_viewport(self.CROP_HANDLE_SIZE)

    def crop_handle_topleft(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomleft(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x(),
            bottomleft.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomright(self):
        bottomright = self.crop_temp.bottomRight()
        return QtCore.QRectF(
            bottomright.x() - self.crop_handle_size,
            bottomright.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_topright(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handles(self):
        return (self.crop_handle_topleft,
                self.crop_handle_bottomleft,
                self.crop_handle_bottomright,
                self.crop_handle_topright)

    def crop_edge_top(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x() + self.crop_handle_size,
            topleft.y(),
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_left(self):
        topleft = self.crop_temp.topLeft()
        return QtCore.QRectF(
            topleft.x(),
            topleft.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edge_bottom(self):
        bottomleft = self.crop_temp.bottomLeft()
        return QtCore.QRectF(
            bottomleft.x() + self.crop_handle_size,
            bottomleft.y() - self.crop_handle_size,
            self.crop_temp.width() - 2 * self.crop_handle_size,
            self.crop_handle_size)

    def crop_edge_right(self):
        topright = self.crop_temp.topRight()
        return QtCore.QRectF(
            topright.x() - self.crop_handle_size,
            topright.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edges(self):
        return (self.crop_edge_top,
                self.crop_edge_left,
                self.crop_edge_bottom,
                self.crop_edge_right)

    def get_crop_handle_cursor(self, handle):
        """Gets the crop cursor for the given handle."""

        is_topleft_or_bottomright = handle in (
            self.crop_handle_topleft, self.crop_handle_bottomright)
        return self.get_diag_cursor(is_topleft_or_bottomright)

    def get_crop_edge_cursor(self, edge):
        """Gets the crop edge cursor for the given edge."""

        top_or_bottom = edge in (
            self.crop_edge_top, self.crop_edge_bottom)
        sideways = (45 < self.rotation() < 135
                    or 225 < self.rotation() < 315)

        if top_or_bottom is sideways:
            return Qt.CursorShape.SizeHorCursor
        else:
            return Qt.CursorShape.SizeVerCursor

    def draw_crop_rect(self, painter, rect):
        """Paint a dotted rectangle for the cropping UI."""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        pen.setWidth(2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)
        pen.setColor(QtGui.QColor(0, 0, 0))
        pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def paint(self, painter, option, widget):
        if abs(painter.combinedTransform().m11()) < 2:
            # We want image smoothing, but only for images where we
            # are not zoomed in a lot. This is to ensure that for
            # example icons and pixel sprites can be viewed correctly.
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform)

        if self.crop_mode:
            self.paint_debug(painter, option, widget)

            # Darken image outside of cropped area
            painter.drawPixmap(0, 0, self.pixmap())
            path = QtWidgets.QGraphicsPixmapItem.shape(self)
            path.addRect(self.crop_temp)
            color = QtGui.QColor(0, 0, 0)
            color.setAlpha(100)
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawPath(path)
            painter.setBrush(QtGui.QBrush())

            for handle in self.crop_handles():
                self.draw_crop_rect(painter, handle())
            self.draw_crop_rect(painter, self.crop_temp)
        else:
            pm = self._grayscale_pixmap if self.grayscale else self.pixmap()
            painter.drawPixmap(self.crop, pm, self.crop)
            self.paint_selectable(painter, option, widget)

    def enter_crop_mode(self):
        logger.debug(f'Entering crop mode on {self}')
        self.prepareGeometryChange()
        self.crop_mode = True
        self.crop_temp = QtCore.QRectF(self.crop)
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.grabKeyboard()
        self.update()
        self.scene().crop_item = self

    def exit_crop_mode(self, confirm):
        logger.debug(f'Exiting crop mode with {confirm} on {self}')
        if confirm and self.crop != self.crop_temp:
            self.scene().undo_stack.push(
                commands.CropItem(self, self.crop_temp))
        self.prepareGeometryChange()
        self.crop_mode = False
        self.crop_temp = None
        self.crop_mode_move = None
        self.crop_mode_event_start = None
        self.ungrabKeyboard()
        self.update()
        self.scene().crop_item = None

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_crop_mode(confirm=True)
        elif event.key() == Qt.Key.Key_Escape:
            self.exit_crop_mode(confirm=False)
        else:
            super().keyPressEvent(event)

    def hoverMoveEvent(self, event):
        if not self.crop_mode:
            return super().hoverMoveEvent(event)

        for handle in self.crop_handles():
            if handle().contains(event.pos()):
                self.set_cursor(self.get_crop_handle_cursor(handle))
                return
        for edge in self.crop_edges():
            if edge().contains(event.pos()):
                self.set_cursor(self.get_crop_edge_cursor(edge))
                return
        self.unset_cursor()

    def mousePressEvent(self, event):
        if not self.crop_mode:
            return super().mousePressEvent(event)

        event.accept()
        for handle in self.crop_handles():
            # Click into a handle?
            if handle().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = handle
                return
        for edge in self.crop_edges():
            # Click into an edge handle?
            if edge().contains(event.pos()):
                self.crop_mode_event_start = event.pos()
                self.crop_mode_move = edge
                return
        # Click not in handle, end cropping mode:
        self.exit_crop_mode(
            confirm=self.crop_temp.contains(event.pos()))

    def ensure_point_within_crop_bounds(self, point, handle):
        """Returns the point, or the nearest point within the pixmap."""

        if handle == self.crop_handle_topleft:
            topleft = QtCore.QPointF(0, 0)
            bottomright = self.crop_temp.bottomRight()
        if handle == self.crop_handle_bottomleft:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_handle_bottomright:
            topleft = self.crop_temp.topLeft()
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_handle_topright:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_top:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_bottom:
            topleft = QtCore.QPointF(0, self.crop_temp.top())
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_edge_left:
            topleft = QtCore.QPointF(0, 0)
            bottomright = QtCore.QPointF(
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_edge_right:
            topleft = QtCore.QPointF(self.crop_temp.left(), 0)
            bottomright = QtCore.QPointF(
                self.pixmap().size().width(), self.pixmap().size().height())

        point.setX(min(bottomright.x(), max(topleft.x(), point.x())))
        point.setY(min(bottomright.y(), max(topleft.y(), point.y())))

        return point

    def mouseMoveEvent(self, event):
        if self.crop_mode and self.crop_mode_event_start:
            diff = event.pos() - self.crop_mode_event_start
            if self.crop_mode_move == self.crop_handle_topleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTopLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomleft:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottomLeft(new)
            if self.crop_mode_move == self.crop_handle_bottomright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomRight() + diff, self.crop_mode_move)
                self.crop_temp.setBottomRight(new)
            if self.crop_mode_move == self.crop_handle_topright:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setTopRight(new)
            if self.crop_mode_move == self.crop_edge_top:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTop(new.y())
            if self.crop_mode_move == self.crop_edge_left:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setLeft(new.x())
            if self.crop_mode_move == self.crop_edge_bottom:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottom(new.y())
            if self.crop_mode_move == self.crop_edge_right:
                new = self.ensure_point_within_crop_bounds(
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setRight(new.x())
            self.update()
            self.crop_mode_event_start = event.pos()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.crop_mode:
            self.crop_mode_move = None
            self.crop_mode_event_start = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


@register_item
class BeeTextItem(BeeItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for text added by the user."""

    TYPE = 'text'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = True
        self.edit_mode = False
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Text "{txt}"')

    def get_extra_save_data(self):
        return {'text': self.toPlainText()}

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(0, 0, 0)
        color.setAlpha(40)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self))
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def create_copy(self):
        item = BeeTextItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        if self.flip() == -1:
            item.do_flip()
        return item

    def enter_edit_mode(self):
        logger.debug(f'Entering edit mode on {self}')
        self.edit_mode = True
        self.old_text = self.toPlainText()
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.scene().edit_item = self

    def exit_edit_mode(self, commit=True):
        logger.debug(f'Exiting edit mode on {self}')
        self.edit_mode = False
        # reset selection:
        self.setTextCursor(QtGui.QTextCursor(self.document()))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.scene().edit_item = None
        if commit:
            self.scene().undo_stack.push(
                commands.ChangeText(self, self.toPlainText(), self.old_text))
            if not self.toPlainText().strip():
                logger.debug('Removing empty text item')
                self.scene().undo_stack.push(
                    commands.DeleteItems(self.scene(), [self]))
        else:
            self.setPlainText(self.old_text)

    def has_selection_handles(self):
        return super().has_selection_handles() and not self.edit_mode

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode()
            event.accept()
            return
        if (event.key() == Qt.Key.Key_Escape
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode(commit=False)
            event.accept()
            return
        super().keyPressEvent(event)

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.toPlainText())


@register_item
class BeeErrorItem(BeeItemMixin, QtWidgets.QGraphicsTextItem):
    """Class for displaying error messages when an item can't be loaded
    from a bee file.

    This item will be displayed instead of the original item. It won't
    save to bee files. The original item will be preserved in the bee
    file, unless this item gets deleted by the user, or a new bee file
    is saved.
    """

    TYPE = 'error'

    def __init__(self, text=None, **kwargs):
        super().__init__(text or "Text")
        self.original_save_id = None
        logger.debug(f'Initialized {self}')
        self.is_image = False
        self.init_selectable()
        self.is_editable = False
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text']))

    @classmethod
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {})
        item = cls(**data)
        return item

    def __str__(self):
        txt = self.toPlainText()[:40]
        return (f'Error "{txt}"')

    def contains(self, point):
        return self.boundingRect().contains(point)

    def paint(self, painter, option, widget):
        painter.setPen(Qt.PenStyle.NoPen)
        color = QtGui.QColor(200, 0, 0)
        brush = QtGui.QBrush(color)
        painter.setBrush(brush)
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self))
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled
        super().paint(painter, option, widget)
        self.paint_selectable(painter, option, widget)

    def update_from_data(self, **kwargs):
        self.original_save_id = kwargs.get('save_id', self.original_save_id)
        self.setPos(kwargs.get('x', self.pos().x()),
                    kwargs.get('y', self.pos().y()))
        self.setZValue(kwargs.get('z', self.zValue()))
        self.setScale(kwargs.get('scale', self.scale()))
        self.setRotation(kwargs.get('rotation', self.rotation()))

    def create_copy(self):
        item = BeeErrorItem(self.toPlainText())
        item.setPos(self.pos())
        item.setZValue(self.zValue())
        item.setScale(self.scale())
        item.setRotation(self.rotation())
        return item

    def flip(self, *args, **kwargs):
        """Returns the flip value (1 or -1)"""
        # Never display error messages flipped
        return 1

    def do_flip(self, *args, **kwargs):
        """Flips the item."""
        # Never flip error messages
        pass

    def copy_to_clipboard(self, clipboard):
        clipboard.setText(self.toPlainText())
