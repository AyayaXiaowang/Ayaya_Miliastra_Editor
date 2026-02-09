from __future__ import annotations

"""
Node stub generation (for IDE autocomplete / type hints).

Design goals:
- Pure generation (no side effects other than returning text). Writing files is handled by CLI.
- Derived from the authoritative NodeRegistry / NodeDef, so it stays aligned with node specs.
- Prefer stable, deterministic output (sorted, explicit types, minimal whitespace noise).

Notes:
- This generator targets `.pyi` stubs (type checkers only). It does not affect runtime behavior.
- We intentionally type the first `game` parameter as `Any` to avoid leaking `app.*` dependencies into
  plugin-layer stubs.
"""

import keyword
from pathlib import Path
from typing import Any, Dict, List, Tuple

from engine.type_registry import (
    TYPE_DICT,
    TYPE_ENUM,
    TYPE_FLOW,
    TYPE_STRING,
    normalize_type_text,
    parse_typed_dict_alias,
)
from engine.utils.graph.graph_utils import is_flow_port_name

from .constants import ALLOWED_SCOPES
from .node_definition_loader import NodeDef
from .node_registry import get_node_registry


def _is_safe_identifier(name: str) -> bool:
    text = str(name or "").strip()
    return bool(text) and text.isidentifier() and (not keyword.iskeyword(text))


def _split_name_scope(name_part: str) -> Tuple[str, str | None]:
    """Split `名称#scope` -> (名称, scope)."""
    text = str(name_part or "")
    if "#" not in text:
        return text, None
    base, suffix = text.split("#", 1)
    return base, (suffix or None)


def _iter_callable_node_defs_by_call_name(
    library: Dict[str, NodeDef],
    *,
    scope: str,
) -> Dict[str, NodeDef]:
    """Return {call_name: NodeDef} for the given scope.

    Rule:
    - call_name comes from the "name part" of `category/name_part` (Graph Code cannot carry category prefix)
    - `name_part#scope` variant wins over `name_part` when scope matches
    - only safe identifiers are included
    """
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    chosen: Dict[str, Tuple[int, NodeDef]] = {}
    for full_key, node_def in (library.items() if isinstance(library, dict) else []):
        if not isinstance(full_key, str) or "/" not in full_key:
            continue
        if not isinstance(node_def, NodeDef):
            continue
        if node_def.is_composite:
            continue
        if not node_def.is_available_in_scope(scope_text):
            continue

        _, name_part = full_key.split("/", 1)
        base_name, scope_suffix = _split_name_scope(name_part)
        if not _is_safe_identifier(base_name):
            continue

        if scope_suffix is None:
            priority = 1
        elif scope_suffix == scope_text:
            priority = 2
        else:
            continue

        existing = chosen.get(base_name)
        if existing is None or priority > existing[0]:
            chosen[base_name] = (priority, node_def)

    return {name: pair[1] for name, pair in chosen.items()}


def _type_expr_from_port_type(type_name: str) -> str:
    """Map engine port type text -> `.pyi` type expression."""
    text = normalize_type_text(type_name)
    if not text:
        return "Any"
    if text == TYPE_FLOW:
        return "Any"
    if text == TYPE_ENUM:
        # Enum values are represented as strings in Graph Code.
        return TYPE_STRING
    if text == TYPE_DICT:
        return TYPE_DICT

    ok, key_type, value_type = parse_typed_dict_alias(text)
    if ok:
        # The typing placeholder uses `_` as the separator (not `-`).
        return f"{key_type}_{value_type}{TYPE_DICT}"

    # NOTE:
    # - Base/list types map 1:1 to `engine.configs.rules.datatypes_typing` placeholders.
    # - For unknown/extended types, fall back to Any (type checkers should not block authoring).
    if _is_safe_identifier(text):
        return text
    return "Any"


def _render_return_type(node_def: NodeDef) -> str:
    output_types = getattr(node_def, "output_types", {}) or {}
    outputs = [p for p in (getattr(node_def, "outputs", []) or []) if not is_flow_port_name(str(p))]
    if not outputs:
        return "None"
    parts: List[str] = []
    for port_name in outputs:
        port_type = output_types.get(port_name, "")
        parts.append(_type_expr_from_port_type(str(port_type)))
    if len(parts) == 1:
        return parts[0]
    return "tuple[" + ", ".join(parts) + "]"


def _render_params(node_def: NodeDef) -> Tuple[List[str], bool]:
    input_types = getattr(node_def, "input_types", {}) or {}
    input_defaults = getattr(node_def, "input_defaults", {}) or {}
    inputs = [p for p in (getattr(node_def, "inputs", []) or []) if not is_flow_port_name(str(p))]

    params: List[str] = ["game: Any"]
    needs_kwargs = False

    for port_name in inputs:
        port_text = str(port_name)
        if not _is_safe_identifier(port_text):
            # Dynamic/expanded ports may not be valid identifiers (e.g. "0~99"); keep a kwargs escape hatch.
            needs_kwargs = True
            continue

        port_type = input_types.get(port_text, "")
        type_expr = _type_expr_from_port_type(str(port_type))

        # Optional: if the node declares an input default, treat as optional in stubs.
        if port_text in input_defaults:
            params.append(f"{port_text}: {type_expr} = ...")
        else:
            params.append(f"{port_text}: {type_expr}")

    dynamic_port_type = str(getattr(node_def, "dynamic_port_type", "") or "").strip()
    if dynamic_port_type:
        needs_kwargs = True

    return params, needs_kwargs


def generate_nodes_pyi_stub(
    workspace_path: Path,
    *,
    scope: str,
) -> str:
    """Generate the `.pyi` content for `plugins.nodes.<scope>`."""
    scope_text = str(scope or "").strip().lower()
    if scope_text not in ALLOWED_SCOPES:
        scope_text = "server"

    registry = get_node_registry(workspace_path, include_composite=False)
    lib = registry.get_library()
    call_map = _iter_callable_node_defs_by_call_name(lib, scope=scope_text)

    lines: List[str] = []
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("# AUTO-GENERATED: node function typing stubs")
    lines.append("# - Source of truth: NodeRegistry/NodeDef (V2 AST pipeline)")
    lines.append("# - Runtime is unaffected (pyright/pylance only)")
    lines.append("")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from engine.configs.rules.datatypes_typing import *")
    lines.append("")

    for fn_name in sorted(call_map.keys()):
        node_def = call_map[fn_name]
        params, needs_kwargs = _render_params(node_def)
        if needs_kwargs:
            params.append("**kwargs: Any")
        ret = _render_return_type(node_def)
        signature = f"def {fn_name}(" + ", ".join(params) + f") -> {ret}: ..."
        lines.append(signature)

    lines.append("")
    return "\n".join(lines)


__all__ = ["generate_nodes_pyi_stub"]


