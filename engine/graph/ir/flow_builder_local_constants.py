from __future__ import annotations

import ast
from typing import List

from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value

from .var_env import VarEnv


def scan_and_register_local_constants(*, env: VarEnv, body: List[ast.stmt]) -> None:
    """预扫描方法体内“命名常量”赋值，写入 VarEnv.local_const_values。

    重要：
    - parse_method_body 会被递归用于 if/match/for 的分支体解析；
    - 因此这里不会清空已有常量，而是在当前作用域基础上增量补充/覆盖：
      - 外层常量在分支体内仍可被引用；
      - 分支体内新增/覆盖的常量在该次解析过程中可用。
    """
    method_module = ast.Module(body=list(body or []), type_ignores=[])

    # 第一遍：收集可静态提取的常量
    for stmt in ast.walk(method_module):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            value_expr = getattr(stmt, "value", None)
            if not isinstance(value_expr, ast.expr):
                continue
            const_val = extract_constant_value(value_expr)
            if const_val is NOT_EXTRACTABLE:
                continue
            env.set_local_constant(targets[0].id, const_val)
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            value_expr = getattr(stmt, "value", None)
            if not isinstance(target, ast.Name) or value_expr is None:
                continue
            if not isinstance(value_expr, ast.expr):
                continue
            const_val = extract_constant_value(value_expr)
            if const_val is NOT_EXTRACTABLE:
                continue
            env.set_local_constant(target.id, const_val)

    # 第二遍：允许“命名常量引用命名常量”（例如 B = A），只要 A 已在第一遍收集到。
    for stmt in ast.walk(method_module):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            target_name = str(targets[0].id or "").strip()
            if not target_name or env.has_local_constant(target_name):
                continue
            value_expr = getattr(stmt, "value", None)
            if isinstance(value_expr, ast.Name) and env.has_local_constant(value_expr.id):
                env.set_local_constant(target_name, env.get_local_constant(value_expr.id))
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            value_expr = getattr(stmt, "value", None)
            if not isinstance(target, ast.Name) or value_expr is None:
                continue
            target_name = str(target.id or "").strip()
            if not target_name or env.has_local_constant(target_name):
                continue
            if isinstance(value_expr, ast.Name) and env.has_local_constant(value_expr.id):
                env.set_local_constant(target_name, env.get_local_constant(value_expr.id))

