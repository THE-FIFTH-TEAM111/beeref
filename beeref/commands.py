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

from PyQt6 import QtCore, QtGui


class InsertItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, position=None, ignore_first_redo=False):
        super().__init__('Insert items')
        self.scene = scene
        self.items = items
        self.position = position
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        self.scene.deselect_all_items()
        if self.position:
            self.old_positions = []
            rect = self.scene.itemsBoundingRect(items=self.items)
            for item in self.items:
                self.old_positions.append(item.pos())
                item.setPos(item.pos() + self.position - rect.center())
        for item in self.items:
            self.scene.addItem(item)
            item.setSelected(True)
            item.bring_to_front()

    def undo(self):
        self.scene.deselect_all_items()
        for item in self.items:
            self.scene.removeItem(item)
        if self.position:
            for item, pos in zip(self.items, self.old_positions):
                item.setPos(pos)


class DeleteItems(QtGui.QUndoCommand):
    def __init__(self, scene, items, view=None):
        super().__init__('Delete items')
        self.scene = scene
        self.items = items
        self.view = view

    def redo(self):
        for item in self.items:
            self.scene.removeItem(item)
        if self.view:
            self.view.update_menu_and_actions()

    def undo(self):
        self.scene.deselect_all_items()
        for item in self.items:
            item.setSelected(True)
            self.scene.addItem(item)
        # 如果提供了视图，更新收藏菜单
        if self.view:
            self.view.update_menu_and_actions()


class MoveItemsBy(QtGui.QUndoCommand):

    def __init__(self, items, delta, ignore_first_redo=False):
        super().__init__('Move items')
        self.items = items
        self.delta = delta
        self.ignore_first_redo = ignore_first_redo

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.moveBy(self.delta.x(), self.delta.y())

    def undo(self):
        for item in self.items:
            item.moveBy(-self.delta.x(), -self.delta.y())


