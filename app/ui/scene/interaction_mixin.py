"""场景交互 Mixin

提供鼠标事件处理、端口高亮、自动连接等交互能力。
假设宿主场景提供: model, node_items, edge_items, undo_manager, get_node_def 等。
"""

from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, TYPE_CHECKING
from engine.nodes.port_type_system import can_connect_ports
from ui.foundation.theme_manager import Colors

if TYPE_CHECKING:
    from ui.graph.items.port_item import PortGraphicsItem
    from ui.graph.items.node_item import NodeGraphicsItem
    from ui.graph.items.edge_item import EdgeGraphicsItem


class SceneInteractionMixin:
    """场景交互 Mixin
    
    要求宿主类提供以下属性:
    - model: GraphModel
    - node_items: dict[str, NodeGraphicsItem]
    - edge_items: dict[str, EdgeGraphicsItem]
    - undo_manager: UndoRedoManager
    - temp_connection_start: Optional[PortGraphicsItem]
    - temp_connection_line: Optional[QGraphicsLineItem]
    - pending_src_node_id: Optional[str]
    - pending_src_port_name: Optional[str]
    - pending_is_src_output: bool
    - pending_is_src_flow: bool
    - pending_connection_port: Optional[PortGraphicsItem]
    - pending_connection_scene_pos: Optional[QPointF]
    - read_only: bool
    - get_node_def(node): method
    """
    
    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        """统一入口：按职责委托给 Y 调试逻辑与连线起手逻辑。"""
        # 优先委托给 Y 调试图标交互（由 YDebugInteractionMixin 提供）
        ydebug_handler = getattr(self, "_handle_ydebug_mouse_press", None)
        if callable(ydebug_handler) and ydebug_handler(event):
            return

        # 只读模式下禁止创建连接
        if not self.read_only and self._handle_port_connection_mouse_press(event):
            return

        super().mousePressEvent(event)

    def _handle_port_connection_mouse_press(
        self,
        event: QtWidgets.QGraphicsSceneMouseEvent,
    ) -> bool:
        """处理端口拖拽连线的起手逻辑。

        返回:
            bool: 若本方法已处理并接受事件, 则返回 True, 否则返回 False。
        """
        item = self.itemAt(event.scenePos(), QtGui.QTransform())
        # 导入需要在运行时进行, 避免循环依赖
        from ui.graph.items.port_item import PortGraphicsItem

        if not isinstance(item, PortGraphicsItem):
            return False

        self.temp_connection_start = item

        # 高亮所有兼容的端口
        self._highlight_compatible_ports(item)

        # 创建临时预览线
        start_pos = item.scenePos()
        self.temp_connection_line = QtWidgets.QGraphicsLineItem(
            start_pos.x(),
            start_pos.y(),
            event.scenePos().x(),
            event.scenePos().y(),
        )
        pen = QtGui.QPen(QtGui.QColor(Colors.ACCENT), 2, QtCore.Qt.PenStyle.DashLine)
        self.temp_connection_line.setPen(pen)
        self.temp_connection_line.setZValue(10)
        self.addItem(self.temp_connection_line)
        event.accept()
        return True

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        """统一入口：在释放鼠标时协调“结束拖拽连线”和“记录节点移动”两个职责。"""
        # 1) 优先处理“结束拖拽连线”分支（包含类型检查、命令入撤销栈或记录 pending_* 信息）
        if self._handle_connection_on_mouse_release(event):
            return

        # 2) 若当前没有处于连线拖拽状态，则视为普通释放：根据 node_move_tracking 生成 MoveNodeCommand
        self._finalize_node_move_commands()

        # 3) 将事件继续交给基类处理（选择框、其他场景级行为等）
        super().mouseReleaseEvent(event)

    def _handle_connection_on_mouse_release(
        self,
        event: QtWidgets.QGraphicsSceneMouseEvent,
    ) -> bool:
        """处理从端口拖拽产生的临时连接，在鼠标释放时决定最终行为。

        返回:
            bool: 若本方法已完整处理事件（包括 accept），返回 True；否则返回 False。
        """
        from ui.graph.items.port_item import PortGraphicsItem

        # 若当前没有处于“拖拽连线”状态，交由后续逻辑处理
        if self.temp_connection_start is None:
            return False

        # 无论后续是成功连线、弹出菜单还是放弃，都先清理 UI 状态
        self._clear_port_highlights()
        self._remove_temp_connection_preview_line()

        target_item = self.itemAt(event.scenePos(), QtGui.QTransform())

        # 情形 A：拖到另一个方向相反的端口上，尝试直接建立连线
        if isinstance(target_item, PortGraphicsItem) and (
            target_item.is_input != self.temp_connection_start.is_input
        ):
            self._try_commit_edge_between_ports(
                source_port=self.temp_connection_start,
                target_port=target_item,
            )
        # 情形 B：拖到空白或非端口位置，记录 pending_* 并通过视图弹出“添加节点”菜单
        elif target_item is None or not isinstance(target_item, PortGraphicsItem):
            self._prepare_pending_connection_and_open_menu(
                event_scene_pos=event.scenePos(),
            )

        # 无论走哪条分支，都重置起点端口并标记事件已处理
        self.temp_connection_start = None
        event.accept()
        return True

    def _try_commit_edge_between_ports(
        self,
        source_port: "PortGraphicsItem",
        target_port: "PortGraphicsItem",
    ) -> None:
        """在两个端口之间尝试创建连线（包含显式类型检查与命令入撤销栈）。"""
        from ui.graph.graph_undo import AddEdgeCommand
        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[连接] 松开到端口: {target_port.node_item.node.title}.{target_port.name}")

        # 统一确定“数据流向”：source 始终视为输出端口，target 视为输入端口
        src_port = source_port if not source_port.is_input else target_port
        dst_port = target_port if target_port.is_input else source_port

        # 优先从 NodeDef 获取显式端口类型；缺失时回退到端口自身的类型
        src_node_def = self.get_node_def(src_port.node_item.node)
        dst_node_def = self.get_node_def(dst_port.node_item.node)

        if src_node_def and dst_node_def:
            src_type = src_node_def.get_port_type(src_port.name, is_input=False)
            dst_type = dst_node_def.get_port_type(dst_port.name, is_input=True)
        else:
            src_type = src_port.port_type
            dst_type = dst_port.port_type

        # 类型不兼容时直接终止，不落地任何连线
        if not can_connect_ports(src_type, dst_type):
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(f"[连接] 类型不匹配: {src_type} -> {dst_type}")
            return

        src_node_id = src_port.node_item.node.id
        dst_node_id = dst_port.node_item.node.id

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[连接] 创建连线: {src_node_id}.{src_port.name} -> {dst_node_id}.{dst_port.name}")

        edge_id = self.model.gen_id("edge")
        command = AddEdgeCommand(
            self.model,
            self,
            edge_id,
            src_node_id,
            src_port.name,
            dst_node_id,
            dst_port.name,
        )
        self.undo_manager.execute_command(command)

    def _prepare_pending_connection_and_open_menu(
        self,
        event_scene_pos: QtCore.QPointF,
    ) -> None:
        """拖拽到空白处时，记录待连接信息并通过视图弹出“添加节点”菜单。"""
        from engine.configs.settings import settings as _settings_ui
        from engine.utils.logging.logger import log_warn

        # 保存连接起始端口信息，供后续 auto_connect_new_node 使用
        self.pending_connection_port = self.temp_connection_start
        self.pending_connection_scene_pos = event_scene_pos

        if self.temp_connection_start is None:
            return

        self.pending_src_node_id = self.temp_connection_start.node_item.node.id
        self.pending_src_port_name = self.temp_connection_start.name
        self.pending_is_src_output = not self.temp_connection_start.is_input
        self.pending_is_src_flow = self.temp_connection_start.is_flow

        # 获取端口的显式类型（从 NodeDef），缺少定义时记录一次警告并退化为“泛型”
        src_node = self.model.nodes.get(self.pending_src_node_id)
        src_node_def = self.get_node_def(src_node) if src_node else None
        if src_node_def:
            filter_port_type = src_node_def.get_port_type(
                self.pending_src_port_name,
                is_input=not self.pending_is_src_output,
            )
        else:
            log_warn(
                "[GraphScene] 节点 '{}' 缺少 NodeDef，无法获取端口类型",
                self.pending_src_node_id or "",
            )
            filter_port_type = "泛型"

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(
                f"[连接] 保存起始信息: node={self.pending_src_node_id}, "
                f"port={self.pending_src_port_name}, 类型={filter_port_type}",
            )

        # 通过视图显示节点菜单（带类型过滤）
        for view in self.views():
            if not hasattr(view, "_show_add_node_menu"):
                continue

            view_pos = view.mapFromScene(event_scene_pos)
            global_pos = view.mapToGlobal(view_pos)
            view._show_add_node_menu(
                global_pos,
                event_scene_pos,
                filter_port_type,
                self.pending_is_src_output,
            )
            break

    def _remove_temp_connection_preview_line(self) -> None:
        """移除拖拽连线时的临时预览线（若存在）。"""
        if self.temp_connection_line:
            self.removeItem(self.temp_connection_line)
            self.temp_connection_line = None

    def _finalize_node_move_commands(self) -> None:
        """根据 node_move_tracking 生成 MoveNodeCommand，并清理移动标记。"""
        from ui.graph.graph_undo import MoveNodeCommand

        tracking = getattr(self, "node_move_tracking", None)
        if not tracking:
            return

        for node_id, old_pos in list(tracking.items()):
            node_item = self.node_items.get(node_id)
            if not node_item:
                continue

            new_pos = node_item.pos()
            new_pos_tuple = (new_pos.x(), new_pos.y())

            # 只有位置真的改变了才记录到撤销栈
            if old_pos != new_pos_tuple:
                command = MoveNodeCommand(
                    self.model,
                    self,
                    node_id,
                    old_pos,
                    new_pos_tuple,
                )
                self.undo_manager.execute_command(command)

            # 清除节点级的“正在移动”标记，避免后续误判
            if hasattr(node_item, "_moving_started"):
                delattr(node_item, "_moving_started")

        tracking.clear()

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        # 记录鼠标位置,用于粘贴
        self.last_mouse_scene_pos = event.scenePos()
        
        # 更新临时连线预览
        if self.temp_connection_line and self.temp_connection_start:
            start_pos = self.temp_connection_start.scenePos()
            end_pos = event.scenePos()
            self.temp_connection_line.setLine(
                start_pos.x(), start_pos.y(), 
                end_pos.x(), end_pos.y()
            )
        super().mouseMoveEvent(event)
    
    def auto_connect_new_node(self, new_node_id: str = None) -> None:
        """自动连接新创建的节点到待连接的端口"""
        from ui.graph.graph_undo import AddEdgeCommand

        if not self.pending_src_node_id or not self.pending_connection_scene_pos:
            self._clear_pending_connection()
            return

        if not getattr(self, "undo_manager", None):
            self._clear_pending_connection()
            return

        target_node_id = self._resolve_new_node_id_for_connection(new_node_id)
        if not target_node_id:
            self._clear_pending_connection()
            return

        latest_node = self.model.nodes.get(target_node_id)
        latest_node_item = self.node_items.get(target_node_id)
        if latest_node is None or latest_node_item is None:
            self._clear_pending_connection()
            return

        source_port_type = self._get_pending_source_port_type()
        new_node_def = self.get_node_def(latest_node) if hasattr(self, "get_node_def") else None
        candidate_ports = latest_node_item._ports_in if self.pending_is_src_output else latest_node_item._ports_out
        compatible_port = self._find_compatible_port(
            candidate_ports,
            new_node_def,
            source_port_type,
            expect_input=self.pending_is_src_output,
        )

        if compatible_port is None:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("[自动连接] 未找到兼容端口，跳过自动连接")
            self._clear_pending_connection()
            return

        if self.pending_is_src_output:
            src_node_id = self.pending_src_node_id
            src_port_name = self.pending_src_port_name
            dst_node_id = target_node_id
            dst_port_name = compatible_port.name
        else:
            src_node_id = target_node_id
            src_port_name = compatible_port.name
            dst_node_id = self.pending_src_node_id
            dst_port_name = self.pending_src_port_name

        edge_id = self.model.gen_id("edge")
        cmd = AddEdgeCommand(
            self.model,
            self,
            edge_id,
            src_node_id,
            src_port_name,
            dst_node_id,
            dst_port_name,
        )
        self.undo_manager.execute_command(cmd)
        self._clear_pending_connection()
    
    def _clear_pending_connection(self) -> None:
        """清除待连接状态"""
        self.pending_connection_port = None
        self.pending_connection_scene_pos = None
        self.temp_connection_start = None
        self.pending_src_node_id = None
        self.pending_src_port_name = None
        self.pending_is_src_output = False
        self.pending_is_src_flow = False

    def _resolve_new_node_id_for_connection(self, explicit_node_id: Optional[str]) -> Optional[str]:
        if explicit_node_id and explicit_node_id in self.model.nodes:
            return explicit_node_id
        last_added = getattr(self, "last_added_node_id", None)
        if last_added and last_added in self.model.nodes:
            return last_added
        node_ids = list(self.model.nodes.keys())
        if node_ids:
            return node_ids[-1]
        return None

    def _get_pending_source_port_type(self) -> str:
        node = self.model.nodes.get(self.pending_src_node_id) if self.pending_src_node_id else None
        node_def = self.get_node_def(node) if (node is not None and hasattr(self, "get_node_def")) else None
        if node_def:
            explicit_type = node_def.get_port_type(
                self.pending_src_port_name,
                is_input=not self.pending_is_src_output,
            )
            if explicit_type:
                return explicit_type
        pending_port = getattr(self, "pending_connection_port", None)
        if pending_port is not None and getattr(pending_port, "port_type", None):
            return pending_port.port_type
        return "泛型"

    def _find_compatible_port(
        self,
        candidate_ports,
        node_def,
        source_port_type: str,
        expect_input: bool,
    ):
        for port in candidate_ports:
            target_type = self._get_target_port_type(port, node_def, expect_input)
            if expect_input:
                if can_connect_ports(source_port_type, target_type):
                    return port
            else:
                if can_connect_ports(target_type, source_port_type):
                    return port
        return None

    def _get_target_port_type(self, port_item, node_def, expect_input: bool) -> str:
        if node_def:
            explicit = node_def.get_port_type(port_item.name, is_input=expect_input)
            if explicit:
                return explicit
        return getattr(port_item, "port_type", "泛型")
    
    def _highlight_compatible_ports(self, source_port: 'PortGraphicsItem') -> None:
        """高亮所有与源端口兼容的端口
        
        Args:
            source_port: 源端口(拖拽起点)
        """
        # 获取源端口的类型(使用与连接时相同的逻辑)
        source_node_def = self.get_node_def(source_port.node_item.node)
        if source_node_def:
            source_type = source_node_def.get_port_type(source_port.name, is_input=source_port.is_input)
        else:
            source_type = source_port.port_type
        
        from engine.configs.settings import settings as _settings_ui

        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[高亮] 源端口类型: {source_type}, 方向: {'输入' if source_port.is_input else '输出'}")
        
        # 遍历所有节点的所有端口,使用 can_connect_ports 进行精确判断
        highlight_count = 0
        for node_item in self.node_items.values():
            # 如果源端口是输出,检查所有输入端口
            if not source_port.is_input:
                for port in node_item._ports_in:
                    if port != source_port:
                        # 获取目标端口的类型(使用与连接时相同的逻辑)
                        target_node_def = self.get_node_def(port.node_item.node)
                        if target_node_def:
                            target_type = target_node_def.get_port_type(port.name, is_input=True)
                        else:
                            target_type = port.port_type
                        
                        # 使用与实际连接完全相同的判断逻辑
                        if can_connect_ports(source_type, target_type):
                            port.is_highlighted = True
                            port.update()
                            highlight_count += 1
            # 如果源端口是输入,检查所有输出端口
            else:
                for port in node_item._ports_out:
                    if port != source_port:
                        # 获取目标端口的类型(使用与连接时相同的逻辑)
                        target_node_def = self.get_node_def(port.node_item.node)
                        if target_node_def:
                            target_type = target_node_def.get_port_type(port.name, is_input=False)
                        else:
                            target_type = port.port_type
                        
                        # 使用与实际连接完全相同的判断逻辑
                        if can_connect_ports(target_type, source_type):
                            port.is_highlighted = True
                            port.update()
                            highlight_count += 1
        
        if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
            print(f"[高亮] 高亮了 {highlight_count} 个兼容端口")
    
    def _clear_port_highlights(self) -> None:
        """清除所有端口高亮"""
        for node_item in self.node_items.values():
            for port in node_item._ports_in + node_item._ports_out:
                if port.is_highlighted:
                    port.is_highlighted = False
                    port.update()

    def on_node_item_position_change_started(
        self,
        node_item: "NodeGraphicsItem",
        old_pos: tuple[float, float],
    ) -> None:
        """节点开始移动时由 `NodeGraphicsItem.itemChange` 调用。
        
        仅记录一次移动操作的起点位置，供鼠标释放时生成 MoveNodeCommand 使用；
        不直接修改模型或撤销栈，保持模型更新逻辑集中在命令对象中。
        """
        node_id = node_item.node.id
        tracking = getattr(self, "node_move_tracking", None)
        if tracking is None:
            return
        if node_id not in tracking:
            tracking[node_id] = old_pos

    def on_node_item_position_changed(
        self,
        node_item: "NodeGraphicsItem",
        new_pos: tuple[float, float],
    ) -> None:
        """节点位置发生变化时由 `NodeGraphicsItem.itemChange` 调用。
        
        - 负责刷新与该节点相连的连线路径（基于邻接索引或 edge_items 扫描）；
        - 不直接更新 `NodeModel.pos`，模型位置仅通过 `MoveNodeCommand` 统一更新。
        """
        _ = new_pos  # 预留参数，便于后续扩展对齐/吸附等行为
        node_id = node_item.node.id

        # 优先使用 GraphScene 提供的邻接索引接口（O(度数)）
        edges_for_node = []
        if hasattr(self, "get_edges_for_node"):
            edges_for_node = self.get_edges_for_node(node_id)  # type: ignore[call-arg]
        else:
            edge_map = getattr(self, "edge_items", {}) or {}
            for edge_item in edge_map.values():
                src_item = getattr(edge_item, "src", None)
                dst_item = getattr(edge_item, "dst", None)
                if getattr(src_item, "node_item", None) is node_item or getattr(
                    dst_item, "node_item", None
                ) is node_item:
                    edges_for_node.append(edge_item)

        for edge_item in edges_for_node:
            edge_item.update_path()

