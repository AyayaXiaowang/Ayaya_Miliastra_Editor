from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.common import VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import collect_module_constants
from engine.validate.node_semantics import (
    SEMANTIC_GRAPH_VAR_GET,
    SEMANTIC_GRAPH_VAR_SET,
    is_semantic_node_call,
)

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
)


_GRAPH_VAR_NAME_MAX_LEN = 20


def _resolve_string_constant(expr: ast.AST | None, module_constants: dict) -> str | None:
    if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), str):
        return str(expr.value).strip()
    if isinstance(expr, ast.Name):
        constant_value = module_constants.get(expr.id)
        if isinstance(constant_value, str):
            return constant_value.strip()
    return None


def _iter_graph_variable_config_name_exprs(tree: ast.Module) -> List[ast.AST]:
    """提取 GRAPH_VARIABLES 中每个 GraphVariableConfig 的 name 表达式节点（用于定位行号）。"""
    graph_vars_value: ast.AST | None = None
    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            for target in list(getattr(stmt, "targets", []) or []):
                if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES":
                    graph_vars_value = getattr(stmt, "value", None)
                    break
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            if isinstance(target, ast.Name) and target.id == "GRAPH_VARIABLES":
                graph_vars_value = getattr(stmt, "value", None)
        if graph_vars_value is not None:
            break

    if graph_vars_value is None or not isinstance(graph_vars_value, (ast.List, ast.Tuple)):
        return []

    results: List[ast.AST] = []
    for elt in list(getattr(graph_vars_value, "elts", []) or []):
        if not isinstance(elt, ast.Call):
            continue
        func = getattr(elt, "func", None)
        is_cfg_call = False
        if isinstance(func, ast.Name) and func.id == "GraphVariableConfig":
            is_cfg_call = True
        elif isinstance(func, ast.Attribute) and func.attr == "GraphVariableConfig":
            is_cfg_call = True
        if not is_cfg_call:
            continue

        # name=... 优先，其次兼容位置参数第 1 个
        name_expr: ast.AST | None = None
        for kw in list(getattr(elt, "keywords", []) or []):
            if kw.arg == "name":
                name_expr = getattr(kw, "value", None)
                break
        if name_expr is None:
            args = list(getattr(elt, "args", []) or [])
            if args:
                name_expr = args[0]
        if name_expr is not None:
            results.append(name_expr)
    return results


class GraphVarNameLengthRule(ValidationRule):
    """节点图变量名长度上限：Graph 变量（GRAPH_VARIABLES.name）与获取/设置调用的『变量名』均不得超过 20 字符。

    说明：
    - 长度统计按 Python 的 `len(str)`（Unicode 字符数）；
    - 对无法静态解析为字符串常量的写法，降级为 warning（无法判断长度）。
    """

    rule_id = "engine_code_graph_var_name_length"
    category = "节点图变量"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        module_constants = collect_module_constants(tree)

        issues: List[EngineIssue] = []

        # 1) GRAPH_VARIABLES 声明（仅普通节点图需要；复合节点一般不声明）
        if not bool(ctx.is_composite):
            for name_expr in _iter_graph_variable_config_name_exprs(tree):
                resolved = _resolve_string_constant(name_expr, module_constants)
                if resolved is None:
                    issues.append(
                        EngineIssue(
                            level="warning",
                            category=self.category,
                            code="CODE_GRAPH_VAR_NAME_DYNAMIC",
                            message=(
                                f"{line_span_text(name_expr)}: GRAPH_VARIABLES 中的 GraphVariableConfig.name "
                                "无法静态解析为字符串常量，已跳过长度上限校验。"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(name_expr),
                        )
                    )
                    continue

                name_text = resolved
                if name_text and len(name_text) > _GRAPH_VAR_NAME_MAX_LEN:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            name_expr,
                            "CODE_GRAPH_VAR_NAME_TOO_LONG",
                            (
                                f"{line_span_text(name_expr)}: 节点图变量名过长：{name_text!r} "
                                f"（len={len(name_text)}，上限={_GRAPH_VAR_NAME_MAX_LEN}）。"
                                "请压缩变量名（<=20）。"
                            ),
                        )
                    )

        # 2) 获取/设置节点图变量调用（普通节点图 + 复合节点都可能出现）
        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(getattr(node, "func", None), ast.Name)
                ):
                    continue
                call_name = str(node.func.id or "").strip()
                if not call_name:
                    continue

                is_graph_var_node = (
                    is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_GRAPH_VAR_SET,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_GRAPH_VAR_GET,
                    )
                )
                if not is_graph_var_node:
                    continue

                var_kw = None
                for kw in getattr(node, "keywords", []) or []:
                    if kw.arg == VARIABLE_NAME_PORT_NAME:
                        var_kw = kw
                        break
                if var_kw is None:
                    continue

                value_expr = getattr(var_kw, "value", None)
                resolved = _resolve_string_constant(value_expr, module_constants)
                if resolved is None:
                    target = value_expr if value_expr is not None else node
                    issues.append(
                        EngineIssue(
                            level="warning",
                            category=self.category,
                            code="CODE_GRAPH_VAR_NAME_DYNAMIC",
                            message=(
                                f"{line_span_text(target)}: 【{call_name}】的参数『{VARIABLE_NAME_PORT_NAME}』来自运行期表达式，"
                                "无法静态校验长度上限（<=20）；已跳过。"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(target),
                        )
                    )
                    continue

                name_text = resolved
                if name_text and len(name_text) > _GRAPH_VAR_NAME_MAX_LEN:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            value_expr if value_expr is not None else node,
                            "CODE_GRAPH_VAR_NAME_TOO_LONG",
                            (
                                f"{line_span_text(value_expr if value_expr is not None else node)}: "
                                f"节点图变量名过长：{name_text!r}（len={len(name_text)}，上限={_GRAPH_VAR_NAME_MAX_LEN}）。"
                                "请压缩变量名（<=20）。"
                            ),
                        )
                    )

        return issues


__all__ = ["GraphVarNameLengthRule"]

