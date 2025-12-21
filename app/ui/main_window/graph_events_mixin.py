"""节点图与复合节点相关的事件处理 Mixin"""
from __future__ import annotations

from typing import Any, Dict

from PyQt6 import QtCore

from engine.nodes.node_registry import get_node_registry
from engine.utils.logging.logger import log_info, log_warn
from app.ui.graph.scene_builder import populate_scene_from_model
from app.runtime.services.graph_data_service import get_shared_graph_data_service


class GraphEventsMixin:
    """负责节点图加载/保存、图库交互以及复合节点库更新的事件处理逻辑。"""

    # === 图加载/保存与文件监控 ===

    def _on_graph_loaded(self, graph_id: str) -> None:
        """节点图加载完成"""
        self.file_watcher_manager.setup_file_watcher(graph_id)

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        graph_state = getattr(view_state, "graph", None)
        if graph_state is not None:
            setattr(graph_state, "graph_editor_open_graph_id", str(graph_id or ""))

        # 打开图后，若当前处于编辑器模式，则同步右侧"图属性"面板的内容
        from app.models.view_modes import ViewMode as _VM

        if _VM.from_index(self.central_stack.currentIndex()) == _VM.GRAPH_EDITOR:
            self.graph_property_panel.set_graph(graph_id)
            self.right_panel.ensure_visible("graph_property", visible=True, switch_to=True)
            log_info("[GRAPH] synced graph_property_panel: graph_id={}", graph_id)

        # 与任务清单联动（如果存在对应 Todo 上下文）
        self._ensure_todo_data_loaded()
        self._ensure_todo_context_for_graph(graph_id)
        self._update_graph_editor_todo_button_visibility()

    def _on_graph_saved(self, graph_id: str) -> None:
        """节点图保存完成"""
        self.file_watcher_manager.update_last_save_time()
        # 节点图写盘位于 assets/资源库/节点图/...，会触发资源库目录 watcher；
        # 这里同步标记为“内部写盘”，避免误触发整库刷新。
        graph_file_path = self.app_state.resource_manager.get_graph_file_path(graph_id)
        suppress_directory = graph_file_path.parent if graph_file_path is not None else None
        self.file_watcher_manager.update_last_resource_write_time(suppress_directory)

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

    def _on_graph_runtime_cache_updated(self, graph_id: str) -> None:
        """节点图运行期缓存已更新（例如自动排版覆盖持久化缓存 / 强制重解析）。

        目标：统一失效上层缓存，避免出现“某入口刷新后又回退/显示不一致”。
        """
        if not isinstance(graph_id, str) or not graph_id:
            return

        provider = get_shared_graph_data_service(
            self.app_state.resource_manager,
            self.app_state.package_index_manager,
        )
        provider.drop_payload_for_graph(graph_id)
        provider.invalidate_graph(graph_id)

        # 失效图属性面板使用的图数据缓存；若面板正在展示该图，则立刻刷新一次。
        if hasattr(self, "graph_property_panel"):
            panel = self.graph_property_panel
            data_provider = getattr(panel, "data_provider", None)
            invalidate_graph = getattr(data_provider, "invalidate_graph", None) if data_provider is not None else None
            if callable(invalidate_graph):
                invalidate_graph(graph_id)
            if getattr(panel, "current_graph_id", None) == graph_id:
                panel.set_graph(graph_id)

    def _on_open_graph_request(
        self,
        graph_id: str,
        graph_data: Dict[str, Any],
        container: Any,
    ) -> None:
        """打开图请求"""
        log_info(
            "[GRAPH] open_request: graph_id={} container_present={}",
            graph_id,
            bool(container),
        )
        self.graph_controller.open_graph_for_editing(graph_id, graph_data, container)

    # === 图编辑器视图内的定位 ===

    def _focus_node(self, node_id: str) -> None:
        """聚焦节点"""
        view = self.graph_controller.view
        view.highlight_node(node_id)
        view.focus_on_node(node_id)

    def _focus_edge(self, src_node_id: str, dst_node_id: str, edge_id: str) -> None:
        """聚焦连线"""
        view = self.graph_controller.view
        if edge_id:
            view.highlight_edge(edge_id)
        view.focus_on_nodes_and_edge(src_node_id, dst_node_id, edge_id)

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
        # 重要：图属性面板在不同模式下由不同上下文驱动。
        # - GRAPH_LIBRARY：由“节点图库列表选中”驱动；
        # - GRAPH_EDITOR ：由“当前打开的图”驱动（graph_loaded / GraphEditorModePresenter）。
        # 因此必须先校验 ViewMode，避免后台刷新（例如切换存档触发图库列表重建）
        # 发出空 graph_id 时，把编辑器右侧图属性面板误清空、并将文件监控切走。
        from app.models.view_modes import ViewMode

        current_view_mode = ViewMode.from_index(self.central_stack.currentIndex())
        if current_view_mode != ViewMode.GRAPH_LIBRARY:
            return

        self.graph_property_panel.set_graph(graph_id)

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        graph_state = getattr(view_state, "graph", None)
        if graph_state is not None:
            setattr(graph_state, "graph_library_selected_graph_id", str(graph_id or ""))

        # 在图库模式下也监控当前选中的节点图，支持外部修改后自动刷新右侧变量视图
        if hasattr(self, "file_watcher_manager"):
            self.file_watcher_manager.setup_file_watcher(graph_id)
        self.schedule_ui_session_state_save()

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
        self.graph_library_widget.reload()

    # === 复合节点库与属性联动 ===

    def _on_composite_library_updated(self) -> None:
        """复合节点库更新"""
        registry = get_node_registry(self.app_state.workspace_path, include_composite=True)
        registry.refresh()
        updated_library = registry.get_library()
        self.app_state.node_library = updated_library
        # GraphEditorController/GraphView/GraphScene 的节点库应保持一致
        self.graph_controller.node_library = updated_library
        self.graph_controller.view.node_library = updated_library
        current_scene = self.graph_controller.get_current_scene()
        current_scene.node_library = updated_library

        self.composite_widget.node_library = updated_library

        if self.graph_controller.current_graph_id:
            current_model = self.graph_controller.get_current_model()
            updated_count = current_model.sync_composite_nodes_from_library(updated_library)
            if updated_count > 0:
                log_info("[COMPOSITE] synced composite node ports: updated_count={}", updated_count)
                self._refresh_current_graph_display()

        log_info("[COMPOSITE] composite library refreshed")

    def _refresh_current_graph_display(self) -> None:
        """刷新当前图显示"""
        current_scene = self.graph_controller.get_current_scene()

        current_scene.clear()
        current_scene.node_items.clear()
        current_scene.edge_items.clear()

        populate_scene_from_model(current_scene, enable_batch_mode=True)

        if hasattr(current_scene, "undo_manager") and current_scene.undo_manager:
            current_scene.undo_manager.clear()

        self.file_watcher_manager.update_last_save_time()
        self.file_watcher_manager.update_last_resource_write_time()

    def _on_composite_selected(self, composite_id: str) -> None:
        """复合节点选中"""
        composite = self.composite_widget.get_current_composite()
        log_info(
            "[COMPOSITE] selected: composite_id={} has_composite={}",
            composite_id,
            bool(composite),
        )

        if composite:
            self.composite_property_panel.load_composite(composite)
            self.composite_pin_panel.load_composite(composite)
        else:
            log_warn("[COMPOSITE] selected but composite not found: composite_id={}", composite_id)
            self.composite_property_panel.clear()
            self.composite_pin_panel.clear()

    def _on_jump_to_graph_element(self, jump_info: Dict[str, Any]) -> None:
        """跳转到图元素（例如从预览/验证面板跳转）"""
        # GraphView 为全局共享画布：在 TODO 预览中触发的 jump 由 todo_binder 处理，
        # 避免这里再重复响应造成双重导航。
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) == ViewMode.TODO:
            return

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




