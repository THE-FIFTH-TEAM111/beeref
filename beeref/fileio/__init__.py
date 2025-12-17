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
import logging                                              # 用于日志记录

from PyQt6 import QtCore                                    # 导入PyQt6的QtCore模块，用于处理Qt的核心功能

from beeref import commands                                 # 导入commands命令模块，用于实现撤销和重做功能
from beeref.fileio.errors import BeeFileIOError             # 导入自定义的文件IO错误类
from beeref.fileio.image import load_image                  # 导入加载图片的函数
from beeref.fileio.sql import SQLiteIO, is_bee_file         # 导入SQLite数据库相关的类和函数
from beeref.items import BeePixmapItem                      # 导入自定义的图片项类


# 定义公共API，指定从该模块导入时可访问的名称
__all__ = [
    'is_bee_file',          # 判断文件是否为BeeRef格式的函数
    'load_bee',             # 加载BeeRef原生文件的函数
    'save_bee',             # 保存BeeRef原生文件的函数
    'load_images',          # 加载图像函数
    'ThreadedLoader',       # 线程加载器类
    'BeeFileIOError',       # 自定义的文件IO错误类
]

# 创建日志记录器
logger = logging.getLogger(__name__)


# 加载BeeRef原生文件函数
def load_bee(filename, scene, worker=None):
    """Load BeeRef native file."""
    """
    参数:
        filename: 要加载的文件路径
        scene: 目标场景对象
        worker: 可选的工作线程对象，用于报告进度
    """
    logger.info(f'Loading from file {filename}...')                 # 记录加载文件的信息日志
    io = SQLiteIO(filename, scene, readonly=True, worker=worker)    # 创建SQLiteIO对象，用于读取文件，设置为只读模式
    return io.read()                                                # 调用read方法读取文件内容并返回


# 保存BeeRef原生文件函数
def save_bee(filename, scene, create_new=False, worker=None):
    """Save BeeRef native file."""
    """
    参数:
        filename: 要保存的文件路径
        scene: 要保存的场景对象
        create_new: 是否创建新文件
        worker: 可选的工作线程对象，用于报告进度
    """
    logger.info(f'Saving to file {filename}...')                # 记录保存文件的信息日志
    logger.debug(f'Create new: {create_new}')                   # 记录创建新文件的调试日志
    io = SQLiteIO(filename, scene, create_new, worker=worker)   # 创建SQLiteIO对象，用于写入文件，根据create_new参数确定是否创建新文件
    io.write()                                                  # 调用write方法将场景数据写入文件
    logger.info('End save')                                     # 记录保存结束的信息日志



# 加载图像到现有场景函数    
def load_images(filenames, pos, scene, worker):
    """Add images to existing scene."""
    """
    参数:
        filenames: 图像文件路径列表
        pos: 图像在场景中的位置
        scene: 目标场景对象
        worker: 工作线程对象，用于报告进度和处理取消操作
    """
    errors = []                 # 存储加载失败的图像文件路径
    items = []                  # 存储成功加载的图片项对象
    worker.begin_processing.emit(len(filenames))              # 发送开始处理信号，参数为图像文件数量
    # 遍历图像文件路径列表
    for i, filename in enumerate(filenames):
        logger.info(f'Loading image from file {filename}')    # 记录加载图像文件的信息日志
        img, filename = load_image(filename)                  # 调用load_image函数加载图像文件，返回图像对象和文件名
        worker.progress.emit(i)                               # 发送进度更新信号
        if img.isNull():                                      # 检查图像是否加载失败
            logger.info(f'Could not load file {filename}')    # 记录加载失败的图像文件路径的信息日志
            errors.append(filename)                           # 将加载失败的图像文件路径添加到errors列表中
            continue                                          # 继续处理下一个图像文件

        item = BeePixmapItem(img, filename)                   # 创建BeePixmapItem对象，参数为加载的图像对象和文件名
        item.set_pos_center(pos)                              # 设置图片项的位置为指定的中心位置
        scene.add_item_later({'item': item, 'type': 'pixmap'}, selected=True)   # 将图片项添加到场景中，参数为字典，包含项对象和类型
        items.append(item)                                                      # 将图片项对象添加到items列表中
        if worker.canceled:
            break                                                               # 如果工作线程被取消，跳出循环  
        # Give main thread time to process items:
        worker.msleep(10)                                                       # 线程休眠10毫秒，允许主线程处理其他任务

    # 将添加项的操作添加到撤销栈
    scene.undo_stack.push(
        commands.InsertItems(scene, items, ignore_first_redo=True))
    worker.finished.emit('', errors)                                            # 发送完成信号，传递错误列表


# 用于加载和保存的专用线程类
class ThreadedIO(QtCore.QThread):
    """Dedicated thread for loading and saving."""

    # 定义信号
    progress = QtCore.pyqtSignal(int)               # 进度更新信号
    finished = QtCore.pyqtSignal(str, list)         # 完成信号，传递文件名和和错误列表
    begin_processing = QtCore.pyqtSignal(int)       # 开始处理信号，传递总处理数量
    user_input_required = QtCore.pyqtSignal(str)    # 用户输入required信号，参数为提示信息

    # 初始化线程，设置要执行的函数和参数    
    def __init__(self, func, *args, **kwargs):
        """
        参数:
            func: 要在线程中执行的函数
            *args: 传递给func的位置参数
            **kwargs: 传递给func的关键字参数
        """
        super().__init__()                   # 调用父类QThread构造函数
        self.func = func                     # 存储要执行的函数
        self.args = args                     # 存储要传递给函数的位置参数
        self.kwargs = kwargs                 # 存储要传递给函数的关键字参数
        self.kwargs['worker'] = self         # 将自身作为worker参数传递给函数
        self.canceled = False                # 取消标志，初始化为False
    # 线程执行函数
    def run(self):
        self.func(*self.args, **self.kwargs) # 调用指定的函数执行IO操作

    # 处理取消操作的方法
    def on_canceled(self):
        self.canceled = True                 # 设置取消标志为True
