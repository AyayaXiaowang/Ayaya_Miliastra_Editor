"""节点图编辑控制器 - 管理节点图的编辑逻辑

治理约束（重要）：
- 本文件仅负责：依赖注入、Qt 信号转发、调用流程服务；
- 跨域链路（load/save/validate/auto_layout_prepare）下沉到 `app.ui.controllers.graph_editor_flow`；
- 会话能力/只读语义/保存状态统一由状态机收敛为单一真源，避免分叉。

实现拆分（避免单文件过大）：
- 具体实现按职责拆分到 `app.ui.controllers.graph_editor_parts` 下的 mixin；
- `GraphEditorController` 作为组合根：保留信号 + `__init__`（字段初始化/依赖注入）。
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from PyQt6 import QtCore

from engine.graph.models.graph_model import GraphModel
from engine.resources.resource_manager import ResourceManager
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.controllers.graph_error_tracker import get_instance as get_error_tracker
from app.ui.controllers.graph_editor_flow import (
    GraphAutoLayoutReparseThread,
    GraphEditorAutoLayoutPrepareService,
    GraphEditorLoadService,
    GraphEditorSaveService,
    GraphEditorSessionStateMachine,
    GraphEditorValidateService,
    GraphPrepareThread,
)
from app.ui.controllers.graph_editor_parts.auto_layout_mixin import GraphEditorAutoLayoutMixin
from app.ui.controllers.graph_editor_parts.capabilities_mixin import GraphEditorCapabilitiesMixin
from app.ui.controllers.graph_editor_parts.load_pipeline_mixin import GraphEditorLoadPipelineMixin
from app.ui.controllers.graph_editor_parts.open_session_mixin import GraphEditorOpenSessionMixin
from app.ui.controllers.graph_editor_parts.save_validate_mixin import GraphEditorSaveValidateMixin
from app.ui.controllers.graph_editor_parts.scene_cache_mixin import (
    _GraphSceneCacheEntry,
    GraphEditorSceneCacheMixin,
)
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.graph.scene_builder import IncrementalScenePopulateJob


class GraphEditorController(
    GraphEditorCapabilitiesMixin,
    GraphEditorSceneCacheMixin,
    GraphEditorAutoLayoutMixin,
    GraphEditorLoadPipelineMixin,
    GraphEditorSaveValidateMixin,
    GraphEditorOpenSessionMixin,
    QtCore.QObject,
):
    """节点图编辑管理控制器（组合根）。"""

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
        parent: Optional[QtCore.QObject] = None,
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
        self._session_state_machine = GraphEditorSessionStateMachine(
            capabilities=initial_capabilities
        )

        # 用于获取存档（由主窗口设置）
        self.get_current_package = None
        self.get_property_panel_object_type = None

        # 错误跟踪器（单例）
        self.error_tracker = get_error_tracker()
        # 自动保存防抖计时器（根据全局设置控制）
        self._save_debounce_timer: Optional[QtCore.QTimer] = None
        # 下次自动排版前是否强制从 .py 重新解析（忽略持久化缓存）
        self._force_reparse_on_next_auto_layout: bool = False
        # 自动排版前重解析线程 generation（用于丢弃旧任务回调）
        self._auto_layout_reparse_generation: int = 0
        self._auto_layout_reparse_thread: GraphAutoLayoutReparseThread | None = None
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

