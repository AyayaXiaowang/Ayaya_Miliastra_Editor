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
    iter_class_methods,
    line_span_text,
)


def _is_typed_literal_assignment(node: ast.AST) -> bool:
    """判断是否为“带中文类型注解 + 字面量赋值”的声明形式。

    例：
        零: "整数" = 0
        标识: "配置ID" = "1077936129"
    """
    if not isinstance(node, ast.AnnAssign):
        return False
    target = getattr(node, "target", None)
    annotation = getattr(node, "annotation", None)
    value = getattr(node, "value", None)
    if not isinstance(target, ast.Name):
        return False
    if not isinstance(annotation, ast.Constant):
        return False
    if not isinstance(getattr(annotation, "value", None), str):
        return False
    text = str(annotation.value).strip()
    if not text:
        return False
    return _is_literal_expression(value)


def _collect_module_level_constant_var_names(tree: ast.AST) -> Set[str]:
    """收集模块顶层“命名常量”变量名。

    背景：
    - 模块顶层的 `常量: "类型" = 字面量` 通常用于为节点入参提供可复用的常量值。
    - 对这类“命名常量”，规则仍禁止在方法体中用赋值语句把它复制到其它运行时变量，避免把常量当“变量初始化来源”产生误导。
    - 但方法体内的 `变量: "类型" = 字面量` 允许作为“端口常量”的可读写法（见规则 apply 中的例外）。
      注意：方法体内的这类“端口常量”自身允许声明，但同样禁止再通过赋值语句复制到新变量（见 apply 中的 alias 规则）。
    """
    out: Set[str] = set()
    if not isinstance(tree, ast.Module):
        return out
    for stmt in list(getattr(tree, "body", []) or []):
        if not _is_typed_literal_assignment(stmt):
            continue
        target = getattr(stmt, "target", None)
        if isinstance(target, ast.Name):
            out.add(target.id)
    return out


def _collect_method_level_typed_literal_var_names(method: ast.AST) -> Set[str]:
    """收集方法体内“带中文类型注解 + 字面量赋值”的变量名。

    说明：
    - 该写法允许作为端口常量（提高可读性），但仍禁止把它再赋值复制到新变量；
    - 因此这里仅作为“禁止 const alias 复制”的来源集合，不影响其自身声明的合法性。
    """
    out: Set[str] = set()
    for node in ast.walk(method):
        if not _is_typed_literal_assignment(node):
            continue
        target = getattr(node, "target", None)
        if isinstance(target, ast.Name):
            out.add(target.id)
    return out


def _is_literal_expression(expr: ast.AST | None) -> bool:
    """判断表达式是否是纯字面量（含正负号包裹）。"""
    if expr is None:
        return False
    if isinstance(expr, ast.Constant):
        if getattr(expr, "value", None) is None:
            return False
        return True
    if (
        isinstance(expr, ast.UnaryOp)
        and isinstance(expr.op, (ast.USub, ast.UAdd))
        and isinstance(expr.operand, ast.Constant)
    ):
        return True
    return False


class NoLiteralAssignmentRule(ValidationRule):
    """禁止使用 Python 常量直接赋值（应依附节点输出或事件参数）。

    例外：
    - 方法体内允许“带中文类型注解 + 字面量赋值”作为端口常量的可读写法，例如：
        零: "整数" = 0
        秒: "浮点数" = 1.0
        文案: "字符串" = "hello"
    - 模块顶层允许“命名常量”声明（同上形式），用于为节点入参提供可复用常量值；
      但仍禁止在方法体内通过赋值语句把这类常量复制到其它变量（避免把常量当“变量初始化来源”）。
    """

    rule_id = "engine_code_no_literal_assignment"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        # 收集模块顶层“命名常量”声明的变量名（方法体内的端口常量将在逐方法阶段补充）。
        module_constant_var_names = _collect_module_level_constant_var_names(tree)

        for _, method in iter_class_methods(tree):
            constant_var_names = module_constant_var_names | _collect_method_level_typed_literal_var_names(method)
            for node in ast.walk(method):
                if isinstance(node, ast.Assign):
                    value = getattr(node, "value", None)
                    # 1) 直接字面量赋值（原有规则）
                    if _is_literal_expression(value):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                value or node,
                                "CODE_NO_LITERAL_ASSIGNMENT",
                                f"{line_span_text(value or node)}: 禁止在方法体中直接将字面量赋值给变量；请改为“带中文类型注解的字面量初始化”（例如 `零: \"整数\" = 0`），或改用节点输出（如【获取局部变量】）",
                            )
                        )
                        continue

                    # 2) 命名常量的别名赋值：目标变量 = 常量变量
                    if isinstance(value, ast.Name) and value.id in constant_var_names:
                        # 取第一个简单目标名用于错误提示（忽略拆分赋值等复杂形式）
                        target_label = "该变量"
                        targets = getattr(node, "targets", []) or []
                        if targets and isinstance(targets[0], ast.Name):
                            target_label = f"变量『{targets[0].id}』"
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_NO_CONST_ALIAS_ASSIGNMENT",
                                f"{line_span_text(node)}: 禁止通过赋值语句将命名常量『{value.id}』复制到{target_label}；"
                                f"请直接在节点参数中使用该常量，或改用【获取局部变量】/【设置局部变量】节点管理运行时变量",
                            )
                        )
                elif isinstance(node, ast.AnnAssign):
                    value = getattr(node, "value", None)
                    # 1) 方法体内允许“带中文类型注解 + 字面量赋值”
                    if _is_literal_expression(value):
                        if not _is_typed_literal_assignment(node):
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    value or node,
                                    "CODE_NO_LITERAL_ASSIGNMENT",
                                    f"{line_span_text(value or node)}: 禁止在方法体中直接将字面量赋值给变量；请改为“带中文类型注解的字面量初始化”（例如 `零: \"整数\" = 0`），或改用节点输出（如【获取局部变量】）",
                                )
                            )
                        continue

                    # 2) 命名常量的别名赋值：带类型注解的“目标变量 = 常量变量”
                    if isinstance(value, ast.Name) and value.id in constant_var_names:
                        target = getattr(node, "target", None)
                        target_label = "该变量"
                        if isinstance(target, ast.Name):
                            target_label = f"变量『{target.id}』"
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_NO_CONST_ALIAS_ASSIGNMENT",
                                f"{line_span_text(node)}: 禁止通过赋值语句将命名常量『{value.id}』复制到{target_label}；"
                                f"请直接在节点参数中使用该常量，或改用【获取局部变量】/【设置局部变量】节点管理运行时变量",
                            )
                        )

        return issues


__all__ = ["NoLiteralAssignmentRule"]


