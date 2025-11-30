from __future__ import annotations

from typing import Dict

from engine.nodes.node_definition_loader import NodeDef


def expand_composites(validated: Dict[str, NodeDef]) -> Dict[str, NodeDef]:
    """
    复合节点扩展阶段（占位实现）。
    当前直接透传，后续可在此处做作用域变体或派生增强。
    """
    if not isinstance(validated, dict):
        raise TypeError("复合节点扩展输入必须是字典")
    return validated

