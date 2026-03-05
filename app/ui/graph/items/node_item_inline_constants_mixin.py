"""NodeGraphicsItem：行内常量控件虚拟化（占位绘制 + 按需创建控件）。"""

from __future__ import annotations

from typing import Any, cast

from PyQt6 import QtCore, QtWidgets

from app.ui.graph import graph_component_styles as graph_styles
from app.ui.widgets.constant_editors import (
    ConstantBoolComboBox,
    ConstantTextEdit,
    ConstantVector3Edit,
    create_constant_editor_for_port,
    resolve_constant_display_for_port,
)
from engine.configs.settings import settings

from app.ui.graph.items.node_item_constants import ROW_HEIGHT


class NodeInlineConstantsMixin:
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

