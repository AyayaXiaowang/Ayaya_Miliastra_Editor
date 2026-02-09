from __future__ import annotations

from typing import Optional, Tuple
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.ui.graph.graph_view import GraphView
from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_canvas_host import GraphCanvasHost
from app.ui.graph.graph_view.shared_graph_view_lease import get_shared_graph_view_lease_manager
from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.todo.todo_config import TodoStyles, LayoutConstants, StepTypeRules
from app.ui.todo.todo_preview_controller import TodoPreviewController
from app.ui.todo.preview_graph_context_resolver import resolve_graph_preview_context
from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.todo.todo_widgets import create_execute_button
from engine.configs.settings import settings
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.todo.todo_ui_context import TodoUiContext


class _GraphPreviewLoadWorker(QtCore.QThread):
    """后台加载 graph_data（避免 UI 线程同步磁盘读取/解析导致卡顿）。"""

    succeeded = QtCore.pyqtSignal(int, str, object, str)  # request_id, graph_id, graph_data, cache_key
    failed = QtCore.pyqtSignal(int, str, str)  # request_id, graph_id, error_text

    def __init__(
        self,
        *,
        request_id: int,
        graph_root_id: str,
        graph_id: str,
        graph_data_service,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.request_id = int(request_id)
        self.graph_root_id = str(graph_root_id or "")
        self.graph_id = str(graph_id or "")
        self.graph_data_service = graph_data_service
        self.setObjectName(f"GraphPreviewLoadWorker#{self.request_id}")

    def run(self) -> None:
        if self.isInterruptionRequested():
            return
        if not self.graph_id:
            self.failed.emit(self.request_id, self.graph_id, "graph_id 为空，无法加载节点图数据。")
            return
        service = self.graph_data_service
        if service is None:
            self.failed.emit(self.request_id, self.graph_id, "GraphDataService 不可用，无法加载节点图数据。")
            return

        graph_data = service.load_graph_data(self.graph_id)
        if self.isInterruptionRequested():
            return
        if not isinstance(graph_data, dict):
            error_text = service.get_graph_load_error(self.graph_id) or (
                f"节点图 '{self.graph_id}' 不存在或已被删除。"
            )
            self.failed.emit(self.request_id, self.graph_id, str(error_text))
            return

        graph_root_id = self.graph_root_id
        if not graph_root_id:
            # graph_root_id 是 payload cache key 的必填项；用 graph_id 兜底保证 key 稳定
            graph_root_id = str(self.graph_id)

        cache_key = service.store_payload_graph_data(graph_root_id, self.graph_id, graph_data)
        self.succeeded.emit(self.request_id, self.graph_id, graph_data, str(cache_key or ""))


class TodoPreviewPanel(QtWidgets.QWidget):
    """右侧预览面板：加载/缓存、聚焦/高亮，并与控制器内聚。

    对外暴露：
    - preview_view: GraphView（供主窗口连接 jump_to_graph_element 信号）
    - execute_clicked、back_to_detail 请求信号
    - edit_requested(graph_id, graph_data, container)
    - recognition_focus_succeeded 透传（供执行桥接层联动）
    """

    execute_clicked = QtCore.pyqtSignal()
    execute_remaining_clicked = QtCore.pyqtSignal()
    back_to_detail_requested = QtCore.pyqtSignal()
    edit_requested = QtCore.pyqtSignal(str, dict, object)
    recognition_focus_succeeded = QtCore.pyqtSignal(list)
    # 预览中的节点/连线/空白单击信号（主要用于任务清单联动）
    node_clicked = QtCore.pyqtSignal(str)
    related_edge_clicked = QtCore.pyqtSignal(str, str, str)
    background_clicked = QtCore.pyqtSignal()

    def __init__(self, parent=None, ui_context: TodoUiContext | None = None) -> None:
        super().__init__(parent)
        self._ui_context = ui_context
        self.current_graph_id: Optional[str] = None
        self.current_graph_data: Optional[dict] = None
        self.current_template_or_instance = None
        self._todo_map: dict[str, object] = {}
        self._shared_preview_controller: TodoPreviewController | None = None
        self._shared_view_bound: bool = False
        # 图预览：异步加载 graph_data（磁盘 IO + 解析）与“加载完成后聚焦”
        self._graph_preview_load_request_id: int = 0
        self._graph_preview_load_worker: _GraphPreviewLoadWorker | None = None
        self._graph_controller_bound: bool = False
        self._pending_focus_after_graph_loaded: dict | None = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        toolbar = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(10)

        self.back_button = QtWidgets.QPushButton("← 返回详情")
        self.back_button.setStyleSheet(TodoStyles.back_button_qss())
        self.back_button.clicked.connect(self.back_to_detail_requested.emit)
        toolbar_layout.addWidget(self.back_button)

        self.execute_button = create_execute_button(
            toolbar,
            self.execute_clicked.emit,
        )
        toolbar_layout.addWidget(self.execute_button)

        # 执行剩余步骤（预览工具条版本）
        self.execute_remaining_button = QtWidgets.QPushButton("执行剩余步骤")
        self.execute_remaining_button.setStyleSheet(TodoStyles.execute_button_qss())
        self.execute_remaining_button.setVisible(False)
        # 将按钮点击转发为自身信号（供宿主连接）
        self.execute_remaining_button.clicked.connect(self.execute_remaining_clicked.emit)
        toolbar_layout.addWidget(self.execute_remaining_button)

        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        # 预览区域：图预览（共享画布）/复合节点预览（独立只读画布）。
        # 说明：复合节点的子图并非 ResourceType.GRAPH，不能走 GraphEditorController 的保存链路，
        # 因此仍保留一个独立只读预览画布，避免污染编辑器会话与落盘语义。
        self.preview_stack = QtWidgets.QStackedWidget()
        self.preview_stack.setObjectName("todoPreviewStack")

        # 0) 共享画布 Host（承载 app_state.graph_view）
        self.preview_canvas_host = GraphCanvasHost()
        self.preview_canvas_host.setObjectName("todoPreviewCanvasHost")
        self.preview_canvas_host.setMinimumHeight(LayoutConstants.PREVIEW_VIEW_MIN_HEIGHT)
        self.preview_stack.addWidget(self.preview_canvas_host)

        # 1) 复合节点预览画布（本地只读 GraphView）
        composite_capabilities = EditSessionCapabilities.read_only_preview()
        self._composite_preview_model: GraphModel = GraphModel()
        self._composite_preview_scene: GraphScene = GraphScene(
            self._composite_preview_model,
            read_only=True,
            edit_session_capabilities=composite_capabilities,
        )
        self._composite_preview_view: GraphView = GraphView(
            self._composite_preview_scene,
            edit_session_capabilities=composite_capabilities,
        )
        self._composite_preview_view.setObjectName("todoCompositePreviewGraphView")
        self._composite_preview_view.setMinimumHeight(LayoutConstants.PREVIEW_VIEW_MIN_HEIGHT)
        self._composite_preview_view.show_coordinates = True
        self._composite_preview_view.enable_click_signals = False
        self._composite_preview_controller: TodoPreviewController = TodoPreviewController(
            self._composite_preview_view
        )

        composite_page = QtWidgets.QWidget()
        composite_layout = QtWidgets.QVBoxLayout(composite_page)
        composite_layout.setContentsMargins(0, 0, 0, 0)
        composite_layout.setSpacing(0)
        composite_layout.addWidget(self._composite_preview_view)
        self.preview_stack.addWidget(composite_page)

        layout.addWidget(self.preview_stack)

        # 右上角“前往编辑”按钮（绑定到共享 GraphView 上，由 ensure_shared_canvas_attached() 负责挂载）
        self.preview_edit_button = QtWidgets.QPushButton("前往编辑", self)
        self.preview_edit_button.setObjectName("previewEditButton")
        self.preview_edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview_edit_button.setStyleSheet(TodoStyles.execute_button_qss())
        self.preview_edit_button.setVisible(False)
        self.preview_edit_button.setToolTip("前往节点图编辑器")
        self.preview_edit_button.clicked.connect(self._emit_edit_requested)

        # 与执行监控面板的“定位镜头识别回填”信号绑定状态（避免重复 connect）
        self._recognition_bound_monitor_panel = None

        # 注意：GraphView 是共享实例，点击信号绑定在首次 attach 时执行（避免构造期 main_window 未注入）。

    # === 预览內部交互映射 ===

    def _on_graph_element_clicked(self, info: dict) -> None:
        if not isinstance(info, dict):
            return
        element_type = info.get("type", "")
        if element_type == "node":
            node_id = str(info.get("node_id") or "")
            if node_id:
                self.node_clicked.emit(node_id)
        elif element_type == "edge":
            edge_id = str(info.get("edge_id") or "")
            src_node = str(info.get("src_node") or "")
            dst_node = str(info.get("dst_node") or "")
            if edge_id and src_node and dst_node:
                self.related_edge_clicked.emit(edge_id, src_node, dst_node)
        elif element_type == "background":
            # 清理由“单击节点/连线”引入的预览高亮与灰显，让画布回到基线状态
            self._clear_canvas_highlight_state()
            self.background_clicked.emit()

    def _clear_canvas_highlight_state(self) -> None:
        """清理预览画布的高亮/置灰/浮窗叠加（仅影响视觉，不改变树选中项）。"""
        view: GraphView | None = None

        # 复合节点预览使用独立画布（但默认不启用点击信号；此处仍保留兼容入口）
        if hasattr(self, "preview_stack") and self.preview_stack.currentIndex() == 1:
            candidate = getattr(self, "_composite_preview_view", None)
            if isinstance(candidate, GraphView):
                view = candidate
        else:
            if self._shared_preview_controller is not None:
                candidate = getattr(self._shared_preview_controller, "view", None)
                if isinstance(candidate, GraphView):
                    view = candidate
            if view is None:
                view = self._ensure_shared_canvas_attached()

        if view is None:
            return

        view.setUpdatesEnabled(False)
        try:
            view.clear_highlights()
            view.restore_all_opacity()
            overlay_manager = getattr(view, "overlay_manager", None)
            if overlay_manager is not None and hasattr(overlay_manager, "hide"):
                overlay_manager.hide()
        finally:
            view.setUpdatesEnabled(True)

    # === 外部交互 ===

    def set_execute_visible(self, visible: bool) -> None:
        self.execute_button.setVisible(visible)

    def set_execute_remaining_visible(self, visible: bool) -> None:
        self.execute_remaining_button.setVisible(visible)

    def set_execute_text(self, text: str) -> None:
        self.execute_button.setText(text)

    def set_execute_remaining_text(self, text: str) -> None:
        self.execute_remaining_button.setText(text)

    def get_current_graph_info(self) -> Tuple[Optional[str], Optional[dict], object]:
        return (self.current_graph_id, self.current_graph_data, self.current_template_or_instance)

    # === 共享画布（全局唯一 GraphView） ===

    def _ensure_shared_canvas_attached(self) -> Optional[GraphView]:
        """将全局唯一的 GraphView 挂载到预览容器，并确保预览控制器/信号就绪。"""
        if self._ui_context is None:
            return None

        app_state = self._ui_context.get_app_state()
        if app_state is None:
            return None

        shared_view = getattr(app_state, "graph_view", None)
        if not isinstance(shared_view, GraphView):
            return None

        # 当前预览切回“共享画布”页
        if hasattr(self, "preview_stack"):
            self.preview_stack.setCurrentIndex(0)

        main_window = self._ui_context.get_main_window()
        graph_controller = getattr(main_window, "graph_controller", None) if main_window is not None else None
        node_library = self._ui_context.try_get_node_library()

        # 统一通过租约服务管理共享画布的归属与只读能力切换
        lease_manager = get_shared_graph_view_lease_manager()
        lease_manager.acquire_for_todo_preview(
            graph_view=shared_view,
            todo_preview_host=self.preview_canvas_host,
            graph_controller=graph_controller,
            preview_edit_button=self.preview_edit_button,
            node_library=node_library,
        )

        # 4) 绑定“单击图元素”信号（幂等）
        if not self._shared_view_bound:
            shared_view.graph_element_clicked.connect(self._on_graph_element_clicked)
            self._shared_view_bound = True

        # 5) 预览控制器（只做高亮/聚焦，不负责重建 scene）
        if self._shared_preview_controller is None:
            self._shared_preview_controller = TodoPreviewController(shared_view)

        # 6) 监听 GraphEditorController.graph_loaded：用于非阻塞加载完成后再聚焦/高亮
        if (
            not self._graph_controller_bound
            and graph_controller is not None
            and hasattr(graph_controller, "graph_loaded")
        ):
            graph_controller.graph_loaded.connect(self._on_shared_graph_loaded)
            self._graph_controller_bound = True

        return shared_view

    def show_shared_canvas_now(self) -> None:
        """公开入口：立刻把共享画布挂到 Todo 预览页并显示出来。

        用途：从图编辑器跳到 Todo 时，让用户感觉画布没有“消失后再出现”。
        """
        _ = self._ensure_shared_canvas_attached()

    def bind_monitor_panel(self, monitor_panel, workspace_path: Path) -> None:
        """将执行监控面板与预览上下文绑定（供“检查/定位镜头/拖拽测试”等复用预览模型与视图）。

        注意：
        - 本方法可被频繁调用（切换任务/预览），因此必须保证信号连接是幂等的，不能重复 connect；
        """
        if monitor_panel is None:
            self.wire_recognition_from_monitor_panel(None)
            return

        # 若当前正在显示复合节点预览（独立画布），则将监控上下文绑定到该画布与模型。
        if hasattr(self, "preview_stack") and self.preview_stack.currentIndex() == 1:
            monitor_panel.set_context(workspace_path, self._composite_preview_model, self._composite_preview_view)
            self.wire_recognition_from_monitor_panel(monitor_panel)
            return

        if self._ui_context is None:
            return
        main_window = self._ui_context.get_main_window()
        if main_window is None:
            return
        shared_view = self._ensure_shared_canvas_attached()
        if shared_view is None:
            return

        graph_controller = getattr(main_window, "graph_controller", None)
        if graph_controller is None:
            return
        graph_model = graph_controller.get_current_model()
        monitor_panel.set_context(workspace_path, graph_model, shared_view)

        # 统一将监控面板的识别信号透传为本面板信号，外层只需监听一次即可
        self.wire_recognition_from_monitor_panel(monitor_panel)

    def wire_recognition_from_monitor_panel(self, monitor_panel) -> None:
        """将监控面板的 `recognition_focus_succeeded` 幂等绑定到本面板信号。

        - 该绑定不依赖 set_context，可供执行桥接层在注入执行上下文时复用；
        - 只允许存在一条当前有效的连接，避免重复回调导致的批量回填与勾选抖动。
        """
        if monitor_panel is self._recognition_bound_monitor_panel:
            return

        previous_panel = self._recognition_bound_monitor_panel
        if previous_panel is not None:
            previous_panel.recognition_focus_succeeded.disconnect(
                self._on_monitor_recognition_focus_succeeded
            )

        self._recognition_bound_monitor_panel = None

        if monitor_panel is None:
            return

        monitor_panel.recognition_focus_succeeded.connect(
            self._on_monitor_recognition_focus_succeeded
        )
        self._recognition_bound_monitor_panel = monitor_panel

    def _on_monitor_recognition_focus_succeeded(self, visible_node_ids: list[str]) -> None:
        self.recognition_focus_succeeded.emit(visible_node_ids)

    # === 预览加载 ===

    def handle_graph_preview(
        self,
        todo,
        todo_map: dict[str, object],
        *,
        tree_manager=None,
        ui_context: TodoUiContext | None = None,
    ) -> bool:
        """根据 todo 切换/加载预览并聚焦。
        返回是否显示预览（True → 应切换到预览页）。
        """
        shared_view = self._ensure_shared_canvas_attached()
        if shared_view is None:
            return False

        info = todo.detail_info or {}
        detail_type = info.get("type", "")

        # 非图相关步骤直接回退到详情页；图相关但显式标记为“仅详情展示”的同样不切到预览。
        if not StepTypeRules.is_graph_step(detail_type):
            return False
        # 特例：节点图变量步骤不属于“可执行叶子步骤”，但仍应保持共享画布可见，
        # 供用户在画布中对照变量使用位置；右侧面板会切到“图属性 → 节点图变量”。
        if not StepTypeRules.should_preview_graph(detail_type):
            if str(detail_type) != "graph_variables_table":
                return False

        # 注入节点库：供类型相关的高亮使用（例如仅高亮“泛型家族”端口）
        effective_context = ui_context or self._ui_context
        node_library = effective_context.try_get_node_library() if effective_context is not None else None
        if node_library:
            shared_view.node_library = node_library
            current_scene = shared_view.scene()
            if current_scene is not None and hasattr(current_scene, "node_library"):
                current_scene.node_library = node_library
        # 缓存 todo_map 供事件流聚焦时收集节点ID
        self._todo_map = dict(todo_map or {})

        resolved_tree_manager = tree_manager
        if resolved_tree_manager is None:
            return False
        if effective_context is None:
            return False

        graph_data, graph_id, template_or_instance = resolve_graph_preview_context(
            todo,
            todo_map,  # type: ignore[arg-type]
            tree_manager=resolved_tree_manager,
            graph_data_service=effective_context.get_graph_data_service(),
            current_package=effective_context.try_get_current_package(),
        )

        previous_graph_id = self.current_graph_id

        # graph_data 可能暂时不存在（仅有 graph_id，需要后台加载）
        effective_graph_id = str(
            graph_id
            or (graph_data.get("graph_id") if isinstance(graph_data, dict) else "")
            or info.get("graph_id")
            or "graph_preview"
        )

        self.current_graph_id = effective_graph_id
        self.current_template_or_instance = template_or_instance
        self.current_graph_data = graph_data if isinstance(graph_data, dict) else None

        main_window = effective_context.get_main_window()
        if main_window is None:
            return False
        graph_controller = getattr(main_window, "graph_controller", None)
        if graph_controller is None:
            return False

        controller_graph_id = str(getattr(graph_controller, "current_graph_id", "") or "")
        should_reload = controller_graph_id != effective_graph_id

        # 若正在加载同一张图：更新“加载完成后聚焦目标”，不在此时强行聚焦（避免空转/闪烁）
        pending = getattr(self, "_pending_focus_after_graph_loaded", None)
        if (
            not should_reload
            and isinstance(pending, dict)
            and str(pending.get("graph_id") or "") == str(effective_graph_id or "")
        ):
            pending["todo"] = todo
            return True

        # 预览已在该图上：直接聚焦即可
        if not should_reload:
            if hasattr(shared_view, "hide_loading_overlay"):
                shared_view.hide_loading_overlay()
            self._focus_and_highlight_task(todo)
            return True

        # 触发一次新的“预览加载请求”：用于取消旧 worker、过滤回调、聚焦门禁
        self._graph_preview_load_request_id = int(self._graph_preview_load_request_id) + 1
        request_id = int(self._graph_preview_load_request_id)
        self._cancel_pending_graph_preview_load()
        self._pending_focus_after_graph_loaded = None

        if settings.PREVIEW_VERBOSE:
            print(
                "[PREVIEW] 预览切换 → 使用共享画布加载: "
                f"prev_id={previous_graph_id}, curr_id={effective_graph_id}"
            )

        # graph_data 尚未就绪：后台加载（禁止 UI 线程同步触发磁盘读取/解析）
        if not isinstance(graph_data, dict):
            resolved_graph_id = str(graph_id or info.get("graph_id") or "")
            if not resolved_graph_id:
                return False
            self.current_graph_id = resolved_graph_id
            self._begin_graph_preview_loading_overlay(shared_view, graph_id=resolved_graph_id)
            self._set_pending_focus_after_graph_loaded(
                todo,
                expected_graph_id=resolved_graph_id,
                request_id=request_id,
            )
            self._start_async_graph_preview_load(
                request_id=request_id,
                todo=todo,
                todo_map=todo_map,
                tree_manager=resolved_tree_manager,
                effective_context=effective_context,
                graph_id=resolved_graph_id,
                template_or_instance=template_or_instance,
            )
            return True

        # 进入 Todo 预览：统一强制只读能力，避免任何编辑入口漏网。
        graph_controller.set_edit_session_capabilities(EditSessionCapabilities.read_only_preview())
        self._begin_graph_preview_loading_overlay(
            shared_view,
            graph_id=effective_graph_id,
            detail="构建预览画布…",
        )
        self._set_pending_focus_after_graph_loaded(
            todo,
            expected_graph_id=effective_graph_id,
            request_id=request_id,
        )
        if self._should_use_non_blocking_preview_load(graph_data):
            graph_controller.load_graph_non_blocking(
                effective_graph_id,
                graph_data,
                container=template_or_instance,
            )
        else:
            graph_controller.load_graph(effective_graph_id, graph_data, container=template_or_instance)

        # 加载后同步一次 node_library（只读预览高亮/端口类型依赖）
        node_library_after = effective_context.try_get_node_library()
        if node_library_after:
            shared_view.node_library = node_library_after
            current_scene = shared_view.scene()
            if current_scene is not None and hasattr(current_scene, "node_library"):
                current_scene.node_library = node_library_after

        # 聚焦/高亮统一改为在 graph_loaded 后执行（对非阻塞加载尤其重要）
        return True

    def _cancel_pending_graph_preview_load(self) -> None:
        worker = getattr(self, "_graph_preview_load_worker", None)
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
        self._graph_preview_load_worker = None

    def _begin_graph_preview_loading_overlay(
        self,
        shared_view: GraphView,
        *,
        graph_id: str,
        detail: str = "",
    ) -> None:
        if not hasattr(shared_view, "show_loading_overlay"):
            return
        shared_view.show_loading_overlay(
            title="正在加载节点图预览…",
            detail=str(detail or f"graph_id={graph_id}"),
            progress_value=None,
            progress_max=None,
        )

    def _set_pending_focus_after_graph_loaded(
        self,
        todo,
        *,
        expected_graph_id: str,
        request_id: int,
    ) -> None:
        self._pending_focus_after_graph_loaded = {
            "request_id": int(request_id),
            "graph_id": str(expected_graph_id or ""),
            "todo": todo,
        }

    def _should_use_non_blocking_preview_load(self, graph_data: dict) -> bool:
        nodes_value = graph_data.get("nodes") if isinstance(graph_data, dict) else None
        edges_value = graph_data.get("edges") if isinstance(graph_data, dict) else None
        node_count = len(nodes_value) if isinstance(nodes_value, (list, dict)) else 0
        edge_count = len(edges_value) if isinstance(edges_value, (list, dict)) else 0
        node_threshold = int(getattr(settings, "GRAPH_ASYNC_LOAD_NODE_THRESHOLD", 300) or 300)
        edge_threshold = int(getattr(settings, "GRAPH_ASYNC_LOAD_EDGE_THRESHOLD", 600) or 600)
        return bool(node_count >= node_threshold or edge_count >= edge_threshold)

    def _start_async_graph_preview_load(
        self,
        *,
        request_id: int,
        todo,
        todo_map: dict[str, object],
        tree_manager,
        effective_context: TodoUiContext,
        graph_id: str,
        template_or_instance,
    ) -> None:
        # 尽量找到“模板图根 todo_id”，作为 payload cache key 的 root_id（避免每个叶子步骤重复缓存）。
        detail_type = get_detail_type(todo)
        root_todo = None
        if StepTypeRules.is_graph_root(detail_type):
            root_todo = todo
        else:
            root_todo = tree_manager.find_template_graph_root_for_todo(todo.todo_id)

        graph_root_id = ""
        if root_todo is not None and getattr(root_todo, "todo_id", ""):
            graph_root_id = str(getattr(root_todo, "todo_id", "") or "")
        if not graph_root_id:
            graph_root_id = str(graph_id or "")

        self._graph_preview_load_worker = _GraphPreviewLoadWorker(
            request_id=int(request_id),
            graph_root_id=graph_root_id,
            graph_id=str(graph_id or ""),
            graph_data_service=effective_context.get_graph_data_service(),
            parent=self,
        )

        def _on_succeeded(_rid: int, loaded_graph_id: str, graph_data_obj: object, cache_key: str) -> None:
            if int(_rid) != int(getattr(self, "_graph_preview_load_request_id", 0)):
                return
            if str(loaded_graph_id or "") != str(graph_id or ""):
                return
            if not isinstance(graph_data_obj, dict):
                return

            # 写回 graph_data_key：后续 preview/执行/GraphModel 构建都可直接走进程内 payload 缓存
            if root_todo is not None:
                info = dict(getattr(root_todo, "detail_info", None) or {})
                if cache_key:
                    info["graph_data_key"] = str(cache_key)
                    info.pop("graph_data", None)
                    root_todo.detail_info = info

            self.current_graph_id = str(loaded_graph_id or "")
            self.current_graph_data = graph_data_obj
            self.current_template_or_instance = template_or_instance

            shared_view = self._ensure_shared_canvas_attached()
            if shared_view is not None and hasattr(shared_view, "update_loading_overlay_detail"):
                shared_view.update_loading_overlay_detail("构建预览画布…")

            main_window = effective_context.get_main_window()
            graph_controller = getattr(main_window, "graph_controller", None) if main_window is not None else None
            if graph_controller is None:
                return

            graph_controller.set_edit_session_capabilities(EditSessionCapabilities.read_only_preview())
            if self._should_use_non_blocking_preview_load(graph_data_obj):
                graph_controller.load_graph_non_blocking(
                    str(loaded_graph_id or ""),
                    graph_data_obj,
                    container=template_or_instance,
                )
            else:
                graph_controller.load_graph(
                    str(loaded_graph_id or ""),
                    graph_data_obj,
                    container=template_or_instance,
                )

        def _on_failed(_rid: int, failed_graph_id: str, error_text: str) -> None:
            if int(_rid) != int(getattr(self, "_graph_preview_load_request_id", 0)):
                return
            if str(failed_graph_id or "") != str(graph_id or ""):
                return
            shared_view = self._ensure_shared_canvas_attached()
            if shared_view is not None and hasattr(shared_view, "hide_loading_overlay"):
                shared_view.hide_loading_overlay()
            self._pending_focus_after_graph_loaded = None
            show_warning_dialog(self, "无法加载节点图预览", str(error_text or "加载失败"))

        worker = self._graph_preview_load_worker
        worker.succeeded.connect(_on_succeeded)
        worker.failed.connect(_on_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    @QtCore.pyqtSlot(str)
    def _on_shared_graph_loaded(self, graph_id: str) -> None:
        pending = getattr(self, "_pending_focus_after_graph_loaded", None)
        if not isinstance(pending, dict):
            return
        expected_graph_id = str(pending.get("graph_id") or "")
        if not expected_graph_id or str(graph_id or "") != expected_graph_id:
            return
        request_id = int(pending.get("request_id") or 0)
        if request_id != int(getattr(self, "_graph_preview_load_request_id", 0)):
            return
        todo = pending.get("todo")
        self._pending_focus_after_graph_loaded = None

        # 注意：graph_loaded 可能在用户已切回“详情/复合预览”等场景时到达。
        # 此处只负责清遮罩与同步 node_library，不强行切页/重挂载共享画布，避免打断用户当前上下文。
        shared_view: GraphView | None = None
        if self._ui_context is not None:
            app_state = self._ui_context.get_app_state()
            candidate = getattr(app_state, "graph_view", None) if app_state is not None else None
            if isinstance(candidate, GraphView):
                shared_view = candidate

        if shared_view is not None:
            node_library = (
                self._ui_context.try_get_node_library()
                if self._ui_context is not None
                else None
            )
            if node_library:
                shared_view.node_library = node_library
                current_scene = shared_view.scene()
                if current_scene is not None and hasattr(current_scene, "node_library"):
                    current_scene.node_library = node_library
            if hasattr(shared_view, "hide_loading_overlay"):
                shared_view.hide_loading_overlay()

        # 仅在“当前确实处于共享画布预览页”时才聚焦，避免后台加载完成后打断其它预览/详情。
        if not self.isVisible():
            return
        if hasattr(self, "preview_stack") and self.preview_stack.currentIndex() != 0:
            return
        if todo is None:
            return
        self._focus_and_highlight_task(todo)

    def handle_composite_preview(self, todo, ui_context: TodoUiContext | None) -> bool:
        detail_type = get_detail_type(todo)
        if not StepTypeRules.is_composite_step(detail_type):
            return False

        # 切到复合节点预览：取消可能仍在进行的“共享画布图预览加载”，避免后台回调打断当前上下文
        self._cancel_pending_graph_preview_load()
        self._pending_focus_after_graph_loaded = None
        if self._ui_context is not None:
            app_state = self._ui_context.get_app_state()
            candidate = getattr(app_state, "graph_view", None) if app_state is not None else None
            if isinstance(candidate, GraphView) and hasattr(candidate, "hide_loading_overlay"):
                candidate.hide_loading_overlay()

        info = todo.detail_info
        composite_id = info.get("composite_id", "") or todo.target_id
        if not composite_id:
            return False
        if ui_context is None:
            return False
        workspace_path = ui_context.try_get_workspace_path()
        if workspace_path is None:
            return False

        graph_data, composite_obj = self._composite_preview_controller.load_composite_internal_graph(
            composite_id,
            workspace_path,
        )
        if not (graph_data and isinstance(graph_data, dict) and ("nodes" in graph_data or "edges" in graph_data)):
            return False

        # 复合节点预览使用独立画布：切换到对应页面并加载子图
        self.preview_stack.setCurrentIndex(1)
        self.preview_edit_button.setVisible(False)

        self._composite_preview_model, self._composite_preview_scene = self._composite_preview_controller.load_graph_preview(
            graph_data
        )
        self._composite_preview_controller.focus_composite_task(todo, composite_obj)
        return True

    # === 内部 ===

    def _emit_edit_requested(self) -> None:
        gid, gdata, container = self.get_current_graph_info()
        if gid and isinstance(gdata, dict):
            self.edit_requested.emit(gid, gdata, container)

    def _focus_and_highlight_task(self, todo) -> None:
        if self._shared_preview_controller is None:
            return
        detail_type = get_detail_type(todo)
        if StepTypeRules.is_event_flow_root(detail_type):
            # 极少用到：此处仅保留逻辑完整
            node_ids = self._collect_nodes_from_subtasks(todo, self._todo_map)
            self._shared_preview_controller.focus_and_highlight_task(
                todo,
                event_flow_node_ids=node_ids,
            )
            return
        self._shared_preview_controller.focus_and_highlight_task(todo)

    def focus_on_node_group(self, node_ids: list[str]) -> None:
        """公开：聚焦一组节点（主要供 BasicBlock 分组头选中时使用）。"""
        if self._shared_preview_controller is None:
            return
        self._shared_preview_controller.focus_on_node_group(node_ids)

    def _collect_nodes_from_subtasks(self, todo, todo_map: dict) -> list[str]:
        node_ids: list[str] = []
        def collect_from_task(task_id: str):
            task = todo_map.get(task_id)
            if not task:
                return
            node_id = task.detail_info.get("node_id")
            if node_id and node_id not in node_ids:
                node_ids.append(node_id)
            src_node = task.detail_info.get("src_node")
            dst_node = task.detail_info.get("dst_node")
            if src_node and src_node not in node_ids:
                node_ids.append(src_node)
            if dst_node and dst_node not in node_ids:
                node_ids.append(dst_node)
            prev_node_id = task.detail_info.get("prev_node_id")
            if prev_node_id and prev_node_id not in node_ids:
                node_ids.append(prev_node_id)
            branch_node_id = task.detail_info.get("branch_node_id")
            if branch_node_id and branch_node_id not in node_ids:
                node_ids.append(branch_node_id)
            for child_id in task.children:
                collect_from_task(child_id)
        collect_from_task(todo.todo_id)
        return node_ids


