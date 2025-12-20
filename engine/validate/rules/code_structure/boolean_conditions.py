from __future__ import annotations

import ast
from pathlib import Path
from typing import List, Set

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
from ..node_index import boolean_node_names


def _is_boolean_expr(
    expr: ast.expr, boolean_funcs: Set[str], bool_vars_assigned: Set[str]
) -> bool:
    """判断表达式是否为布尔类型"""
    # True/False
    if isinstance(expr, ast.Constant):
        return isinstance(getattr(expr, "value", None), bool)
    # 变量：要求来自布尔来源
    if isinstance(expr, ast.Name):
        return expr.id in bool_vars_assigned
    # 调用：要求布尔函数
    if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
        return expr.func.id in boolean_funcs
    # not X
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _is_boolean_expr(expr.operand, boolean_funcs, bool_vars_assigned)
    # X and Y / X or Y
    if isinstance(expr, ast.BoolOp):
        values = getattr(expr, "values", [])
        if not values:
            return False
        return all(
            _is_boolean_expr(value, boolean_funcs, bool_vars_assigned) for value in values
        )
    # 比较表达式
    if isinstance(expr, ast.Compare):
        return True
    return False


def _contains_inline_compare(expr: ast.expr) -> bool:
    """判断表达式内是否存在 Python 比较（==, !=, is, in 等）。"""
    for inner in ast.walk(expr):
        if isinstance(inner, ast.Compare):
            return True
    return False


class IfBooleanRule(ValidationRule):
    """if 条件必须为布尔表达式。"""

    rule_id = "engine_code_if_boolean"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        boolean_funcs = boolean_node_names(ctx.workspace_path, scope)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            bool_vars_assigned: Set[str] = set()
            # 收集布尔变量赋值
            for node in ast.walk(method):
                targets = []
                value = None
                annotation_is_bool: bool = False

                # 普通赋值：flag = True / flag = 是否相等(...)
                if isinstance(node, ast.Assign):
                    targets = list(getattr(node, "targets", []) or [])
                    value = getattr(node, "value", None)

                # 带类型注解的赋值：flag: "布尔值" = 是否相等(...)
                elif isinstance(node, ast.AnnAssign):
                    target = getattr(node, "target", None)
                    if isinstance(target, ast.Name):
                        targets = [target]
                    elif isinstance(target, ast.Tuple):
                        targets = list(getattr(target, "elts", []) or [])
                    value = getattr(node, "value", None)
                    annotation = getattr(node, "annotation", None)
                    if (
                        isinstance(annotation, ast.Constant)
                        and isinstance(getattr(annotation, "value", None), str)
                        and str(annotation.value).strip() == "布尔值"
                    ):
                        annotation_is_bool = True

                if not targets or value is None:
                    continue

                # 带“布尔值”类型注解的变量：视为布尔来源（允许 if / if not 直接使用）
                if annotation_is_bool:
                    for tgt in targets:
                        if isinstance(tgt, ast.Name):
                            bool_vars_assigned.add(tgt.id)

                # 常量布尔赋值
                if isinstance(value, ast.Constant) and isinstance(
                    getattr(value, "value", None), bool
                ):
                    for tgt in targets:
                        if isinstance(tgt, ast.Name):
                            bool_vars_assigned.add(tgt.id)
                # 布尔节点调用赋值
                if isinstance(value, ast.Call) and isinstance(
                    getattr(value, "func", None), ast.Name
                ):
                    fname = value.func.id
                    if fname in boolean_funcs:
                        for tgt in targets:
                            if isinstance(tgt, ast.Name):
                                bool_vars_assigned.add(tgt.id)

            # 检查 if 条件
            for node in ast.walk(method):
                if not isinstance(node, ast.If):
                    continue
                # 必须是布尔表达式
                is_boolean_expr = _is_boolean_expr(
                    node.test, boolean_funcs, bool_vars_assigned
                )
                if not is_boolean_expr:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_IF_NON_BOOL_CONDITION",
                            f"{line_span_text(node)}: if 条件必须为布尔类型；请使用布尔节点或其输出赋值后的变量，禁止将非布尔数据直接作为条件",
                        )
                    )
                    continue
                if _contains_inline_compare(node.test):
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node.test,
                            "CODE_IF_INLINE_COMPARISON",
                            f"{line_span_text(node.test)}: 禁止在 if 条件中直接书写 Python 比较（如 'A == B' 或 'X is None'）；请改用比较类节点输出，或先将布尔结果赋值给变量后再分支",
                        )
                    )

        return issues


