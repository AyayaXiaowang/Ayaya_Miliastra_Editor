"""
布局常量定义模块

集中管理所有布局算法使用的固定数值、颜色和语义常量。
"""

from typing import List
from engine.configs.settings import settings
from engine.utils.logging.logger import log_info

# ============================================================================
# 全局布局常量（统一收口所有固定数值）
# ============================================================================

# 基础尺寸（与UI近似一致）
NODE_WIDTH_DEFAULT: float = 180.0
NODE_HEIGHT_DEFAULT: float = 80.0
SLOT_WIDTH_MULTIPLIER: float = 2.0  # 块内槽位宽度 = 节点宽度 * 该倍率

# UI 节点的最小宽度（与 `app/ui/graph/items/node_item.py::NodeGraphicsItem` 对齐：min=260）
# 说明：布局核心层仍以 NODE_WIDTH_DEFAULT 做“历史基线”，但在缩小间距时需要以 UI 最小宽度为下界，
# 否则槽位宽度可能小于实际渲染宽度，导致节点矩形重叠。
UI_NODE_MIN_WIDTH: float = 260.0

# UI 内部行高与头部高度估算
#
# 约定：
# - UI 渲染与布局层共用同一份行高常量（`UI_ROW_HEIGHT`），避免“布局估算的节点高度/端口Y”与实际绘制不一致；
# - 端口两行结构不变（标签行 + 控件行），但收敛行高以减少控件上下留白（紧凑显示）。
UI_ROW_HEIGHT: float = 32.0           # 单"行"高度；输入端口按两行计（更紧凑）
UI_NODE_HEADER_HEIGHT: float = UI_ROW_HEIGHT + 10.0  # 对齐 UI：header_h = ROW_HEIGHT + UI_HEADER_EXTRA(10)
UI_CATEGORY_EXTRA_HEIGHT: float = 0.0 # 事件/流程控制类节点额外高度

# 与 UI 完全一致的外边距设置（用于高度精确对齐）
# UI 计算公式（见 ui/graph_scene.py::_layout_ports）：
#   content_h = max_rows * ROW_HEIGHT + NODE_PADDING
#   header_h  = ROW_HEIGHT + UI_HEADER_EXTRA
#   total_h   = header_h + content_h + NODE_PADDING
# 其中 NODE_PADDING=10, UI_HEADER_EXTRA=10
UI_NODE_PADDING: float = 10.0
UI_HEADER_EXTRA: float = 10.0

# 块/事件/间距配置
BLOCK_PADDING_DEFAULT: float = 25.0
BLOCK_X_SPACING_DEFAULT: float = 200.0
BLOCK_Y_SPACING_DEFAULT: float = 40.0
INITIAL_X_DEFAULT: float = 100.0
INITIAL_Y_DEFAULT: float = 100.0
# 事件组（事件流）之间的默认垂直间距
EVENT_Y_GAP_DEFAULT: float = 100

# 数据与流程之间的安全间隔
FLOW_TO_DATA_GAP_DEFAULT: float = 50.0

# 数据行的基础附加高度（相对于节点高度的固定下限）
DATA_BASE_EXTRA_MARGIN: float = 100.0

# 数据节点垂直堆叠时的基础间隙
DATA_STACK_GAP_DEFAULT: float = 20.0

# 端口与数据之间的附加安全间隔（端口近似位置 → 数据节点）
INPUT_PORT_TO_DATA_GAP_DEFAULT: float = 16.0

# 事件/排序中的大数回退
ORDER_MAX_FALLBACK: int = 10**9

# 基本块调色板
BLOCK_COLORS_DEFAULT: List[str] = [
    "#FF5E9C",  # 粉红色
    "#9CD64B",  # 绿色
    "#2D5FE3",  # 蓝色
    "#2FAACB",  # 青色
    "#FF9955",  # 橙色
    "#AA55FF",  # 紫色
    "#FFD700",  # 金色
    "#FF6B6B",  # 浅红色
    "#4ECDC4",  # 青绿色
    "#95E1D3",  # 浅绿色
]

