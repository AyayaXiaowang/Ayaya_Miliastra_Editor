# -*- coding: utf-8 -*-
"""多分支节点的动态端口管理UI组件"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from engine.nodes.port_name_rules import (
    map_index_to_range_instance,
    parse_range_definition,
)
from ui.foundation.base_widgets import BaseDialog
from ui.foundation.dialog_utils import show_warning_dialog
from ui.foundation.theme_manager import Colors, ThemeManager

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
            painter.setBrush(QtGui.QColor(Colors.PRIMARY))
        else:
            painter.setBrush(QtGui.QColor(Colors.PRIMARY_DARK))
        
        painter.setPen(QtGui.QPen(QtGui.QColor(Colors.TEXT_ON_PRIMARY), 1))
        painter.drawEllipse(self.boundingRect())
        
        # 绘制"+"号
        painter.setPen(QtGui.QPen(QtGui.QColor(Colors.TEXT_ON_PRIMARY), 2))
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

        # 1) 优先尝试“字典键值对”模式：一次点击同时新增一对 (键N, 值N)
        if self._try_add_dict_key_value_pair(scene):
            return

        # 2) 通用变参模式：按节点定义中的范围端口依次补齐（如 0,1,2,...）
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

    def _try_add_dict_key_value_pair(self, scene: QtWidgets.QGraphicsScene) -> bool:
        """在支持键/值成对变参的节点上，一次性新增一对(键N, 值N)输入端口。

        识别规则：
        - NodeDef.inputs 中存在两个非流程的范围端口定义，形如“前缀数字~数字”；
        - 二者前缀非空且不同，起止索引区间一致（如“键0~49”与“值0~49”）。
        """
        node = self.node_item.node
        node_def = self._get_node_definition()
        if node_def is None:
            return False

        defined_inputs = list(getattr(node_def, "inputs", []) or [])
        # 仅考虑非流程输入端口定义
        data_input_names: list[str] = [
            str(name)
            for name in defined_inputs
            if str(name) not in ("流程入", "流程出")
        ]

        range_defs: list[tuple[str, dict]] = []
        for name in data_input_names:
            parsed = parse_range_definition(str(name))
            if parsed is None:
                continue
            prefix = str(parsed.get("prefix") or "")
            if prefix == "":
                continue
            range_defs.append((str(name), parsed))

        # 仅当恰好存在两种前缀一致范围（例如“键0~49”“值0~49”）时视为字典模式
        if len(range_defs) != 2:
            return False

        _, first = range_defs[0]
        _, second = range_defs[1]
        start_a = int(first.get("start", 0))
        end_a = int(first.get("end", 0))
        start_b = int(second.get("start", 0))
        end_b = int(second.get("end", 0))
        prefix_key = str(first.get("prefix") or "")
        prefix_value = str(second.get("prefix") or "")

        if prefix_key == "" or prefix_value == "":
            return False
        if prefix_key == prefix_value:
            return False
        if start_a != start_b or end_a != end_b:
            return False

        range_start = int(start_a)
        range_end = int(end_a)

        # 统计当前节点上已有的“键N/值N”索引
        existing_keys: set[int] = set()
        existing_values: set[int] = set()
        for port_model in getattr(node, "inputs", []) or []:
            raw_name = str(getattr(port_model, "name", "") or "")
            if raw_name.startswith(prefix_key):
                suffix = raw_name[len(prefix_key) :]
                if suffix.isdigit():
                    existing_keys.add(int(suffix))
            if raw_name.startswith(prefix_value):
                suffix = raw_name[len(prefix_value) :]
                if suffix.isdigit():
                    existing_values.add(int(suffix))

        # 选择下一个可用索引：从范围起点开始，跳过已有的键/值索引
        next_index: Optional[int] = None
        occupied_indices = existing_keys | existing_values
        for idx in range(range_start, range_end + 1):
            if idx not in occupied_indices:
                next_index = idx
                break

        if next_index is None:
            return False

        key_name = f"{prefix_key}{next_index}"
        value_name = f"{prefix_value}{next_index}"

        existing_names = {str(p.name) for p in getattr(node, "inputs", []) or []}
        names_to_add: list[str] = []
        if key_name not in existing_names:
            names_to_add.append(key_name)
        if value_name not in existing_names:
            names_to_add.append(value_name)

        if not names_to_add:
            return False

        for name in names_to_add:
            self._add_port_via_command(scene, name, is_input=True)

        return True

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


class AddPortDialog(BaseDialog):
    """添加端口对话框（统一主题样式，校验非空输入）。"""

    def __init__(self, node_item: "NodeGraphicsItem") -> None:
        super().__init__(
            title="添加分支",
            width=360,
            height=200,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
            parent=None,
        )
        self.node_item = node_item
        self._setup_ui()

    def _setup_ui(self) -> None:
        description = QtWidgets.QLabel("请输入新分支的匹配值（字符串或整数）：")
        description.setWordWrap(True)
        description.setStyleSheet(ThemeManager.info_label_simple_style())
        self.content_layout.addWidget(description)

        self.input_edit = QtWidgets.QLineEdit()
        self.input_edit.setPlaceholderText("例如：字符串1 或 100")
        self.content_layout.addWidget(self.input_edit)

    def validate(self) -> bool:
        value = self.get_port_value()
        if value:
            return True
        show_warning_dialog(self, "无效分支值", "请输入非空的字符串作为分支值")
        return False

    def get_port_value(self) -> str:
        """获取输入的端口值"""
        return self.input_edit.text().strip()


