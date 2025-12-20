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

# 导入必要的模块和类
import base64                               # 用于编码图片数据
import logging                              # 用于记录日志
import pathlib                              # 用于处理文件路径
from xml.etree import ElementTree as ET     # 用于创建XML文档

from PyQt6 import QtCore, QtGui             # 用于处理Qt的核心功能和图形用户界面

from .errors import BeeFileIOError          # 自定义异常类，用于导出时的错误处理
from beeref import constants, widgets       # 导入 BeeRef 常量和小部件
from beeref.items import BeePixmapItem      # 导入 BeeRef 图片项类


# 创建日志记录器
logger = logging.getLogger(__name__)     


# 导出器注册类，继承自字典类
class ExporterRegistry(dict):      

    DEFAULT_TYPE = 0                    # 默认导出器类型

    def __getitem__(self, key):         # 获取指定类型的导出器
        key = key.removeprefix('.')     # 移除类型前缀的点号
        exp = self.get(key, super().__getitem__(self.DEFAULT_TYPE))    # 获取指定类型的导出器，若不存在则返回默认导出器
        logger.debug(f'Exporter for type {key}: {exp}')                # 记录获取的导出器
        return exp                                                     # 返回获取的导出器


# 创建导出器注册表实例
exporter_registry = ExporterRegistry()    


# 导出器注册装饰器，用于注册导出器类
def register_exporter(cls):                 
    exporter_registry[cls.TYPE] = cls       # 将导出器类注册到导出器注册实例中
    return cls                              # 返回导出器类注册装饰器，用于注册导出器类


# 导出器基类，用于定义导出器的通用方法
class ExporterBase:

    # 发送开始处理信号
    def emit_begin_processing(self, worker, start):
        if worker:                                    # 如果有工作线程
            worker.begin_processing.emit(start)       # 触发工作线程的开始处理信号
        else:                                                                   # 若没有工作线程
            logger.debug(f'No worker, emit begin processing signal: {start}')   # 若没有工作线程，则记录日志
    # 发送进度更新信号
    def emit_progress(self, worker, progress):
        if worker:                              # 若有工作线程
            worker.progress.emit(progress)      # 若有工作线程，则触发工作线程的进度更新信号

    # 发送完成信号
    def emit_finished(self, worker, filename, errors):
        filename = str(filename)                      # 确保文件名是字符串类型
        if worker:                                    # 若有工作线程
            worker.finished.emit(filename, errors)    # 若有工作线程，则触发工作线程的完成信号

    # 发送需要用户输入信号
    def emit_user_input_required(self, worker, msg):
        if worker:                                    # 若有工作线程
            worker.user_input_required.emit(msg)      # 若有工作线程，则触发工作线程的用户输入要求信号

    # 处理导出错误
    def handle_export_error(self, filename, error, worker):
        filename = str(filename)                         # 确保文件名是字符串类型
        logger.debug(f'Export failed: {error}')          # 记录导出失败的日志
        if worker:                                       # 若有工作线程
            worker.finished.emit(filename, [str(error)]) # 若有工作线程，则触发工作线程的完成信号，包含错误信息  
            return                                       # 若有工作线程，则返回错误信息
        else:                                                               # 若没有工作线程
            e = error if isinstance(error, Exception) else None             # 若错误不是异常类型，则设为None
            raise BeeFileIOError(msg=str(error), filename=filename) from e  # 抛出自定义异常，包含错误信息和文件名


