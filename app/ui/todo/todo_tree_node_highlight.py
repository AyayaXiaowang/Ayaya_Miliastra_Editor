from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.models.todo_detail_info_accessors import get_detail_type, get_node_id
from app.ui.foundation.theme_manager import Colors as ThemeColors
from app.ui.todo.todo_config import StepTypeRules


class TodoTreeNodeHighlighter:
    """负责“从图到步骤”的反向联动：高亮相关步骤、置灰无关步骤。

    该类不持有业务状态（如当前高亮的 todo_id 集合），由上层 Presenter
    （例如 TodoTreeManager）维护并在调用前后同步状态字段，便于测试与编排层读取。
    """

    def __init__(
        self,
        tree: QtWidgets.QTreeWidget,
        *,
        rich_segments_role: int,
        dimmed_role: int,
    ) -> None:
        self._tree = tree
        self._rich_segments_role = rich_segments_role
        self._dimmed_role = dimmed_role

    def collect_related_todos_for_node(
        self,
        node_id: str,
        *,
        todos: List[TodoItem],
    ) -> List[TodoItem]:
        """返回与给定节点 ID 相关的所有图步骤 Todo。"""
        if not node_id:
            return []
        normalized = str(node_id)
        related: List[TodoItem] = []
        for todo in todos:
            detail_info: Dict[str, Any] = todo.detail_info or {}
            detail_type = get_detail_type(detail_info)
            if not StepTypeRules.is_graph_step(detail_type):
                continue
            if self.is_todo_related_to_node(detail_info, normalized):
                related.append(todo)
        return related

    def highlight_steps_for_node(
        self,
        node_id: str,
        *,
        todos: List[TodoItem],
        todo_map: Dict[str, TodoItem],
        item_map: Dict[str, QtWidgets.QTreeWidgetItem],
        anchor_todo_id: Optional[str] = None,
    ) -> Set[str]:
        """为与 node_id 相关的步骤应用高亮与置灰。

        返回：被高亮的 todo_id 集合（空集合表示没有任何相关步骤）。
        """
        if not node_id:
            return set()

        normalized = str(node_id)
        highlight_ids: Set[str] = set()

        for todo in todos:
            detail_info: Dict[str, Any] = todo.detail_info or {}
            detail_type = get_detail_type(detail_info)
            if not StepTypeRules.is_graph_step(detail_type):
                continue
            if not self.is_todo_related_to_node(detail_info, normalized):
                continue

            todo_id = todo.todo_id
            item = item_map.get(todo_id)
            if item is None:
                continue

            is_anchor = bool(anchor_todo_id and todo_id == anchor_todo_id)
            self._apply_node_highlight_to_item(item, is_anchor=is_anchor)
            highlight_ids.add(todo_id)

        if highlight_ids:
            self._dim_unrelated_steps(
                related_ids=highlight_ids,
                todo_map=todo_map,
            )

        return highlight_ids

    def apply_node_highlight_to_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
        *,
        is_anchor: bool,
    ) -> None:
        """对单个树项应用“节点联动高亮”样式。

        说明：
        - 该方法只负责视觉叠加（背景 + tokens 前缀），不做整树遍历或状态维护；
        - 上层（TodoTreeManager）应负责差量更新与 dimmed_role 的写入。
        """
        self._apply_node_highlight_to_item(item, is_anchor=is_anchor)

    def clear_node_highlight_from_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """清除单个树项上的“节点联动高亮”样式（背景 + tokens 前缀）。"""
        if item is None:
            return

        # 清理背景色（恢复为默认，由样式/选中态控制）
        item.setBackground(0, QtGui.QBrush())

        tokens = item.data(0, self._rich_segments_role)
        if not isinstance(tokens, list) or len(tokens) == 0:
            return

        # 若存在此前插入的前缀 token，则移除一枚即可。
        first_token = tokens[0] if tokens else None
        if isinstance(first_token, dict):
            first_text = str(first_token.get("text", ""))
            if first_text in {"★ ", "• "}:
                item.setData(0, self._rich_segments_role, list(tokens[1:]))

    def clear_dimmed_flags(self) -> None:
        """清除整棵树上的置灰标记。"""
        root = self._tree.invisibleRootItem()
        if root is None:
            return

        stack: List[QtWidgets.QTreeWidgetItem] = [root]
        while stack:
            parent_item = stack.pop()
            for index in range(parent_item.childCount()):
                item = parent_item.child(index)
                if item is None:
                    continue
                stack.append(item)
                item.setData(0, self._dimmed_role, None)

    @staticmethod
    def is_todo_related_to_node(detail_info: Dict[str, Any], node_id: str) -> bool:
        """判断给定 detail_info 是否与指定节点 ID 存在直接关联。"""
        if not node_id:
            return False
        normalized = str(node_id)
        candidate_ids = [
            get_node_id(detail_info),
            detail_info.get("dst_node"),
            detail_info.get("src_node"),
            detail_info.get("target_node_id"),
            detail_info.get("data_node_id"),
            detail_info.get("prev_node_id"),
            detail_info.get("node1_id"),
            detail_info.get("node2_id"),
            detail_info.get("branch_node_id"),
        ]
        for candidate in candidate_ids:
            if candidate is None:
                continue
            if str(candidate) == normalized:
                return True
        return False

    def _apply_node_highlight_to_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
        *,
        is_anchor: bool,
    ) -> None:
        """为与当前节点相关的步骤应用高亮样式（背景 + token 前缀）。"""
        if item is None:
            return

        background_color = (
            ThemeColors.PRIMARY_LIGHT if is_anchor else ThemeColors.BG_SELECTED
        )
        item.setBackground(0, QtGui.QBrush(QtGui.QColor(background_color)))

        tokens = item.data(0, self._rich_segments_role)
        if not isinstance(tokens, list):
            return

        prefix_token: Dict[str, Any]
        if is_anchor:
            prefix_token = {
                "text": "★ ",
                "color": ThemeColors.PRIMARY,
                "bold": True,
            }
        else:
            prefix_token = {
                "text": "• ",
                "color": ThemeColors.TEXT_SECONDARY,
            }

        # 避免前缀堆叠：若 tokens 已包含此前插入的前缀，则先移除。
        base_tokens = tokens
        if base_tokens and isinstance(base_tokens[0], dict):
            first_text = str(base_tokens[0].get("text", ""))
            if first_text in {"★ ", "• "}:
                base_tokens = base_tokens[1:]

        new_tokens = [prefix_token]
        new_tokens.extend(list(base_tokens))
        item.setData(0, self._rich_segments_role, new_tokens)

    def _dim_unrelated_steps(
        self,
        *,
        related_ids: Set[str],
        todo_map: Dict[str, TodoItem],
    ) -> None:
        """将当前树中除 related_ids 以外的步骤统一置灰。"""
        root = self._tree.invisibleRootItem()
        if root is None:
            return

        stack: List[QtWidgets.QTreeWidgetItem] = [root]
        while stack:
            parent_item = stack.pop()
            for index in range(parent_item.childCount()):
                item = parent_item.child(index)
                if item is None:
                    continue
                stack.append(item)

                todo_id = item.data(0, Qt.ItemDataRole.UserRole)
                if not todo_id or todo_id in related_ids:
                    continue
                if todo_id not in todo_map:
                    continue
                item.setData(0, self._dimmed_role, True)


__all__ = ["TodoTreeNodeHighlighter"]


