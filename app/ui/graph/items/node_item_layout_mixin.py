"""NodeGraphicsItem：端口布局管线（拆分版）。"""

from __future__ import annotations

from typing import Any, cast

from PyQt6 import QtCore, QtGui

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph import graph_component_styles as graph_styles
from app.ui.graph.items.port_item import BranchPortValueEdit, PortGraphicsItem
from app.ui.graph.items.port_settings_button import PortSettingsButton
from app.ui.widgets.constant_editors import (
    ConstantBoolComboBox,
    ConstantTextEdit,
    ConstantVector3Edit,
    create_constant_editor_for_port,
    resolve_constant_display_for_port,
)
from engine.graph.common import is_selection_input_port
from engine.layout.utils.graph_query_utils import build_input_port_layout_plan

from app.ui.graph.items.node_item_constants import (
    NODE_PADDING,
    OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX,
    PORT_SETTINGS_BUTTON_MARGIN_PX,
    ROW_HEIGHT,
)


class NodePortLayoutMixin:
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

