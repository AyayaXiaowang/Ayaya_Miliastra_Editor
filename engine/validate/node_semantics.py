from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, Mapping, Optional

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.validate.node_def_resolver import ResolvedNodeDef, resolve_node_def_from_library
from engine.validate.rules.node_index import callable_node_defs_by_name, callable_node_keys_by_name


# -----------------------------------------------------------------------------
# 语义节点定位（校验层单一入口）
#
# 目标：
# - 校验规则不要散落硬编码“节点显示名字符串”，而是统一用语义 ID 表达意图；
# - 语义识别完全依赖节点库 `NodeDef.semantic_id`（由实现侧 `@node_spec(semantic_id=...)` 透传）；
# - 统一处理 alias key 与 `#scope` 变体，避免“节点改名/分 scope 实现”导致校验漂移。
# -----------------------------------------------------------------------------

SEMANTIC_SIGNAL_SEND: str = "signal.send"
SEMANTIC_SIGNAL_LISTEN: str = "signal.listen"
SEMANTIC_GRAPH_VAR_SET: str = "graph_var.set"
SEMANTIC_GRAPH_VAR_GET: str = "graph_var.get"
SEMANTIC_CUSTOM_VAR_SET: str = "custom_var.set"
SEMANTIC_CUSTOM_VAR_GET: str = "custom_var.get"
SEMANTIC_CUSTOM_VAR_CHANGED: str = "custom_var.changed"
SEMANTIC_STRUCT_BUILD: str = "struct.build"
SEMANTIC_STRUCT_SPLIT: str = "struct.split"
SEMANTIC_STRUCT_MODIFY: str = "struct.modify"


def _strip_scope_suffix_from_node_key(node_key: str) -> str:
    """将 `类别/名称#scope` 规约为 `类别/名称`（仅剥离名称部分的 scope 后缀）。"""
    key_text = str(node_key or "").strip()
    if "/" not in key_text:
        return key_text
    category_text, name_text = key_text.split("/", 1)
    if "#" not in name_text:
        return key_text
    base_name, suffix = name_text.split("#", 1)
    suffix_text = str(suffix or "").strip().lower()
    if suffix_text in ("server", "client"):
        return f"{category_text}/{base_name}"
    return key_text


@lru_cache(maxsize=8)
def _alias_to_key(workspace_path: Path) -> Dict[str, str]:
    """返回实现侧基础节点的 alias_to_key 映射（用于将 alias key 规约为标准 key）。"""
    registry = get_node_registry(Path(workspace_path), include_composite=True)
    index = registry.get_node_library_index()
    raw = index.get("alias_to_key", {})
    if not isinstance(raw, dict):
        return {}
    mapping: Dict[str, str] = {}
    for alias_key, standard_key in raw.items():
        alias_text = str(alias_key or "")
        standard_text = str(standard_key or "")
        if alias_text and standard_text:
            mapping[alias_text] = standard_text
    return mapping


def canonicalize_node_key(workspace_path: Path, node_key: str) -> str:
    """将 alias key 映射为标准 key（若无法映射则原样返回）。"""
    key_text = str(node_key or "").strip()
    if key_text == "":
        return ""
    return str(_alias_to_key(Path(workspace_path)).get(key_text) or key_text)


def _semantic_id_for_node_key(workspace_path: Path, node_key: str) -> str:
    """从节点库中解析某个 key 的 semantic_id（支持 alias key 与 `#scope` 变体）。"""
    canonical_key = canonicalize_node_key(Path(workspace_path), node_key)
    if canonical_key == "":
        return ""

    # 基于 `by_key`（标准键）优先查 semantic_id；若未命中再回退到 NodeDef 对象（覆盖复合节点等）。
    base_key = _strip_scope_suffix_from_node_key(canonical_key)
    registry = get_node_registry(Path(workspace_path), include_composite=True)
    index = registry.get_node_library_index()
    by_key = index.get("by_key", {})
    if isinstance(by_key, dict):
        item = by_key.get(base_key) or by_key.get(canonical_key)
        if isinstance(item, dict):
            return str(item.get("semantic_id") or "").strip()

    node_library = registry.get_library()
    node_def = node_library.get(canonical_key) or node_library.get(base_key)
    return str(getattr(node_def, "semantic_id", "") or "").strip() if node_def is not None else ""


