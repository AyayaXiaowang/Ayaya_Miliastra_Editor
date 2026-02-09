"""节点图编辑控制器 - 管理节点图的编辑逻辑

治理约束（重要）：
- 本文件仅负责：依赖注入、Qt 信号转发、调用流程服务；
- 跨域链路（load/save/validate/auto_layout_prepare）下沉到 `app.ui.controllers.graph_editor_flow`；
- 会话能力/只读语义/保存状态统一由状态机收敛为单一真源，避免分叉。
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.graph.models.graph_config import GraphConfig
from engine.layout import LayoutService
from engine.resources.graph_cache_facade import GraphCacheFacade
from engine.resources.resource_manager import ResourceManager
from engine.utils.graph.node_defs_fingerprint import compute_node_defs_fingerprint
from app.ui.graph.graph_undo import AddNodeCommand
from engine.nodes.node_definition_loader import NodeDef
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.graph.scene_builder import IncrementalScenePopulateJob
from app.ui.controllers.graph_error_tracker import get_instance as get_error_tracker
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.controllers.graph_editor_flow import (
    GraphEditorAutoLayoutPrepareService,
    GraphEditorLoadRequest,
    GraphEditorLoadService,
    GraphPrepareThread,
    GraphEditorSaveService,
    GraphEditorSessionStateMachine,
    GraphEditorValidateService,
    derive_initial_input_names_for_new_node,
)


@dataclass(slots=True)
class _GraphSceneCacheEntry:
    """运行期 GraphScene 缓存项（同一次进程内复用 QGraphicsItem）。"""

    graph_id: str
    model: GraphModel
    scene: GraphScene
    baseline_content_hash: str
    edit_session_capabilities: EditSessionCapabilities
    node_defs_fp: str
    layout_settings: dict
    build_settings_signature: tuple[tuple[str, object], ...]
    graph_file_path: str
    graph_file_mtime_ms: int


class GraphEditorController(QtCore.QObject):
    """节点图编辑管理控制器"""
    
    # 信号定义
    graph_loaded = QtCore.pyqtSignal(str)  # graph_id
    graph_saved = QtCore.pyqtSignal(str)  # graph_id
    graph_runtime_cache_updated = QtCore.pyqtSignal(str)  # graph_id（持久化缓存更新/强制重解析等）
    graph_validated = QtCore.pyqtSignal(list)  # issues
    validation_triggered = QtCore.pyqtSignal()
    switch_to_editor_requested = QtCore.pyqtSignal()  # 切换到编辑页面
    title_update_requested = QtCore.pyqtSignal(str)  # 更新窗口标题
    save_status_changed = QtCore.pyqtSignal(str)  # "saved" | "unsaved" | "saving" | "readonly"
    
    def __init__(
        self,
        resource_manager: ResourceManager,
        model: GraphModel,
        scene: GraphScene,
        view: GraphView,
        node_library: dict,
        *,
        edit_session_capabilities: EditSessionCapabilities | None = None,
        parent: Optional[QtCore.QObject] = None
    ):
        super().__init__(parent)
        
        self.resource_manager = resource_manager
        self.model = model
        self.scene = scene
        self.view = view
        self.node_library = node_library
        self._load_service = GraphEditorLoadService()
        self._save_service = GraphEditorSaveService()
        self._validate_service = GraphEditorValidateService()
        self._auto_layout_prepare_service = GraphEditorAutoLayoutPrepareService()
        # 额外场景参数（例如复合节点编辑上下文）
        self._scene_extra_options: dict = {}
        
        # 当前节点图状态（graph_id 由状态机持有，controller 只保留 container）
        self.current_graph_container = None  # 存储当前编辑的对象（template或instance）
        initial_capabilities: EditSessionCapabilities = (
            edit_session_capabilities
            if isinstance(edit_session_capabilities, EditSessionCapabilities)
            else EditSessionCapabilities.interactive_preview()
        )
        self._session_state_machine = GraphEditorSessionStateMachine(capabilities=initial_capabilities)
        
        # 用于获取存档（由主窗口设置）
        self.get_current_package = None
        self.get_property_panel_object_type = None
        
        # 错误跟踪器（单例）
        self.error_tracker = get_error_tracker()
        # 自动保存防抖计时器（根据全局设置控制）
        self._save_debounce_timer: Optional[QtCore.QTimer] = None
        # 下次自动排版前是否强制从 .py 重新解析（忽略持久化缓存）
        self._force_reparse_on_next_auto_layout: bool = False
        # 若自动排版前触发“重解析+重载”，则在加载完成后自动触发一次自动排版（避免 AutoLayout 在旧模型上运行）。
        self._pending_auto_layout_after_reparse_graph_id: str | None = None
        # 仅在重解析重载链路中使用：保存并在“加载完成”后恢复视图中心/缩放，避免画面跳变。
        self._pending_view_restore_after_reparse: dict | None = None

        # === 大图加载：后台准备 + 主线程分帧装配（避免阻塞 UI） ===
        self._async_load_generation: int = 0
        self._async_prepare_thread: GraphPrepareThread | None = None
        self._async_populate_job: IncrementalScenePopulateJob | None = None
        self._async_batch_build_context: dict | None = None
        # 仅对“用户显式打开图”的路径应用镜头策略（避免内部重载/重建场景破坏用户视角）
        self._pending_post_load_camera_graph_id: str | None = None

        # === 运行期 GraphScene LRU 缓存（A→B→A 秒切回，避免重建 QGraphicsItem）===
        # 约定：缓存仅覆盖“同一次程序运行期内”的切图；跨重启不可能复用 Qt 图元对象。
        self._scene_lru_cache: "OrderedDict[str, _GraphSceneCacheEntry]" = OrderedDict()
        # 非阻塞加载 attach 阶段：是否清空旧场景（若旧场景被缓存则必须跳过 clear）
        self._async_clear_old_scene_on_attach: bool = True

        # 启动时同步一次能力到初始 scene/view，避免出现“控制器能力已设定但 view/scene 仍沿用旧状态”。
        self._apply_edit_session_capabilities_to_view_and_scene()

    # === EditSessionCapabilities + save_status（单一真源：状态机） ===

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._session_state_machine.capabilities

    def set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        current_hash = self.model.get_content_hash() if self.model is not None else None
        new_status = self._session_state_machine.set_capabilities(capabilities, current_content_hash=current_hash)
        self._apply_edit_session_capabilities_to_view_and_scene()
        self.save_status_changed.emit(new_status)

    def _apply_edit_session_capabilities_to_view_and_scene(self) -> None:
        capabilities = self._session_state_machine.capabilities
        if self.view is not None and hasattr(self.view, "set_edit_session_capabilities"):
            self.view.set_edit_session_capabilities(capabilities)
        if self.scene is not None and hasattr(self.scene, "set_edit_session_capabilities"):
            self.scene.set_edit_session_capabilities(capabilities)

        if self.view is not None:
            # “添加节点”入口仅在可交互会话开放
            self.view.on_add_node_callback = (
                self.add_node_at_position if capabilities.can_interact else None
            )

    # === GraphScene 运行期 LRU 缓存（QGraphicsItem 复用；同进程 A→B→A 秒切回）===

    def _get_graph_scene_lru_cache_capacity(self) -> int:
        from engine.configs.settings import settings as _settings_ui

        capacity = int(getattr(_settings_ui, "GRAPH_SCENE_LRU_CACHE_SIZE", 2) or 2)
        return int(capacity) if int(capacity) > 0 else 0

    def _is_graph_scene_lru_cache_enabled(self) -> bool:
        return self._get_graph_scene_lru_cache_capacity() > 0

    def _current_graph_scene_build_settings_signature(self) -> tuple[tuple[str, object], ...]:
        """影响 GraphScene/图元装配的设置签名（用于缓存失效判定）。"""
        from engine.configs.settings import settings as _settings_ui

        keys = [
            # 行内常量控件虚拟化：节点图元是否常驻创建 QGraphicsProxyWidget
            "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED",
            # 大图快速预览：是否创建端口/常量控件等重图元
            "GRAPH_FAST_PREVIEW_ENABLED",
            "GRAPH_FAST_PREVIEW_NODE_THRESHOLD",
            "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD",
            # 批量边层：是否创建 BatchedFastPreviewEdgeLayer（替代 per-edge item）
            "GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED",
            "GRAPH_READONLY_BATCHED_EDGES_ENABLED",
            "GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_CELL_SIZE",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_PICK_STROKE_WIDTH",
            "GRAPH_FAST_PREVIEW_BATCHED_EDGE_BOUNDS_MARGIN",
            # YDebug 会强制关闭批量边层（依赖逐边图元）
            "SHOW_LAYOUT_Y_DEBUG",
            # basic blocks 可能在 GraphScene 初始化阶段被补算（开关变化需失效缓存）
            "SHOW_BASIC_BLOCKS",
        ]
        return tuple((k, getattr(_settings_ui, k, None)) for k in keys)

    def _get_graph_file_fingerprint(self, graph_id: str) -> tuple[str, int]:
        """返回 (resolved_path_posix, mtime_ms)；无法定位则返回 ("", 0)。"""
        file_path = self.resource_manager.get_graph_file_path(str(graph_id))
        if file_path is None:
            return "", 0
        if not file_path.exists():
            return "", 0
        resolved_path = file_path.resolve().as_posix()
        mtime_ms = int(file_path.stat().st_mtime * 1000)
        return str(resolved_path), int(mtime_ms)

    def _dispose_scene_cache_entry(self, entry: _GraphSceneCacheEntry) -> None:
        scene = getattr(entry, "scene", None)
        if scene is None:
            return
        scene.clear()
        if hasattr(scene, "node_items"):
            scene.node_items.clear()
        if hasattr(scene, "edge_items"):
            scene.edge_items.clear()
        if hasattr(scene, "undo_manager") and getattr(scene, "undo_manager", None) is not None:
            scene.undo_manager.clear()
        # GraphScene/QGraphicsScene 为 QObject：尽量让 Qt 侧也及时释放
        if hasattr(scene, "deleteLater"):
            scene.deleteLater()

    def _clear_scene_lru_cache(self) -> None:
        cache = getattr(self, "_scene_lru_cache", None)
        if not isinstance(cache, OrderedDict) or not cache:
            return
        for entry in list(cache.values()):
            self._dispose_scene_cache_entry(entry)
        cache.clear()

    def _trim_scene_lru_cache(self) -> None:
        capacity = int(self._get_graph_scene_lru_cache_capacity())
        if capacity <= 0:
            self._clear_scene_lru_cache()
            return
        while len(self._scene_lru_cache) > capacity:
            _graph_id, evicted = self._scene_lru_cache.popitem(last=False)
            self._dispose_scene_cache_entry(evicted)

    def _is_scene_cache_entry_compatible(
        self,
        entry: _GraphSceneCacheEntry,
        *,
        expected_capabilities: EditSessionCapabilities,
    ) -> bool:
        if not isinstance(entry, _GraphSceneCacheEntry):
            return False
        if not entry.graph_id:
            return False
        if entry.scene is None or entry.model is None:
            return False
        if bool(getattr(entry.scene, "is_composite_editor", False)):
            return False

        # 能力不一致：fast_preview_mode / read_only 等图元结构可能不一致，禁止复用
        if entry.edit_session_capabilities != expected_capabilities:
            return False

        # 节点实现/解析器变更：必须失效（避免复用旧端口规则/标题等）
        current_node_defs_fp = compute_node_defs_fingerprint(self.resource_manager.workspace_path)
        if str(entry.node_defs_fp or "") != str(current_node_defs_fp or ""):
            return False

        # 布局设置快照：切换布局语义后不应复用旧场景（避免结构增强/副本等差异）
        current_layout_settings = GraphCacheFacade.current_layout_settings_snapshot()
        if entry.layout_settings != current_layout_settings:
            return False

        # 画布装配开关：影响图元结构/边层，必须一致
        if entry.build_settings_signature != self._current_graph_scene_build_settings_signature():
            return False

        # 图文件变更：必须失效（避免显示旧模型）
        current_path, current_mtime_ms = self._get_graph_file_fingerprint(entry.graph_id)
        if not current_path or int(current_mtime_ms) <= 0:
            return False
        if str(entry.graph_file_path or "") != str(current_path):
            return False
        if int(entry.graph_file_mtime_ms) != int(current_mtime_ms):
            return False

        return True

    def _pop_scene_from_cache_if_compatible(
        self,
        *,
        graph_id: str,
        expected_capabilities: EditSessionCapabilities,
    ) -> _GraphSceneCacheEntry | None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return None
        entry = self._scene_lru_cache.get(graph_id_text)
        if entry is None:
            return None
        if not self._is_scene_cache_entry_compatible(entry, expected_capabilities=expected_capabilities):
            self._scene_lru_cache.pop(graph_id_text, None)
            self._dispose_scene_cache_entry(entry)
            return None
        return self._scene_lru_cache.pop(graph_id_text)

    def _cache_current_scene_as_inactive(self, *, next_graph_id: str) -> bool:
        """将当前 graph 的 scene 作为“非激活缓存”存入 LRU（用于 A→B→A 秒切回）。"""
        if not self._is_graph_scene_lru_cache_enabled():
            return False

        current_graph_id = str(self.current_graph_id or "").strip()
        if not current_graph_id:
            return False
        if str(next_graph_id or "").strip() == current_graph_id:
            return False
        if self.scene is None or self.model is None:
            return False
        if bool(getattr(self.scene, "is_composite_editor", False)):
            return False
        # 若仍在“非阻塞分帧装配”中：避免缓存半成品场景
        if self._async_populate_job is not None:
            return False

        file_path, file_mtime_ms = self._get_graph_file_fingerprint(current_graph_id)
        if not file_path or int(file_mtime_ms) <= 0:
            return False

        baseline_hash = str(self._session_state_machine.baseline_content_hash or "").strip()
        if not baseline_hash:
            baseline_hash = self.model.get_content_hash()

        entry = _GraphSceneCacheEntry(
            graph_id=str(current_graph_id),
            model=self.model,
            scene=self.scene,
            baseline_content_hash=str(baseline_hash),
            edit_session_capabilities=self._session_state_machine.capabilities,
            node_defs_fp=compute_node_defs_fingerprint(self.resource_manager.workspace_path),
            layout_settings=GraphCacheFacade.current_layout_settings_snapshot(),
            build_settings_signature=self._current_graph_scene_build_settings_signature(),
            graph_file_path=str(file_path),
            graph_file_mtime_ms=int(file_mtime_ms),
        )

        existing = self._scene_lru_cache.pop(str(current_graph_id), None)
        if existing is not None:
            # 兜底：理论上 active graph 不应同时在 cache 中；若存在且不是同一个 scene，则释放旧缓存项
            if getattr(existing, "scene", None) is not self.scene:
                self._dispose_scene_cache_entry(existing)

        self._scene_lru_cache[str(current_graph_id)] = entry
        self._scene_lru_cache.move_to_end(str(current_graph_id))
        self._trim_scene_lru_cache()
        return True

    def _restore_graph_from_scene_cache_entry(
        self,
        *,
        entry: _GraphSceneCacheEntry,
        request: GraphEditorLoadRequest,
    ) -> None:
        """将缓存的 GraphScene 重新挂回 view，并走统一收尾（graph_loaded/save_status/camera）。"""
        graph_id = str(entry.graph_id)
        scene = entry.scene
        model = entry.model

        # 复用场景时将 node_library 指向当前库（避免引用旧 dict）
        if hasattr(scene, "node_library"):
            scene.node_library = self.node_library

        self._load_service.attach_scene_to_view_for_load(
            scene=scene,
            view=self.view,
            node_library=self.node_library,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = model
        self.scene = scene
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 加载后按需同步信号节点端口（保持与正常加载口径一致）
        self._load_service.sync_signals_after_load_if_needed(
            scene=self.scene,
            model=self.model,
            get_current_package=self.get_current_package,
        )

        baseline_hash = self.model.get_content_hash()
        self._finalize_after_graph_loaded(
            graph_id=str(graph_id),
            container=request.container,
            baseline_hash=str(baseline_hash),
        )

    # === 兼容字段：logic_read_only（历史语义） ===

    @property
    def logic_read_only(self) -> bool:
        """历史字段：映射为“不可保存到资源落盘”。"""
        return not self._session_state_machine.capabilities.can_persist

    @logic_read_only.setter
    def logic_read_only(self, value: bool) -> None:
        # 兼容旧写法：只改“可保存”能力位；可保存要求可校验，交由 EditSessionCapabilities 自身约束。
        self.set_edit_session_capabilities(
            self._session_state_machine.capabilities.with_overrides(can_persist=not bool(value))
        )

    @property
    def current_graph_id(self) -> Optional[str]:
        """当前图 id：由状态机持有，避免与 save_status/baseline 分叉。"""
        return self._session_state_machine.current_graph_id

    @current_graph_id.setter
    def current_graph_id(self, value: Optional[str]) -> None:
        # 兼容旧代码：允许外部清空 current_graph_id（例如缓存清理回退逻辑）。
        if value is None:
            self._session_state_machine.on_graph_closed()
            return
        self._session_state_machine.current_graph_id = str(value)

    def schedule_reparse_on_next_auto_layout(self) -> None:
        """安排在下一次自动排版前强制从 .py 重新解析当前图（忽略持久化缓存）。"""
        self._force_reparse_on_next_auto_layout = True

    def prepare_for_auto_layout(self) -> bool:
        """在自动排版前按需（一次性标记）重建模型：清缓存→从 .py 解析→替换到场景。
        
        说明：
        - 默认不重载，避免打断当前视图缩放/中心导致“居中偏移”的体验问题。
        - 当设置页面触发一次性标记（例如 DATA_NODE_CROSS_BLOCK_COPY 从 True→False）时，
          才进行清缓存与重载；重载前后会保存并恢复视图缩放与中心点，保持画面稳定。

        返回：
        - True：本次触发了“重解析+重载”，自动排版应延后到加载完成后再执行
        - False：未触发重载，可立即继续自动排版
        """
        if not self.current_graph_id:
            self._force_reparse_on_next_auto_layout = False
            return False

        graph_id = str(self.current_graph_id)
        
        # 仅当被安排“下一次自动排版前强制重解析”时才执行重载
        should_reparse = bool(self._force_reparse_on_next_auto_layout)
        if not should_reparse:
            return False

        # 先清除一次性标记，避免“重载完成后自动触发排版”再次走重解析
        self._force_reparse_on_next_auto_layout = False

        # 保存当前视图的缩放与中心（场景坐标系下的中心点），在加载完成后恢复
        prev_center_xy: tuple[float, float] | None = None
        prev_scale = 1.0
        if self.view is not None:
            viewport_center = self.view.viewport().rect().center()
            prev_center_scene = self.view.mapToScene(viewport_center)
            prev_center_xy = (float(prev_center_scene.x()), float(prev_center_scene.y()))
            prev_scale = float(self.view.transform().m11())
        
        # 清除该图的内存与持久化缓存，使后续加载直接解析 .py
        reparse_result = self._auto_layout_prepare_service.reparse_graph_from_py(
            resource_manager=self.resource_manager,
            graph_id=graph_id,
        )
        # 通知主窗口统一失效 GraphDataService / 图属性面板等上层缓存，避免仍拿到旧数据。
        self.graph_runtime_cache_updated.emit(graph_id)
        
        if not reparse_result.graph_data:
            self._pending_auto_layout_after_reparse_graph_id = None
            self._pending_view_restore_after_reparse = None
            return False

        # 标记：加载完成后自动恢复视图 + 自动排版
        self._pending_auto_layout_after_reparse_graph_id = str(graph_id)
        self._pending_view_restore_after_reparse = {
            "graph_id": str(graph_id),
            "center": prev_center_xy,
            "scale": float(prev_scale),
        }

        # 重新加载并替换到场景（使用解析结果中的 data 字段）；自动排版将延后到加载完成后触发
        self.load_graph(graph_id, reparse_result.graph_data, container=self.current_graph_container)
        return True

    def rebuild_scene_for_settings_change(self, *, preserve_view: bool = True) -> None:
        """基于当前模型重建 GraphScene 与图元，用于设置变更后立即生效。

        设计目标：
        - **不改变会话状态机的 baseline/dirty/save_status**（避免把“未保存修改”误判为已保存）；
        - 主要用于“画布性能相关开关”切换后，需要重新构建图元才能生效的场景：
          fast_preview_mode、行内常量控件虚拟化、批量边层等。

        注意：
        - 该方法不会触发 `graph_loaded` 信号；它属于“重建显示层”，不是重新加载另一张图。
        """
        # 设置变更可能影响 GraphScene/图元结构：清空运行期 scene 缓存，避免复用旧渲染策略
        self._clear_scene_lru_cache()
        if not self.current_graph_id:
            return
        if self.model is None or self.scene is None or self.view is None:
            return

        # 保存视图状态（缩放 + 视口中心的场景坐标），用于重建后恢复。
        prev_transform = None
        prev_center_scene = None
        if preserve_view:
            prev_transform = self.view.transform()
            viewport_center = self.view.viewport().rect().center()
            prev_center_scene = self.view.mapToScene(viewport_center)

        # 保存会话状态机关键字段（重建不应影响 dirty 判定）
        state_machine = self._session_state_machine
        prev_graph_id = state_machine.current_graph_id
        prev_baseline_hash = state_machine.baseline_content_hash

        graph_data = self.model.serialize()
        if not isinstance(graph_data, dict) or not graph_data:
            return

        load_result = self._load_service.load(
            request=GraphEditorLoadRequest(
                graph_id=str(self.current_graph_id),
                graph_data=graph_data,
                container=self.current_graph_container,
            ),
            current_scene=self.scene,
            view=self.view,
            node_library=self.node_library,
            edit_session_capabilities=state_machine.capabilities,
            base_scene_extra_options=self._scene_extra_options,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = load_result.model
        self.scene = load_result.scene
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 恢复会话状态机（保持 baseline 不变）
        state_machine.current_graph_id = prev_graph_id
        state_machine.baseline_content_hash = prev_baseline_hash

        # 重新派生 save_status（避免状态机与新 model 分叉）
        current_hash = self.model.get_content_hash() if self.model is not None else None
        if not state_machine.capabilities.can_persist:
            state_machine.save_status = "readonly"
        else:
            if prev_graph_id is None:
                state_machine.save_status = "saved"
            elif prev_baseline_hash is None or current_hash is None:
                state_machine.save_status = "unsaved"
            else:
                state_machine.save_status = (
                    "saved" if str(current_hash) == str(prev_baseline_hash) else "unsaved"
                )
        self.save_status_changed.emit(state_machine.save_status)

        # 恢复视图状态（尽量保持画面稳定）
        if preserve_view and prev_transform is not None:
            self.view.setTransform(prev_transform)
        if preserve_view and prev_center_scene is not None:
            self.view.centerOn(prev_center_scene)

    def load_graph_for_composite(
        self,
        composite_id: str,
        graph_data: dict,
        *,
        composite_edit_context: dict,
    ) -> None:
        """加载复合节点子图到编辑器（含预排版与复合上下文注入）。

        设计目标：
        - 由控制器统一负责对子图做一次预排版（LayoutService.compute_layout）；
        - 将复合节点专用的 composite_edit_context 通过 scene_extra_options 注入 GraphScene；
        - UI 层仅关心“当前选中的复合节点 ID 与其子图数据”，不再手动构造场景与批量 add_node/add_edge。
        """
        if not graph_data or not isinstance(graph_data, dict):
            raise ValueError("复合节点子图数据为空或类型错误")

        # 1) 在当前进程内对复合节点子图做一次事件区域预排版（不落盘，仅调整位置语义）。
        pre_layout_model = GraphModel.deserialize(graph_data)

        # 1.1) 复合节点子图的端口类型展示需要“有效类型快照”（input_types/output_types）。
        # 普通节点图加载由资源层 GraphLoader 在写 graph_cache 时补齐；但复合节点预览页直接加载 sub_graph，
        # 因此必须在此处补齐：
        # - 将虚拟引脚上声明的具体类型写入 metadata.port_type_overrides（按 mapped_ports 定位到内部端口）；
        # - 再对整张子图执行一次“有效端口类型推断 → 快照写回”，避免 UI 长期显示为“泛型”。
        manager = composite_edit_context.get("manager") if isinstance(composite_edit_context, dict) else None
        if manager is not None and composite_id:
            load_subgraph_if_needed = getattr(manager, "load_subgraph_if_needed", None)
            if callable(load_subgraph_if_needed):
                load_subgraph_if_needed(str(composite_id))
            get_composite_node = getattr(manager, "get_composite_node", None)
            composite_config = get_composite_node(str(composite_id)) if callable(get_composite_node) else None
            virtual_pins = list(getattr(composite_config, "virtual_pins", []) or []) if composite_config is not None else []
            if virtual_pins:
                meta = getattr(pre_layout_model, "metadata", None)
                if not isinstance(meta, dict):
                    meta = {}
                    pre_layout_model.metadata = meta
                overrides = meta.get("port_type_overrides")
                if not isinstance(overrides, dict):
                    overrides = {}
                    meta["port_type_overrides"] = overrides
                for vpin in virtual_pins:
                    if bool(getattr(vpin, "is_flow", False)):
                        continue
                    pin_type_text = str(getattr(vpin, "pin_type", "") or "").strip()
                    if not pin_type_text or pin_type_text == "泛型":
                        continue
                    for mapped in (getattr(vpin, "mapped_ports", None) or []):
                        if bool(getattr(mapped, "is_flow", False)):
                            continue
                        node_id = str(getattr(mapped, "node_id", "") or "").strip()
                        port_name = str(getattr(mapped, "port_name", "") or "").strip()
                        if not node_id or not port_name:
                            continue
                        per_node = overrides.get(node_id)
                        if not isinstance(per_node, dict):
                            per_node = {}
                            overrides[node_id] = per_node
                        per_node[port_name] = pin_type_text

        LayoutService.compute_layout(
            pre_layout_model,
            node_library=self.node_library,
            clone_model=False,
        )

        from engine.resources.graph_loader import GraphLoader

        GraphLoader._apply_port_type_snapshots(pre_layout_model, node_library=self.node_library)  # type: ignore[attr-defined]
        layouted_graph_data = pre_layout_model.serialize()

        # 2) 注入复合节点编辑上下文（仅对本次加载生效）：由 GraphScene 消费，用于端口同步与虚拟引脚回调。
        # 注意：不写入控制器全局 `_scene_extra_options`，避免污染后续普通图加载。
        scene_extra_options_override = {
            "composite_edit_context": dict(composite_edit_context or {}),
        }

        # 3) 复用通用加载管线，确保布局/场景装配/小地图等行为与普通图一致。
        effective_graph_id = composite_id or "composite_graph"
        self._load_graph_pipeline(
            GraphEditorLoadRequest(
                graph_id=effective_graph_id,
                graph_data=layouted_graph_data,
                container=None,
                scene_extra_options_override=scene_extra_options_override,
            ),
        )

    def load_graph(self, graph_id: str, graph_data: dict, container=None) -> None:
        """加载节点图
        
        Args:
            graph_id: 节点图ID
            graph_data: 节点图数据
            container: 容器对象（模板或实例）
        """
        self._load_graph_pipeline(GraphEditorLoadRequest(graph_id=graph_id, graph_data=graph_data, container=container))

    def load_graph_non_blocking(
        self,
        graph_id: str,
        graph_data: dict,
        container=None,
        *,
        scene_extra_options_override: dict | None = None,
    ) -> None:
        """非阻塞加载节点图（后台准备模型 + 主线程分帧装配图元）。

        注意：该入口主要用于“用户显式打开超大图”的场景；
        对内部重载/重建显示层等需要同步完成的链路，仍应使用 `load_graph()`（同步）。
        """
        self._load_graph_pipeline_non_blocking(
            GraphEditorLoadRequest(
                graph_id=str(graph_id),
                graph_data=graph_data,
                container=container,
                scene_extra_options_override=scene_extra_options_override,
            )
        )

    def _estimate_graph_size_from_data(self, graph_data: dict) -> tuple[int, int]:
        """从序列化 dict 估算节点/连线数量（用于选择加载策略）。"""
        if not isinstance(graph_data, dict):
            return 0, 0
        nodes_value = graph_data.get("nodes")
        edges_value = graph_data.get("edges")

        # GraphModel.serialize 的唯一格式：nodes/edges 为 list[dict]
        # 但为兼容旧缓存/工具链输入，这里同时兼容 dict（id->payload）形式。
        if isinstance(nodes_value, list):
            node_count = int(len(nodes_value))
        elif isinstance(nodes_value, dict):
            node_count = int(len(nodes_value))
        else:
            node_count = 0

        if isinstance(edges_value, list):
            edge_count = int(len(edges_value))
        elif isinstance(edges_value, dict):
            edge_count = int(len(edges_value))
        else:
            edge_count = 0
        return node_count, edge_count

    def _should_use_non_blocking_load(self, graph_data: dict) -> bool:
        """是否对当前图启用“非阻塞加载”。

        约定：
        - 阈值走 settings（缺省值足够保守），便于后续按体验调参而不改代码；
        - 只作为“打开图”的 UI 体验策略，不影响其它内部管线。
        """
        from engine.configs.settings import settings as _settings_ui

        node_count, edge_count = self._estimate_graph_size_from_data(graph_data)
        node_threshold = int(getattr(_settings_ui, "GRAPH_ASYNC_LOAD_NODE_THRESHOLD", 300) or 300)
        edge_threshold = int(getattr(_settings_ui, "GRAPH_ASYNC_LOAD_EDGE_THRESHOLD", 600) or 600)
        return bool(node_count >= node_threshold or edge_count >= edge_threshold)

    def _cancel_pending_non_blocking_load(self) -> None:
        job = getattr(self, "_async_populate_job", None)
        if job is not None:
            job.cancel()
        self._async_populate_job = None

        thread = getattr(self, "_async_prepare_thread", None)
        if thread is not None and thread.isRunning():
            thread.requestInterruption()
        self._async_prepare_thread = None

        self._async_batch_build_context = None

    def _load_graph_pipeline_non_blocking(self, load_request: GraphEditorLoadRequest) -> None:
        """非阻塞节点图加载管线（后台准备模型 + 主线程分帧装配）。"""
        graph_id = str(load_request.graph_id)
        container = load_request.container

        self._async_load_generation += 1
        generation = int(self._async_load_generation)

        # 取消上一轮未完成任务（若存在）
        self._cancel_pending_non_blocking_load()

        # 运行期 GraphScene LRU 缓存：若目标图仍在内存中且兼容，则直接秒切回（无需后台准备/分帧装配）
        cached_entry: _GraphSceneCacheEntry | None = None
        current_graph_id = str(self.current_graph_id or "").strip()
        if graph_id and graph_id != current_graph_id:
            cached_entry = self._pop_scene_from_cache_if_compatible(
                graph_id=str(graph_id),
                expected_capabilities=self._session_state_machine.capabilities,
            )

        # 切图：将当前图作为“非激活缓存”存入 LRU（若符合条件）
        cached_source = self._cache_current_scene_as_inactive(next_graph_id=str(graph_id))
        # 后续 attach 新场景时是否清空旧场景：若旧场景已缓存则必须跳过 clear
        self._async_clear_old_scene_on_attach = not bool(cached_source)

        if cached_entry is not None:
            if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
                self.view.hide_loading_overlay()
            self._restore_graph_from_scene_cache_entry(entry=cached_entry, request=load_request)
            return

        print(f"[加载] 开始加载节点图（非阻塞）: {graph_id}")
        if self.view is not None and hasattr(self.view, "show_loading_overlay"):
            self.view.show_loading_overlay(
                title=f"正在加载节点图：{graph_id}",
                detail="准备模型（反序列化/语义对齐）…",
                progress_value=None,
                progress_max=None,
            )

        thread = GraphPrepareThread(
            graph_id=str(graph_id),
            graph_data=load_request.graph_data,
            node_library=self.node_library,
            parent=self,
        )
        self._async_prepare_thread = thread

        def _on_finished() -> None:
            self._on_non_blocking_prepare_finished(
                generation=generation,
                thread=thread,
                container=container,
                scene_extra_options_override=load_request.scene_extra_options_override,
            )

        thread.finished.connect(_on_finished)
        thread.start()

    def _on_non_blocking_prepare_finished(
        self,
        *,
        generation: int,
        thread: GraphPrepareThread,
        container: object | None,
        scene_extra_options_override: dict | None,
    ) -> None:
        if int(generation) != int(getattr(self, "_async_load_generation", 0)):
            return

        result = getattr(thread, "result", None)
        if result is None:
            raise RuntimeError("GraphPrepareThread 失败：未返回 result（详见控制台 traceback）")

        graph_id = str(result.graph_id)
        model = result.model
        baseline_hash = str(result.baseline_content_hash)

        # 清空旧场景以释放图元；随后会替换为新 GraphScene。
        # 若旧场景已被 LRU 缓存（切图秒切回），则必须跳过 clear，避免把缓存图元清掉。
        should_clear_old = bool(getattr(self, "_async_clear_old_scene_on_attach", True))
        if should_clear_old and self.scene is not None:
            self.scene.clear()

        edit_caps = self._session_state_machine.capabilities
        new_scene = self._load_service.create_scene_for_load(
            model=model,
            node_library=self.node_library,
            edit_session_capabilities=edit_caps,
            base_scene_extra_options=self._scene_extra_options,
            scene_extra_options_override=scene_extra_options_override,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )
        self._load_service.attach_scene_to_view_for_load(
            scene=new_scene,
            view=self.view,
            node_library=self.node_library,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = model
        self.scene = new_scene

        # 会话能力同步到 view/scene（含 read_only 与“添加节点”入口）
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 分帧装配图元：关闭 viewport 更新 + 关闭回调 + NoIndex
        viewport = self.view.viewport()
        prev_viewport_updates = bool(viewport.updatesEnabled())
        old_on_change_cb = new_scene.undo_manager.on_change_callback
        old_on_data_changed = new_scene.on_data_changed

        viewport.setUpdatesEnabled(False)
        new_scene.undo_manager.on_change_callback = None
        new_scene.on_data_changed = None
        new_scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)

        self._async_batch_build_context = {
            "graph_id": graph_id,
            "container": container,
            "baseline_hash": baseline_hash,
            "prev_viewport_updates": prev_viewport_updates,
            "old_on_change_cb": old_on_change_cb,
            "old_on_data_changed": old_on_data_changed,
        }

        job = IncrementalScenePopulateJob(
            new_scene,
            enable_batch_mode=True,
            time_budget_ms=10,
            parent=self,
        )
        self._async_populate_job = job

        total = int(job.nodes_total + job.edges_total)
        if self.view is not None and hasattr(self.view, "update_loading_overlay_progress"):
            self.view.update_loading_overlay_progress(progress_value=0, progress_max=total if total > 0 else None)
            self.view.update_loading_overlay_detail("装配图元…")

        def _on_progress(nodes_done: int, nodes_total: int, edges_done: int, edges_total: int) -> None:
            if int(generation) != int(getattr(self, "_async_load_generation", 0)):
                return
            # 分帧装配除了节点/连线，还包含“批量装配收尾”的延迟端口重排（flush_deferred_port_layouts）。
            # 该阶段若不纳入进度条，会出现 100% 卡住但仍在忙的错觉（尤其是超大图）。
            flush_done = int(getattr(job, "flush_done", 0) or 0)
            flush_total = int(getattr(job, "flush_total", 0) or 0)

            done = int(nodes_done) + int(edges_done) + int(flush_done)
            all_total = int(nodes_total) + int(edges_total) + int(flush_total)
            if self.view is not None and hasattr(self.view, "update_loading_overlay_progress"):
                self.view.update_loading_overlay_progress(
                    progress_value=done,
                    progress_max=all_total if all_total > 0 else None,
                )
                phase = str(getattr(job, "phase", "") or "")
                if phase == "flush_ports":
                    self.view.update_loading_overlay_detail(
                        f"整理端口布局… {int(flush_done)}/{int(flush_total)}"
                    )
                elif phase in {"finalize", "finished"}:
                    self.view.update_loading_overlay_detail("收尾中…")
                else:
                    self.view.update_loading_overlay_detail(
                        f"节点 {int(nodes_done)}/{int(nodes_total)}  连线 {int(edges_done)}/{int(edges_total)}"
                    )

        def _on_finished() -> None:
            self._on_non_blocking_populate_finished(generation=generation)

        job.progress.connect(_on_progress)
        job.finished.connect(_on_finished)
        job.start()

    def _on_non_blocking_populate_finished(self, *, generation: int) -> None:
        if int(generation) != int(getattr(self, "_async_load_generation", 0)):
            return

        ctx = getattr(self, "_async_batch_build_context", None)
        if not isinstance(ctx, dict):
            raise RuntimeError("非阻塞加载：缺少 batch_build_context")

        graph_id = str(ctx.get("graph_id") or "")
        container = ctx.get("container")
        baseline_hash = str(ctx.get("baseline_hash") or "")
        prev_viewport_updates = bool(ctx.get("prev_viewport_updates", True))
        old_on_change_cb = ctx.get("old_on_change_cb", None)
        old_on_data_changed = ctx.get("old_on_data_changed", None)

        # 加载后按需同步信号节点端口（仍保持 viewport 更新关闭，避免中途重绘）
        self._load_service.sync_signals_after_load_if_needed(
            scene=self.scene,
            model=self.model,
            get_current_package=self.get_current_package,
        )

        # 恢复索引/回调/更新
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.scene.undo_manager.on_change_callback = old_on_change_cb
        self.scene.on_data_changed = old_on_data_changed

        viewport = self.view.viewport()
        viewport.setUpdatesEnabled(bool(prev_viewport_updates))
        viewport.update()
        self._load_service._refresh_mini_map_after_batch_build(view=self.view)  # noqa: SLF001

        if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
            self.view.hide_loading_overlay()

        self._async_populate_job = None
        self._async_prepare_thread = None
        self._async_batch_build_context = None

        # 收尾：状态、验证与通知信号
        self._finalize_after_graph_loaded(
            graph_id=str(graph_id),
            container=container,
            baseline_hash=str(baseline_hash),
        )

    def _load_graph_pipeline(self, load_request: GraphEditorLoadRequest) -> None:
        """统一的节点图加载管线。

        说明：
        - 公共入口 `load_graph` 与复合入口 `load_graph_for_composite` 统一走此处，减少“改一点牵一片”。
        - `scene_extra_options_override` 为“单次加载 override”，不写入控制器全局 `_scene_extra_options`。
        """
        graph_id = str(load_request.graph_id)
        container = load_request.container

        # 若此前存在非阻塞加载任务：提升 generation + 取消，避免旧任务完成后覆盖本次同步加载结果
        self._async_load_generation += 1
        self._cancel_pending_non_blocking_load()
        if self.view is not None and hasattr(self.view, "hide_loading_overlay"):
            self.view.hide_loading_overlay()

        # 运行期 GraphScene LRU 缓存：切图时优先秒切回（避免重建 QGraphicsItem）
        cached_entry: _GraphSceneCacheEntry | None = None
        current_graph_id = str(self.current_graph_id or "").strip()
        if graph_id and graph_id != current_graph_id:
            cached_entry = self._pop_scene_from_cache_if_compatible(
                graph_id=str(graph_id),
                expected_capabilities=self._session_state_machine.capabilities,
            )

        cached_source = self._cache_current_scene_as_inactive(next_graph_id=str(graph_id))
        if cached_entry is not None:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(f"[缓存][scene] 命中，秒切回: {graph_id}")
            self._restore_graph_from_scene_cache_entry(entry=cached_entry, request=load_request)
            return

        print(f"[加载] 开始加载节点图: {graph_id}")

        load_result = self._load_service.load(
            request=load_request,
            current_scene=self.scene,
            clear_current_scene=not bool(cached_source),
            view=self.view,
            node_library=self.node_library,
            edit_session_capabilities=self._session_state_machine.capabilities,
            base_scene_extra_options=self._scene_extra_options,
            get_current_package=self.get_current_package,
            main_window=self.parent(),
            on_graph_modified=self._on_graph_modified,
        )

        # 更新引用：后续行为必须基于新的 model/scene
        self.model = load_result.model
        self.scene = load_result.scene

        # 会话能力同步到 view/scene（含 read_only 与“添加节点”入口）
        self._apply_edit_session_capabilities_to_view_and_scene()

        # 收尾：状态、验证与通知信号
        self._finalize_after_graph_loaded(graph_id=load_result.graph_id, container=container, baseline_hash=load_result.baseline_content_hash)

    def _finalize_after_graph_loaded(self, *, graph_id: str, container: object | None, baseline_hash: str) -> None:
        # 更新当前图状态
        new_status = self._session_state_machine.on_graph_loaded(graph_id=str(graph_id), baseline_content_hash=str(baseline_hash))
        self.current_graph_container = container

        self.save_status_changed.emit(new_status)

        from engine.configs.settings import settings as _settings_ui
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[加载] 完成，加载了 {len(self.scene.node_items)} 个节点")

        # 加载完成后清除错误状态（如果有的话）
        self.error_tracker.clear_error(graph_id)

        # 加载完成后触发验证（需显式允许 can_validate）
        if self._session_state_machine.capabilities.can_validate and self._session_state_machine.capabilities.can_persist:
            self.validate_current_graph()

        # 发送加载完成信号
        self.graph_loaded.emit(graph_id)

        # 用户显式打开图：在“加载完成”后再应用镜头策略（避免超大图同步 fit_all/sceneRect 计算卡顿）。
        pending_graph_id = str(getattr(self, "_pending_post_load_camera_graph_id", "") or "")
        if pending_graph_id and pending_graph_id == str(graph_id or ""):
            self._pending_post_load_camera_graph_id = None
            from engine.configs.settings import settings as _settings_ui

            if bool(getattr(_settings_ui, "GRAPH_AUTO_FIT_ALL_ENABLED", False)):
                # 延迟一帧，确保视口尺寸有效
                QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))
            else:
                # 不改变缩放，仅轻量居中
                QtCore.QTimer.singleShot(
                    0,
                    lambda gid=str(graph_id): self._center_view_after_graph_loaded(gid),
                )

        # 自动排版前的“重解析+重载”：恢复视图中心/缩放（保持画面稳定）
        pending_restore = getattr(self, "_pending_view_restore_after_reparse", None)
        if (
            isinstance(pending_restore, dict)
            and str(pending_restore.get("graph_id") or "") == str(graph_id or "")
        ):
            self._pending_view_restore_after_reparse = None
            if self.view is not None:
                center = pending_restore.get("center", None)
                scale = float(pending_restore.get("scale", 1.0) or 1.0)
                if isinstance(center, (list, tuple)) and len(center) >= 2:
                    self.view.resetTransform()
                    self.view.scale(float(scale), float(scale))
                    self.view.centerOn(QtCore.QPointF(float(center[0]), float(center[1])))

        # 若本次加载来自“自动排版前重解析”，则在加载完成后自动触发一次自动排版
        pending_auto_layout_graph_id = str(
            getattr(self, "_pending_auto_layout_after_reparse_graph_id", "") or ""
        )
        if pending_auto_layout_graph_id and pending_auto_layout_graph_id == str(graph_id or ""):
            self._pending_auto_layout_after_reparse_graph_id = None
            if self.view is not None:
                from app.ui.graph.graph_view.auto_layout.auto_layout_controller import AutoLayoutController

                QtCore.QTimer.singleShot(0, lambda v=self.view: AutoLayoutController.run(v))
    
    def save_current_graph(self) -> None:
        """保存当前节点图（仅当内容变化时）
        
        统一保存入口：所有节点图保存必须通过此方法
        - 保存前：验证数据完整性
        - 保存中：序列化并生成代码
        - 保存后：验证结果并更新UI
        """
        if not self.current_graph_id:
            return
        
        # 计算当前内容哈希（不含位置信息）
        current_hash = self.model.get_content_hash()
        if not self._session_state_machine.has_unsaved_changes(current_content_hash=current_hash):
            return
        
        # 不可保存会话：不写入资源（避免“看起来能保存”），仅维持基线与只读提示。
        if not self._session_state_machine.capabilities.can_persist:
            print(f"[保存] 当前会话不可保存（不落盘），跳过写入: {self.current_graph_id}")
            new_status = self._session_state_machine.on_modified(current_content_hash=current_hash)
            self.save_status_changed.emit(new_status)
            return
        
        # 非只读：正常保存
        print(f"[保存] 检测到内容变化，开始保存: {self.current_graph_id}")
        self.save_status_changed.emit(self._session_state_machine.on_save_started())

        save_result = self._save_service.save_graph(
            resource_manager=self.resource_manager,
            graph_id=str(self.current_graph_id),
            model=self.model,
        )
        if not save_result.success:
            error_message = save_result.error_message or "节点图保存失败"
            print(f"❌ [保存] 保存被阻止: {self.current_graph_id}")
            print(f"   原因: {save_result.error_code or 'unknown_error'}")
            self.save_status_changed.emit(self._session_state_machine.on_save_failed())
            self.error_tracker.mark_error(
                self.current_graph_id,
                error_message,
                str(save_result.error_code or "save_failed"),
            )
            return

        self.save_status_changed.emit(self._session_state_machine.on_save_succeeded(new_baseline_content_hash=current_hash))
        print(f"✅ [保存] 完成: {self.current_graph_id}")
        self.error_tracker.clear_error(self.current_graph_id)
        if self._session_state_machine.capabilities.can_validate:
            self.validate_current_graph()
        self.graph_saved.emit(self.current_graph_id)
    
    def validate_current_graph(self) -> None:
        """验证当前编辑的节点图并更新UI显示"""
        if not self._session_state_machine.capabilities.can_validate:
            return
        if not self.get_current_package or not self.get_property_panel_object_type:
            return
        
        current_package = self.get_current_package()
        if not current_package or not self.current_graph_container:
            return

        # 确定实体类型（由验证服务推导）
        object_type = self.get_property_panel_object_type()

        issues = self._validate_service.validate_for_ui(
            model=self.model,
            resource_manager=self.resource_manager,
            current_package=current_package,
            current_container=self.current_graph_container,
            object_type=str(object_type or ""),
            graph_id=str(self.current_graph_id or ""),
        )

        self.scene.update_validation(issues)
        self.graph_validated.emit(issues)
    
    def add_node_at_position(self, node_def: NodeDef, scene_pos: QtCore.QPointF) -> None:
        """添加节点"""
        print(f"[添加节点] 准备添加节点: {node_def.name}")
        print(f"[添加节点] 添加前Model中有 {len(self.model.nodes)} 个节点")
        
        node_id = self.model.gen_id("node")

        # 新建节点的“初始端口策略”统一收敛到 flow service，避免控制器硬编码业务分支。
        input_names = derive_initial_input_names_for_new_node(node_def)

        cmd = AddNodeCommand(
            self.model,
            self.scene,
            node_id,
            node_def.name,
            node_def.category,
            input_names,
            node_def.outputs,
            pos=(scene_pos.x(), scene_pos.y())
        )
        self.scene.undo_manager.execute_command(cmd)
        
        print(f"[添加节点] 添加后Model中有 {len(self.model.nodes)} 个节点")
        print(f"[添加节点] Scene.model中有 {len(self.scene.model.nodes)} 个节点")

    def _on_graph_modified(self) -> None:
        """节点图被修改时的回调 - 触发自动保存"""
        current_hash = self.model.get_content_hash()
        if not self._session_state_machine.capabilities.can_persist:
            # 不落盘会话：保持“只读/不落盘”提示，并将当前快照视为基线，避免把包标记为脏。
            self.save_status_changed.emit(self._session_state_machine.on_modified(current_content_hash=current_hash))
            return

        # 可保存会话：标记为脏状态并按全局设置触发自动保存
        self.save_status_changed.emit(self._session_state_machine.on_modified(current_content_hash=current_hash))

        # 基于全局设置的自动保存防抖（单位：秒；0 表示立即保存）
        from engine.configs.settings import settings as _settings
        interval_seconds = float(getattr(_settings, "AUTO_SAVE_INTERVAL", 0.0) or 0.0)
        if interval_seconds <= 0.0:
            self.save_current_graph()
            return
        # 延迟保存：合并短时间内的频繁修改
        if self._save_debounce_timer is None:
            self._save_debounce_timer = QtCore.QTimer(self)
            self._save_debounce_timer.setSingleShot(True)
            self._save_debounce_timer.timeout.connect(self.save_current_graph)
        # 重启计时器
        self._save_debounce_timer.start(int(interval_seconds * 1000))
    
    def mark_as_dirty(self) -> None:
        """标记节点图为未保存状态"""
        if not self._session_state_machine.capabilities.can_persist:
            return
        current_hash = self.model.get_content_hash()
        self.save_status_changed.emit(self._session_state_machine.on_modified(current_content_hash=current_hash))
    
    def mark_as_saved(self) -> None:
        """标记节点图为已保存状态"""
        current_hash = self.model.get_content_hash()
        self.save_status_changed.emit(self._session_state_machine.on_save_succeeded(new_baseline_content_hash=current_hash))
    
    @property
    def is_dirty(self) -> bool:
        """判断是否有未保存的修改"""
        current_hash = self.model.get_content_hash() if self.model is not None else None
        return self._session_state_machine.has_unsaved_changes(current_content_hash=current_hash)
    
    def open_graph_for_editing(self, graph_id: str, graph_data: dict, container=None) -> None:
        """打开节点图进行编辑（从属性面板触发）"""
        print(f"[EDITOR] open_graph_for_editing: graph_id={graph_id}, container={'Y' if container else 'N'}")
        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()
        
        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()
        print("[EDITOR] 已发出 switch_to_editor_requested 信号")

        # 进入编辑器时确保能力回到“可交互 + 可校验”，避免从 TODO 预览/清缓存等路径残留只读，
        # 导致自动排版按钮被隐藏且场景仍处于只读。
        self._ensure_interactive_capabilities_for_editor()

        # 标记：本次为“用户显式打开图”，加载完成后应用镜头策略（在 _finalize_after_graph_loaded 中统一执行）
        self._pending_post_load_camera_graph_id = str(graph_id or "")

        # 加载节点图：超大图走“非阻塞”管线，避免 UI 卡死；小图保留同步加载以维持内部链路兼容性
        if self._should_use_non_blocking_load(graph_data):
            self.load_graph_non_blocking(graph_id, graph_data, container)
            print("[EDITOR] 已发起加载请求（非阻塞）")
        else:
            self.load_graph(graph_id, graph_data, container)
            print("[EDITOR] 已加载图数据到编辑视图（同步）")

    def _center_view_after_graph_loaded(self, expected_graph_id: str) -> None:
        """加载完成后将视图轻量居中到当前场景内容中心（不改变缩放）。"""
        if str(getattr(self, "current_graph_id", "") or "") != str(expected_graph_id or ""):
            return
        view = getattr(self, "view", None)
        scene = getattr(self, "scene", None)
        if view is None or scene is None:
            return
        scene_rect = scene.sceneRect() if hasattr(scene, "sceneRect") else None
        if scene_rect is None or scene_rect.isEmpty():
            return
        # 若当前缩放极小（常见于从 Todo 预览页借回共享画布后，预览侧曾执行 fit_all），
        # 则将缩放恢复到默认比例，避免“打开即压缩”的体验。
        current_scale = float(getattr(view.transform(), "m11", lambda: 1.0)())
        if current_scale < 0.12:
            view.resetTransform()
        view.centerOn(scene_rect.center())
    
    def _ensure_interactive_capabilities_for_editor(self) -> None:
        """确保编辑器会话至少处于“可交互 + 可校验”的能力集合。

        背景：
        - Todo 预览会将会话能力切到 `read_only_preview()` 以隐藏自动排版入口并禁用编辑；
        - 设置页“清除所有缓存”会关闭编辑会话并重置为只读；
        - 若随后打开节点图但能力未被恢复，右上角“自动排版”按钮会消失。
        """
        capabilities = self._session_state_machine.capabilities
        if capabilities.can_interact and capabilities.can_validate:
            return
        self.set_edit_session_capabilities(EditSessionCapabilities.interactive_preview())

    def open_independent_graph(self, graph_id: str, graph_data: dict, graph_name: str) -> None:
        """打开独立节点图（从节点图库触发）"""
        # 如目标与当前相同：直接切换到编辑器，避免重复装载
        if self.current_graph_id == graph_id:
            self.switch_to_editor_requested.emit()
            self._ensure_interactive_capabilities_for_editor()
            self.title_update_requested.emit(f"节点图: {graph_name}")
            return
        
        # 保存当前节点图
        if self.current_graph_id and self.current_graph_container:
            self.save_current_graph()
        
        # 加载节点图配置
        graph_config = GraphConfig.deserialize(graph_data)
        
        # 切换到节点图编辑页面
        self.switch_to_editor_requested.emit()

        # 进入编辑器时确保能力回到“可交互 + 可校验”，避免从只读路径残留只读导致编辑器按钮缺失。
        self._ensure_interactive_capabilities_for_editor()

        # 标记：本次为“用户显式打开图”，加载完成后应用镜头策略（在 _finalize_after_graph_loaded 中统一执行）
        self._pending_post_load_camera_graph_id = str(graph_id or "")

        # 加载节点图数据（独立节点图没有容器）
        if self._should_use_non_blocking_load(graph_config.data):
            self.load_graph_non_blocking(graph_id, graph_config.data, container=None)
        else:
            self.load_graph(graph_id, graph_config.data, container=None)
        
        # 更新窗口标题
        self.title_update_requested.emit(f"节点图: {graph_name}")
    
    def close_editor_session(self) -> None:
        """关闭当前节点图编辑会话并恢复空场景，用于清理缓存或强制返回列表。"""
        # 关闭会话属于“强制清理”：同时释放运行期 scene 缓存，避免占用大量内存
        self._clear_scene_lru_cache()
        had_graph = bool(self.current_graph_id)
        if had_graph:
            self.save_current_graph()
        if self._save_debounce_timer and self._save_debounce_timer.isActive():
            self._save_debounce_timer.stop()
        if self.scene:
            self.scene.clear()
            if hasattr(self.scene, "node_items"):
                self.scene.node_items.clear()
            if hasattr(self.scene, "edge_items"):
                self.scene.edge_items.clear()
            if hasattr(self.scene, "undo_manager") and self.scene.undo_manager:
                self.scene.undo_manager.clear()
        self.model = GraphModel()
        self.scene = GraphScene(
            self.model,
            read_only=True,
            node_library=self.node_library,
            edit_session_capabilities=EditSessionCapabilities.read_only_preview(),
        )
        self.scene.undo_manager.on_change_callback = None
        self.scene.on_data_changed = None
        if self.view is not None:
            self.view.setScene(self.scene)
            self.view.resetTransform()
            self.view.viewport().update()
        self._session_state_machine.on_graph_closed()
        self.current_graph_container = None
        self._force_reparse_on_next_auto_layout = False
        self.set_edit_session_capabilities(EditSessionCapabilities.read_only_preview())
        self.title_update_requested.emit("节点图: 未打开")
    
    def refresh_persistent_cache_after_layout(self) -> None:
        """将当前模型写入持久化缓存（用于自动排版后覆盖缓存）。
        
        位置变化不落盘，但希望下次打开时直接使用最新位置，
        因此在自动排版完成后，将当前 GraphModel 序列化并写入 app/runtime/cache/graph_cache。
        """
        if not self.current_graph_id or not self.model:
            return
        graph_id = str(self.current_graph_id)
        self.resource_manager.update_persistent_graph_cache_from_model(
            graph_id,
            self.model,
            layout_changed=True,
        )
        print(f"[缓存] 已刷新持久化缓存（自动排版后）: {graph_id}")

        # 通知主窗口统一失效 GraphDataService / 图属性面板等上层缓存，避免“显示不一致/回退”。
        self.graph_runtime_cache_updated.emit(graph_id)
        # 自动排版完成后默认不强制改变镜头；
        # 若用户显式开启“自动适配全图（压缩视图）”，则恢复旧行为。
        from engine.configs.settings import settings as _settings_ui
        if bool(getattr(_settings_ui, "GRAPH_AUTO_FIT_ALL_ENABLED", False)) and self.view is not None:
            QtCore.QTimer.singleShot(100, lambda: self.view and self.view.fit_all(use_animation=False))

    def get_current_model(self) -> GraphModel:
        """获取当前模型"""
        return self.model
    
    def get_current_scene(self) -> GraphScene:
        """获取当前场景"""
        return self.scene

    def set_scene_extra_options(self, options: dict) -> None:
        """设置场景额外参数（例如复合节点编辑上下文）
        
        Args:
            options: 传入 GraphScene 的关键字参数字典
        """
        self._scene_extra_options = options or {}

