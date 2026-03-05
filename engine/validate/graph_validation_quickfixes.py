from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Set, Tuple

from engine.graph.utils.ast_utils import collect_module_constants
from engine.graph.utils.metadata_extractor import extract_graph_variables_from_ast
from engine.nodes.composite_file_policy import is_composite_definition_file
from engine.utils.graph_path_inference import infer_graph_type_and_folder_path
from engine.utils.path_utils import normalize_slash
from engine.utils.source_text import read_source_text
from engine.validate.node_semantics import (
    SEMANTIC_GRAPH_VAR_GET,
    SEMANTIC_GRAPH_VAR_SET,
    is_semantic_node_call,
)

from .rules.ast_utils import build_parent_map

__all__ = [
    "QuickFixAction",
    "apply_graph_validation_quickfixes",
]


@dataclass(frozen=True)
class QuickFixAction:
    file_path: str
    kind: str
    summary: str
    detail: Dict[str, object]


def apply_graph_validation_quickfixes(
    targets: Sequence[Path],
    workspace_root: Path,
    *,
    dry_run: bool,
) -> List[QuickFixAction]:
    """对 validate-graphs 的 targets 执行一组“可自动修复”的修复动作。

    设计原则：
    - 默认只读：只有显式开启时才允许写盘（由调用方传入 dry_run=False 控制）。
    - 只做“确定性、低风险、可回退”的补齐类修复；不做会改变业务语义的重构。
    - 不使用 try/except；修复过程出现异常应直接抛出，由上层决定是否中止。
    """
    actions: List[QuickFixAction] = []
    for file_path in list(targets or []):
        if not isinstance(file_path, Path):
            continue
        if not file_path.exists():
            continue
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() != ".py":
            continue
        if is_composite_definition_file(file_path):
            continue
        actions.extend(
            _fix_missing_graph_variables_declarations(
                file_path=file_path,
                workspace_root=workspace_root,
                dry_run=bool(dry_run),
            )
        )
    return actions


def _infer_graph_scope_for_file(file_path: Path) -> str:
    scope, _folder_path = infer_graph_type_and_folder_path(file_path)
    if scope in {"server", "client"}:
        return scope
    return "server"


def _extract_string_literal(value_node: ast.AST, module_constants: Mapping[str, object]) -> str | None:
    if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
        text = value_node.value.strip()
        return text or None
    if isinstance(value_node, ast.Name):
        constant_value = module_constants.get(value_node.id)
        if isinstance(constant_value, str):
            text = constant_value.strip()
            return text or None
    return None


def _collect_type_hints_from_module(tree: ast.Module) -> Dict[str, str]:
    """收集模块顶层“命名常量”的类型注解：用于推断 GraphVariableConfig.variable_type。"""
    result: Dict[str, str] = {}
    for stmt in tree.body:
        if not isinstance(stmt, ast.AnnAssign):
            continue
        if not isinstance(stmt.target, ast.Name):
            continue
        ann = stmt.annotation
        if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
            type_name = ann.value.strip()
            if type_name:
                result[stmt.target.id] = type_name
    return result


def _collect_local_type_hints(tree: ast.Module) -> Dict[ast.FunctionDef, Dict[str, str]]:
    """收集每个方法体内的局部变量类型注解（形如 `x: "整数" = ...`）。"""
    mapping: Dict[ast.FunctionDef, Dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        locals_map: Dict[str, str] = {}
        for sub in ast.walk(node):
            if not isinstance(sub, ast.AnnAssign):
                continue
            if not isinstance(sub.target, ast.Name):
                continue
            ann = sub.annotation
            if isinstance(ann, ast.Constant) and isinstance(ann.value, str):
                type_name = ann.value.strip()
                if type_name:
                    locals_map[sub.target.id] = type_name
        mapping[node] = locals_map
    return mapping


def _infer_expr_type_name(
    expr: ast.AST,
    *,
    local_types: Mapping[str, str],
    module_types: Mapping[str, str],
    module_constants: Mapping[str, object],
) -> str | None:
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, bool):
            return "布尔值"
        if isinstance(expr.value, int) and not isinstance(expr.value, bool):
            return "整数"
        if isinstance(expr.value, float):
            return "浮点数"
        if isinstance(expr.value, str):
            return "字符串"
        return None

    if isinstance(expr, ast.Name):
        if expr.id in local_types:
            return local_types[expr.id]
        if expr.id in module_types:
            return module_types[expr.id]
        const_val = module_constants.get(expr.id)
        if isinstance(const_val, bool):
            return "布尔值"
        if isinstance(const_val, int) and not isinstance(const_val, bool):
            return "整数"
        if isinstance(const_val, float):
            return "浮点数"
        if isinstance(const_val, str):
            return "字符串"
        return None

    if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
        fname = expr.func.id
        if fname == "int":
            return "整数"
        if fname == "float":
            return "浮点数"
        if fname == "str":
            return "字符串"
        if fname == "bool":
            return "布尔值"
        return None

    return None


