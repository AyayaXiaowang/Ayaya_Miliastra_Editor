from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from app.ui.foundation.theme_manager import Colors
from app.ui.graph.items.node_item import NodeGraphicsItem
from app.ui.graph.virtual_pin_ui_service import cleanup_virtual_pins_for_deleted_node as cleanup_virtual_pins_for_deleted_node_ui
from app.ui.graph.signal_node_service import (
    get_effective_node_def_for_scene as get_effective_signal_node_def_for_scene,
    on_signals_updated_from_manager as on_signals_updated_from_manager_service,
    prepare_node_model_for_scene as prepare_signal_node_model_for_scene,
)
from app.ui.graph.struct_node_service import (
    get_effective_node_def_for_scene as get_effective_struct_node_def_for_scene,
    prepare_node_model_for_scene as prepare_struct_node_model_for_scene,
)
from app.ui.overlays.scene_overlay import SceneOverlayMixin
from app.ui.scene.interaction_mixin import SceneInteractionMixin
from app.ui.scene.model_ops_mixin import SceneModelOpsMixin
from app.ui.scene.view_context_menu_mixin import SceneViewContextMenuMixin
from app.ui.scene.ydebug_interaction_mixin import YDebugInteractionMixin
from typing import Optional, List, Dict, TYPE_CHECKING, Iterable
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.ui.graph.graph_undo import UndoRedoManager
from engine.layout import UI_ROW_HEIGHT  # unified row height metric
from engine.layout import LayoutService
from engine.configs.settings import settings as _settings_ui
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.runtime.services.graph_scene_policy import (
    compute_blocks_only_overview_mode,
    compute_enable_batched_edge_layer,
    compute_fast_preview_auto_eligible,
    compute_lod_edges_culled_mode,
    compute_lod_ports_hidden_mode,
    compute_should_skip_ports_sync_on_scale_change,
    is_blocks_only_overview_supported,
)

if TYPE_CHECKING:
    from app.ui.dynamic_port_widget import AddPortButton
    from app.ui.graph.items.edge_item import EdgeGraphicsItem
    from app.ui.graph.items.port_item import PortGraphicsItem
NODE_PADDING = 10
ROW_HEIGHT = UI_ROW_HEIGHT
# 为多分支节点的"+"按钮额外预留一行高度，提升可点击与视觉间距
BRANCH_PLUS_EXTRA_ROWS = 1


