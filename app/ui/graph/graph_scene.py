from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from ui.foundation.theme_manager import Colors, ThemeManager
from ui.foundation.context_menu_builder import ContextMenuBuilder
from ui.graph.items.port_item import PortGraphicsItem, BranchPortValueEdit
from ui.graph.items.node_item import NodeGraphicsItem
from ui.graph.items.edge_item import EdgeGraphicsItem
from ui.graph.virtual_pin_ui_service import cleanup_virtual_pins_for_deleted_node as cleanup_virtual_pins_for_deleted_node_ui
from ui.graph.signal_node_service import (
    get_effective_node_def_for_scene as get_effective_signal_node_def_for_scene,
    bind_signal_for_node as bind_signal_for_node_service,
    open_signal_manager as open_signal_manager_service,
    on_signals_updated_from_manager as on_signals_updated_from_manager_service,
)
from ui.graph.struct_node_service import (
    get_effective_node_def_for_scene as get_effective_struct_node_def_for_scene,
    bind_struct_for_node as bind_struct_for_node_service,
)
from ui.overlays.scene_overlay import SceneOverlayMixin
from ui.scene.interaction_mixin import SceneInteractionMixin
from ui.scene.model_ops_mixin import SceneModelOpsMixin
from ui.scene.ydebug_interaction_mixin import YDebugInteractionMixin
from typing import Optional, List, Dict, TYPE_CHECKING, Iterable
from collections import defaultdict, deque
from engine.graph.models.graph_model import GraphModel, NodeModel, EdgeModel
from engine.nodes.node_definition_loader import NodeDef
from ui.graph.graph_undo import (
    UndoRedoManager,
    AddNodeCommand,
    DeleteNodeCommand,
    AddEdgeCommand,
    DeleteEdgeCommand,
    MoveNodeCommand,
)
from engine.nodes.port_type_system import can_connect_ports
from engine.layout import UI_ROW_HEIGHT  # unified row height metric
from engine.layout import LayoutService
from engine.layout.flow.preprocess import promote_flow_outputs_for_layout
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.configs.settings import settings as _settings_ui
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    STRUCT_NODE_TITLES,
)

if TYPE_CHECKING:
    from ui.dynamic_port_widget import AddPortButton
NODE_PADDING = 10
ROW_HEIGHT = UI_ROW_HEIGHT
# 为多分支节点的"+"按钮额外预留一行高度，提升可点击与视觉间距
BRANCH_PLUS_EXTRA_ROWS = 1


