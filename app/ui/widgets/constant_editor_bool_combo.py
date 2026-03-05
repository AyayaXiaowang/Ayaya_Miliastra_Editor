"""常量编辑器：布尔值下拉框（ConstantBoolComboBox）。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING, cast

from PyQt6 import QtCore, QtGui, QtWidgets

from app.ui.foundation import fonts as ui_fonts
from app.ui.graph import graph_component_styles as graph_styles

from app.ui.widgets.constant_editors_helpers import _is_inline_constant_virtualization_active_for_node_item

if TYPE_CHECKING:
    from app.ui.graph.items.node_item import NodeGraphicsItem


class ConstantBoolComboBox(QtWidgets.QGraphicsProxyWidget):
    """布尔值下拉选择框"""

    def __init__(self, node_item: "NodeGraphicsItem", port_name: str, parent=None):
        super().__init__(parent)
        self.node_item = node_item
        self.port_name = port_name

        # 创建QComboBox
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["否", "是"])
        self.combo.setFont(ui_fonts.ui_font(8))
        self.combo.setStyleSheet(graph_styles.graph_inline_bool_combo_box_style())
        # 节点图行内的布尔下拉需要紧凑，但不能“写死高度”：
        # - Win10/DPI 缩放、字体回退（中日韩）时 sizeHint 会变化；
        # - QSS 生效后控件的真实绘制高度也可能变化。
        # 因此用 minimumSizeHint() + 字体度量兜底取最大值，避免出现“被裁断”，同时保持紧凑。
        self.combo.ensurePolished()
        combo_font_metrics = QtGui.QFontMetrics(self.combo.font())
        font_based_height = combo_font_metrics.height() + graph_styles.GRAPH_INLINE_BOOL_COMBO_HEIGHT_EXTRA_PX
        hint_height = self.combo.minimumSizeHint().height()
        target_height = int(
            max(
                graph_styles.GRAPH_INLINE_BOOL_COMBO_MIN_HEIGHT_PX,
                font_based_height,
                hint_height,
            )
        )
        self.combo.setFixedSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.combo.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
        # QGraphicsProxyWidget 自己也锁定尺寸，避免代理尺寸与 QWidget 尺寸不同步引起的裁剪。
        self.setMinimumSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.setMaximumSize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)

        # 设置初始值
        current_value = node_item.node.input_constants.get(port_name, False)

        # 如果没有保存过值，立即保存默认值
        if port_name not in node_item.node.input_constants:
            node_item.node.input_constants[port_name] = current_value

        is_true: bool = False
        if isinstance(current_value, bool):
            is_true = bool(current_value)
        elif isinstance(current_value, (int, float)):
            is_true = bool(current_value)
        elif isinstance(current_value, str):
            text = current_value.strip().lower()
            is_true = text in {"true", "是", "1", "yes", "y", "on"}

        if is_true:
            self.combo.setCurrentIndex(1)
        else:
            self.combo.setCurrentIndex(0)

        # 连接信号
        self.combo.currentIndexChanged.connect(self._on_value_changed)

        self.setWidget(self.combo)
        self.resize(graph_styles.GRAPH_INLINE_BOOL_COMBO_WIDTH_PX, target_height)
        self.setZValue(25)

    def _on_value_changed(self, index):
        """值改变时保存"""
        value = bool(index == 1)
        self.node_item.node.input_constants[self.port_name] = value
        # 只更新显示，不重新布局（布尔值控件大小固定，不需要重新布局）
        self.node_item.update()

        # 触发自动保存
        scene = self.scene()
        if scene is not None:
            scene_any = cast(Any, scene)
            on_data_changed = getattr(scene_any, "on_data_changed", None)
            if on_data_changed:
                on_data_changed()

        # 虚拟化开启：提交后释放控件（避免大量 QGraphicsProxyWidget 常驻）
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
            if callable(release_fn):
                QtCore.QTimer.singleShot(0, lambda: release_fn(self.port_name))

    def focusOutEvent(self, event: QtGui.QFocusEvent | None) -> None:  # type: ignore[override]
        super().focusOutEvent(event)
        if _is_inline_constant_virtualization_active_for_node_item(self.node_item):
            release_fn = getattr(self.node_item, "release_inline_constant_editor", None)
            if callable(release_fn):
                QtCore.QTimer.singleShot(0, lambda: release_fn(self.port_name))

