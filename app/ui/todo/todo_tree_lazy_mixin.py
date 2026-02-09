from __future__ import annotations

from typing import Any, Callable, List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets, sip
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.ui.foundation.theme_manager import Colors as ThemeColors
from app.ui.todo.todo_event_flow_blocks import (
    build_event_flow_block_groups,
    collect_block_node_ids_for_header_item,
    create_block_header_item,
)
from app.ui.todo.todo_tree_graph_expander import expand_graph_on_demand


class TodoTreeLazyMixin:
    """TodoTreeManager 的懒加载（图根/事件流根）与按需定位 mixin。"""

    def ensure_item_built(
        self,
        todo_id: str,
        *,
        on_ready: Callable[[QtWidgets.QTreeWidgetItem], None] | None = None,
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """确保给定 todo_id 在树上已拥有对应的 QTreeWidgetItem（必要时触发懒加载）。

        典型用途：
        - 执行线程发出 step_will_start(todo_id) 时，事件流根的子步骤可能尚未被 UI 懒加载创建，
          直接 setCurrentItem 会失败；这里会自动触发事件流根子步骤分批构建，并在目标树项
          出现后回调 on_ready。

        返回：
        - 若树项已存在：立即返回该 item（并同步调用 on_ready）
        - 若需要异步懒加载：返回 None（on_ready 会在树项就绪后被调用）
        """
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return None

        existing_item = self._item_map.get(normalized_todo_id)
        if existing_item is not None:
            if callable(on_ready):
                on_ready(existing_item)
            return existing_item

        todo = self.todo_map.get(normalized_todo_id)
        if todo is None:
            return None

        flow_root = self.find_event_flow_root_for_todo(normalized_todo_id)
        if flow_root is None:
            return None
        flow_root_id = str(getattr(flow_root, "todo_id", "") or "")
        if not flow_root_id:
            return None

        flow_root_item = self._item_map.get(flow_root_id)
        if flow_root_item is None:
            return None

        if callable(on_ready):
            self._event_flow_item_waiters.setdefault(flow_root_id, []).append((normalized_todo_id, on_ready))

        # 若目标树项已在此前批次中被构建（但调用方还未来得及看到），这里立刻冲刷一次。
        self._flush_event_flow_item_waiters(flow_root_id)

        # 主动展开并触发分批构建（幂等）。
        flow_root_item.setExpanded(True)
        self._expand_event_flow_children_on_demand(flow_root, item=flow_root_item)
        return None

    def _flush_event_flow_item_waiters(self, flow_root_id: str) -> None:
        """在事件流根子步骤分批挂载过程中，尽早唤醒已就绪的等待者。"""
        normalized_flow_root_id = str(flow_root_id or "")
        if not normalized_flow_root_id:
            return
        waiters = self._event_flow_item_waiters.get(normalized_flow_root_id)
        if not waiters:
            return

        remaining: list[tuple[str, Callable[[QtWidgets.QTreeWidgetItem], None]]] = []
        for target_todo_id, callback in waiters:
            item = self._item_map.get(target_todo_id)
            if item is None:
                remaining.append((target_todo_id, callback))
                continue
            if sip.isdeleted(item):
                continue
            if callable(callback):
                callback(item)

        if remaining:
            self._event_flow_item_waiters[normalized_flow_root_id] = remaining
        else:
            self._event_flow_item_waiters.pop(normalized_flow_root_id, None)

    def find_template_graph_root_for_todo(self, start_todo_id: str) -> Optional[TodoItem]:
        """公开定位接口：先尝试沿树项父链，再回退至 todo_id 链路。"""
        if not start_todo_id:
            return None
        return self._graph_support.find_template_graph_root_for_todo(
            start_todo_id,
            self.todo_map,
            self._item_map,
        )

    def load_graph_data_for_root(self, root_todo: TodoItem) -> Optional[dict]:
        """通过 TodoTreeGraphSupport 加载指定图根的 graph_data。

        统一由 `_graph_support` 负责解析缓存与 ResourceManager，
        避免在调用方重复实现图数据加载与缓存更新逻辑。
        """
        if root_todo is None:
            return None
        return self._graph_support.load_graph_data_for_root(root_todo)

    def find_event_flow_root_for_todo(self, start_todo_id: str) -> Optional[TodoItem]:
        return self._graph_support.find_event_flow_root_for_todo(start_todo_id, self.todo_map)

    def collect_block_node_ids_for_header_item(
        self,
        header_item: QtWidgets.QTreeWidgetItem,
    ) -> List[str]:
        """为“逻辑块分组头”推导该块内节点 ID 集合（供预览聚焦）。"""
        return collect_block_node_ids_for_header_item(
            header_item,
            self.todo_map,
            graph_support=self._graph_support,
        )

    # === 懒加载 ===

    def expand_graph_on_demand(
        self,
        graph_root: TodoItem,
        *,
        on_finished: Optional[Callable[[bool], None]] = None,
    ) -> None:
        expand_graph_on_demand(self, graph_root, on_finished=on_finished)

    def _expand_event_flow_children_on_demand(
        self,
        flow_root: TodoItem,
        *,
        item: QtWidgets.QTreeWidgetItem,
        on_finished: Optional[Callable[[bool], None]] = None,
    ) -> None:
        """为事件流根按需构建其子步骤树项（分批挂载，避免 UI 卡顿）。"""
        flow_root_id = str(flow_root.todo_id or "")
        if not flow_root_id:
            if callable(on_finished):
                on_finished(False)
            return

        if flow_root_id in self._event_flow_children_built:
            if callable(on_finished):
                on_finished(True)
            return

        if callable(on_finished):
            self._event_flow_build_callbacks.setdefault(flow_root_id, []).append(on_finished)

        if self._event_flow_build_inflight.get(flow_root_id):
            return

        self._event_flow_build_inflight[flow_root_id] = True

        # 先清空可能残留的子项（例如之前的中途构建/占位）
        while item.childCount() > 0:
            item.takeChild(0)

        total_children = len(flow_root.children or [])
        loading_item = QtWidgets.QTreeWidgetItem()
        loading_item.setData(0, Qt.ItemDataRole.UserRole, "")
        loading_item.setData(0, self.MARKER_ROLE, "lazy_loading_placeholder")
        loading_item.setFlags(
            loading_item.flags()
            & ~Qt.ItemFlag.ItemIsSelectable
            & ~Qt.ItemFlag.ItemIsUserCheckable
        )
        loading_item.setText(0, f"正在加载步骤… (0/{total_children})")
        loading_item.setForeground(0, QtGui.QBrush(QtGui.QColor(ThemeColors.TEXT_SECONDARY)))
        item.addChild(loading_item)
        self._event_flow_loading_items[flow_root_id] = loading_item

        from app.ui.todo.todo_event_flow_blocks import EventFlowBlockGroup

        # 预计算分组（若无块信息则退回扁平结构）。
        # 注意：超大事件流下，分组需要加载图模型并扫描全部子步骤，成本很高；
        # 为保证交互优先，超大流默认使用扁平结构（仍保持顺序与可展开加载）。
        enable_block_grouping = total_children <= 800
        if enable_block_grouping:
            groups = build_event_flow_block_groups(
                flow_root,
                item,
                self.todo_map,
                graph_support=self._graph_support,
            )
            if not groups:
                groups = [
                    EventFlowBlockGroup(
                        block_index=None,
                        child_ids=list(flow_root.children or []),
                    )
                ]

            model, _graph_id = self._graph_support.get_graph_model_for_item(
                item=item,
                todo_id=flow_root.todo_id,
                todo_map=self.todo_map,
            )
            basic_blocks: List[Any] = []
            if model is not None:
                basic_blocks_raw = getattr(model, "basic_blocks", None)
                if isinstance(basic_blocks_raw, list):
                    basic_blocks = list(basic_blocks_raw)
        else:
            groups = [
                EventFlowBlockGroup(
                    block_index=None,
                    child_ids=list(flow_root.children or []),
                )
            ]
            basic_blocks = []

        batch_size = 60 if total_children > 1500 else 120

        state = {
            "group_index": 0,
            "child_index": 0,
            "added": 0,
            "total": total_children,
            "groups": groups,
            "basic_blocks": basic_blocks,
            "current_header_item": None,
        }

        def _insert_before_loading(child: QtWidgets.QTreeWidgetItem) -> None:
            placeholder = self._event_flow_loading_items.get(flow_root_id)
            if placeholder is None or placeholder.parent() is None:
                item.addChild(child)
                return
            insert_at = max(0, item.indexOfChild(placeholder))
            item.insertChild(insert_at, child)

        def _continue_build() -> None:
            if flow_root_id not in self._event_flow_build_inflight:
                return

            # 若树或目标 item 已被整树刷新释放，则停止本轮构建并清理 inflight，避免
            # `wrapped C/C++ object ... has been deleted` 造成 UI 假死（updatesEnabled 永久为 False）。
            if sip.isdeleted(self.tree) or sip.isdeleted(item):
                self._event_flow_build_inflight.pop(flow_root_id, None)
                self._event_flow_children_pending.discard(flow_root_id)
                self._event_flow_loading_items.pop(flow_root_id, None)
                self._event_flow_item_waiters.pop(flow_root_id, None)
                callbacks = self._event_flow_build_callbacks.pop(flow_root_id, [])
                for cb in callbacks:
                    if callable(cb):
                        cb(False)
                return

            self._refresh_gate.set_refreshing(True)
            self.tree.setUpdatesEnabled(False)
            try:
                added_this_round = 0
                while added_this_round < batch_size:
                    if state["group_index"] >= len(state["groups"]):
                        break

                    group = state["groups"][state["group_index"]]
                    child_ids = list(getattr(group, "child_ids", []) or [])
                    if state["child_index"] >= len(child_ids):
                        state["group_index"] += 1
                        state["child_index"] = 0
                        state["current_header_item"] = None
                        continue

                    # 进入一个新的 block 分组：需要创建块头
                    if state["child_index"] == 0 and getattr(group, "block_index", None) is not None:
                        block_index = group.block_index
                        block_color_hex = ""
                        if isinstance(block_index, int) and 0 <= block_index < len(state["basic_blocks"]):
                            basic_block = state["basic_blocks"][block_index]
                            color_value = getattr(basic_block, "color", "")
                            if isinstance(color_value, str) and color_value:
                                block_color_hex = color_value

                        header_item = create_block_header_item(
                            group.block_index,
                            int(state["group_index"]),
                            block_color_hex,
                            rich_segments_role=self.RICH_SEGMENTS_ROLE,
                            marker_role=self.MARKER_ROLE,
                        )
                        _insert_before_loading(header_item)
                        header_item.setExpanded(True)
                        state["current_header_item"] = header_item

                    child_id = child_ids[state["child_index"]]
                    state["child_index"] += 1
                    child_todo = self.todo_map.get(child_id)
                    if child_todo is None:
                        continue

                    target_parent_item = state["current_header_item"] or item
                    placeholder = self._event_flow_loading_items.get(flow_root_id)
                    if target_parent_item is item and placeholder is not None:
                        self._build_single_todo_subtree(
                            target_parent_item,
                            child_todo,
                            insert_before=placeholder,
                        )
                    else:
                        self._build_single_todo_subtree(target_parent_item, child_todo)
                    state["added"] += 1
                    added_this_round += 1

                placeholder = self._event_flow_loading_items.get(flow_root_id)
                if placeholder is not None:
                    placeholder.setText(0, f"正在加载步骤… ({state['added']}/{state['total']})")
            finally:
                if not sip.isdeleted(self.tree):
                    self.tree.setUpdatesEnabled(True)
                self._refresh_gate.set_refreshing(False)
            # 尽早唤醒“定位到某一步”的等待者：一旦对应树项出现在 item_map 中即可触发。
            self._flush_event_flow_item_waiters(flow_root_id)

            # 完成：清理占位与 inflight，并触发回调
            if state["added"] >= state["total"] or state["group_index"] >= len(state["groups"]):
                placeholder = self._event_flow_loading_items.pop(flow_root_id, None)
                if placeholder is not None and placeholder.parent() is item:
                    item.removeChild(placeholder)

                self._event_flow_build_inflight.pop(flow_root_id, None)
                self._event_flow_children_pending.discard(flow_root_id)
                self._event_flow_children_built.add(flow_root_id)

                callbacks = self._event_flow_build_callbacks.pop(flow_root_id, [])
                for cb in callbacks:
                    if callable(cb):
                        cb(True)
                # 构建结束：再冲刷一次等待者（防止最后一批完成后未触发）。
                self._flush_event_flow_item_waiters(flow_root_id)
                return

            QtCore.QTimer.singleShot(0, _continue_build)

        QtCore.QTimer.singleShot(0, _continue_build)



