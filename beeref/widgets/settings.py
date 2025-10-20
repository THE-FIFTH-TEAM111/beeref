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

# 导入工具函数和库
from functools import partial  # 用于固定函数参数，创建偏函数
import logging                 # 用于日志记录

# 导入PyQt6 UI组件和核心常量
from PyQt6 import QtWidgets    # 导入QtWidgets模块，用于创建UI组件
from PyQt6.QtCore import Qt    # 导入Qt核心常量（如复选框状态）

# 导入应用内部模块
from beeref import constants   # 包含应用名称、变更符号等常量
from beeref.config import BeeSettings, settings_events  # 导入设置管理类和事件信号


# 初始化日志记录器，命名为当前模块名
logger = logging.getLogger(__name__)


class GroupBase(QtWidgets.QGroupBox):
    """设置项分组的基类，继承自QGroupBox（UI分组容器）
    
    类属性（需子类重写）：
    - TITLE: 分组标题
    - HELPTEXT: 分组帮助文本（可选）
    - KEY: 关联的配置键（对应BeeSettings中的FIELDS键）
    """

    TITLE = None    # 分组标题（子类必须重写）
    HELPTEXT = None # 分组帮助文本（子类可重写，可选）
    KEY = None      # 关联的配置键（子类必须重写）

    def __init__(self):
        """初始化基类，创建分组容器并关联配置"""
        # 调用父类QGroupBox的构造函数
        super().__init__()
        # 实例化配置管理对象，用于读取/写入配置
        self.settings = BeeSettings()
        # 更新分组标题（含变更标记）
        self.update_title()
        # 创建垂直布局，用于排列分组内的UI组件
        self.layout = QtWidgets.QVBoxLayout()
        # 将布局应用到当前分组容器
        self.setLayout(self.layout)
        # 连接“恢复默认设置”信号到处理函数
        settings_events.restore_defaults.connect(self.on_restore_defaults)

        # 如果有帮助文本，创建标签并添加到布局
        if self.HELPTEXT:
            # 创建帮助文本标签
            helptxt = QtWidgets.QLabel(self.HELPTEXT)
            # 允许帮助文本自动换行
            helptxt.setWordWrap(True)
            # 将帮助标签添加到布局
            self.layout.addWidget(helptxt)

    def update_title(self):
        """更新分组标题，若配置已修改则添加变更符号"""
        # 初始化标题列表（基础标题）
        title = [self.TITLE]
        # 检查当前配置是否偏离默认值
        if self.settings.value_changed(self.KEY):
            # 若已修改，添加变更符号（如星号，定义在constants中）
            title.append(constants.CHANGED_SYMBOL)
        # 设置最终标题（拼接基础标题和变更符号）
        self.setTitle(' '.join(title))

    def on_value_changed(self, value):
        """UI值变更的处理函数，将新值写入配置
        
        参数：
            value: UI组件传递的原始值
        """
        # 若标记为“忽略值变更”，直接返回（避免递归触发）
        if self.ignore_value_changed:
            return

        # 将UI原始值转换为配置所需格式（子类可重写转换逻辑）
        value = self.convert_value_from_qt(value)
        # 检查转换后的值是否与当前配置值不同
        if value != self.settings.valueOrDefault(self.KEY):
            # 记录配置变更日志
            logger.debug(f'Setting {self.KEY} changed to: {value}')
            # 将新值写入配置
            self.settings.setValue(self.KEY, value)
            # 更新分组标题（添加/移除变更符号）
            self.update_title()

    def convert_value_from_qt(self, value):
        """将UI组件的原始值转换为配置格式（默认无转换）
        
        参数：
            value: UI组件传递的原始值
        
        返回：
            转换后的值（默认返回原始值）
        """
        return value

    def on_restore_defaults(self):
        """恢复当前配置项为默认值，并更新UI"""
        # 获取当前配置项的默认值
        new_value = self.settings.valueOrDefault(self.KEY)
        # 标记为“忽略值变更”，避免UI更新触发配置写入
        self.ignore_value_changed = True
        # 调用子类实现的set_value方法，更新UI组件显示
        self.set_value(new_value)
        # 取消“忽略值变更”标记
        self.ignore_value_changed = False
        # 更新分组标题（移除变更符号）
        self.update_title()


