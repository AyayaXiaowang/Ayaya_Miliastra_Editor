from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

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


def _iter_assigned_target_names(target: ast.AST | None) -> List[str]:
    """提取赋值目标里的变量名（仅 Name/Tuple/List 递归展开）。"""
    if target is None:
        return []
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: List[str] = []
        for element in list(getattr(target, "elts", []) or []):
            out.extend(_iter_assigned_target_names(element))
        return out
    return []


def _collect_method_assignment_events(method: ast.AST) -> Dict[str, List[Tuple[int, str]]]:
    """收集方法内变量写入事件：name -> [(lineno, kind)]。

    kind:
    - typed_literal：AnnAssign + 中文类型注解 + 字面量初始化（命名常量声明）
    - other：其它任何形式的写入（普通赋值/增量赋值/循环目标等）
    """
    events: Dict[str, List[Tuple[int, str]]] = {}

    def _add_event(name: str, lineno: int, kind: str) -> None:
        name_text = str(name or "").strip()
        if not name_text:
            return
        events.setdefault(name_text, []).append((int(lineno), str(kind)))

    for node in ast.walk(method):
        lineno = int(getattr(node, "lineno", 0) or 0)
        if isinstance(node, ast.AnnAssign):
            kind = "typed_literal" if _is_typed_literal_assignment(node) else "other"
            for name in _iter_assigned_target_names(getattr(node, "target", None)):
                _add_event(name, lineno, kind)
            continue
        if isinstance(node, ast.Assign):
            for target in list(getattr(node, "targets", []) or []):
                for name in _iter_assigned_target_names(target):
                    _add_event(name, lineno, "other")
            continue
        if isinstance(node, ast.AugAssign):
            for name in _iter_assigned_target_names(getattr(node, "target", None)):
                _add_event(name, lineno, "other")
            continue
        if isinstance(node, (ast.For, ast.AsyncFor)):
            for name in _iter_assigned_target_names(getattr(node, "target", None)):
                _add_event(name, lineno, "other")
            continue
        if isinstance(node, ast.With):
            for item in list(getattr(node, "items", []) or []):
                for name in _iter_assigned_target_names(getattr(item, "optional_vars", None)):
                    _add_event(name, lineno, "other")
            continue
        if isinstance(node, ast.AsyncWith):
            for item in list(getattr(node, "items", []) or []):
                for name in _iter_assigned_target_names(getattr(item, "optional_vars", None)):
                    _add_event(name, lineno, "other")
            continue
        if isinstance(node, ast.NamedExpr):
            for name in _iter_assigned_target_names(getattr(node, "target", None)):
                _add_event(name, lineno, "other")
            continue
        if isinstance(node, ast.ExceptHandler):
            ex_name = getattr(node, "name", None)
            if isinstance(ex_name, str) and ex_name.strip():
                _add_event(ex_name, lineno, "other")
            continue

    for name, seq in events.items():
        seq.sort(key=lambda item: (int(item[0]), item[1]))
        events[name] = seq
    return events


def _is_stable_const_alias_assignment(
    *,
    source_name: str,
    alias_node: ast.AST,
    module_constant_var_names: Set[str],
    method_assignment_events: Dict[str, List[Tuple[int, str]]],
) -> bool:
    """判断 `B = A` 是否可视为“稳定常量折叠”。

    规则（保守）：
    - 在别名语句之前，`A` 的最近一次写入必须是 `typed_literal`；
    - 若别名前没有任何方法内写入，则 `A` 必须是模块级命名常量；
    - 否则视为不稳定（例如运行时节点输出覆盖、分支赋值覆盖等），继续报错。
    """
    src = str(source_name or "").strip()
    if not src:
        return False

    alias_lineno = int(getattr(alias_node, "lineno", 0) or 0)
    if alias_lineno <= 0:
        return False

    events = method_assignment_events.get(src, [])
    latest_before_alias: Tuple[int, str] | None = None
    for lineno, kind in events:
        if int(lineno) < alias_lineno:
            latest_before_alias = (int(lineno), str(kind))
            continue
        break

    if latest_before_alias is None:
        return src in module_constant_var_names

    _, latest_kind = latest_before_alias
    return latest_kind == "typed_literal"


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
            method_constant_var_names = _collect_method_level_typed_literal_var_names(method)
            constant_var_names = module_constant_var_names | method_constant_var_names
            method_assignment_events = _collect_method_assignment_events(method)
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
                        if _is_stable_const_alias_assignment(
                            source_name=str(value.id),
                            alias_node=node,
                            module_constant_var_names=module_constant_var_names,
                            method_assignment_events=method_assignment_events,
                        ):
                            continue
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
                        if _is_stable_const_alias_assignment(
                            source_name=str(value.id),
                            alias_node=node,
                            module_constant_var_names=module_constant_var_names,
                            method_assignment_events=method_assignment_events,
                        ):
                            continue
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