def _choose_graph_var_type_name(type_candidates: Iterable[str]) -> tuple[str, bool]:
    """返回 (type_name, is_confident)。"""
    items = [str(x).strip() for x in type_candidates if str(x).strip()]
    if not items:
        return "整数", False
    unique = sorted(set(items), key=lambda x: x.casefold())
    if len(unique) == 1:
        return unique[0], True
    # 发生冲突：以“出现次数最多”的为准，仍标记为不确定
    counts: Dict[str, int] = {}
    for t in items:
        counts[t] = counts.get(t, 0) + 1
    chosen = max(unique, key=lambda x: (counts.get(x, 0), -len(x)))
    return chosen, False


def _build_graph_variable_config_block(
    *,
    var_name: str,
    variable_type: str,
    confident: bool,
    indent: str,
) -> str:
    inner = indent + " " * 4
    desc = "自动补齐：由 validate-graphs --fix 生成，占位；请补充默认值与说明。"
    if not confident:
        desc = f"{desc}（类型推断不确定，请确认 variable_type）"
    lines = [
        f"{indent}GraphVariableConfig(",
        f'{inner}name="{var_name}",',
        f'{inner}variable_type="{variable_type}",',
        f"{inner}default_value=None,",
        f'{inner}description="{desc}",',
        f"{inner}is_exposed=False,",
        f"{indent}),",
    ]
    return "\n".join(lines)


