from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    extract_declared_graph_vars,
    get_cached_module,
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
        declared: Set[str] = extract_declared_graph_vars(tree, read_source(file_path))
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(getattr(node, "func", None), ast.Name)
                ):
                    continue
                fname = node.func.id
                if fname not in ("设置节点图变量", "获取节点图变量"):
                    continue
                var_kw = None
                for kw in (node.keywords or []):
                    if kw.arg == "变量名":
                        var_kw = kw
                        break
                if var_kw is None:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_GRAPH_VAR_DECLARATION",
                            f"{line_span_text(node)}: 【{fname}】必须提供参数『变量名』，且为字符串常量并在文件顶部的 GRAPH_VARIABLES 清单中声明",
                        )
                    )
                    continue
                value_node = var_kw.value
                if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
                    var_name = value_node.value.strip()
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
                                f"{line_span_text(value_node)}: 【{fname}】参数『变量名』='{var_name}' 未在 GRAPH_VARIABLES 清单中声明{extra}",
                            )
                        )
                else:
                    target = value_node if hasattr(value_node, "lineno") else node
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            target,
                            "CODE_GRAPH_VAR_DECLARATION",
                            f"{line_span_text(target)}: 【{fname}】的参数『变量名』必须为字符串常量，并在 GRAPH_VARIABLES 清单中声明",
                        )
                    )

        return issues


__all__ = ["GraphVarsDeclarationRule"]