class GraphScene(
    SceneOverlayMixin,
    SceneViewContextMenuMixin,
    SceneInteractionMixin,
    SceneModelOpsMixin,
    YDebugInteractionMixin,
    QtWidgets.QGraphicsScene,
):
    def __init__(
        self,
        model: GraphModel,
        read_only: bool = False,
        node_library: Dict = None,
        composite_edit_context: Dict = None,
        signal_edit_context: Dict = None,
        *,
        edit_session_capabilities: EditSessionCapabilities | None = None,
        allow_node_drag_in_read_only: bool = False,
    ):
        super().__init__()
        if edit_session_capabilities is not None:
            expected_read_only = bool(edit_session_capabilities.is_read_only)
            if bool(read_only) != expected_read_only:
                raise ValueError(
                    "GraphScene 初始化参数冲突：read_only 与 edit_session_capabilities.can_interact 不一致；"
                    f"read_only={read_only}, can_interact={edit_session_capabilities.can_interact}"
                )
            effective_capabilities = edit_session_capabilities
        else:
            # 兼容旧调用：仅提供 read_only 时，映射为默认能力组合。
            effective_capabilities = (
                EditSessionCapabilities.read_only_preview()
                if bool(read_only)
                else EditSessionCapabilities.interactive_preview()
            )

        self.model = model
        # 只读预览默认禁止拖拽节点；某些页面（例如复合节点库预览）希望“只读但可拖拽”以便查看。
        self._allow_node_drag_in_read_only: bool = bool(allow_node_drag_in_read_only)
        # ===== 快速预览模式（大图性能优化）=====
        #
        # 适用场景：
        # - 当前会话不可落盘（can_persist=False），即 UI 的修改不会写回 .py 源文件；
        # - 图规模过大（节点/连线数量超过阈值）时，完整 NodeGraphicsItem（端口+常量控件）创建成本很高。
        #
        # 行为：
        # - 使用轻量 Node/Edge 图元（不创建端口与行内常量编辑控件），显著降低打开与渲染成本；
        # - 仍保留节点选择/跳转等能力，供“预览与定位”使用。
        node_count = len(getattr(model, "nodes", {}) or {})
        edge_count = len(getattr(model, "edges", {}) or {})
        fast_preview_enabled = bool(getattr(_settings_ui, "GRAPH_FAST_PREVIEW_ENABLED", True))
        fast_preview_node_threshold = int(getattr(_settings_ui, "GRAPH_FAST_PREVIEW_NODE_THRESHOLD", 500))
        fast_preview_edge_threshold = int(getattr(_settings_ui, "GRAPH_FAST_PREVIEW_EDGE_THRESHOLD", 900))
        self.fast_preview_auto_eligible: bool = compute_fast_preview_auto_eligible(
            fast_preview_enabled=fast_preview_enabled,
            can_persist=bool(effective_capabilities.can_persist),
            node_count=node_count,
            edge_count=edge_count,
            node_threshold=fast_preview_node_threshold,
            edge_threshold=fast_preview_edge_threshold,
        )
        self.fast_preview_mode = bool(self.fast_preview_auto_eligible)
        # ===== 批量连线渲染层（进一步降低超大图边图元数量）=====
        #
        # 说明：
        # - fast_preview_mode 下启用：批量渲染“轻量预览边”（原 FastPreviewEdgeGraphicsItem）；
        # - 只读大图（非 fast_preview）也可启用：节点仍保留为 item，但边不再逐条创建 QGraphicsItem，
        #   用于任务清单预览等“只读联动”场景显著降本（点击/高亮/灰显改走模型级命中与批量状态）；
        # - 仅批量渲染“轻量预览边”（原 FastPreviewEdgeGraphicsItem），节点级展开时仍可将局部边 materialize
        #   为 EdgeGraphicsItem 以便看清端口连接；
        # - SHOW_LAYOUT_Y_DEBUG 下默认关闭：链路高亮调试依赖逐边图元，调试场景优先保持语义一致。
        self._batched_fast_preview_edge_layer = None
        batched_edges_enabled = bool(getattr(_settings_ui, "GRAPH_FAST_PREVIEW_BATCHED_EDGES_ENABLED", True))
        read_only_batched_enabled = bool(getattr(_settings_ui, "GRAPH_READONLY_BATCHED_EDGES_ENABLED", True))
        read_only_batched_edge_threshold = int(
            getattr(_settings_ui, "GRAPH_READONLY_BATCHED_EDGES_EDGE_THRESHOLD", 900) or 900
        )
        enable_batched_layer = compute_enable_batched_edge_layer(
            fast_preview_mode=bool(self.fast_preview_mode),
            batched_edges_enabled=bool(batched_edges_enabled),
            read_only_batched_enabled=bool(read_only_batched_enabled),
            is_read_only=bool(effective_capabilities.is_read_only),
            edge_count=edge_count,
            read_only_edge_threshold=read_only_batched_edge_threshold,
            force_disable=bool(getattr(_settings_ui, "SHOW_LAYOUT_Y_DEBUG", False)),
        )

        if enable_batched_layer:
            from app.ui.graph.items.batched_edge_layer import BatchedFastPreviewEdgeLayer

            layer = BatchedFastPreviewEdgeLayer()
            self.addItem(layer)
            self._batched_fast_preview_edge_layer = layer
        # 快速预览下的“节点级展开”：
        # - 允许多个节点同时展开；
        # - 选中节点会自动展开（框选多选则全部展开）；
        # - 不会因为取消选中而自动收起，仅允许用户手动点击按钮收起。
        self._fast_preview_last_selected_node_ids: set[str] = set()
        self._fast_preview_auto_expand_guard: bool = False
        # 自动展开防抖：避免“拖拽节点/快速多选”期间频繁重建端口与相邻连线。
        self._fast_preview_auto_expand_pending_node_ids: set[str] = set()
        self._fast_preview_auto_expand_timer: QtCore.QTimer | None = None
        self._fast_preview_auto_expand_debounce_ms: int = 120
        # 批量构建标志：加载大图时由控制器临时开启，避免每次 add_node_item 都全局重算场景矩形与小地图
        self.is_bulk_adding_items: bool = False
        # 批量构建期间的端口重排延迟队列：
        # - add_edge_item 在连接建立后通常会触发目标节点 _layout_ports() 用于隐藏“已连线输入端口”的常量输入框；
        # - 在批量装配大图时，逐边重排会导致 O(E) 次端口重算，成为主要卡顿来源；
        # - 因此在 is_bulk_adding_items=True 时先记录需要刷新端口的节点，批量结束后统一 flush。
        self._deferred_port_layout_node_ids: set[str] = set()
        self.node_library = node_library or {}  # 节点定义库（用于获取显式类型）
        # 布局层的“节点注册表派生信息”只读上下文：
        # 用于端口行规划/高度估算与布局层保持同一真源，避免 graph_query_utils 使用隐式 workspace_root。
        from engine.layout.internal.layout_registry_context import LayoutRegistryContext
        self.layout_registry_context = LayoutRegistryContext.from_settings()
        self.node_items: dict[str, NodeGraphicsItem] = {}
        self.edge_items: dict[str, EdgeGraphicsItem] = {}
        # 邻接索引: 记录每个节点关联的连线图形项，避免在拖动节点或移动命令中遍历全图
        # 键为节点 ID，值为包含 EdgeGraphicsItem 的集合
        self._edges_by_node_id: dict[str, set[EdgeGraphicsItem]] = {}
        self.temp_connection_start: Optional[PortGraphicsItem] = None
        self.temp_connection_line: Optional[QtWidgets.QGraphicsLineItem] = None
        self.undo_manager = UndoRedoManager()
        self.node_move_tracking: dict[str, tuple[float, float]] = {}  # 记录节点移动前的位置
        # 记录最近添加的节点，供自动连接在找不到显式 new_node_id 时回退使用
        self.last_added_node_id: Optional[str] = None
        # 用于拖拽数据线后弹出节点菜单时的自动连接
        self.pending_connection_port: Optional[PortGraphicsItem] = None
        self.pending_connection_scene_pos: Optional[QtCore.QPointF] = None
        # 保存待连接的节点和端口信息（使用ID而不是引用）
        self.pending_src_node_id: Optional[str] = None
        # 数据变更回调（用于自动保存）
        self.on_data_changed = None
        self.pending_src_port_name: Optional[str] = None
        self.pending_is_src_output: bool = False
        self.pending_is_src_flow: bool = False
        # 复制粘贴相关
        self.clipboard_nodes: list[dict] = []  # 复制的节点数据
        self.clipboard_edges: list[dict] = []  # 复制的连线数据
        self.last_mouse_scene_pos: Optional[QtCore.QPointF] = None  # 记录最后的鼠标位置
        self._edit_session_capabilities: EditSessionCapabilities = effective_capabilities
        self._read_only: bool = bool(effective_capabilities.is_read_only)
        # 使用主题深色背景，统一节点画布观感
        self.setBackgroundBrush(QtGui.QColor(Colors.BG_DARK))
        # 视图缩放提示（由 GraphView 在绘制阶段同步）：
        # 用于低倍率 LOD（端口/连线命中测试）等“无 option 的路径”（例如 Edge.shape）。
        self.view_scale_hint: float = 1.0
        # 视图交互状态：画布平移/缩放期间用于临时降级叠层与端口可见性，减少重绘开销。
        # 该状态由 GraphViewInteractionController 在交互开始/结束时显式同步。
        #
        # 说明：
        # - `_view_panning` 作为“视图交互中”的兼容标记，供叠加层快速判断是否进入低细节模式；
        # - 内部按来源拆分为“拖拽平移/滚轮缩放”两类，避免并发交互时互相覆盖恢复逻辑。
        self._view_panning: bool = False
        self._view_pan_dragging: bool = False
        self._view_wheel_zooming: bool = False
        # 块鸟瞰模式（极低倍率）：仅显示 basic blocks 背景色，隐藏节点/连线图元。
        # 说明：该模式会在视图缩放提示更新时自动切换，避免在缩到很小时仍遍历/绘制大量图元导致卡顿。
        self._blocks_only_overview_mode: bool = False
        # LOD：端口/连线可见性“真隐藏”（setVisible(False)），用于避免在 paint/shape 虽然早退
        # 但仍需被 Qt 枚举调用导致的超大图卡顿。
        self._lod_ports_hidden_mode: bool = False
        self._lod_edges_culled_mode: bool = False
        # 边裁剪模式下的“当前可见边集合”（按 edge_id 记录），用于在 selectionChanged 时做差量更新。
        self._lod_culled_visible_edge_ids: set[str] = set()
        
        # 网格设置
        self.grid_size = 50  # 网格大小
        
        # 验证结果缓存（从验证系统获取）
        self.validation_issues: dict[str, List] = {}  # {node_id: [ValidationIssue, ...]}
        
        # 复合节点编辑上下文（仅在复合节点编辑器中使用）
        self.composite_edit_context = composite_edit_context or {}
        self.is_composite_editor = bool(composite_edit_context)

        # 信号编辑上下文（节点图编辑器中使用）：
        # 约定字段：
        # - get_current_package: Callable[[], PackageView | None]
        # - main_window: QMainWindow（可选，用于对话框父窗口）
        self.signal_edit_context = signal_edit_context or {}
        
        # 当启用基本块可视化且当前模型未包含基本块时：
        # 使用引擎的纯计算布局服务获取 basic_blocks（不改动当前模型的节点位置）
        from engine.configs.settings import settings as _settings
        if (
            (not self.fast_preview_mode)
            and _settings.SHOW_BASIC_BLOCKS
            and (not getattr(self.model, "basic_blocks", None))
        ):
            node_lib = self.node_library if isinstance(self.node_library, dict) else None
            _result = LayoutService.compute_layout(
                self.model,
                node_library=node_lib,
                include_augmented_model=False,
                workspace_path=getattr(self.layout_registry_context, "workspace_path", None),
            )
            self.model.basic_blocks = _result.basic_blocks

        # 布局 Y 调试：
        # - SHOW_LAYOUT_Y_DEBUG 启用后，overlay 会依赖 GraphModel 上的 `_layout_y_debug_info` 绘制图标与 tooltip；
        # - 该调试信息应在加载/重建阶段一次性生成，禁止在 drawForeground 等绘制路径内“临时补算布局”。
        if bool(getattr(_settings, "SHOW_LAYOUT_Y_DEBUG", False)):
            debug_map = getattr(self.model, "_layout_y_debug_info", None)
            if debug_map is None:
                node_lib = self.node_library if isinstance(self.node_library, dict) else None
                LayoutService.compute_layout(
                    self.model,
                    node_library=node_lib,
                    include_augmented_model=False,
                    registry_context=self.layout_registry_context,
                )

        # 自动展开：监听 selectionChanged（仅 fast_preview_mode 生效）
        self.selectionChanged.connect(self._on_selection_changed_fast_preview_auto_expand)
        # 选择变化：在“边裁剪模式”下刷新边可见性（程序性选中/高亮也会触发 selectionChanged）
        self.selectionChanged.connect(self._on_selection_changed_sync_lod_visibility)

    def set_view_scale_hint(self, scale: float) -> None:
        """由视图同步当前缩放比例（1.0=100%）。"""
        self.view_scale_hint = float(scale or 1.0)
        self._sync_blocks_only_overview_mode()
        # panning 期间若启用“隐藏图标”，端口可见性由 set_view_panning() 接管，
        # 避免缩放变化触发 LOD 切换把端口又显示出来。
        skip_ports_sync = compute_should_skip_ports_sync_on_scale_change(
            is_view_panning=bool(getattr(self, "_view_panning", False)),
            pan_hide_icons_enabled=bool(getattr(_settings_ui, "GRAPH_PAN_HIDE_ICONS_ENABLED", True)),
        )
        if not skip_ports_sync:
            self._sync_ports_hidden_mode()
        self._sync_edges_culled_mode()

    def set_view_panning(self, is_panning: bool) -> None:
        """由视图交互控制器同步“是否正在拖拽平移（panning）”状态。"""
        new_state = bool(is_panning)
        if bool(getattr(self, "_view_pan_dragging", False)) == new_state:
            return
        self._view_pan_dragging = new_state
        self._sync_view_interaction_panning_flag()

    def set_view_zooming(self, is_zooming: bool) -> None:
        """由视图交互控制器同步“是否正在滚轮缩放（zooming）”状态。"""
        new_state = bool(is_zooming)
        if bool(getattr(self, "_view_wheel_zooming", False)) == new_state:
            return
        self._view_wheel_zooming = new_state
        self._sync_view_interaction_panning_flag()

    def _sync_view_interaction_panning_flag(self) -> None:
        """根据平移/缩放状态同步 `_view_panning` 与低细节降级逻辑。"""
        new_state = bool(getattr(self, "_view_pan_dragging", False)) or bool(
            getattr(self, "_view_wheel_zooming", False)
        )
        if bool(getattr(self, "_view_panning", False)) == new_state:
            return
        self._view_panning = new_state

        if new_state:
            if bool(getattr(_settings_ui, "GRAPH_PAN_HIDE_ICONS_ENABLED", True)):
                # 端口真隐藏：端口圆点/⚙按钮/+按钮等统一 setVisible(False)，并让节点主体启用设备坐标缓存。
                self._apply_ports_hidden_visibility_to_all_nodes(should_show_ports=False)
                # YDebug：清空命中映射，避免在图标不可见时仍可点击命中（也避免使用上一帧陈旧 rect）。
                if hasattr(self, "_ydebug_icon_rects"):
                    self._ydebug_icon_rects.clear()
            self.update()
            return

        # 交互结束：按当前缩放的 LOD 状态恢复端口可见性。
        # 注意：交互期间我们暂停了 _sync_ports_hidden_mode；这里需要补齐一次同步。
        self._sync_ports_hidden_mode()
        if not self.blocks_only_overview_mode:
            self._apply_ports_hidden_visibility_to_all_nodes(
                should_show_ports=not bool(self.lod_ports_hidden_mode)
            )
        self.update()

    def drawItems(self, painter: QtGui.QPainter, numItems: int, items, options, widget=None) -> None:  # noqa: N802, ANN001
        """场景绘制项入口（用于性能面板的 item 级分解）。

        说明：
        - 当画布性能面板启用时，GraphView 会将 `GraphPerfMonitor` 挂载到 `GraphScene._perf_monitor`；
        - 这里仅记录 drawItems 的总耗时与本次调用绘制的 item 数量，不做类型遍历（类型分布由各 item 的 paint 自行计数）。
        """
        monitor = getattr(self, "_perf_monitor", None)
        if monitor is None:
            super().drawItems(painter, numItems, items, options, widget)
            return

        t0 = time.perf_counter_ns()
        inc = getattr(monitor, "inc", None)
        if callable(inc):
            inc("scene.drawItems.calls", 1)
            try_items = int(numItems) if isinstance(numItems, int) else 0
            if try_items <= 0 and hasattr(items, "__len__"):
                try_items = int(len(items))  # type: ignore[arg-type]
            if try_items > 0:
                inc("scene.drawItems.items", int(try_items))

        super().drawItems(painter, numItems, items, options, widget)

        dt_ns = int(time.perf_counter_ns() - int(t0))
        accum = getattr(monitor, "accum_ns", None)
        if callable(accum):
            accum("scene.drawItems.total", dt_ns)

    @property
    def blocks_only_overview_mode(self) -> bool:
        """是否处于“仅显示块颜色”的鸟瞰模式。"""
        return bool(getattr(self, "_blocks_only_overview_mode", False))

    @property
    def lod_ports_hidden_mode(self) -> bool:
        """是否处于“端口真隐藏”模式（端口图元 setVisible(False)）。"""
        return bool(getattr(self, "_lod_ports_hidden_mode", False))

    @property
    def lod_edges_culled_mode(self) -> bool:
        """是否处于“边裁剪”模式（非选中边 setVisible(False)）。"""
        return bool(getattr(self, "_lod_edges_culled_mode", False))

    def _is_blocks_only_overview_supported(self) -> bool:
        """是否允许进入“仅显示块颜色”的鸟瞰模式。

        约束：
        - 需要 basic_blocks 数据，否则进入后会出现“画布空白”；
        - 该模式属于 LOD 能力的一部分，可通过 settings 开关关闭。
        """
        return is_blocks_only_overview_supported(
            graph_block_overview_enabled=bool(getattr(_settings_ui, "GRAPH_BLOCK_OVERVIEW_ENABLED", True)),
            graph_lod_enabled=bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True)),
            basic_blocks=getattr(getattr(self, "model", None), "basic_blocks", None),
        )

    def _sync_blocks_only_overview_mode(self) -> None:
        """根据当前缩放比例自动切换“仅显示块颜色”的鸟瞰模式（带回滞，避免临界抖动）。"""
        supported = bool(self._is_blocks_only_overview_supported())
        scale_hint = float(getattr(self, "view_scale_hint", 1.0) or 1.0)
        new_state = compute_blocks_only_overview_mode(
            supported=supported,
            prev_enabled=bool(self.blocks_only_overview_mode),
            scale_hint=scale_hint,
            enter_scale_value=getattr(_settings_ui, "GRAPH_BLOCK_OVERVIEW_ENTER_SCALE", 0.10),
            exit_scale_value=getattr(_settings_ui, "GRAPH_BLOCK_OVERVIEW_EXIT_SCALE", None),
        )
        if bool(self.blocks_only_overview_mode) != bool(new_state):
            self._set_blocks_only_overview_mode(bool(new_state))

    def _set_blocks_only_overview_mode(self, enabled: bool) -> None:
        """切换鸟瞰模式：隐藏/恢复节点与连线图元。"""
        new_state = bool(enabled)
        if self.blocks_only_overview_mode == new_state:
            return

        self._blocks_only_overview_mode = new_state
        should_show_items = not bool(new_state)

        # 节点/连线：统一切换可见性。隐藏节点时其子项（端口/常量控件/按钮等）会自动随之隐藏。
        for node_item in (self.node_items or {}).values():
            if node_item is not None:
                node_item.setVisible(should_show_items)
        for edge_item in (self.edge_items or {}).values():
            if edge_item is not None:
                edge_item.setVisible(should_show_items)
        batched_layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        if batched_layer is not None:
            batched_layer.setVisible(should_show_items)

        # 临时连线预览（拖拽端口时）也需隐藏，避免鸟瞰视角出现孤立直线。
        temp_line = getattr(self, "temp_connection_line", None)
        if isinstance(temp_line, QtWidgets.QGraphicsLineItem):
            temp_line.setVisible(should_show_items)

        # 退出鸟瞰模式后：需要重新应用当前 LOD 的“真隐藏”状态，否则可能出现
        # blocks-only 切换把边/端口恢复可见，但 LOD 模式状态未变化而不再触发同步的问题。
        if should_show_items:
            if self.lod_ports_hidden_mode:
                self._apply_ports_hidden_visibility_to_all_nodes(should_show_ports=False)
            if self.lod_edges_culled_mode:
                self._apply_edges_culled_visibility_to_all_edges()

        # 请求刷新：背景层会继续绘制 basic blocks（SceneOverlayMixin），从而形成“只看块颜色”的鸟瞰效果。
        self.update()

    def _sync_ports_hidden_mode(self) -> None:
        """当缩放低于端口阈值时，将端口图元 setVisible(False) 以降低超大图枚举成本。"""
        lod_enabled = bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True))
        scale_hint = float(getattr(self, "view_scale_hint", 1.0) or 1.0)
        new_state = compute_lod_ports_hidden_mode(
            lod_enabled=lod_enabled,
            prev_enabled=bool(self.lod_ports_hidden_mode),
            scale_hint=scale_hint,
            enter_scale_value=getattr(_settings_ui, "GRAPH_LOD_PORT_MIN_SCALE", 0.30),
            exit_scale_value=getattr(_settings_ui, "GRAPH_LOD_PORT_VISIBILITY_EXIT_SCALE", None),
        )
        if bool(self.lod_ports_hidden_mode) != bool(new_state):
            self._set_ports_hidden_mode(bool(new_state))

    def _set_ports_hidden_mode(self, enabled: bool) -> None:
        new_state = bool(enabled)
        if self.lod_ports_hidden_mode == new_state:
            return
        self._lod_ports_hidden_mode = new_state
        self._apply_ports_hidden_visibility_to_all_nodes(should_show_ports=not bool(new_state))
        self.update()

    def _apply_ports_hidden_visibility_to_all_nodes(self, *, should_show_ports: bool) -> None:
        """根据 should_show_ports 统一切换端口/端口按钮可见性。"""
        for node_item in (self.node_items or {}).values():
            if node_item is None:
                continue
            self._apply_ports_hidden_visibility_to_node_item(node_item, should_show_ports=bool(should_show_ports))

        # 临时连线预览：端口隐藏时也一并隐藏，避免出现“线悬空”的视觉错觉。
        temp_line = getattr(self, "temp_connection_line", None)
        if isinstance(temp_line, QtWidgets.QGraphicsLineItem):
            temp_line.setVisible(bool(should_show_ports))

    def _apply_ports_hidden_visibility_to_node_item(self, node_item: object, *, should_show_ports: bool) -> None:
        """对单个节点项应用端口/端口按钮可见性（用于新增节点或节点重布局后补齐）。"""
        if node_item is None:
            return
        # 仅隐藏端口图元本身；端口标签/常量/验证图标等由 NodeGraphicsItem 的 LOD 自己控制。
        iter_ports = getattr(node_item, "iter_all_ports", None)
        if callable(iter_ports):
            for port_item in list(iter_ports() or []):
                if port_item is not None:
                    port_item.setVisible(bool(should_show_ports))
        # 端口旁边的“⚙查看类型”按钮：在低倍率下本就不绘制，显式隐藏可避免被 Qt 枚举调用。
        buttons = getattr(node_item, "_port_settings_buttons", None)
        if isinstance(buttons, list):
            for btn_item in list(buttons or []):
                if btn_item is not None:
                    btn_item.setVisible(bool(should_show_ports))
        # 变参/多分支“+”按钮：低倍率下不需要交互，显式隐藏避免额外绘制。
        add_btn = getattr(node_item, "_add_port_button", None)
        if add_btn is not None:
            add_btn.setVisible(bool(should_show_ports))

        # 低倍率平移优化：节点主体启用设备坐标缓存，避免在拖动画布时反复重绘（仅普通节点图元）。
        # 快速预览节点自身已管理 cache mode（折叠态 DeviceCoordinateCache / 展开态 NoCache），这里不强行覆盖。
        if not hasattr(node_item, "_preview_detail_expanded"):
            set_cache_mode = getattr(node_item, "setCacheMode", None)
            if callable(set_cache_mode):
                set_cache_mode(
                    QtWidgets.QGraphicsItem.CacheMode.NoCache
                    if bool(should_show_ports)
                    else QtWidgets.QGraphicsItem.CacheMode.DeviceCoordinateCache
                )

    def on_node_item_position_change_started(
        self,
        node_item: NodeGraphicsItem,
        old_pos: tuple[float, float],
    ) -> None:
        super().on_node_item_position_change_started(node_item, old_pos)

    def on_node_item_position_changed(
        self,
        node_item: NodeGraphicsItem,
        new_pos: tuple[float, float],
    ) -> None:
        super().on_node_item_position_changed(node_item, new_pos)
        # basic block 背景矩形：若缓存已建立，增量扩张以覆盖拖拽中的节点（模型 pos 在释放前不会更新）。
        node = getattr(node_item, "node", None)
        node_id = str(getattr(node, "id", "") or "")
        if node_id:
            note_moved = getattr(self, "note_basic_block_node_moved", None)
            if callable(note_moved):
                note_moved(node_id, new_pos)

    def _finalize_node_move_commands(self) -> None:
        """鼠标释放时的节点移动收尾：除了 MoveNodeCommand，还要让 basic blocks 背景收敛更新。"""
        moved_node_ids: list[str] = []
        tracking = getattr(self, "node_move_tracking", None)
        if isinstance(tracking, dict) and tracking:
            for node_id, old_pos in list(tracking.items()):
                node_id_text = str(node_id or "").strip()
                if not node_id_text:
                    continue
                node_item = (self.node_items or {}).get(node_id_text)
                if node_item is None:
                    continue
                new_pos = node_item.pos()
                new_pos_tuple = (float(new_pos.x()), float(new_pos.y()))
                if tuple(old_pos) != new_pos_tuple:
                    moved_node_ids.append(node_id_text)

        super()._finalize_node_move_commands()

        # 移动结束后可能需要收缩/重新包围，因此标记相关块 dirty，让下次背景绘制重算矩形。
        if moved_node_ids:
            mark_dirty = getattr(self, "mark_basic_block_rect_dirty_for_node", None)
            if callable(mark_dirty):
                for node_id_text in moved_node_ids:
                    mark_dirty(node_id_text)
            self.update()

    def _sync_edges_culled_mode(self) -> None:
        """当缩放低于连线阈值时，将“不会被绘制”的边直接 setVisible(False)。"""
        lod_enabled = bool(getattr(_settings_ui, "GRAPH_LOD_ENABLED", True))
        scale_hint = float(getattr(self, "view_scale_hint", 1.0) or 1.0)
        new_state = compute_lod_edges_culled_mode(
            lod_enabled=lod_enabled,
            prev_enabled=bool(self.lod_edges_culled_mode),
            scale_hint=scale_hint,
            enter_scale_value=getattr(_settings_ui, "GRAPH_LOD_EDGE_MIN_SCALE", 0.22),
            exit_scale_value=getattr(_settings_ui, "GRAPH_LOD_EDGE_VISIBILITY_EXIT_SCALE", None),
        )
        if bool(self.lod_edges_culled_mode) != bool(new_state):
            self._set_edges_culled_mode(bool(new_state))

    def _set_edges_culled_mode(self, enabled: bool) -> None:
        new_state = bool(enabled)
        if self.lod_edges_culled_mode == new_state:
            return
        self._lod_edges_culled_mode = new_state

        # 鸟瞰模式：边永远不应显示（由 blocks-only 统一控制）。
        if self.blocks_only_overview_mode:
            return

        if not new_state:
            # 退出裁剪模式：恢复所有边可见性
            for edge_item in (self.edge_items or {}).values():
                if edge_item is not None:
                    edge_item.setVisible(True)
            self._lod_culled_visible_edge_ids.clear()
            self.update()
            return

        # 进入裁剪模式：仅保留应显示的边可见（选中/高亮）。
        self._apply_edges_culled_visibility_to_all_edges()
        self.update()

    def _on_selection_changed_sync_lod_visibility(self) -> None:
        """selectionChanged 回调：在边裁剪模式下刷新边可见性。"""
        if self.blocks_only_overview_mode:
            return
        if not self.lod_edges_culled_mode:
            return
        # 差量更新：仅更新“选中边集合”的变化，避免每次选中节点也 O(E) 全量扫描。
        selected_edge_ids: set[str] = set()
        for item in list(self.selectedItems() or []):
            edge_id_value = getattr(item, "edge_id", None)
            if isinstance(edge_id_value, str) and edge_id_value:
                selected_edge_ids.add(edge_id_value)

        prev_visible = set(getattr(self, "_lod_culled_visible_edge_ids", set()) or set())

        # 1) 新选中的边：显示
        for edge_id in list(selected_edge_ids - prev_visible):
            edge_item = (self.edge_items or {}).get(edge_id)
            if edge_item is not None:
                edge_item.setVisible(True)

        # 2) 取消选中的边：若不处于高亮，则隐藏
        for edge_id in list(prev_visible - selected_edge_ids):
            edge_item = (self.edge_items or {}).get(edge_id)
            if edge_item is None:
                continue
            highlight_color = getattr(edge_item, "_highlight_color", None)
            if highlight_color is None:
                edge_item.setVisible(False)

        # 3) 更新缓存集合：保留“选中边”与“仍因高亮而可见的边”
        new_visible: set[str] = set(selected_edge_ids)
        for edge_id in list(prev_visible - selected_edge_ids):
            edge_item = (self.edge_items or {}).get(edge_id)
            if edge_item is None:
                continue
            if getattr(edge_item, "_highlight_color", None) is not None and edge_item.isVisible():
                new_visible.add(edge_id)
        self._lod_culled_visible_edge_ids = new_visible
        self.update()

    def _apply_edges_culled_visibility_to_all_edges(self) -> None:
        """边裁剪模式下：根据选中/高亮状态设置边可见性。"""
        visible_edge_ids: set[str] = set()
        for edge_item in (self.edge_items or {}).values():
            if edge_item is None:
                continue
            highlight_color = getattr(edge_item, "_highlight_color", None)
            should_show = bool(edge_item.isSelected()) or (highlight_color is not None)
            edge_item.setVisible(should_show)
            if should_show:
                edge_id_value = getattr(edge_item, "edge_id", None)
                if isinstance(edge_id_value, str) and edge_id_value:
                    visible_edge_ids.add(edge_id_value)
        self._lod_culled_visible_edge_ids = visible_edge_ids

    def _on_selection_changed_fast_preview_auto_expand(self) -> None:
        """快速预览模式下：新选中的节点自动展开。

        规则：
        - 仅在 fast_preview_mode 下生效；
        - 只对“本次新被选中”的节点做展开，避免用户手动收起后又被立刻自动展开；
        - 取消选中不会自动收起（收起只能手动点按钮）。
        """
        if not bool(getattr(self, "fast_preview_mode", False)):
            return
        if self._fast_preview_auto_expand_guard:
            return
        self._fast_preview_auto_expand_guard = True
        try:
            from app.ui.graph.items.fast_preview_items import FastPreviewNodeGraphicsItem

            selected_node_ids: set[str] = set()
            for item in self.selectedItems():
                if isinstance(item, FastPreviewNodeGraphicsItem):
                    node_id_value = getattr(getattr(item, "node", None), "id", "") if item is not None else ""
                    node_id = str(node_id_value or "")
                    if node_id:
                        selected_node_ids.add(node_id)

            newly_selected = selected_node_ids - (self._fast_preview_last_selected_node_ids or set())
            self._fast_preview_last_selected_node_ids = selected_node_ids

            if not newly_selected:
                return

            # 框选/多选：一次性展开所有新选中节点
            self._schedule_fast_preview_auto_expand(newly_selected)
        finally:
            self._fast_preview_auto_expand_guard = False

    def _ensure_fast_preview_auto_expand_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_fast_preview_auto_expand_timer", None)
        if isinstance(timer, QtCore.QTimer):
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._flush_fast_preview_auto_expand)
        self._fast_preview_auto_expand_timer = timer
        return timer

    def _schedule_fast_preview_auto_expand(self, node_ids: Iterable[str]) -> None:
        pending = getattr(self, "_fast_preview_auto_expand_pending_node_ids", None)
        if not isinstance(pending, set):
            pending = set()
            self._fast_preview_auto_expand_pending_node_ids = pending

        for node_id in node_ids:
            normalized = str(node_id or "")
            if normalized:
                pending.add(normalized)

        if not pending:
            return

        timer = self._ensure_fast_preview_auto_expand_timer()
        debounce_ms = int(getattr(self, "_fast_preview_auto_expand_debounce_ms", 120))
        timer.start(debounce_ms)

    def _flush_fast_preview_auto_expand(self) -> None:
        if not bool(getattr(self, "fast_preview_mode", False)):
            return

        pending = getattr(self, "_fast_preview_auto_expand_pending_node_ids", None)
        if not isinstance(pending, set) or not pending:
            return

        # 若节点仍在移动（拖拽中），则延后执行，避免边/端口重建与拖拽刷新互相打架导致卡顿。
        now = time.perf_counter()
        last_move_ts = float(getattr(self, "_fast_preview_last_node_move_ts", 0.0) or 0.0)
        if now - last_move_ts < 0.10:
            timer = self._ensure_fast_preview_auto_expand_timer()
            debounce_ms = int(getattr(self, "_fast_preview_auto_expand_debounce_ms", 120))
            timer.start(debounce_ms)
            return

        node_ids: list[str] = list(pending)
        pending.clear()

        if self._fast_preview_auto_expand_guard:
            return

        self._fast_preview_auto_expand_guard = True
        try:
            for node_id in node_ids:
                self.set_fast_preview_node_detail_expanded(node_id, True)
        finally:
            self._fast_preview_auto_expand_guard = False

    # === EditSessionCapabilities（单一真源） ===

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._edit_session_capabilities

    def set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        """更新会话能力，并同步到场景交互开关（read_only）与现有节点可拖拽状态。"""
        self._edit_session_capabilities = capabilities
        self._read_only = bool(capabilities.is_read_only)

        # 同步现有节点项的可移动标志，避免“先只读构建→后切交互”时节点仍不可拖拽。
        for node_item in self.node_items.values():
            node_item.setFlag(
                QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable,
                (not self._read_only) or bool(self._allow_node_drag_in_read_only),
            )

        # 同步行内常量编辑控件的可交互性：
        # - QGraphicsTextItem：只读时允许“选中复制”但禁止编辑
        # - QGraphicsProxyWidget：只读时尽量保持控件可选中（例如 QLineEdit），并禁止修改
        desired_text_flags = (
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
            if self._read_only
            else QtCore.Qt.TextInteractionFlag.TextEditorInteraction
        )

        def _sync_embedded_constant_widget(widget: QtWidgets.QWidget | None) -> None:
            """同步行内常量控件的只读交互策略。

            目标：
            - 只读会话：禁止修改，但允许选中复制（尽力覆盖 QLineEdit 等文本控件）。
            - 可交互会话：恢复为可编辑状态。
            """
            if widget is None:
                return

            if isinstance(widget, QtWidgets.QLineEdit):
                widget.setEnabled(True)
                widget.setReadOnly(bool(self._read_only))
                return
            if isinstance(widget, QtWidgets.QTextEdit):
                widget.setEnabled(True)
                widget.setReadOnly(bool(self._read_only))
                return
            if isinstance(widget, QtWidgets.QPlainTextEdit):
                widget.setEnabled(True)
                widget.setReadOnly(bool(self._read_only))
                return

            # QComboBox 不支持“选中文字复制”；只读时直接禁用以阻止误改。
            if isinstance(widget, QtWidgets.QComboBox):
                widget.setEnabled(not bool(self._read_only))
                return

            # 容器类 widget：保持可交互，递归处理子控件。
            widget.setEnabled(True)
            for line_edit in widget.findChildren(QtWidgets.QLineEdit):
                line_edit.setEnabled(True)
                line_edit.setReadOnly(bool(self._read_only))
            for text_edit in widget.findChildren(QtWidgets.QTextEdit):
                text_edit.setEnabled(True)
                text_edit.setReadOnly(bool(self._read_only))
            for plain_text_edit in widget.findChildren(QtWidgets.QPlainTextEdit):
                plain_text_edit.setEnabled(True)
                plain_text_edit.setReadOnly(bool(self._read_only))
            for combo in widget.findChildren(QtWidgets.QComboBox):
                combo.setEnabled(not bool(self._read_only))

        for node_item in self.node_items.values():
            constant_edits = getattr(node_item, "_constant_edits", None)
            if not isinstance(constant_edits, dict):
                continue
            for edit_item in constant_edits.values():
                if hasattr(edit_item, "setTextInteractionFlags"):
                    edit_item.setTextInteractionFlags(desired_text_flags)
                if hasattr(edit_item, "widget") and callable(getattr(edit_item, "widget")):
                    embedded_widget = edit_item.widget()
                    if isinstance(embedded_widget, QtWidgets.QWidget):
                        _sync_embedded_constant_widget(embedded_widget)

    @property
    def read_only(self) -> bool:
        """兼容字段：只读由 capabilities.can_interact 推导。

        注意：请优先使用 set_edit_session_capabilities()，避免语义分叉。
        """
        return self._read_only

    @read_only.setter
    def read_only(self, value: bool) -> None:
        # 兼容旧写法：只改“可交互”能力，保留其余能力位。
        self.set_edit_session_capabilities(
            self._edit_session_capabilities.with_overrides(can_interact=not bool(value))
        )

    # === 辅助方法：维护节点到连线的邻接索引 ===

    def _register_edge_for_nodes(self, edge_item: EdgeGraphicsItem) -> None:
        """在邻接索引中登记一条连线，供节点拖动与移动命令快速查找关联连线。"""
        src_node_id = edge_item.src.node_item.node.id
        dst_node_id = edge_item.dst.node_item.node.id
        if src_node_id not in self._edges_by_node_id:
            self._edges_by_node_id[src_node_id] = set()
        if dst_node_id not in self._edges_by_node_id:
            self._edges_by_node_id[dst_node_id] = set()
        self._edges_by_node_id[src_node_id].add(edge_item)
        self._edges_by_node_id[dst_node_id].add(edge_item)

    def _unregister_edge_for_nodes(self, edge_item: EdgeGraphicsItem) -> None:
        """从邻接索引中移除一条连线，在删除连线或删除节点时调用。"""
        src_node = getattr(edge_item.src, "node_item", None)
        dst_node = getattr(edge_item.dst, "node_item", None)
        src_node_id = getattr(src_node.node, "id", None) if src_node is not None else None
        dst_node_id = getattr(dst_node.node, "id", None) if dst_node is not None else None
        if src_node_id is not None:
            edge_set = self._edges_by_node_id.get(src_node_id)
            if edge_set is not None:
                edge_set.discard(edge_item)
                if not edge_set:
                    self._edges_by_node_id.pop(src_node_id, None)
        if dst_node_id is not None:
            edge_set = self._edges_by_node_id.get(dst_node_id)
            if edge_set is not None:
                edge_set.discard(edge_item)
                if not edge_set:
                    self._edges_by_node_id.pop(dst_node_id, None)

    def get_edges_for_node(self, node_id: str) -> list[EdgeGraphicsItem]:
        """返回与给定节点 ID 相连的所有连线图形项列表。"""
        edge_set = self._edges_by_node_id.get(node_id)
        if not edge_set:
            return []
        return list(edge_set)

    # === Batched edges layer（fast_preview_mode / 只读大图） ===

    def has_batched_fast_preview_edges(self) -> bool:
        return getattr(self, "_batched_fast_preview_edge_layer", None) is not None

    def pick_batched_edge_id_at(self, scene_pos: QtCore.QPointF) -> str | None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        pick_fn = getattr(layer, "pick_edge_id_at", None) if layer is not None else None
        if not callable(pick_fn):
            return None
        scale_hint = float(getattr(self, "view_scale_hint", 1.0) or 1.0)
        return pick_fn(scene_pos, scale_hint=scale_hint)

    def get_batched_edge_ids_for_node(self, node_id: str) -> set[str]:
        """返回批量边层中，与 node_id 相连的 edge_id 集合。"""
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        get_fn = getattr(layer, "get_edge_ids_for_node", None) if layer is not None else None
        if not callable(get_fn):
            return set()
        return set(get_fn(str(node_id or "")) or set())

    def set_batched_selected_edge_ids(self, edge_ids: Iterable[str]) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        set_fn = getattr(layer, "set_selected_edge_ids", None) if layer is not None else None
        if callable(set_fn):
            set_fn(edge_ids)

    def clear_batched_selected_edges(self) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        clear_fn = getattr(layer, "clear_selected_edges", None) if layer is not None else None
        if callable(clear_fn):
            clear_fn()

    def set_batched_dim_state(self, *, active: bool, focused_edge_ids: Iterable[str]) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        set_fn = getattr(layer, "set_dim_state", None) if layer is not None else None
        if callable(set_fn):
            set_fn(active=bool(active), focused_edge_ids=focused_edge_ids)

    def clear_batched_dim_state(self) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        clear_fn = getattr(layer, "clear_dim_state", None) if layer is not None else None
        if callable(clear_fn):
            clear_fn()

    def update_batched_edges_for_node_ids(self, node_ids: Iterable[str]) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        update_fn = getattr(layer, "update_edges_for_node_ids", None) if layer is not None else None
        if callable(update_fn):
            update_fn(node_ids)

    def remove_batched_edge(self, edge_id: str) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        remove_fn = getattr(layer, "remove_edge", None) if layer is not None else None
        if callable(remove_fn):
            remove_fn(str(edge_id or ""))

    def set_batched_edge_excluded(self, edge_id: str, excluded: bool) -> None:
        layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        set_fn = getattr(layer, "set_edge_excluded", None) if layer is not None else None
        if callable(set_fn):
            set_fn(str(edge_id or ""), bool(excluded))
    
    def get_node_def(self, node: NodeModel):
        """获取节点定义（包含显式端口类型）。
        
        - 对于“发送信号/监听信号”节点，会在基础定义上叠加当前信号绑定对应的参数类型；
        - 对于结构体相关节点，会在基础定义上叠加选中字段对应的端口类型。
        """
        node_def_ref = getattr(node, "node_def_ref", None)
        if node_def_ref is None:
            raise ValueError(f"GraphScene.get_node_def: 节点缺少 node_def_ref：{getattr(node, 'category', '')}/{getattr(node, 'title', '')}")

        kind = str(getattr(node_def_ref, "kind", "") or "").strip()
        ref_key = str(getattr(node_def_ref, "key", "") or "").strip()
        if kind == "builtin":
            chosen_def = self.node_library.get(ref_key)
            if chosen_def is None:
                raise KeyError(f"GraphScene.get_node_def: node_library 中未找到 builtin NodeDef：{ref_key}")
        elif kind == "composite":
            chosen_def = None
            for _, candidate in (self.node_library or {}).items():
                if not getattr(candidate, "is_composite", False):
                    continue
                if str(getattr(candidate, "composite_id", "") or "") == ref_key:
                    chosen_def = candidate
                    break
            if chosen_def is None:
                raise KeyError(f"GraphScene.get_node_def: node_library 中未找到 composite NodeDef（composite_id={ref_key}）")
        elif kind == "event":
            # event 的 key 通常为事件实例标识；端口判定/类型推断需要按 (category/title) 映射回 builtin NodeDef。
            category = str(getattr(node, "category", "") or "").strip()
            title = str(getattr(node, "title", "") or "").strip()
            builtin_key = f"{category}/{title}" if (category and title) else ""
            chosen_def = self.node_library.get(builtin_key) if builtin_key else None
        else:
            raise ValueError(f"GraphScene.get_node_def: 非法 node_def_ref.kind：{kind!r}")

        node_def = get_effective_signal_node_def_for_scene(self, node, chosen_def)
        node_def = get_effective_struct_node_def_for_scene(self, node, node_def)
        return node_def
    
    def _refresh_all_ports(self, node_ids: Optional[Iterable[str]] = None) -> None:
        """刷新端口显示；可选地仅刷新指定节点"""
        if node_ids is None:
            target_items = list(self.node_items.values())
        else:
            unique_ids = []
            seen_ids: set[str] = set()
            for node_id in node_ids:
                if node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                unique_ids.append(node_id)
            target_items = [
                self.node_items[node_id]
                for node_id in unique_ids
                if node_id in self.node_items
            ]
        if not target_items:
            return
        for node_item in target_items:
            # 刷新所有输入端口（数据端口）
            for port_item in node_item._ports_in:
                port_item._update_tooltip()
                port_item.update()
            # 刷新所有输出端口（数据端口）
            for port_item in node_item._ports_out:
                port_item._update_tooltip()
                port_item.update()
            # 刷新输入流程端口
            if node_item._flow_in:
                node_item._flow_in._update_tooltip()
                node_item._flow_in.update()
            # 刷新输出流程端口
            if node_item._flow_out:
                node_item._flow_out._update_tooltip()
                node_item._flow_out.update()
    
    def cleanup_virtual_pins_for_deleted_node(self, node_id: str) -> bool:
        """清理删除节点后的虚拟引脚映射（委托给虚拟引脚 UI 服务）。
        
        说明：
        - 仅在“复合节点编辑器”上下文中生效（is_composite_editor=True）；
        - 具体的映射清理与持久化策略由 `virtual_pin_ui_service.cleanup_virtual_pins_for_deleted_node`
          负责，本方法只关心刷新端口显示。
        """
        if not self.is_composite_editor:
            return False

        has_changes, affected_node_ids = cleanup_virtual_pins_for_deleted_node_ui(self, node_id)
        if not has_changes:
            return False

        # 局部刷新受影响节点的端口提示与高亮
        self._refresh_all_ports(affected_node_ids or None)
        return True
    
    def add_node_item(self, node: NodeModel) -> NodeGraphicsItem:
        # 信号/结构体节点的 UI 侧模型预处理下沉到 service，GraphScene 不直接写业务规则。
        prepare_signal_node_model_for_scene(node)
        prepare_struct_node_model_for_scene(self, node)

        if getattr(self, "fast_preview_mode", False):
            from app.ui.graph.items.fast_preview_items import FastPreviewNodeGraphicsItem

            item = FastPreviewNodeGraphicsItem(node)
        else:
            item = NodeGraphicsItem(node)
        item.setPos(node.pos[0], node.pos[1])
        
        # 只读模式下禁止移动节点
        if self.read_only and (not bool(self._allow_node_drag_in_read_only)):
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        
        self.addItem(item)
        # NodeGraphicsItem 的端口布局依赖 scene() 与 layout_registry_context。
        # 必须在 addItem 后触发一次布局，避免构造阶段 scene() 仍为 None。
        item._layout_ports()
        # port items are already added as child items, no need to add to scene separately
        self.node_items[node.id] = item
        self.last_added_node_id = node.id

        # 新增节点：按当前 LOD/鸟瞰模式立即收敛可见性，避免在缩放较小/鸟瞰状态下
        # 仍然创建并枚举大量端口/按钮图元造成卡顿。
        if self.blocks_only_overview_mode:
            item.setVisible(False)
        if self.lod_ports_hidden_mode:
            self._apply_ports_hidden_visibility_to_node_item(item, should_show_ports=False)
        # 调试：流程出口占位节点可见性追踪（受 GRAPH_UI_VERBOSE 控制）
        if node.title == "流程出口" or node.id.startswith("node_flow_exit_"):
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                input_names = [p.name for p in node.inputs]
                output_names = [p.name for p in node.outputs]
                print(
                    "[流程出口-节点] 创建占位节点: "
                    f"id={node.id}, pos={node.pos}, inputs={input_names}, outputs={output_names}"
                )
        
        # 单次编辑模式下：立即更新场景矩形与小地图
        # 批量构建阶段（例如加载大图）由控制器关闭该路径，统一在结束后调用 rebuild_scene_rect_and_minimap()
        if not getattr(self, "is_bulk_adding_items", False):
            # 更新场景矩形以包含新节点，并保持大量的扩展空间
            self._update_scene_rect()
            
            # 通知所有视图更新小地图
            for view in self.views():
                if hasattr(view, 'mini_map') and view.mini_map:
                    view.mini_map.update()
        
        return item

    def add_edge_item(self, edge):  # type: ignore[override]
        """创建连线图形项。

        - 非快速预览：复用 SceneModelOpsMixin.add_edge_item（端口驱动的 EdgeGraphicsItem）
        - 快速预览：使用轻量 Edge（不依赖端口图元），按节点矩形绘制
        """
        if not getattr(self, "fast_preview_mode", False):
            # 只读大图批量边：不再逐条创建 EdgeGraphicsItem，改由批量渲染层绘制（显著降低 item 数量）
            batched_layer = getattr(self, "_batched_fast_preview_edge_layer", None)
            add_batched = getattr(batched_layer, "add_edge", None) if batched_layer is not None else None
            if callable(add_batched) and bool(getattr(self, "read_only", False)):
                edge_id_value = str(getattr(edge, "id", "") or "")
                if edge_id_value:
                    src_id = str(getattr(edge, "src_node", "") or "")
                    dst_id = str(getattr(edge, "dst_node", "") or "")
                    if src_id and dst_id:
                        add_batched(edge_id=edge_id_value, src_node_id=src_id, dst_node_id=dst_id)
                        # 端口布局：与 SceneModelOpsMixin.add_edge_item 的语义对齐（隐藏已连线输入端口的常量输入框）
                        if getattr(self, "is_bulk_adding_items", False):
                            self._deferred_port_layout_node_ids.add(dst_id)
                        else:
                            dst_item = (self.node_items or {}).get(dst_id)
                            if dst_item is not None and hasattr(dst_item, "_layout_ports"):
                                dst_item._layout_ports()
                        # 鸟瞰：边不显示（统一隐藏渲染层）
                        if self.blocks_only_overview_mode:
                            batched_layer.setVisible(False)
                return None

            edge_item_obj = SceneModelOpsMixin.add_edge_item(self, edge)
            if edge_item_obj is None:
                return None
            # 鸟瞰模式：边不显示
            if self.blocks_only_overview_mode:
                edge_item_obj.setVisible(False)
                return edge_item_obj
            # 边裁剪模式：按当前规则设置可见性
            if self.lod_edges_culled_mode:
                highlight_color = getattr(edge_item_obj, "_highlight_color", None)
                edge_item_obj.setVisible(bool(edge_item_obj.isSelected()) or (highlight_color is not None))
            return edge_item_obj

        src_item = self.node_items.get(getattr(edge, "src_node", ""))
        dst_item = self.node_items.get(getattr(edge, "dst_node", ""))
        if not src_item or not dst_item:
            return None

        # fast_preview_mode + batched edges：不再为每条边创建 QGraphicsItem，改由单一渲染层绘制。
        batched_layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        add_batched = getattr(batched_layer, "add_edge", None) if batched_layer is not None else None
        if callable(add_batched):
            edge_id_value = str(getattr(edge, "id", "") or "")
            if edge_id_value:
                add_batched(
                    edge_id=edge_id_value,
                    src_node_id=str(getattr(edge, "src_node", "") or ""),
                    dst_node_id=str(getattr(edge, "dst_node", "") or ""),
                )
                # 鸟瞰：边不显示（统一隐藏渲染层）
                if self.blocks_only_overview_mode:
                    batched_layer.setVisible(False)
            return None

        from app.ui.graph.items.fast_preview_items import FastPreviewEdgeGraphicsItem, PreviewEdgeEndpoint
        from engine.graph.common import FLOW_PORT_PLACEHOLDER
        from engine.utils.graph.graph_utils import is_flow_port_name

        src_name = str(getattr(edge, "src_port", "") or "")
        dst_name = str(getattr(edge, "dst_port", "") or "")
        # 兼容：流程边在序列化中可能使用占位符 'flow'，UI 展示按“流程入/流程出”统一命名。
        if src_name == FLOW_PORT_PLACEHOLDER:
            src_name = "流程出"
        if dst_name == FLOW_PORT_PLACEHOLDER:
            dst_name = "流程入"

        preview_src = PreviewEdgeEndpoint(src_item, src_name, is_flow=is_flow_port_name(src_name))
        preview_dst = PreviewEdgeEndpoint(dst_item, dst_name, is_flow=is_flow_port_name(dst_name))

        edge_id_value = str(getattr(edge, "id", "") or "")
        edge_item = FastPreviewEdgeGraphicsItem(preview_src, preview_dst, edge_id_value)
        self.addItem(edge_item)
        self.edge_items[edge_id_value] = edge_item  # type: ignore[assignment]
        if hasattr(self, "_register_edge_for_nodes"):
            self._register_edge_for_nodes(edge_item)  # type: ignore[arg-type]
        # 鸟瞰/边裁剪：对新增预览边应用当前可见性规则
        if self.blocks_only_overview_mode:
            edge_item.setVisible(False)
        elif self.lod_edges_culled_mode:
            highlight_color = getattr(edge_item, "_highlight_color", None)
            edge_item.setVisible(bool(edge_item.isSelected()) or (highlight_color is not None))
        return edge_item

    # === 快速预览：节点级展开/收起（只影响用户点中的节点） ===

    def toggle_fast_preview_node_detail(self, node_id: str) -> None:
        """在 fast_preview_mode 下切换某个节点的“展开详情”。

        约定：
        - 只允许同时展开一个节点；
        - 展开节点后，将其相邻边升级为“端口对齐边”（EdgeGraphicsItem），以便看清连接端口；
        - 收起时降级回轻量边（FastPreviewEdgeGraphicsItem）。
        """
        if not bool(getattr(self, "fast_preview_mode", False)):
            return
        normalized_node_id = str(node_id or "")
        if not normalized_node_id:
            return

        from app.ui.graph.items.fast_preview_items import FastPreviewNodeGraphicsItem

        target_item = self.node_items.get(normalized_node_id)
        if not isinstance(target_item, FastPreviewNodeGraphicsItem):
            return

        if target_item.is_preview_detail_expanded:
            self.set_fast_preview_node_detail_expanded(normalized_node_id, False)
        else:
            self.set_fast_preview_node_detail_expanded(normalized_node_id, True)

    def set_fast_preview_node_detail_expanded(self, node_id: str, expanded: bool) -> None:
        """显式设置某个节点的展开状态（fast_preview_mode 下）。

        注意：
        - 该方法不会因为其它节点状态而自动收起任何节点；
        - 展开/收起后，会重建与该节点相邻的边类型（轻量边/端口对齐边）。
        """
        if not bool(getattr(self, "fast_preview_mode", False)):
            return
        normalized_node_id = str(node_id or "")
        if not normalized_node_id:
            return

        from app.ui.graph.items.fast_preview_items import FastPreviewNodeGraphicsItem

        node_item = self.node_items.get(normalized_node_id)
        if not isinstance(node_item, FastPreviewNodeGraphicsItem):
            return

        node_item.set_preview_detail_expanded(bool(expanded))
        self._rebuild_fast_preview_edges_around_node(normalized_node_id)

    def _rebuild_fast_preview_edges_around_node(self, node_id: str) -> None:
        """重建与 node_id 相邻的连线渲染类型（轻量/端口对齐）。"""
        normalized_node_id = str(node_id or "")
        if not normalized_node_id:
            return

        # batched fast preview edges：邻接集合不再来自 edge_items，而由渲染层维护的 edge_id 索引提供。
        batched_layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        get_ids = getattr(batched_layer, "get_edge_ids_for_node", None) if batched_layer is not None else None
        if callable(get_ids):
            edge_ids = list(get_ids(normalized_node_id) or [])
        else:
            edges = list(self.get_edges_for_node(normalized_node_id))
            edge_ids = []
            for edge_item in edges:
                edge_id_value = getattr(edge_item, "edge_id", None)
                if isinstance(edge_id_value, str) and edge_id_value:
                    edge_ids.append(edge_id_value)
        for edge_id in edge_ids:
            self._rebuild_fast_preview_edge_item(edge_id)

    def _rebuild_fast_preview_edge_item(self, edge_id: str) -> None:
        """根据“端点节点是否展开”选择 EdgeGraphicsItem 或 FastPreviewEdgeGraphicsItem。"""
        edge_id_value = str(edge_id or "")
        if not edge_id_value:
            return

        edge_model = self.model.edges.get(edge_id_value) if hasattr(self, "model") else None
        if edge_model is None:
            return

        src_node_id = str(getattr(edge_model, "src_node", "") or "")
        dst_node_id = str(getattr(edge_model, "dst_node", "") or "")
        if not src_node_id or not dst_node_id:
            return

        src_node_item = self.node_items.get(src_node_id)
        dst_node_item = self.node_items.get(dst_node_id)
        if src_node_item is None or dst_node_item is None:
            return

        src_expanded = bool(getattr(src_node_item, "is_preview_detail_expanded", False))
        dst_expanded = bool(getattr(dst_node_item, "is_preview_detail_expanded", False))
        use_port_aligned_edge = src_expanded or dst_expanded

        # 先移除旧边
        existing_edge_item = self.edge_items.get(edge_id_value)
        if existing_edge_item is not None:
            if hasattr(self, "_unregister_edge_for_nodes"):
                self._unregister_edge_for_nodes(existing_edge_item)  # type: ignore[arg-type]
            self.removeItem(existing_edge_item)
            del self.edge_items[edge_id_value]

        from app.ui.graph.items.fast_preview_items import FastPreviewEdgeGraphicsItem, PreviewEdgeEndpoint
        from engine.graph.common import FLOW_PORT_PLACEHOLDER
        from engine.utils.graph.graph_utils import is_flow_port_name

        src_port_name = str(getattr(edge_model, "src_port", "") or "")
        dst_port_name = str(getattr(edge_model, "dst_port", "") or "")
        if src_port_name == FLOW_PORT_PLACEHOLDER:
            src_port_name = "流程出"
        if dst_port_name == FLOW_PORT_PLACEHOLDER:
            dst_port_name = "流程入"

        src_is_flow = bool(is_flow_port_name(src_port_name))
        dst_is_flow = bool(is_flow_port_name(dst_port_name))

        # batched fast preview edges：轻量边由渲染层绘制；仅在需要“端口对齐”时 materialize 单条边图元
        batched_layer = getattr(self, "_batched_fast_preview_edge_layer", None)
        has_batched = batched_layer is not None and callable(getattr(batched_layer, "add_edge", None))

        if use_port_aligned_edge:
            if has_batched:
                # 确保该 edge_id 从渲染层排除（避免重复绘制）
                self.set_batched_edge_excluded(edge_id_value, True)
            from app.ui.graph.items.edge_item import EdgeGraphicsItem

            src_endpoint = self._resolve_edge_endpoint_for_fast_preview(
                src_node_item,
                src_port_name,
                is_input=False,
                is_flow=src_is_flow,
                prefer_port=src_expanded,
            )
            dst_endpoint = self._resolve_edge_endpoint_for_fast_preview(
                dst_node_item,
                dst_port_name,
                is_input=True,
                is_flow=dst_is_flow,
                prefer_port=dst_expanded,
            )
            new_edge_item = EdgeGraphicsItem(src_endpoint, dst_endpoint, edge_id_value)  # type: ignore[arg-type]
            self.addItem(new_edge_item)
            self.edge_items[edge_id_value] = new_edge_item  # type: ignore[assignment]
            if hasattr(self, "_register_edge_for_nodes"):
                self._register_edge_for_nodes(new_edge_item)  # type: ignore[arg-type]

            # 鸟瞰/边裁剪：对新增边应用当前可见性规则
            if self.blocks_only_overview_mode:
                new_edge_item.setVisible(False)
            elif self.lod_edges_culled_mode:
                highlight_color = getattr(new_edge_item, "_highlight_color", None)
                new_edge_item.setVisible(bool(new_edge_item.isSelected()) or (highlight_color is not None))
            return

        # use_port_aligned_edge=False：回到轻量边
        if has_batched:
            # 重新纳入渲染层绘制
            self.set_batched_edge_excluded(edge_id_value, False)
            has_edge = getattr(batched_layer, "has_edge", None)
            if not callable(has_edge) or not bool(has_edge(edge_id_value)):
                batched_layer.add_edge(edge_id=edge_id_value, src_node_id=src_node_id, dst_node_id=dst_node_id)
            # 节点展开/收起会改变节点矩形，需刷新相关边几何缓存
            self.update_batched_edges_for_node_ids([src_node_id, dst_node_id])
            return

        preview_src = PreviewEdgeEndpoint(src_node_item, src_port_name, is_flow=src_is_flow)
        preview_dst = PreviewEdgeEndpoint(dst_node_item, dst_port_name, is_flow=dst_is_flow)
        new_edge_item = FastPreviewEdgeGraphicsItem(preview_src, preview_dst, edge_id_value)

        self.addItem(new_edge_item)
        self.edge_items[edge_id_value] = new_edge_item  # type: ignore[assignment]
        if hasattr(self, "_register_edge_for_nodes"):
            self._register_edge_for_nodes(new_edge_item)  # type: ignore[arg-type]
        # 鸟瞰/边裁剪：对新增预览边应用当前可见性规则
        if self.blocks_only_overview_mode:
            new_edge_item.setVisible(False)
        elif self.lod_edges_culled_mode:
            highlight_color = getattr(new_edge_item, "_highlight_color", None)
            new_edge_item.setVisible(bool(new_edge_item.isSelected()) or (highlight_color is not None))

    def _resolve_edge_endpoint_for_fast_preview(
        self,
        node_item: NodeGraphicsItem,
        port_name: str,
        *,
        is_input: bool,
        is_flow: bool,
        prefer_port: bool,
    ):
        """为端口对齐边解析端点：

        - prefer_port=True 且能找到对应 PortGraphicsItem → 返回 PortGraphicsItem
        - 否则返回 PreviewEdgeEndpoint（按节点中心作为端点）
        """
        from app.ui.graph.items.fast_preview_items import PreviewEdgeEndpoint

        normalized_port_name = str(port_name or "")
        if prefer_port and hasattr(node_item, "get_port_by_name"):
            port_item = node_item.get_port_by_name(normalized_port_name, is_input=is_input)  # type: ignore[arg-type]
            if port_item is not None:
                return port_item
        return PreviewEdgeEndpoint(node_item, normalized_port_name, is_flow=bool(is_flow))
    
    def rebuild_scene_rect_and_minimap(self) -> None:
        """在批量修改后一次性更新场景矩形与小地图缓存。
        
        - 避免在加载大图时对每个节点调用 itemsBoundingRect（O(N²)）
        - 仅在批量构建完成后调用一次，保持网格与小地图范围正确
        """
        # 统一更新场景矩形
        self._update_scene_rect()
        
        # 统一刷新所有视图中的小地图（重置缓存以适配最新内容边界）
        for view in self.views():
            if hasattr(view, "mini_map") and view.mini_map:
                mini_map_widget = view.mini_map
                if hasattr(mini_map_widget, "reset_cached_rect"):
                    mini_map_widget.reset_cached_rect()
                else:
                    mini_map_widget.update()

    def flush_deferred_port_layouts(self) -> None:
        """批量构建阶段结束后，统一刷新被连线影响的节点端口布局。

        设计目标：
        - 避免在批量装配过程中每条边都触发一次 NodeGraphicsItem._layout_ports()；
        - 批量装配完成后再集中重排一次，保证“已连接端口隐藏输入框”等 UI 语义正确。
        """
        if not self._deferred_port_layout_node_ids:
            return
        node_ids = list(self._deferred_port_layout_node_ids)
        self._deferred_port_layout_node_ids.clear()
        for node_id in node_ids:
            node_item = self.node_items.get(node_id)
            if node_item is not None:
                node_item._layout_ports()

    def _on_signals_updated_from_manager(self) -> None:
        """当信号管理器中的信号定义被修改后，尝试同步当前图中相关节点的端口。"""
        on_signals_updated_from_manager_service(self)