# 场景导出器基类，用于定义场景导出器为单个图像
class SceneExporterBase(ExporterBase):
    """For exporting the scene to a single image."""        # 场景导出器基类，用于定义场景导出器的通用方法

    # 场景导出器基类的初始化方法
    def __init__(self, scene):
        self.scene = scene                                  # 场景导出器基类的初始化方法，接收场景作为参数
        self.scene.cancel_active_modes()                    # 取消场景中所有活动模式
        self.scene.deselect_all_items()                     # 取消场景中所有项的选择
        # Selection outlines/handles will be rendered to the exported
        # image, so deselect first. (Alternatively, pass an attribute
        # to paint functions to not paint them?)
        rect = self.scene.itemsBoundingRect()                        # 获取场景中所有项的边界矩形
        logger.trace(f'Items bounding rect: {rect}')                 # 记录场景中所有项的边界矩形
        size = QtCore.QSize(int(rect.width()), int(rect.height()))   # 计算导出图像的大小，取项边界矩形的宽度和高度
        logger.trace(f'Export size without margins: {size}')         # 记录导出图像的大小，不包含边距
        self.margin = max(size.width(), size.height()) * 0.03        # 计算导出图像的边距，取宽度和高度的较大值乘以0.03
        self.default_size = size.grownBy(                            # 计算导出图像的大小，包含边距
            QtCore.QMargins(*([int(self.margin)] * 4)))              # 计算导出图像的大小，包含边距
        logger.debug(f'Default export margin: {self.margin}')        # 记录导出图像的边距
        logger.debug(f'Default export size with margins: {self.default_size}')# 记录导出图像的大小，包含边距


# 注册场景到像素图导出器
@register_exporter
class SceneToPixmapExporter(SceneExporterBase):        # 场景导出器基类，用于定义场景导出器的通用方法

    TYPE = ExporterRegistry.DEFAULT_TYPE               # 设置为默认导出类型

    # 场景导出器基类的用户输入方法，用于获取用户输入的导出大小
    def get_user_input(self, parent):
        """Ask user for final export size."""          # 场景导出器基类的用户输入方法，用于获取用户输入的导出大小

        # 创建导出对话框，让用户输入最终导出尺寸
        dialog = widgets.SceneToPixmapExporterDialog(       # 创建场景导出器对话框实例
            parent=parent,                                  # 场景导出器对话框的父窗口
            default_size=self.default_size,                 # 场景导出器对话框的默认导出大小
        )
        if dialog.exec():                                   # 若场景导出器对话框执行成功
            size = dialog.value()                           # 获取场景导出器对话框中用户输入的导出大小
            logger.debug(f'Got export size {size}')         # 记录用户输入的导出大小
            self.size = size                                # 将用户输入的导出大小赋值给场景导出器基类的属性
            return True                                     # 返回True表示用户输入成功
        else:                                               # 若场景导出器对话框执行失败
            return False                                    # 返回False表示用户输入失败

    # 场景导出器基类的渲染方法，用于将场景渲染为图像
    def render_to_image(self):
        logger.debug(f'Final export size: {self.size}')                         # 记录最终导出图像的大小
        # 按比例调整边距
        margin = self.margin * self.size.width() / self.default_size.width()    # 计算最终导出图像的边距，取宽度和高度的较大值乘以0.03
        logger.debug(f'Final export margin: {margin}')                          # 记录最终导出图像的边距

        image = QtGui.QImage(self.size, QtGui.QImage.Format.Format_RGB32)       # 创建导出图像，大小为最终导出大小，格式为RGB32
        image.fill(QtGui.QColor(*constants.COLORS['Scene:Canvas']))             # 用画布颜色作为导出图像的背景颜色
        painter = QtGui.QPainter(image)                                         # 创建画家对象
        # 定义目标矩形
        target_rect = QtCore.QRectF(
            margin,                              # 取导出图像的边距作为偏移量
            margin,                              # 取导出图像的边距作为偏移量
            self.size.width() - 2 * margin,      # 取导出图像的宽度减去2倍边距作为矩形宽度
            self.size.height() - 2 * margin)     # 取导出图像的高度减去2倍边距作为矩形高度
        logger.trace(f'Final export target_rect: {target_rect}')    # 记录最终导出图像的目标矩形
        self.scene.render(painter,                                  # 渲染场景到导出图像的绘图器
                          source=self.scene.itemsBoundingRect(),    # 获取场景中所有项的边界矩形
                          target=target_rect)                       # 将场景渲染到最终导出图像的目标矩形
        painter.end()           # 结束导出图像的绘图器
        return image            # 返回导出图像


    # 场景导出器基类的导出方法，用于将场景导出为图像文件
    def export(self, filename, worker=None):
        logger.debug(f'Exporting scene to {filename}')      # 记录导出场景的文件名
        self.emit_begin_processing(worker, 1)               # 发送导出开始信号，参数为导出器实例和导出任务数量
        image = self.render_to_image()                      # 调用场景导出器基类的渲染方法，渲染场景到图像

        # 若导出器实例存在且取消导出标志为True
        if worker and worker.canceled:
            logger.debug('Export canceled')                 # 记录导出被取消的信息
            self.emit_finished(worker, filename, [])        # 发送导出完成信号，参数为导出器实例、导出文件名和空列表
            return                                          # 若导出器实例存在且取消导出标志为True，则直接返回，不导出图像

        # 若导出图像保存失败
        if not image.save(filename, quality=90):
            self.handle_export_error(filename, 'Error writing file', worker) # 处理导出错误，参数为导出文件名、错误信息和导出器实例
            return                                                           # 返回，不继续导出

        logger.debug('Export finished')               # 记录导出完成的信息
        self.emit_progress(worker, 1)                 # 发送导出进度信号，参数为导出器实例和导出进度值1
        self.emit_finished(worker, filename, [])      # 发送导出完成信号，参数为导出器实例、导出文件名和空列表

