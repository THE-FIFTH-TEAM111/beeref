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

    def bounding_rect_unselected(self): # 定义项的未选中状态下的边界矩形方法
        if self.crop_mode: # 如果项的裁剪模式为True
            return QtWidgets.QGraphicsPixmapItem.boundingRect(self) # 返回项的QPixmap对象的边界矩形
        else: # 如果项的裁剪模式为False
            return self.crop # 返回项的裁剪区域属性值

    def get_extra_save_data(self): # 定义项的额外保存数据方法，用于获取项的额外保存信息
        return {'filename': self.filename,
                'opacity': self.opacity(),
                'grayscale': self.grayscale,
                'crop': [self.crop.topLeft().x(),
                         self.crop.topLeft().y(),
                         self.crop.width(),
                         self.crop.height()]} # 返回项的裁剪区域属性值的列表，包含左上角的x、y坐标、宽度和高度

    def get_filename_for_export(self, imgformat, save_id_default=None): # 定义项的导出文件名方法，用于获取项导出时的文件名
        save_id = self.save_id or save_id_default # 如果项的保存ID为None，则使用默认值
        assert save_id is not None # 断言项的保存ID不为None

        if self.filename: # 如果项的文件名属性不为None
            basename = os.path.splitext(os.path.basename(self.filename))[0] # 从项的文件名属性中提取文件名部分，不包含扩展名
            return f'{save_id:04}-{basename}.{imgformat}' # 返回导出文件名，格式为"{save_id:04}-{basename}.{imgformat}"，其中save_id为项的保存ID，basename为项的文件名部分，imgformat为导出的图像格式
        else:
            return f'{save_id:04}.{imgformat}' # 返回导出文件名，格式为"{save_id:04}.{imgformat}"，其中save_id为项的保存ID，imgformat为导出的图像格式

    def get_imgformat(self, img): # 定义项的图像格式方法，用于根据图像属性确定存储格式
        """Determines the format for storing this image."""

        formt = self.settings.valueOrDefault('Items/image_storage_format') # 从项的设置中获取图像存储格式选项，默认值为'best'

        if formt == 'best': # 如果图像存储格式选项为'best'
            # Images with alpha channel and small images are stored as png
            if (img.hasAlphaChannel() # 如果图像有alpha通道
                    or (img.height() < 500 and img.width() < 500)): # 如果图像高度或宽度小于500像素
                formt = 'png' # 如果图像有alpha通道或高度或宽度小于500像素，则存储为png格式
            else:
                formt = 'jpg' # 如果图像没有alpha通道且高度和宽度都大于等于500像素，则存储为jpg格式

        logger.debug(f'Found format {formt} for {self}') # 记录调试信息，显示项的图像存储格式选项和项的文件名属性
        return formt # 返回项的图像存储格式选项

    def pixmap_to_bytes(self, apply_grayscale=False, apply_crop=False): # 定义项的Pixmap转换为字节字符串方法，用于将项的Pixmap数据转换为PNG格式的字节字符串
        """Convert the pixmap data to PNG bytestring."""
        barray = QtCore.QByteArray() # 创建一个空的QByteArray对象，用于存储转换后的字节字符串
        buffer = QtCore.QBuffer(barray) # 创建一个QBuffer对象，将barray作为参数传入，用于将Pixmap数据写入字节字符串
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly) # 以只写模式打开QBuffer对象，用于将Pixmap数据写入字节字符串
        if apply_grayscale and self.grayscale:
            pm = self._grayscale_pixmap # 如果应用灰度属性为True且项的灰度属性为True，则将项的灰度Pixmap赋值给pm变量
        else:
            pm = self.pixmap() # 如果应用灰度属性为False或项的灰度属性为False，则将项的QPixmap对象赋值给pm变量

        if apply_crop: # 如果应用裁剪属性为True
            pm = pm.copy(self.crop.toRect()) # 将项的Pixmap对象裁剪为指定区域，赋值给pm变量

        img = pm.toImage() # 将项的Pixmap对象转换为QImage对象
        imgformat = self.get_imgformat(img) # 根据图像属性确定存储格式
        img.save(buffer, imgformat.upper(), quality=90) # 将图像保存到QBuffer对象中，格式为PNG，质量为90
        return (barray.data(), imgformat) # 返回转换后的字节字符串和图像格式

    def setPixmap(self, pixmap): # 定义项的Pixmap设置方法，用于设置项的Pixmap对象
        super().setPixmap(pixmap) # 调用父类的setPixmap方法，将项的Pixmap对象设置为传入的Pixmap对象
        self.reset_crop() # 调用项的重置裁剪方法，将项的裁剪区域属性值重置为默认值

    def pixmap_from_bytes(self, data): # 定义项的Pixmap从字节字符串设置方法，用于将项的Pixmap数据从PNG格式的字节字符串中设置
        """Set image pimap from a bytestring."""
        pixmap = QtGui.QPixmap() # 创建一个空的QPixmap对象，用于存储从字节字符串中加载的Pixmap数据
        pixmap.loadFromData(data) # 从字节字符串中加载Pixmap数据到QPixmap对象中
        self.setPixmap(pixmap) # 将项的Pixmap对象设置为加载的Pixmap对象

    def create_copy(self): # 定义项的复制方法，用于创建项的副本
        item = BeePixmapItem(QtGui.QImage(), self.filename) # 创建一个空的Pixmap项对象，用于存储复制的Pixmap数据
        item.setPixmap(self.pixmap()) # 将项的Pixmap对象复制到新创建的Pixmap项对象中
        item.setPos(self.pos()) # 将项的位置属性值复制到新创建的Pixmap项对象中
        item.setZValue(self.zValue()) # 将项的Z值属性值复制到新创建的Pixmap项对象中
        item.setScale(self.scale()) # 将项的缩放属性值复制到新创建的Pixmap项对象中
        item.setRotation(self.rotation()) # 将项的旋转属性值复制到新创建的Pixmap项对象中
        item.setOpacity(self.opacity()) # 将项的不透明度属性值复制到新创建的Pixmap项对象中
        item.grayscale = self.grayscale # 将项的灰度属性值复制到新创建的Pixmap项对象中
        if self.flip() == -1:
            item.do_flip() # 如果项的翻转属性值为-1，则调用项的翻转方法，将项的Pixmap对象水平翻转
        item.crop = self.crop # 将项的裁剪区域属性值复制到新创建的Pixmap项对象中
        return item # 返回新创建的Pixmap项对象

    @cached_property 
    def color_gamut(self): # 定义项的颜色 Gamut 计算方法，用于计算项的颜色 Gamut
        logger.debug(f'Calculating color gamut for {self}') # 记录调试信息，显示项的颜色 Gamut 计算方法和项的文件名属性
        gamut = defaultdict(int) # 创建一个默认值为整数的字典对象，用于存储项的颜色 Gamut 值
        img = self.pixmap().toImage() # 将项的Pixmap对象转换为QImage对象
        # Don't evaluate every pixel for larger images:
        step = max(1, int(max(img.width(), img.height()) / 1000)) # 计算步长，用于减少计算量，避免处理过大的图像
        logger.debug(f'Considering every {step}. row/column') # 记录调试信息，显示项的颜色 Gamut 计算方法和项的文件名属性

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

        for i in range(0, img.width(), step):# 遍历图像的每一行，步长为step
            for j in range(0, img.height(), step):# 遍历图像的每一列，步长为step
                rgb = img.pixelColor(i, j) # 获取图像在(i, j)位置的像素颜色
                rgbtuple = (rgb.red(), rgb.blue(), rgb.green()) # 将像素颜色转换为RGB元组
                if (5 < rgb.alpha() # 如果像素的alpha值大于5
                        and min(rgbtuple) < 250 and max(rgbtuple) > 5): # 如果像素的RGB值都在5到250之间，且不是接近透明、白色或黑色
                    # Only consider pixels that aren't close to
                    # transparent, white or black
                    gamut[rgb.hue(), rgb.saturation()] += 1 # 如果像素的RGB值都在5到250之间，且不是接近透明、白色或黑色，则将像素的Hue值和Saturation值作为键，将1作为值，添加到颜色 Gamut 字典中

        logger.debug(f'Got {len(gamut)} color gamut values') # 记录调试信息，显示项的颜色 Gamut 计算方法和项的文件名属性
        return gamut # 返回项的颜色 Gamut 字典对象

    def copy_to_clipboard(self, clipboard): # 定义项的复制到剪贴板方法，用于将项的Pixmap数据复制到剪贴板中
        clipboard.setPixmap(self.pixmap()) # 将项的Pixmap对象复制到剪贴板中

    def reset_crop(self):
        self.crop = QtCore.QRectF(
            0, 0, self.pixmap().size().width(), self.pixmap().size().height()) # 将项的裁剪区域属性值重置为默认值，即整个Pixmap图像

    @property
    def crop_handle_size(self): # 定义项的裁剪区域句柄大小属性方法，用于计算项的裁剪区域句柄大小
        return self.fixed_length_for_viewport(self.CROP_HANDLE_SIZE) # 返回项的裁剪区域句柄大小属性值，根据当前视口大小进行缩放

    def crop_handle_topleft(self): # 定义项的裁剪区域句柄左上角方法，用于计算项的裁剪区域句柄左上角位置
        topleft = self.crop_temp.topLeft() # 获取项的裁剪区域临时属性值的左上角位置
        return QtCore.QRectF( # 返回项的裁剪区域句柄左上角位置的矩形对象
            topleft.x(),
            topleft.y(),
            self.crop_handle_size,
            self.crop_handle_size) # 返回项的裁剪区域句柄左上角位置的矩形对象，宽度和高度都等于项的裁剪区域句柄大小属性值

    def crop_handle_bottomleft(self): # 定义项的裁剪区域句柄左下角方法，用于计算项的裁剪区域句柄左下角位置
        bottomleft = self.crop_temp.bottomLeft() # 获取项的裁剪区域临时属性值的左下角位置
        return QtCore.QRectF( # 返回项的裁剪区域句柄左下角位置的矩形对象
            bottomleft.x(),
            bottomleft.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_bottomright(self): # 定义项的裁剪区域句柄右下角方法，用于计算项的裁剪区域句柄右下角位置
        bottomright = self.crop_temp.bottomRight() # 获取项的裁剪区域临时属性值的右下角位置
        return QtCore.QRectF( # 返回项的裁剪区域句柄右下角位置的矩形对象
            bottomright.x() - self.crop_handle_size,
            bottomright.y() - self.crop_handle_size,
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handle_topright(self): # 定义项的裁剪区域句柄右上角方法，用于计算项的裁剪区域句柄右上角位置
        topright = self.crop_temp.topRight() # 获取项的裁剪区域临时属性值的右上角位置
        return QtCore.QRectF( # 返回项的裁剪区域句柄右上角位置的矩形对象
            topright.x() - self.crop_handle_size,
            topright.y(),
            self.crop_handle_size,
            self.crop_handle_size)

    def crop_handles(self): # 定义项的裁剪区域句柄方法，用于返回项的裁剪区域句柄列表
        return (self.crop_handle_topleft, # 返回项的裁剪区域句柄左上角方法
                self.crop_handle_bottomleft, # 返回项的裁剪区域句柄左下角方法
                self.crop_handle_bottomright, # 返回项的裁剪区域句柄右下角方法
                self.crop_handle_topright) # 返回项的裁剪区域句柄右上角方法

    def crop_edge_top(self): # 定义项的裁剪区域顶部边缘方法，用于计算项的裁剪区域顶部边缘位置
        topleft = self.crop_temp.topLeft() # 获取项的裁剪区域临时属性值的顶部边缘位置
        return QtCore.QRectF( # 返回项的裁剪区域顶部边缘位置的矩形对象
            topleft.x() + self.crop_handle_size, # 顶部边缘位置的横坐标等于项的裁剪区域句柄大小属性值加上项的裁剪区域临时属性值的顶部边缘位置的横坐标
            topleft.y(), # 顶部边缘位置的纵坐标等于项的裁剪区域临时属性值的顶部边缘位置的纵坐标
            self.crop_temp.width() - 2 * self.crop_handle_size, # 顶部边缘位置的宽度等于项的裁剪区域临时属性值的宽度减去2倍的项的裁剪区域句柄大小属性值
            self.crop_handle_size) # 返回项的裁剪区域顶部边缘位置的矩形对象，高度等于项的裁剪区域句柄大小属性值

    def crop_edge_left(self): # 定义项的裁剪区域左侧边缘方法，用于计算项的裁剪区域左侧边缘位置
        topleft = self.crop_temp.topLeft() # 获取项的裁剪区域临时属性值的左侧边缘位置
        return QtCore.QRectF( # 返回项的裁剪区域左侧边缘位置的矩形对象
            topleft.x(), # 左侧边缘位置的横坐标等于项的裁剪区域临时属性值的左侧边缘位置的横坐标
            topleft.y() + self.crop_handle_size, # 左侧边缘位置的纵坐标等于项的裁剪区域句柄大小属性值加上项的裁剪区域临时属性值的左侧边缘位置的纵坐标
            self.crop_handle_size, # 左侧边缘位置的宽度等于项的裁剪区域句柄大小属性值
            self.crop_temp.height() - 2 * self.crop_handle_size) # 返回项的裁剪区域左侧边缘位置的矩形对象，高度等于项的裁剪区域临时属性值的高度减去2倍的项的裁剪区域句柄大小属性值

    def crop_edge_bottom(self): # 定义项的裁剪区域底部边缘方法，用于计算项的裁剪区域底部边缘位置
        bottomleft = self.crop_temp.bottomLeft() # 获取项的裁剪区域临时属性值的底部边缘位置
        return QtCore.QRectF( # 返回项的裁剪区域底部边缘位置的矩形对象
            bottomleft.x() + self.crop_handle_size, # 底部边缘位置的横坐标等于项的裁剪区域句柄大小属性值加上项的裁剪区域临时属性值的底部边缘位置的横坐标
            bottomleft.y() - self.crop_handle_size, # 底部边缘位置的纵坐标等于项的裁剪区域句柄大小属性值减去项的裁剪区域临时属性值的底部边缘位置的纵坐标
            self.crop_temp.width() - 2 * self.crop_handle_size, # 底部边缘位置的宽度等于项的裁剪区域临时属性值的宽度减去2倍的项的裁剪区域句柄大小属性值
            self.crop_handle_size) # 返回项的裁剪区域底部边缘位置的矩形对象，高度等于项的裁剪区域句柄大小属性值

    def crop_edge_right(self): # 定义项的裁剪区域右侧边缘方法，用于计算项的裁剪区域右侧边缘位置
        topright = self.crop_temp.topRight() # 获取项的裁剪区域临时属性值的右侧边缘位置
        return QtCore.QRectF( # 返回项的裁剪区域右侧边缘位置的矩形对象
            topright.x() - self.crop_handle_size, # 右侧边缘位置的横坐标等于项的裁剪区域句柄大小属性值减去项的裁剪区域临时属性值的右侧边缘位置的横坐标
            topright.y() + self.crop_handle_size,
            self.crop_handle_size,
            self.crop_temp.height() - 2 * self.crop_handle_size)

    def crop_edges(self): # 定义项的裁剪区域边缘方法，用于返回项的裁剪区域边缘列表
        return (self.crop_edge_top, # 返回项的裁剪区域顶部边缘方法
                self.crop_edge_left, # 返回项的裁剪区域左侧边缘方法
                self.crop_edge_bottom, # 返回项的裁剪区域底部边缘方法
                self.crop_edge_right) # 返回项的裁剪区域右侧边缘方法

    def get_crop_handle_cursor(self, handle): # 定义项的裁剪区域句柄光标方法，用于返回项的裁剪区域句柄光标
        """Gets the crop cursor for the given handle."""

        is_topleft_or_bottomright = handle in ( # 判断项的裁剪区域句柄是否为左上角或右下角句柄
            self.crop_handle_topleft, self.crop_handle_bottomright)
        return self.get_diag_cursor(is_topleft_or_bottomright) # 返回项的裁剪区域句柄光标，根据项的裁剪区域句柄是否为左上角或右下角句柄来判断光标类型

    def get_crop_edge_cursor(self, edge): # 定义项的裁剪区域边缘光标方法，用于返回项的裁剪区域边缘光标
        """Gets the crop edge cursor for the given edge."""

        top_or_bottom = edge in (
            self.crop_edge_top, self.crop_edge_bottom) # 判断项的裁剪区域边缘是否为顶部或底部边缘
        sideways = (45 < self.rotation() < 135 # 判断项的旋转角度是否为45度到135度或225度到315度之间
                    or 225 < self.rotation() < 315)

        if top_or_bottom is sideways: # 如果项的裁剪区域边缘为顶部或底部边缘且项的旋转角度为45度到135度或225度到315度之间
            return Qt.CursorShape.SizeHorCursor # 返回水平光标类型
        else:
            return Qt.CursorShape.SizeVerCursor # 返回垂直光标类型

    def draw_crop_rect(self, painter, rect): # 定义项的裁剪区域矩形绘制方法，用于绘制项的裁剪区域矩形
        """Paint a dotted rectangle for the cropping UI."""
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255)) # 创建白色画笔对象
        pen.setWidth(2) # 设置画笔宽度为2像素
        pen.setCosmetic(True) # 设置画笔为无宽度模式，用于绘制虚线矩形
        painter.setPen(pen) # 设置画笔为白色画笔对象
        painter.drawRect(rect) # 绘制项的裁剪区域矩形
        pen.setColor(QtGui.QColor(0, 0, 0)) # 设置画笔颜色为黑色
        pen.setStyle(Qt.PenStyle.DotLine) # 设置画笔样式为虚线
        painter.setPen(pen) # 设置画笔为黑色虚线画笔对象
        painter.drawRect(rect) # 绘制项的裁剪区域矩形

    def paint(self, painter, option, widget): # 定义项的绘制方法，用于绘制项
        if abs(painter.combinedTransform().m11()) < 2: # 检查缩放比例是否小于2倍
            # We want image smoothing, but only for images where we
            # are not zoomed in a lot. This is to ensure that for
            # example icons and pixel sprites can be viewed correctly.
            painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform) # 设置图像平滑渲染提示

        if self.crop_mode: # 如果处于裁剪模式
            self.paint_debug(painter, option, widget) # 绘制调试信息

            # Darken image outside of cropped area
            painter.drawPixmap(0, 0, self.pixmap()) # 绘制完整图像
            path = QtWidgets.QGraphicsPixmapItem.shape(self) # 获取项目形状路径
            path.addRect(self.crop_temp) # 向路径添加临时裁剪矩形
            color = QtGui.QColor(0, 0, 0) # 创建黑色
            color.setAlpha(100) # 设置透明度
            painter.setBrush(QtGui.QBrush(color)) # 设置画刷
            painter.setPen(Qt.PenStyle.NoPen) # 设置无笔
            painter.drawPath(path) # 绘制路径（使裁剪区域外变暗）
            painter.setBrush(QtGui.QBrush()) # 重置画刷

            for handle in self.crop_handles(): # 遍历所有裁剪手柄
                self.draw_crop_rect(painter, handle()) # 绘制裁剪手柄矩形
            self.draw_crop_rect(painter, self.crop_temp) # 绘制临时裁剪矩形
        else: # 非裁剪模式
            pm = self._grayscale_pixmap if self.grayscale else self.pixmap() # 根据灰度模式选择像素图
            painter.drawPixmap(self.crop, pm, self.crop) # 绘制裁剪区域
            self.paint_selectable(painter, option, widget) # 绘制选择效果

    def enter_crop_mode(self): # 进入裁剪模式
        logger.debug(f'Entering crop mode on {self}') # 记录进入裁剪模式的日志
        self.prepareGeometryChange() # 通知Qt几何形状将要改变
        self.crop_mode = True # 启用裁剪模式
        self.crop_temp = QtCore.QRectF(self.crop) # 复制当前裁剪区域作为临时裁剪区域
        self.crop_mode_move = None # 初始化裁剪移动类型
        self.crop_mode_event_start = None # 初始化裁剪事件起始位置
        self.grabKeyboard() # 抓取键盘输入
        self.update() # 更新项目显示
        self.scene().crop_item = self # 设置场景的当前裁剪项目

    def exit_crop_mode(self, confirm): # 退出裁剪模式，参数confirm表示是否确认裁剪
        logger.debug(f'Exiting crop mode with {confirm} on {self}') # 记录退出裁剪模式的日志
        if confirm and self.crop != self.crop_temp: # 如果确认且裁剪区域有变化
            self.scene().undo_stack.push( # 将裁剪操作添加到撤销栈
                commands.CropItem(self, self.crop_temp))
        self.prepareGeometryChange() # 通知Qt几何形状将要改变
        self.crop_mode = False # 禁用裁剪模式
        self.crop_temp = None # 清除临时裁剪区域
        self.crop_mode_move = None # 清除裁剪移动类型
        self.crop_mode_event_start = None # 清除裁剪事件起始位置
        self.ungrabKeyboard() # 释放键盘抓取
        self.update() # 更新项目显示
        self.scene().crop_item = None # 清除场景的当前裁剪项目

    def keyPressEvent(self, event): # 键盘按键事件处理
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter): # 如果按下Enter键
            self.exit_crop_mode(confirm=True) # 确认并退出裁剪模式
        elif event.key() == Qt.Key.Key_Escape: # 如果按下Escape键
            self.exit_crop_mode(confirm=False) # 取消并退出裁剪模式
        else: # 其他按键
            super().keyPressEvent(event) # 调用父类处理

    def hoverMoveEvent(self, event): # 鼠标悬停移动事件处理
        if not self.crop_mode: # 如果不是裁剪模式
            return super().hoverMoveEvent(event) # 调用父类处理

        for handle in self.crop_handles(): # 遍历所有裁剪手柄
            if handle().contains(event.pos()): # 如果鼠标在手柄内
                self.set_cursor(self.get_crop_handle_cursor(handle)) # 设置对应的光标
                return
        for edge in self.crop_edges(): # 遍历所有裁剪边缘
            if edge().contains(event.pos()): # 如果鼠标在边缘内
                self.set_cursor(self.get_crop_edge_cursor(edge)) # 设置对应的光标
                return
        self.unset_cursor() # 重置光标

    def mousePressEvent(self, event): # 鼠标按下事件处理
        if not self.crop_mode: # 如果不是裁剪模式
            return super().mousePressEvent(event) # 调用父类处理

        event.accept() # 接受事件
        for handle in self.crop_handles(): # 遍历所有裁剪手柄
            # Click into a handle?
            if handle().contains(event.pos()): # 如果点击位置在手柄内
                self.crop_mode_event_start = event.pos() # 记录事件起始位置
                self.crop_mode_move = handle # 设置移动类型为该手柄
                return
        for edge in self.crop_edges(): # 遍历所有裁剪边缘
            # Click into an edge handle?
            if edge().contains(event.pos()): # 如果点击位置在边缘内
                self.crop_mode_event_start = event.pos() # 记录事件起始位置
                self.crop_mode_move = edge # 设置移动类型为该边缘
                return
        # Click not in handle, end cropping mode: 如果点击不在手柄或边缘上，结束裁剪模式
        self.exit_crop_mode(
            confirm=self.crop_temp.contains(event.pos())) # 根据点击位置决定是否确认裁剪

    def ensure_point_within_crop_bounds(self, point, handle): # 确保点在裁剪边界内
        """Returns the point, or the nearest point within the pixmap."""

        if handle == self.crop_handle_topleft: # 如果是左上角手柄
            topleft = QtCore.QPointF(0, 0) # 左上角边界
            bottomright = self.crop_temp.bottomRight() # 右下角边界（临时裁剪区域的右下角）
        if handle == self.crop_handle_bottomleft: # 如果是左下角手柄
            topleft = QtCore.QPointF(0, self.crop_temp.top()) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_handle_bottomright: # 如果是右下角手柄
            topleft = self.crop_temp.topLeft() # 左上角边界（临时裁剪区域的左上角）
            bottomright = QtCore.QPointF( # 右下角边界（整个像素图的右下角）
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_handle_topright: # 如果是右上角手柄
            topleft = QtCore.QPointF(self.crop_temp.left(), 0) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_top: # 如果是顶部边缘
            topleft = QtCore.QPointF(0, 0) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.pixmap().size().width(), self.crop_temp.bottom())
        if handle == self.crop_edge_bottom: # 如果是底部边缘
            topleft = QtCore.QPointF(0, self.crop_temp.top()) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.pixmap().size().width(), self.pixmap().size().height())
        if handle == self.crop_edge_left: # 如果是左侧边缘
            topleft = QtCore.QPointF(0, 0) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.crop_temp.right(), self.pixmap().size().height())
        if handle == self.crop_edge_right: # 如果是右侧边缘
            topleft = QtCore.QPointF(self.crop_temp.left(), 0) # 左上角边界
            bottomright = QtCore.QPointF( # 右下角边界
                self.pixmap().size().width(), self.pixmap().size().height())

        point.setX(min(bottomright.x(), max(topleft.x(), point.x()))) # 限制点的X坐标在边界内
        point.setY(min(bottomright.y(), max(topleft.y(), point.y()))) # 限制点的Y坐标在边界内

        return point # 返回限制后的点

    def mouseMoveEvent(self, event): # 鼠标移动事件处理
        if self.crop_mode and self.crop_mode_event_start: # 如果处于裁剪模式且有起始位置
            diff = event.pos() - self.crop_mode_event_start # 计算位置差异
            if self.crop_mode_move == self.crop_handle_topleft: # 如果移动左上角手柄
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTopLeft(new) # 更新左上角
            if self.crop_mode_move == self.crop_handle_bottomleft: # 如果移动左下角手柄
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottomLeft(new) # 更新左下角
            if self.crop_mode_move == self.crop_handle_bottomright: # 如果移动右下角手柄
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.bottomRight() + diff, self.crop_mode_move)
                self.crop_temp.setBottomRight(new) # 更新右下角
            if self.crop_mode_move == self.crop_handle_topright: # 如果移动右上角手柄
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setTopRight(new) # 更新右上角
            if self.crop_mode_move == self.crop_edge_top: # 如果移动顶部边缘
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setTop(new.y()) # 更新顶部
            if self.crop_mode_move == self.crop_edge_left: # 如果移动左侧边缘
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.topLeft() + diff, self.crop_mode_move)
                self.crop_temp.setLeft(new.x()) # 更新左侧
            if self.crop_mode_move == self.crop_edge_bottom: # 如果移动底部边缘
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.bottomLeft() + diff, self.crop_mode_move)
                self.crop_temp.setBottom(new.y()) # 更新底部
            if self.crop_mode_move == self.crop_edge_right: # 如果移动右侧边缘
                new = self.ensure_point_within_crop_bounds( # 确保新位置在边界内
                    self.crop_temp.topRight() + diff, self.crop_mode_move)
                self.crop_temp.setRight(new.x()) # 更新右侧
            self.update() # 更新项目显示
            self.crop_mode_event_start = event.pos() # 更新事件起始位置
            event.accept() # 接受事件
        else: # 非裁剪模式或没有起始位置
            super().mouseMoveEvent(event) # 调用父类处理

    def mouseReleaseEvent(self, event): # 鼠标释放事件处理
        if self.crop_mode: # 如果处于裁剪模式
            self.crop_mode_move = None # 清除移动类型
            self.crop_mode_event_start = None # 清除事件起始位置
            event.accept() # 接受事件
        else: # 非裁剪模式
            super().mouseReleaseEvent(event) # 调用父类处理


