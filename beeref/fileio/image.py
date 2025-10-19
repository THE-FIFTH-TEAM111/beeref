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

# 导入必要的模块
import logging                             # 导入日志模块，用于记录运行时信息和错误
import os.path                             # 导入os.path模块，用于处理文件路径
import tempfile                            # 导入tempfile模块，用于创建临时文件
from urllib.error import URLError          # 导入URLError类，用于处理URL错误
from urllib import parse, request          # 导入urllib模块中的parse和request子模块，用于处理URL解析和请求

from PyQt6 import QtGui                    # 导入QtGui模块，用于处理图像和绘图

import exif                                # 导入exif模块，用于处理图像的EXIF数据
from lxml import etree                     # 导入lxml模块中的etree子模块，用于解析HTML
import plum                                # 导入plum模块，用于处理图像的二进制数据

# 创建日志记录器实例
logger = logging.getLogger(__name__)


# 定义函数exif_rotated_image，用于根据图像的EXIF数据进行旋转和镜像变换
def exif_rotated_image(path=None):
    """Returns a QImage that is transformed according to the source's
    orientation EXIF data.
    """

    # 创建QImage对象
    img = QtGui.QImage(path)
    # 检查图像是否为空（无法加载）
    if img.isNull():
        return img                          # 如果图像为空，直接返回

    # 尝试读取EXIF数据
    with open(path, 'rb') as f:
        try:
            exifimg = exif.Image(f)                                     # 从文件对象创建EXIF图像对象
        except (plum.exceptions.UnpackError, NotImplementedError):      # 处理EXIF解析错误  
            logger.exception(f'Exif parser failed on image: {path}')    # 记录EXIF解析错误日志
            return img                                                  # 如果EXIF解析错误，直接返回原始图像

    try:
        if 'orientation' in exifimg.list_all():          # 检查是否存在方向EXIF信息
            orientation = exifimg.orientation            # 获取方向EXIF信息
        else:
            return img                                   # 如果不存在方向EXIF信息，直接返回原始图像    
    except (NotImplementedError, ValueError):            # 处理其他EXIF读取错误
        logger.exception(f'Exif failed reading orientation of image: {path}')   # 记录EXIF读取错误日志
        return img                                                              # 如果EXIF读取错误，直接返回原始图像

    # 创建变换对象
    transform = QtGui.QTransform()

    # 根据EXIF方向值进行相应的变换
    if orientation == exif.Orientation.TOP_RIGHT:                   # 方向值2：方向为顶部右侧，需要水平镜像
        return img.mirrored(horizontal=True, vertical=False)
    if orientation == exif.Orientation.BOTTOM_RIGHT:                # 方向值3：方向为底部右侧，需要旋转180度
        transform.rotate(180)
        return img.transformed(transform)
    if orientation == exif.Orientation.BOTTOM_LEFT:                 # 方向值4：方向为底部左侧，需要垂直镜像
        return img.mirrored(horizontal=False, vertical=True)
    if orientation == exif.Orientation.LEFT_TOP:                    # 方向值5：方向为左侧顶部，需要顺时针旋转90度
        transform.rotate(90)
        return img.transformed(transform).mirrored(
            horizontal=True, vertical=False)
    if orientation == exif.Orientation.RIGHT_TOP:                   # 方向值6：方向为右侧顶部，需要逆时针旋转90度
        transform.rotate(90)
        return img.transformed(transform)
    if orientation == exif.Orientation.RIGHT_BOTTOM:                # 方向值7：方向为右侧底部，需要顺时针旋转270度
        transform.rotate(270)
        return img.transformed(transform).mirrored(
            horizontal=True, vertical=False)
    if orientation == exif.Orientation.LEFT_BOTTOM:                 # 方向值8：方向为左侧底部，需要逆时针旋转270度
        transform.rotate(270)
        return img.transformed(transform)

    return img                                                      # 方向值1或其他未知值，返回原始图像


# 加载图像的主要函数
def load_image(path):
    
    # 处理本地文件路径（字符串形式）
    if isinstance(path, str):                       # 检查路径是否为字符串类型
        path = os.path.normpath(path)               # 规范路径格式，处理路径中的特殊字符和点号
        return (exif_rotated_image(path), path)     # 加载图像并处理EXIF方向
    
    # 处理QUrl对象指向的本地文件
    if path.isLocalFile():                              # 检查路径是否为本地文件路径
        path = os.path.normpath(path.toLocalFile())     # 转化为本地路径并规范本地文件路径格式
        return (exif_rotated_image(path), path)         # 加载图像并处理EXIF方向

     # 处理远程URL
    url = bytes(path.toEncoded()).decode()                          # 将QUrl对象转化为URL字符串并解码
    domain = '.'.join(parse.urlparse(url).netloc.split(".")[-2:])   # 从URL中提取域名（例如：'pinterest.com'）
    img = exif_rotated_image()                                      # 创建一个空的QImage对象

    # 对Pinterest特定处理
    if domain == 'pinterest.com':
        try:                                                        # 尝试下载Pinterest页面HTML内容
            page_data = request.urlopen(url).read()                 # 下载Pinterest页面HTML内容
            root = etree.HTML(page_data)                            # 解析HTML内容为ElementTree对象
            url = root.xpath("//img")[0].get('src')                 # 从HTML中提取第一个img标签的src属性值（图像URL）
        except Exception as e:                                      # 处理下载Pinterest页面HTML内容时的异常
            logger.debug(f'Pinterest image download failed: {e}')   # 如果Pinterest图片下载失败，记录Pinterest图像下载失败日志

    # 尝试下载图像数据
    try:
        imgdata = request.urlopen(url).read()                       # 下载图像数据
    except URLError as e:                                           # 处理下载图像数据时的异常
        logger.debug(f'Downloading image failed: {e.reason}')       # 如果图像下载失败，记录图像下载失败日志 
    else:
        with tempfile.TemporaryDirectory() as tmp:                  # 创建一个临时文件用于存储下载成功的图像数据
            fname = os.path.join(tmp, 'img')                        # 构建临时文件路径（例如：'/tmp/img'）
            with open(fname, 'wb') as f:                            # 以二进制写入模式打开临时文件
                f.write(imgdata)                                    # 将图像数据写入临时文件
                logger.debug(f'Temporarily saved in: {fname}')      # 记录临时保存的图像路径
            img = exif_rotated_image(fname)                         # 加载临时图像文件并处理EXIF方向
    return (img, url)                                               # 返回处理后的图像对象和原始URL
