from __future__ import annotations

from PyQt6 import QtCore, QtWidgets

from app.ui.graph.graph_library.graph_resource_async_loader import GraphResourceAsyncLoader


class PackageLibraryDetailTreeMixin:
    """右侧详情树：单击激活、双击跳转、节点图后台打开。"""

    # === 辅助：为树节点标记可预览的资源类型 ===
    def _set_item_resource_kind(
        self,
        item: QtWidgets.QTreeWidgetItem,
        section_title: str,
        resource_id: str,
        *,
        is_level_entity: bool = False,
    ) -> None:
        """根据所属分组与上下文，为叶子节点写入 (kind, resource_id) 数据。

        kind 取值：
        - "template"     → 元件
        - "instance"     → 实体摆放
        - "level_entity" → 关卡实体
        - "graph"        → 节点图
        其它分组目前不在右侧属性面板中直接展开，保持为浏览用途。
        """
        if not resource_id:
            return
        if is_level_entity:
            kind = "level_entity"
        elif section_title == "元件":
            kind = "template"
        elif section_title == "实体摆放":
            kind = "instance"
        elif section_title == "节点图":
            kind = "graph"
        else:
            return
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (kind, resource_id))

    # === 交互 ===
    def _on_detail_item_activated(
        self,
        item: QtWidgets.QTreeWidgetItem,
        column: int,
    ) -> None:
        """当用户在项目存档内容详情中点击某一行时，发射资源激活信号。"""
        _ = column
        value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)

        if isinstance(value, tuple) and len(value) == 2:
            kind, resource_id = value
            if isinstance(kind, str) and isinstance(resource_id, str) and kind and resource_id:
                self.resource_activated.emit(kind, resource_id)
                return

        # 管理配置条目：仅当 UserRole+1 中标记了 (resource_key, resource_id) 时发射单击信号，
        # 用于在当前视图右侧通过 ManagementPropertyPanel 展示摘要与“所属存档”行。
        if isinstance(management_value, dict):
            binding_key = management_value.get("binding_key")
            item_id = management_value.get("item_id")
            if (
                isinstance(binding_key, str)
                and isinstance(item_id, str)
                and binding_key
                and item_id
            ):
                self.management_resource_activated.emit(binding_key, item_id)
                return

        if isinstance(management_value, tuple) and len(management_value) == 2:
            resource_key, resource_id = management_value
            if (
                isinstance(resource_key, str)
                and isinstance(resource_id, str)
                and resource_key
                and resource_id
            ):
                self.management_resource_activated.emit(resource_key, resource_id)

    def _on_detail_item_double_clicked(
        self,
        item: QtWidgets.QTreeWidgetItem,
        column: int,
    ) -> None:
        """当用户在项目存档内容详情中双击某一行时，触发跨页面跳转。"""
        _ = column
        # “加载更多”占位：双击后为其父节点追加条目
        action = item.data(0, self._ROLE_TREE_ACTION)
        if isinstance(action, str) and action == self._ACTION_LOAD_MORE:
            parent_item = item.parent()
            if parent_item is not None:
                self._load_more_children_for_item(parent_item)
                self.detail_tree.expandItem(parent_item)
            return

        resource_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(resource_value, tuple) and len(resource_value) == 2:
            kind, resource_id = resource_value
            if not isinstance(kind, str) or not isinstance(resource_id, str):
                return
            if not kind or not resource_id:
                return

            # 模板 / 实体摆放 / 关卡实体：依赖当前项目存档上下文，通过导航协调器跳转到对应页面。
            if kind in ("template", "instance", "level_entity"):
                package_id_for_entity = self._current_package_id
                if not package_id_for_entity or self._is_special_id(package_id_for_entity):
                    # 聚合视图下没有唯一的项目存档上下文，仅提供只读预览，不执行跳转。
                    return
                self.jump_to_entity_requested.emit(kind, resource_id, package_id_for_entity)
                return

            # 节点图：直接打开对应节点图进行编辑（不依赖具体项目存档容器）。
            if kind == "graph":
                # 轻量检查：若无法读取 docstring 元数据，通常意味着图不在当前作用域或文件已损坏。
                metadata = self.rm.load_graph_metadata(resource_id)
                if not metadata:
                    self.show_warning(
                        "无法打开节点图",
                        f"节点图 '{resource_id}' 无法打开。\n\n可能的原因：\n"
                        "• 该节点图不在当前资源作用域（共享 + 当前项目存档）内\n"
                        "• 文件缺失/损坏或包含语法错误\n\n"
                        "建议：\n"
                        "• 若该图属于其它项目存档，请先点击“切换为当前”再打开\n"
                        "• 查看控制台输出中的详细错误信息\n"
                        "• 运行节点图校验：python -X utf8 -m app.cli.graph_tools validate-file <图文件路径>",
                    )
                    return

                # 后台加载：避免 load_resource(ResourceType.GRAPH, ...) 在 UI 线程阻塞
                loader = self._ensure_graph_resource_async_loader()
                loader.request_load(resource_manager=self.rm, graph_id=resource_id)
                return

        # 管理配置：根据 section_key + item_id 请求主窗口跳转到对应管理页面。
        management_value = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        if isinstance(management_value, dict):
            jump_section_key = management_value.get("jump_section_key")
            item_id = management_value.get("item_id", "")
            if not isinstance(jump_section_key, str) or not jump_section_key:
                return
            if not isinstance(item_id, str):
                return
            section_key = jump_section_key
        else:
            if not isinstance(management_value, tuple) or len(management_value) != 2:
                return
            section_key, item_id = management_value
            if not isinstance(section_key, str) or not section_key:
                return
            if not isinstance(item_id, str):
                return
        package_id = self._current_package_id
        if not package_id:
            return
        self.management_item_requested.emit(section_key, item_id, package_id)

    def _ensure_graph_resource_async_loader(self) -> GraphResourceAsyncLoader:
        loader = getattr(self, "_graph_resource_async_loader", None)
        if isinstance(loader, GraphResourceAsyncLoader):
            return loader
        loader = GraphResourceAsyncLoader(parent=self)
        setattr(self, "_graph_resource_async_loader", loader)
        loader.graph_loaded.connect(self._on_graph_resource_loaded)
        loader.graph_load_failed.connect(self._on_graph_resource_load_failed)
        return loader

    def _on_graph_resource_loaded(self, graph_id: str, graph_data: dict) -> None:
        self.graph_double_clicked.emit(str(graph_id or ""), graph_data)

    def _on_graph_resource_load_failed(self, graph_id: str) -> None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return
        self.show_warning(
            "加载失败",
            f"无法加载节点图 '{graph_id_text}'。\n\n可能的原因：\n"
            "• 文件不存在、已被移动/删除或已损坏\n"
            "• 节点图无法通过校验（请检查节点图逻辑并修正后再加载）\n\n"
            "建议：\n"
            "• 查看控制台输出中的详细错误信息\n"
            "• 若该图属于其它项目存档，请先点击“切换为当前”再打开\n"
            "• 运行节点图校验：python -X utf8 -m app.cli.graph_tools validate-file <图文件路径>",
        )

