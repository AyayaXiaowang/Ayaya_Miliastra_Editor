from __future__ import annotations

import keyword
from typing import Dict, List, Sequence

from engine.graph.models import NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.name_utils import make_valid_identifier

from engine.graph.reverse_codegen._common import ReverseGraphCodeError


def _pick_call_name_for_node(
    *,
    node: NodeModel,
    node_def: NodeDef,
    node_library: Dict[str, NodeDef],
    node_name_index: Dict[str, str],
    call_name_candidates_by_identity: Dict[int, List[str]],
) -> str:
    """为节点选择稳定且可调用的函数名。"""
    # 优先：title 若可直接作为调用名且能命中 name_index，且映射到同一 NodeDef
    title = str(getattr(node, "title", "") or "").strip()
    if title and title.isidentifier() and (not keyword.iskeyword(title)):
        mapped_key = node_name_index.get(title)
        if mapped_key is not None:
            mapped_def = node_library.get(mapped_key)
            if mapped_def is node_def:
                return title

    identity = id(node_def)
    candidates = call_name_candidates_by_identity.get(identity) or []
    if not candidates:
        raise ReverseGraphCodeError(
            f"节点 {node.category}/{node.title} 缺少可调用名（title 不可用且未找到别名键）"
        )
    return candidates[0]


def _finalize_output_var_names(raw_names: Sequence[str], *, used: set[str]) -> List[str]:
    """将输出端口名规范化为可用且不冲突的变量名列表。"""
    finalized: List[str] = []
    for raw in raw_names:
        candidate = make_valid_identifier(raw or "")
        if not candidate or candidate == "_":
            candidate = "var"
        while candidate in used or keyword.iskeyword(candidate):
            candidate = f"{candidate}_1"
        used.add(candidate)
        finalized.append(candidate)
    return finalized

