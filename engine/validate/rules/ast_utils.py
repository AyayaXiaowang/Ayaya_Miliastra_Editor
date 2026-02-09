from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import ValidationContext

from ..issue import EngineIssue
from engine.graph.utils.metadata_extractor import (
    extract_graph_variables_from_ast,
    extract_metadata_from_docstring,
)
from engine.utils.graph_path_inference import infer_graph_type_and_folder_path
from engine.utils.source_text import read_text


@lru_cache(maxsize=256)
def read_source(file_path: Path) -> str:
    # 兼容 Windows 常见的 UTF-8 BOM，避免 ast.parse 因 U+FEFF 失败
    return read_text(file_path)


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


def infer_graph_scope(ctx: "ValidationContext") -> str:
    """推断当前节点图文件的作用域（server/client）。

    说明：
    - 校验规则需要按作用域读取节点库（同名节点在不同作用域可能存在不同端口定义）；
    - 优先根据文件路径快速推断，其次回退到 docstring 的 `graph_type/scope` 字段；
    - 无法识别时默认 server（与引擎默认一致）。
    """
    if ctx.file_path is None:
        return "server"

    # 1) 路径快速推断（最稳定且无需依赖 docstring 格式）
    # 目录结构约定：<资源根>/节点图/<server|client>/...
    # 其中 <资源根> 可以是：assets/资源库/共享/ 或 assets/资源库/项目存档/<package_id>/
    inferred_type, _ = infer_graph_type_and_folder_path(ctx.file_path)
    if inferred_type:
        return inferred_type

    # 2) docstring 回退：graph_type / scope
    tree = get_cached_module(ctx)
    docstring = ast.get_docstring(tree) or ""
    meta = extract_metadata_from_docstring(docstring)
    scope_text = str(meta.graph_type or meta.scope or "").strip().lower()
    if scope_text in {"server", "client"}:
        return scope_text

    return "server"


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


