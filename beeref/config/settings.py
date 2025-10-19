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

# 导入必要的库
import argparse  # 用于解析命令行参数
import logging   # 用于日志记录
import os        # 用于处理操作系统相关功能
import os.path   # 用于处理文件路径

from PyQt6 import QtCore, QtGui  # 导入PyQt6核心和GUI模块

from beeref import constants     # 导入应用程序常量


# 配置日志记录器
logger = logging.getLogger(__name__)


# 创建命令行参数解析器
parser = argparse.ArgumentParser(
    description=f'{constants.APPNAME_FULL} {constants.VERSION}')  # 程序描述，包含全名和版本

# 添加文件名参数：可指定要打开的bee文件或图像文件
parser.add_argument(
    'filenames',
    nargs='*',  # 接受0个或多个参数
    default=None,
    help=('Bee file or images to open. '
          'If the first file is a bee file, it will be opened and all '
          'further files will be ignored. If the first argument isn\'t a '
          'bee file, all files will be treated as images and inserted as '
          'if opened with "Insert -> Images".'))  # 参数帮助说明

# 添加设置目录参数：指定非默认的设置目录
parser.add_argument(
    '--settings-dir',
    help='settings directory to use instead of default location')

# 添加日志级别参数：指定控制台输出的日志级别
parser.add_argument(
    '-l', '--loglevel',
    default='INFO',  # 默认日志级别为INFO
    choices=list(logging._nameToLevel.keys()),  # 允许的日志级别选项
    help='log level for console output')

# 添加调试边界矩形参数：用于调试，绘制项目的边界矩形
parser.add_argument(
    '--debug-boundingrects',
    default=False,
    action='store_true',  # 无需参数，出现即设为True
    help='draw item\'s bounding rects for debugging')

# 添加调试形状参数：用于调试，绘制项目的鼠标事件形状
parser.add_argument(
    '--debug-shapes',
    default=False,
    action='store_true',
    help='draw item\'s mouse event shapes for debugging')

# 添加调试手柄参数：用于调试，绘制项目的变换手柄区域
parser.add_argument(
    '--debug-handles',
    default=False,
    action='store_true',
    help='draw item\'s transform handle areas for debugging')

# 添加调试错误参数：立即退出并显示指定错误消息
parser.add_argument(
    '--debug-raise-error',
    default='',
    help='immediately exit with given error message')


class CommandlineArgs:
    """命令行参数解析的包装类。

    检查未知参数是可配置的，以便在main()函数中有选择地启用，
    而在其他导入中忽略，这样单元测试就不会失败。

    这是一个单例类，因此参数只会被解析一次，除非with_check为True。
    """

    _instance = None  # 单例实例

    def __new__(cls, *args, **kwargs):
        """创建单例实例，确保只存在一个CommandlineArgs对象"""
        if not cls._instance or kwargs.get('with_check'):
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, with_check=False):
        """初始化方法，解析命令行参数
        
        参数:
            with_check: 是否严格检查未知参数，True则严格检查，False则忽略未知参数
        """
        # 确保只初始化一次
        if not hasattr(self, '_args'):
            if with_check:
                # 严格解析所有参数，未知参数会抛出错误
                self._args = parser.parse_args()
            else:
                # 解析已知参数，忽略未知参数
                self._args = parser.parse_known_args()[0]

    def __getattribute__(self, name):
        """自定义属性获取方法，将属性访问转发到解析后的参数对象
        
        参数:
            name: 要获取的属性名
        
        返回:
            参数对象中对应属性的值
        """
        if name == '_args':
            return super().__getattribute__(name)
        else:
            return getattr(self._args, name)


class BeeSettingsEvents(QtCore.QObject):
    """设置相关事件的信号类，用于全局发送设置变更信号"""
    # 恢复默认设置信号
    restore_defaults = QtCore.pyqtSignal()
    # 恢复键盘默认设置信号
    restore_keyboard_defaults = QtCore.pyqtSignal()


# 全局设置事件代理实例，用于发送和接收全局设置事件
# 不能在模块级别实例化BeeSettings，因为Qt应用程序可能尚未存在
settings_events = BeeSettingsEvents()


