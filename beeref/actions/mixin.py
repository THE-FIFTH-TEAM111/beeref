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
from collections import defaultdict  # 用于创建默认值为列表的字典
from functools import partial       # 用于创建偏函数，固定部分参数
import os.path                      # 用于处理文件路径

from PyQt6 import QtGui, QtWidgets  # 导入PyQt6的GUI组件

from .actions import Action, actions  # 导入自定义的Action类和actions字典
from .menu_structure import menu_structure, MENU_SEPARATOR  # 导入菜单结构和分隔符常量


class ActionsMixin:
    """动作混合类，负责创建和管理应用程序的菜单和动作"""

    def actiongroup_set_enabled(self, group, value):
        """
        设置指定动作组中所有动作的启用状态
        
        参数:
            group: 动作组名称
            value: 布尔值，True启用，False禁用
        """
        # 遍历指定组中的所有动作并设置启用状态
        for action in self.bee_actiongroups[group]:
            action.setEnabled(value)

    def build_menu_and_actions(self):
        """创建新菜单或重建给定菜单，初始化所有动作和菜单结构"""
        # 创建上下文菜单
        self.context_menu = QtWidgets.QMenu(self)
        # 存储顶级菜单列表
        self.toplevel_menus = []
        # 创建动作组字典，键为组名，值为动作列表
        self.bee_actiongroups = defaultdict(list)
        # 存储创建后需要执行的函数列表
        self._post_create_functions = []
        # 创建所有动作
        self._create_actions()
        # 根据菜单结构创建菜单
        self._create_menu(self.context_menu, menu_structure)
        # 执行所有创建后的函数
        for func, arg in self._post_create_functions:
            func(arg)
        # 清理临时存储的函数列表
        del self._post_create_functions

    def update_menu_and_actions(self):
        """更新菜单和动作状态，目前主要用于更新最近文件列表"""
        self._build_recent_files()

    def create_menubar(self):
        """创建菜单栏并添加所有顶级菜单"""
        menu_bar = QtWidgets.QMenuBar()
        # 将所有顶级菜单添加到菜单栏
        for menu in self.toplevel_menus:
            menu_bar.addMenu(menu)
        return menu_bar

    def _store_checkable_setting(self, key, value):
        """
        将可勾选动作的状态存储到设置中
        
        参数:
            key: 设置的键名
            value: 要存储的布尔值
        """
        self.settings.setValue(key, value)

    def _init_action_checkable(self, actiondef, qaction):
        """
        初始化可勾选动作的属性和信号连接
        
        参数:
            actiondef: 动作定义对象
            qaction: PyQt的QAction对象
        """
        # 设置为可勾选动作
        qaction.setCheckable(True)
        # 获取动作对应的回调函数
        callback = getattr(self, actiondef.callback)
        # 连接勾选状态变化信号到回调函数
        qaction.toggled.connect(callback)
        # 获取设置键名和默认勾选状态
        settings_key = actiondef.settings
        checked = actiondef.checked
        # 设置初始勾选状态
        qaction.setChecked(checked)
        
        # 如果有设置键名，从设置中加载状态
        if settings_key:
            val = self.settings.value(settings_key, checked, type=bool)
            qaction.setChecked(val)
            # 存储创建后需要执行的回调函数
            self._post_create_functions.append((callback, val))
            # 连接勾选状态变化信号到设置存储函数
            qaction.toggled.connect(
                partial(self._store_checkable_setting, settings_key))
    
    # 创建所有动作
    def _create_actions(self):
        """创建所有定义在actions中的动作"""
        # 遍历所有动作定义
        for action in actions.values():
            # 创建QAction对象
            qaction = QtGui.QAction(action.text, self)
            # 禁用自动重复（防止按住快捷键时重复触发）
            qaction.setAutoRepeat(False)
            # 获取并设置快捷键
            shortcuts = action.get_shortcuts()
            if shortcuts:
                qaction.setShortcuts(shortcuts)
            
            # 处理可勾选动作
            if action.checkable:
                self._init_action_checkable(action, qaction)
            # 处理普通动作
            else:
                # 连接触发信号到对应的回调函数
                qaction.triggered.connect(getattr(self, action.callback))
            
            # 将动作添加到窗口
            self.addAction(qaction)
            # 设置初始启用状态
            qaction.setEnabled(action.enabled)
            
            # 如果动作属于某个组，添加到对应的动作组
            if action.group:
                self.bee_actiongroups[action.group].append(qaction)
                qaction.setEnabled(False)
            
            # 在动作定义中保存对应的QAction对象
            action.qaction = qaction

    def _create_menu(self, menu, items):
        """
        递归创建菜单结构
        
        参数:
            menu: 父菜单对象
            items: 要添加到菜单中的项目列表
        
        返回:
            创建好的菜单对象
        """
        # 如果项目是字符串且是方法名，调用该方法处理菜单
        if isinstance(items, str):
            getattr(self, items)(menu)
            return menu
        
        # 遍历所有项目并添加到菜单
        for item in items:
            # 如果是动作ID字符串，添加对应的动作
            if isinstance(item, str):
                menu.addAction(actions[item].qaction)
            # 如果是分隔符，添加菜单分隔线
            if item == MENU_SEPARATOR:
                menu.addSeparator()
            # 如果是字典，创建子菜单
            if isinstance(item, dict):
                # 创建子菜单
                submenu = menu.addMenu(item['menu'])
                # 如果父菜单是上下文菜单，则将子菜单添加到顶级菜单列表
                if menu == self.context_menu:
                    self.toplevel_menus.append(submenu)
                # 递归创建子菜单的内容
                self._create_menu(submenu, item['items'])

        return menu

    def _build_recent_files(self, menu=None):
        """
        构建最近文件菜单
        
        参数:
            menu: 最近文件子菜单对象（可选）
        """
        # 如果提供了菜单，则保存为最近文件子菜单
        if menu:
            self._recent_files_submenu = menu
        # 清除现有最近文件菜单内容
        self._clear_recent_files()

        # 从设置中获取最近文件列表（只保留存在的文件）
        files = self.settings.get_recent_files(existing_only=True)
        items = []

        # 创建最多10个最近文件的动作
        for i in range(10):
            action_id = f'recent_files_{i}'
            # 快捷键处理：Ctrl+0对应第10个文件，其余为Ctrl+1到Ctrl+9
            key = 0 if i == 9 else i + 1
            # 创建动作定义
            action = Action(id=action_id,
                            menu_id='_build_recent_files',
                            text=f'File {i + 1}',
                            shortcuts=[f'Ctrl+{key}'])
            # 将动作添加到actions字典
            actions[action_id] = action

            # 如果有足够的最近文件，创建对应的QAction
            if i < len(files):
                filename = files[i]
                # 创建动作对象，显示文件名（不含路径）
                qaction = QtGui.QAction(os.path.basename(filename), self)
                # 设置快捷键
                qaction.setShortcuts(action.get_shortcuts())
                # 连接触发信号到打开最近文件的方法（绑定当前文件名）
                qaction.triggered.connect(
                    partial(self.on_action_open_recent_file, filename))
                # 将动作添加到窗口
                self.addAction(qaction)
                # 保存QAction到动作定义
                action.qaction = qaction
                # 将动作添加到最近文件子菜单
                self._recent_files_submenu.addAction(qaction)
                items.append(action_id)

    def _clear_recent_files(self):
        """清除最近文件菜单中的所有动作"""
        # 移除子菜单中所有动作的关联
        for action in self._recent_files_submenu.actions():
            self.removeAction(action)
        # 清空子菜单
        self._recent_files_submenu.clear()
        # 从actions字典中移除最近文件相关的动作
        for key in list(actions.keys()):
            if key.startswith('recent_files_'):
                actions[key].qaction = None