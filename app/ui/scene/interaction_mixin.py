"""场景交互 Mixin

提供鼠标事件处理、端口高亮、自动连接等交互能力。
假设宿主场景提供: model, node_items, edge_items, undo_manager, get_node_def 等。
"""

from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from typing import Optional, TYPE_CHECKING

from engine.nodes.port_type_system import can_connect_ports, GENERIC_PORT_TYPE
from engine.type_registry import can_convert_type
from app.ui.foundation.theme_manager import Colors

if TYPE_CHECKING:
    from app.ui.graph.items.port_item import PortGraphicsItem
    from app.ui.graph.items.node_item import NodeGraphicsItem
    from app.ui.graph.items.edge_item import EdgeGraphicsItem


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

    _TYPE_CONVERSION_NODE_TITLE = "数据类型转换"
    _TYPE_CONVERSION_INPUT_PORT_NAME = "输入"
    _TYPE_CONVERSION_OUTPUT_PORT_NAMES = ("输出", "转换结果")

    # ===== 节点拖拽时的连线路径刷新节流（大图性能优化）=====
    #
    # 说明：节点在拖拽过程中会频繁触发 ItemPositionHasChanged；若每个像素都同步刷新关联边的路径，
    # 在超大图下会导致明显卡顿。这里提供一个保守的节流策略：
    # - fast_preview_mode 下始终节流；
    # - 非 fast_preview_mode 时，仅在节点/连线数量达到阈值后启用节流。
    _EDGE_PATH_UPDATE_THROTTLE_NODE_THRESHOLD: int = 500
    _EDGE_PATH_UPDATE_THROTTLE_EDGE_THRESHOLD: int = 900
    _EDGE_PATH_UPDATE_THROTTLE_INTERVAL_MS: int = 16  # ~60 FPS

    def _normalize_port_type(self, port_type: str) -> str:
        return str(port_type or "").strip()

    def _is_generic_port_type(self, port_type: str) -> bool:
        return self._normalize_port_type(port_type) == GENERIC_PORT_TYPE

    def _pick_unique_specific_type(self, types: list[str]) -> tuple[str, bool]:
        """从类型列表中提取唯一具体类型。

        Returns:
            (type_text, is_conflicting)
            - type_text: 若存在且仅存在一个具体类型则返回该类型；否则返回空字符串
            - is_conflicting: 若存在多个不同具体类型则为 True
        """
        normalized = [self._normalize_port_type(t) for t in (types or [])]
        specific_types = [
            t for t in normalized if t and (t != GENERIC_PORT_TYPE) and (t != "流程")
        ]
        unique_types = sorted(set(specific_types))
        if len(unique_types) == 1:
            return unique_types[0], False
        if len(unique_types) > 1:
            return "", True
        return "", False

    def _get_connected_types_for_node_port(
        self,
        *,
        node_id: str,
        port_name: str,
        is_input: bool,
    ) -> list[str]:
        """获取某个节点端口当前已连接的“对端端口类型”列表（用于类型联动校验）。"""
        connected_types: list[str] = []
        if not node_id or not port_name:
            return connected_types

        for edge in (getattr(self.model, "edges", {}) or {}).values():
            if is_input:
                if getattr(edge, "dst_node", "") != node_id or getattr(edge, "dst_port", "") != port_name:
                    continue
                src_node_id = getattr(edge, "src_node", "")
                src_port_name = getattr(edge, "src_port", "")
                src_node = self.model.nodes.get(src_node_id) if src_node_id else None
                src_node_def = self.get_node_def(src_node) if src_node else None
                if src_node_def:
                    connected_types.append(
                        self._normalize_port_type(
                            src_node_def.get_port_type(src_port_name, is_input=False)
                        )
                    )
                else:
                    connected_types.append(GENERIC_PORT_TYPE)
            else:
                if getattr(edge, "src_node", "") != node_id or getattr(edge, "src_port", "") != port_name:
                    continue
                dst_node_id = getattr(edge, "dst_node", "")
                dst_port_name = getattr(edge, "dst_port", "")
                dst_node = self.model.nodes.get(dst_node_id) if dst_node_id else None
                dst_node_def = self.get_node_def(dst_node) if dst_node else None
                if dst_node_def:
                    connected_types.append(
                        self._normalize_port_type(
                            dst_node_def.get_port_type(dst_port_name, is_input=True)
                        )
                    )
                else:
                    connected_types.append(GENERIC_PORT_TYPE)

        return connected_types

    def _is_connection_allowed_by_generic_constraints(
        self,
        *,
        src_node_def: object | None,
        src_port_name: str,
        src_type: str,
        dst_node_def: object | None,
        dst_port_name: str,
        dst_type: str,
    ) -> bool:
        """在 can_connect_ports 之外，额外检查 NodeDef 声明的泛型约束。"""
        normalized_src_type = self._normalize_port_type(src_type)
        normalized_dst_type = self._normalize_port_type(dst_type)

        # “泛型家族”端口（泛型/泛型列表/泛型字典…）统一视为泛型端口参与约束判定。
        src_is_generic = normalized_src_type.startswith(GENERIC_PORT_TYPE)
        dst_is_generic = normalized_dst_type.startswith(GENERIC_PORT_TYPE)

        # 目标为泛型：若声明了 allowed，则要求源类型落在 allowed 内（源为泛型时无法收敛，不在此处阻断）
        if dst_is_generic and dst_node_def and hasattr(dst_node_def, "get_generic_constraints"):
            allowed = list(dst_node_def.get_generic_constraints(dst_port_name, True) or [])
            if allowed and (not src_is_generic) and normalized_src_type:
                return normalized_src_type in allowed

        # 源为泛型：若声明了 allowed，则要求目标类型落在 allowed 内（目标为泛型时无法收敛，不在此处阻断）
        if src_is_generic and src_node_def and hasattr(src_node_def, "get_generic_constraints"):
            allowed = list(src_node_def.get_generic_constraints(src_port_name, False) or [])
            if allowed and (not dst_is_generic) and normalized_dst_type:
                return normalized_dst_type in allowed

        # 泛型 ↔ 泛型：若双方均声明了 allowed，则要求交集非空（表示存在可满足的具体类型）
        if src_is_generic and dst_is_generic:
            if (
                src_node_def
                and dst_node_def
                and hasattr(src_node_def, "get_generic_constraints")
                and hasattr(dst_node_def, "get_generic_constraints")
            ):
                src_allowed = list(src_node_def.get_generic_constraints(src_port_name, False) or [])
                dst_allowed = list(dst_node_def.get_generic_constraints(dst_port_name, True) or [])
                if src_allowed and dst_allowed:
                    return bool(set(src_allowed).intersection(dst_allowed))

        return True

    def _is_connection_allowed_for_type_conversion_node(
        self,
        *,
        src_node,
        src_port_name: str,
        src_type: str,
        dst_node,
        dst_port_name: str,
        dst_type: str,
    ) -> bool:
        """对【数据类型转换】节点做输入/输出联动校验（基于 TYPE_CONVERSIONS）。"""
        src_title = getattr(src_node, "title", "")
        dst_title = getattr(dst_node, "title", "")
        src_node_id = getattr(src_node, "id", "")
        dst_node_id = getattr(dst_node, "id", "")

        normalized_src_type = self._normalize_port_type(src_type)
        normalized_dst_type = self._normalize_port_type(dst_type)

        is_src_conversion_output = (
            (src_title == self._TYPE_CONVERSION_NODE_TITLE)
            and (src_port_name in self._TYPE_CONVERSION_OUTPUT_PORT_NAMES)
        )
        is_dst_conversion_input = (
            (dst_title == self._TYPE_CONVERSION_NODE_TITLE)
            and (dst_port_name == self._TYPE_CONVERSION_INPUT_PORT_NAME)
        )

        # 当前连线与数据类型转换节点无关
        if (not is_src_conversion_output) and (not is_dst_conversion_input):
            return True

        # 统一定位“转换节点 ID”
        conversion_node_id = src_node_id if is_src_conversion_output else dst_node_id
        if not conversion_node_id:
            return True

        # 1) 输出类型一致性：同一个转换节点的输出只能被消费为同一种具体类型
        if is_src_conversion_output and normalized_dst_type and normalized_dst_type != GENERIC_PORT_TYPE:
            existing_output_types = []
            for output_port_name in self._TYPE_CONVERSION_OUTPUT_PORT_NAMES:
                existing_output_types.extend(
                    self._get_connected_types_for_node_port(
                        node_id=conversion_node_id,
                        port_name=output_port_name,
                        is_input=False,
                    )
                )
            existing_output_type, output_conflict = self._pick_unique_specific_type(existing_output_types)
            if output_conflict:
                return False
            if existing_output_type and existing_output_type != normalized_dst_type:
                return False

        # 2) 输入类型一致性：同一个转换节点的输入不应出现多个不同具体类型
        if is_dst_conversion_input and normalized_src_type and normalized_src_type != GENERIC_PORT_TYPE:
            existing_input_types = self._get_connected_types_for_node_port(
                node_id=conversion_node_id,
                port_name=self._TYPE_CONVERSION_INPUT_PORT_NAME,
                is_input=True,
            )
            existing_input_type, input_conflict = self._pick_unique_specific_type(existing_input_types)
            if input_conflict:
                return False
            if existing_input_type and existing_input_type != normalized_src_type:
                return False

        # 3) 联动校验：若输入/输出两侧类型都已确定为具体类型，则必须存在转换规则
        # - 若本次连线决定了输出类型，则输出=dst_type；输入从既有连线推断
        # - 若本次连线决定了输入类型，则输入=src_type；输出从既有连线推断
        if is_src_conversion_output:
            desired_output_type = normalized_dst_type
            existing_input_types = self._get_connected_types_for_node_port(
                node_id=conversion_node_id,
                port_name=self._TYPE_CONVERSION_INPUT_PORT_NAME,
                is_input=True,
            )
            desired_input_type, input_conflict = self._pick_unique_specific_type(existing_input_types)
            if input_conflict:
                return False
        else:
            desired_input_type = normalized_src_type
            existing_output_types = []
            for output_port_name in self._TYPE_CONVERSION_OUTPUT_PORT_NAMES:
                existing_output_types.extend(
                    self._get_connected_types_for_node_port(
                        node_id=conversion_node_id,
                        port_name=output_port_name,
                        is_input=False,
                    )
                )
            desired_output_type, output_conflict = self._pick_unique_specific_type(existing_output_types)
            if output_conflict:
                return False

        if (
            desired_input_type
            and desired_output_type
            and desired_input_type != GENERIC_PORT_TYPE
            and desired_output_type != GENERIC_PORT_TYPE
            and desired_input_type != "流程"
            and desired_output_type != "流程"
        ):
            can_convert, _ = can_convert_type(desired_input_type, desired_output_type)
            return bool(can_convert)

        return True

    def _can_connect_ports_with_constraints(
        self,
        *,
        src_port: "PortGraphicsItem",
        dst_port: "PortGraphicsItem",
        src_node_def: object | None,
        dst_node_def: object | None,
        src_type: str,
        dst_type: str,
    ) -> bool:
        if not can_connect_ports(src_type, dst_type):
            return False
        if not self._is_connection_allowed_by_generic_constraints(
            src_node_def=src_node_def,
            src_port_name=src_port.name,
            src_type=src_type,
            dst_node_def=dst_node_def,
            dst_port_name=dst_port.name,
            dst_type=dst_type,
        ):
            return False
        if not self._is_connection_allowed_for_type_conversion_node(
            src_node=src_port.node_item.node,
            src_port_name=src_port.name,
            src_type=src_type,
            dst_node=dst_port.node_item.node,
            dst_port_name=dst_port.name,
            dst_type=dst_type,
        ):
            return False
        return True
    
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
        from app.ui.graph.items.port_item import PortGraphicsItem

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
        from app.ui.graph.items.port_item import PortGraphicsItem

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
        from app.ui.graph.graph_undo import AddEdgeCommand
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

        # 类型/约束不兼容时直接终止，不落地任何连线
        if not self._can_connect_ports_with_constraints(
            src_port=src_port,
            dst_port=dst_port,
            src_node_def=src_node_def,
            dst_node_def=dst_node_def,
            src_type=src_type,
            dst_type=dst_type,
        ):
            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(f"[连接] 连接不允许: {src_type} -> {dst_type}")
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
        from app.ui.graph.graph_view import GraphView
        for view in self.views():
            if not isinstance(view, GraphView):
                continue

            view_pos = view.mapFromScene(event_scene_pos)
            global_pos = view.mapToGlobal(view_pos)
            view.show_add_node_menu(
                global_pos,
                event_scene_pos,
                filter_port_type=filter_port_type,
                is_output=self.pending_is_src_output,
            )
            break

    def _remove_temp_connection_preview_line(self) -> None:
        """移除拖拽连线时的临时预览线（若存在）。"""
        if self.temp_connection_line:
            self.removeItem(self.temp_connection_line)
            self.temp_connection_line = None

    def _finalize_node_move_commands(self) -> None:
        """根据 node_move_tracking 生成 MoveNodeCommand，并清理移动标记。"""
        from app.ui.graph.graph_undo import MoveNodeCommand

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

        # 结束拖拽时补齐一次连线路径刷新（若启用了节流，避免最终位置仍停留在上一帧）。
        self._flush_scheduled_edge_path_updates()
        timer = getattr(self, "_edge_path_update_timer", None)
        if isinstance(timer, QtCore.QTimer) and timer.isActive():
            timer.stop()

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
        pending_source_port = getattr(self, "pending_connection_port", None)
        compatible_port = None
        if pending_source_port is not None:
            for port in candidate_ports:
                if port is pending_source_port:
                    continue
                # _try_commit_edge_between_ports 会做最终拦截，这里尽量选择一个“可连”的端口
                # （包含泛型约束与数据类型转换节点的联动规则）
                tentative_src = pending_source_port if not pending_source_port.is_input else port
                tentative_dst = port if port.is_input else pending_source_port
                tentative_src_def = self.get_node_def(tentative_src.node_item.node)
                tentative_dst_def = self.get_node_def(tentative_dst.node_item.node)
                if tentative_src_def and tentative_dst_def:
                    tentative_src_type = tentative_src_def.get_port_type(tentative_src.name, is_input=False)
                    tentative_dst_type = tentative_dst_def.get_port_type(tentative_dst.name, is_input=True)
                else:
                    tentative_src_type = tentative_src.port_type
                    tentative_dst_type = tentative_dst.port_type
                if self._can_connect_ports_with_constraints(
                    src_port=tentative_src,
                    dst_port=tentative_dst,
                    src_node_def=tentative_src_def,
                    dst_node_def=tentative_dst_def,
                    src_type=tentative_src_type,
                    dst_type=tentative_dst_type,
                ):
                    compatible_port = port
                    break

        if compatible_port is None:
            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print("[自动连接] 未找到兼容端口，跳过自动连接")
            self._clear_pending_connection()
            return

        # 复用统一连线入口，确保与手工连线的约束/联动规则完全一致
        if pending_source_port is not None:
            self._try_commit_edge_between_ports(
                source_port=pending_source_port,
                target_port=compatible_port,
            )
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
                        
                        # 使用与实际连接完全相同的判断逻辑（含泛型约束与转换节点联动）
                        if self._can_connect_ports_with_constraints(
                            src_port=source_port,
                            dst_port=port,
                            src_node_def=source_node_def,
                            dst_node_def=target_node_def,
                            src_type=source_type,
                            dst_type=target_type,
                        ):
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
                        
                        # 使用与实际连接完全相同的判断逻辑（含泛型约束与转换节点联动）
                        if self._can_connect_ports_with_constraints(
                            src_port=port,
                            dst_port=source_port,
                            src_node_def=target_node_def,
                            dst_node_def=source_node_def,
                            src_type=target_type,
                            dst_type=source_type,
                        ):
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

    def _should_throttle_edge_path_updates(self) -> bool:
        """是否对节点拖拽期间的连线路径刷新启用节流。"""
        if bool(getattr(self, "fast_preview_mode", False)):
            return True
        node_count = len(getattr(self, "node_items", {}) or {})
        # edge_count 以模型为准：在“批量渲染边（无 per-edge item）”时 edge_items 无法反映真实规模。
        model = getattr(self, "model", None)
        model_edges = getattr(model, "edges", None) if model is not None else None
        if isinstance(model_edges, dict):
            edge_count = len(model_edges)
        else:
            edge_count = len(getattr(self, "edge_items", {}) or {})
        return bool(
            node_count >= self._EDGE_PATH_UPDATE_THROTTLE_NODE_THRESHOLD
            or edge_count >= self._EDGE_PATH_UPDATE_THROTTLE_EDGE_THRESHOLD
        )

    def _ensure_edge_path_update_timer(self) -> QtCore.QTimer:
        timer = getattr(self, "_edge_path_update_timer", None)
        if isinstance(timer, QtCore.QTimer):
            return timer
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._flush_scheduled_edge_path_updates)
        self._edge_path_update_timer = timer
        return timer

    def _schedule_edge_path_update_for_node(self, node_id: str) -> None:
        pending = getattr(self, "_pending_edge_path_update_node_ids", None)
        if not isinstance(pending, set):
            pending = set()
            self._pending_edge_path_update_node_ids = pending
        pending.add(str(node_id or ""))

        timer = self._ensure_edge_path_update_timer()
        if not timer.isActive():
            timer.start(int(self._EDGE_PATH_UPDATE_THROTTLE_INTERVAL_MS))

    def _flush_scheduled_edge_path_updates(self) -> None:
        pending = getattr(self, "_pending_edge_path_update_node_ids", None)
        if not isinstance(pending, set) or not pending:
            return
        node_ids: set[str] = set(pending)
        pending.clear()

        # 批处理去重：同一条边可能同时属于多个移动节点的邻接集合
        edges_by_obj_id: dict[int, object] = {}
        if hasattr(self, "get_edges_for_node"):
            for node_id in node_ids:
                for edge_item in self.get_edges_for_node(node_id):  # type: ignore[call-arg]
                    edges_by_obj_id[id(edge_item)] = edge_item
        else:
            edge_map = getattr(self, "edge_items", {}) or {}
            for edge_item in edge_map.values():
                src_item = getattr(getattr(edge_item, "src", None), "node_item", None)
                dst_item = getattr(getattr(edge_item, "dst", None), "node_item", None)
                src_id = str(getattr(getattr(src_item, "node", None), "id", "") or "")
                dst_id = str(getattr(getattr(dst_item, "node", None), "id", "") or "")
                if src_id in node_ids or dst_id in node_ids:
                    edges_by_obj_id[id(edge_item)] = edge_item

        for edge_item in edges_by_obj_id.values():
            if hasattr(edge_item, "update_path"):
                edge_item.update_path()

        # 批量渲染边：GraphScene 提供增量刷新入口（内部会做局部 update 失效，避免残影）
        update_batched = getattr(self, "update_batched_edges_for_node_ids", None)
        if callable(update_batched):
            update_batched(node_ids)

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

        # fast_preview_mode 下用于“选中自动展开”的防抖：节点移动期间不做重建
        if bool(getattr(self, "fast_preview_mode", False)):
            setattr(self, "_fast_preview_last_node_move_ts", time.perf_counter())

        if self._should_throttle_edge_path_updates():
            self._schedule_edge_path_update_for_node(str(node_id or ""))
            return

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

        update_batched = getattr(self, "update_batched_edges_for_node_ids", None)
        if callable(update_batched):
            update_batched([str(node_id or "")])

