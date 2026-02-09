from __future__ import annotations

"""
Authoring helpers for Graph Code files.

This module focuses on improving the *writing experience* without changing the parsing/validation contract:
- Graph variables remain single-source-of-truth in code-level `GRAPH_VARIABLES`.
- We can generate a small constants block (e.g. `GV.原始位置`) to reduce string typos and improve IDE autocomplete.

All helpers are designed to be deterministic and side-effect free. File I/O is handled by CLI.
"""

import ast
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from engine.utils.name_utils import generate_unique_name, make_valid_identifier


GV_BLOCK_START = "# === AUTO-GENERATED START: GRAPH_VAR_NAMES ==="
GV_BLOCK_END = "# === AUTO-GENERATED END: GRAPH_VAR_NAMES ==="


@dataclass(frozen=True)
class GraphVarInfo:
    name: str
    variable_type: str
    default_value: Any
    is_exposed: bool


def find_graph_variables_decl_span(tree: ast.Module) -> Tuple[int, int] | None:
    """Return (lineno, end_lineno) for the module-level `GRAPH_VARIABLES` declaration, if present."""
    for node in getattr(tree, "body", []) or []:
        if isinstance(node, ast.Assign):
            targets = getattr(node, "targets", []) or []
            if any(isinstance(t, ast.Name) and t.id == "GRAPH_VARIABLES" for t in targets):
                lineno = int(getattr(node, "lineno", 0) or 0)
                end_lineno = int(getattr(node, "end_lineno", 0) or 0)
                if lineno > 0 and end_lineno >= lineno:
                    return lineno, end_lineno
        if isinstance(node, ast.AnnAssign):
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES":
                lineno = int(getattr(node, "lineno", 0) or 0)
                end_lineno = int(getattr(node, "end_lineno", 0) or 0)
                if lineno > 0 and end_lineno >= lineno:
                    return lineno, end_lineno
    return None


def normalize_graph_variables(raw: List[Dict[str, Any]]) -> List[GraphVarInfo]:
    """Normalize `metadata_extractor.extract_graph_variables_from_ast` output."""
    result: List[GraphVarInfo] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        vtype = str(item.get("variable_type") or "").strip()
        if not name or not vtype:
            continue
        result.append(
            GraphVarInfo(
                name=name,
                variable_type=vtype,
                default_value=item.get("default_value"),
                is_exposed=bool(item.get("is_exposed", False)),
            )
        )
    return result


def render_graph_var_name_constants_block(
    graph_vars: List[GraphVarInfo],
    *,
    class_name: str = "GV",
) -> str:
    used: List[str] = []
    attr_pairs: List[Tuple[str, str]] = []
    for v in graph_vars:
        base_attr = make_valid_identifier(v.name)
        attr = generate_unique_name(base_attr, used, separator="_", start_index=2)
        used.append(attr)
        attr_pairs.append((attr, v.name))

    lines: List[str] = []
    lines.append(GV_BLOCK_START)
    lines.append(f"class {class_name}:")
    lines.append('    """节点图变量名常量（自动生成，用于减少字符串拼写风险与获得 IDE 补全）。"""')
    if not attr_pairs:
        lines.append("    pass")
    else:
        for attr, raw in attr_pairs:
            escaped = raw.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'    {attr} = "{escaped}"')
    lines.append(GV_BLOCK_END)
    return "\n".join(lines) + "\n"


def upsert_graph_var_name_constants_block(
    source_text: str,
    *,
    graph_vars: List[GraphVarInfo],
    insert_after_lineno: int | None,
    class_name: str = "GV",
) -> str:
    """Upsert the GV block. If not present, insert after the given line number (1-based)."""
    new_block = render_graph_var_name_constants_block(graph_vars, class_name=class_name)

    start_idx = source_text.find(GV_BLOCK_START)
    end_idx = source_text.find(GV_BLOCK_END)
    if start_idx >= 0 and end_idx >= 0 and end_idx >= start_idx:
        end_idx = end_idx + len(GV_BLOCK_END)
        # Replace the whole block region.
        before = source_text[:start_idx].rstrip("\n")
        after = source_text[end_idx:].lstrip("\n")
        merged = before + "\n\n" + new_block.rstrip("\n") + "\n\n" + after
        return merged + ("\n" if source_text.endswith("\n") else "")

    if not insert_after_lineno or insert_after_lineno <= 0:
        return source_text.rstrip("\n") + "\n\n" + new_block + ("\n" if source_text.endswith("\n") else "")

    lines = source_text.splitlines()
    insert_idx = min(max(insert_after_lineno, 0), len(lines))
    block_lines = new_block.rstrip("\n").splitlines()
    # Insert with a blank line before and after for readability.
    to_insert: List[str] = [""]
    to_insert.extend(block_lines)
    to_insert.append("")
    lines[insert_idx:insert_idx] = to_insert
    return "\n".join(lines) + ("\n" if source_text.endswith("\n") else "")


__all__ = [
    "GraphVarInfo",
    "GV_BLOCK_START",
    "GV_BLOCK_END",
    "find_graph_variables_decl_span",
    "normalize_graph_variables",
    "upsert_graph_var_name_constants_block",
]


