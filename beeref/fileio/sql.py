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
    # 使用os.path.splitext分割文件名和扩展名
    return os.path.splitext(path)[1] == '.bee'                       


# 处理SQLite错误
def handle_sqlite_errors(func):
    def wrapper(self, *args, **kwargs):
        try:
            # 尝试执行原始函数
            func(self, *args, **kwargs)                                     
        except Exception as e:   
            # 记录异常日志，包含文件名信息                                           
            logger.exception(f'Error while reading/writing {self.filename}')
            try:                                                            
                # Try to roll back transaction if there is any
                # 检查是否有数据库连接属性
                if (hasattr(self, '_connection')   
                        # 检查是否有未提交的事务                          
                        and self._connection.in_transaction):               
                    self.ex('ROLLBACK')                                     
                    logger.debug('Transaction rolled back') 
            # 捕获SQLite错误                
            except sqlite3.Error as e:                                      
                pass      
            # 关闭数据库连接
            self._close_connection()   
            # 如果有工作线程，则向其发送完成信号并附带错误信息                                     
            if self.worker:                                                 
                self.worker.finished.emit(self.filename, [str(e)])         
            else:                                                           
                raise BeeFileIOError(msg=str(e), filename=self.filename) from e
    # 返回包装后的函数
    return wrapper                                                             

