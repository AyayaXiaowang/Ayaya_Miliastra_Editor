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

# UI内部行高与头部高度估算
UI_NODE_HEADER_HEIGHT: float = 56.0
UI_ROW_HEIGHT: float = 41.6           # 单"行"高度；输入端口按两行计
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



