# 数据库版本号，用于跟踪数据库结构的更改
USER_VERSION = 2
# SQLite数据库的应用程序ID，用于标识特定应用程序的数据库文件
APPLICATION_ID = 2060242126


# 数据库架构定义，包含创建表的SQL语句列表
SCHEMA = [
    # 创建items表，存储应用中的所有项目信息
    """
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,  # 主键，唯一标识每个项目
        type TEXT NOT NULL,      # 项目类型，如图片、文本等
        x REAL DEFAULT 0,        # X坐标位置
        y REAL DEFAULT 0,        # Y坐标位置
        z REAL DEFAULT 0,        # Z轴位置，用于确定项目的显示顺序
        scale REAL DEFAULT 1,    # 缩放比例
        rotation REAL DEFAULT 0, # 旋转角度（以度为单位）
        flip INTEGER DEFAULT 1,  # 翻转状态，用于水平或垂直翻转项目
        data JSON                # JSON格式的数据，存储项目的其他属性
    )
    """,
    # 创建sqlar表，用于存储与项目关联的二进制数据
    """
    CREATE TABLE sqlar (
        name TEXT PRIMARY KEY,   # 文件名作为主键
        item_id INTEGER NOT NULL UNIQUE, # 关联的items表中的项目ID
        mode INT,                # 文件模式
        mtime INT default current_timestamp, # 修改时间戳
        sz INT,                  # 文件大小
        data BLOB,               # 二进制数据内容
        FOREIGN KEY (item_id)    # 外键约束，关联items表
          REFERENCES items (id)
             ON DELETE CASCADE   # 级联删除，当items表中的记录被删除时，相关的sqlar记录也会被删除
             ON UPDATE NO ACTION # 禁止更新关联字段
    )
    """,
]


# 数据库迁移定义，键为目标版本号，值为实现该版本升级所需的SQL语句列表
MIGRATIONS = {
    # 从版本1迁移到版本2的SQL语句
    2: [
        "ALTER TABLE items ADD COLUMN data JSON",            # 添加JSON类型的data列
        "UPDATE items SET data = json_object('filename', filename)",  # 将原有的filename数据迁移到新的JSON格式中
    ],
}