class BeeSettings(QtCore.QSettings):
    """应用程序设置类，继承自QSettings，提供自定义设置管理功能"""

    # 定义所有可配置的设置字段及其元数据
    FIELDS = {
        'Save/confirm_close_unsaved': {
            'default': True,          # 默认值：关闭未保存文件时确认
            'cast': bool,             # 类型转换：转换为布尔值
        },
        'Items/image_storage_format': {
            'default': 'best',        # 默认值：最佳存储格式
            'validate': lambda x: x in ('png', 'jpg', 'best'),  # 验证：必须是这三个值之一
        },
        'Items/arrange_gap': {
            'default': 0,             # 默认值：排列间隙为0
            'cast': int,              # 类型转换：转换为整数
            'validate': lambda x: 0 <= x <= 200,  # 验证：必须在0-200之间
        },
        'Items/arrange_default': {
            'default': 'optimal',     # 默认值：最佳排列方式
            'validate': lambda x: x in (  # 验证：必须是这四个值之一
                'optimal', 'horizontal', 'vertical', 'square'),
        },
        'Items/image_allocation_limit': {
            'default': 256,           # 默认值：图像分配限制为256MB
            'cast': int,              # 类型转换：转换为整数
            'validate': lambda x: x >= 0,  # 验证：必须大于等于0
            # 保存后回调：设置QImageReader的分配限制
            'post_save_callback': QtGui.QImageReader.setAllocationLimit,
        }
    }

    def __init__(self):
        """初始化设置对象，配置设置存储路径和格式"""
        settings_format = QtCore.QSettings.Format.IniFormat  # 使用INI格式存储
        settings_scope = QtCore.QSettings.Scope.UserScope    # 存储在用户范围
        settings_dir = self.get_settings_dir()               # 获取设置目录
        
        # 如果指定了自定义设置目录，则设置路径
        if settings_dir:
            QtCore.QSettings.setPath(
                settings_format, settings_scope, settings_dir)
        
        # 调用父类构造函数，初始化设置
        super().__init__(
            settings_format,
            settings_scope,
            constants.APPNAME,       # 组织名称
            constants.APPNAME)       # 应用程序名称

    def on_startup(self):
        """应用程序启动时需要应用的设置"""
        # 检查环境变量中是否设置了图像分配限制
        if os.environ.get('QT_IMAGEIO_MAXALLOC'):
            alloc = int(os.environ['QT_IMAGEIO_MAXALLOC'])
        else:
            # 从设置中获取图像分配限制
            alloc = self.valueOrDefault('Items/image_allocation_limit')
        
        # 设置QImageReader的分配限制
        QtGui.QImageReader.setAllocationLimit(alloc)

    def setValue(self, key, value):
        """重写setValue方法，添加保存后回调功能
        
        参数:
            key: 设置的键名
            value: 要设置的值
        """
        super().setValue(key, value)  # 调用父类方法设置值
        
        # 如果该设置有保存后回调函数，则执行
        if key in self.FIELDS and 'post_save_callback' in self.FIELDS[key]:
            self.FIELDS[key]['post_save_callback'](value)

    def remove(self, key):
        """重写remove方法，移除设置后恢复默认值并执行回调
        
        参数:
            key: 要移除的设置键名
        """
        super().remove(key)  # 调用父类方法移除设置
        
        # 如果该设置有保存后回调函数，则使用默认值执行回调
        if key in self.FIELDS and 'post_save_callback' in self.FIELDS[key]:
            value = self.valueOrDefault(key)
            self.FIELDS[key]['post_save_callback'](value)

    def valueOrDefault(self, key):
        """获取指定键的值，如果不存在或无效则返回默认值
        
        这是用于可配置设置的方法（与BeeRef自行存储的设置相对）。
        如果FIELDS中为给定键指定了'cast'和'validate'，将对值进行
        类型转换和验证。如果类型转换或验证失败，将返回默认值。
        
        参数:
            key: 要获取的设置键名
        
        返回:
            有效的设置值或默认值
        """
        val = self.value(key)  # 从设置中获取值
        conf = self.FIELDS[key]  # 获取该键的配置信息
        
        # 如果值不存在，使用默认值
        if val is None:
            val = conf['default']
        
        # 如果需要类型转换，尝试转换
        if 'cast' in conf:
            try:
                val = conf['cast'](val)
            except (ValueError, TypeError):
                # 转换失败，使用默认值
                val = conf['default']
        
        # 如果需要验证，检查值是否有效
        if 'validate' in conf:
            if not conf['validate'](val):
                # 验证失败，使用默认值
                val = conf['default']
        
        return val

    def value_changed(self, key):
        """检查指定键的值是否与默认值不同
        
        参数:
            key: 要检查的设置键名
        
        返回:
            如果值与默认值不同则为True，否则为False
        """
        return self.valueOrDefault(key) != self.FIELDS[key]['default']

    def restore_defaults(self):
        """将所有在FIELDS中指定的值恢复为默认值，通过从设置文件中移除它们实现"""
        logger.debug('Restoring settings to defaults')  # 记录调试日志
        # 遍历所有设置键并移除
        for key in self.FIELDS.keys():
            self.remove(key)
        # 发送恢复默认设置信号
        settings_events.restore_defaults.emit()

    def fileName(self):
        """获取设置文件的规范化路径
        
        返回:
            规范化的设置文件路径字符串
        """
        return os.path.normpath(super().fileName())

    def get_settings_dir(self):  # pragma: no cover
        """获取设置目录，从命令行参数中获取
        
        返回:
            命令行中指定的设置目录或None
        """
        args = CommandlineArgs()
        return args.settings_dir

    def update_recent_files(self, filename):
        """更新最近文件列表，将指定文件添加到列表开头，最多保留10个
        
        参数:
            filename: 要添加到最近文件列表的文件路径
        """
        filename = os.path.abspath(filename)  # 获取绝对路径
        values = self.get_recent_files()      # 获取当前最近文件列表
        
        # 如果文件已在列表中，先移除
        if filename in values:
            values.remove(filename)
        
        # 将文件添加到列表开头
        values.insert(0, filename)
        
        # 写入最近文件列表到设置，最多保留前10个
        self.beginWriteArray('RecentFiles')
        for i, filename in enumerate(values[:10]):
            self.setArrayIndex(i)
            self.setValue('path', filename)
        self.endArray()

    def get_recent_files(self, existing_only=False):
        """获取最近文件列表
        
        参数:
            existing_only: 是否只返回存在的文件
        
        返回:
            最近文件路径列表
        """
        values = []
        # 读取RecentFiles数组
        size = self.beginReadArray('RecentFiles')
        for i in range(size):
            self.setArrayIndex(i)
            values.append(self.value('path'))
        self.endArray()
        
        # 如果需要，过滤掉不存在的文件
        if existing_only:
            values = [f for f in values if os.path.exists(f)]
        
        return values