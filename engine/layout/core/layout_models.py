from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

from .constants import NODE_WIDTH_DEFAULT


@dataclass(eq=False)
class LayoutBlock:
    """
    用于布局计算的基本块（内部数据结构）
    """

    flow_nodes: List[str] = field(default_factory=list)
    data_nodes: List[str] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0
    top_left_pos: Tuple[float, float] = (0.0, 0.0)
    node_local_pos: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    node_width: float = NODE_WIDTH_DEFAULT
    color: str = ""
    last_node_branches: List[Tuple[str, str]] = field(default_factory=list)
    # 分块阶段即确定的稳定序号（按事件逐个完整编号），从1开始
    order_index: int = 0
    event_root_id: Optional[str] = None

