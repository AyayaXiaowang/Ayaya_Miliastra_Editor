from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class SyntaxSugarRewriteIssue:
    """语法糖重写过程中的问题。

    约定：
    - issue.node 必须是可定位行号的 AST 节点；
    - 不做 try/except：若 AST 结构异常直接抛出。
    """

    code: str
    message: str
    node: ast.AST