class GraphScene(SceneOverlayMixin, SceneInteractionMixin, SceneModelOpsMixin, YDebugInteractionMixin, QtWidgets.QGraphicsScene):
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
        self.node_library = node_library or {}  # 节点定义库（用于获取显式类型）
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
            _result = LayoutService.compute_layout(self.model, node_library=node_lib, include_augmented_model=False)
            self.model.basic_blocks = _result.basic_blocks

    # === 视图上下文菜单桥接（由 GraphView 委托调用） ===

    def handle_view_context_menu(
        self,
        view: QtWidgets.QGraphicsView,
        event: QtGui.QContextMenuEvent,
        scene_pos: QtCore.QPointF,
        item: Optional[QtWidgets.QGraphicsItem],
    ) -> bool:
        """处理由 GraphView 转发的右键菜单请求。

        返回:
            bool: 若已处理并接受事件, 返回 True; 否则返回 False 交由默认逻辑处理。
        """
        # 在端口上右键：保留原有端口自身的菜单行为（由 Qt 标准分发负责）
        if isinstance(item, PortGraphicsItem):
            return False

        # 在节点上右键：为特定节点类型提供节点级菜单（例如信号/结构体节点）
        node_item: Optional[NodeGraphicsItem] = None
        if isinstance(item, NodeGraphicsItem):
            node_item = item
        elif item is not None and isinstance(item.parentItem(), NodeGraphicsItem):
            parent_node_item = item.parentItem()
            if isinstance(parent_node_item, NodeGraphicsItem):
                node_item = parent_node_item

        if node_item is not None:
            node_title = getattr(node_item.node, "title", "") or ""
            node_id = getattr(node_item.node, "id", "") or ""

            menu_builder = ContextMenuBuilder(view)
            has_action = False

            # 发送/监听信号节点：提供信号绑定与信号管理入口
            if node_title in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE) and node_id:
                if hasattr(self, "bind_signal_for_node"):
                    def _bind_signal() -> None:
                        self.bind_signal_for_node(node_id)  # type: ignore[attr-defined]

                    menu_builder.add_action("选择信号…", _bind_signal)
                    has_action = True

                if hasattr(self, "open_signal_manager"):
                    def _open_signal_manager() -> None:
                        self.open_signal_manager()  # type: ignore[attr-defined]

                    if has_action:
                        menu_builder.add_separator()
                    menu_builder.add_action("打开信号管理器…", _open_signal_manager)
                    has_action = True

            # 结构体相关节点：提供结构体绑定入口
            if node_title in STRUCT_NODE_TITLES and node_id:
                if hasattr(self, "bind_struct_for_node"):
                    def _bind_struct() -> None:
                        self.bind_struct_for_node(node_id)  # type: ignore[attr-defined]

                    if has_action:
                        menu_builder.add_separator()
                    menu_builder.add_action("配置结构体…", _bind_struct)
                    has_action = True

            if has_action:
                menu_builder.exec_global(event.globalPos())
                event.accept()
                return True

        # 在连线上右键：显示“删除连线”菜单（统一构建与样式）
        if isinstance(item, EdgeGraphicsItem):
            edge_id = item.edge_id

            def _delete_edge() -> None:
                command = DeleteEdgeCommand(self.model, self, edge_id)
                self.undo_manager.execute_command(command)

            ContextMenuBuilder(view).add_action("删除连线", _delete_edge).exec_global(event.globalPos())
            event.accept()
            return True

        # 在空白处右键：显示“添加节点”菜单（仍复用 GraphView 提供的桥接方法）
        if item is None and hasattr(view, "_show_add_node_menu"):
            view._show_add_node_menu(event.globalPos(), scene_pos)
            event.accept()
            return True

        # 其它情况：不处理, 交由默认逻辑(例如图元自身的 contextMenuEvent)
        return False

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
        # 监听信号节点在模型层默认没有输入端口，但 UI 需要一个“信号名”选择行：
        # 若缺失则为当前场景中的节点副本补充一个只读选择输入端口。
        if getattr(node, "title", "") == SIGNAL_LISTEN_NODE_TITLE:
            has_signal_name_input = any(
                getattr(port, "name", "") == "信号名"
                for port in getattr(node, "inputs", []) or []
            )
            if not has_signal_name_input:
                node.add_input_port("信号名")

        item = NodeGraphicsItem(node)
        item.setPos(node.pos[0], node.pos[1])
        
        # 只读模式下禁止移动节点
        if self.read_only:
            item.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        
        self.addItem(item)
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

    # === 信号系统：节点绑定与端口同步 ===

    def bind_signal_for_node(self, node_id: str) -> None:
        """为指定节点弹出信号选择对话框并写入绑定信息（委托给信号适配服务）。"""
        bind_signal_for_node_service(self, node_id)

    def open_signal_manager(self) -> None:
        """打开信号管理器对话框，并在信号定义变更后同步当前图中的信号端口。"""
        open_signal_manager_service(self)

    def _on_signals_updated_from_manager(self) -> None:
        """当信号管理器中的信号定义被修改后，尝试同步当前图中相关节点的端口。"""
        on_signals_updated_from_manager_service(self)

    # === 结构体系统：节点绑定与端口同步 ===

    def bind_struct_for_node(self, node_id: str) -> None:
        """为指定节点弹出结构体选择对话框并写入绑定信息（委托给结构体适配服务）。"""
        bind_struct_for_node_service(self, node_id)


