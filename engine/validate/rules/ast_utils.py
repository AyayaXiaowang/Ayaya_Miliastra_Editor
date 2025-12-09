from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import ValidationContext

from ..issue import EngineIssue
from engine.graph.utils.metadata_extractor import extract_graph_variables_from_ast


@lru_cache(maxsize=256)
def read_source(file_path: Path) -> str:
    return file_path.read_text(encoding="utf-8")


@lru_cache(maxsize=256)
def parse_module(file_path: Path) -> ast.Module:
    source = read_source(file_path)
    return ast.parse(source, filename=str(file_path))


def get_cached_module(ctx: "ValidationContext") -> ast.Module:
    if ctx.file_path is None:
        raise ValueError("ValidationContext 缺少 file_path，无法解析 AST")
    cached = ctx.ast_cache.get(ctx.file_path)
    if cached is None:
        cached = parse_module(ctx.file_path)
        ctx.ast_cache[ctx.file_path] = cached
    return cached


def build_parent_map(tree: ast.AST) -> Dict[ast.AST, ast.AST]:
    parent_map: Dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent_map[child] = node
    return parent_map


def line_span_text(node: ast.AST) -> str:
    start_ln = getattr(node, "lineno", None)
    end_ln = getattr(node, "end_lineno", start_ln)
    if isinstance(start_ln, int):
        end_val = end_ln if isinstance(end_ln, int) else start_ln
        return f"第{start_ln}~{end_val}行"
    return "第?~?行"


def normalize_expr(expr: ast.AST) -> str:
    # 不使用 try/except，尽量使用 ast.unparse；失败时回退至类型名
    text = ast.unparse(expr)  # type: ignore[attr-defined]
    if not isinstance(text, str) or len(text) == 0:
        return expr.__class__.__name__
    return text


def extract_declared_graph_vars_from_code(tree: ast.Module) -> Set[str]:
    """从代码级 GRAPH_VARIABLES 声明中提取已声明的图变量名集合。"""
    declared: Set[str] = set()
    variables = extract_graph_variables_from_ast(tree)
    for entry in variables:
        name_value = entry.get("name")
        if isinstance(name_value, str):
            stripped = name_value.strip()
            if stripped:
                declared.add(stripped)
    return declared


def extract_declared_graph_vars(tree: ast.Module, source_text: str) -> Set[str]:
    """返回通过 GRAPH_VARIABLES 声明的图变量名集合。"""
    return extract_declared_graph_vars_from_code(tree)


def iter_class_methods(tree: ast.Module) -> Iterator[Tuple[ast.ClassDef, ast.FunctionDef]]:
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node, item


def create_rule_issue(
    rule: Any,
    file_path: Path,
    at: ast.AST,
    code: str,
    message: str,
) -> EngineIssue:
    return EngineIssue(
        level=getattr(rule, "default_level", "error"),
        category=getattr(rule, "category", "代码规范"),
        code=code,
        message=message,
        file=str(file_path),
        line_span=line_span_text(at),
    )


