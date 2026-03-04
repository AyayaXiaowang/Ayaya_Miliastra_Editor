from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from engine.resources.resource_manager import ResourceType

from app.common.pagination import compute_lazy_pagination_target_index


class PackageLibraryLazyTreeMixin:
    """右侧预览树的懒加载/加载更多。"""

    def _on_detail_tree_item_expanded(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """展开分类节点时加载预览条目（前 N 条），并提供“加载更多”入口。"""
        if item is None:
            return
        self._ensure_preview_children_for_item(item)

    def _ensure_preview_children_for_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """确保该分类节点至少加载了预览条目（前 N 条）。"""
        self._ensure_lazy_children_loaded(item, ensure_total=self._PREVIEW_CHILD_LIMIT)

    def _load_more_children_for_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """追加加载更多条目。"""
        self._ensure_lazy_children_loaded(item, add_count=self._LOAD_MORE_CHUNK_SIZE)

    def _ensure_lazy_children_loaded(
        self,
        item: QtWidgets.QTreeWidgetItem,
        *,
        ensure_total: int | None = None,
        add_count: int | None = None,
    ) -> None:
        payload = item.data(0, self._ROLE_LAZY_PAYLOAD)
        if not isinstance(payload, dict):
            return

        ids = payload.get("ids")
        if not isinstance(ids, list) or not ids:
            return

        raw_next = payload.get("next_index", 0)
        next_index = raw_next if isinstance(raw_next, int) and raw_next >= 0 else 0
        total = len(ids)
        if next_index > total:
            next_index = total

        target_index = compute_lazy_pagination_target_index(
            total=total,
            next_index=next_index,
            ensure_total=ensure_total,
            add_count=add_count,
            default_chunk_size=self._LOAD_MORE_CHUNK_SIZE,
        )

        if target_index <= next_index:
            self._sync_load_more_item(item, remaining=total - next_index)
            return

        # 先移除旧的“加载更多”占位，再追加新条目。
        self._remove_trailing_load_more_item(item)

        for idx in range(next_index, target_index):
            resource_id = ids[idx]
            if not isinstance(resource_id, str) or not resource_id:
                continue
            leaf_item = self._build_leaf_item_from_lazy_payload(payload, resource_id)
            item.addChild(leaf_item)

        payload["next_index"] = target_index
        item.setData(0, self._ROLE_LAZY_PAYLOAD, payload)

        self._sync_load_more_item(item, remaining=total - target_index)

    def _sync_load_more_item(self, item: QtWidgets.QTreeWidgetItem, *, remaining: int) -> None:
        """确保末尾的“加载更多”占位与 remaining 一致。"""
        self._remove_trailing_load_more_item(item)
        if isinstance(remaining, int) and remaining > 0:
            item.addChild(self._build_load_more_item(remaining))

    def _remove_trailing_load_more_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
        if item.childCount() <= 0:
            return
        last = item.child(item.childCount() - 1)
        if last is None:
            return
        action = last.data(0, self._ROLE_TREE_ACTION)
        if isinstance(action, str) and action == self._ACTION_LOAD_MORE:
            item.takeChild(item.childCount() - 1)

    def _build_load_more_item(self, remaining: int) -> QtWidgets.QTreeWidgetItem:
        text = f"… 加载更多（剩余 {remaining} 项）"
        load_item = QtWidgets.QTreeWidgetItem(["", text, "", ""])
        load_item.setData(0, self._ROLE_TREE_ACTION, self._ACTION_LOAD_MORE)
        load_item.setToolTip(1, "双击此行加载更多条目")
        return load_item

    def _build_leaf_item_from_lazy_payload(
        self,
        payload: dict,
        resource_id: str,
    ) -> QtWidgets.QTreeWidgetItem:
        """根据懒加载 payload 构建单条叶子节点。"""
        kind = payload.get("kind", "")

        # 资源分类（元件/实体摆放/节点图）
        if kind == self._LAZY_KIND_RESOURCE_SECTION:
            section_title = payload.get("section_title", "")
            section_text = section_title if isinstance(section_title, str) else ""

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                if resource_type == ResourceType.GRAPH:
                    display_name = self._resolve_graph_display_name(resource_id)
                else:
                    display_name = self._display_name(resource_type, resource_id)
                    guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            child_item = QtWidgets.QTreeWidgetItem(
                [section_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            child_item.setToolTip(1, resource_id)
            self._set_item_resource_kind(child_item, section_text, resource_id)
            return child_item

        # 战斗预设分类（玩家模板/职业/技能/道具...）
        if kind == self._LAZY_KIND_COMBAT_CATEGORY:
            category_label = payload.get("category_label", "")
            category_text = category_label if isinstance(category_label, str) else ""
            combat_kind = payload.get("combat_kind", None)

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                display_name = self._display_name(resource_type, resource_id)
                guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            entry_item = QtWidgets.QTreeWidgetItem(
                [category_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            entry_item.setToolTip(1, resource_id)
            if isinstance(combat_kind, str) and combat_kind:
                entry_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (combat_kind, resource_id))
            return entry_item

        # 管理配置分类
        if kind == self._LAZY_KIND_MANAGEMENT_CATEGORY:
            resource_key = payload.get("resource_key", "")
            resource_key_text = resource_key if isinstance(resource_key, str) else ""
            category_label = payload.get("category_label", "")
            category_text = category_label if isinstance(category_label, str) else ""

            resource_type = payload.get("resource_type", None)
            display_name = resource_id
            guid_text = ""
            graphs_text = ""
            if isinstance(resource_type, ResourceType):
                display_name = self._display_name(resource_type, resource_id)
                if resource_type != ResourceType.GRAPH:
                    guid_text, graphs_text = self._get_resource_extra_info(resource_type, resource_id)

            entry_item = QtWidgets.QTreeWidgetItem(
                [category_text, str(display_name or resource_id), guid_text, graphs_text]
            )
            entry_item.setToolTip(1, resource_id)
            if resource_key_text:
                jump_section_key = payload.get("jump_section_key", "")
                jump_section_key_text = jump_section_key if isinstance(jump_section_key, str) else ""
                if not jump_section_key_text:
                    jump_section_key_text = self._resolve_management_jump_section_key(resource_key_text)
                entry_item.setData(
                    0,
                    QtCore.Qt.ItemDataRole.UserRole + 1,
                    self._build_management_item_marker(
                        binding_key=resource_key_text,
                        item_id=resource_id,
                        jump_section_key=jump_section_key_text,
                    ),
                )
            return entry_item

        # 兜底：不应发生
        return QtWidgets.QTreeWidgetItem(["", resource_id, "", ""])

