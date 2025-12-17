# This file is part of BeeRef.
# 说明：此文件是 BeeRef 项目的一部分，用于定义应用内所有交互动作（如菜单操作、快捷键响应等）
#
# BeeRef is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 说明：BeeRef 是自由软件，可根据 GNU 通用公共许可证（第三版或更高版本）重新分发和修改，无商业限制
#
# BeeRef is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 说明：分发 BeeRef 仅保证功能可用，不承担任何质量担保（如适销性、特定场景适用性），详情参考许可证
#
# You should have received a copy of the GNU General Public License
# along with BeeRef.  If not, see <https://www.gnu.org/licenses/>.
# 说明：若未随软件获取许可证副本，可访问上述链接查看官方 GNU 通用公共许可证内容

from functools import cached_property  # 导入缓存属性装饰器，用于缓存方法返回值，避免重复计算提升性能
import logging  # 导入日志模块，用于记录动作相关的调试、错误信息

from PyQt6 import QtGui  # 从 PyQt6 导入 QtGui 模块，用于处理图形界面相关的键盘快捷键（QKeySequence）

# 从beeref.actions.menu_structure模块导入菜单结构定义menu_structure
# 作用：用于定位每个动作在应用菜单中的层级路径（如“文件→打开”）
from beeref.actions.menu_structure import menu_structure
# 从配置模块导入键盘设置类和设置事件
# KeyboardSettings：管理快捷键的读取、保存；settings_events：处理设置变更事件（如恢复默认快捷键）
from beeref.config import KeyboardSettings, settings_events
# 从工具模块导入动作列表类，用于统一管理所有Action实例，提供批量操作能力
from beeref.utils import ActionList


logger = logging.getLogger(__name__)  # 创建当前模块的日志记录器，日志名称与模块名一致


