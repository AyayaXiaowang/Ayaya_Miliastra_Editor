from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    line_span_text,
)


class ClientFilterGraphSingleReturnRule(ValidationRule):
    """client 过滤器节点图返回值规则：

    - 过滤器节点图以返回值作为图输出（会被建模为“节点图结束(整数/布尔型)”的输入）；
    - 因此要求事件方法体**只能有一个 return**，且必须是方法体最后一条语句（禁止分支内提前 return）。

    设计动机：
    - 过滤器图的输出节点为纯数据节点，端口不允许多源输入；
    - 多个 return 会导致多出口/多结束节点，无法在不引入额外合流节点的前提下稳定建模。
    """

    rule_id = "engine_code_client_filter_graph_single_return"
    category = "客户端节点图"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        scope = infer_graph_scope(ctx)
        if scope != "client":
            return []

        file_path: Path = ctx.file_path
        normalized_path = file_path.as_posix()
        is_filter_graph = (
            ("/节点图/client/布尔过滤器节点图/" in normalized_path)
            or ("/节点图/client/整数过滤器节点图/" in normalized_path)
            or ("/节点图/client/本地过滤器节点图/" in normalized_path)
        )
        if not is_filter_graph:
            return []

        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for node in list(getattr(tree, "body", []) or []):
            if not isinstance(node, ast.ClassDef):
                continue

            for item in list(getattr(node, "body", []) or []):
                if not (isinstance(item, ast.FunctionDef) and item.name.startswith("on_")):
                    continue

                method_body = list(getattr(item, "body", []) or [])
                if not method_body:
                    continue

                # 要求：仅一个 return 且为最后一条语句
                returns = [n for n in ast.walk(item) if isinstance(n, ast.Return) and getattr(n, "value", None) is not None]
                last_stmt = method_body[-1]
                ok_last = isinstance(last_stmt, ast.Return) and getattr(last_stmt, "value", None) is not None
                ok_single = (len(returns) == 1) and (returns[0] is last_stmt)
                if ok_last and ok_single:
                    continue

                message = (
                    f"{line_span_text(item)}: client 过滤器节点图的事件方法 `{item.name}` 必须且只能在方法末尾 `return <值>` 一次；"
                    f"当前检测到 return 次数={len(returns)}。请将分支内提前 return 改写为："
                    "先计算结果变量，再在方法末尾统一 return。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        item,
                        "CODE_CLIENT_FILTER_GRAPH_RETURN_STYLE",
                        message,
                    )
                )

        return issues


__all__ = ["ClientFilterGraphSingleReturnRule"]


