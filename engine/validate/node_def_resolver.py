from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from engine.nodes.constants import ALLOWED_SCOPES
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes import get_canonical_node_def_key


@dataclass(frozen=True)
class ResolvedNodeDef:
    """节点定义解析结果（用于结构校验/类型校验共用）。"""

    key: str
    node_def: NodeDef


def normalize_category_to_standard(category_text: str) -> str:
    """统一类别名为内部标准：带“节点”后缀。"""
    category_clean = str(category_text or "").strip()
    if category_clean.endswith("节点"):
        return category_clean
    return f"{category_clean}节点"


def _split_scope_suffix(name_text: str) -> Tuple[str, Optional[str]]:
    """拆分 `名称#scope` → (名称, scope)。"""
    text = str(name_text or "")
    if "#" not in text:
        return text, None
    base, suffix = text.split("#", 1)
    suffix_text = str(suffix or "").strip().lower()
    return base, (suffix_text or None)


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in list(items or []):
        text = str(item or "")
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _candidate_keys(
    *,
    category_standard: str,
    node_title: str,
    scope_text: Optional[str],
) -> list[str]:
    """
    生成用于在 node_library 中查找 NodeDef 的候选 key 列表（稳定顺序）。

    约定：
    - key 形态为 `类别/名称` 或 `类别/名称#scope`
    - 若 scope_text 给定：优先尝试 `#scope` 变体，再回退基键
    - 若 node_title 自身已携带 `#scope`：视为显式指定（优先该变体）
    """
    title_base, explicit_scope = _split_scope_suffix(node_title)
    base_key = f"{category_standard}/{title_base}"

    resolved_scope = str((explicit_scope or scope_text or "")).strip().lower() or None
    keys: list[str] = []

    if resolved_scope and resolved_scope in ALLOWED_SCOPES:
        keys.append(f"{base_key}#{resolved_scope}")

    # 基键（无后缀）
    keys.append(base_key)

    # 未显式指定 scope 时，为兼容旧逻辑/未知 scope 的场景，补齐另一个 scope 变体
    if not explicit_scope:
        for other_scope in ALLOWED_SCOPES:
            if resolved_scope and other_scope == resolved_scope:
                continue
            keys.append(f"{base_key}#{other_scope}")

    return _dedupe_preserve_order(keys)


def resolve_node_def_from_library(
    node_library: Mapping[str, NodeDef],
    *,
    node_category: str,
    node_title: str,
    scope_text: Optional[str] = None,
) -> Optional[ResolvedNodeDef]:
    """旧入口：从 NodeDef 库中解析节点定义（基于 title/category/#scope）。

    注意：该函数仅用于离线迁移/诊断；运行时主链路应使用 `resolve_node_def_for_model(...)`
    并以 `NodeModel.node_def_ref` 为唯一真源，禁止 title fallback。
    """
    if not node_library:
        return None
    category_standard = normalize_category_to_standard(str(node_category or ""))
    for key in _candidate_keys(
        category_standard=category_standard,
        node_title=str(node_title or ""),
        scope_text=str(scope_text or "").strip().lower() or None,
    ):
        node_def = node_library.get(key)
        if node_def is not None:
            return ResolvedNodeDef(key=key, node_def=node_def)
    return None


def resolve_node_def_for_model(
    node_library: Mapping[str, NodeDef],
    *,
    node_model: object,
) -> Optional[ResolvedNodeDef]:
    """运行时入口：基于 NodeModel.node_def_ref 精确解析 NodeDef。"""
    node_def_ref = getattr(node_model, "node_def_ref", None)
    if node_def_ref is None:
        return None
    kind = str(getattr(node_def_ref, "kind", "") or "").strip()
    key = str(getattr(node_def_ref, "key", "") or "").strip()
    if kind == "builtin":
        node_def = node_library.get(key)
        if node_def is None:
            return None
        return ResolvedNodeDef(key=get_canonical_node_def_key(node_def), node_def=node_def)
    if kind == "composite":
        for _, node_def in node_library.items():
            if not getattr(node_def, "is_composite", False):
                continue
            if str(getattr(node_def, "composite_id", "") or "") == key:
                return ResolvedNodeDef(key=get_canonical_node_def_key(node_def), node_def=node_def)
        return None
    return None


__all__ = [
    "ResolvedNodeDef",
    "normalize_category_to_standard",
    "resolve_node_def_from_library",
    "resolve_node_def_for_model",
]


