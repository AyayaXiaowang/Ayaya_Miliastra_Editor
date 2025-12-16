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


def _is_constant_var_declaration(node: ast.AST) -> bool:
    """判断是否为允许的“常量变量”声明形式。

    当前仅放行带中文类型注解的 AnnAssign，例如：
        常量名: "配置ID" = "1077936129"
    其余字面量赋值仍按原规则报错，鼓励通过节点输出或事件参数提供数据。
    """
    if not isinstance(node, ast.AnnAssign):
        return False
    target = getattr(node, "target", None)
    annotation = getattr(node, "annotation", None)
    if not isinstance(target, ast.Name):
        return False
    if not isinstance(annotation, ast.Constant):
        return False
    if not isinstance(getattr(annotation, "value", None), str):
        return False
    text = str(annotation.value).strip()
    if not text:
        return False
    return True


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

    例外：允许带中文类型注解的“常量变量”声明形式，例如：
        标识: "配置ID" = "1077936129"
    这类声明仅作为命名常量，用于为节点输入端提供常量值，不参与连线。
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

        # 收集当前模块中所有“命名常量”声明的变量名，供后续禁止别名赋值使用。
        constant_var_names: Set[str] = set()
        for node in ast.walk(tree):
            if _is_constant_var_declaration(node):
                target = getattr(node, "target", None)
                if isinstance(target, ast.Name):
                    constant_var_names.add(target.id)

        for _, method in iter_class_methods(tree):
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
                                f"{line_span_text(value or node)}: 禁止直接将常量赋值给变量，请改用节点输出（如【获取局部变量】或常量节点）",
                            )
                        )
                        continue

                    # 2) 命名常量的别名赋值：目标变量 = 常量变量
                    if isinstance(value, ast.Name) and value.id in constant_var_names:
                        # 取第一个简单目标名用于错误提示（忽略解包等复杂形式）
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
                    # 1) 直接字面量赋值（原有规则，排除“命名常量”声明本身）
                    if _is_literal_expression(value):
                        if not _is_constant_var_declaration(node):
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    value or node,
                                    "CODE_NO_LITERAL_ASSIGNMENT",
                                    f"{line_span_text(value or node)}: 禁止直接将常量赋值给变量，请改用节点输出（如【获取局部变量】或常量节点）",
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