class ScaleItemsBy(QtGui.QUndoCommand):
    """Scale items by a given factor around the given anchor."""

    def __init__(self, items, factor, anchor, ignore_first_redo=False):
        super().__init__('Scale items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.factor = factor
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setScale(item.scale() * self.factor,
                          item.mapFromScene(self.anchor))

    def undo(self):
        for item in self.items:
            item.setScale(item.scale() / self.factor,
                          item.mapFromScene(self.anchor))


class RotateItemsBy(QtGui.QUndoCommand):
    """Rotate items by a given delta around the given anchor."""

    def __init__(self, items, delta, anchor, ignore_first_redo=False):
        super().__init__('Rotate items')
        self.ignore_first_redo = ignore_first_redo
        self.items = items
        self.delta = delta
        self.anchor = anchor

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return
        for item in self.items:
            item.setRotation(
                item.rotation() + self.delta * item.flip(),
                item.mapFromScene(self.anchor))

    def undo(self):
        for item in self.items:
            item.setRotation(item.rotation() - self.delta * item.flip(),
                             item.mapFromScene(self.anchor))


class NormalizeItems(QtGui.QUndoCommand):

    def __init__(self, items, scale_factors):
        super().__init__('Normalize items')
        self.items = items
        self.scale_factors = scale_factors

    def redo(self):
        self.old_scale_factors = []
        for item, factor in zip(self.items, self.scale_factors):
            self.old_scale_factors.append(item.scale())
            item.setScale(item.scale() * factor, item.center)

    def undo(self):
        for item, factor in zip(self.items, self.old_scale_factors):
            item.setScale(factor, item.center)


class FlipItems(QtGui.QUndoCommand):

    def __init__(self, items, anchor, vertical):
        super().__init__('Flip items')
        self.items = items
        self.anchor = anchor
        self.vertical = vertical

    def redo(self):
        for item in self.items:
            item.do_flip(self.vertical, item.mapFromScene(self.anchor))

    def undo(self):
        self.redo()


class ResetScale(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Scale')
        self.items = items

    def redo(self):
        self.old_scale_factors = []
        for item in self.items:
            self.old_scale_factors.append(item.scale())
            item.setScale(1, anchor=item.center)

    def undo(self):
        for item, scale_factor in zip(self.items, self.old_scale_factors):
            item.setScale(scale_factor, anchor=item.center)


class ResetRotation(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Rotation')
        self.items = items

    def redo(self):
        self.old_rotations = []
        for item in self.items:
            self.old_rotations.append(item.rotation())
            item.setRotation(0, anchor=item.center)

    def undo(self):
        for item, rotation in zip(self.items, self.old_rotations):
            item.setRotation(rotation, anchor=item.center)


class ResetFlip(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Flip')
        self.items = items

    def redo(self):
        self.old_flips = []
        for item in self.items:
            self.old_flips.append(item.flip())
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, flip in zip(self.items, self.old_flips):
            if flip == -1:
                item.do_flip(anchor=item.center)


class ResetCrop(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset Crop')
        self.items = [item for item in items if item.is_image]

    def redo(self):
        self.old_crops = []
        for item in self.items:
            self.old_crops.append(item.crop)
            item.reset_crop()

    def undo(self):
        for item, crop in zip(self.items, self.old_crops):
            item.crop = crop


class ResetTransforms(QtGui.QUndoCommand):

    def __init__(self, items):
        super().__init__('Reset All Transformations')
        self.items = items

    def redo(self):
        self.old_values = []
        for item in self.items:
            values = {
                'scale': item.scale(),
                'rotation': item.rotation(),
                'flip': item.flip(),
            }
            if item.is_image:
                values['crop'] = item.crop
                item.reset_crop()
            self.old_values.append(values)

            item.setScale(1, anchor=item.center)
            item.setRotation(0, anchor=item.center)
            if item.flip() == -1:
                item.do_flip(anchor=item.center)

    def undo(self):
        for item, old in zip(self.items, self.old_values):
            item.setScale(old['scale'], anchor=item.center)
            item.setRotation(old['rotation'], anchor=item.center)
            if old['flip'] == -1:
                item.do_flip(anchor=item.center)
            if item.is_image:
                item.crop = old['crop']


class ArrangeItems(QtGui.QUndoCommand):

    def __init__(self, scene, items, positions):
        super().__init__('Arrange items')
        self.scene = scene
        self.items = items
        self.positions = positions

    def redo(self):
        self.old_positions = []
        for item, pos in zip(self.items, self.positions):
            self.old_positions.append(item.pos())
            orig_topleft = item.mapToScene(QtCore.QPointF(0, 0))
            rect_topleft = self.scene.itemsBoundingRect(
                items=[item]).topLeft()
            item.setPos(pos + orig_topleft - rect_topleft)

    def undo(self):
        for item, pos in zip(self.items, self.old_positions):
            item.setPos(pos)


class CropItem(QtGui.QUndoCommand):
    def __init__(self, item, crop):
        super().__init__('Crop item')
        self.item = item
        self.crop = crop

    def redo(self):
        self.old_crop = self.item.crop
        self.item.crop = self.crop

    def undo(self):
        self.item.crop = self.old_crop


class ChangeText(QtGui.QUndoCommand):

    def __init__(self, item, new_text, old_text):
        super().__init__('Change text')
        self.item = item
        self.new_text = new_text
        self.old_text = old_text

    def redo(self):
        self.item.setPlainText(self.new_text)

    def undo(self):
        self.item.setPlainText(self.old_text)


class ChangeOpacity(QtGui.QUndoCommand):
    """Change opacity on images."""

    def __init__(self, items, opacity, ignore_first_redo=False):
        super().__init__('Change Opacity')
        self.ignore_first_redo = ignore_first_redo
        self.items = list(filter(lambda item: item.is_image, items))
        self.opacity = opacity
        self.old_opacities = [item.opacity() for item in items]

    def redo(self):
        if self.ignore_first_redo:
            self.ignore_first_redo = False
            return

        for item in self.items:
            item.setOpacity(self.opacity)

    def undo(self):
        for item, opacity in zip(self.items, self.old_opacities):
            item.setOpacity(opacity)


class ToggleGrayscale(QtGui.QUndoCommand):
    """Toggle grayscale mode on images."""

    def __init__(self, items, grayscale):
        super().__init__('Toggle Grayscale')
        self.items = list(filter(lambda item: item.is_image, items))
        self.grayscale = grayscale
        self.old_grayscales = [item.grayscale for item in items]

    def redo(self):
        for item in self.items:
            item.grayscale = self.grayscale

    def undo(self):
        for item, grayscale in zip(self.items, self.old_grayscales):
            item.grayscale = grayscale

#===================新增===========================
from beeref.tag_manager import TagManager  # 保留TagManager导入（核心依赖）

class AddTagCommand(QtGui.QUndoCommand):
    """添加标签的命令（支持撤销/重做）"""
    def __init__(self, tag_manager: TagManager, tag_name: str, tag_group: str = "默认分组"):
        super().__init__(f'添加标签：{tag_name}')
        self.tag_manager = tag_manager
        self.tag_name = tag_name
        self.tag_group = tag_group
        self.tag_id = -1  # 后续存储创建的标签ID

    def redo(self):
        """执行添加标签"""
        self.tag_id = self.tag_manager.create_tag(self.tag_name, self.tag_group)

    def undo(self):
        """撤销：删除标签"""
        cursor = self.tag_manager.tag_repo.conn.cursor()
        # 直接写死表名（替代TagTable.TABLE_NAME），与tag_schema.py中定义的表名一致
        cursor.execute("DELETE FROM tags WHERE tag_id = ?", (self.tag_id,))
        self.tag_manager.tag_repo.conn.commit()
        self.tag_manager.load_tags()  # 刷新标签列表
# ------------------------------
# 新增：更新图片Pixmap的撤销命令（用于水印操作）
# ------------------------------
class UpdatePixmap(QtGui.QUndoCommand):
    def __init__(self, item, new_pixmap):
        super().__init__("修改图片")
        self.item = item
        self.old_pixmap = item.pixmap()
        self.new_pixmap = new_pixmap

    def redo(self):
        self.item.setPixmap(self.new_pixmap)

    def undo(self):
        self.item.setPixmap(self.old_pixmap)
# 新增：切换收藏状态的撤销命令
class ToggleFavorite(QtGui.QUndoCommand):
    """Toggle favorite status of selected items."""
    
    def __init__(self, items, scene, is_favorite=None):
        action_text = 'Toggle Favorite' if is_favorite is None else \
                     'Mark as Favorite' if is_favorite else 'Unmark as Favorite'
        super().__init__(action_text)
        self.items = items
        self.scene = scene
        self.old_states = {item: item.favorite for item in items}
        self.new_state = is_favorite
        
    def redo(self):
        for item in self.items:
            if hasattr(item, 'favorite'):
                item.favorite = not item.favorite if self.new_state is None else self.new_state
        self.scene.update()
        
    def undo(self):
        for item, old_state in self.old_states.items():
            if hasattr(item, 'favorite'):
                item.favorite = old_state
        self.scene.update()