def _fix_missing_graph_variables_declarations(
    *,
    file_path: Path,
    workspace_root: Path,
    dry_run: bool,
) -> List[QuickFixAction]:
    """修复：Graph Code 中使用了【设置/获取节点图变量】但未在 GRAPH_VARIABLES 中声明。"""
    source = read_source_text(file_path)
    text = source.text
    tree = ast.parse(text, filename=str(file_path))

    declared_vars: Set[str] = set()
    for entry in extract_graph_variables_from_ast(tree):
        name_val = entry.get("name")
        if isinstance(name_val, str) and name_val.strip():
            declared_vars.add(name_val.strip())

    scope = _infer_graph_scope_for_file(file_path)
    module_constants = collect_module_constants(tree)
    module_types = _collect_type_hints_from_module(tree)
    local_types_by_func = _collect_local_type_hints(tree)

    parent_map = build_parent_map(tree)

    used_var_names: List[str] = []
    type_candidates_by_var: Dict[str, List[str]] = {}

    def record_type_candidate(var_name: str, type_name: str) -> None:
        key = str(var_name).strip()
        if not key:
            return
        t = str(type_name).strip()
        if not t:
            return
        type_candidates_by_var.setdefault(key, []).append(t)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name)):
            continue
        fname = node.func.id
        is_get = is_semantic_node_call(
            workspace_path=workspace_root,
            scope=scope,
            call_name=fname,
            semantic_id=SEMANTIC_GRAPH_VAR_GET,
        )
        is_set = is_semantic_node_call(
            workspace_path=workspace_root,
            scope=scope,
            call_name=fname,
            semantic_id=SEMANTIC_GRAPH_VAR_SET,
        )
        if not (is_get or is_set):
            continue

        var_kw = None
        value_kw = None
        for kw in node.keywords or []:
            if kw.arg == "变量名":
                var_kw = kw
            if kw.arg == "变量值":
                value_kw = kw

        if var_kw is None:
            continue
        var_name = _extract_string_literal(var_kw.value, module_constants)
        if var_name is None:
            continue

        used_var_names.append(var_name)

        # 1) 获取节点图变量：优先从承接变量的类型注解推断
        if is_get:
            parent = parent_map.get(node)
            if isinstance(parent, ast.AnnAssign) and parent.value is node:
                ann = parent.annotation
                if isinstance(ann, ast.Constant) and isinstance(ann.value, str) and ann.value.strip():
                    record_type_candidate(var_name, ann.value.strip())
            continue

        # 2) 设置节点图变量：从变量值表达式推断
        if is_set and value_kw is not None:
            locals_map: Mapping[str, str] = {}
            parent = parent_map.get(node)
            while parent is not None and not isinstance(parent, ast.FunctionDef):
                parent = parent_map.get(parent)
            if isinstance(parent, ast.FunctionDef):
                locals_map = local_types_by_func.get(parent, {})

            inferred = _infer_expr_type_name(
                value_kw.value,
                local_types=locals_map,
                module_types=module_types,
                module_constants=module_constants,
            )
            if inferred:
                record_type_candidate(var_name, inferred)

    missing_vars = [name for name in used_var_names if name and name not in declared_vars]
    if not missing_vars:
        return []

    # 去重保持顺序
    missing_unique: List[str] = []
    seen: Set[str] = set()
    for name in missing_vars:
        if name in seen:
            continue
        seen.add(name)
        missing_unique.append(name)

    new_entries: List[Tuple[str, str, bool]] = []
    for name in missing_unique:
        inferred_type, confident = _choose_graph_var_type_name(type_candidates_by_var.get(name, []))
        new_entries.append((name, inferred_type, confident))

    # --- patch text ---
    new_text, changed = _patch_graph_variables_declaration_text(
        original_text=text,
        file_path=file_path,
        new_entries=new_entries,
    )
    if not changed:
        return []

    if not dry_run:
        has_bom = source.raw_bytes.startswith(b"\xef\xbb\xbf")
        encoding = "utf-8-sig" if has_bom else "utf-8"
        file_path.write_text(new_text, encoding=encoding)

    resolved_file = file_path.resolve()
    resolved_workspace = workspace_root.resolve()
    rel = normalize_slash(str(resolved_file))
    ws_prefix = normalize_slash(str(resolved_workspace)) + "/"
    if rel.startswith(ws_prefix):
        rel = rel[len(ws_prefix) :]
    else:
        rel = normalize_slash(str(file_path))

    added_names = [name for name, _t, _c in new_entries]
    type_preview = {name: t for name, t, _c in new_entries}
    return [
        QuickFixAction(
            file_path=rel,
            kind="add_graph_variables",
            summary=f"补齐 GRAPH_VARIABLES：新增 {len(new_entries)} 个变量声明",
            detail={"added": added_names, "types": type_preview},
        )
    ]


