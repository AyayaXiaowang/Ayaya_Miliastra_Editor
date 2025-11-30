"""UI 控件组模板树构建辅助。"""

from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional, Union

from PyQt6 import QtCore, QtWidgets

from engine.configs.components.ui_control_group_model import UIControlGroupTemplate

TreeParent = Union[QtWidgets.QTreeWidget, QtWidgets.QTreeWidgetItem]
TemplatePredicate = Callable[[UIControlGroupTemplate], bool]


def is_custom_template(template: UIControlGroupTemplate) -> bool:
    """判断模板是否为自定义模板（无内建部件）。"""
    return not any(widget.is_builtin for widget in template.widgets)


def build_template_tree_section(
    parent: TreeParent,
    templates: Dict[str, UIControlGroupTemplate],
    root_text: str,
    predicate: TemplatePredicate | None = None,
    *,
    query: str | None = None,
) -> QtWidgets.QTreeWidgetItem:
    """在树控件下创建一个带筛选条件的模板分组。"""
    normalized_query = (query or "").casefold()
    root = QtWidgets.QTreeWidgetItem(parent)
    root.setText(0, root_text)
    root.setExpanded(True)

    sorted_items = sorted(
        templates.items(),
        key=lambda pair: pair[1].template_name.casefold(),
    )
    for template_id, template in sorted_items:
        if predicate and not predicate(template):
            continue
        if normalized_query and normalized_query not in template.template_name.casefold():
            continue
        item = QtWidgets.QTreeWidgetItem()
        item.setText(0, template.template_name)
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, template_id)
        root.addChild(item)

    return root


def iter_template_preview_configs(
    template: UIControlGroupTemplate,
    *,
    overrides: Optional[Dict[str, Any]] = None,
) -> Iterable[Dict[str, Any]]:
    """根据模板生成用于预览画布的控件配置。"""
    overrides = overrides or {}
    for widget in template.widgets:
        widget_config = widget.serialize()
        if overrides:
            widget_config.update(overrides)
        yield widget_config


def apply_template_translation(template: UIControlGroupTemplate, *, x: float, y: float) -> bool:
    """平移控件组与内部部件位置，若无变化返回 False。"""
    previous_x, previous_y = template.group_position
    delta_x = x - previous_x
    delta_y = y - previous_y
    if delta_x == 0 and delta_y == 0:
        return False
    template.group_position = (x, y)
    for widget in template.widgets:
        widget.position = (
            widget.position[0] + delta_x,
            widget.position[1] + delta_y,
        )
    return True


def apply_template_resize(
    template: UIControlGroupTemplate,
    *,
    width: float,
    height: float,
) -> bool:
    """缩放控件组与内部部件，若尺寸未变返回 False。"""
    old_width, old_height = template.group_size
    if width == old_width and height == old_height:
        return False
    template.group_size = (width, height)
    width_ratio = width / old_width if old_width else 1.0
    height_ratio = height / old_height if old_height else 1.0
    origin_x, origin_y = template.group_position
    for widget in template.widgets:
        rel_x = widget.position[0] - origin_x
        rel_y = widget.position[1] - origin_y
        widget.position = (
            origin_x + rel_x * width_ratio,
            origin_y + rel_y * height_ratio,
        )
        widget.size = (
            widget.size[0] * width_ratio,
            widget.size[1] * height_ratio,
        )
    return True


def translate_widget_in_store(store, widget_id: str, *, x: float, y: float) -> tuple[bool, Optional[str]]:
    """在 store 中平移指定控件，返回是否有变更及模板 ID。"""
    template, _ = store.find_widget(widget_id)
    if not template:
        return False, None
    if apply_template_translation(template, x=x, y=y):
        template.updated_at = datetime.now().isoformat()
        return True, template.template_id
    return False, template.template_id


def resize_widget_in_store(store, widget_id: str, *, width: float, height: float) -> tuple[bool, Optional[str]]:
    """在 store 中缩放指定控件，返回是否有变更及模板 ID。"""
    template, _ = store.find_widget(widget_id)
    if not template:
        return False, None
    if apply_template_resize(template, width=width, height=height):
        template.updated_at = datetime.now().isoformat()
        return True, template.template_id
    return False, template.template_id