class RadioGroup(GroupBase):
    """单选按钮分组类，继承自GroupBase，用于多选项配置"""

    OPTIONS = None  # 单选按钮选项列表（子类必须重写）
    # OPTIONS格式：[(配置值1, 按钮文本1, 按钮提示1), (配置值2, 按钮文本2, 按钮提示2), ...]

    def __init__(self):
        """初始化单选按钮分组，创建单选按钮并关联配置"""
        # 调用父类GroupBase的构造函数
        super().__init__()

        # 标记为“忽略值变更”，避免初始化时触发配置写入
        self.ignore_value_changed = True
        # 存储单选按钮的字典：key=配置值，value=QRadioButton对象
        self.buttons = {}

        # 遍历选项列表，创建每个单选按钮
        for (value, label, helptext) in self.OPTIONS:
            # 创建单选按钮，设置显示文本
            btn = QtWidgets.QRadioButton(label)
            # 将按钮存入字典，关联配置值
            self.buttons[value] = btn
            # 设置按钮的悬停提示文本
            btn.setToolTip(helptext)
            # 连接按钮“状态切换”信号到值变更处理函数（固定当前选项的配置值）
            btn.toggled.connect(partial(self.on_value_changed, value=value))
            # 检查当前选项是否为配置的默认值，若是则选中该按钮
            if value == self.settings.valueOrDefault(self.KEY):
                btn.setChecked(True)
            # 将按钮添加到分组布局
            self.layout.addWidget(btn)

        # 取消“忽略值变更”标记，允许后续用户操作触发配置写入
        self.ignore_value_changed = False
        # 添加弹性拉伸，将按钮顶到布局上方（避免按钮分散）
        self.layout.addStretch(100)

    def set_value(self, value):
        """根据配置值更新单选按钮的选中状态
        
        参数：
            value: 要设置的配置值
        """
        # 遍历所有单选按钮，匹配配置值并选中对应按钮
        for old_value, btn in self.buttons.items():
            btn.setChecked(old_value == value)


class IntegerGroup(GroupBase):
    """整数输入分组类，继承自GroupBase，用于整数型配置（如数值范围）"""

    MIN = None  # 输入最小值（子类必须重写）
    MAX = None  # 输入最大值（子类必须重写）

    def __init__(self):
        """初始化整数输入分组，创建数值输入框并关联配置"""
        # 调用父类GroupBase的构造函数
        super().__init__()

        # 创建整数输入框（QSpinBox）
        self.input = QtWidgets.QSpinBox()
        # 设置输入框的数值范围（从子类的MIN和MAX获取）
        self.input.setRange(self.MIN, self.MAX)
        # 从配置读取默认值，更新输入框显示
        self.set_value(self.settings.valueOrDefault(self.KEY))
        # 连接输入框“值变更”信号到处理函数
        self.input.valueChanged.connect(self.on_value_changed)
        # 将输入框添加到分组布局
        self.layout.addWidget(self.input)
        # 添加弹性拉伸，将输入框顶到布局上方
        self.layout.addStretch(100)
        # 初始化“忽略值变更”标记为False（无需初始化规避，因set_value在信号连接前调用）
        self.ignore_value_changed = False

    def set_value(self, value):
        """根据配置值更新整数输入框的显示
        
        参数：
            value: 要设置的整数配置值
        """
        # 设置输入框的当前值
        self.input.setValue(value)


class SingleCheckboxGroup(GroupBase):
    """单复选框分组类，继承自GroupBase，用于布尔型配置（是/否选项）"""

    LABEL = None  # 复选框显示文本（子类必须重写）

    def __init__(self):
        """初始化复选框分组，创建复选框并关联配置"""
        # 调用父类GroupBase的构造函数
        super().__init__()

        # 创建复选框，设置显示文本（从子类的LABEL获取）
        self.input = QtWidgets.QCheckBox(self.LABEL)
        # 从配置读取默认值，更新复选框选中状态
        self.set_value(self.settings.valueOrDefault(self.KEY))
        # 连接复选框“状态变更”信号到处理函数
        self.input.checkStateChanged.connect(self.on_value_changed)
        # 将复选框添加到分组布局
        self.layout.addWidget(self.input)
        # 添加弹性拉伸，将复选框顶到布局上方
        self.layout.addStretch(100)
        # 初始化“忽略值变更”标记为False
        self.ignore_value_changed = False

    def set_value(self, value):
        """根据配置值更新复选框的选中状态
        
        参数：
            value: 布尔值，True=选中，False=未选中
        """
        # 设置复选框的选中状态
        self.input.setChecked(value)

    def convert_value_from_qt(self, value):
        """将复选框的Qt状态值转换为布尔值
        
        参数：
            value: Qt.CheckState枚举值（Checked/Unchecked/PartiallyChecked）
        
        返回：
            布尔值，True=选中（Checked），False=其他状态
        """
        # 仅当状态为“Checked”时返回True，其他状态返回False
        return value == Qt.CheckState.Checked


