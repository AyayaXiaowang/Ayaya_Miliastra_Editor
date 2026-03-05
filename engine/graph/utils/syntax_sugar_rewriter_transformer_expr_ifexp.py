from __future__ import annotations

import ast
from typing import Optional

from .syntax_sugar_rewriter_issue import SyntaxSugarRewriteIssue


class _GraphCodeSyntaxSugarTransformerExprIfExpMixin:
    def visit_IfExp(self, node: ast.IfExp):  # noqa: N802
        """三元表达式语法糖：X if 条件 else Y

        约束：
        - 仅在普通节点图启用（复合节点内部禁止嵌套其它复合节点）；
        - 仅 server 作用域；
        - 目前仅支持“整数/浮点数”两类输出（使用共享复合节点封装）。
        """
        if not (self.enable_shared_composite_sugars and self.scope == "server"):
            return self.generic_visit(node)

        test_expr = getattr(node, "test", None)
        true_expr = getattr(node, "body", None)
        false_expr = getattr(node, "orelse", None)
        if not (isinstance(test_expr, ast.expr) and isinstance(true_expr, ast.expr) and isinstance(false_expr, ast.expr)):
            return self.generic_visit(node)

        # 类型推断：优先用分支的显式类型/常量类型，避免误判。
        inferred_type = _infer_numeric_type_for_ifexp(true_expr, false_expr, self.var_type_by_name)
        if inferred_type not in {"整数", "浮点数"}:
            return self.generic_visit(node)

        visited_test = self.visit(test_expr)
        visited_true = self.visit(true_expr)
        visited_false = self.visit(false_expr)
        if isinstance(visited_test, ast.expr):
            test_expr = visited_test
        if isinstance(visited_true, ast.expr):
            true_expr = visited_true
        if isinstance(visited_false, ast.expr):
            false_expr = visited_false

        if inferred_type == "整数":
            class_name = "三元表达式_整数"
            alias = "_共享复合_三元表达式_整数"
        else:
            class_name = "三元表达式_浮点数"
            alias = "_共享复合_三元表达式_浮点数"

        self._require_shared_composite(alias=alias, class_name=class_name)
        return self._shared_composite_instance_call(
            alias=alias,
            method_name="按条件选择",
            keywords=[
                ast.keyword(arg="条件", value=test_expr),
                ast.keyword(arg="条件为真输出", value=true_expr),
                ast.keyword(arg="条件为假输出", value=false_expr),
            ],
            source_node=node,
        )


def _infer_numeric_type_for_ifexp(
    true_expr: ast.expr,
    false_expr: ast.expr,
    var_type_by_name: dict[str, str],
) -> Optional[str]:
    def _infer_one(expr: ast.expr) -> Optional[str]:
        if isinstance(expr, ast.Constant):
            value = getattr(expr, "value", None)
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return "整数"
            if isinstance(value, float):
                return "浮点数"
            return None
        if isinstance(expr, ast.Name):
            type_text = str(var_type_by_name.get(expr.id, "") or "").strip()
            if type_text in {"整数", "浮点数"}:
                return type_text
        return None

    true_type = _infer_one(true_expr)
    false_type = _infer_one(false_expr)
    if true_type == "浮点数" or false_type == "浮点数":
        return "浮点数"
    if true_type == "整数" and false_type == "整数":
        return "整数"
    return None


