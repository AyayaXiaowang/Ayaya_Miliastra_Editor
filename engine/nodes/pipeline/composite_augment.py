from __future__ import annotations

from typing import Dict

from engine.nodes.node_definition_loader import NodeDef


def augment_composites(expanded: Dict[str, NodeDef], base_node_library: Dict[str, NodeDef]) -> Dict[str, NodeDef]:
    """
    最终增强与整理阶段。
    目前直接返回扩展结果，保持与主管线类似的阶段风格。
    """
    if not isinstance(expanded, dict):
        raise TypeError("复合节点扩展产物应为字典")
    return expanded


