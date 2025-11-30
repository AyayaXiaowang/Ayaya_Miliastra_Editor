from __future__ import annotations

from typing import Dict

from engine.nodes.node_definition_loader import NodeDef


def validate_composites(parsed: Dict[str, NodeDef], base_node_library: Dict[str, NodeDef]) -> Dict[str, NodeDef]:
    """
    对复合节点的 NodeDef 进行最小校验占位。
    现阶段委托 CompositeNodeManager 的内部校验；此处保持通路与风格一致。
    """
    if not isinstance(parsed, dict):
        raise TypeError("复合节点解析产物应为字典")
    # 预留：可在此补充与主管线一致的错误格式化与校验项
    return parsed