# 统一语义常量
TITLE_MULTI_BRANCH: str = "多分支"
PORT_EXIT_LOOP: str = "跳出循环"
CATEGORY_EVENT: str = "事件节点"
CATEGORY_FLOW_CTRL: str = "流程控制节点"


def debug(message: str) -> None:
    """
    布局调试输出函数
    
    根据 settings.LAYOUT_DEBUG_PRINT 配置决定是否输出调试信息。
    
    Args:
        message: 调试信息
    """
    if settings.LAYOUT_DEBUG_PRINT:
        log_info(message)


# ============================================================================
# 自动排版间距倍率（与 SettingsDialog 的范围对齐）
# ============================================================================

LAYOUT_NODE_SPACING_PERCENT_MIN: int = 10
LAYOUT_NODE_SPACING_PERCENT_MAX: int = 200


def _clamp_layout_spacing_percent(value: int) -> int:
    if value < LAYOUT_NODE_SPACING_PERCENT_MIN:
        return LAYOUT_NODE_SPACING_PERCENT_MIN
    if value > LAYOUT_NODE_SPACING_PERCENT_MAX:
        return LAYOUT_NODE_SPACING_PERCENT_MAX
    return value


def get_layout_node_spacing_multipliers() -> tuple[float, float]:
    """返回自动排版的横/纵间距倍率（x_multiplier, y_multiplier）。"""
    x_percent = _clamp_layout_spacing_percent(int(settings.LAYOUT_NODE_SPACING_X_PERCENT))
    y_percent = _clamp_layout_spacing_percent(int(settings.LAYOUT_NODE_SPACING_Y_PERCENT))
    return (float(x_percent) / 100.0, float(y_percent) / 100.0)


def scale_layout_gap_x(base_gap: float) -> float:
    """按横向倍率缩放“纯间隙类”常量（不包含节点自身宽度）。

    重要：横向的“视觉间隙”基线需要考虑 UI 节点最小宽度与布局默认宽度的差值，
    以保证在缩小倍率（如 40%）时不会因为宽度基线偏小而产生节点矩形重叠。
    """
    x_multiplier, _ = get_layout_node_spacing_multipliers()
    base_gap_value = float(base_gap)
    width_offset = max(0.0, float(UI_NODE_MIN_WIDTH) - float(NODE_WIDTH_DEFAULT))
    baseline_gap = max(0.0, base_gap_value - width_offset)
    return float(width_offset) + float(baseline_gap) * float(x_multiplier)


def scale_layout_gap_y(base_gap: float) -> float:
    """按纵向倍率缩放“纯间隙类”常量（不包含节点自身高度）。"""
    _, y_multiplier = get_layout_node_spacing_multipliers()
    return float(base_gap) * float(y_multiplier)


def compute_slot_width_from_node_width(node_width: float) -> float:
    """
    计算“列槽位宽度”（用于把列索引映射为像素 X）。

    关键点：倍率按“相邻节点之间的间隙”缩放，而不是把节点宽度也一起放大。
    - 基线：slot_width = node_width * SLOT_WIDTH_MULTIPLIER
    - 间隙：gap = slot_width - node_width = node_width * (SLOT_WIDTH_MULTIPLIER - 1)
    - 缩放：slot_width' = node_width + gap * x_multiplier
    """
    x_multiplier, _ = get_layout_node_spacing_multipliers()
    slot_width_multiplier = float(SLOT_WIDTH_MULTIPLIER)
    base_slot_width = float(node_width) * slot_width_multiplier

    # 以 UI 最小宽度为“列下界”，只缩放 slot_width 与 UI 宽度之间的间隙，
    # 保证倍率缩小后列宽不会小于实际渲染宽度。
    min_ui_width = max(float(UI_NODE_MIN_WIDTH), float(node_width))
    base_gap = max(0.0, float(base_slot_width) - float(min_ui_width))
    return float(min_ui_width) + float(base_gap) * float(x_multiplier)