def is_semantic_node_key(*, workspace_path: Path, node_key: str, semantic_id: str) -> bool:
    """判断某个节点库 key 是否属于指定语义（支持 alias key 与 `#scope` 变体）。"""
    expected = str(semantic_id or "").strip()
    if expected == "":
        return False
    return _semantic_id_for_node_key(Path(workspace_path), str(node_key)) == expected


def resolve_graph_node_def(
    node_library: Mapping[str, NodeDef],
    *,
    node_category: str,
    node_title: str,
    scope_text: Optional[str] = None,
) -> Optional[ResolvedNodeDef]:
    """解析图节点到 NodeDef（返回包含 key 的结果；不做语义判断）。"""
    return resolve_node_def_from_library(
        node_library,
        node_category=str(node_category or ""),
        node_title=str(node_title or ""),
        scope_text=str(scope_text or "").strip().lower() or None,
    )


def is_semantic_graph_node(
    *,
    workspace_path: Path,
    node_library: Mapping[str, NodeDef],
    node_category: str,
    node_title: str,
    scope_text: Optional[str],
    semantic_id: str,
) -> bool:
    """在图数据层判断节点语义：通过解析 NodeDef key 并做 alias/#scope 规约。"""
    resolved = resolve_graph_node_def(
        node_library,
        node_category=node_category,
        node_title=node_title,
        scope_text=scope_text,
    )
    if resolved is None:
        return False
    expected = str(semantic_id or "").strip()
    node_semantic_id = str(getattr(resolved.node_def, "semantic_id", "") or "").strip()
    return bool(expected) and node_semantic_id == expected


def resolve_semantic_call_node_key(
    *,
    workspace_path: Path,
    scope: str,
    call_name: str,
    semantic_id: str,
    include_composite: bool = True,
) -> Optional[str]:
    """在 Graph Code（函数调用名）层解析指定语义节点的标准 key。"""
    scope_text = str(scope or "").strip().lower()
    node_defs_by_name = callable_node_defs_by_name(
        Path(workspace_path),
        scope_text,
        include_composite=bool(include_composite),
    )
    mapping = callable_node_keys_by_name(
        Path(workspace_path),
        scope_text,
        include_composite=bool(include_composite),
    )
    matched_key = mapping.get(str(call_name or ""))
    if not matched_key:
        return None
    canonical_key = canonicalize_node_key(Path(workspace_path), matched_key)

    node_def = node_defs_by_name.get(str(call_name or ""))
    node_semantic_id = str(getattr(node_def, "semantic_id", "") or "").strip() if node_def is not None else ""
    expected = str(semantic_id or "").strip()
    if not expected:
        return None
    if node_semantic_id != expected:
        return None
    return canonical_key


def is_semantic_node_call(
    *,
    workspace_path: Path,
    scope: str,
    call_name: str,
    semantic_id: str,
    include_composite: bool = True,
) -> bool:
    """判断 Graph Code 中的函数调用是否指向某语义节点（支持别名与 `名称#scope` 规约）。"""
    return (
        resolve_semantic_call_node_key(
            workspace_path=Path(workspace_path),
            scope=str(scope),
            call_name=str(call_name),
            semantic_id=str(semantic_id),
            include_composite=bool(include_composite),
        )
        is not None
    )


__all__ = [
    "SEMANTIC_CUSTOM_VAR_CHANGED",
    "SEMANTIC_CUSTOM_VAR_GET",
    "SEMANTIC_CUSTOM_VAR_SET",
    "SEMANTIC_GRAPH_VAR_GET",
    "SEMANTIC_GRAPH_VAR_SET",
    "SEMANTIC_SIGNAL_LISTEN",
    "SEMANTIC_SIGNAL_SEND",
    "SEMANTIC_STRUCT_BUILD",
    "SEMANTIC_STRUCT_MODIFY",
    "SEMANTIC_STRUCT_SPLIT",
    "canonicalize_node_key",
    "is_semantic_graph_node",
    "is_semantic_node_call",
    "is_semantic_node_key",
    "resolve_graph_node_def",
    "resolve_semantic_call_node_key",
]


