from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.models.todo_block_index_helper import (
    build_node_block_index as build_node_block_index_for_model,
    resolve_block_index_for_todo as resolve_block_index_for_todo_item,
)
from app.ui.foundation.theme_manager import Colors as ThemeColors


@dataclass
class EventFlowBlockGroup:
    """事件流 BasicBlock 分组的中间结构，避免直接操作嵌套 tuple。"""

    block_index: Optional[int]
    child_ids: List[str]


def build_event_flow_block_groups(
    flow_root_todo: TodoItem,
    flow_root_item: QtWidgets.QTreeWidgetItem,
    todo_map: Dict[str, TodoItem],
    *,
    graph_support: Any,
) -> List[EventFlowBlockGroup]:
    """按 BasicBlock 将事件流根的直接子步骤分组。

    分组规则：
    - 先按原顺序为每个子步骤解析其所在 BasicBlock（可能为 None）；
    - 将相邻且 block_index 相同的步骤聚合为一个 EventFlowBlockGroup；
    - 若所有子步骤均无法解析出 block_index（全为 None），则返回空列表，由调用方退回扁平结构。
    """
    model, _graph_id = graph_support.get_graph_model_for_item(
        item=flow_root_item,
        todo_id=flow_root_todo.todo_id,
        todo_map=todo_map,
    )
    node_block_index = build_node_block_index_for_model(model)

    ordered_children: List[tuple[str, Optional[int]]] = []
    for child_id in flow_root_todo.children:
        child_todo = todo_map.get(child_id)
        if not child_todo:
            continue
        block_index = resolve_block_index_for_todo_item(
            child_todo,
            node_block_index,
        )
        ordered_children.append((child_id, block_index))

    if not ordered_children:
        return []

    has_any_block_info = any(
        block_index is not None for _child_id, block_index in ordered_children
    )
    if not has_any_block_info:
        return []

    groups: List[EventFlowBlockGroup] = []
    current_block_index = ordered_children[0][1]
    current_child_ids: List[str] = [ordered_children[0][0]]

    for child_id, block_index in ordered_children[1:]:
        if block_index == current_block_index:
            current_child_ids.append(child_id)
        else:
            groups.append(
                EventFlowBlockGroup(
                    block_index=current_block_index,
                    child_ids=current_child_ids,
                )
            )
            current_block_index = block_index
            current_child_ids = [child_id]

    groups.append(
        EventFlowBlockGroup(
            block_index=current_block_index,
            child_ids=current_child_ids,
        )
    )
    return groups


def collect_block_node_ids_for_header_item(
    header_item: QtWidgets.QTreeWidgetItem,
    todo_map: Dict[str, TodoItem],
    *,
    graph_support: Any,
) -> List[str]:
    """根据“逻辑块分组”树项推导该块内所有节点 ID 列表。

    仅依赖 BasicBlock 索引；若无法解析出块索引或图模型，则返回空列表。
    """
    if header_item is None:
        return []

    model, _graph_id = graph_support.get_graph_model_for_item(
        header_item,
        "",
        todo_map,
    )
    if model is None:
        return []

    node_block_index = build_node_block_index_for_model(model)
    if not node_block_index:
        return []

    block_index: Optional[int] = None
    child_count = header_item.childCount()
    for child_row in range(child_count):
        child_item = header_item.child(child_row)
        if child_item is None:
            continue
        todo_id = child_item.data(0, Qt.ItemDataRole.UserRole)
        if not todo_id:
            continue
        child_todo = todo_map.get(todo_id)
        if not child_todo:
            continue
        candidate_index = resolve_block_index_for_todo_item(
            child_todo,
            node_block_index,
        )
        if isinstance(candidate_index, int):
            block_index = candidate_index
            break

    if block_index is None:
        return []

    block_node_ids: List[str] = []
    for node_id, index in node_block_index.items():
        if index == block_index:
            block_node_ids.append(node_id)
    return block_node_ids


def create_block_header_item(
    block_index: int,
    group_index: int,
    block_color_hex: str | None = None,
    *,
    rich_segments_role: int,
    marker_role: int,
) -> QtWidgets.QTreeWidgetItem:
    """创建只读的“逻辑块分组”树项，用于包裹同一 BasicBlock 内的步骤。

    Args:
        block_index: 对应的 BasicBlock 索引（从 0 开始）。
        group_index: 逻辑分组序号（同一块被多次打断时用于区分组）。
        block_color_hex: 来自图模型 BasicBlock 的颜色（如 "#FF5E9C"），
            若为空则退回为主题的次文本色。
        rich_segments_role: 任务树富文本 tokens 使用的数据角色（应与委托一致）。
        marker_role: 用于标记该 item 为“块头”的数据角色（必须与 dimmed_role 分离）。
    """
    header_item = QtWidgets.QTreeWidgetItem()
    header_label = f"逻辑块 {block_index + 1}"
    header_item.setText(0, header_label)
    # 标记为分组头：不对应具体 TodoItem
    header_item.setData(0, Qt.ItemDataRole.UserRole, "")
    header_item.setData(0, marker_role, "block_header")
    # 记录块颜色，供高亮与后续样式使用
    if isinstance(block_color_hex, str) and block_color_hex:
        stored_color = block_color_hex
    else:
        stored_color = ThemeColors.TEXT_SECONDARY
    header_item.setData(0, Qt.ItemDataRole.UserRole + 3, stored_color)
    # 分组头不可勾选，仅用于折叠与视觉分隔
    header_flags = header_item.flags()
    header_flags &= ~Qt.ItemFlag.ItemIsUserCheckable
    header_item.setFlags(header_flags)

    header_font = header_item.font(0)
    header_font.setBold(True)
    header_item.setFont(0, header_font)
    header_color = QtGui.QColor(stored_color)
    header_item.setForeground(0, QtGui.QBrush(header_color))

    # 为逻辑块分组头也提供一组富文本 tokens，与任务清单叶子步骤保持一致的“彩色标签”体验。
    def _tint_background_color(hex_color: str) -> str:
        if not isinstance(hex_color, str):
            return ""
        if not (len(hex_color) == 7 and hex_color.startswith("#")):
            return ""
        red_value = int(hex_color[1:3], 16)
        green_value = int(hex_color[3:5], 16)
        blue_value = int(hex_color[5:7], 16)
        mix_ratio = 0.82
        mixed_red = int(red_value + (255 - red_value) * mix_ratio)
        mixed_green = int(green_value + (255 - green_value) * mix_ratio)
        mixed_blue = int(blue_value + (255 - blue_value) * mix_ratio)
        if mixed_red > 255:
            mixed_red = 255
        if mixed_green > 255:
            mixed_green = 255
        if mixed_blue > 255:
            mixed_blue = 255
        return f"#{mixed_red:02X}{mixed_green:02X}{mixed_blue:02X}"

    bg_color = _tint_background_color(stored_color)
    header_tokens: List[Dict[str, Any]] = [
        {
            "text": header_label,
            "color": stored_color,
            "bg": bg_color,
            "bold": True,
        }
    ]
    header_item.setData(0, int(rich_segments_role), header_tokens)
    return header_item