# 注册场景到SVG，
@register_exporter
class SceneToSVGExporter(SceneExporterBase):

    TYPE = 'svg'                        # 场景导出器基类的导出类型属性，值为'svg'，表示导出为SVG格式

    # 场景导出器基类的用户输入方法，用于获取用户输入的导出大小
    def get_user_input(self, parent):
        self.size = self.default_size   # 将场景导出器基类的默认导出大小赋值给场景导出器基类的属性
        return True                     # 返回True表示用户输入成功

    # 场景导出器基类的文本样式方法，用于获取项的字体样式
    def _get_textstyles(self, item):
        # 字体样式映射字典，将QFont的字体样式枚举值映射为SVG的字体样式字符串
        fontstylemap = {
            QtGui.QFont.Style.StyleNormal: 'normal',        # 将QFont的字体样式枚举值StyleNormal映射为SVG的字体样式字符串normal
            QtGui.QFont.Style.StyleItalic: 'italic',        # 将QFont的字体样式枚举值StyleItalic映射为SVG的字体样式字符串italic
            QtGui.QFont.Style.StyleOblique: 'oblique',      # 将QFont的字体样式枚举值StyleOblique映射为SVG的字体样式字符串oblique
        }

        font = item.font()                              # 获取项的字体
        fontsize = font.pointSize() * item.scale()      # 计算项的字体大小，取字体点大小乘以项的缩放比例
        families = ', '.join(font.families())           # 取字体的所有字体家族，用逗号分隔
        fontstyle = fontstylemap[font.style()]          # 取字体的字体样式，根据字体样式映射表映射为SVG的字体样式字符串

        # 返回CSS样式元组
        return ('white-space:pre',
                f'font-size:{fontsize}pt',          # 取项的字体大小，取字体点大小乘以项的缩放比例
                f'font-family:{families}',          # 取项的字体家族，用逗号分隔
                f'font-weight:{font.weight()}',     # 取项的字体重量
                f'font-stretch:{font.stretch()}',   # 取项的字体拉伸
                f'font-style:{fontstyle}')          # 取项的字体样式，根据字体样式映射表映射为SVG的字体样式字符串

    # 场景导出器基类的导出方法，用于将场景导出为SVG文件
    def render_to_svg(self, worker=None):
        svg = ET.Element(                                           # 创建SVG元素，参数为元素标签名svg
            'svg',
            attrib={'width': str(self.size.width()),                # 设置SVG元素的宽度属性，值为场景导出器基类的属性size的宽度
                    'height': str(self.size.height()),              # 设置SVG元素的高度属性，值为场景导出器基类的属性size的高度
                    'xmlns': 'http://www.w3.org/2000/svg',          # 设置SVG元素的XML命名空间属性，值为http://www.w3.org/2000/svg
                    'xmlns:xlink': 'http://www.w3.org/1999/xlink',  # 设置SVG元素的XML链接命名空间属性，值为http://www.w3.org/1999/xlink
                    })

        rect = self.scene.itemsBoundingRect()                             # 获取场景中所有项的边界矩形
        offset = rect.topLeft() - QtCore.QPointF(self.margin, self.margin)# 计算项的位置偏移量，取场景中所有项的边界矩形的左上角坐标减去导出器基类的属性margin

        # 按z值排序项目并遍历
        for i, item in enumerate(sorted(self.scene.items(),
                                        key=lambda x: x.zValue())):
            # z order in SVG specified via the order of elements in the tree
            pos = item.pos() - offset       # 计算项的位置，取项的位置减去项的位置偏移量
            anchor = pos                    # 设置项的变换锚点，取项的位置

            # 处理文本项
            if item.TYPE == 'text':                           # 若项的类型为文本项
                styles = self._get_textstyles(item)           # 获取项的字体样式
                element = ET.Element(                         # 创建文本元素，参数为元素标签名text
                    'text',                                   # 设置文本元素的标签名，值为text
                    attrib={'style': ';'.join(styles),        # 将样式列表用分号连接成CSS样式字符串，设置为元素的style属性
                            'dominant-baseline': 'hanging'})  # 设置文本元素的属性，值为hanging，指定文本的基线位置为悬挂基线
                element.text = item.toPlainText()             # 设置文本元素的文本内容，值为项的纯文本内容
            # 处理图片项
            if item.TYPE == 'pixmap':                           # 若项的类型为图片项
                width = item.width * item.scale()               # 计算项的宽度，取项的宽度乘以项的缩放比例
                height = item.height * item.scale()             # 计算项的高度，取项的高度乘以项的缩放比例
                pixmap, imgformat = item.pixmap_to_bytes(       # 将项的像素图转换为字节数组，参数为项的像素图，是否应用灰度化，是否应用裁剪
                    apply_grayscale=True,                       # 是否应用灰度化，值为True
                    apply_crop=True)                            # 是否应用裁剪，值为True
                pixmap = base64.b64encode(pixmap).decode('ascii')# 将项的像素图字节数组转换为Base64编码的字符串
                element = ET.Element(                            # 创建图片元素，参数为元素标签名image
                    'image',                                     # 设置图片元素的标签名，值为image
                    attrib={                                     # 设置图片元素的属性，值为项的像素图Base64编码的字符串
                        'xlink:href':                            # 设置图片元素的XML链接属性，值为项的像素图Base64编码的字符串
                        f'data:image/{imgformat};base64,{pixmap}',# 设置图片元素的XML链接属性，值为项的像素图Base64编码的字符串
                        'width': str(width),                      # 设置图片元素的宽度属性，值为项的宽度乘以项的缩放比例
                        'height': str(height),                    # 设置图片元素的高度属性，值为项的高度乘以项的缩放比例   
                        'image-rendering': ('crisp-edges' if item.scale() > 2# 设置图片元素的渲染属性，值为crisp-edges或optimizeQuality，根据项的缩放比例判断
                                            else 'optimizeQuality')})
                pos = pos + item.crop.topLeft()                              # 计算项的位置，取项的位置加上项的裁剪区域的左上角坐标

            #设置变换属性
            transforms = []            # 创建变换列表，用于存储项的变换操作
            if item.flip() == -1:      # 若项的翻转方向为-1
                # The following is not recognised by Inkscape and not an
                # official standard:
                # element.set('transform-origin', f'{anchor.x()} {anchor.y()}')
                # Thus we need to fix the origin manually
                transforms.append(f'translate({anchor.x()} {anchor.y()})')      # 若项的翻转方向为-1，添加变换操作，将项的锚点平移到项的位置
                transforms.append(f'scale({item.flip()} 1)')                    # 添加变换操作，将项的像素图水平翻转
                transforms.append(f'translate(-{anchor.x()} -{anchor.y()})')    # 添加变换操作，将项的锚点平移回项的位置

            #添加变换操作，将项的像素图旋转项的旋转角度
            transforms.append(
                f'rotate({item.rotation()} {anchor.x()} {anchor.y()})')         #围绕项的锚点旋转项的旋转角度

            #应用变换
            element.set('transform', ' '.join(transforms))        # 设置元素的变换属性，值为变换列表用空格连接成的字符串
            element.set('x', str(pos.x()))                        # 设置元素的x属性，值为项的位置的x坐标
            element.set('y', str(pos.y()))                        # 设置元素的y属性，值为项的位置的y坐标
            element.set('opacity', str(item.opacity()))           # 设置元素的透明度属性，值为项的透明度

            svg.append(element)                  # 将元素添加到SVG根元素中
            self.emit_progress(worker, i)        # 发送进度信号，参数为项的索引i
            if worker and worker.canceled:       # 若导出任务被取消
                return                           # 若导出任务被取消，直接返回

        return svg                               # 返回SVG根元素

    #导出场景到SVG文件
    def export(self, filename, worker=None):
        logger.debug(f'Exporting scene to {filename}')                  # 调试日志，输出导出场景到SVG文件的文件名
        self.emit_begin_processing(worker, len(self.scene.items()))     # 发送开始处理信号，设置总进度为项的数量
        svg = self.render_to_svg(worker)                                # 渲染场景到SVG元素，参数为导出任务的工作线程

        if worker and worker.canceled:             # 若导出任务被取消
            logger.debug('Export canceled')        # 调试日志，输出导出任务被取消
            worker.finished.emit(filename, [])     # 发送导出任务完成信号，参数为文件名和空列表
            return                                 # 若导出任务被取消，直接返回

        tree = ET.ElementTree(svg)       # 创建XML元素树，参数为SVG根元素
        ET.indent(tree, space='  ')      # 缩进XML元素树，参数为空格字符串

        try:
            with open(filename, 'w') as f:                              # 以UTF-8编码打开文件，参数为文件名和写入模式
                tree.write(f, encoding='unicode', xml_declaration=True) # 将XML元素树写入文件，参数为文件对象，编码为unicode，XML声明为True
        except OSError as e:                                # 若导出任务发生OS错误
            self.handle_export_error(filename, e, worker)   # 处理导出任务错误，参数为文件名、错误对象和导出任务的工作线程
            return                                          # 若导出任务发生OS错误，直接返回 

        logger.debug('Export finished')                     # 调试日志，输出导出任务完成
        self.emit_finished(worker, filename, [])            # 发送导出任务完成信号，参数为导出任务的工作线程、文件名和空列表


