from __future__ import annotations

import time

from PyQt6 import QtCore, QtGui, QtWidgets
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import Colors
from app.ui.graph.graph_palette import GraphPalette
from app.ui.graph import graph_component_styles as graph_styles
from app.ui.graph.items.port_item import PortGraphicsItem, BranchPortValueEdit
from app.ui.graph.items.port_settings_button import PortSettingsButton
from app.ui.widgets.constant_editors import (
    ConstantTextEdit,
    ConstantBoolComboBox,
    ConstantVector3Edit,
    create_constant_editor_for_port,
    resolve_constant_display_for_port,
)
from typing import Any, Optional, List, Dict, TYPE_CHECKING, cast
from engine.graph.models.graph_model import NodeModel
from engine.layout.internal.constants import UI_ROW_HEIGHT
from engine.layout.utils.graph_query_utils import build_input_port_layout_plan
from engine.graph.common import is_selection_input_port
from engine.configs.settings import settings

if TYPE_CHECKING:
    from app.ui.graph.graph_scene import GraphScene
    from app.ui.dynamic_port_widget import AddPortButton

NODE_PADDING = 10
ROW_HEIGHT = UI_ROW_HEIGHT
BRANCH_PLUS_EXTRA_ROWS = 1
PORT_SETTINGS_BUTTON_MARGIN_PX = 6
OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX = 30


