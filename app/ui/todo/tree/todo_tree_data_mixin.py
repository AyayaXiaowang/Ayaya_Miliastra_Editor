from __future__ import annotations

from typing import Dict, List, Optional

from PyQt6 import QtWidgets
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.ui.todo.misc.todo_config import StepTypeRules
from app.ui.todo.tree.tree_check_helpers import set_all_children_state, apply_parent_progress


class TodoTreeDataMixin:
    """TodoTreeManager 的数据注入/索引/批量勾选等 mixin。"""

    def set_data(self, todos: List[TodoItem], todo_states: Dict[str, bool]) -> None:
        """注入最新的 Todo 列表与完成状态，作为全局权威数据源。

        - todos / todo_states 直接引用调用方传入的容器，便于与外层状态保持一致；
        - todo_map 作为集中索引，保持字典实例稳定，仅在此处清空并重建内容，
          外部若持有对该 dict 的引用（例如详情面板/右键菜单），可继续复用；
        - 若当前树中仍存在 todo_id 已不在最新 todo_map 中的树项（例如此前懒加载
          生成的图内步骤），则视为结构已发生变化，强制整树重建以避免“残影”
          或重复步骤。
        """
        self.todos = todos
        self.todo_states = todo_states
        self.todo_map.clear()
        for todo in todos:
            self.todo_map[todo.todo_id] = todo

        # 修复/兜底：children 列表中不应出现重复 todo_id。
        # 若存在重复引用，会导致：
        # - 树上出现“两个看起来一模一样的事件流/图根”等重复项；
        # - 由于懒加载与缓存状态以 todo_id 为键，常见表现是“一个能展开，另一个展开为空/没反应”。
        # 这里做稳定去重（保持首次出现顺序），确保 UI 结构为严格树。
        had_duplicate_children = False
        for todo in todos:
            raw_children = getattr(todo, "children", None)
            if not isinstance(raw_children, list) or not raw_children:
                continue
            seen_child_ids: set[str] = set()
            unique_children: list[str] = []
            for child_id in raw_children:
                normalized_child_id = str(child_id or "")
                if not normalized_child_id:
                    continue
                if normalized_child_id in seen_child_ids:
                    had_duplicate_children = True
                    continue
                seen_child_ids.add(normalized_child_id)
                unique_children.append(normalized_child_id)
            if unique_children != raw_children:
                todo.children = unique_children

        # 检测当前树中是否存在“孤儿树项”（tree_item 有 todo_id，但 todo_map 中已不存在）
        # 典型场景：此前在旧一轮任务结构下懒加载了图步骤，后续重新生成任务清单后，
        # 这些旧步骤的 todo_id 不再出现在新的 todos 中，但对应的树节点仍然存在。
        # 为保证“树结构与 todo_map 一一对应”的约定，此时需要视为结构已变更，
        # 强制走整树重建逻辑而不是仅做样式刷新。
        has_orphan_tree_items = False
        if self._item_map:
            for mapped_todo_id in self._item_map.keys():
                if mapped_todo_id and mapped_todo_id not in self.todo_map:
                    has_orphan_tree_items = True
                    break

        new_signature = self._compute_structure_signature(todos)
        structure_changed = (new_signature != self._structure_signature) or has_orphan_tree_items
        self._structure_signature = new_signature
        if had_duplicate_children:
            structure_changed = True
        if structure_changed or not self._item_map:
            self.refresh_tree()
        else:
            self.refresh_entire_tree_display()

    def get_item_map(self) -> Dict[str, QtWidgets.QTreeWidgetItem]:
        return self._item_map

    def get_item_by_id(self, todo_id: str) -> Optional[QtWidgets.QTreeWidgetItem]:
        return self._item_map.get(todo_id)

    def select_task_by_id(
        self,
        todo_id: str,
        *,
        scroll: bool = True,
        scroll_hint: QAbstractItemView.ScrollHint = QAbstractItemView.ScrollHint.PositionAtCenter,
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """统一的“选中某个 todo_id”入口（收口 current 状态）。

        约定：
        - 只负责树侧行为：展开父链、设置 currentItem、可选滚动；
        - 不负责右侧详情/预览的切换（由 currentItemChanged 信号驱动的编排层负责）；
        - 对懒加载场景：若 item 尚未被构建，应由调用方先走 ensure_item_built(..., on_ready=...)。
        """
        normalized = str(todo_id or "")
        if not normalized:
            return None
        item = self.get_item_by_id(normalized)
        if item is None:
            return None

        parent_item = item.parent()
        while parent_item is not None:
            parent_item.setExpanded(True)
            parent_item = parent_item.parent()

        already_selected = self.tree.currentItem() is item
        if not already_selected:
            self.tree.setCurrentItem(item)

        if scroll:
            self.tree.scrollToItem(item, scroll_hint)

        return item

    def set_leaf_checked_silent(self, todo_id: str, checked: bool) -> None:
        """静默设置叶子步骤的勾选状态：更新 todo_states 与样式，但不触发 todo_checked 信号。

        典型使用场景：
        - 识别回填（定位镜头后批量自动勾选历史步骤）应只更新当前会话的 UI 状态，
          不应触发外层“每次勾选都立即落盘”的持久化路径。

        注意：
        - 仅作用于“叶子步骤”（无 children 且非图根语义）；父级/分组节点的三态由叶子状态反推。
        """
        self._set_leaf_checked(todo_id, checked, emit_signal=False)

    def set_leaf_checked(self, todo_id: str, checked: bool) -> bool:
        """设置叶子步骤的勾选状态（会发出 todo_checked 信号）。

        设计目的：
        - 让“完成度状态”在 UI 层拥有单一入口（TodoTreeManager），避免外部直接操作 QTreeWidgetItem
          导致 todo_states、运行态清理、父级三态反推与持久化信号发出时序不一致。
        - 执行桥接层（execution）与其它调用方都应优先使用该方法，而不是 item.setCheckState(...)。

        返回：
        - True: 成功作用于一个“叶子步骤”
        - False: todo_id 不存在或不是叶子步骤（例如父级/图根/分组头）
        """
        return self._set_leaf_checked(todo_id, checked, emit_signal=True)

    def _set_leaf_checked(self, todo_id: str, checked: bool, *, emit_signal: bool) -> bool:
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return False
        item = self._item_map.get(normalized_todo_id)
        todo = self.todo_map.get(normalized_todo_id)
        if item is None or todo is None:
            return False

        detail_type = (todo.detail_info or {}).get("type", "")
        is_leaf_like = (not todo.children) and not StepTypeRules.is_graph_root(detail_type)
        if not is_leaf_like:
            return False

        target_checked = bool(checked)
        previous_state = bool(self.todo_states.get(normalized_todo_id, False))
        if previous_state == target_checked and not emit_signal:
            # 静默且状态无变化：仍返回 True 表示该 todo_id 属于叶子步骤
            return True

        # 先更新权威状态字典：避免后续 UI 写回触发 itemChanged 时出现“状态回退”
        self.todo_states[normalized_todo_id] = target_checked
        # 完成态切换时清理运行态（failed/skipped）
        self.runtime_state.clear(normalized_todo_id)

        # 增量刷新：用 refresh_gate 防止 apply_leaf_state 写 checkState 时触发 itemChanged 递归
        self._refresh_gate.set_refreshing(True)
        try:
            self.update_item_incrementally(item, todo)
        finally:
            self._refresh_gate.set_refreshing(False)

        if emit_signal and previous_state != target_checked:
            self.todo_checked.emit(normalized_todo_id, target_checked)
        return True

    def _update_ancestor_states(self, item: QtWidgets.QTreeWidgetItem) -> None:
        current_item = item.parent()
        while current_item:
            todo_id = current_item.data(0, Qt.ItemDataRole.UserRole)
            todo = self.todo_map.get(todo_id)
            if todo and todo.children:
                apply_parent_progress(
                    current_item, todo, self.todo_states, self._get_task_icon
                )
                # 重新应用父级样式与富文本 tokens，使进度与颜色保持同步
                self._apply_parent_style(current_item, todo)
            current_item = current_item.parent()

    def _compute_structure_signature(self, todos: List[TodoItem]) -> tuple:
        signature = []
        for todo in todos:
            children = tuple(todo.children or [])
            detail_type = str((todo.detail_info or {}).get("type", ""))
            signature.append((todo.todo_id, children, detail_type))
        signature.sort(key=lambda item: item[0])
        return tuple(signature)

    def set_all_children_state(self, todo: TodoItem, is_checked: bool) -> None:
        # 统一由 set_leaf_checked 写入完成度（并在变化时发出 todo_checked），避免外部直接改 todo_states。
        def _emit_checked(todo_id: str, checked: bool) -> None:
            _ = self.set_leaf_checked(todo_id, checked)

        set_all_children_state(self.todo_map, self.todo_states, todo, is_checked, _emit_checked)