class ArrangeDefaultWidget(RadioGroup):
    """“默认排列方式”配置项，继承自RadioGroup（单选按钮分组）"""
    TITLE = 'Default Arrange Method:'  # 分组标题
    HELPTEXT = ('How images are arranged when inserted in batch')  # 帮助文本
    KEY = 'Items/arrange_default'  # 关联的配置键（对应BeeSettings的FIELDS）
    # 单选按钮选项：(配置值, 按钮文本, 按钮提示)
    OPTIONS = (
        ('optimal', 'Optimal', 'Arrange Optimal'),  # 优化排列
        ('horizontal', 'Horizontal (by filename)',
         'Arrange Horizontal (by filename)'),  # 按文件名水平排列
        ('vertical', 'Vertical (by filename)',
         'Arrange Vertical (by filename)'),  # 按文件名垂直排列
        ('square', 'Square (by filename)', 'Arrannge Square (by filename)'))  # 按文件名方形排列


class ImageStorageFormatWidget(RadioGroup):
    """“图像存储格式”配置项，继承自RadioGroup（单选按钮分组）"""
    TITLE = 'Image Storage Format:'  # 分组标题
    # 帮助文本（说明格式作用及生效时机）
    HELPTEXT = ('How images are stored inside bee files.'
                ' Changes will only take effect on newly saved images.')
    KEY = 'Items/image_storage_format'  # 关联的配置键
    # 单选按钮选项
    OPTIONS = (
        ('best', 'Best Guess',
         ('Small images and images with alpha channel are stored as png,'
          ' everything else as jpg')),  # 自动判断：小图/透明图存PNG，其他存JPG
        ('png', 'Always PNG', 'Lossless, but large bee file'),  # 始终存PNG（无损，文件大）
        ('jpg', 'Always JPG',
         'Small bee file, but lossy and no transparency support'))  # 始终存JPG（文件小，有损无透明）


class ArrangeGapWidget(IntegerGroup):
    """“排列间隙”配置项，继承自IntegerGroup（整数输入分组）"""
    TITLE = 'Arrange Gap:'  # 分组标题
    HELPTEXT = ('The gap between images when using arrange actions.')  # 帮助文本
    KEY = 'Items/arrange_gap'  # 关联的配置键
    MIN = 0  # 最小间隙（0像素）
    MAX = 200  # 最大间隙（200像素）


class AllocationLimitWidget(IntegerGroup):
    """“最大图像尺寸”配置项，继承自IntegerGroup（整数输入分组）"""
    TITLE = 'Maximum Image Size:'  # 分组标题
    # 帮助文本（说明尺寸单位及无限制设置）
    HELPTEXT = ('The maximum image size that can be loaded (in megabytes). '
                'Set to 0 for no limitation.')
    KEY = 'Items/image_allocation_limit'  # 关联的配置键
    MIN = 0  # 最小值（0=无限制）
    MAX = 10000  # 最大值（10000MB）


class ConfirmCloseUnsavedWidget(SingleCheckboxGroup):
    """“关闭未保存文件确认”配置项，继承自SingleCheckboxGroup（复选框分组）"""
    TITLE = 'Confirm when closing an unsaved file:'  # 分组标题
    # 帮助文本（说明确认功能的作用）
    HELPTEXT = (
        'When about to close an unsaved file, should BeeRef ask for '
        'confirmation?')
    LABEL = 'Confirm when closing'  # 复选框显示文本
    KEY = 'Save/confirm_close_unsaved'  # 关联的配置键