class NodeGraphicsItem(QtWidgets.QGraphicsItem):
    def __init__(self, node: NodeModel):
        super().__init__()
        self.node = node
        self.title_font = ui_fonts.ui_font(11, bold=True)
        self._ports_in: List[PortGraphicsItem] = []
        self._ports_out: List[PortGraphicsItem] = []
        self._flow_in: Optional[PortGraphicsItem] = None
        self._flow_out: Optional[PortGraphicsItem] = None
        self._constant_edits: Dict[str, QtWidgets.QGraphicsItem] = {}  # 常量编辑框（可能是不同类型的控件）
        self._control_positions: Dict[str, tuple[float, float, float, str]] = {}  # {端口名: (x, y, width, type)} type可以是'text', 'bool', 'vector'
        # 行内常量控件（虚拟化占位渲染）缓存：
        # - 端口类型：用于按需 materialize editor 或绘制占位文本
        # - display/tooltip：与 ConstantTextEdit 的语义化展示口径对齐（变量名映射等）
        self._inline_constant_port_types: Dict[str, str] = {}
        self._inline_constant_display_text: Dict[str, str] = {}
        self._inline_constant_tooltips: Dict[str, str] = {}
        self._port_settings_buttons: list[PortSettingsButton] = []  # 端口旁边的“⚙查看类型”按钮
        # 输入端口所在的"标签行"索引映射（控件换行后，行索引不再等于端口序号）
        self._input_row_index_map: Dict[str, int] = {}
        self._add_port_button: Optional['AddPortButton'] = None  # 多分支节点的添加端口按钮
        # 节点拖拽开始标记：用于避免在 ItemPositionChange 频繁触发时重复记录起点。
        self._moving_started: bool = False
        # 画布搜索命中高亮（不影响选中态；用于 Ctrl+F 搜索结果批量标注）
        self._search_highlighted: bool = False
        # 给节点比连线更高的 z 值，让节点在连线上面
        self.setZValue(10)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        # 端口布局依赖 GraphScene 上下文（layout_registry_context / edge_items 等）。
        # QGraphicsItem 在未加入场景前 self.scene() 为 None，因此必须由 GraphScene.add_node_item()
        # 在 addItem(item) 之后触发一次布局。

    # === 搜索高亮（Ctrl+F） ===

    def set_search_highlighted(self, highlighted: bool) -> None:
        """设置“搜索命中”高亮描边（不改变选中状态）。"""
        new_state = bool(highlighted)
        if bool(getattr(self, "_search_highlighted", False)) == new_state:
            return
        self._search_highlighted = new_state
        self.update()

    def _paint_search_highlight_outline(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        *,
        corner_radius: float,
    ) -> None:
        """绘制搜索命中描边（仅对未选中节点生效）。"""
        if not bool(getattr(self, "_search_highlighted", False)):
            return
        if self.isSelected():
            return
        pen = QtGui.QPen(QtGui.QColor(Colors.INFO_LIGHT))
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            rect.adjusted(-2.0, -2.0, 2.0, 2.0),
            float(corner_radius + 2.0),
            float(corner_radius + 2.0),
        )
    
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
        # 统一走“有效类型解析”：与任务清单/端口类型气泡共用同一套规则来源。
        # 这样可以根除 `input_types/output_types`（常量字符串污染）导致的画布展示漂移。
        from app.ui.graph.items.port_type_resolver import resolve_effective_port_type_for_scene

        scene = self.scene()
        if scene is None:
            return "泛型"

        # 常量编辑控件只会出现在数据端口行，但这里仍显式传 is_flow=False 以保证口径一致。
        return resolve_effective_port_type_for_scene(
            scene,
            self.node,
            port_name,
            is_input=is_input,
            is_flow=False,
        )

    # === 行内常量控件虚拟化（占位绘制 + 按需创建控件） ===

    def _is_inline_constant_virtualization_active(self) -> bool:
        """当前节点是否启用“行内常量控件虚拟化”。

        约定：
        - 仅影响“行内常量编辑控件”的创建策略（占位绘制 vs QGraphicsProxyWidget/文本编辑控件）；
        - fast_preview_mode 下的“节点级展开”需要直接展示完整控件，因此在 fast_preview_mode 中关闭虚拟化。
        """
        scene = self.scene()
        if scene is not None and bool(getattr(scene, "fast_preview_mode", False)):
            return False
        return bool(getattr(settings, "GRAPH_CONSTANT_WIDGET_VIRTUALIZATION_ENABLED", True))

    def _update_inline_constant_display_cache_for_port(self, port_name: str) -> None:
        port_name_text = str(port_name or "").strip()
        if not port_name_text:
            return
        port_type = self._inline_constant_port_types.get(port_name_text) or self._get_port_type(port_name_text, True)
        self._inline_constant_port_types[port_name_text] = str(port_type or "")
        display_text, tooltip_text = resolve_constant_display_for_port(self, port_name_text, str(port_type or ""))
        self._inline_constant_display_text[port_name_text] = str(display_text or "")
        self._inline_constant_tooltips[port_name_text] = str(tooltip_text or "")

    def _inline_constant_rect_for_port(self, port_name: str) -> QtCore.QRectF | None:
        """返回端口对应的“常量控件占位区域”（item-local 坐标）。"""
        spec = self._control_positions.get(str(port_name or ""))
        if not spec:
            return None
        x, y, width, control_type = spec
        control_type_text = str(control_type or "")
        if control_type_text == "text":
            # 文本输入框：高度尽量接近行高，保留少量 padding
            text_box_height = max(20.0, float(ROW_HEIGHT) - 8.0)
            text_box_height = min(text_box_height, max(12.0, float(ROW_HEIGHT) - 2.0))
            return QtCore.QRectF(float(x), float(y) + 1.0, float(width), float(text_box_height))
        if control_type_text == "bool":
            height = float(max(getattr(graph_styles, "GRAPH_INLINE_BOOL_COMBO_MIN_HEIGHT_PX", 18), int(ROW_HEIGHT) - 6))
            return QtCore.QRectF(float(x), float(y), float(width), height)
        if control_type_text == "vector":
            height = float(getattr(graph_styles, "GRAPH_INLINE_VECTOR3_CONTAINER_HEIGHT_PX", int(ROW_HEIGHT) - 4))
            return QtCore.QRectF(float(x), float(y), float(width), height)
        return None

    def materialize_inline_constant_editor(
        self,
        port_name: str,
        *,
        focus: bool = True,
    ) -> QtWidgets.QGraphicsItem | None:
        """按需创建并挂载指定端口的真实常量编辑控件（若可用）。"""
        port_name_text = str(port_name or "").strip()
        if not port_name_text:
            return None
        # 已 materialize
        existing = self._constant_edits.get(port_name_text)
        if existing is not None:
            if focus:
                existing.setFocus()
            return existing

        spec = self._control_positions.get(port_name_text)
        if not spec:
            return None
        control_x, control_y, control_width, control_type = spec
        port_type = self._inline_constant_port_types.get(port_name_text) or self._get_port_type(port_name_text, True)
        self._inline_constant_port_types[port_name_text] = str(port_type or "")

        edit_item = create_constant_editor_for_port(self, port_name_text, str(port_type or ""), self)
        if edit_item is None:
            return None

        # 位置与尺寸：沿用 _layout_input_ports_and_controls 的既有策略
        if isinstance(edit_item, ConstantBoolComboBox):
            edit_item.setPos(float(control_x), float(control_y))
        elif isinstance(edit_item, ConstantVector3Edit):
            edit_item.setPos(float(control_x), float(control_y))
        elif isinstance(edit_item, ConstantTextEdit):
            edit_item.setPos(float(control_x), float(control_y) + 1.0)
            edit_item.setTextWidth(float(control_width))
        else:
            edit_item.setPos(float(control_x), float(control_y))

        # 只读会话：禁止修改但尽量允许选中复制（与 GraphScene.set_edit_session_capabilities 口径一致）
        scene_ref = self.scene()
        is_read_only_scene = bool(scene_ref is not None and getattr(scene_ref, "read_only", False))
        if is_read_only_scene:
            if isinstance(edit_item, ConstantTextEdit):
                edit_item.setTextInteractionFlags(
                    QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
                    | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
                )
            if hasattr(edit_item, "widget") and callable(getattr(edit_item, "widget")):
                embedded_widget = edit_item.widget()
                if isinstance(embedded_widget, QtWidgets.QWidget):
                    if isinstance(embedded_widget, QtWidgets.QLineEdit):
                        embedded_widget.setEnabled(True)
                        embedded_widget.setReadOnly(True)
                    elif isinstance(embedded_widget, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                        embedded_widget.setEnabled(True)
                        embedded_widget.setReadOnly(True)
                    elif isinstance(embedded_widget, QtWidgets.QComboBox):
                        embedded_widget.setEnabled(False)
                    else:
                        embedded_widget.setEnabled(True)
                        for line_edit in embedded_widget.findChildren(QtWidgets.QLineEdit):
                            line_edit.setEnabled(True)
                            line_edit.setReadOnly(True)
                        for text_edit in embedded_widget.findChildren(QtWidgets.QTextEdit):
                            text_edit.setEnabled(True)
                            text_edit.setReadOnly(True)
                        for plain_text_edit in embedded_widget.findChildren(QtWidgets.QPlainTextEdit):
                            plain_text_edit.setEnabled(True)
                            plain_text_edit.setReadOnly(True)
                        for combo in embedded_widget.findChildren(QtWidgets.QComboBox):
                            combo.setEnabled(False)

        self._constant_edits[port_name_text] = edit_item

        # 真实控件出现后，占位文本不再需要；但 tooltip 仍可复用（例如变量名映射时保留 var_xxx）
        tooltip_text = str(self._inline_constant_tooltips.get(port_name_text, "") or "")
        if tooltip_text:
            edit_item.setToolTip(tooltip_text)

        if focus:
            if isinstance(edit_item, ConstantBoolComboBox):
                edit_item.setFocus()
                combo = getattr(edit_item, "combo", None)
                if isinstance(combo, QtWidgets.QComboBox) and (not is_read_only_scene):
                    combo.showPopup()
            elif isinstance(edit_item, ConstantVector3Edit):
                edit_item.setFocus()
                x_container = getattr(edit_item, "x_edit", None)
                if isinstance(x_container, QtWidgets.QWidget):
                    x_line = x_container.findChild(QtWidgets.QLineEdit)
                    if isinstance(x_line, QtWidgets.QLineEdit):
                        x_line.setFocus()
                        x_line.selectAll()
            else:
                edit_item.setFocus()
        return edit_item

    def release_inline_constant_editor(self, port_name: str) -> None:
        """释放（销毁）指定端口的真实常量编辑控件，并恢复占位绘制。"""
        port_name_text = str(port_name or "").strip()
        if not port_name_text:
            return
        edit_item = self._constant_edits.get(port_name_text)
        if edit_item is None:
            return
        edit_item.setParentItem(None)
        self._constant_edits.pop(port_name_text, None)
        # 控件销毁后刷新占位文本缓存（布尔/向量等在编辑过程中可能写回过多次）
        self._update_inline_constant_display_cache_for_port(port_name_text)
        self.update()
    
    def itemChange(self, change, value):
        """节点位置/选中状态变化时的钩子。
        
        - 移动相关逻辑（模型更新、撤销命令、场景索引维护）统一委托给场景，
          避免视图对象直接操作 GraphScene 内部字段或 GraphModel。
        - 本类仅在合适的时机调用宿主场景提供的钩子方法：
          - on_node_item_position_change_started(node_item, old_pos)
          - on_node_item_position_changed(node_item, new_pos)
        """
        from app.ui.scene.interaction_mixin import SceneInteractionMixin
        # 当节点位置即将改变时，通知场景记录旧位置（用于撤销命令）
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            current_scene = self.scene()
            # Qt 可能在 QGraphicsItem 构造/挂载阶段提前触发 itemChange；
            # 此时 Python 侧字段尚未初始化完成，因此这里必须允许缺省为 False。
            moving_started = bool(getattr(self, "_moving_started", False))
            if current_scene and not moving_started:
                old_pos = self.pos()
                if isinstance(current_scene, SceneInteractionMixin):
                    current_scene.on_node_item_position_change_started(
                        self,
                        (old_pos.x(), old_pos.y()),
                    )
                self._moving_started = True  # 标记一次拖拽开始
        
        # 当节点位置已经改变时，仅通知场景刷新与该节点相连的连线
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            current_scene = self.scene()
            if isinstance(current_scene, SceneInteractionMixin):
                new_pos = self.pos()
                current_scene.on_node_item_position_changed(
                    self,
                    (new_pos.x(), new_pos.y()),
                )
        
        # 当选中状态改变时，触发重绘以更新高亮效果
        if change == QtWidgets.QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            self.update()
        
        return super().itemChange(change, value)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        """鼠标按下：在虚拟化开启时，允许点击常量占位区域按需创建真实控件。"""
        if event is None:
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            if self._is_inline_constant_virtualization_active() and self.isSelected():
                # LOD：低倍率缩放时不允许 materialize（此时常量控件/占位本应隐藏）
                if bool(getattr(settings, "GRAPH_LOD_ENABLED", True)):
                    scene_ref = self.scene()
                    scale_hint = float(getattr(scene_ref, "view_scale_hint", 1.0) or 1.0) if scene_ref is not None else 1.0
                    details_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
                    if scale_hint < details_min_scale:
                        super().mousePressEvent(event)
                        return
                pos = event.pos()
                for port_name in list(self._control_positions.keys()):
                    rect = self._inline_constant_rect_for_port(port_name)
                    if rect is not None and rect.contains(pos):
                        self.materialize_inline_constant_editor(str(port_name), focus=True)
                        event.accept()
                        return
        super().mousePressEvent(event)

    # === 端口布局管线（拆分版） ===

    def _collect_edges_for_update(self) -> list[tuple]:
        """收集与当前节点相关、需要在布局后刷新的连线项及其端口名。"""
        edges_to_update: list[tuple] = []
        scene_ref_for_edges = self.scene()
        if not scene_ref_for_edges:
            return edges_to_update
        from app.ui.graph.graph_scene import GraphScene
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
        for btn_item in self._port_settings_buttons:
            btn_item.setParentItem(None)
        self._ports_in.clear()
        self._ports_out.clear()
        self._constant_edits.clear()
        self._control_positions.clear()
        self._inline_constant_port_types.clear()
        self._inline_constant_display_text.clear()
        self._inline_constant_tooltips.clear()
        self._port_settings_buttons.clear()
        self._flow_in = None
        self._flow_out = None

    def _collect_connected_input_ports(self) -> set[str]:
        """收集所有已连线的输入端口名称，用于布局与行内编辑判定。"""
        connected_input_ports: set[str] = set()
        scene_ref = self.scene()
        if not scene_ref:
            return connected_input_ports
        # 性能关键：大图加载/渲染时不能对全图 edge_items 做 O(E) 扫描。
        # GraphScene 维护了“节点 -> 连线”的邻接索引（get_edges_for_node），可将复杂度降为 O(度数)。
        get_edges_for_node = getattr(scene_ref, "get_edges_for_node", None)
        if callable(get_edges_for_node):
            for edge_item in get_edges_for_node(self.node.id):
                if edge_item.dst.node_item == self:
                    connected_input_ports.add(edge_item.dst.name)

        # 批量边模式：edge_items 可能为空（无 per-edge item），需从模型边推导“已连线输入端口”。
        # 这里通过 GraphScene 提供的 batched 邻接索引（node -> edge_id）把复杂度收敛为 O(度数)。
        get_batched_edge_ids_for_node = getattr(scene_ref, "get_batched_edge_ids_for_node", None)
        model = getattr(scene_ref, "model", None)
        edges_map = getattr(model, "edges", None) if model is not None else None
        if callable(get_batched_edge_ids_for_node) and isinstance(edges_map, dict):
            from engine.graph.common import FLOW_IN_PORT_NAMES, FLOW_PORT_PLACEHOLDER

            node_id_text = str(getattr(self.node, "id", "") or "")
            for edge_id in set(get_batched_edge_ids_for_node(node_id_text) or set()):
                edge_model = edges_map.get(str(edge_id))
                if edge_model is None:
                    continue
                if str(getattr(edge_model, "dst_node", "") or "") != node_id_text:
                    continue
                dst_port_name = str(getattr(edge_model, "dst_port", "") or "")
                if dst_port_name == FLOW_PORT_PLACEHOLDER:
                    dst_port_name = str(FLOW_IN_PORT_NAMES[0])
                if dst_port_name:
                    connected_input_ports.add(dst_port_name)
            return connected_input_ports

        # 兼容：若 scene 不是 GraphScene（或缺少邻接索引实现），回退到全量扫描。
        scene_any = cast(Any, scene_ref)
        for edge_item in scene_any.edge_items.values():
            if edge_item.dst.node_item == self:
                connected_input_ports.add(edge_item.dst.name)
        return connected_input_ports

    def _create_font_metrics(self) -> tuple[QtGui.QFontMetrics, QtGui.QFontMetrics]:
        """构造标签与输入文本的字体度量，用于宽度估算。"""
        label_font = ui_fonts.ui_font(9)
        input_font = ui_fonts.monospace_font(8)
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

            scene_ref = self.scene()
            scene_any = cast(Any, scene_ref)
            scene_library = getattr(scene_any, "node_library", None)
            is_flow = _flow_ctx_with_lib(self.node, port_name, False, scene_library)
            # 选择端口：不可连线，仅保留行内输入控件
            is_select_input = (not is_flow) and is_selection_input_port(self.node, port_name)

            row_index = plan.row_index_by_port.get(port_name, input_index)
            port_y = input_start_y + row_index * ROW_HEIGHT + ROW_HEIGHT // 2

            # 端口“⚙查看类型”按钮：放在端口标签右侧（但限制在左半区，避免遮挡右侧输出标签）
            label_x = 30
            btn_half = PortSettingsButton.DEFAULT_SIZE_PX / 2
            text_width = float(fm_label.horizontalAdvance(str(port_name)))
            btn_x = float(label_x) + text_width + float(PORT_SETTINGS_BUTTON_MARGIN_PX) + float(btn_half)
            max_btn_x = float(width) * 0.5 - float(btn_half) - float(PORT_SETTINGS_BUTTON_MARGIN_PX)
            btn_x = min(btn_x, max_btn_x)
            settings_button = PortSettingsButton(
                self,
                port_name,
                is_input=True,
                is_flow=is_flow,
            )
            settings_button.setParentItem(self)
            settings_button.setPos(btn_x, port_y)
            self._port_settings_buttons.append(settings_button)

            if not is_select_input:
                port_item = PortGraphicsItem(self, port_name, True, input_index, is_flow=is_flow)
                port_item.setParentItem(self)
                port_item.setPos(12, port_y)
                self._ports_in.append(port_item)
                # 关键：`_flow_in` 仅代表名为“流程入”的主流程入口端口。
                # 像“有限循环”这类节点同时包含“流程入/跳出循环”两个流程输入口时，
                # 不能让后者覆盖 `_flow_in`，否则会导致按“流程入”查找/高亮时指向错误端口。
                if is_flow and port_name == "流程入":
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
            # 控件行的上下留白主要来自这里的偏移 + 行高本身。
            # 将偏移缩小一半（2px → 1px），配合更紧凑的 UI_ROW_HEIGHT，
            # 实现“控件上下间距缩短约 50%”，而不是把输入框本体压扁。
            control_y = input_start_y + control_row_index * ROW_HEIGHT + 1
            
            port_type = self._get_port_type(port_name, is_input=True)
            port_type_text = str(port_type or "")
            # “实体/结构体”属于引用/复合数据：只允许连线，不提供行内常量编辑（与 create_constant_editor_for_port 口径一致）
            if port_type_text == "实体" or port_type_text.startswith("结构体"):
                continue

            # 缓存端口类型与展示文本：供占位绘制/按需 materialize 使用
            self._inline_constant_port_types[port_name] = port_type_text

            # 兼容历史行为：部分控件在构造时会“补齐默认常量值”（例如布尔/向量），虚拟化时也需要保持一致。
            if port_type_text == "布尔值" and port_name not in self.node.input_constants:
                self.node.input_constants[port_name] = False
            if port_type_text == "三维向量" and port_name not in self.node.input_constants:
                self.node.input_constants[port_name] = "0, 0, 0"

            display_text, tooltip_text = resolve_constant_display_for_port(self, port_name, port_type_text)
            self._inline_constant_display_text[port_name] = str(display_text or "")
            self._inline_constant_tooltips[port_name] = str(tooltip_text or "")

            # 根据端口类型记录控件占位位置（不依赖真实控件是否创建）
            if port_type_text == "布尔值":
                self._control_positions[port_name] = (
                    control_x,
                    control_y,
                    graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX,
                    "bool",
                )
            elif port_type_text == "三维向量":
                self._control_positions[port_name] = (
                    control_x,
                    control_y,
                    graph_styles.GRAPH_INLINE_VECTOR3_CONTAINER_WIDTH_PX,
                    "vector",
                )
            else:
                # 限制宽度为节点宽度的一半左右，避免覆盖右侧输出端口标签
                max_text_width = width * 0.5 - control_x
                text_width = max(60, max_text_width)
                self._control_positions[port_name] = (
                    control_x,
                    control_y,
                    text_width,
                    "text",
                )

            # 虚拟化开启：默认仅绘制占位外观，不创建真实控件（用户交互时再 materialize）
            if self._is_inline_constant_virtualization_active():
                continue

            edit_item = create_constant_editor_for_port(self, port_name, port_type_text, self)
            if edit_item is None:
                continue

            # 根据控件类型设置布局
            if isinstance(edit_item, ConstantBoolComboBox):
                edit_item.setPos(control_x, control_y)
            elif isinstance(edit_item, ConstantVector3Edit):
                edit_item.setPos(control_x, control_y)
            elif isinstance(edit_item, ConstantTextEdit):
                edit_item.setPos(control_x, control_y + 1)
                control_spec = self._control_positions.get(port_name)
                if control_spec is not None:
                    edit_item.setTextWidth(float(control_spec[2]))
            else:
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

            scene_ref = self.scene()
            scene_any = cast(Any, scene_ref)
            scene_lib_out = getattr(scene_any, "node_library", None)
            is_flow = _flow_ctx_out(self.node, port.name, True, scene_lib_out)
            port_item = PortGraphicsItem(self, port.name, False, output_index, is_flow=is_flow)
            port_item.setParentItem(self)
            port_y = output_start_y + output_index * ROW_HEIGHT + ROW_HEIGHT // 2
            port_item.setPos(self._rect.width() - 12, port_y)
            self._ports_out.append(port_item)
            # `_flow_out` 同理：仅代表名为“流程出”的主流程出口端口，避免被其它流程输出口覆盖。
            if is_flow and port.name == "流程出":
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
                edit_y = output_start_y + output_index * ROW_HEIGHT + 1
                edit_item.setPos(edit_x, edit_y)
                self._constant_edits[f"_branch_port_{port.name}"] = edit_item

            # 端口“⚙查看类型”按钮：放在右侧端口圆点左侧
            btn_x = float(self._rect.width()) - float(OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX)
            settings_button = PortSettingsButton(
                self,
                port.name,
                is_input=False,
                is_flow=is_flow,
            )
            settings_button.setParentItem(self)
            settings_button.setPos(btn_x, port_y)
            self._port_settings_buttons.append(settings_button)

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

        # 批量边模式：端口布局可能改变节点尺寸，需要刷新批量边几何（以免边仍连到旧矩形位置）
        scene_ref = self.scene()
        update_batched = getattr(scene_ref, "update_batched_edges_for_node_ids", None) if scene_ref is not None else None
        if callable(update_batched):
            node_id_text = str(getattr(self.node, "id", "") or "")
            if node_id_text:
                update_batched([node_id_text])

    def _layout_add_port_button(
        self,
        is_variadic_input_node: bool,
        header_height: float,
        total_input_rows: int,
    ) -> None:
        """为变参输入节点与多分支节点布局“+”端口按钮。"""
        from app.ui.dynamic_port_widget import AddPortButton

        scene_ref_for_plus = self.scene()
        is_read_only_scene = bool(
            scene_ref_for_plus
            and hasattr(scene_ref_for_plus, "read_only")
            and getattr(scene_ref_for_plus, "read_only")
        )

        if is_read_only_scene:
            if self._add_port_button is not None:
                button_scene = self._add_port_button.scene()
                if button_scene is not None:
                    button_scene.removeItem(self._add_port_button)
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
                button_scene = self._add_port_button.scene()
                if button_scene is not None:
                    button_scene.removeItem(self._add_port_button)
                self._add_port_button = None

    def _layout_ports(self) -> None:
        self.prepareGeometryChange()
        edges_to_update = self._collect_edges_for_update()
        self._reset_ports_and_controls()

        connected_input_ports = self._collect_connected_input_ports()
        fm_label, fm_input = self._create_font_metrics()

        scene_ref = self.scene()
        registry_context = getattr(scene_ref, "layout_registry_context", None) if scene_ref is not None else None
        if registry_context is None:
            raise RuntimeError(
                "NodeGraphicsItem 无法获取 layout_registry_context。"
                "请确保 GraphScene 在初始化时已创建 LayoutRegistryContext（依赖 settings.set_config_path(...)）。"
            )
        plan = build_input_port_layout_plan(
            self.node,
            connected_input_ports,
            registry_context=registry_context,
        )
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

        # basic blocks 背景：端口布局会改变节点尺寸（例如“拼装列表”等可变高度节点），
        # 需要通知场景在下一次背景绘制时重算所属 basic block 的包围矩形。
        scene_ref = self.scene()
        mark_dirty = getattr(scene_ref, "mark_basic_block_rect_dirty_for_node", None) if scene_ref is not None else None
        if callable(mark_dirty):
            mark_dirty(str(getattr(self.node, "id", "") or ""))

    def boundingRect(self) -> QtCore.QRectF:
        return getattr(self, '_rect', QtCore.QRectF(0, 0, 280, 140))

    def paint(self, painter: QtGui.QPainter | None, option, widget=None) -> None:
        if painter is None:
            return

        scene_ref_for_perf = self.scene()
        monitor = getattr(scene_ref_for_perf, "_perf_monitor", None) if scene_ref_for_perf is not None else None
        inc = getattr(monitor, "inc", None) if monitor is not None else None
        accum = getattr(monitor, "accum_ns", None) if monitor is not None else None
        track = getattr(monitor, "track_slowest", None) if monitor is not None else None
        t_total0 = time.perf_counter_ns() if monitor is not None else 0
        if callable(inc):
            inc("items.paint.node.calls", 1)

        r = self.boundingRect()
        header_h = ROW_HEIGHT + 10
        corner_radius = 12

        # === 缩放分级渲染（LOD）：低倍率下跳过高成本细节绘制 ===
        lod_enabled = bool(getattr(settings, "GRAPH_LOD_ENABLED", True))
        details_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_DETAILS_MIN_SCALE", 0.55))
        lod_scale = 1.0
        if lod_enabled:
            if option is not None and hasattr(option, "levelOfDetailFromTransform"):
                lod_scale = float(option.levelOfDetailFromTransform(painter.worldTransform()))
            else:
                lod_scale = float(painter.worldTransform().m11())
        low_detail = bool(lod_enabled and (lod_scale < details_min_scale))
        title_min_scale = float(getattr(settings, "GRAPH_LOD_NODE_TITLE_MIN_SCALE", 0.28))
        show_title_text = True
        if lod_enabled and (lod_scale < title_min_scale):
            # 低倍率下标题文字通常不可读且绘制成本很高；仅对“选中/搜索命中”的节点保留文字。
            show_title_text = bool(self.isSelected() or getattr(self, "_search_highlighted", False))

        # 搜索命中描边：在选中高亮之前绘制，且选中态下不重复叠加
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            self._paint_search_highlight_outline(painter, r, corner_radius=float(corner_radius))
            accum("items.paint.node.search_outline", int(time.perf_counter_ns() - int(t0)))
        else:
            self._paint_search_highlight_outline(painter, r, corner_radius=float(corner_radius))
        
        # 选中状态的高亮效果（使用主题主色系描边，与全局渐变高亮保持一致）
        if self.isSelected():
            if monitor is not None and callable(accum):
                t0 = time.perf_counter_ns()
                glow_pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY))
                glow_pen.setWidth(4)
                painter.setPen(glow_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)
                accum("items.paint.node.selection_glow", int(time.perf_counter_ns() - int(t0)))
            else:
                glow_pen = QtGui.QPen(QtGui.QColor(Colors.PRIMARY))
                glow_pen.setWidth(4)
                painter.setPen(glow_pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 14, 14)
        
        # 绘制标题栏背景（带圆角的顶部）
        # 创建标题栏路径 - 只在顶部有圆角
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
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
            accum("items.paint.node.title_path", int(time.perf_counter_ns() - int(t0)))
        else:
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
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            grad = QtGui.QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, self._category_color_start())
            grad.setColorAt(1.0, self._category_color_end())
            painter.fillPath(title_path, QtGui.QBrush(grad))
            accum("items.paint.node.title_gradient", int(time.perf_counter_ns() - int(t0)))
        else:
            grad = QtGui.QLinearGradient(r.topLeft(), r.topRight())
            grad.setColorAt(0.0, self._category_color_start())
            grad.setColorAt(1.0, self._category_color_end())
            painter.fillPath(title_path, QtGui.QBrush(grad))

        # 节点内容区背景不透明度（由设置面板控制；默认 70% 与当前观感一致）
        node_content_alpha = float(getattr(settings, "GRAPH_NODE_CONTENT_ALPHA", 0.7))

        # 兼容既有观感：标题栏当前有一层“暗底覆罩”让渐变更柔和；
        # 为避免用户将不透明度调到 100% 时把标题渐变完全盖掉，这里将标题覆罩上限固定为 70%。
        header_overlay_alpha = min(float(node_content_alpha), 0.7)
        header_overlay_color = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        header_overlay_color.setAlpha(int(255 * header_overlay_alpha))
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            painter.fillPath(title_path, QtGui.QBrush(header_overlay_color))
            accum("items.paint.node.title_overlay", int(time.perf_counter_ns() - int(t0)))
        else:
            painter.fillPath(title_path, QtGui.QBrush(header_overlay_color))

        # 内容区填充：只对 header 以下区域生效，避免覆盖标题栏的类别渐变
        content_rect = QtCore.QRectF(
            r.left(),
            r.top() + header_h,
            r.width(),
            r.height() - header_h,
        )
        content_color = QtGui.QColor(GraphPalette.NODE_CONTENT_BG)
        content_color.setAlpha(int(255 * node_content_alpha))

        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            node_path = QtGui.QPainterPath()
            node_path.addRoundedRect(r, corner_radius, corner_radius)
            painter.save()
            painter.setClipRect(content_rect)
            painter.fillPath(node_path, QtGui.QBrush(content_color))
            painter.restore()
            accum("items.paint.node.content_fill", int(time.perf_counter_ns() - int(t0)))
        else:
            node_path = QtGui.QPainterPath()
            node_path.addRoundedRect(r, corner_radius, corner_radius)
            painter.save()
            painter.setClipRect(content_rect)
            painter.fillPath(node_path, QtGui.QBrush(content_color))
            painter.restore()

        # 绘制整体轮廓（圆角矩形描边）
        pen_color = (
            QtGui.QColor(Colors.PRIMARY)
            if self.isSelected()
            else QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER)
        )
        if monitor is not None and callable(accum):
            t0 = time.perf_counter_ns()
            pen = QtGui.QPen(pen_color)
            pen.setWidth(2 if self.isSelected() else 1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(node_path)
            accum("items.paint.node.outline", int(time.perf_counter_ns() - int(t0)))
        else:
            pen = QtGui.QPen(pen_color)
            pen.setWidth(2 if self.isSelected() else 1)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(node_path)

        # title text
        if show_title_text:
            if monitor is not None and callable(accum):
                t0 = time.perf_counter_ns()
            painter.setFont(self.title_font)
            painter.setPen(QtGui.QColor(GraphPalette.TEXT_BRIGHT))
            
            # 如果是虚拟引脚节点，在标题前添加序号标记
            if self.node.is_virtual_pin:
                direction_symbol = "⬅️ " if self.node.is_virtual_pin_input else "➡️ "
                title_text = f"[{self.node.virtual_pin_index}] {direction_symbol}{self.node.title}"
            else:
                title_text = self.node.title
            
            # 定义标题区域用于绘制文本
            title_rect = QtCore.QRectF(r.left(), r.top(), r.width(), header_h)
            painter.drawText(
                title_rect.adjusted(12, 0, -12, 0),
                QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                title_text,
            )
            if monitor is not None and callable(accum):
                accum("items.paint.node.title_text", int(time.perf_counter_ns() - int(t0)))

        # LOD：低倍率下仅保留“标题栏颜色 + 标题文本 + 节点框”，其它细节（端口/常量/验证图标等）全部跳过
        if low_detail:
            if monitor is not None and callable(accum):
                dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
                accum("items.paint.node.total", dt_total_ns)
                if callable(track):
                    track(f"node:{getattr(self.node, 'id', '')}", dt_total_ns)
            return

        # port labels (including flow ports) - 所有标签都使用亮色
        t_ports0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        painter.setFont(ui_fonts.ui_font(9))
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 统一使用亮色
        header_h = ROW_HEIGHT + 10
        
        # draw input port labels（使用真实行索引映射）
        input_start_y = header_h + NODE_PADDING
        fm_label = painter.fontMetrics()
        btn_half = PortSettingsButton.DEFAULT_SIZE_PX / 2
        for p in self.node.inputs:
            # 如果此端口未渲染（如变参占位），跳过
            if p.name not in self._input_row_index_map:
                continue
            row_index = self._input_row_index_map.get(p.name, 0)
            label_y = input_start_y + row_index * ROW_HEIGHT
            
            # 输入标签：端口右侧开始，左对齐
            painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 确保标签是亮色
            
            # 检查端口是否有控件，并获取控件信息
            has_control = p.name in self._control_positions
            
            # 标签在独立一行渲染，固定起点与宽度
            label_x = 30
            label_width = r.width() - 60

            # 预留“⚙”按钮区域，避免标签文本覆盖按钮（与布局阶段的按钮定位保持同一规则）
            text_width = float(fm_label.horizontalAdvance(str(p.name)))
            btn_x = float(label_x) + text_width + float(PORT_SETTINGS_BUTTON_MARGIN_PX) + float(btn_half)
            max_btn_x = float(r.width()) * 0.5 - float(btn_half) - float(PORT_SETTINGS_BUTTON_MARGIN_PX)
            btn_x = min(btn_x, max_btn_x)
            label_right_edge = min(float(label_x + label_width), float(btn_x - btn_half - 2.0))
            label_width = max(0.0, label_right_edge - float(label_x))
            
            # 绘制标签（使用clip确保不超出区域，避免遮挡控件）
            label_rect = QtCore.QRectF(label_x, label_y, label_width, ROW_HEIGHT)
            painter.save()
            painter.setClipRect(label_rect)  # 裁剪区域，防止文本溢出到控件
            painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, p.name)
            painter.restore()
            
            # 为文本类型的常量编辑框绘制背景（只为text类型绘制，bool和vector自带样式）
            if has_control:
                control_x, control_y, control_width, control_type = self._control_positions[p.name]
                control_type_text = str(control_type or "")
                placeholder_rect = self._inline_constant_rect_for_port(p.name)
                if placeholder_rect is None:
                    continue

                is_materialized = p.name in self._constant_edits
                display_text = str(self._inline_constant_display_text.get(p.name, "") or "")

                if control_type_text == "text":
                    # 文本输入框背景：无论是否 materialize，都由节点自绘（ConstantTextEdit 本身无底色）
                    painter.fillRect(placeholder_rect, QtGui.QColor(GraphPalette.INPUT_BG))
                    painter.setPen(QtGui.QColor(GraphPalette.BORDER_SUBTLE))
                    painter.drawRoundedRect(placeholder_rect, 2, 2)

                    # 占位文本：仅在未创建真实控件时绘制（避免与 ConstantTextEdit 重叠）
                    if (not is_materialized) and display_text:
                        painter.save()
                        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
                        painter.setFont(ui_fonts.monospace_font(8))
                        inner = placeholder_rect.adjusted(4.0, 0.0, -4.0, 0.0)
                        painter.setClipRect(inner)
                        fm = QtGui.QFontMetrics(painter.font())
                        elided = fm.elidedText(
                            display_text,
                            QtCore.Qt.TextElideMode.ElideRight,
                            max(0, int(inner.width())),
                        )
                        painter.drawText(
                            inner,
                            QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                            elided,
                        )
                        painter.restore()
                else:
                    # bool/vector：占位绘制（真实控件不存在时）
                    if is_materialized:
                        continue
                    painter.save()
                    painter.fillRect(placeholder_rect, QtGui.QColor(GraphPalette.INPUT_BG))
                    painter.setPen(QtGui.QColor(GraphPalette.BORDER_SUBTLE))
                    painter.drawRoundedRect(placeholder_rect, 2, 2)
                    painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))
                    painter.setFont(ui_fonts.monospace_font(8))
                    inner = placeholder_rect.adjusted(4.0, 0.0, -4.0, 0.0)
                    painter.setClipRect(inner)
                    fm = QtGui.QFontMetrics(painter.font())
                    elided = fm.elidedText(
                        display_text,
                        QtCore.Qt.TextElideMode.ElideRight,
                        max(0, int(inner.width())),
                    )
                    align = (
                        QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignCenter
                        if control_type_text == "bool"
                        else QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft
                    )
                    painter.drawText(inner, align, elided)
                    painter.restore()
        
        # draw output port labels
        painter.setPen(QtGui.QColor(GraphPalette.TEXT_LABEL))  # 确保标签是亮色
        output_start_y = header_h + NODE_PADDING
        for out_index, p in enumerate(self.node.outputs):
            label_y = output_start_y + out_index * ROW_HEIGHT
            # 输出标签：端口左侧结束，右对齐（多分支分支口也绘制常规标签）
            btn_half = PortSettingsButton.DEFAULT_SIZE_PX / 2
            btn_left = float(r.width()) - float(OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX) - float(btn_half)
            label_right_edge = float(btn_left) - 6.0
            label_left = float(r.width()) * 0.5
            label_width = max(0.0, label_right_edge - label_left)
            painter.drawText(
                QtCore.QRectF(label_left, label_y, label_width, ROW_HEIGHT),
                QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight,
                p.name,
            )
        if monitor is not None and callable(accum):
            accum("items.paint.node.port_labels", int(time.perf_counter_ns() - int(t_ports0)))
        
        # 绘制验证警告（基于验证系统的结果）
        t_val0 = time.perf_counter_ns() if monitor is not None and callable(accum) else 0
        scene_ref_for_validation = self.scene()
        scene_any = cast(Any, scene_ref_for_validation)
        validation_issues = getattr(scene_any, "validation_issues", None)
        if validation_issues is not None:
            issues = validation_issues.get(self.node.id, [])
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
                                    warning_color = QtGui.QColor(GraphPalette.WARN_GOLD)  # 金黄色
                                elif issue.level == "warning":
                                    warning_color = QtGui.QColor(GraphPalette.WARN_ORANGE)  # 橙色
                                else:
                                    warning_color = QtGui.QColor(GraphPalette.INFO_SKY)  # 浅蓝色
                            else:
                                warning_color = QtGui.QColor(GraphPalette.WARN_GOLD)
                            
                            # 绘制警告感叹号（在输入框位置）
                            painter.setPen(warning_color)
                            painter.setFont(ui_fonts.ui_font(11, bold=True))
                            warning_rect = QtCore.QRectF(r.width() * 0.35, label_y, 20, ROW_HEIGHT)
                            painter.drawText(warning_rect, QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignCenter, "!")
                            painter.setFont(ui_fonts.ui_font(9))  # 恢复字体
                            break
        if monitor is not None and callable(accum):
            accum("items.paint.node.validation", int(time.perf_counter_ns() - int(t_val0)))

        if monitor is not None and callable(accum):
            dt_total_ns = int(time.perf_counter_ns() - int(t_total0))
            accum("items.paint.node.total", dt_total_ns)
            if callable(track):
                track(f"node:{getattr(self.node, 'id', '')}", dt_total_ns)

    def _category_color_start(self) -> QtGui.QColor:
        cat = self.node.category
        
        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_IN) if self.node.is_virtual_pin_input else QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_OUT)
        
        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, 'composite_id') and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START)
        
        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            '查询': QtGui.QColor(GraphPalette.CATEGORY_QUERY),
            '查询节点': QtGui.QColor(GraphPalette.CATEGORY_QUERY),
            '事件': QtGui.QColor(GraphPalette.CATEGORY_EVENT),
            '事件节点': QtGui.QColor(GraphPalette.CATEGORY_EVENT),
            '运算': QtGui.QColor(GraphPalette.CATEGORY_COMPUTE),
            '运算节点': QtGui.QColor(GraphPalette.CATEGORY_COMPUTE),
            '执行': QtGui.QColor(GraphPalette.CATEGORY_EXECUTION),
            '执行节点': QtGui.QColor(GraphPalette.CATEGORY_EXECUTION),
            '流程控制': QtGui.QColor(GraphPalette.CATEGORY_FLOW),
            '流程控制节点': QtGui.QColor(GraphPalette.CATEGORY_FLOW),
            '复合': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
            '复合节点': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_START),
        }
        return color_map.get(cat, QtGui.QColor(GraphPalette.CATEGORY_DEFAULT))

    def _category_color_end(self) -> QtGui.QColor:
        cat = self.node.category
        
        # 虚拟引脚节点使用特殊颜色
        if self.node.is_virtual_pin:
            return QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_IN_DARK) if self.node.is_virtual_pin_input else QtGui.QColor(GraphPalette.CATEGORY_VIRTUAL_OUT_DARK)
        
        # 复合节点使用集中管理的银白渐变色（优先于category判断）
        if hasattr(self.node, 'composite_id') and self.node.composite_id:
            return QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END)
        
        # 支持简化版（"事件"）和完整版（"事件节点"）
        color_map = {
            '查询': QtGui.QColor(GraphPalette.CATEGORY_QUERY_DARK),
            '查询节点': QtGui.QColor(GraphPalette.CATEGORY_QUERY_DARK),
            '事件': QtGui.QColor(GraphPalette.CATEGORY_EVENT_DARK),
            '事件节点': QtGui.QColor(GraphPalette.CATEGORY_EVENT_DARK),
            '运算': QtGui.QColor(GraphPalette.CATEGORY_COMPUTE_DARK),
            '运算节点': QtGui.QColor(GraphPalette.CATEGORY_COMPUTE_DARK),
            '执行': QtGui.QColor(GraphPalette.CATEGORY_EXECUTION_DARK),
            '执行节点': QtGui.QColor(GraphPalette.CATEGORY_EXECUTION_DARK),
            '流程控制': QtGui.QColor(GraphPalette.CATEGORY_FLOW_DARK),
            '流程控制节点': QtGui.QColor(GraphPalette.CATEGORY_FLOW_DARK),
            '复合': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
            '复合节点': QtGui.QColor(Colors.NODE_HEADER_COMPOSITE_END),
        }
        return color_map.get(cat, QtGui.QColor(GraphPalette.NODE_CONTENT_BORDER))

