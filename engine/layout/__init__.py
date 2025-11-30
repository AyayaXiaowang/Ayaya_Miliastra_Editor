"""
布局算法与相关数据结构（纯逻辑，无 UI）。

对外暴露少量稳定 API，核心实现位于 engine.layout 的子包中。
"""

from .core.layout_service import LayoutResult, LayoutService
from .core.layout_algorithm import layout_by_event_regions
from .flow.flow_tree_generator import generate_flow_tree
from .core import constants as _constants
from .core.layout_context import LayoutContext
from .flow.event_flow_analyzer import find_event_roots

_CONSTANT_EXPORTS = (
    "NODE_WIDTH_DEFAULT",
    "NODE_HEIGHT_DEFAULT",
    "SLOT_WIDTH_MULTIPLIER",
    "UI_NODE_HEADER_HEIGHT",
    "UI_ROW_HEIGHT",
    "UI_NODE_PADDING",
    "UI_HEADER_EXTRA",
    "UI_CATEGORY_EXTRA_HEIGHT",
    "BLOCK_PADDING_DEFAULT",
    "BLOCK_X_SPACING_DEFAULT",
    "BLOCK_Y_SPACING_DEFAULT",
    "INITIAL_X_DEFAULT",
    "INITIAL_Y_DEFAULT",
    "EVENT_Y_GAP_DEFAULT",
    "FLOW_TO_DATA_GAP_DEFAULT",
    "DATA_BASE_EXTRA_MARGIN",
    "DATA_STACK_GAP_DEFAULT",
    "INPUT_PORT_TO_DATA_GAP_DEFAULT",
    "BLOCK_COLORS_DEFAULT",
    "TITLE_MULTI_BRANCH",
    "PORT_EXIT_LOOP",
    "CATEGORY_EVENT",
    "CATEGORY_FLOW_CTRL",
    "ORDER_MAX_FALLBACK",
)

globals().update({name: getattr(_constants, name) for name in _CONSTANT_EXPORTS})

__all__ = [
    "layout_by_event_regions",
    "generate_flow_tree",
    "LayoutService",
    "LayoutResult",
    "LayoutContext",
    "find_event_roots",
] + list(_CONSTANT_EXPORTS)
