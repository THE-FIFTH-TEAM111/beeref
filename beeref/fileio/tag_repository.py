import sqlite3
import logging
from typing import List, Optional, Dict
from beeref.fileio.tag_schema import init_tag_tables

# 新增日志记录器
logger = logging.getLogger(__name__)

class TagRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        # 初始化标签数据表（首次使用时创建）
        init_tag_tables(conn)
        # 优化数据库性能：启用外键约束（关键！确保关联关系生效）
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.cur = self.conn.cursor()  # 复用游标，减少创建开销

    # 标签CRUD
    def create_tag(self, tag_name: str, tag_group: str = "默认分组") -> int:
        """创建标签（重复名称自动加序号）"""
        # 参数校验：空名称直接返回
        if not tag_name or tag_name.strip() == "":
            logger.error("标签名称不能为空")
            raise ValueError("标签名称不能为空")
        
        base_name = tag_name.strip()
        suffix = 1
        tag_name = base_name
        
        try:
            while True:
                try:
                    self.cur.execute("""
                        INSERT INTO tags (tag_name, tag_group)
                        VALUES (?, ?)
                    """, (tag_name, tag_group))
                    self.conn.commit()
                    tag_id = self.cur.lastrowid
                    logger.info(f"创建标签成功：ID={tag_id}, 名称={tag_name}, 分组={tag_group}")
                    return tag_id
                except sqlite3.IntegrityError:
                    # 名称重复，添加序号
                    tag_name = f"{base_name}-{suffix}"
                    suffix += 1
                    logger.debug(f"标签名称重复，尝试新名称：{tag_name}")
        except Exception as e:
            self.conn.rollback()  # 出错回滚事务
            logger.error(f"创建标签失败：{e}", exc_info=True)
            raise

    def get_all_tags(self) -> List[Dict]:
        """获取所有标签（含分组）"""
        try:
            self.cur.execute("SELECT * FROM tags ORDER BY tag_group, tag_name")
            columns = [desc[0] for desc in self.cur.description]
            tags = [dict(zip(columns, row)) for row in self.cur.fetchall()]
            logger.debug(f"获取标签列表：共{len(tags)}个标签")
            return tags
        except Exception as e:
            logger.error(f"获取标签列表失败：{e}", exc_info=True)
            return []

    def delete_tag(self, tag_id: int) -> bool:
        """删除标签（用于撤销操作）"""
        try:
            self.cur.execute("DELETE FROM tags WHERE tag_id = ?", (tag_id,))
            self.conn.commit()
            success = self.cur.rowcount > 0
            if success:
                logger.info(f"删除标签成功：ID={tag_id}")
            else:
                logger.warning(f"删除标签失败：ID={tag_id}不存在")
            return success
        except Exception as e:
            self.conn.rollback()
            logger.error(f"删除标签失败：{e}", exc_info=True)
            return False

    # 图像-标签关联
    def add_image_tag_relation(self, image_id: str, tag_id: int) -> bool:
        """为图像关联标签（防重复插入）"""
    # 参数校验：确保tag_id是正整数
        if not image_id or not isinstance(tag_id, int) or tag_id <= 0:
            logger.error(f"关联参数无效：image_id={image_id}, tag_id={tag_id}")
            return False
    
        try:
        # 先检查是否已关联，避免重复插入
            self.cur.execute("""
                SELECT 1 FROM image_tag_relations 
                WHERE image_id=? AND tag_id=?
            """, (image_id, tag_id))
        
            if self.cur.fetchone():
                logger.debug(f"图片{image_id}已关联标签{tag_id}，跳过插入")
                return True  # 已关联视为“成功”
        
        # 插入关联关系
            self.cur.execute("""
                INSERT INTO image_tag_relations (image_id, tag_id)
                VALUES (?, ?)
            """, (image_id, tag_id))
        
            self.conn.commit()
            logger.info(f"图片{image_id}关联标签{tag_id}成功")
            return True
        except sqlite3.IntegrityError as e:
            self.conn.rollback()
            logger.error(f"关联失败：标签{tag_id}不存在或外键约束失败 - {e}")
            return False
        except Exception as e:
            self.conn.rollback()
            logger.error(f"图片{image_id}关联标签{tag_id}失败：{e}", exc_info=True)
            return False

    def get_image_tags(self, image_id: str) -> List[Dict]:
        """获取某图像的所有标签"""
        if not image_id:
            logger.error("image_id不能为空")
            return []
        
        try:
            self.cur.execute("""
                SELECT t.* FROM tags t
                JOIN image_tag_relations r ON t.tag_id = r.tag_id
                WHERE r.image_id = ?
            """, (image_id,))
            columns = [desc[0] for desc in self.cur.description]
            tags = [dict(zip(columns, row)) for row in self.cur.fetchall()]
            logger.debug(f"图片{image_id}关联的标签：{tags}")
            return tags
        except Exception as e:
            logger.error(f"获取图片{image_id}的标签失败：{e}", exc_info=True)
            return []

    def get_tag_images(self, tag_id: int) -> List[str]:
        """获取某标签关联的所有图像ID"""
        if not isinstance(tag_id, int) or tag_id <= 0:
            logger.error(f"标签ID无效：{tag_id}")
            return []
        
        try:
            self.cur.execute("""
                SELECT image_id FROM image_tag_relations
                WHERE tag_id = ?
            """, (tag_id,))
            image_ids = [row[0] for row in self.cur.fetchall()]
            logger.debug(f"标签{tag_id}关联的图片ID：{image_ids}")
            return image_ids
        except Exception as e:
            logger.error(f"获取标签{tag_id}关联的图片失败：{e}", exc_info=True)
            return []

    def remove_image_tag_relation(self, image_id: str, tag_id: int) -> bool:
        """解除图像与标签的关联"""
        if not image_id or not isinstance(tag_id, int):
            logger.error(f"解除关联参数无效：image_id={image_id}, tag_id={tag_id}")
            return False
        
        try:
            self.cur.execute("""
                DELETE FROM image_tag_relations
                WHERE image_id = ? AND tag_id = ?
            """, (image_id, tag_id))
            self.conn.commit()
            success = self.cur.rowcount > 0
            if success:
                logger.info(f"图片{image_id}解除标签{tag_id}关联成功")
            else:
                logger.warning(f"图片{image_id}未关联标签{tag_id}，无需解除")
            return success
        except Exception as e:
            self.conn.rollback()
            logger.error(f"图片{image_id}解除标签{tag_id}关联失败：{e}", exc_info=True)
            return False