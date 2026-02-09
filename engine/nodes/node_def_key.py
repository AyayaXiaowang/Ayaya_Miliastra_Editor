from __future__ import annotations

from typing import Mapping

from engine.nodes.node_definition_loader import NodeDef


def get_canonical_node_def_key(node_def: NodeDef) -> str:
    """获取 NodeDef 的 canonical key（稳定主键）。

    约定：
    - canonical key 是节点库对该 NodeDef 的唯一真源定位键；
    - 运行时禁止调用侧自行拼 key（例如用 title/category/scope 组合），必须由节点库构建阶段写入并在此处读取。
    """
    key = str(getattr(node_def, "canonical_key", "") or "").strip()
    if not key:
        raise ValueError(f"NodeDef 缺少 canonical_key：{getattr(node_def, 'category', '')}/{getattr(node_def, 'name', '')}")
    return key


def resolve_node_def_by_key(key: str, *, node_library: Mapping[str, NodeDef]) -> NodeDef:
    """通过 canonical key 从 node_library 精确解析 NodeDef。

    说明：
    - 若 key 无法命中，直接抛错（fail-fast），调用侧不得 title fallback。
    """
    key_text = str(key or "").strip()
    if not key_text:
        raise ValueError("resolve_node_def_by_key: key 不能为空")
    node_def = node_library.get(key_text)
    if node_def is None:
        raise KeyError(f"node_library 中未找到 NodeDef：{key_text}")
    return node_def