class NoDirectLogicNotCallInIfRule(ValidationRule):
    """禁止在 if 条件中直接调用【逻辑非运算(...)】。

    背景：
    - `if 逻辑非运算(布尔条件): ...` 在 UI 中往往会导致“主流程从否分支接续”，阅读体验较差；
    - 更推荐的写法是“正向条件 + else 提前 return/执行”，使主流程从“是”分支接续。

    推荐改写：
    - 守卫式返回：
      - 不推荐：`if 逻辑非运算(...): return`
      - 推荐：`if 条件: pass else: return`
    - 正向分支：
      - 推荐：`if 条件: ... else: return`
    """

    rule_id = "engine_code_if_no_direct_logic_not_call"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.If):
                    continue
                test = getattr(node, "test", None)
                if not isinstance(test, ast.Call):
                    continue
                func = getattr(test, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                if func.id != "逻辑非运算":
                    continue

                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        test,
                        "CODE_IF_DIRECT_LOGIC_NOT_CALL",
                        f"{line_span_text(test)}: 禁止在 if 条件中直接调用【逻辑非运算】；请改写为正向条件（例如 `if 条件: pass else: return` 或 `if 条件: ... else: return`），避免在 UI 中出现“if 逻辑非 → 主流程接否分支”的阅读负担",
                    )
                )

        return issues


class IfBoolEqualityToConstRule(ValidationRule):
    """提醒：避免在 if 条件中写 `是否相等(布尔值, True/False)` 的冗余比较。

    目的：
    - `if 是否相等(x, True)` 在 UI 中会引入额外的【是否相等】节点，读起来不如直接 `if x:` 直观；
    - 对布尔值而言，和 True/False 做等号比较通常没有信息增量，建议人工确认是否真的需要。
    """

    rule_id = "engine_code_if_bool_equality_to_const"
    category = "代码规范"
    default_level = "warning"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.If):
                    continue
                test = getattr(node, "test", None)
                if not (
                    isinstance(test, ast.Call)
                    and isinstance(getattr(test, "func", None), ast.Name)
                ):
                    continue
                if test.func.id != "是否相等":
                    continue

                # 是否相等(self.game, 输入1=..., 输入2=...)
                kw_map = {
                    kw.arg: kw.value
                    for kw in (test.keywords or [])
                    if isinstance(kw, ast.keyword) and isinstance(kw.arg, str)
                }
                left = kw_map.get("输入1")
                right = kw_map.get("输入2")
                if left is None or right is None:
                    continue

                # 仅关注与 True/False 的比较
                left_is_bool_const = isinstance(left, ast.Constant) and isinstance(
                    getattr(left, "value", None), bool
                )
                right_is_bool_const = isinstance(right, ast.Constant) and isinstance(
                    getattr(right, "value", None), bool
                )
                if not (left_is_bool_const or right_is_bool_const):
                    continue

                bool_value = (
                    left.value if left_is_bool_const else right.value
                )  # type: ignore[attr-defined]
                other_expr = right if left_is_bool_const else left
                other_text = (
                    ast.unparse(other_expr) if hasattr(ast, "unparse") else "布尔变量"
                )

                if bool_value is True:
                    suggestion = (
                        f"建议直接写 `if {other_text}: ...`（例如守卫式：`if {other_text}: return`）"
                    )
                else:
                    suggestion = (
                        f"建议避免写 `== False`；可改为正向条件 `if {other_text}: pass else: ...`，"
                        f"或先用【逻辑非运算】得到取反变量再分支"
                    )

                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        test,
                        "CODE_IF_BOOL_EQUALITY_TO_CONST",
                        f"{line_span_text(test)}: if 条件使用了【是否相等(布尔值, {bool_value})】的冗余比较；{suggestion}。请确认该比较是否真的有意义",
                    )
                )

        return issues


__all__ = [
    "IfBooleanRule",
    "NoDirectLogicNotCallInIfRule",
    "IfBoolEqualityToConstRule",
]