class Action:
    # 定义动作设置的分组名称，用于在配置文件中归类存储动作相关设置（如快捷键）
    SETTINGS_GROUP = 'Actions'

    def __init__(self, id, text, callback=None, shortcuts=None,
                 checkable=False, checked=False, group=None, settings=None,
                 enabled=True, menu_item=None, menu_id=None):
        # 初始化动作实例的核心属性
        self.id = id  # 动作唯一标识符（如“open”“save”），用于区分不同动作
        self.text = text  # 动作在界面上的显示文本（如“&Open”，&后字母为菜单快捷键）
        self.callback = callback  # 动作触发时调用的方法名（如“on_action_open”），需在业务逻辑中实现
        self.shortcuts = shortcuts or []  # 动作的默认快捷键列表（如['Ctrl+O']），无默认则为空列表
        self.checkable = checkable  # 动作是否为可勾选状态（如“全屏”“灰度模式”等开关类动作）
        self.checked = checked  # 动作初始勾选状态（仅checkable=True时有效）
        self.group = group  # 动作所属功能组，用于控制动作可用性（如“仅选中项目时激活”）
        self.settings = settings  # 关联的配置项路径（如“View/show_scrollbars”），用于同步设置状态
        self.enabled = enabled  # 动作初始是否启用（True=可用，False=灰色不可点击）
        self.menu_item = menu_item  # 关联的菜单项原始数据（用于菜单路径计算）
        self.menu_id = menu_id  # 动作在动态菜单中的标识（如“最近文件”菜单下的动态项）
        self.qaction = None  # 存储与当前Action绑定的PyQt QAction对象（后续界面渲染时赋值）
        self.kb_settings = KeyboardSettings()  # 实例化键盘设置对象，用于读取/保存用户自定义快捷键
        # 绑定“恢复键盘默认值”事件：当用户触发恢复默认设置时，调用当前动作的on_restore_defaults方法
        settings_events.restore_keyboard_defaults.connect(
            self.on_restore_defaults)

    def __eq__(self, other):
        # 定义Action实例的相等判断规则：仅当两个动作的id相同时，认为是同一个动作
        return self.id == other.id

    def __str__(self):
        # 定义Action实例的字符串表示形式：返回动作id，便于日志打印和调试
        return self.id

    def on_restore_defaults(self):
        # 恢复默认快捷键的具体实现：若已绑定QAction对象，将其快捷键重置为当前获取的默认值
        if self.qaction:
            self.qaction.setShortcuts(self.get_shortcuts())

    @cached_property
    def menu_path(self):
        # 缓存属性：计算并缓存动作在菜单中的层级路径（如["文件", "打开"]），避免重复递归计算
        path = []  # 存储菜单路径的临时列表，初始为空

        def _get_path(menu_item):
            # 递归函数：遍历menu_structure，查找当前动作所在的菜单层级
            if isinstance(menu_item['items'], list):
                # 情况1：当前菜单项是普通菜单（items为列表，包含子菜单项或动作id）
                for item in menu_item['items']:
                    if item == self.id:
                        # 找到当前动作，将当前菜单名称加入路径，返回True表示找到路径
                        path.append(menu_item['menu'])
                        return True
                    if isinstance(item, dict):
                        # 子项是子菜单（dict类型），递归查找子菜单
                        if _get_path(item):
                            # 子菜单中找到动作，将当前菜单名称加入路径，返回True
                            path.append(menu_item['menu'])
                            return True
            elif menu_item['items'] == self.menu_id:
                # 情况2：当前菜单项是动态菜单（如“最近文件”，items为动态标识）
                path.append(menu_item['menu'])
                return True

        # 遍历顶级菜单结构，触发递归查找
        for menu_item in menu_structure:
            _get_path(menu_item)

        # 递归结果是“子菜单→父菜单”顺序，反转后变为“父菜单→子菜单”的正确路径
        return path[::-1]

    def get_shortcuts(self):
        # 获取动作的实际生效快捷键：优先读取用户自定义配置，无配置则使用默认快捷键
        return self.kb_settings.get_list(
            self.SETTINGS_GROUP, self.id, self.shortcuts)

    def set_shortcuts(self, value):
        # 设置并保存用户自定义快捷键：记录日志→保存到配置→同步更新QAction快捷键
        logger.debug(f'Setting shortcut "{self.id}" to: {value}')  # 打印调试日志，记录快捷键变更
        # 调用KeyboardSettings的set_list方法保存快捷键（参数：分组名、动作id、新值、默认值）
        self.kb_settings.set_list(
            self.SETTINGS_GROUP, self.id, value, self.shortcuts)
        if self.qaction:
            # 若已绑定QAction，实时更新界面上的快捷键显示
            self.qaction.setShortcuts(value)

    def get_qkeysequence(self, index):
        """Current shortcuts as QKeySequence"""
        # 将指定索引的快捷键转换为PyQt的QKeySequence对象（用于界面显示和键盘事件绑定）
        try:
            # 从生效快捷键列表中取指定索引的快捷键，转换为QKeySequence
            return QtGui.QKeySequence(self.get_shortcuts()[index])
        except IndexError:
            # 索引超出范围（如快捷键列表为空），返回空的QKeySequence
            return QtGui.QKeySequence()

    def shortcuts_changed(self):
        """Whether shortcuts have changed from their defaults."""
        # 判断当前生效快捷键是否与默认值不同（用于界面显示“是否已自定义”标识）
        return self.get_shortcuts() != self.shortcuts

    def get_default_shortcut(self, index):
        # 获取默认快捷键列表中指定索引的快捷键（用于界面显示默认值）
        try:
            return self.shortcuts[index]
        except IndexError:
            # 索引超出范围，返回None
            return None


