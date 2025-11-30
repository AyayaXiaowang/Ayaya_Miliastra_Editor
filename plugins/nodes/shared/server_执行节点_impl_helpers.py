from __future__ import annotations

"""server_执行节点的实现 - 自动生成的框架"""
from engine.nodes.node_spec import node_spec
from app.runtime.engine.node_executor import LoopProtection
class _BreakLoop(Exception):
    """用于跳出循环"""
    pass
