from __future__ import annotations

from typing import Dict

from engine.nodes.node_definition_loader import NodeDef


def validate_composites(library: Dict[str, NodeDef]) -> Dict[str, NodeDef]:
    """
    复合节点基本校验（阻断式）。

    校验项：
    - 标记 is_composite=True 的项必须具有非空 composite_id
    - NodeDef 的基本字段应为字符串列表/字典（由上游保证），此处不重复验证
    """
    if not isinstance(library, dict):
        raise TypeError("复合节点库必须是字典")
    for key, node in library.items():
        if not isinstance(node, NodeDef):
            raise TypeError(f"复合节点条目类型非法: key={key}")
        if getattr(node, "is_composite", False):
            composite_id = getattr(node, "composite_id", "")
            if not isinstance(composite_id, str) or composite_id.strip() == "":
                raise ValueError(f"[COMPOSITE][VALIDATOR] 复合节点缺少 composite_id: key={key}")
    return library