# 图像到目录导出器
class ImagesToDirectoryExporter(ExporterBase):
    """Export all images to a folder.

    Not registered in the registry as it is accessed via its own menu entry,
    not auto-detected by file extension.
    """

    #初始化图像到目录导出器
    def __init__(self, scene, dirname):
        self.scene = scene                                              # 场景对象
        self.dirname = dirname                                          # 目录名
        self.items = list(self.scene.items_by_type(BeePixmapItem.TYPE)) # 获取所有像素图项的列表
        self.max_save_id = 0                                            # 最大保存ID
        #查找当前最大保存ID
        for item in self.items:                                         # 遍历所有像素图项
            if item.save_id:                                            # 若项有保存ID
                self.max_save_id = max(self.max_save_id, item.save_id)  # 更新最大保存ID为项的保存ID和当前最大保存ID中的较大值
        self.num_total = len(self.items)        # 总项数
        self.start_from = 0                     # 起始索引
        self.handle_existing = None             # 处理已存在文件的方式，初始值为None

    #导出场景中的图像到目录
    def export(self, worker=None):
        logger.debug(f'Exporting images to {self.dirname}')     # 调试日志，输出导出图像到目录的目录名
        logger.debug(f'Starting at {self.start_from}')          # 调试日志，输出导出任务的起始索引

        self.emit_begin_processing(worker, self.num_total)      # 发送开始处理信号，参数为项的数量
        self.emit_progress(worker, self.start_from)             # 发送当前进度信号，参数为起始索引
        
        #遍历项目
        for i, item in enumerate(
                self.items[self.start_from:], start=self.start_from):   # 遍历从起始索引开始的项
            self.emit_progress(worker, i)                               # 发送当前进度信号，参数为项的索引i
            if worker and worker.canceled:                              # 若导出任务被取消
                logger.debug('Export canceled')                         # 调试日志，输出导出任务被取消
                worker.finished.emit(self.dirname, [])                  # 发送导出任务完成信号，参数为目录名和空列表
                return                                                  # 若导出任务被取消，直接返回 

            pixmap, imgformat = item.pixmap_to_bytes()                  # 获取项的像素图和图像格式

            #确定文件名
            if item.save_id:                                        # 若项有保存ID
                filename = item.get_filename_for_export(imgformat)  # 获取项的导出文件名，参数为图像格式
            else:                                      # 若项没有保存ID
                self.max_save_id += 1                  # 最大保存ID加1
                save_id = self.max_save_id                                  # 保存ID为最大保存ID
                filename = item.get_filename_for_export(imgformat, save_id) # 获取项的导出文件名，参数为图像格式和保存ID

            try:
                path = pathlib.Path(self.dirname) / filename    # 构建文件路径，参数为目录名和文件名
                path_exists = path.exists()                     # 检查文件路径是否存在
            except OSError as e:                                    # 若导出任务发生OS错误
                self.handle_export_error(self.dirname, e, worker)   # 处理导出任务错误，参数为目录名、错误对象和导出任务的工作线程
                return                                              # 直接返回

            #处理文件已存在的情况
            if path_exists:                                            # 若文件路径已存在
                logger.debug(f'File already exists: {path}')           # 调试日志，输出文件已存在的路径
                if self.handle_existing is None:                       # 若处理已存在文件的方式为None
                    self.start_from = i                                # 更新起始索引为当前项的索引，记录当前位置
                    self.emit_user_input_required(worker, str(path))   # 发送用户输入要求信号，请求用户输入
                    return                                             # 若导出任务发生OS错误，直接返回
                else:                                                # 若处理已存在文件的方式不为None
                    if self.handle_existing == 'skip':               # 若处理已存在文件的方式为跳过
                        self.handle_existing = None                  # 处理已存在文件的方式设为None，记录当前位置
                        logger.debug('Skipping file')                # 调试日志，输出跳过文件    
                        continue                                     # 若处理已存在文件的方式为跳过，继续下一项
                    elif self.handle_existing == 'skip_all':     # 若处理已存在文件的方式为跳过所有
                        logger.debug('Skipping file')            # 调试日志，输出跳过文件
                        continue                                 # 若处理已存在文件的方式为跳过所有，继续下一项
                    elif self.handle_existing == 'overwrite':    # 若处理已存在文件的方式为覆盖
                        self.handle_existing = None              # 处理已存在文件的方式设为None，记录当前位置
                        logger.debug('Overwrite file')           # 调试日志，输出覆盖文件     
                    elif self.handle_existing == 'overwrite_all':# 若处理已存在文件的方式为覆盖所有
                        logger.debug('Overwrite file')           # 调试日志，输出覆盖文件   

            logger.debug(f'Writing file: {path}')           # 调试日志，输出写入文件的路径
            try:
                path.write_bytes(pixmap)                    # 写入像素图到文件路径，参数为像素图
            except OSError as e:                            # 若写入像素图到文件路径发生OS错误
                self.handle_export_error(path, e, worker)   # 处理导出任务错误，参数为文件路径、错误对象和导出任务的工作线程
                return                                      # 若导出任务发生OS错误，直接返回

            self.emit_progress(worker, i)              # 发送进度信号，参数为当前项的索引，记录当前位置

        self.emit_finished(worker, self.dirname, [])   # 发送导出任务完成信号，参数为目录名和空列表
