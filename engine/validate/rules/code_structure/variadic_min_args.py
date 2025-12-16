from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, iter_class_methods, line_span_text
from ..node_index import variadic_min_args


class VariadicMinArgsRule(ValidationRule):
    """可变参数节点：至少提供指定数量的数据入参。"""

    rule_id = "engine_code_variadic_min_args"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        rules = variadic_min_args(ctx.workspace_path)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                fname = func.id
                if fname not in rules:
                    continue
                required = int(rules[fname])
                total_pos_args = len(getattr(node, "args", []) or [])
                provided_data_args = max(0, total_pos_args - 1)  # 跳过 self.game
                if provided_data_args < required:
                    if required == 1:
                        msg = (
                            f"{line_span_text(node)}: 【{fname}】不允许空参数，至少提供 1 个输入"
                        )
                    else:
                        msg = f"{line_span_text(node)}: 【{fname}】不允许空参数，至少提供 {required} 个输入（例如一对键值）"
                    issues.append(
                        create_rule_issue(
                            self, file_path, node, "CODE_VARIADIC_MIN_ARGS", msg
                        )
                    )

        return issues


__all__ = ["VariadicMinArgsRule"]