@register_item # 使用装饰器注册该类
class BeeTextItem(BeeItemMixin, QtWidgets.QGraphicsTextItem): # 文本项目类，继承自BeeItemMixin和QtWidgets.QGraphicsTextItem
    """Class for text added by the user."""

    TYPE = 'text' # 项目类型标识符

    def __init__(self, text=None, **kwargs): # 初始化文本项目
        super().__init__(text or "Text") # 调用父类构造函数，默认文本为"Text"
        self.save_id = None # 保存ID，用于标识项目
        logger.debug(f'Initialized {self}') # 记录初始化日志
        self.is_image = False # 标记为非图像类型
        self.init_selectable() # 初始化可选择属性
        self.is_editable = True # 标记为可编辑
        self.edit_mode = False # 编辑模式标志
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text'])) # 设置默认文本颜色

    @classmethod # 类方法，从数据创建项目
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {}) # 获取项目数据
        item = cls(**data) # 创建项目实例
        return item # 返回创建的项目

    def __str__(self): # 返回项目的字符串表示
        txt = self.toPlainText()[:40] # 获取文本前40个字符
        return (f'Text "{txt}"') # 返回格式化的字符串

    def get_extra_save_data(self): # 获取需要保存的额外数据
        return {'text': self.toPlainText()} # 返回文本内容

    def contains(self, point): # 检查点是否在项目内
        return self.boundingRect().contains(point) # 检查点是否在边界矩形内

    def paint(self, painter, option, widget): # 绘制项目
        painter.setPen(Qt.PenStyle.NoPen) # 设置无笔
        color = QtGui.QColor(0, 0, 0) # 创建黑色
        color.setAlpha(40) # 设置透明度
        brush = QtGui.QBrush(color) # 创建画刷
        painter.setBrush(brush) # 设置画刷
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self)) # 绘制背景矩形
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled # 设置选项状态为启用
        super().paint(painter, option, widget) # 调用父类绘制文本
        self.paint_selectable(painter, option, widget) # 绘制选择效果

    def create_copy(self): # 创建项目的副本
        item = BeeTextItem(self.toPlainText()) # 创建新项目，文本内容相同
        item.setPos(self.pos()) # 设置相同的位置
        item.setZValue(self.zValue()) # 设置相同的Z值
        item.setScale(self.scale()) # 设置相同的缩放比例
        item.setRotation(self.rotation()) # 设置相同的旋转角度
        if self.flip() == -1: # 如果当前是翻转状态
            item.do_flip() # 翻转新项目
        return item # 返回创建的副本

    def enter_edit_mode(self): # 进入编辑模式
        logger.debug(f'Entering edit mode on {self}') # 记录进入编辑模式的日志
        self.edit_mode = True # 启用编辑模式
        self.old_text = self.toPlainText() # 保存当前文本，用于取消编辑
        self.setTextInteractionFlags( # 设置文本交互标志为编辑交互
            Qt.TextInteractionFlag.TextEditorInteraction)
        self.scene().edit_item = self # 设置场景的当前编辑项目

    def exit_edit_mode(self, commit=True): # 退出编辑模式，参数commit表示是否确认修改
        logger.debug(f'Exiting edit mode on {self}') # 记录退出编辑模式的日志
        self.edit_mode = False # 禁用编辑模式
        # reset selection: 重置选择
        self.setTextCursor(QtGui.QTextCursor(self.document())) # 重置文本光标
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction) # 禁用文本交互
        self.scene().edit_item = None # 清除场景的当前编辑项目
        if commit: # 如果确认编辑
            self.scene().undo_stack.push( # 将文本更改添加到撤销栈
                commands.ChangeText(self, self.toPlainText(), self.old_text))
            if not self.toPlainText().strip(): # 如果文本为空
                logger.debug('Removing empty text item') # 记录删除空文本项目的日志
                self.scene().undo_stack.push( # 将删除操作添加到撤销栈
                    commands.DeleteItems(self.scene(), [self]))
        else: # 如果取消编辑
            self.setPlainText(self.old_text) # 恢复旧文本

    def has_selection_handles(self): # 检查项目是否有选择手柄（编辑模式下没有选择手柄）
        return super().has_selection_handles() and not self.edit_mode

    def keyPressEvent(self, event): # 键盘按键事件处理
        if (event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return) # 如果按下Enter键且没有修饰键
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode() # 退出编辑模式并确认
            event.accept()
            return
        if (event.key() == Qt.Key.Key_Escape # 如果按下Escape键且没有修饰键
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            self.exit_edit_mode(commit=False) # 退出编辑模式并取消
            event.accept()
            return
        super().keyPressEvent(event) # 其他按键，调用父类处理

    def copy_to_clipboard(self, clipboard): # 将项目复制到剪贴板
        clipboard.setText(self.toPlainText()) # 设置剪贴板内容为文本


@register_item # 使用装饰器注册该类
class BeeErrorItem(BeeItemMixin, QtWidgets.QGraphicsTextItem): # 错误项目类，继承自BeeItemMixin和QtWidgets.QGraphicsTextItem
    """Class for displaying error messages when an item can't be loaded
    from a bee file.

    This item will be displayed instead of the original item. It won't
    save to bee files. The original item will be preserved in the bee
    file, unless this item gets deleted by the user, or a new bee file
    is saved.
    """

    TYPE = 'error' # 项目类型标识符

    def __init__(self, text=None, **kwargs): # 初始化错误项目
        super().__init__(text or "Text") # 调用父类构造函数
        self.original_save_id = None # 原始项目的保存ID
        logger.debug(f'Initialized {self}') # 记录初始化日志
        self.is_image = False # 标记为非图像类型
        self.init_selectable() # 初始化可选择属性
        self.is_editable = False # 标记为不可编辑
        self.setDefaultTextColor(QtGui.QColor(*COLORS['Scene:Text'])) # 设置默认文本颜色

    @classmethod # 类方法，从数据创建项目
    def create_from_data(cls, **kwargs):
        data = kwargs.get('data', {}) # 获取项目数据
        item = cls(**data) # 创建项目实例
        return item # 返回创建的项目

    def __str__(self): # 返回项目的字符串表示
        txt = self.toPlainText()[:40] # 获取文本前40个字符
        return (f'Error "{txt}"') # 返回格式化的字符串

    def contains(self, point): # 检查点是否在项目内
        return self.boundingRect().contains(point) # 检查点是否在边界矩形内

    def paint(self, painter, option, widget): # 绘制项目
        painter.setPen(Qt.PenStyle.NoPen) # 设置无笔
        color = QtGui.QColor(200, 0, 0) # 创建红色
        brush = QtGui.QBrush(color) # 创建画刷
        painter.setBrush(brush) # 设置画刷
        painter.drawRect(QtWidgets.QGraphicsTextItem.boundingRect(self)) # 绘制红色背景矩形
        option.state = QtWidgets.QStyle.StateFlag.State_Enabled # 设置选项状态为启用
        super().paint(painter, option, widget) # 调用父类绘制文本
        self.paint_selectable(painter, option, widget) # 绘制选择效果

    def update_from_data(self, **kwargs): # 从数据更新项目属性
        self.original_save_id = kwargs.get('save_id', self.original_save_id) # 更新原始保存ID
        self.setPos(kwargs.get('x', self.pos().x()), # 更新X坐标
                    kwargs.get('y', self.pos().y())) # 更新Y坐标
        self.setZValue(kwargs.get('z', self.zValue())) # 更新Z值
        self.setScale(kwargs.get('scale', self.scale())) # 更新缩放比例
        self.setRotation(kwargs.get('rotation', self.rotation())) # 更新旋转角度

    def create_copy(self): # 创建项目的副本
        item = BeeErrorItem(self.toPlainText()) # 创建新项目，文本内容相同
        item.setPos(self.pos()) # 设置相同的位置
        item.setZValue(self.zValue()) # 设置相同的Z值
        item.setScale(self.scale()) # 设置相同的缩放比例
        item.setRotation(self.rotation()) # 设置相同的旋转角度
        return item # 返回创建的副本

    def flip(self, *args, **kwargs): # 返回翻转值（错误项目永远不翻转）
        """Returns the flip value (1 or -1)"""
        # Never display error messages flipped
        return 1

    def do_flip(self, *args, **kwargs): # 翻转项目（错误项目永远不翻转）
        """Flips the item."""
        # Never flip error messages
        pass

    def copy_to_clipboard(self, clipboard): # 将项目复制到剪贴板
        clipboard.setText(self.toPlainText()) # 设置剪贴板内容为文本