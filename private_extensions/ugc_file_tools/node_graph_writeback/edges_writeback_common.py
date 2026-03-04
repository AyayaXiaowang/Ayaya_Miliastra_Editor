from __future__ import annotations

from typing import Any, Dict


def resolve_node_def_for_graph_node(
    *,
    node_id: str,
    node_title: str,
    node_payload: Dict[str, Any],
    node_defs_by_name: Dict[str, Any],
) -> Any:
    """
    将 GraphModel 的节点映射到 Graph_Generater NodeDef。

    关键兼容：
    - signal listen 的“事件节点”在 GraphModel 中常表现为：title/key=信号名（例如 '第七关_开始游戏'），
      但其实际 NodeDef 仍应视为 '监听信号'。
    """
    _ = node_id  # 兼容保留：用于未来增强诊断信息

    resolved = node_defs_by_name.get(str(node_title))
    if resolved is not None:
        return resolved

    node_def_ref = node_payload.get("node_def_ref")
    if isinstance(node_def_ref, dict):
        kind = str(node_def_ref.get("kind") or "").strip().lower()
        if kind == "event":
            outputs = node_payload.get("outputs")
            if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                return node_defs_by_name.get("监听信号")
    return None

