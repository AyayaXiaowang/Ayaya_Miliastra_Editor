from __future__ import annotations

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
from engine.layout.flow.preprocess import promote_flow_outputs_for_layout
from engine.configs.settings import settings as _settings_ui

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
    ):
        super().__init__()
        self.model = model
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
        self.read_only = read_only  # 只读模式
        # 使用主题深色背景，统一节点画布观感
        self.setBackgroundBrush(QtGui.QColor(Colors.BG_DARK))
        
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
        if _settings.SHOW_BASIC_BLOCKS and (not getattr(self.model, "basic_blocks", None)):
            node_lib = self.node_library if isinstance(self.node_library, dict) else None
            _result = LayoutService.compute_layout(
                self.model,
                node_library=node_lib,
                include_augmented_model=False,
                workspace_path=getattr(self.layout_registry_context, "workspace_path", None),
            )
            self.model.basic_blocks = _result.basic_blocks

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
    
    def _promote_flow_outputs_for_layout(self, model_copy: GraphModel, node_library: Dict) -> None:
        """
        将模型中的“流程输出端口但名称不含‘流程’关键字”的端口临时改名为包含‘流程’的名字，
        以便布局/分块阶段使用基于端口名的规则正确识别流程边。
        仅修改 model_copy（克隆体），不影响原始模型与UI展示。
        """
        promote_flow_outputs_for_layout(model_copy, node_library)
    
    def get_node_def(self, node: NodeModel):
        """获取节点定义（包含显式端口类型）。
        
        - 对于“发送信号/监听信号”节点，会在基础定义上叠加当前信号绑定对应的参数类型；
        - 对于结构体相关节点，会在基础定义上叠加选中字段对应的端口类型。
        """
        key = f"{node.category}/{node.title}"
        base_def = self.node_library.get(key)
        node_def = get_effective_signal_node_def_for_scene(self, node, base_def)
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

        item = NodeGraphicsItem(node)
        item.setPos(node.pos[0], node.pos[1])
        
        # 只读模式下禁止移动节点
        if self.read_only:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        
        self.addItem(item)
        # NodeGraphicsItem 的端口布局依赖 scene() 与 layout_registry_context。
        # 必须在 addItem 后触发一次布局，避免构造阶段 scene() 仍为 None。
        item._layout_ports()
        # port items are already added as child items, no need to add to scene separately
        self.node_items[node.id] = item
        self.last_added_node_id = node.id
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
