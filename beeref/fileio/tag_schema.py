"""标签数据表结构定义（适配现有 SQLiteIO 架构）"""
import sqlite3

# 标签表：存储标签基本信息
TAG_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tag_name TEXT NOT NULL UNIQUE,
    tag_group TEXT DEFAULT '默认分组',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# 图像-标签关联表：多对多关系（优化唯一性约束+外键关联）
# 移除对 items 表的外键约束，改为在应用层面确保数据完整性
IMAGE_TAG_RELATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS image_tag_relations (
    relation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id TEXT NOT NULL,  -- 关联图像的save_id（与现有items表的id一致）
    tag_id INTEGER NOT NULL,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE,
    -- 移除对 items 表的外键约束，避免创建表时的依赖问题
    UNIQUE(image_id, tag_id)  -- 强制避免重复关联（核心约束）
)
"""

def init_tag_tables(conn: sqlite3.Connection):
    """初始化标签相关数据表（在数据库连接建立后调用）"""
    # 启用外键约束（关键：确保关联关系完整性）
    conn.execute("PRAGMA foreign_keys = ON")
    
    cursor = conn.cursor()
    try:
        # 创建标签表
        cursor.execute(TAG_TABLE_SCHEMA)
        # 创建图像-标签关联表
        cursor.execute(IMAGE_TAG_RELATION_SCHEMA)
        conn.commit()
        print("✅ 标签数据表初始化成功")
    except sqlite3.Error as e:
        conn.rollback()
        print(f"❌ 标签数据表初始化失败：{e}")
        raise  # 抛出异常便于上层捕获

def check_relation_exists(conn: sqlite3.Connection, image_id: str, tag_id: int) -> bool:
    """检查图像与标签的关联关系是否已存在（快捷方法）"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM image_tag_relations WHERE image_id=? AND tag_id=?",
        (image_id, tag_id)
    )
    return cursor.fetchone() is not None

def create_tag_relation(conn: sqlite3.Connection, image_id: str, tag_id: int) -> bool:
    """创建图像-标签关联（自动处理重复）"""
    if check_relation_exists(conn, image_id, tag_id):
        return True  # 已存在则直接返回成功
    
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO image_tag_relations (image_id, tag_id) VALUES (?, ?)",
            (image_id, tag_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        conn.rollback()
        print(f"❌ 创建关联失败：{e}")
        return False

def delete_tag_relation(conn: sqlite3.Connection, image_id: str, tag_id: int) -> bool:
    """删除图像-标签关联"""
    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM image_tag_relations WHERE image_id=? AND tag_id=?",
            (image_id, tag_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.Error as e:
        conn.rollback()
        print(f"❌ 删除关联失败：{e}")
        return False