from __future__ import annotations

# Server 侧节点图最小导入预设：
# - 暴露 GameRuntime（用于类型注解）
# - 导入所有 server 侧节点实现（执行/查询/运算/流程/事件）
# - 导入"占位类型"以消除类型检查器对中文类型名的未定义提示

from .game_state import GameRuntime
from plugins.nodes.server import *  # noqa: F401,F403
from engine.configs.rules.datatypes_typing import *  # noqa: F401,F403
from engine.graph.composite.pin_api import (  # noqa: F401,F403
    流程入,
    流程入引脚,
    流程出,
    流程出引脚,
    数据入,
    数据出,
)
from .node_graph_validator import validate_node_graph  # 便于节点图以装饰器形式启用验证


