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

"""BeeRef's native file format is using SQLite. Embedded files are
stored in an sqlar table so that they can be extracted using sqlite's
archive command line option.

For more info, see:

https://www.sqlite.org/appfileformat.html
https://www.sqlite.org/sqlar.html
"""

# 导入必要的模块
import json                   # 导入 JSON 模块，用于处理 JSON 数据
import logging                # 导入日志模块，用于记录程序运行时的信息
import os                     # 导入 os 模块，用于处理文件路径
import pathlib                # 导入 pathlib 模块，用于处理文件路径
import shutil                 # 导入 shutil 模块，用于文件操作
import sqlite3                # 导入 sqlite3 模块，用于操作 SQLite 数据库
import tempfile               # 导入 tempfile 模块，用于创建临时文件

from PyQt6 import QtGui       # 导入 PyQt6 模块，用于 GUI 编程

from beeref import constants  # 导入 BeeRef 模块，用于定义常量
from beeref.items import BeePixmapItem, BeeErrorItem                  # 导入 BeeRef 模块，用于定义项
from .errors import BeeFileIOError, IMG_LOADING_ERROR_MSG             # 导入 BeeRef 模块，用于定义错误
from .schema import SCHEMA, USER_VERSION, MIGRATIONS, APPLICATION_ID  # 导入 BeeRef 模块，用于定义数据库模式    

# 配置日志记录器
logger = logging.getLogger(__name__)


# 检查文件是否为bee文件
def is_bee_file(path):
    """Check whether the file at the given path is a bee file."""
    
    return os.path.splitext(path)[1] == '.bee'                       # 使用os.path.splitext分割文件名和扩展名


# 处理SQLite错误
def handle_sqlite_errors(func):
    def wrapper(self, *args, **kwargs):
        try:
            # 尝试执行原始函数
            func(self, *args, **kwargs)                                     # 执行函数
        except Exception as e:                                              # 捕获所有异常
            logger.exception(f'Error while reading/writing {self.filename}')# 记录异常日志，包含文件名信息
            try:                                                            # 尝试回滚事务
                # Try to roll back transaction if there is any
                if (hasattr(self, '_connection')                            # 检查是否有数据库连接属性 
                        and self._connection.in_transaction):               # 检查是否有未提交的事务
                    self.ex('ROLLBACK')                                     # 执行SQL回滚命令
                    logger.debug('Transaction rolled back')                 # 记录回滚信息
            except sqlite3.Error as e:                                      # 捕获SQLite错误
                pass                                                        # 如果回滚失败，忽略SQLite错误
            self._close_connection()                                        # 关闭数据库连接
            if self.worker:                                                 # 如果有工作线程，则向其发送完成信号并附带错误信息
                self.worker.finished.emit(self.filename, [str(e)])          # 发射工作线程完成信号
            else:                                                           # 如果没有工作线程
                raise BeeFileIOError(msg=str(e), filename=self.filename) from e# 抛出 BeeFileIOError 异常

    return wrapper                                                             # 返回包装后的函数

