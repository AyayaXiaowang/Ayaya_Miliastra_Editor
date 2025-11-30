# -*- coding: utf-8 -*-
"""多分支节点的动态端口管理UI组件"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.nodes.port_name_rules import (
    map_index_to_range_instance,
    parse_range_definition,
)
from ui.foundation.dialog_utils import show_warning_dialog

if TYPE_CHECKING:
    from ui.graph.graph_scene import NodeGraphicsItem, GraphScene


class AddPortButton(QtWidgets.QGraphicsItem):
    """添加端口按钮
    
    - 输入模式（is_input=True）：为可变参数节点（如“拼装列表”）添加数据输入端口
    - 输出模式（is_input=False）：为多分支节点添加新的分支流程端口
    """
    
    def __init__(self, node_item: 'NodeGraphicsItem', is_input: bool = False):
        # QGraphicsItem 在 __init__ 过程中会调用 boundingRect，因此按 super() 之前就初始化几何相关字段
        self.button_size = 20
        self.is_hovered = False

        super().__init__(parent=node_item)
        self.node_item = node_item
        self.is_input = is_input
        self.setAcceptHoverEvents(True)
        self.setZValue(25)  # 比端口更高
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点击添加输入" if is_input else "点击添加新分支")
    
    def boundingRect(self) -> QtCore.QRectF:
        return QtCore.QRectF(
            -self.button_size / 2,
            -self.button_size / 2,
            self.button_size,
            self.button_size
        )
    
    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        # 绘制圆形按钮背景
        if self.is_hovered:
            painter.setBrush(QtGui.QColor('#5A9EFF'))
        else:
            painter.setBrush(QtGui.QColor('#4A8EEF'))
        
        painter.setPen(QtGui.QPen(QtGui.QColor('#FFFFFF'), 1))
        painter.drawEllipse(self.boundingRect())
        
        # 绘制"+"号
        painter.setPen(QtGui.QPen(QtGui.QColor('#FFFFFF'), 2))
        center_x = 0
        center_y = 0
        line_length = 6
        
        # 横线
        painter.drawLine(
            QtCore.QPointF(center_x - line_length, center_y),
            QtCore.QPointF(center_x + line_length, center_y)
        )
        # 竖线
        painter.drawLine(
            QtCore.QPointF(center_x, center_y - line_length),
            QtCore.QPointF(center_x, center_y + line_length)
        )
    
    def hoverEnterEvent(self, event) -> None:
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)
    
    def hoverLeaveEvent(self, event) -> None:
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            # 只读场景下禁用添加端口
            scene_ref = self.node_item.scene()
            is_read_only = bool(scene_ref and hasattr(scene_ref, 'read_only') and getattr(scene_ref, 'read_only'))
            if not is_read_only:
                if self.is_input:
                    self.add_input_port_auto()
                else:
                    self.add_branch_port_auto()
        super().mousePressEvent(event)
    
    def add_input_port_auto(self) -> None:
        """自动添加新的输入端口（用于可变参数节点）"""
        node = self.node_item.node
        scene = self.node_item.scene()

        if not isinstance(scene, QtWidgets.QGraphicsScene):
            return

        port_name = self._generate_dynamic_port_name(
            is_input=True,
            existing_names=[port_model.name for port_model in node.inputs],
        )
        self._add_port_via_command(scene, port_name, is_input=True)

    def add_branch_port_auto(self) -> None:
        """自动添加新的分支端口（不弹窗，直接创建）"""
        node = self.node_item.node
        scene = self.node_item.scene()
        
        if not isinstance(scene, QtWidgets.QGraphicsScene):
            return
        existing_ports = [p.name for p in node.outputs if p.name != "默认"]

        if self._has_string_branch(existing_ports):
            port_name = self._prompt_branch_value()
            if port_name is None:
                return
            if node.has_output_port(port_name):
                show_warning_dialog(self._dialog_parent(), "已存在", f"分支 '{port_name}' 已存在")
                return
            self._add_port_via_command(scene, port_name, is_input=False)
            return

        port_name = self._generate_dynamic_port_name(
            is_input=False,
            existing_names=existing_ports,
        )
        self._add_port_via_command(scene, port_name, is_input=False)

    def _add_port_via_command(self, scene: QtWidgets.QGraphicsScene, port_name: str, is_input: bool) -> None:
        from ui.graph.graph_undo import AddPortCommand
        from ui.graph.graph_scene import GraphScene

        if not isinstance(scene, GraphScene) or not scene.undo_manager:
            return

        command = AddPortCommand(
            scene.model,
            scene,
            self.node_item.node.id,
            port_name,
            is_input=is_input,
        )
        scene.undo_manager.execute_command(command)
        if hasattr(scene, "on_data_changed") and scene.on_data_changed:
            scene.on_data_changed()

    def _generate_dynamic_port_name(
        self,
        is_input: bool,
        existing_names: Sequence[str],
    ) -> str:
        node_def = self._get_node_definition()
        candidate = self._generate_from_node_definition(node_def, is_input, existing_names)
        if candidate:
            return candidate
        return self._generate_incremental_port_name(existing_names)

    def _generate_from_node_definition(
        self,
        node_def,
        is_input: bool,
        existing_names: Sequence[str],
    ) -> Optional[str]:
        if not node_def:
            return None
        defined_names = node_def.inputs if is_input else node_def.outputs
        existing_lookup = {name for name in existing_names}
        for defined_name in defined_names:
            parsed = parse_range_definition(str(defined_name))
            if not parsed:
                continue
            max_offset = parsed["end"] - parsed["start"]
            for offset in range(max_offset + 1):
                candidate = map_index_to_range_instance(str(defined_name), offset)
                if candidate and candidate not in existing_lookup:
                    return candidate
        return None

    def _generate_incremental_port_name(self, existing_names: Sequence[str]) -> str:
        numeric_values = [
            int(name) for name in existing_names if self._is_int_literal(name)
        ]
        next_value = (max(numeric_values) + 1) if numeric_values else 0
        return str(next_value)

    def _get_node_definition(self):
        scene = self.node_item.scene()
        if scene and hasattr(scene, "get_node_def"):
            return scene.get_node_def(self.node_item.node)
        return None

    @staticmethod
    def _is_int_literal(text: str) -> bool:
        stripped = text.strip()
        if stripped.startswith("-"):
            stripped = stripped[1:]
        return stripped.isdigit()

    def _has_string_branch(self, port_names: list[str]) -> bool:
        if not port_names:
            return False
        numeric_count = sum(1 for name in port_names if self._is_int_literal(name))
        return numeric_count != len(port_names)

    def _prompt_branch_value(self) -> Optional[str]:
        dlg = AddPortDialog(self.node_item)
        dlg.setWindowTitle("添加分支（字符串）")
        if dlg.exec():
            value = dlg.get_port_value()
            if not value:
                show_warning_dialog(self._dialog_parent(), "无效分支值", "请输入非空的字符串作为分支值")
                return None
            return value
        return None

    def _dialog_parent(self) -> Optional[QtWidgets.QWidget]:
        scene = self.node_item.scene()
        if isinstance(scene, QtWidgets.QGraphicsScene):
            views = scene.views()
            if views:
                return views[0]
        return None


class AddPortDialog(QtWidgets.QDialog):
    """添加端口对话框"""
    
    def __init__(self, node_item: 'NodeGraphicsItem'):
        super().__init__()
        self.node_item = node_item
        self.setWindowTitle("添加分支")
        self.setModal(True)
        self.setMinimumWidth(300)
        
        self.setup_ui()
    
    def setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        
        # 说明文本
        label = QtWidgets.QLabel("请输入新分支的匹配值（字符串或整数）：")
        layout.addWidget(label)
        
        # 输入框
        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setPlaceholderText("例如：字符串1 或 100")
        layout.addWidget(self.input_edit)
        
        # 按钮
        button_layout = QtWidgets.QHBoxLayout()
        self.ok_button = QtWidgets.QPushButton("确定")
        self.cancel_button = QtWidgets.QPushButton("取消")
        
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        layout.addLayout(button_layout)
    
    def get_port_value(self) -> str:
        """获取输入的端口值"""
        return self.input_edit.text().strip()


