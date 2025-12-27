"""标签功能核心管理器（适配BeeRef原生BeePixmapItem）"""
import logging
from typing import List, Dict, Optional
import sqlite3

from PyQt6.QtCore import QObject, pyqtSignal  # 新增导入：支持Qt信号机制
from beeref.items import BeePixmapItem  # 替换ImageItem为实际的图像项类
from beeref.fileio.tag_repository import TagRepository

logger = logging.getLogger(__name__)

class TagManager(QObject):  # 核心修改：继承QObject以支持信号
    # 新增信号：标签列表更新时触发（传递标签列表）
    tags_updated = pyqtSignal(list)
    
    def __init__(self, db_conn: sqlite3.Connection):
        super().__init__()  # 初始化QObject父类
        # 初始化标签仓库（依赖sqlite3连接）
        self.tag_repo = TagRepository(db_conn)
        # 存储所有图像项（BeePixmapItem）
        self.all_images: List[BeePixmapItem] = []
        # 筛选信号回调存储（用于通知场景更新显示）
        self._filter_callbacks = []

    @property
    def filter_applied(self):
        """模拟Qt信号：筛选完成后触发（适配原有信号绑定逻辑）"""
        return self

    def connect(self, callback):
        """绑定筛选完成回调（模拟Qt信号connect）"""
        self._filter_callbacks.append(callback)

    def load_tags(self):
        """加载所有标签（刷新标签列表），并触发tags_updated信号"""
        tags = self.tag_repo.get_all_tags()
        self.tags_updated.emit(tags)  # 触发标签更新信号，通知UI刷新
        return tags

    # 新增：适配外部调用的get_all_tags方法（解决AttributeError）
    def get_all_tags(self) -> List[Dict]:
        """获取所有标签（对外暴露的统一接口）"""
        return self.load_tags()  # 复用load_tags逻辑，保证数据一致性

    def create_tag(self, tag_name: str, tag_group: str = "默认分组") -> int:
        """创建标签（调用仓库层），创建后触发标签更新信号"""
        tag_id = self.tag_repo.create_tag(tag_name, tag_group)
        self.load_tags()  # 创建标签后自动刷新列表并触发信号
        return tag_id

    def add_tags_to_image(self, image: BeePixmapItem, tag_ids: List[int]):
        """为图像添加多个标签"""
        if not hasattr(image, 'save_id') or image.save_id is None:
            logger.warning(f"图像{image}无有效save_id，无法关联标签")
            return
        
        image_id = str(image.save_id)  # 统一转换为字符串（适配数据库存储）
        for tag_id in tag_ids:
            self.tag_repo.add_image_tag_relation(image_id, tag_id)
        logger.debug(f"图像{image}关联标签ID：{tag_ids}")

    def get_image_tags(self, image_id: str) -> List[Dict]:
        """获取指定图像的所有标签"""
        return self.tag_repo.get_image_tags(image_id)

    def apply_tag_filter(self, tag_ids: List[int]):
        """应用标签筛选：显示关联指定标签的图像，隐藏其他"""
        # 1. 获取需要显示的图像ID列表
        show_image_ids = set()
        for tag_id in tag_ids:
            show_image_ids.update(self.tag_repo.get_tag_images(tag_id))
        
        # 2. 遍历所有图像项，设置显示/隐藏
        filtered_ids = []
        for img in self.all_images:
            img_id = str(img.save_id) if img.save_id else ""
            should_show = img_id in show_image_ids or not tag_ids  # 无筛选时显示所有
            img.setVisible(should_show)
            if should_show:
                filtered_ids.append(img_id)
        
        # 3. 触发筛选完成回调（通知场景更新）
        for callback in self._filter_callbacks:
            callback(filtered_ids)

    def export_tagged_images(self, tag_id: int, export_path: str, export_params: Dict) -> bool:
        """按标签导出图像（适配BeePixmapItem的导出逻辑）"""
        try:
            # 获取该标签关联的所有图像ID
            image_ids = self.tag_repo.get_tag_images(tag_id)
            if not image_ids:
                logger.warning(f"标签ID{tag_id}无关联图像")
                return False

            # 遍历图像项，执行导出
            export_count = 0
            for img in self.all_images:
                img_id = str(img.save_id) if img.save_id else ""
                if img_id in image_ids and isinstance(img, BeePixmapItem):
                    # 调用BeePixmapItem原生的导出逻辑
                    img_format = export_params.get("format", "PNG")
                    quality = export_params.get("quality", 90)
                    
                    # 生成导出文件名
                    save_id = img.save_id or export_count
                    filename = img.get_filename_for_export(img_format.lower(), save_id)
                    full_path = f"{export_path}/{filename}"

                    # 转换为字节并保存
                    pixmap_bytes, _ = img.pixmap_to_bytes(
                        apply_grayscale=export_params.get("grayscale", False),
                        apply_crop=export_params.get("crop", False)
                    )
                    with open(full_path, 'wb') as f:
                        f.write(pixmap_bytes)
                    
                    export_count += 1
                    logger.debug(f"导出图像{img}到{full_path}")

            logger.info(f"成功导出{export_count}张图像到{export_path}")
            return export_count > 0

        except Exception as e:
            logger.error(f"按标签导出失败：{e}", exc_info=True)
            return False

    # 兼容原有代码的快捷方法
    def add_tags_to_images(self, images: List[BeePixmapItem], tag_ids: List[int]):
        """批量为图像添加标签"""
        for img in images:
            self.add_tags_to_image(img, tag_ids)

    def remove_tag_from_image(self, image: BeePixmapItem, tag_id: int):
        """移除图像的指定标签"""
        if not image.save_id:
            return
        self.tag_repo.remove_image_tag_relation(str(image.save_id), tag_id)

    def get_all_tags_with_count(self) -> List[Dict]:
        """获取所有标签及关联图像数量"""
        tags = self.load_tags()  # 触发tags_updated信号
        for tag in tags:
            tag['image_count'] = len(self.tag_repo.get_tag_images(tag['tag_id']))
        return tags