class SettingsDialog(QtWidgets.QDialog):
    """设置对话框类，继承自QDialog（模态对话框），整合所有配置项"""

    def __init__(self, parent):
        """初始化设置对话框，创建标签页和按钮
        
        参数：
            parent: 父窗口对象（确保对话框模态关联父窗口）
        """
        # 调用父类QDialog的构造函数，指定父窗口
        super().__init__(parent)
        # 设置对话框标题（含应用名称）
        self.setWindowTitle(f'{constants.APPNAME} Settings')
        # 创建标签页组件（用于分类显示配置项）
        tabs = QtWidgets.QTabWidget()

        # ---------------------- 第一个标签页：Miscellaneous（杂项） ----------------------
        # 创建杂项标签页的容器 widget
        misc = QtWidgets.QWidget()
        # 创建网格布局（用于排列杂项配置项）
        misc_layout = QtWidgets.QGridLayout()
        # 将布局应用到杂项容器
        misc.setLayout(misc_layout)
        # 添加“关闭未保存文件确认”配置项到网格布局（第0行第0列）
        misc_layout.addWidget(ConfirmCloseUnsavedWidget(), 0, 0)
        # 将杂项标签页添加到标签页组件，设置标签文本（&用于快捷键，Alt+M）
        tabs.addTab(misc, '&Miscellaneous')

        # ---------------------- 第二个标签页：Images & Items（图像与项目） ----------------------
        # 创建图像与项目标签页的容器 widget
        items = QtWidgets.QWidget()
        # 创建网格布局（用于排列图像相关配置项）
        items_layout = QtWidgets.QGridLayout()
        # 将布局应用到图像与项目容器
        items.setLayout(items_layout)
        # 添加配置项到网格布局（按行/列排列）
        items_layout.addWidget(ImageStorageFormatWidget(), 0, 0)  # 图像存储格式（第0行第0列）
        items_layout.addWidget(AllocationLimitWidget(), 0, 1)    # 最大图像尺寸（第0行第1列）
        items_layout.addWidget(ArrangeGapWidget(), 1, 0)         # 排列间隙（第1行第0列）
        items_layout.addWidget(ArrangeDefaultWidget(), 1, 1)     # 默认排列方式（第1行第1列）
        # 将图像与项目标签页添加到标签页组件，设置标签文本（&用于快捷键，Alt+I）
        tabs.addTab(items, '&Images && Items')

        # ---------------------- 对话框主布局 ----------------------
        # 创建垂直布局（用于排列标签页和底部按钮）
        layout = QtWidgets.QVBoxLayout()
        # 将布局应用到对话框
        self.setLayout(layout)
        # 将标签页组件添加到主布局
        layout.addWidget(tabs)

        # ---------------------- 底部按钮区 ----------------------
        # 创建对话框按钮盒，包含“关闭”按钮（标准按钮）
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close)
        # 连接“关闭”按钮的“拒绝”信号到对话框的关闭函数（reject()会关闭对话框）
        buttons.rejected.connect(self.reject)

        # 创建“恢复默认值”按钮（自定义按钮）
        reset_btn = QtWidgets.QPushButton('&Restore Defaults')
        # 取消按钮的“自动默认”属性（避免按Enter键触发）
        reset_btn.setAutoDefault(False)
        # 连接“恢复默认值”按钮的点击信号到处理函数
        reset_btn.clicked.connect(self.on_restore_defaults)
        # 将“恢复默认值”按钮添加到按钮盒，指定按钮角色为“动作角色”
        buttons.addButton(reset_btn,
                          QtWidgets.QDialogButtonBox.ButtonRole.ActionRole)

        # 将按钮盒添加到主布局（位于标签页下方）
        layout.addWidget(buttons)
        # 显示对话框（模态显示，阻塞父窗口操作）
        self.show()

    def on_restore_defaults(self, *args, **kwargs):
        """“恢复默认值”按钮的点击处理函数，弹出确认对话框并执行恢复"""
        # 弹出确认对话框，询问用户是否恢复所有默认设置
        reply = QtWidgets.QMessageBox.question(
            self,  # 父窗口（当前设置对话框）
            'Restore defaults?',  # 对话框标题
            'Do you want to restore all settings to their default values?')  # 对话框内容

        # 若用户点击“是”（Yes），执行恢复默认设置
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # 实例化配置对象并调用恢复默认方法
            BeeSettings().restore_defaults()