def _patch_graph_variables_declaration_text(
    *,
    original_text: str,
    file_path: Path,
    new_entries: Sequence[Tuple[str, str, bool]],
) -> tuple[str, bool]:
    """在源码中补齐 GRAPH_VARIABLES 声明（尽量保持原有格式）。"""
    if not new_entries:
        return original_text, False

    lines = original_text.splitlines(keepends=True)
    tree = ast.parse(original_text, filename=str(file_path))

    assign_node: ast.Assign | ast.AnnAssign | None = None
    list_node: ast.List | None = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES" and isinstance(stmt.value, ast.List):
                    assign_node = stmt
                    list_node = stmt.value
                    break
        if assign_node is not None:
            break
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == "GRAPH_VARIABLES" and isinstance(stmt.value, ast.List):
                assign_node = stmt
                list_node = stmt.value
                break

    if assign_node is None or list_node is None:
        # 没有 GRAPH_VARIABLES：插入一个新块（优先放在 prelude import 之后）
        insert_at = _find_graph_variables_insert_line(lines)
        block = _render_graph_variables_block(new_entries)
        insertion = block + "\n\n"
        lines.insert(insert_at, insertion)
        return "".join(lines), True

    list_start = getattr(list_node, "lineno", None)
    list_end = getattr(list_node, "end_lineno", None)
    if not isinstance(list_start, int) or not isinstance(list_end, int):
        return original_text, False

    if list_start == list_end:
        # 过于紧凑的一行声明，自动补齐可能会破坏格式；先跳过
        return original_text, False

    closing_idx = list_end - 1  # 0-based
    if closing_idx < 0 or closing_idx > len(lines):
        return original_text, False

    # 推断条目缩进：优先从已有 GraphVariableConfig(...) 行推断，否则使用 4 空格
    entry_indent = " " * 4
    scan_start = max(list_start - 1, 0)
    scan_end = min(closing_idx, len(lines))
    for i in range(scan_start, scan_end):
        raw = lines[i].lstrip("\r\n")
        if "GraphVariableConfig" not in raw:
            continue
        prefix = lines[i].split("G", 1)[0]
        if prefix.strip() == "":
            entry_indent = prefix
            break

    # 确保最后一个元素与新元素之间有逗号分隔
    _ensure_list_trailing_comma(lines, start_idx=scan_start, closing_idx=closing_idx)

    # 生成新增条目（稳定排序：按变量名）
    rendered_blocks: List[str] = []
    for name, type_name, confident in sorted(list(new_entries), key=lambda x: str(x[0]).casefold()):
        rendered_blocks.append(
            _build_graph_variable_config_block(
                var_name=str(name),
                variable_type=str(type_name),
                confident=bool(confident),
                indent=entry_indent,
            )
        )
    insertion_text = "\n".join(rendered_blocks) + "\n"
    lines.insert(closing_idx, insertion_text)
    return "".join(lines), True


def _find_graph_variables_insert_line(lines: Sequence[str]) -> int:
    """返回应插入 GRAPH_VARIABLES 块的行索引（0-based，插入点）。"""
    # 优先：插在 prelude import 之后
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("from app.runtime.engine.graph_prelude_") and "import *" in stripped:
            return idx + 1
    # 回退：插在第一个 class 定义之前
    for idx, line in enumerate(lines):
        if line.startswith("class "):
            return idx
    return 0


def _render_graph_variables_block(new_entries: Sequence[Tuple[str, str, bool]]) -> str:
    entry_indent = " " * 4
    blocks: List[str] = []
    for name, type_name, confident in sorted(list(new_entries), key=lambda x: str(x[0]).casefold()):
        blocks.append(
            _build_graph_variable_config_block(
                var_name=str(name),
                variable_type=str(type_name),
                confident=bool(confident),
                indent=entry_indent,
            )
        )
    body = "\n".join(blocks)
    return "\n".join(
        [
            "GRAPH_VARIABLES: list[GraphVariableConfig] = [",
            body,
            "]",
        ]
    )


def _ensure_list_trailing_comma(lines: List[str], *, start_idx: int, closing_idx: int) -> None:
    """确保 closing bracket 之前的最后一个有效元素行带逗号。"""
    if closing_idx <= 0:
        return
    i = closing_idx - 1
    while i >= start_idx:
        line = lines[i]
        # 保留行尾换行符
        newline = ""
        if line.endswith("\r\n"):
            newline = "\r\n"
        elif line.endswith("\n"):
            newline = "\n"
        core = line[:-len(newline)] if newline else line
        if core.strip() == "":
            i -= 1
            continue
        # 空列表：上一行是 '['，不需要逗号
        if core.rstrip().endswith("["):
            return
        # 已有逗号
        head, sep, tail = core.partition("#")
        head_r = head.rstrip()
        if head_r.endswith(","):
            return
        # 追加逗号（放在注释之前）
        if sep:
            lines[i] = f"{head_r}, {sep}{tail}{newline}"
        else:
            lines[i] = f"{head_r},{newline}"
        return