# 定义SQLiteIO类，用于操作SQLite数据库文件
class SQLiteIO:

    # 初始化SQLiteIO类
    def __init__(self, filename, scene, create_new=False, readonly=False,
                 worker=None):
        self.scene = scene                               # 保存场景引用，用于添加或获取项目
        self.create_new = create_new                     # 设置是否创建新文件的标志
        self.filename = filename                         # 保存数据库文件名
        self.readonly = readonly                         # 设置是否为只读模式
        self.worker = worker                             # 保存工作线程引用，用于进度更新
        self.retry = False                               # 初始化重试标志，用于错误恢复

    # 析构函数
    def __del__(self):
        self._close_connection()                         # 在对象被销毁时调用，确保资源被正确释放  

    # 关闭数据库连接
    def _close_connection(self):
        # 检查并关闭数据库连接
        if hasattr(self, '_connection'):        # 检查是否有数据库连接属性
            self._connection.close()            # 关闭数据库连接
            delattr(self, '_connection')        # 删除数据库连接属性
        # 检查并删除游标引用
        if hasattr(self, '_cursor'):            # 检查是否有游标属性
            delattr(self, '_cursor')            # 删除游标属性
        # 检查并清理临时目录  
        if hasattr(self, '_tmpdir'):            # 检查是否有临时目录属性
            self._tmpdir.cleanup()              # 清理临时目录
            delattr(self, '_tmpdir')            # 删除临时目录属性

    # 建立数据库连接
    def _establish_connection(self):
        # 如果需要创建新文件且文件已存在，则删除现有文件
        if (self.create_new                             # 检查是否创建新文件
                and not self.readonly                   # 检查是否为只读模式
                and os.path.exists(self.filename)):     # 检查文件是否已存在
            os.remove(self.filename)                    # 删除已存在的文件

        # 如果创建新文件，清除场景中所有项目的保存I
        if self.create_new:                             # 检查是否创建新文件
            self.scene.clear_save_ids()                 # 清除场景中所有项目的保存ID

        uri = pathlib.Path(self.filename).resolve().as_uri()# 将文件路径转换为URI格式，确保跨平台兼容性
        if self.readonly:                                   # 检查是否为只读模式
            uri = f'{uri}?mode=rw'                          # 如果是只读模式，添加查询参数以指定为读写模式
        self._connection = sqlite3.connect(uri, uri=True)   # 建立数据库连接，使用URI格式
        self._cursor = self._connection.cursor()            # 创建游标对象，用于执行SQL语句 
        # 如果不是创建新文件，则尝试迁移数据库
        if not self.create_new:                             # 检查是否不是创建新文件
            try:
                self._migrate()                             # 尝试迁移数据库
            except Exception as e:                          # 捕获所有异常
                # Updating a file failed; try creating it from scratch instead
                logger.exception('Error migrating bee file: %s', e) # 记录异常日志，包含异常信息
                self.create_new = True                              # 标记为创建新文件
                self._establish_connection()                        # 重新建立数据库连接

    # 迁移数据库
    def _migrate(self):
        """Migrate database if necessary."""

        version = self.fetchone('PRAGMA user_version')[0]           # 获取数据库用户版本号
        logger.debug(f'Found bee file version: {version}')          # 记录数据库版本号
        if version >= USER_VERSION:                                 # 检查数据库版本号是否大于等于用户版本号
            logger.debug('Version ok; no migrations necessary')     # 如果版本号大于等于用户版本号，无需迁移
            return                                                  # 如果版本号大于等于用户版本号，无需迁移
        # 如果版本已经是最新的，不需要迁移
        if self.readonly:
            try:
                # See whether file is writable so we can migrate it directly
                self.ex('PRAGMA application_id=%s' % APPLICATION_ID)         # 设置应用程序ID，确保数据库与应用程序兼容
            except sqlite3.Error as e:                                       # 捕获 SQLite 错误异常
                logger.debug('File not writable; use temporary copy instead')# 记录文件不可写日志，建议使用临时副本
                self._connection.close()                                     # 关闭数据库连接
                self._tmpdir = tempfile.TemporaryDirectory(                  # 创建临时目录，用于存储迁移后的数据库文件
                    prefix=constants.APPNAME)                                # 设置临时目录前缀，确保与应用程序名称一致
                tmpname = os.path.join(self._tmpdir.name, 'mig.bee')         # 构建临时数据库文件名
                shutil.copyfile(self.filename, tmpname)                      # 复制原始数据库文件到临时目录
                self._connection = sqlite3.connect(tmpname)                  # 连接到临时数据库文件
                self._cursor = self.connection.cursor()                      # 创建游标对象，用于执行SQL语句

        self.ex('BEGIN TRANSACTION')                                      # 开始事务，确保迁移的原子性
        for i in range(version, USER_VERSION):                            # 遍历需要迁移的版本号范围
            logger.debug(f'Migrating from version {i} to {i + 1}...')     # 记录迁移信息，包含当前版本号和目标版本号
            for migration in MIGRATIONS[i + 1]:                           # 遍历当前版本号对应的迁移SQL语句列表
                self.ex(migration)                                        # 执行迁移SQL语句
        self.write_meta()                                                 # 写入数据库元数据，包括应用程序ID和用户版本号
        self.connection.commit()                                          # 提交事务，确保所有迁移操作都被永久保存
        logger.debug('Migration finished')                                # 记录迁移完成日志

    @property
    # 获取数据库连接属性
    def connection(self):
        if not hasattr(self, '_connection'):    # 检查是否没有数据库连接属性
            self._establish_connection()        # 如果没有数据库连接属性，建立数据库连接
        return self._connection                 # 返回数据库连接属性

    @property
    # 获取数据库游标属性
    def cursor(self):
        if not hasattr(self, '_cursor'):        # 检查是否没有数据库游标属性
            self._establish_connection()        # 如果没有数据库游标属性，建立数据库连接
        return self._cursor                     # 返回数据库游标属性    

    # 执行SQL语句，返回执行结果
    def ex(self, *args, **kwargs):
        return self.cursor.execute(*args, **kwargs)

    # 执行批量SQL语句，返回执行结果
    def exmany(self, *args, **kwargs):
        return self.cursor.executemany(*args, **kwargs)

    # 从数据库游标中获取一条记录，返回记录元组
    def fetchone(self, *args, **kwargs):
        self.ex(*args, **kwargs)            # 执行SQL语句，传入参数和关键字参数
        return self.cursor.fetchone()       # 返回查询结果的第一行

    # 从数据库游标中获取所有记录，返回记录列表
    def fetchall(self, *args, **kwargs):
        self.ex(*args, **kwargs)            # 执行SQL语句，传入参数和关键字参数
        return self.cursor.fetchall()       # 从游标中获取所有记录，返回记录列表

    # 写入数据库元数据，包括应用程序ID和用户版本号
    def write_meta(self):
        self.ex('PRAGMA application_id=%s' % APPLICATION_ID)    # 设置应用程序ID，确保数据库与应用程序兼容  
        self.ex('PRAGMA user_version=%s' % USER_VERSION)        # 设置用户版本，用于版本控制
        self.ex('PRAGMA foreign_keys=ON')                       # 启用外键约束，确保数据完整性

    # 创建新文件时创建数据库架构
    def create_schema_on_new(self):
        if self.create_new:                 # 仅在创建新文件时执行
            self.write_meta()               # 写入数据库元数据
            for schema in SCHEMA:           # 执行所有架构创建SQL语句
                self.ex(schema)             # 执行架构创建SQL语句

    # 从数据库中读取所有项，包括图片和文本项
    @handle_sqlite_errors
    def read(self):
         # 读取所有图像项目及其关联的二进制数据
        rows = self.fetchall(
            'SELECT items.id, type, x, y, z, scale, rotation, flip, '
            'items.data, sqlar.data '
            'FROM sqlar JOIN items on sqlar.item_id = items.id')
        # Avoid OUTER JOIN for performance reasons; fetch text items
        # separately instead
        # 读取所有文本项目
        rows.extend(self.fetchall(
            'SELECT items.id, type, x, y, z, scale, rotation, flip, '
            ' items.data, null as data '
            'FROM items '
            'WHERE items.type = "text"'))
        if self.worker:                                     # 如果有工作线程
            self.worker.begin_processing.emit(len(rows))    # 发送开始处理信号，包含项数

        # 遍历所有读取的项目数据
        for i, row in enumerate(rows):
             # 构建项目数据字典
            data = {
                'save_id': row[0],          # 项目ID
                'type': row[1],             # 项目类型
                'x': row[2],                # X坐标
                'y': row[3],                # Y坐标
                'z': row[4],                # Z坐标
                'scale': row[5],            # 缩放比例
                'rotation': row[6],         # 旋转角度
                'flip': row[7],             # 是否翻转
                'data': json.loads(row[8]), # 项目数据
            }

            # 处理像素图项目
            if data['type'] == 'pixmap':                                    # 如果项目类型为像素图
                item = BeePixmapItem(QtGui.QImage())                        # 创建空的像素图项目
                item.pixmap_from_bytes(row[9])                              # 从二进制数据创建像素图
                # 检查图像是否加载成功
                if item.pixmap().isNull():
                    # 如果图像加载失败，创建错误项目
                    item = data['data']['text'] = ( 
                        f'Image could not be loaded: {item.filename}\n'
                        + IMG_LOADING_ERROR_MSG)
                    data['type'] = BeeErrorItem.TYPE                       # 将项目类型设置为错误项类型
                data['item'] = item                                        # 将项目添加到数据字典中

            self.scene.add_item_later(data)             # 稍后将项目添加到场景中
            # 如果有工作线程，更新进度并检查是否取消操作
            if self.worker:
                logger.trace(f'Emit progress: {i}')     # 记录进度信息
                self.worker.progress.emit(i)            # 发送进度信号，包含当前项索引
                if self.worker.canceled:                # 如果工作线程已取消
                    self.worker.finished.emit('', [])   # 发送完成信号，包含空字符串和空列表
                    return                              # 退出循环，停止处理
                # Give main thread time to process items:
                self.worker.msleep(10)                  # 暂停10毫秒，允许主线程处理事件
        if self.worker:                                 # 如果有工作线程
            self.worker.finished.emit(self.filename, [])# 发送完成信号，包含文件名和空列表

    @handle_sqlite_errors
    # 写入数据库中的所有项，包括图片和文本项
    def write(self):
        # 检查是否为只读模式
        if self.readonly:                                                   # 如果数据库为只读模式
            raise sqlite3.OperationalError(                                 # 抛出操作错误异常
                'Attempt to write to a readonly database')
        try:                                                                # 尝试执行写入操作
            self.create_schema_on_new()                                     # 创建新文件时创建数据库架构
            self.write_data()                                               # 写入所有数据
        except Exception as e:                                              # 捕获所有异常
            #处理写入错误
            if self.retry:                                                  # 如果允许重试
                # Trying to recover failed
                raise                                                       # 如果已经重试过一次，则放弃并抛出异常
            else:
                self.retry = True                                           # 第一次失败后，标记为需要重试
                # Try creating file from scratch and save again
                logger.exception(                                           # 尝试从头创建文件并再次保存
                    f'Updating to existing file {self.filename} failed')    # 记录更新失败的异常信息
                self.create_new = True                                      # 标记为创建新文件
                self._close_connection()                                    # 关闭现有连接，以便重新建立连接
                self.write()                                                # 递归调用写入方法，尝试重新创建文件并保存

    # 写入场景数据到数据库
    def write_data(self):
        to_delete = {row[0] for row in self.fetchall('SELECT id from ITEMS')}   # 获取所有需要删除的项目ID
        # We don't want to touch existing items that are displayed as errors:
        keep = {item.original_save_id
                for item in self.scene.items_by_type(BeeErrorItem.TYPE)}        # 获取所有错误项的原始保存ID
        logger.debug(f'Not saving error items: {keep}')                         # 记录不保存错误项的ID
        to_delete = to_delete - keep                                            # 从待删除列表中移除需要保留的项目

        # 获取需要保存的项目列表
        to_save = list(self.scene.items_for_save())
        # 如果有工作线程，发送开始处理信号
        if self.worker:
            self.worker.begin_processing.emit(len(to_save))
        # 遍历所有需要保存的项目
        for i, item in enumerate(to_save):
            logger.debug(f'Saving {item} with id {item.save_id}')   # 记录正在保存的项目信息
            if item.save_id:                                        # 如果项目已存在数据库中
                self.update_item(item)                              # 更新项目数据
                to_delete.remove(item.save_id)                      # 从待删除列表中移除已更新的项目ID
            else:                                                   # 如果项目不在数据库中
                self.insert_item(item)                              # 插入新项目到数据库中
            # 如果有工作线程，发送进度信号，包含当前项索引
            if self.worker:
                self.worker.progress.emit(i)
                # 如果工作线程已取消，跳出循环，停止处理
                if self.worker.canceled:
                    break
        self.delete_items(to_delete)                                # 删除不再需要的项目
        self.ex('VACUUM')                                           # 执行VACUUM命令，优化数据库空间
        self.connection.commit()                                    # 提交事务，确保所有更改生效
        if self.worker:                                             # 如果有工作线程
            self.worker.finished.emit(self.filename, [])            # 发送完成信号，包含文件名和空列表

    # 从数据库中删除指定的项目
    def delete_items(self, to_delete):
        to_delete = [(pk,) for pk in to_delete]                     # 将待删除项目ID转换为元组列表
        self.exmany('DELETE FROM items WHERE id=?', to_delete)      # 执行批量删除项目的SQL语句
        self.exmany('DELETE FROM sqlar WHERE item_id=?', to_delete) # 执行批量删除关联文件的SQL语句
        self.connection.commit()                                    # 提交事务，确保所有更改生效

    # 向数据库中插入新项目
    def insert_item(self, item):
        # 插入项目基本信息到items表
        self.ex(
            'INSERT INTO items (type, x, y, z, scale, rotation, flip, '
            'data) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (item.TYPE, item.pos().x(), item.pos().y(), item.zValue(),  # 插入项目的类型、位置、Z值、缩放比例、旋转角度和翻转状态
             item.scale(), item.rotation(), item.flip(),                # 插入项目的缩放比例、旋转角度和翻转状态
             json.dumps(item.get_extra_save_data())))                   # 插入项目的额外保存数据
        item.save_id = self.cursor.lastrowid                            # 获取新插入项目的ID
        # 如果项目有像素图数据，也保存它
        if hasattr(item, 'pixmap_to_bytes'):
            pixmap, imgformat = item.pixmap_to_bytes()                  # 获取像素图的二进制数据和图像格式
            name = item.get_filename_for_export(imgformat)              # 获取导出文件名
            # 将二进制数据插入到sqlar表
            self.ex(
                'INSERT INTO sqlar (item_id, name, mode, sz, data) '
                'VALUES (?, ?, ?, ?, ?)',
                (item.save_id, name, 0o644, len(pixmap), pixmap))       # 插入像素图数据到sqlar表
        self.connection.commit()                                        # 提交事务，确保所有更改生效

    # 更新数据库中的项目数据
    def update_item(self, item):
        """Update item data.

        We only update the item data, not the pixmap data, as pixmap
        data never changes and is also time-consuming to save.
        """
        # 更新items表中的项目数据
        self.ex(
            'UPDATE items SET x=?, y=?, z=?, scale=?, rotation=?, flip=?, '
            'data=? '
            'WHERE id=?',
            (item.pos().x(), item.pos().y(), item.zValue(), item.scale(), # 更新项目的位置、Z值、缩放比例
             item.rotation(), item.flip(),                                # 更新项目的旋转角度和翻转状态
             json.dumps(item.get_extra_save_data()),                      # 更新项目的额外保存数据
             item.save_id))                                               # 更新项目的ID
        self.connection.commit()                                          # 提交事务，确保所有更改生效
