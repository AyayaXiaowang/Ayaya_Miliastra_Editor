"""节点图与复合节点相关的事件处理 Mixin"""
from __future__ import annotations

from typing import Any, Dict

from PyQt6 import QtCore

from engine.configs.resource_types import ResourceType
from engine.nodes.node_registry import get_node_registry
from engine.utils.graph.node_defs_fingerprint import invalidate_composite_node_defs_fingerprint_cache
from engine.utils.logging.logger import log_info, log_warn
from app.ui.graph.scene_builder import populate_scene_from_model
from app.runtime.services.graph_data_service import GraphLoadPayload, get_shared_graph_data_service


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
        # 节点图写盘位于 assets/资源库/(共享|项目存档/<package_id>)/节点图/...，会触发资源库目录 watcher；
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

        # 1b) 同步失效/刷新“信号/结构体/变量”只读面板（仅在非图编辑器模式下自动刷新）
        if hasattr(self, "graph_used_definitions_panel"):
            used_panel = self.graph_used_definitions_panel
            used_provider = getattr(used_panel, "data_provider", None)
            invalidate_graph = (
                getattr(used_provider, "invalidate_graph", None) if used_provider is not None else None
            )
            if callable(invalidate_graph):
                invalidate_graph(graph_id)
            if getattr(used_panel, "current_graph_id", None) == graph_id and self.central_stack is not None:
                from app.models.view_modes import ViewMode as _VM
                current_mode = _VM.from_index(self.central_stack.currentIndex())
                if current_mode is not _VM.GRAPH_EDITOR:
                    used_panel.set_graph(graph_id)

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

        # 同步刷新“信号/结构体/变量”只读面板（若正在展示该图）
        if hasattr(self, "graph_used_definitions_panel"):
            used_panel = self.graph_used_definitions_panel
            used_provider = getattr(used_panel, "data_provider", None)
            invalidate_graph = (
                getattr(used_provider, "invalidate_graph", None) if used_provider is not None else None
            )
            if callable(invalidate_graph):
                invalidate_graph(graph_id)
            if getattr(used_panel, "current_graph_id", None) == graph_id:
                used_panel.set_graph(graph_id)

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
        normalized = str(node_id or "")
        if not normalized:
            return
        expected_graph_id = str(getattr(self.graph_controller, "current_graph_id", "") or "")
        self._focus_node_with_retry(
            normalized,
            expected_graph_id=expected_graph_id,
            attempt=0,
            max_attempts=60,
            interval_ms=100,
        )

    def _focus_edge(self, src_node_id: str, dst_node_id: str, edge_id: str) -> None:
        """聚焦连线"""
        src = str(src_node_id or "")
        dst = str(dst_node_id or "")
        if (not src) or (not dst):
            return
        expected_graph_id = str(getattr(self.graph_controller, "current_graph_id", "") or "")
        self._focus_edge_with_retry(
            src,
            dst,
            str(edge_id or ""),
            expected_graph_id=expected_graph_id,
            attempt=0,
            max_attempts=60,
            interval_ms=100,
        )

    def _focus_node_with_retry(
        self,
        node_id: str,
        *,
        expected_graph_id: str,
        attempt: int,
        max_attempts: int,
        interval_ms: int,
    ) -> None:
        """聚焦节点（带重试）：用于非阻塞加载/分帧装配场景。"""
        current_graph_id = str(getattr(self.graph_controller, "current_graph_id", "") or "")
        if expected_graph_id and current_graph_id and expected_graph_id != current_graph_id:
            return

        view = self.graph_controller.view
        scene = view.scene()
        node_items = getattr(scene, "node_items", None) if scene is not None else None
        if isinstance(node_items, dict) and node_id in node_items:
            view.highlight_node(node_id)
            view.focus_on_node(node_id)
            return

        if int(attempt) >= int(max_attempts):
            # 兜底：即便未命中 node_items，也执行一次聚焦（部分渲染模式下 node_items 可能延迟填充）
            view.highlight_node(node_id)
            view.focus_on_node(node_id)
            return

        QtCore.QTimer.singleShot(
            int(interval_ms),
            lambda: self._focus_node_with_retry(
                node_id,
                expected_graph_id=expected_graph_id,
                attempt=int(attempt) + 1,
                max_attempts=int(max_attempts),
                interval_ms=int(interval_ms),
            ),
        )

    def _focus_edge_with_retry(
        self,
        src_node_id: str,
        dst_node_id: str,
        edge_id: str,
        *,
        expected_graph_id: str,
        attempt: int,
        max_attempts: int,
        interval_ms: int,
    ) -> None:
        """聚焦连线（带重试）：用于非阻塞加载/分帧装配场景。"""
        current_graph_id = str(getattr(self.graph_controller, "current_graph_id", "") or "")
        if expected_graph_id and current_graph_id and expected_graph_id != current_graph_id:
            return

        view = self.graph_controller.view
        scene = view.scene()
        node_items = getattr(scene, "node_items", None) if scene is not None else None
        if isinstance(node_items, dict) and (src_node_id in node_items) and (dst_node_id in node_items):
            if edge_id:
                view.highlight_edge(edge_id)
            view.focus_on_nodes_and_edge(src_node_id, dst_node_id, edge_id)
            return

        if int(attempt) >= int(max_attempts):
            if edge_id:
                view.highlight_edge(edge_id)
            view.focus_on_nodes_and_edge(src_node_id, dst_node_id, edge_id)
            return

        QtCore.QTimer.singleShot(
            int(interval_ms),
            lambda: self._focus_edge_with_retry(
                src_node_id,
                dst_node_id,
                edge_id,
                expected_graph_id=expected_graph_id,
                attempt=int(attempt) + 1,
                max_attempts=int(max_attempts),
                interval_ms=int(interval_ms),
            ),
        )

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

        # 节点图库的“单击选中”必须保持瞬时：此处仅驱动右侧图属性面板做轻量预览，
        # 不触发 `ResourceManager.load_resource(ResourceType.GRAPH, ...)` 的解析+自动布局链路。
        graph_library_widget = getattr(self, "graph_library_widget", None)
        reference_tracker = (
            getattr(graph_library_widget, "reference_tracker", None) if graph_library_widget else None
        )
        reference_count = 0
        if reference_tracker is not None:
            get_count = getattr(reference_tracker, "get_reference_count", None)
            if callable(get_count):
                reference_count = int(get_count(graph_id) or 0)

        preview_method = getattr(self.graph_property_panel, "set_graph_library_preview", None)
        if callable(preview_method):
            # 关键：单击必须瞬时。这里仅传“引用次数”，引用列表详情交给面板在页签可见时惰性加载。
            preview_method(graph_id, references=None, reference_count=reference_count)
        else:
            # 兼容：若面板未提供轻量预览入口，则回退为完整加载（可能较慢）
            self.graph_property_panel.set_graph(graph_id)
        if hasattr(self, "graph_used_definitions_panel"):
            self.graph_used_definitions_panel.set_graph(graph_id)

        # 同步到 ViewState（单一真源）
        view_state = getattr(self, "view_state", None)
        graph_state = getattr(view_state, "graph", None)
        if graph_state is not None:
            setattr(graph_state, "graph_library_selected_graph_id", str(graph_id or ""))

        # 在图库模式下也监控当前选中的节点图，支持外部修改后自动刷新右侧变量视图
        if hasattr(self, "file_watcher_manager"):
            self.file_watcher_manager.setup_file_watcher(graph_id)
        self.schedule_ui_session_state_save()

    def _on_graph_property_panel_payload_loaded(self, graph_id: str, payload: object) -> None:
        """图属性面板异步加载完成（用于在 GRAPH_LIBRARY 模式下同步左侧卡片统计）。

        说明：
        - 节点图库列表页使用 `load_graph_metadata()` 的轻量缓存展示 node/edge 数：
          统计信息只允许来自持久化 graph_cache；未命中缓存时应保持为空（UI 展示为 "-" 或空白）。
        - 当右侧图属性面板触发完整加载并生成/更新持久化 graph_cache 后，轻量元数据缓存可能仍停留在旧值（例如仍为空）；
        - 本回调在“属性面板完成加载且仍为当前选中图”时，主动失效 metadata 缓存并刷新卡片统计，
          使左侧列表与右侧基本信息保持一致。
        """
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) != ViewMode.GRAPH_LIBRARY:
            return

        graph_property_panel = getattr(self, "graph_property_panel", None)
        current_graph_id = getattr(graph_property_panel, "current_graph_id", None) if graph_property_panel else None
        if not graph_id or str(current_graph_id or "") != str(graph_id):
            return

        if not isinstance(payload, GraphLoadPayload):
            return
        if payload.error:
            return
        graph_config = payload.graph_config
        if graph_config is None:
            return

        node_count = int(graph_config.get_node_count())
        edge_count = int(graph_config.get_edge_count())

        # 1) 失效 GraphMetadataReader 的轻量元数据缓存（mtime 不变时否则会一直命中旧统计）
        resource_manager = getattr(self.app_state, "resource_manager", None)
        if resource_manager is not None:
            resource_manager.clear_cache(ResourceType.GRAPH, f"{graph_id}_metadata")

        # 2) 同步更新节点图库左侧卡片统计（仅更新当前列表中已存在的卡片）
        graph_library_widget = getattr(self, "graph_library_widget", None)
        if graph_library_widget is None:
            return

        # 避免旧请求回调误更新：确认节点图库当前选中仍指向同一张图
        get_selected_graph_id = getattr(graph_library_widget, "get_selected_graph_id", None)
        selected_graph_id = get_selected_graph_id() if callable(get_selected_graph_id) else getattr(graph_library_widget, "selected_graph_id", None)
        if str(selected_graph_id or "") != str(graph_id):
            return

        invalidate_meta_cache = getattr(graph_library_widget, "_invalidate_graph_metadata", None)
        if callable(invalidate_meta_cache):
            invalidate_meta_cache(graph_id)

        graph_cards = getattr(graph_library_widget, "graph_cards", None)
        if not isinstance(graph_cards, dict):
            return
        card_widget = graph_cards.get(graph_id)
        if card_widget is None:
            return

        existing_graph_data = getattr(card_widget, "graph_data", None)
        updated_graph_data = dict(existing_graph_data) if isinstance(existing_graph_data, dict) else {"graph_id": graph_id}
        updated_graph_data["node_count"] = node_count
        updated_graph_data["edge_count"] = edge_count

        reference_tracker = getattr(graph_library_widget, "reference_tracker", None)
        reference_count = reference_tracker.get_reference_count(graph_id) if reference_tracker is not None else 0

        error_tracker = getattr(graph_library_widget, "error_tracker", None)
        has_error = error_tracker.has_error(graph_id) if error_tracker is not None else False

        update_graph_info = getattr(card_widget, "update_graph_info", None)
        if callable(update_graph_info):
            update_graph_info(updated_graph_data, reference_count, has_error)

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

    def _refresh_node_library_and_sync_composites(self, *, reload_composite_widget_from_disk: bool) -> None:
        """刷新节点库（含复合节点）并同步 UI 上下文。

        说明：
        - 该入口用于“复合节点库发生变化”时的统一刷新：更新 NodeRegistry、替换主窗口与图编辑器所持有的 node_library，
          并按需同步当前打开节点图中已实例化的复合节点端口。
        - `reload_composite_widget_from_disk=True` 用于外部文件变更/资源库刷新场景：复合节点管理页需要重新扫描磁盘版本，
          否则其内部 CompositeNodeManager 仍会保留旧的内存索引。
        """
        registry = get_node_registry(self.app_state.workspace_path, include_composite=True)
        registry.refresh()
        updated_library = registry.get_library()

        self.app_state.node_library = updated_library

        # GraphEditorController/GraphView/GraphScene 的节点库应保持一致
        self.graph_controller.node_library = updated_library
        self.graph_controller.view.node_library = updated_library
        current_scene = self.graph_controller.get_current_scene()
        current_scene.node_library = updated_library

        composite_widget = getattr(self, "composite_widget", None)
        if composite_widget is not None:
            composite_widget.node_library = updated_library

            composite_graph_view = getattr(composite_widget, "graph_view", None)
            if composite_graph_view is not None:
                composite_graph_view.node_library = updated_library

            composite_graph_scene = getattr(composite_widget, "graph_scene", None)
            if composite_graph_scene is not None:
                composite_graph_scene.node_library = updated_library

            composite_graph_controller = getattr(composite_widget, "graph_editor_controller", None)
            if composite_graph_controller is not None:
                composite_graph_controller.node_library = updated_library

            # 关键：复合节点子图解析依赖 base_node_library；当节点库刷新后必须同步更新，
            # 否则仍可能用旧节点库解析子图并导致端口/类型不一致。
            composite_manager = getattr(composite_widget, "manager", None)
            composite_loader = getattr(composite_manager, "loader", None) if composite_manager is not None else None
            if composite_loader is not None:
                setattr(composite_loader, "base_node_library", updated_library)

            if reload_composite_widget_from_disk:
                reload_method = getattr(composite_widget, "reload_library_from_disk", None)
                if callable(reload_method):
                    reload_method()

        if self.graph_controller.current_graph_id:
            current_model = self.graph_controller.get_current_model()
            updated_count = current_model.sync_composite_nodes_from_library(updated_library)
            if updated_count > 0:
                log_info("[COMPOSITE] synced composite node ports: updated_count={}", updated_count)
                self._refresh_current_graph_display()

    def _on_composite_library_updated(self) -> None:
        """复合节点库更新"""
        # 复合节点库是 node_defs_fp 的组成部分：一旦更新，必须失效其指纹段缓存，
        # 否则节点库缓存/graph_cache 可能在短时间内继续误命中旧指纹。
        invalidate_composite_node_defs_fingerprint_cache()
        self._refresh_node_library_and_sync_composites(reload_composite_widget_from_disk=False)
        log_info("[COMPOSITE] composite library refreshed")

    def _refresh_current_graph_display(self) -> None:
        """刷新当前图显示"""
        current_scene = self.graph_controller.get_current_scene()

        # 先关闭可能悬挂在 viewport 上的 YDebug Tooltip，避免在清空场景时触发回调访问已释放图元。
        current_scene._close_ydebug_tooltip()

        # 关键：先清空 Python 侧图元索引，再调用 QGraphicsScene.clear()。
        # 原因：QGraphicsScene.clear() 会释放底层 C++ 图元；若 dict 仍持有包装对象，
        # 后续任何 UI 回调（例如 Tooltip close → clear_chain_highlight）都可能触发
        # `wrapped C/C++ object ... has been deleted` 崩溃。
        current_scene.node_items.clear()
        current_scene.edge_items.clear()
        if hasattr(current_scene, "_edges_by_node_id"):
            current_scene._edges_by_node_id.clear()

        current_scene.clear()

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

        # 导航历史：在进入复合节点模式后补齐“当前复合节点”上下文，支持后退/前进回放定位
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) == ViewMode.COMPOSITE:
            history = getattr(self, "navigation_history", None)
            if history is not None and bool(getattr(self, "_navigation_history_ready", False)):
                context_update = {"composite_id": str(composite_id or "").strip()}
                if composite is not None and getattr(composite, "node_name", None):
                    context_update["composite_name"] = str(getattr(composite, "node_name", "") or "")
                history.update_current_context(context_update)

        if composite:
            self.composite_property_panel.load_composite(composite)
            self.composite_pin_panel.load_composite(composite)
            # 与“打开节点图”一致：窗口标题显示当前打开/选中的资源名称（而不是内部ID）。
            if hasattr(self, "_update_window_title"):
                self._update_window_title(f"复合节点: {composite.node_name}")
        else:
            log_warn("[COMPOSITE] selected but composite not found: composite_id={}", composite_id)
            self.composite_property_panel.clear()
            self.composite_pin_panel.clear()
            if hasattr(self, "_update_window_title"):
                self._update_window_title("复合节点: 未选择")

    def _on_jump_to_graph_element(self, jump_info: Dict[str, Any]) -> None:
        """跳转到图元素（例如从预览/验证面板跳转）"""
        # GraphView 为全局共享画布：在 TODO 预览中触发的 jump 由 todo_binder 处理，
        # 避免这里再重复响应造成双重导航。
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) == ViewMode.TODO:
            return

        jump_type = jump_info.get("type", "")
        if jump_type == "composite_node":
            composite_id = str(jump_info.get("composite_id", "") or "").strip()
            composite_name = str(jump_info.get("composite_name", "") or "").strip()
            if not composite_id and not composite_name:
                return

            # 关键：无缝切换体验
            # - 先切到 COMPOSITE 模式（同步）；
            # - 立即选中并打开预览页，避免“先看到列表页再打开”的闪动。
            self.nav_coordinator.navigate_to_mode.emit("composite")

            def _select_target_composite() -> None:
                composite_widget = getattr(self, "composite_widget", None)
                if composite_widget is None:
                    return

                select_by_id = getattr(composite_widget, "select_composite_by_id", None)
                if composite_id and callable(select_by_id):
                    if select_by_id(composite_id):
                        return

                select_by_name = getattr(composite_widget, "select_composite_by_name", None)
                if composite_name and callable(select_by_name):
                    select_by_name(composite_name)

            _select_target_composite()
            # 兜底：若首次懒加载/布局导致 composite_widget 尚未就绪，则下一帧再尝试一次
            QtCore.QTimer.singleShot(0, _select_target_composite)

    def _on_select_composite_name(self, composite_name: str) -> None:
        """选择复合节点（来自跳转协调器）"""
        from app.models.view_modes import ViewMode

        if ViewMode.from_index(self.central_stack.currentIndex()) != ViewMode.COMPOSITE:
            self._on_mode_changed("composite")

        if (
            self.composite_widget
            and hasattr(self.composite_widget, "select_composite_by_name")
        ):
            # 同步选中并打开预览页，避免先显示列表页再进入预览
            self.composite_widget.select_composite_by_name(composite_name)