# 定义SQLiteIO类，用于操作SQLite数据库文件
class SQLiteIO:

    # 初始化SQLiteIO类
    def __init__(self, filename, scene, create_new=False, readonly=False,
                 worker=None):
        # 保存场景引用，用于添加或获取项目
        self.scene = scene  
        # 设置是否创建新文件的标志                            
        self.create_new = create_new      
        # 保存数据库文件名               
        self.filename = filename    
        # 设置是否为只读模式                     
        self.readonly = readonly           
        # 保存工作线程引用，用于进度更新              
        self.worker = worker                             
        self.retry = False                               
    # 析构函数
    # 在对象被销毁时调用，确保资源被正确释放
    def __del__(self):
        self._close_connection()                          

    # 关闭数据库连接
    def _close_connection(self):
        # 检查并关闭数据库连接
        if hasattr(self, '_connection'):        
            self._connection.close()           
            delattr(self, '_connection')        
        # 检查并删除游标引用
        if hasattr(self, '_cursor'):            
            delattr(self, '_cursor')          
        # 检查并清理临时目录  
        if hasattr(self, '_tmpdir'):           
            self._tmpdir.cleanup()             
            delattr(self, '_tmpdir')            

    # 建立数据库连接
    def _establish_connection(self):
        # 确保目标目录存在
        dirname = os.path.dirname(self.filename)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)
        
        # 如果需要创建新文件且文件已存在，则删除现有文件
        if (self.create_new                              
                and not self.readonly                    
                and os.path.exists(self.filename)):    
            os.remove(self.filename)                    

        # 如果创建新文件，清除场景中所有项目的保存I
        if self.create_new:                              
            self.scene.clear_save_ids()                 
        # 将文件路径转换为URI格式，确保跨平台兼容性
        uri = pathlib.Path(self.filename).resolve().as_uri()
        # 检查是否为只读模式
        if self.readonly:            
            # 如果是只读模式，添加查询参数以指定为读写模式                       
            uri = f'{uri}?mode=rw'        
        # 建立数据库连接，使用URI格式                  
        self._connection = sqlite3.connect(uri, uri=True)   
        # 创建游标对象，用于执行SQL语句
        self._cursor = self._connection.cursor()             
        # 如果不是创建新文件，则尝试迁移数据库
        if not self.create_new:                             
            try:
                self._migrate()                             
            except Exception as e:                          
                # Updating a file failed; try creating it from scratch instead
                logger.exception('Error migrating bee file: %s', e) 
                self.create_new = True                              
                self._establish_connection()                        

    # 迁移数据库
    def _migrate(self):
        """Migrate database if necessary."""
        # 获取数据库用户版本号
        version = self.fetchone('PRAGMA user_version')[0]           
        logger.debug(f'Found bee file version: {version}')   
        # 检查数据库版本号是否大于等于用户版本号       
        if version >= USER_VERSION:                                 
            logger.debug('Version ok; no migrations necessary')     
            return                                                  
        # 如果版本已经是最新的，不需要迁移
        if self.readonly:
            try:
                # See whether file is writable so we can migrate it directly
                # 设置应用程序ID，确保数据库与应用程序兼容
                self.ex('PRAGMA application_id=%s' % APPLICATION_ID)         
            # 捕获 SQLite 错误异常
            except sqlite3.Error as e:                                  
                # 记录文件不可写日志，建议使用临时副本     
                logger.debug('File not writable; use temporary copy instead')
                self._connection.close()                     
                # 创建临时目录，用于存储迁移后的数据库文件               
                self._tmpdir = tempfile.TemporaryDirectory(           
                    # 设置临时目录前缀，确保与应用程序名称一致       
                    prefix=constants.APPNAME)                                
                tmpname = os.path.join(self._tmpdir.name, 'mig.bee')       
                # 复制原始数据库文件到临时目录  
                shutil.copyfile(self.filename, tmpname)                      
                self._connection = sqlite3.connect(tmpname)    
                # 创建游标对象，用于执行SQL语句              
                self._cursor = self.connection.cursor()         

        # 开始事务，确保迁移的原子性
        self.ex('BEGIN TRANSACTION')         
        # 遍历需要迁移的版本号范围                             
        for i in range(version, USER_VERSION):               
            # 记录迁移信息，包含当前版本号和目标版本号             
            logger.debug(f'Migrating from version {i} to {i + 1}...')     
             # 遍历当前版本号对应的迁移SQL语句列表
            for migration in MIGRATIONS[i + 1]:                          
                self.ex(migration)                      
        # 写入数据库元数据，包括应用程序ID和用户版本号                  
        self.write_meta()                                                 
        self.connection.commit()                                         
        logger.debug('Migration finished')                                

    @property
    # 获取数据库连接属性
    def connection(self):
        if not hasattr(self, '_connection'):   
            self._establish_connection()        
        return self._connection                
    @property
    # 获取数据库游标属性
    def cursor(self):
        if not hasattr(self, '_cursor'):        
            self._establish_connection()        
        return self._cursor                     

    # 执行SQL语句，返回执行结果
    def ex(self, *args, **kwargs):
        return self.cursor.execute(*args, **kwargs)

    # 执行批量SQL语句，返回执行结果
    def exmany(self, *args, **kwargs):
        return self.cursor.executemany(*args, **kwargs)

    # 从数据库游标中获取一条记录，返回记录元组
    def fetchone(self, *args, **kwargs):
        # 执行SQL语句，传入参数和关键字参数
        self.ex(*args, **kwargs)            
        return self.cursor.fetchone()      

    # 从数据库游标中获取所有记录，返回记录列表
    def fetchall(self, *args, **kwargs):
         # 执行SQL语句，传入参数和关键字参数
        self.ex(*args, **kwargs)           
        return self.cursor.fetchall()       

    # 写入数据库元数据，包括应用程序ID和用户版本号
    def write_meta(self):
        # 设置应用程序ID，确保数据库与应用程序兼容
        self.ex('PRAGMA application_id=%s' % APPLICATION_ID)  
        # 设置用户版本，用于版本控制    
        self.ex('PRAGMA user_version=%s' % USER_VERSION)        
        # 启用外键约束，确保数据完整性
        self.ex('PRAGMA foreign_keys=ON')                       

    # 创建新文件时创建数据库架构
    def create_schema_on_new(self):
        if self.create_new:                 
            self.write_meta()              
            # 执行所有架构创建SQL语句
            for schema in SCHEMA:       
                # 执行架构创建SQL语句
                self.ex(schema)             
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
        # 如果有工作线程
        if self.worker:                                   
            # 发送开始处理信号，包含项数
            self.worker.begin_processing.emit(len(rows))    

        # 遍历所有读取的项目数据
        for i, row in enumerate(rows):
             # 构建项目数据字典
            data = {
                'save_id': row[0],          
                'type': row[1],             
                'x': row[2],                
                'y': row[3],               
                'z': row[4],                
                'scale': row[5],           
                'rotation': row[6],        
                'flip': row[7],             
                'data': json.loads(row[8]), 
            }

            # 处理像素图项目
            if data['type'] == 'pixmap':                                   
                item = BeePixmapItem(QtGui.QImage())                       
                item.pixmap_from_bytes(row[9])                              
                # 检查图像是否加载成功
                if item.pixmap().isNull():
                    # 如果图像加载失败，创建错误项目
                    item = data['data']['text'] = ( 
                        f'Image could not be loaded: {item.filename}\n'
                        + IMG_LOADING_ERROR_MSG)
                    data['type'] = BeeErrorItem.TYPE                       
                data['item'] = item                                       

            self.scene.add_item_later(data)            
            # 如果有工作线程，更新进度并检查是否取消操作
            if self.worker:
                # 记录进度信息
                logger.trace(f'Emit progress: {i}')   
                # 发送进度信号，包含当前项索引  
                self.worker.progress.emit(i)            
                if self.worker.canceled:                
                    # 发送完成信号，包含空字符串和空列表
                    self.worker.finished.emit('', [])   
                    return                             
                # Give main thread time to process items:
                self.worker.msleep(10)                  
        if self.worker:                                 
            self.worker.finished.emit(self.filename, [])

    @handle_sqlite_errors
    # 写入数据库中的所有项，包括图片和文本项
    def write(self):
        # 检查是否为只读模式
        if self.readonly:                                                   
            raise sqlite3.OperationalError(                               
                'Attempt to write to a readonly database')
        try:    
            # 创建新文件时创建数据库架构                                                         
            self.create_schema_on_new()                                     
            self.write_data()                                               
        except Exception as e:                                              
            #处理写入错误
            if self.retry:                                                 
                # Trying to recover failed
                raise                                                       
            else:
                self.retry = True                                           
                # Try creating file from scratch and save again
                # 尝试从头创建文件并再次保存
                logger.exception(                                   
                    # 记录更新失败的异常信息        
                    f'Updating to existing file {self.filename} failed')    
                # 标记为创建新文件
                self.create_new = True         
                # 关闭现有连接，以便重新建立连接                             
                self._close_connection() 
                # 递归调用写入方法，尝试重新创建文件并保存                                   
                self.write()                                                
    # 写入场景数据到数据库
    def write_data(self):
        # 获取所有需要删除的项目ID
        to_delete = {row[0] for row in self.fetchall('SELECT id from ITEMS')}   
        # We don't want to touch existing items that are displayed as errors:
        keep = {item.original_save_id
                # 获取所有错误项的原始保存ID
                for item in self.scene.items_by_type(BeeErrorItem.TYPE)}        
        logger.debug(f'Not saving error items: {keep}')   
        # 从待删除列表中移除需要保留的项目                     
        to_delete = to_delete - keep                                            

        # 获取需要保存的项目列表
        to_save = list(self.scene.items_for_save())
        # 如果有工作线程，发送开始处理信号
        if self.worker:
            self.worker.begin_processing.emit(len(to_save))
        # 遍历所有需要保存的项目
        for i, item in enumerate(to_save):
            # 记录正在保存的项目信息
            logger.debug(f'Saving {item} with id {item.save_id}')   
            # 如果项目已存在数据库中
            if item.save_id:                                        
                self.update_item(item)                     
                 # 从待删除列表中移除已更新的项目ID         
                to_delete.remove(item.save_id)                     
            else:                                                   
                self.insert_item(item)                             
            # 如果有工作线程，发送进度信号，包含当前项索引
            if self.worker:
                self.worker.progress.emit(i)
                # 如果工作线程已取消，跳出循环，停止处理
                if self.worker.canceled:
                    break
        self.delete_items(to_delete)                              
        # 执行VACUUM命令，优化数据库空间  
        self.ex('VACUUM')                                           
        # 提交事务，确保所有更改生效
        self.connection.commit()                                    
        # 如果有工作线程
        if self.worker:                                             
            # 发送完成信号，包含文件名和空列表
            self.worker.finished.emit(self.filename, [])      

    # 从数据库中删除指定的项目
    def delete_items(self, to_delete):
        # 将待删除项目ID转换为元组列表
        to_delete = [(pk,) for pk in to_delete]                     
        # 执行批量删除项目的SQL语句
        self.exmany('DELETE FROM items WHERE id=?', to_delete)  
        # 执行批量删除关联文件的SQL语句    
        self.exmany('DELETE FROM sqlar WHERE item_id=?', to_delete) 
        # 提交事务，确保所有更改生效
        self.connection.commit()    

    # 向数据库中插入新项目
    def insert_item(self, item):
        # 插入项目基本信息到items表
        self.ex(
            'INSERT INTO items (type, x, y, z, scale, rotation, flip, '
            'data) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (item.TYPE, item.pos().x(), item.pos().y(), item.zValue(),  
              # 插入项目的缩放比例、旋转角度和翻转状态
             item.scale(), item.rotation(), item.flip(),               
             # 插入项目的额外保存数据
             json.dumps(item.get_extra_save_data())))   
         # 获取新插入项目的ID                
        item.save_id = self.cursor.lastrowid                           
        # 如果项目有像素图数据，也保存它
        if hasattr(item, 'pixmap_to_bytes'):
            pixmap, imgformat = item.pixmap_to_bytes()                 
            name = item.get_filename_for_export(imgformat)             
            # 将二进制数据插入到sqlar表
            self.ex(
                'INSERT INTO sqlar (item_id, name, mode, sz, data) '
                'VALUES (?, ?, ?, ?, ?)',
                # 插入像素图数据到sqlar表
                (item.save_id, name, 0o644, len(pixmap), pixmap))       
            # 提交事务，确保所有更改生效
        self.connection.commit()                                        

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
            # 更新项目的位置、Z值、缩放比例
            (item.pos().x(), item.pos().y(), item.zValue(), item.scale(), 
             # 更新项目的旋转角度和翻转状态
             item.rotation(), item.flip(),                           
             # 更新项目的额外保存数据     
             json.dumps(item.get_extra_save_data()),             
             # 更新项目的ID         
             item.save_id))                         
        # 提交事务，确保所有更改生效                      
        self.connection.commit()                                          
