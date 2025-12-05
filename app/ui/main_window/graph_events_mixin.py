"""节点图与复合节点相关的事件处理 Mixin"""
from __future__ import annotations

from typing import Any, Dict

from PyQt6 import QtCore

from engine.nodes.node_registry import get_node_registry


class GraphEventsMixin:
    """负责节点图加载/保存、图库交互以及复合节点库更新的事件处理逻辑。"""

    # === 图加载/保存与文件监控 ===

    def _on_graph_loaded(self, graph_id: str) -> None:
        """节点图加载完成"""
        self.model = self.graph_controller.get_current_model()
        self.scene = self.graph_controller.get_current_scene()
        self.file_watcher_manager.setup_file_watcher(graph_id)

        # 打开图后，若当前处于编辑器模式，则同步右侧"图属性"面板的内容
        from app.models.view_modes import ViewMode as _VM

        if _VM.from_index(self.central_stack.currentIndex()) == _VM.GRAPH_EDITOR:
            graph_prop_idx = self.side_tab.indexOf(self.graph_property_panel)
            if graph_prop_idx == -1:
                self.side_tab.addTab(self.graph_property_panel, "图属性")
            self.graph_property_panel.set_graph(graph_id)
            self.side_tab.setCurrentWidget(self.graph_property_panel)
            self._update_right_panel_visibility()
            print(f"[MAIN] 已同步图属性面板: graph_id={graph_id}")

        # 与任务清单联动（如果存在对应 Todo 上下文）
        self._ensure_todo_data_loaded()
        self._ensure_todo_context_for_graph(graph_id)
        self._update_graph_editor_todo_button_visibility()

    def _on_graph_saved(self, graph_id: str) -> None:
        """节点图保存完成"""
        self.file_watcher_manager.update_last_save_time()

    def _on_graph_reloaded(self, graph_id: str, graph_data: Dict[str, Any]) -> None:
        """图文件重新加载（来自文件监控）"""
        # 1) 失效图属性面板使用的图数据缓存，确保变量/元数据等信息能够反映最新代码
        if hasattr(self, "graph_property_panel"):
            panel = self.graph_property_panel
            data_provider = getattr(panel, "data_provider", None)
            if data_provider is not None:
                data_provider.invalidate_graph(graph_id)
            # 若当前右侧图属性正在展示该图，且当前模式不是图编辑器，则直接触发一次刷新
            if getattr(panel, "current_graph_id", None) == graph_id and self.central_stack is not None:
                from app.models.view_modes import ViewMode as _VM
                current_mode = _VM.from_index(self.central_stack.currentIndex())
                if current_mode is not _VM.GRAPH_EDITOR:
                    panel.set_graph(graph_id)

        # 2) 若当前编辑器正在编辑同一张图，则替换编辑视图中的模型/场景
        if self.graph_controller.current_graph_id == graph_id:
            container = self.graph_controller.current_graph_container
            self.graph_controller.load_graph(graph_id, graph_data, container)

    def _on_open_graph_request(
        self,
        graph_id: str,
        graph_data: Dict[str, Any],
        container: Any,
    ) -> None:
        """打开图请求"""
        print(
            "[MAIN] 收到打开图请求: "
            f"graph_id={graph_id}, container={'Y' if container else 'N'} → 切换到编辑器并加载"
        )
        self.graph_controller.open_graph_for_editing(graph_id, graph_data, container)

    # === 图编辑器视图内的定位 ===

    def _focus_node(self, node_id: str) -> None:
        """聚焦节点"""
        self.view.highlight_node(node_id)
        self.view.focus_on_node(node_id)

    def _focus_edge(self, src_node_id: str, dst_node_id: str, edge_id: str) -> None:
        """聚焦连线"""
        if edge_id:
            self.view.highlight_edge(edge_id)
        self.view.focus_on_nodes_and_edge(src_node_id, dst_node_id, edge_id)

    # === 属性面板与图库交互 ===

    def _on_graph_selected(self, graph_id: str, graph_data: Dict[str, Any]) -> None:
        """图选中（来自右侧属性面板）"""
        container = self.property_panel.current_object
        self.graph_controller.open_graph_for_editing(graph_id, graph_data, container)

    def _on_player_editor_graph_selected(self, graph_id: str, graph_data: Dict[str, Any]) -> None:
        """图选中（来自战斗预设玩家模板详情面板）。

        对于玩家模板挂载的节点图，目前不依赖特定容器上下文，因此直接以独立方式打开。
        """
        container: Any = None
        self._on_open_graph_request(graph_id, graph_data, container)

    def _on_graph_library_selected(self, graph_id: str) -> None:
        """图库中图选中"""
        self.graph_property_panel.set_graph(graph_id)
        # 在图库模式下也监控当前选中的节点图，支持外部修改后自动刷新右侧变量视图
        if hasattr(self, "file_watcher_manager"):
            self.file_watcher_manager.setup_file_watcher(graph_id)
        if hasattr(self, "_schedule_ui_session_state_save"):
            self._schedule_ui_session_state_save()

    def _on_graph_library_double_clicked(
        self,
        graph_id: str,
        graph_data: Dict[str, Any],
    ) -> None:
        """图库中图双击"""
        from engine.graph.models.graph_config import GraphConfig

        graph_config = GraphConfig.deserialize(graph_data)
        self.graph_controller.open_independent_graph(
            graph_id,
            graph_data,
            graph_config.name,
        )

    def _on_graph_updated_from_property(self, graph_id: str) -> None:
        """图属性面板更新"""
        self.graph_library_widget.refresh()

    # === 复合节点库与属性联动 ===

    def _on_composite_library_updated(self) -> None:
        """复合节点库更新"""
        registry = get_node_registry(self.workspace_path, include_composite=True)
        registry.refresh()
        self.library = registry.get_library()

        self.view.node_library = self.library
        self.scene.node_library = self.library
        self.composite_widget.node_library = self.library

        if self.graph_controller.current_graph_id and self.model:
            updated_count = self.model.sync_composite_nodes_from_library(self.library)
            if updated_count > 0:
                print(f"  [同步] 已更新 {updated_count} 个复合节点的端口定义")
                self._refresh_current_graph_display()

        print("✅ 复合节点库已更新")

    def _refresh_current_graph_display(self) -> None:
        """刷新当前图显示"""
        if not self.scene or not hasattr(self, "model"):
            return

        self.scene.clear()
        self.scene.node_items.clear()
        self.scene.edge_items.clear()

        for node in self.model.nodes.values():
            self.scene.add_node_item(node)
        for edge in self.model.edges.values():
            self.scene.add_edge_item(edge)

        if hasattr(self.scene, "undo_manager") and self.scene.undo_manager:
            self.scene.undo_manager.clear()

        self.file_watcher_manager.update_last_save_time()

    def _on_composite_selected(self, composite_id: str) -> None:
        """复合节点选中"""
        composite = self.composite_widget.get_current_composite()
        print(
            "[主窗口] 复合节点选中回调: "
            f"ID={composite_id}, composite={'存在' if composite else '为空'}"
        )

        if composite:
            self.composite_property_panel.load_composite(composite)
            self.composite_pin_panel.load_composite(composite)
        else:
            print(f"[主窗口] 警告: 无法获取复合节点 {composite_id}")
            self.composite_property_panel.clear()
            self.composite_pin_panel.clear()

    def _on_jump_to_graph_element(self, jump_info: Dict[str, Any]) -> None:
        """跳转到图元素（例如从预览/验证面板跳转）"""
        jump_type = jump_info.get("type", "")
        if jump_type == "composite_node":
            composite_name = jump_info.get("composite_name", "")
            if composite_name:
                self.nav_coordinator.navigate_to_mode.emit("composite")
                QtCore.QTimer.singleShot(
                    100,
                    lambda: self.composite_widget.select_composite_by_name(composite_name),
                )

    def _on_select_composite_name(self, composite_name: str) -> None:
        """选择复合节点（来自跳转协调器）"""
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) != ViewMode.COMPOSITE:
            self._on_mode_changed("composite")

        def _try_select() -> None:
            if (
                self.composite_widget
                and hasattr(self.composite_widget, "select_composite_by_name")
            ):
                self.composite_widget.select_composite_by_name(composite_name)

        QtCore.QTimer.singleShot(200, _try_select)




