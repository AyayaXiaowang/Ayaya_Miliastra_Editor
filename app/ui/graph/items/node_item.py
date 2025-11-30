from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets
from ui.foundation.theme_manager import Colors
from ui.graph.items.port_item import PortGraphicsItem, BranchPortValueEdit
from ui.widgets.constant_editors import (
    ConstantTextEdit,
    ConstantBoolComboBox,
    ConstantVector3Edit,
    create_constant_editor_for_port,
)
from typing import Optional, List, Dict, TYPE_CHECKING
from engine.graph.models.graph_model import NodeModel
from engine.layout import UI_ROW_HEIGHT
from engine.layout.utils.graph_query_utils import build_input_port_layout_plan
from engine.graph.common import is_selection_input_port

if TYPE_CHECKING:
    from ui.graph.graph_scene import GraphScene
    from ui.dynamic_port_widget import AddPortButton

NODE_PADDING = 10
ROW_HEIGHT = UI_ROW_HEIGHT
BRANCH_PLUS_EXTRA_ROWS = 1


class NodeGraphicsItem(QtWidgets.QGraphicsItem):
    def __init__(self, node: NodeModel):
        super().__init__()
        self.node = node
        self.title_font = QtGui.QFont('Microsoft YaHei', 11, QtGui.QFont.Weight.Bold)
        self._ports_in: List[PortGraphicsItem] = []
        self._ports_out: List[PortGraphicsItem] = []
        self._flow_in: Optional[PortGraphicsItem] = None
        self._flow_out: Optional[PortGraphicsItem] = None
        self._constant_edits: Dict[str, QtWidgets.QGraphicsItem] = {}  # 常量编辑框（可能是不同类型的控件）
        self._control_positions: Dict[str, tuple[float, float, float, str]] = {}  # {端口名: (x, y, width, type)} type可以是'text', 'bool', 'vector'
        # 输入端口所在的"标签行"索引映射（控件换行后，行索引不再等于端口序号）
        self._input_row_index_map: Dict[str, int] = {}
        self._add_port_button: Optional['AddPortButton'] = None  # 多分支节点的添加端口按钮
        # 给节点比连线更高的 z 值，让节点在连线上面
        self.setZValue(10)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        self._layout_ports()
    
    def iter_all_ports(self) -> list[PortGraphicsItem]:
        """返回该节点的所有端口（含流程端口）。"""
        ports: list[PortGraphicsItem] = []
        ports.extend(self._ports_in)
        ports.extend(self._ports_out)
        if self._flow_in:
            ports.append(self._flow_in)
        if self._flow_out:
            ports.append(self._flow_out)
        return [port for port in ports if port is not None]

    def get_port_by_name(self, port_name: str, *, is_input: Optional[bool] = None) -> Optional[PortGraphicsItem]:
        """根据端口名查找图形项，可限定输入/输出侧。"""
        if port_name == "流程入":
            return self._flow_in
        if port_name == "流程出":
            return self._flow_out
        if is_input is True:
            candidates = self._ports_in
        elif is_input is False:
            candidates = self._ports_out
        else:
            candidates = self.iter_all_ports()
        for port in candidates:
            if getattr(port, "name", None) == port_name:
                return port
        return None
    
    def _get_port_type(self, port_name: str, is_input: bool) -> str:
        """获取端口的类型
        
        Args:
            port_name: 端口名称
            is_input: 是否为输入端口
            
        Returns:
            端口类型字符串，如"整数"、"布尔值"、"向量3"等
        """
        from ui.graph.graph_scene import GraphScene
        scene = self.scene()
        if scene and isinstance(scene, GraphScene):
            node_def = scene.get_node_def(self.node)
            if node_def:
                return node_def.get_port_type(port_name, is_input)
        return "泛型"
    
    def itemChange(self, change, value):
        """节点位置/选中状态变化时的钩子。
        
        - 移动相关逻辑（模型更新、撤销命令、场景索引维护）统一委托给场景，
          避免视图对象直接操作 GraphScene 内部字段或 GraphModel。
        - 本类仅在合适的时机调用宿主场景提供的钩子方法：
          - on_node_item_position_change_started(node_item, old_pos)
          - on_node_item_position_changed(node_item, new_pos)
        """
        # 当节点位置即将改变时，通知场景记录旧位置（用于撤销命令）
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            current_scene = self.scene()
            if current_scene and not hasattr(self, "_moving_started"):
                old_pos = self.pos()
                if hasattr(current_scene, "on_node_item_position_change_started"):
                    current_scene.on_node_item_position_change_started(  # type: ignore[attr-defined]
                        self,
                        (old_pos.x(), old_pos.y()),
                    )
                self._moving_started = True  # 标记一次拖拽开始
        
        # 当节点位置已经改变时，仅通知场景刷新与该节点相连的连线
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            current_scene = self.scene()
            if current_scene and hasattr(current_scene, "on_node_item_position_changed"):
                new_pos = self.pos()
                current_scene.on_node_item_position_changed(  # type: ignore[attr-defined]
                    self,
                    (new_pos.x(), new_pos.y()),
                )
        
        # 当选中状态改变时，触发重绘以更新高亮效果
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update()
        
        return super().itemChange(change, value)

    # === 端口布局管线（拆分版） ===

    def _collect_edges_for_update(self) -> list[tuple]:
        """收集与当前节点相关、需要在布局后刷新的连线项及其端口名。"""
        edges_to_update: list[tuple] = []
        scene_ref_for_edges = self.scene()
        if not scene_ref_for_edges:
            return edges_to_update
        from ui.graph.graph_scene import GraphScene
        if not isinstance(scene_ref_for_edges, GraphScene):
            return edges_to_update
        connected_edges = scene_ref_for_edges.get_edges_for_node(self.node.id)
        for edge_item in connected_edges:
            is_src_side = edge_item.src.node_item == self
            is_dst_side = edge_item.dst.node_item == self
            src_port_name = edge_item.src.name if is_src_side else None
            dst_port_name = edge_item.dst.name if is_dst_side else None
            edges_to_update.append(
                (edge_item, is_src_side, src_port_name, is_dst_side, dst_port_name)
            )
        return edges_to_update

    def _reset_ports_and_controls(self) -> None:
        """清理旧端口与常量编辑控件，重置内部缓存。"""
        for port_item in self._ports_in + self._ports_out:
            port_item.setParentItem(None)
        for edit_item in self._constant_edits.values():
            edit_item.setParentItem(None)
        self._ports_in.clear()
        self._ports_out.clear()
        self._constant_edits.clear()
        self._control_positions.clear()
        self._flow_in = None
        self._flow_out = None

    def _collect_connected_input_ports(self) -> set[str]:
        """收集所有已连线的输入端口名称，用于布局与行内编辑判定。"""
        connected_input_ports: set[str] = set()
        scene_ref = self.scene()
        if not scene_ref:
            return connected_input_ports
        for edge_item in scene_ref.edge_items.values():
            if edge_item.dst.node_item == self:
                connected_input_ports.add(edge_item.dst.name)
        return connected_input_ports

    def _create_font_metrics(self) -> tuple[QtGui.QFontMetrics, QtGui.QFontMetrics]:
        """构造标签与输入文本的字体度量，用于宽度估算。"""
        label_font = QtGui.QFont("Microsoft YaHei", 9)
        input_font = QtGui.QFont("Consolas", 8)
        fm_label = QtGui.QFontMetrics(label_font)
        fm_input = QtGui.QFontMetrics(input_font)
        return fm_label, fm_input

    def _compute_node_width(
        self,
        plan,
        fm_label: QtGui.QFontMetrics,
    ) -> float:
        """根据左右端口标签的最大宽度，计算节点主体宽度。"""
        in_labels = [name for name in plan.render_inputs if name != "流程入"]
        out_labels = [port.name for port in self.node.outputs if port.name != "流程出"]
        in_width = max([fm_label.horizontalAdvance(text) for text in in_labels], default=0)
        out_width = max(
            [fm_label.horizontalAdvance(text) for text in out_labels], default=0
        )
        min_width_for_content = 20 + in_width + 15 + out_width + 20
        return float(max(260, min_width_for_content))

    def _compute_node_rect_and_rows(
        self,
        plan,
        width: float,
        is_multibranch_node: bool,
    ) -> tuple[QtCore.QRectF, float, float, float, int, int, int]:
        """计算节点整体矩形与内容区行数信息。"""
        total_input_rows = plan.total_input_rows
        total_output_rows = len(self.node.outputs)
        input_plus_rows = plan.input_plus_rows
        output_plus_rows = 1 if is_multibranch_node else 0
        max_rows = max(
            total_input_rows + input_plus_rows,
            total_output_rows + output_plus_rows,
            1,
        )
        content_height = max_rows * ROW_HEIGHT + NODE_PADDING
        header_height = ROW_HEIGHT + 10
        total_height = header_height + content_height + NODE_PADDING
        rect = QtCore.QRectF(0, 0, float(width), float(total_height))
        return (
            rect,
            header_height,
            content_height,
            total_height,
            total_input_rows,
            input_plus_rows,
            output_plus_rows,
        )

    def _layout_input_ports_and_controls(
        self,
        plan,
        width: float,
        input_start_y: float,
        connected_input_ports: set[str],
        fm_label: QtGui.QFontMetrics,
        fm_input: QtGui.QFontMetrics,
    ) -> None:
        """布局输入端口与对应的常量编辑控件。"""
        self._input_row_index_map.clear()

        for input_index, port_name in enumerate(plan.render_inputs):
            from engine.nodes.port_type_system import (  # type: ignore
                is_flow_port_with_context as _flow_ctx_with_lib,
            )

            scene_library = None
            scene_ref = self.scene()
            if scene_ref and hasattr(scene_ref, "node_library"):
                scene_library = scene_ref.node_library
            is_flow = _flow_ctx_with_lib(self.node, port_name, False, scene_library)
            # 选择端口：不可连线，仅保留行内输入控件
            is_select_input = (not is_flow) and is_selection_input_port(self.node, port_name)

            row_index = plan.row_index_by_port.get(port_name, input_index)
            port_y = input_start_y + row_index * ROW_HEIGHT + ROW_HEIGHT // 2

            if not is_select_input:
                port_item = PortGraphicsItem(self, port_name, True, input_index, is_flow=is_flow)
                port_item.setParentItem(self)
                port_item.setPos(12, port_y)
                self._ports_in.append(port_item)
                if is_flow:
                    self._flow_in = port_item

            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(
                    f"[端口布局] 节点[{self.node.title}]({self.node.id}) 输入端口: "
                    f"name='{port_name}', is_flow={is_flow}, pos=(12, {port_y})"
                )

            self._input_row_index_map[port_name] = row_index

            control_row_index = plan.control_row_index_by_port.get(port_name)
            if is_flow or control_row_index is None:
                continue

            control_x = 30
            control_y = input_start_y + control_row_index * ROW_HEIGHT + 2
            
            port_type = self._get_port_type(port_name, is_input=True)
            edit_item = create_constant_editor_for_port(self, port_name, port_type, self)
            if edit_item is None:
                continue

            # 根据控件类型设置布局和记录控制位置信息
            if isinstance(edit_item, ConstantBoolComboBox):
                edit_item.setPos(control_x, control_y)
                if hasattr(edit_item, "combo"):
                    edit_item.combo.setFixedWidth(60)
                self._control_positions[port_name] = (control_x, control_y, 60, "bool")
            elif isinstance(edit_item, ConstantVector3Edit):
                edit_item.setPos(control_x, control_y)
                self._control_positions[port_name] = (control_x, control_y, 150, "vector")
            elif isinstance(edit_item, ConstantTextEdit):
                edit_item.setPos(control_x, control_y + 2)
                available_width = width - control_x - 30
                text_width = max(60, available_width)
                edit_item.setTextWidth(text_width)
                self._control_positions[port_name] = (
                    control_x,
                    control_y,
                    text_width,
                    "text",
                )
            else:
                # 未知控件类型：仅设置位置，并不记录额外布局元数据
                edit_item.setPos(control_x, control_y)

            self._constant_edits[port_name] = edit_item

    def _layout_output_ports_and_branch_controls(
        self,
        header_height: float,
        fm_label: QtGui.QFontMetrics,
    ) -> None:
        """布局输出端口以及多分支节点的分支值编辑控件。"""
        output_start_y = header_height + NODE_PADDING
        is_multibranch_node = self.node.title == "多分支"

        for output_index, port in enumerate(self.node.outputs):
            from engine.nodes.port_type_system import (  # type: ignore
                is_flow_port_with_context as _flow_ctx_out,
            )

            scene_lib_out = None
            scene_ref = self.scene()
            if scene_ref and hasattr(scene_ref, "node_library"):
                scene_lib_out = scene_ref.node_library
            is_flow = _flow_ctx_out(self.node, port.name, True, scene_lib_out)
            port_item = PortGraphicsItem(self, port.name, False, output_index, is_flow=is_flow)
            port_item.setParentItem(self)
            port_y = output_start_y + output_index * ROW_HEIGHT + ROW_HEIGHT // 2
            port_item.setPos(self._rect.width() - 12, port_y)
            self._ports_out.append(port_item)
            if is_flow:
                self._flow_out = port_item

            from engine.configs.settings import settings as _settings_ui

            if getattr(_settings_ui, "GRAPH_UI_VERBOSE", False):
                print(
                    f"[端口布局] 节点[{self.node.title}]({self.node.id}) 输出端口: "
                    f"name='{port.name}', is_flow={is_flow}, "
                    f"pos=({self._rect.width() - 12}, {port_y})"
                )

            if is_multibranch_node and port.name not in ["流程出", "默认"]:
                edit_item = BranchPortValueEdit(self, port.name, self)
                edit_item.setVisible(False)
                port_name_width = fm_label.horizontalAdvance(port.name)
                edit_x = self._rect.width() - 30 - port_name_width - 70
                edit_y = output_start_y + output_index * ROW_HEIGHT + 2
                edit_item.setPos(edit_x, edit_y)
                self._constant_edits[f"_branch_port_{port.name}"] = edit_item

    def _update_edges_after_layout(self, edges_to_update: list[tuple]) -> None:
        """根据新的端口图形项，刷新所有相关连线的端点引用与路径。"""
        for (
            edge_item,
            is_src,
            src_port_name,
            is_dst,
            dst_port_name,
        ) in edges_to_update:
            if is_src and src_port_name:
                new_src_port = next(
                    (port for port in self._ports_out if port.name == src_port_name),
                    None,
                )
                if new_src_port:
                    edge_item.src = new_src_port
            if is_dst and dst_port_name:
                new_dst_port = next(
                    (port for port in self._ports_in if port.name == dst_port_name),
                    None,
                )
                if new_dst_port:
                    edge_item.dst = new_dst_port
            edge_item.update_path()

    def _layout_add_port_button(
        self,
        is_variadic_input_node: bool,
        header_height: float,
        total_input_rows: int,
    ) -> None:
        """为变参输入节点与多分支节点布局“+”端口按钮。"""
        from ui.dynamic_port_widget import AddPortButton

        scene_ref_for_plus = self.scene()
        is_read_only_scene = bool(
            scene_ref_for_plus
            and hasattr(scene_ref_for_plus, "read_only")
            and getattr(scene_ref_for_plus, "read_only")
        )

        if is_read_only_scene:
            if self._add_port_button is not None:
                if self._add_port_button.scene():
                    self.scene().removeItem(self._add_port_button)
                self._add_port_button = None
            return

        output_start_y = header_height + NODE_PADDING
        input_start_y = header_height + NODE_PADDING

        if self.node.title == "多分支":
            if self._add_port_button is None or getattr(
                self._add_port_button, "is_input", False
            ):
                self._add_port_button = AddPortButton(self, is_input=False)
            button_x = self._rect.width() - 12
            button_y = (
                output_start_y
                + len(self.node.outputs) * ROW_HEIGHT
                + ROW_HEIGHT // 2
            )
            self._add_port_button.setPos(button_x, button_y)
            from engine.configs.settings import settings as _settings_ui_button

            if getattr(_settings_ui_button, "GRAPH_UI_VERBOSE", False):
                print(
                    f"[端口布局] 多分支节点创建+按钮: pos=({button_x}, {button_y})"
                )
        elif is_variadic_input_node:
            if self._add_port_button is None or not getattr(
                self._add_port_button, "is_input", False
            ):
                self._add_port_button = AddPortButton(self, is_input=True)
            button_x = 12
            button_y = (
                input_start_y + total_input_rows * ROW_HEIGHT + ROW_HEIGHT // 2
            )
            self._add_port_button.setPos(button_x, button_y)
            from engine.configs.settings import settings as _settings_ui_button

            if getattr(_settings_ui_button, "GRAPH_UI_VERBOSE", False):
                print(
                    f"[端口布局] 可变输入节点({self.node.title})创建+按钮: "
                    f"render_inputs={len(getattr(self.node, 'inputs', []))}, "
                    f"pos=({button_x}, {button_y})"
                )
        else:
            if self._add_port_button is not None:
                if self._add_port_button.scene():
                    self.scene().removeItem(self._add_port_button)
                self._add_port_button = None

    def _layout_ports(self) -> None:
        self.prepareGeometryChange()
        edges_to_update = self._collect_edges_for_update()
        self._reset_ports_and_controls()

        connected_input_ports = self._collect_connected_input_ports()
        fm_label, fm_input = self._create_font_metrics()
        
        plan = build_input_port_layout_plan(self.node, connected_input_ports)
        is_multibranch_node = self.node.title == "多分支"
        is_variadic_input_node = bool(getattr(plan, "input_plus_rows", 0))
        width = self._compute_node_width(plan, fm_label)
        (
            rect,
            header_height,
            _content_height,
            _total_height,
            total_input_rows,
            _input_plus_rows,
            _output_plus_rows,
        ) = self._compute_node_rect_and_rows(plan, width, is_multibranch_node)
        self._rect = rect

        input_start_y = header_height + NODE_PADDING
        self._layout_input_ports_and_controls(
            plan,
            width,
            input_start_y,
            connected_input_ports,
            fm_label,
            fm_input,
        )
        self._layout_output_ports_and_branch_controls(header_height, fm_label)
        self._update_edges_after_layout(edges_to_update)
        self._layout_add_port_button(
            is_variadic_input_node,
            header_height,
            total_input_rows,
        )

    def boundingRect(self) -> QtCore.QRectF:
        return getattr(self, '_rect', QtCore.QRectF(0, 0, 280, 140))

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        r = self.boundingRect()
        header_h = ROW_HEIGHT + 10
        corner_radius = 12
        
        # 选中状态的高亮效果（使用主题主色系描边，与全局渐变高亮保持一致）
        if self.isSelected():
            glow_pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY))
            glow_pen.setWidth(4)
            painter.setPen(glow_pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)
        
        # 绘制标题栏背景（带圆角的顶部）
        # 创建标题栏路径 - 只在顶部有圆角
        title_path = QtGui.QPainterPath()
        
        # 从左下角开始
        title_path.moveTo(r.left(), r.top() + header_h)
        # 左边直线到圆角开始处
        title_path.lineTo(r.left(), r.top() + corner_radius)
        # 左上圆角 - 使用quadTo简化，避免arcTo在小尺寸下的问题
        title_path.quadTo(r.left(), r.top(), r.left() + corner_radius, r.top())
        # 顶边直线到右圆角
        title_path.lineTo(r.right() - corner_radius, r.top())
        # 右上圆角
        title_path.quadTo(r.right(), r.top(), r.right(), r.top() + corner_radius)
        # 右边直线到标题栏底部
        title_path.lineTo(r.right(), r.top() + header_h)
        # 封闭路径
        title_path.closeSubpath()
        
        # 使用渐变填充标题栏
        grad = QtGui.QLinearGradient(r.topLeft(), r.topRight())
        grad.setColorAt(0.0, self._category_color_start())
        grad.setColorAt(1.0, self._category_color_end())
        painter.fillPath(title_path, QtGui.QBrush(grad))
        
        # 绘制内容区域背景（70%不透明度，半透明有底色）
        content_rect = QtCore.QRectF(r.left(), r.top() + header_h, r.width(), r.height() - header_h)
        content_color = QtGui.QColor('#1F1F1F')
        content_color.setAlpha(int(255 * 0.7))  # 70%不透明度，半透明有底色
        painter.setBrush(content_color)
        pen = QtGui.QPen(
            QtGui.QColor('#3A3A3A')
            if not self.isSelected()
            else QtGui.QColor(Colors.PRIMARY)
        )
        pen.setWidth(2 if self.isSelected() else 1)
        painter.setPen(pen)
        
        # 绘制整体轮廓（圆角矩形）
        path = QtGui.QPainterPath()
        path.addRoundedRect(r, corner_radius, corner_radius)
        painter.drawPath(path)

        # title text
        painter.setFont(self.title_font)
        painter.setPen(QtGui.QColor('#FFFFFF'))
        
        # 如果是虚拟引脚节点，在标题前添加序号标记
        if self.node.is_virtual_pin:
            direction_symbol = "⬅️ " if self.node.is_virtual_pin_input else "➡️ "
            title_text = f"[{self.node.virtual_pin_index}] {direction_symbol}{self.node.title}"
        else:
            title_text = self.node.title
        
        # 定义标题区域用于绘制文本
        title_rect = QtCore.QRectF(r.left(), r.top(), r.width(), header_h)
        painter.drawText(title_rect.adjusted(12, 0, -12, 0), QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, title_text)

        # port labels (including flow ports) - 所有标签都使用亮色
        painter.setFont(QtGui.QFont('Microsoft YaHei', 9))
        painter.setPen(QtGui.QColor('#E0E0E0'))  # 统一使用亮色
        header_h = ROW_HEIGHT + 10
        
        # 检查哪些输入端口有连线
        connected_input_ports = set()
        if self.scene():
            for edge_item in self.scene().edge_items.values():
                if edge_item.dst.node_item == self:
                    connected_input_ports.add(edge_item.dst.name)
        
        # draw input port labels（使用真实行索引映射）
        input_start_y = header_h + NODE_PADDING
        for p in self.node.inputs:
            # 如果此端口未渲染（如变参占位），跳过
            if p.name not in self._input_row_index_map:
                continue
            row_index = self._input_row_index_map.get(p.name, 0)
            label_y = input_start_y + row_index * ROW_HEIGHT
            is_flow = p.name == '流程入' or '流程' in p.name.lower()
            has_connection = p.name in connected_input_ports
            
            # 输入标签：端口右侧开始，左对齐
            painter.setPen(QtGui.QColor('#E0E0E0'))  # 确保标签是亮色
            
            # 检查端口是否有控件，并获取控件信息
            has_control = p.name in self._control_positions
            
            # 标签在独立一行渲染，固定起点与宽度
            label_x = 30
            label_width = r.width() - 60
            
            # 绘制标签（使用clip确保不超出区域，避免遮挡控件）
            label_rect = QtCore.QRectF(label_x, label_y, label_width, ROW_HEIGHT)
            painter.save()
            painter.setClipRect(label_rect)  # 裁剪区域，防止文本溢出到控件
            painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, p.name)
            painter.restore()
            
            # 为文本类型的常量编辑框绘制背景（只为text类型绘制，bool和vector自带样式）
            if has_control:
                control_x, control_y, control_width, control_type = self._control_positions[p.name]
                if control_type == 'text':
                    # 文本输入框需要背景（控件在下一行，使用其自身位置）
                    const_rect = QtCore.QRectF(control_x, control_y + 2, control_width, ROW_HEIGHT - 8)
                    painter.fillRect(const_rect, QtGui.QColor('#2A2A2A'))
                    painter.setPen(QtGui.QColor('#444444'))
                    painter.drawRoundedRect(const_rect, 2, 2)
        
        # draw output port labels
        painter.setPen(QtGui.QColor('#E0E0E0'))  # 确保标签是亮色
        output_start_y = header_h + NODE_PADDING
        for out_index, p in enumerate(self.node.outputs):
            label_y = output_start_y + out_index * ROW_HEIGHT
            # 输出标签：端口左侧结束，右对齐（多分支分支口也绘制常规标签）
            painter.drawText(
                QtCore.QRectF(r.width() * 0.5, label_y, r.width() * 0.4, ROW_HEIGHT),
                QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight,
                p.name,
            )
        
        # 绘制验证警告（基于验证系统的结果）
        if self.scene() and hasattr(self.scene(), 'validation_issues'):
            issues = self.scene().validation_issues.get(self.node.id, [])
            for issue in issues:
                # 获取端口名称
                port_name = issue.detail.get("port_name") if hasattr(issue, 'detail') else None
                if port_name:
                    # 找到对应的输入端口索引
                    for p in self.node.inputs:
                        if p.name not in self._input_row_index_map:
                            continue
                        if p.name == port_name:
                            row_index = self._input_row_index_map.get(p.name, 0)
                            label_y = input_start_y + row_index * ROW_HEIGHT
                            
                            # 根据issue级别选择颜色
                            if hasattr(issue, 'level'):
                                if issue.level == "error":
                                    warning_color = QtGui.QColor('#FFD700')  # 金黄色
                                elif issue.level == "warning":
                                    warning_color = QtGui.QColor('#FFA500')  # 橙色
                                else:
                                    warning_color = QtGui.QColor('#87CEEB')  # 浅蓝色
                            else:
                                warning_color = QtGui.QColor('#FFD700')
                            
                            # 绘制警告感叹号（在输入框位置）
                            painter.setPen(warning_color)
                            painter.setFont(QtGui.QFont('Microsoft YaHei', 11, QtGui.QFont.Weight.Bold))
                            warning_rect = QtCore.QRectF(r.width() * 0.35, label_y, 20, ROW_HEIGHT)
                            painter.drawText(warning_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignCenter, "!")
                            painter.setFont(QtGui.QFont('Microsoft YaHei', 9))  # 恢复字体
                            break

    def _category_color_start(self) -> QtGui.QColor:
        cat = self.node.category
        
        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor('#AA55FF') if self.node.is_virtual_pin_input else QtGui.QColor('#55AAFF')
        
        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, 'composite_id') and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START)
        
        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            '查询': QtGui.QColor('#2D5FE3'),
            '查询节点': QtGui.QColor('#2D5FE3'),
            '事件': QtGui.QColor('#FF5E9C'),
            '事件节点': QtGui.QColor('#FF5E9C'),
            '运算': QtGui.QColor('#2FAACB'),
            '运算节点': QtGui.QColor('#2FAACB'),
            '执行': QtGui.QColor('#9CD64B'),
            '执行节点': QtGui.QColor('#9CD64B'),
            '流程控制': QtGui.QColor('#FF9955'),
            '流程控制节点': QtGui.QColor('#FF9955'),
            '复合': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
            '复合节点': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
        }
        return color_map.get(cat, QtGui.QColor('#555555'))

    def _category_color_end(self) -> QtGui.QColor:
        cat = self.node.category
        
        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor('#8833DD') if self.node.is_virtual_pin_input else QtGui.QColor('#3388DD')
        
        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, 'composite_id') and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END)
        
        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            '查询': QtGui.QColor('#1B3FA8'),
            '查询节点': QtGui.QColor('#1B3FA8'),
            '事件': QtGui.QColor('#C23A74'),
            '事件节点': QtGui.QColor('#C23A74'),
            '运算': QtGui.QColor('#1D6F8A'),
            '运算节点': QtGui.QColor('#1D6F8A'),
            '执行': QtGui.QColor('#6BA633'),
            '执行节点': QtGui.QColor('#6BA633'),
            '流程控制': QtGui.QColor('#E87722'),
            '流程控制节点': QtGui.QColor('#E87722'),
            '复合': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
            '复合节点': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
        }
        return color_map.get(cat, QtGui.QColor('#3A3A3A'))

