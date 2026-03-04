from __future__ import annotations

import ast

from .syntax_sugar_rewriter_transformer_expr_call_attr import try_rewrite_attribute_call
from .syntax_sugar_rewriter_transformer_expr_call_builtin import try_rewrite_builtin_call


class _GraphCodeSyntaxSugarTransformerExprCallMixin:
    def visit_Call(self, node: ast.Call):  # noqa: N802
        # 先重写参数，再处理内置函数语法糖：
        # - len/abs/max/min
        # - int/float/str/bool（数据类型转换）
        # - round/floor/ceil（取整数运算，仅 server）
        clamp_rewritten = self._try_rewrite_server_clamp_min_max(node)
        if clamp_rewritten is not None:
            return clamp_rewritten

        time_call_rewritten = self._try_rewrite_time_time_call(node)
        if time_call_rewritten is not None:
            return time_call_rewritten

        datetime_call_rewritten = self._try_rewrite_datetime_calls(node)
        if datetime_call_rewritten is not None:
            return datetime_call_rewritten

        visited = self.generic_visit(node)
        if not isinstance(visited, ast.Call):
            return visited
        node = visited

        positional_args = list(getattr(node, "args", []) or [])
        keywords = list(getattr(node, "keywords", []) or [])

        func = getattr(node, "func", None)
        if isinstance(func, ast.Attribute):
            rewritten = try_rewrite_attribute_call(
                self,
                            node=node,
                func=func,
                positional_args=positional_args,
                keywords=keywords,
            )
            return rewritten if rewritten is not None else node

        if isinstance(func, ast.Name):
            builtin_name = str(getattr(func, "id", "") or "")
            rewritten = try_rewrite_builtin_call(
                self,
                            node=node,
                builtin_name=builtin_name,
                positional_args=positional_args,
                keywords=keywords,
            )
            return rewritten if rewritten is not None else node

        return node

