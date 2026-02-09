from __future__ import annotations

"""server_执行节点的实现 - 自动生成的框架"""
from engine.nodes.node_spec import node_spec
from engine.utils.loop_protection import LoopProtection


class _BreakLoop(Exception):
    """用于跳出循环"""
    pass