# 创建动作列表实例：将所有定义的Action实例传入ActionList，统一管理
actions = ActionList([
    # 1. 文件操作类动作
    Action(
        id='open',  # 动作唯一标识：打开文件
        text='&Open',  # 菜单显示文本：Alt+O为菜单快捷键
        shortcuts=['Ctrl+O'],  # 默认快捷键：Ctrl+O
        callback='on_action_open',  # 触发方法：on_action_open（需在业务类中实现）
    ),
    Action(
        id='save',  # 动作唯一标识：保存文件
        text='&Save',  # 菜单显示文本：Alt+S为菜单快捷键
        shortcuts=['Ctrl+S'],  # 默认快捷键：Ctrl+S
        callback='on_action_save',  # 触发方法：on_action_save
        group='active_when_items_in_scene',  # 可用性组：仅当场景中有项目时激活
    ),
    Action(
        id='save_as',  # 动作唯一标识：另存为
        text='Save &As...',  # 菜单显示文本：Alt+A为菜单快捷键
        shortcuts=['Ctrl+Shift+S'],  # 默认快捷键：Ctrl+Shift+S
        callback='on_action_save_as',  # 触发方法：on_action_save_as
        group='active_when_items_in_scene',  # 可用性组：仅当场景中有项目时激活
    ),
    Action(
        id='export_scene',  # 动作唯一标识：导出场景
        text='E&xport Scene...',  # 菜单显示文本：Alt+X为菜单快捷键
        shortcuts=['Ctrl+Shift+E'],  # 默认快捷键：Ctrl+Shift+E
        callback='on_action_export_scene',  # 触发方法：on_action_export_scene
        group='active_when_items_in_scene',  # 可用性组：仅当场景中有项目时激活
    ),
    Action(
        id='export_images',  # 动作唯一标识：导出图像
        text='Export &Images...',  # 菜单显示文本：Alt+I为菜单快捷键
        callback='on_action_export_images',  # 触发方法：on_action_export_images
        group='active_when_items_in_scene',  # 可用性组：仅当场景中有项目时激活
    ),
    Action(
        id='quit',  # 动作唯一标识：退出应用
        text='&Quit',  # 菜单显示文本：Alt+Q为菜单快捷键
        shortcuts=['Ctrl+Q'],  # 默认快捷键：Ctrl+Q
        callback='on_action_quit',  # 触发方法：on_action_quit
    ),

    # 2. 插入内容类动作
    Action(
        id='insert_images',  # 动作唯一标识：插入图像
        text='&Images...',  # 菜单显示文本：Alt+I为菜单快捷键
        shortcuts=['Ctrl+I'],  # 默认快捷键：Ctrl+I
        callback='on_action_insert_images',  # 触发方法：on_action_insert_images
    ),
    Action(
        id='insert_text',  # 动作唯一标识：插入文本
        text='&Text',  # 菜单显示文本：Alt+T为菜单快捷键
        shortcuts=['Ctrl+T'],  # 默认快捷键：Ctrl+T
        callback='on_action_insert_text',  # 触发方法：on_action_insert_text
    ),

    # 3. 编辑操作类动作
    Action(
        id='undo',  # 动作唯一标识：撤销
        text='&Undo',  # 菜单显示文本：Alt+U为菜单快捷键
        shortcuts=['Ctrl+Z'],  # 默认快捷键：Ctrl+Z
        callback='on_action_undo',  # 触发方法：on_action_undo
        group='active_when_can_undo',  # 可用性组：仅当有可撤销操作时激活
    ),
    Action(
        id='redo',  # 动作唯一标识：重做
        text='&Redo',  # 菜单显示文本：Alt+R为菜单快捷键
        shortcuts=['Ctrl+Shift+Z'],  # 默认快捷键：Ctrl+Shift+Z
        callback='on_action_redo',  # 触发方法：on_action_redo
        group='active_when_can_redo',  # 可用性组：仅当有可重做操作时激活
    ),
    Action(
        id='copy',  # 动作唯一标识：复制
        text='&Copy',  # 菜单显示文本：Alt+C为菜单快捷键
        shortcuts=['Ctrl+C'],  # 默认快捷键：Ctrl+C
        callback='on_action_copy',  # 触发方法：on_action_copy
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='cut',  # 动作唯一标识：剪切
        text='Cu&t',  # 菜单显示文本：Alt+T为菜单快捷键
        shortcuts=['Ctrl+X'],  # 默认快捷键：Ctrl+X
        callback='on_action_cut',  # 触发方法：on_action_cut
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='paste',  # 动作唯一标识：粘贴
        text='&Paste',  # 菜单显示文本：Alt+P为菜单快捷键
        shortcuts=['Ctrl+V'],  # 默认快捷键：Ctrl+V
        callback='on_action_paste',  # 触发方法：on_action_paste
    ),
    Action(
        id='delete',  # 动作唯一标识：删除
        text='&Delete',  # 菜单显示文本：Alt+D为菜单快捷键
        shortcuts=['Del'],  # 默认快捷键：Delete键
        callback='on_action_delete_items',  # 触发方法：on_action_delete_items
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 4. 图层顺序操作类动作
    Action(
        id='raise_to_top',  # 动作唯一标识：置顶
        text='&Raise to Top',  # 菜单显示文本：Alt+R为菜单快捷键
        shortcuts=['PgUp'],  # 默认快捷键：PageUp键
        callback='on_action_raise_to_top',  # 触发方法：on_action_raise_to_top
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='lower_to_bottom',  # 动作唯一标识：置底
        text='Lower to Bottom',  # 菜单显示文本：无字母快捷键
        shortcuts=['PgDown'],  # 默认快捷键：PageDown键
        callback='on_action_lower_to_bottom',  # 触发方法：on_action_lower_to_bottom
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 5. 尺寸标准化操作类动作
    Action(
        id='normalize_height',  # 动作唯一标识：标准化高度
        text='&Height',  # 菜单显示文本：Alt+H为菜单快捷键
        shortcuts=['Shift+H'],  # 默认快捷键：Shift+H
        callback='on_action_normalize_height',  # 触发方法：on_action_normalize_height
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='normalize_width',  # 动作唯一标识：标准化宽度
        text='&Width',  # 菜单显示文本：Alt+W为菜单快捷键
        shortcuts=['Shift+W'],  # 默认快捷键：Shift+W
        callback='on_action_normalize_width',  # 触发方法：on_action_normalize_width
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='normalize_size',  # 动作唯一标识：标准化尺寸
        text='&Size',  # 菜单显示文本：Alt+S为菜单快捷键
        shortcuts=['Shift+S'],  # 默认快捷键：Shift+S
        callback='on_action_normalize_size',  # 触发方法：on_action_normalize_size
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 6. 排列布局操作类动作
    Action(
        id='arrange_optimal',  # 动作唯一标识：优化排列
        text='&Optimal',  # 菜单显示文本：Alt+O为菜单快捷键
        shortcuts=['Shift+O'],  # 默认快捷键：Shift+O
        callback='on_action_arrange_optimal',  # 触发方法：on_action_arrange_optimal
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='arrange_horizontal',  # 动作唯一标识：水平排列（按文件名）
        text='&Horizontal (by filename)',  # 菜单显示文本：Alt+H为菜单快捷键
        callback='on_action_arrange_horizontal',  # 触发方法：on_action_arrange_horizontal
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='arrange_vertical',  # 动作唯一标识：垂直排列（按文件名）
        text='&Vertical (by filename)',  # 菜单显示文本：Alt+V为菜单快捷键
        callback='on_action_arrange_vertical',  # 触发方法：on_action_arrange_vertical
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='arrange_square',  # 动作唯一标识：方形排列（按文件名）
        text='&Square (by filename)',  # 菜单显示文本：Alt+S为菜单快捷键
        callback='on_action_arrange_square',  # 触发方法：on_action_arrange_square
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 7. 图像效果操作类动作
    Action(
        id='change_opacity',  # 动作唯一标识：更改不透明度
        text='Change &Opacity...',  # 菜单显示文本：Alt+O为菜单快捷键
        callback='on_action_change_opacity',  # 触发方法：on_action_change_opacity
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='grayscale',  # 动作唯一标识：灰度模式
        text='&Grayscale',  # 菜单显示文本：Alt+G为菜单快捷键
        shortcuts=['G'],  # 默认快捷键：G键
        checkable=True,  # 可勾选：启用/禁用灰度模式
        callback='on_action_grayscale',  # 触发方法：on_action_grayscale
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='show_color_gamut',  # 动作唯一标识：显示色域
        text='Show &Color Gamut',  # 菜单显示文本：Alt+C为菜单快捷键
        callback='on_action_show_color_gamut',  # 触发方法：on_action_show_color_gamut
        group='active_when_single_image',  # 可用性组：仅当选中单个图像时激活
    ),
    Action(
        id='sample_color',  # 动作唯一标识：颜色采样
        text='Sample Color',  # 菜单显示文本：无字母快捷键
        shortcuts=['S'],  # 默认快捷键：S键
        callback='on_action_sample_color',  # 触发方法：on_action_sample_color
        group='active_when_items_in_scene',  # 可用性组：仅当场景中有项目时激活
    ),
    Action(
        id='crop',  # 动作唯一标识：裁剪
        text='&Crop',  # 菜单显示文本：Alt+C为菜单快捷键
        shortcuts=['Shift+C'],  # 默认快捷键：Shift+C
        callback='on_action_crop',  # 触发方法：on_action_crop
        group='active_when_single_image',  # 可用性组：仅当选中单个图像时激活
    ),
    Action(
        id='flip_horizontally',  # 动作唯一标识：水平翻转
        text='Flip &Horizontally',  # 菜单显示文本：Alt+H为菜单快捷键
        shortcuts=['H'],  # 默认快捷键：H键
        callback='on_action_flip_horizontally',  # 触发方法：on_action_flip_horizontally
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='flip_vertically',  # 动作唯一标识：垂直翻转
        text='Flip &Vertically',  # 菜单显示文本：Alt+V为菜单快捷键
        shortcuts=['V'],  # 默认快捷键：V键
        callback='on_action_flip_vertically',  # 触发方法：on_action_flip_vertically
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 8. 场景视图操作类动作
    Action(
        id='new_scene',  # 动作唯一标识：新建场景
        text='&New Scene',  # 菜单显示文本：Alt+N为菜单快捷键
        shortcuts=['Ctrl+N'],  # 默认快捷键：Ctrl+N
        callback='on_action_new_scene',  # 触发方法：on_action_new_scene
    ),
    Action(
        id='fit_scene',  # 动作唯一标识：适配场景
        text='&Fit Scene',  # 菜单显示文本：Alt+F为菜单快捷键
        shortcuts=['1'],  # 默认快捷键：数字1键
        callback='on_action_fit_scene',  # 触发方法：on_action_fit_scene
    ),
    Action(
        id='fit_selection',  # 动作唯一标识：适配选中项
        text='Fit &Selection',  # 菜单显示文本：Alt+S为菜单快捷键
        shortcuts=['2'],  # 默认快捷键：数字2键
        callback='on_action_fit_selection',  # 触发方法：on_action_fit_selection
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 9. 变换重置操作类动作
    Action(
        id='reset_scale',  # 动作唯一标识：重置缩放
        text='Reset &Scale',  # 菜单显示文本：Alt+S为菜单快捷键
        callback='on_action_reset_scale',  # 触发方法：on_action_reset_scale
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='reset_rotation',  # 动作唯一标识：重置旋转
        text='Reset &Rotation',  # 菜单显示文本：Alt+R为菜单快捷键
        callback='on_action_reset_rotation',  # 触发方法：on_action_reset_rotation
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='reset_flip',  # 动作唯一标识：重置翻转
        text='Reset &Flip',  # 菜单显示文本：Alt+F为菜单快捷键
        callback='on_action_reset_flip',  # 触发方法：on_action_reset_flip
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='reset_crop',  # 动作唯一标识：重置裁剪
        text='Reset Cro&p',  # 菜单显示文本：Alt+P为菜单快捷键
        callback='on_action_reset_crop',  # 触发方法：on_action_reset_crop
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),
    Action(
        id='reset_transforms',  # 动作唯一标识：重置所有变换
        text='Reset &All',  # 菜单显示文本：Alt+A为菜单快捷键
        shortcuts=['R'],  # 默认快捷键：R键
        callback='on_action_reset_transforms',  # 触发方法：on_action_reset_transforms
        group='active_when_selection',  # 可用性组：仅当有选中项目时激活
    ),

    # 10. 选择操作类动作
    Action(
        id='select_all',  # 动作唯一标识：全选
        text='&Select All',  # 菜单显示文本：Alt+S为菜单快捷键
        shortcuts=['Ctrl+A'],  # 默认快捷键：Ctrl+A
        callback='on_action_select_all',  # 触发方法：on_action_select_all
    ),
    Action(
        id='deselect_all',  # 动作唯一标识：取消全选
        text='Deselect &All',  # 菜单显示文本：Alt+A为菜单快捷键
        shortcuts=['Ctrl+Shift+A'],  # 默认快捷键：Ctrl+Shift+A
        callback='on_action_deselect_all',  # 触发方法：on_action_deselect_all
    ),

    # 11. 帮助与关于类动作
    Action(
        id='help',  # 动作唯一标识：帮助
        text='&Help',  # 菜单显示文本：Alt+H为菜单快捷键
        shortcuts=['F1', 'Ctrl+H'],  # 默认快捷键：F1键、Ctrl+H
        callback='on_action_help',  # 触发方法：on_action_help
    ),
    Action(
        id='about',  # 动作唯一标识：关于
        text='&About',  # 菜单显示文本：Alt+A为菜单快捷键
        callback='on_action_about',  # 触发方法：on_action_about
    ),
    Action(
        id='debuglog',  # 动作唯一标识：显示调试日志
        text='Show &Debug Log',  # 菜单显示文本：Alt+D为菜单快捷键
        callback='on_action_debuglog',  # 触发方法：on_action_debuglog
    ),

    # 12. 界面设置类动作
    Action(
        id='show_scrollbars',  # 动作唯一标识：显示滚动条
        text='Show &Scrollbars',  # 菜单显示文本：Alt+S为菜单快捷键
        checkable=True,  # 可勾选：显示/隐藏滚动条
        settings='View/show_scrollbars',  # 关联配置项：View/show_scrollbars
        callback='on_action_show_scrollbars',  # 触发方法：on_action_show_scrollbars
    ),
    Action(
        id='show_menubar',  # 动作唯一标识：显示菜单栏
        text='Show &Menu Bar',  # 菜单显示文本：Alt+M为菜单快捷键
        checkable=True,  # 可勾选：显示/隐藏菜单栏
        settings='View/show_menubar',  # 关联配置项：View/show_menubar
        callback='on_action_show_menubar',  # 触发方法：on_action_show_menubar
    ),
    Action(
        id='show_titlebar',  # 动作唯一标识：显示标题栏
        text='Show &Title Bar',  # 菜单显示文本：Alt+T为菜单快捷键
        checkable=True,  # 可勾选：显示/隐藏标题栏
        checked=True,  # 初始状态：勾选（默认显示标题栏）
        callback='on_action_show_titlebar',  # 触发方法：on_action_show_titlebar
    ),
    Action(
        id='move_window',  # 动作唯一标识：移动窗口
        text='Move &Window',  # 菜单显示文本：Alt+W为菜单快捷键
        shortcuts=['Ctrl+M'],  # 默认快捷键：Ctrl+M
        callback='on_action_move_window',  # 触发方法：on_action_move_window
    ),
    Action(
        id='fullscreen',  # 动作唯一标识：全屏模式
        text='&Fullscreen',  # 菜单显示文本：Alt+F为菜单快捷键
        shortcuts=['F11'],  # 默认快捷键：F11键
        checkable=True,  # 可勾选：启用/禁用全屏
        callback='on_action_fullscreen',  # 触发方法：on_action_fullscreen
    ),
    Action(
        id='always_on_top',  # 动作唯一标识：窗口置顶
        text='&Always On Top',  # 菜单显示文本：Alt+A为菜单快捷键
        checkable=True,  # 可勾选：启用/禁用窗口置顶
        callback='on_action_always_on_top',  # 触发方法：on_action_always_on_top
    ),

    # 13. 应用设置类动作
    Action(
        id='settings',  # 动作唯一标识：打开设置
        text='&Settings',  # 菜单显示文本：Alt+S为菜单快捷键
        callback='on_action_settings',  # 触发方法：on_action_settings
    ),
    Action(
        id='keyboard_settings',  # 动作唯一标识：键盘鼠标设置
        text='&Keyboard && Mouse',  # 菜单显示文本：Alt+K为菜单快捷键（&&转义为单个&显示）
        callback='on_action_keyboard_settings',  # 触发方法：on_action_keyboard_settings
    ),
    Action(
        id='open_settings_dir',  # 动作唯一标识：打开设置文件夹
        text='&Open Settings Folder',  # 菜单显示文本：Alt+O为菜单快捷键
        callback='on_action_open_settings_dir',  # 触发方法：on_action_open_settings_dir
    ),
])