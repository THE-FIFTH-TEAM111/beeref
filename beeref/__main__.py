#!/usr/bin/env python3

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

import logging
import os
import platform
import signal
import sys

from PyQt6 import QtCore, QtWidgets

from beeref import constants
from beeref.assets import BeeAssets
from beeref.config import CommandlineArgs, BeeSettings, logfile_name
from beeref.utils import create_palette_from_dict
from beeref.view import BeeGraphicsView
#===================================
from PyQt6.QtWidgets import QSplitter
from beeref.widgets.controls.tag_panel import TagPanel

logger = logging.getLogger(__name__)


class BeeRefApplication(QtWidgets.QApplication):

    def event(self, event):
        if event.type() == QtCore.QEvent.Type.FileOpen:
            for widget in self.topLevelWidgets():
                if isinstance(widget, BeeRefMainWindow):
                    widget.view.open_from_file(event.file())
                    return True
            return False
        else:
            return super().event(event)


class BeeRefMainWindow(QtWidgets.QMainWindow):

    def __init__(self, app):
        super().__init__()
        app.setOrganizationName(constants.APPNAME)
        app.setApplicationName(constants.APPNAME)
        self.setWindowIcon(BeeAssets().logo)
        self.view = BeeGraphicsView(app, self)
        default_window_size = QtCore.QSize(500, 300)
        geom = self.view.settings.value('MainWindow/geometry')
        if geom is None:
            self.resize(default_window_size)
        else:
            if not self.restoreGeometry(geom):
                self.resize(default_window_size)
        
        #====================新增（修复核心：删除重复的setCentralWidget）==============================
        # 初始化标签面板
        self.tag_panel = TagPanel()
        # 绑定标签面板信号
        self.tag_panel.add_tag_requested.connect(self.on_tag_panel_add_tag)
        self.tag_panel.tag_filter_changed.connect(self.view.scene.tag_manager.apply_tag_filter)
        # 绑定标签管理器的标签更新信号（刷新面板标签列表）
        self.view.scene.tag_manager.tags_updated.connect(self.tag_panel.update_tags)

        # 创建分割布局，整合标签面板和画布视图
        self.splitter = QSplitter(QtCore.Qt.Orientation.Horizontal)  # 水平分割
        self.splitter.addWidget(self.tag_panel)
        self.splitter.addWidget(self.view)
        self.splitter.setSizes([200, 800])  # 标签面板宽度200px，画布占剩余空间
        self.setCentralWidget(self.splitter)  # 仅设置一次中央控件（分割器）
        #=======================================================
        
        self.show()

    def closeEvent(self, event):
        geom = self.saveGeometry()
        self.view.settings.setValue('MainWindow/geometry', geom)
        event.accept()
    
    #============新增==================
    def on_tag_panel_add_tag(self, tag_name: str):
        """标签面板点击“添加标签”触发"""
        from beeref.widgets.tag_dialogs import TagEditDialog
        from beeref.commands import AddTagCommand
        dialog = TagEditDialog(self, tag_name)
        if dialog.exec():
            tag_name, tag_group = dialog.get_result()
            if tag_name:
                command = AddTagCommand(self.view.scene.tag_manager, tag_name, tag_group)
                self.view.undo_stack.push(command)
    #===========================================
    
    def __del__(self):
        if hasattr(self, 'view'):  # 增加属性存在检查
            del self.view


def safe_timer(timeout, func, *args, **kwargs):
    """Create a timer that is safe against garbage collection and
    overlapping calls.
    See: http://ralsina.me/weblog/posts/BB974.html
    """
    def timer_event():
        try:
            func(*args, **kwargs)
        finally:
            QtCore.QTimer.singleShot(timeout, timer_event)
    QtCore.QTimer.singleShot(timeout, timer_event)


def handle_sigint(signum, frame):
    logger.info('Received interrupt. Exiting...')
    QtWidgets.QApplication.quit()


def handle_uncaught_exception(exc_type, exc, traceback):
    logger.critical('Unhandled exception',
                    exc_info=(exc_type, exc, traceback))
    QtWidgets.QApplication.quit()


sys.excepthook = handle_uncaught_exception


def main():
    logger.info(f'Starting {constants.APPNAME} version {constants.VERSION}')
    logger.debug('System: %s', ' '.join(platform.uname()))
    logger.debug('Python: %s', platform.python_version())
    logger.debug('LD_LIBRARY_PATH: %s', os.environ.get('LD_LIBRARY_PATH'))
    settings = BeeSettings()
    logger.info(f'Using settings: {settings.fileName()}')
    logger.info(f'Logging to: {logfile_name()}')
    settings.on_startup()
    args = CommandlineArgs(with_check=True)  # Force checking
    assert not args.debug_raise_error, args.debug_raise_error

    # os.environ["QT_DEBUG_PLUGINS"] = "1"
    app = BeeRefApplication(sys.argv)
    palette = create_palette_from_dict(constants.COLORS)
    app.setPalette(palette)
    bee = BeeRefMainWindow(app)  # NOQA:F841

    signal.signal(signal.SIGINT, handle_sigint)
    # Repeatedly run python-noop to give the interpreter time to
    # handle signals
    safe_timer(50, lambda: None)

    app.exec()
    del bee
    del app
    logger.debug('BeeRef closed')
    QtCore.qInstallMessageHandler(None)


if __name__ == '__main__':
    main()  