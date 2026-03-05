from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

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
    extract_declared_graph_vars,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
    read_source,
)


class GraphVarsDeclarationRule(ValidationRule):
    """【设置/获取节点图变量】的『变量名』必须在 GRAPH_VARIABLES 中声明。"""

    rule_id = "engine_code_graph_vars_decl"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        declared: Set[str] = extract_declared_graph_vars(tree, read_source(file_path))
        module_constants = collect_module_constants(tree)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(getattr(node, "func", None), ast.Name)
                ):
                    continue
                fname = node.func.id
                if not (
                    is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=fname,
                        semantic_id=SEMANTIC_GRAPH_VAR_SET,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=fname,
                        semantic_id=SEMANTIC_GRAPH_VAR_GET,
                    )
                ):
                    continue
                var_kw = None
                for kw in (node.keywords or []):
                    if kw.arg == VARIABLE_NAME_PORT_NAME:
                        var_kw = kw
                        break
                if var_kw is None:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_GRAPH_VAR_DECLARATION",
                            f"{line_span_text(node)}: 【{fname}】必须提供参数『{VARIABLE_NAME_PORT_NAME}』，且为字符串常量并在文件顶部的 GRAPH_VARIABLES 清单中声明",
                        )
                    )
                    continue
                value_node = var_kw.value

                # 变量名允许来自运行期表达式：当无法静态解析到明确的字符串时，跳过“声明存在性”强校验（降级为 warning）。
                resolved_var_name: str | None = None
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    resolved_var_name = value_node.value.strip()
                elif isinstance(value_node, ast.Name):
                    constant_value = module_constants.get(value_node.id)
                    if isinstance(constant_value, str):
                        resolved_var_name = constant_value.strip()

                if resolved_var_name is None:
                    target = value_node if hasattr(value_node, "lineno") else node
                    issues.append(
                        EngineIssue(
                            level="warning",
                            category=self.category,
                            code="CODE_GRAPH_VAR_DECLARATION_DYNAMIC_NAME",
                            message=(
                                f"{line_span_text(target)}: 【{fname}】的参数『{VARIABLE_NAME_PORT_NAME}』来自运行期表达式，"
                                "校验器无法静态判断其是否已在 GRAPH_VARIABLES 中声明；已跳过声明存在性校验。"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(target),
                        )
                    )
                    continue

                var_name = resolved_var_name
                if (not declared) or (var_name not in declared):
                    extra = ""
                    if declared:
                        preview = "、".join(sorted(list(declared))[:8])
                        more = "" if len(declared) <= 8 else "..."
                        extra = f"；已声明: {preview}{more}"
                    else:
                        extra = "；未在文件顶部声明任何 GRAPH_VARIABLES 图变量"
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            value_node,
                            "CODE_GRAPH_VAR_DECLARATION",
                            f"{line_span_text(value_node)}: 【{fname}】参数『{VARIABLE_NAME_PORT_NAME}』='{var_name}' 未在 GRAPH_VARIABLES 清单中声明{extra}",
                        )
                    )

        return issues


__all__ = ["GraphVarsDeclarationRule"]


