from __future__ import annotations

from PyQt6 import QtWidgets
from typing import Dict, List, Optional, TYPE_CHECKING

from app.ui.foundation import fonts as ui_fonts
from engine.graph.models.graph_model import NodeModel

from app.ui.graph.items.node_item_constants import (
    BRANCH_PLUS_EXTRA_ROWS,
    NODE_PADDING,
    OUTPUT_SETTINGS_BUTTON_CENTER_X_FROM_RIGHT_PX,
    PORT_SETTINGS_BUTTON_MARGIN_PX,
    ROW_HEIGHT,
)
from app.ui.graph.items.node_item_inline_constants_mixin import NodeInlineConstantsMixin
from app.ui.graph.items.node_item_interaction_mixin import NodeInteractionMixin
from app.ui.graph.items.node_item_layout_mixin import NodePortLayoutMixin
from app.ui.graph.items.node_item_paint_mixin import NodePaintMixin
from app.ui.graph.items.node_item_ports_mixin import NodePortsMixin
from app.ui.graph.items.node_item_search_highlight_mixin import NodeSearchHighlightMixin

if TYPE_CHECKING:
    from app.ui.dynamic_port_widget import AddPortButton
    from app.ui.graph.items.port_item import PortGraphicsItem
    from app.ui.graph.items.port_settings_button import PortSettingsButton


class NodeGraphicsItem(
    NodeSearchHighlightMixin,
    NodePortsMixin,
    NodeInlineConstantsMixin,
    NodeInteractionMixin,
    NodePortLayoutMixin,
    NodePaintMixin,
    QtWidgets.QGraphicsItem,
):
    def __init__(self, node: NodeModel):
        super().__init__()
        self.node = node
        self.title_font = ui_fonts.ui_font(11, bold=True)
        self._ports_in: List["PortGraphicsItem"] = []
        self._ports_out: List["PortGraphicsItem"] = []
        self._flow_in: Optional["PortGraphicsItem"] = None
        self._flow_out: Optional["PortGraphicsItem"] = None
        self._constant_edits: Dict[str, QtWidgets.QGraphicsItem] = {}  # 常量编辑框（可能是不同类型的控件）
        self._control_positions: Dict[str, tuple[float, float, float, str]] = {}  # {端口名: (x, y, width, type)} type可以是'text', 'bool', 'vector'
        # 行内常量控件（虚拟化占位渲染）缓存：
        # - 端口类型：用于按需 materialize editor 或绘制占位文本
        # - display/tooltip：与 ConstantTextEdit 的语义化展示口径对齐（变量名映射等）
        self._inline_constant_port_types: Dict[str, str] = {}
        self._inline_constant_display_text: Dict[str, str] = {}
        self._inline_constant_tooltips: Dict[str, str] = {}
        self._port_settings_buttons: list["PortSettingsButton"] = []  # 端口旁边的“⚙查看类型”按钮
        # 输入端口所在的"标签行"索引映射（控件换行后，行索引不再等于端口序号）
        self._input_row_index_map: Dict[str, int] = {}
        self._add_port_button: Optional["AddPortButton"] = None  # 多分支节点的添加端口按钮
        # 节点拖拽开始标记：用于避免在 ItemPositionChange 频繁触发时重复记录起点。
        self._moving_started: bool = False
        # 画布搜索命中高亮（不影响选中态；用于 Ctrl+F 搜索结果批量标注）
        self._search_highlighted: bool = False
        # 给节点比连线更高的 z 值，让节点在连线上面
        self.setZValue(10)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        # 端口布局依赖 GraphScene 上下文（layout_registry_context / edge_items 等）。
        # QGraphicsItem 在未加入场景前 self.scene() 为 None，因此必须由 GraphScene.add_node_item()
        # 在 addItem(item) 之后触发一次布局。

