from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List

from engine.signal import get_default_signal_repository

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    create_rule_issue,
    get_cached_module,
    infer_graph_scope,
    iter_class_methods,
    line_span_text,
    normalize_expr,
)
from ..node_index import event_node_names


def _normalize_event_name_for_handler(event_name: str) -> str:
    """将事件名规约为可用于 Python 方法名后缀的形式。"""
    return str(event_name or "").replace("/", "或")


class EventHandlerNameRule(ValidationRule):
    """事件回调命名校验：

    - 当 register_event_handler 注册的是**内置事件**（来自事件节点列表）时，回调必须为 `on_<事件名>`；
    - 当注册的是**信号事件**（signal_id 或可由信号库解析的信号名称）时，回调命名不做强制约束。

    背景：
    - Graph Code 里常见写法 `on_定时器触发时_XXX` 会造成“看起来像新事件，但实际注册的是同一个内置事件”，
      使代码审阅与规则系统难以对齐；因此对内置事件回调名强制使用标准事件名。
    """

    rule_id = "engine_code_event_handler_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        scope = infer_graph_scope(ctx)
        builtin_event_names = event_node_names(ctx.workspace_path, scope)
        signal_repo = get_default_signal_repository()
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue

                func = getattr(node, "func", None)
                is_attr_call = (
                    isinstance(func, ast.Attribute)
                    and getattr(func, "attr", "") == "register_event_handler"
                )
                is_name_call = isinstance(func, ast.Name) and func.id == "register_event_handler"
                if not (is_attr_call or is_name_call):
                    continue

                event_arg_node = None
                positional_args = getattr(node, "args", []) or []
                if positional_args:
                    event_arg_node = positional_args[0]
                else:
                    for keyword in getattr(node, "keywords", []) or []:
                        if keyword.arg in {"event", "event_name"}:
                            event_arg_node = keyword.value
                            break

                event_name = _extract_event_name_from_value(
                    event_arg_node,
                    module_constant_strings,
                )
                if not event_name:
                    continue

                # 信号事件：不强制回调名（EventNameRule/信号规则负责其余约束）
                if event_name.startswith("signal_"):
                    continue
                if signal_repo.resolve_id_by_name(event_name):
                    continue

                # 非内置事件（未知事件名）交由 EventNameRule 报错；这里不重复报。
                if event_name not in builtin_event_names:
                    continue

                handler_node = None
                if len(positional_args) >= 2:
                    handler_node = positional_args[1]
                else:
                    for keyword in getattr(node, "keywords", []) or []:
                        if keyword.arg in {"handler", "callback", "func"}:
                            handler_node = keyword.value
                            break

                if handler_node is None:
                    continue

                handler_name = _extract_handler_symbol_name(handler_node)
                expected_name = f"on_{_normalize_event_name_for_handler(event_name)}"
                if handler_name == expected_name:
                    continue

                handler_text = handler_name if handler_name else normalize_expr(handler_node)
                message = (
                    f"{line_span_text(handler_node)}: 内置事件 '{event_name}' 的回调命名必须为 "
                    f"'{expected_name}'，当前为 '{handler_text}'。"
                    f"内置事件不允许在 `on_{event_name}` 后追加后缀；"
                    f"若需要区分不同业务分支，请在同一个标准回调内部通过节点逻辑分流。"
                    f"（信号事件允许自定义信号名与回调名）"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        handler_node,
                        "CODE_EVENT_HANDLER_NAME_MISMATCH",
                        message,
                    )
                )

        return issues


def _extract_handler_symbol_name(node: ast.AST) -> str:
    """从 handler AST 节点提取“符号名”。

    - `self.on_实体创建时` → `on_实体创建时`
    - `on_实体创建时` → `on_实体创建时`
    - 其他表达式返回空字符串（由调用方决定如何展示）
    """

    if isinstance(node, ast.Attribute) and isinstance(getattr(node, "attr", None), str):
        return node.attr
    if isinstance(node, ast.Name) and isinstance(getattr(node, "id", None), str):
        return node.id
    return ""


__all__ = ["EventHandlerNameRule"]


def _collect_module_constant_strings(tree: ast.AST) -> Dict[str, str]:
    """收集模块顶层的字符串常量声明，支持普通与注解赋值。"""

    constant_strings: Dict[str, str] = {}
    module_body = getattr(tree, "body", []) or []
    for node in module_body:
        target_names: List[str] = []
        value_node = None
        if isinstance(node, ast.Assign):
            value_node = getattr(node, "value", None)
            for target in getattr(node, "targets", []) or []:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            value_node = getattr(node, "value", None)
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name):
                target_names.append(target.id)
        if not target_names or not isinstance(value_node, ast.Constant):
            continue
        if not isinstance(getattr(value_node, "value", None), str):
            continue
        constant_text = value_node.value.strip()
        if not constant_text:
            continue
        for target_name in target_names:
            if target_name and target_name not in constant_strings:
                constant_strings[target_name] = constant_text
    return constant_strings


def _extract_event_name_from_value(
    value_node: ast.AST | None, constant_strings: Dict[str, str]
) -> str:
    """解析事件名参数的取值：直接字面量或顶层命名常量。"""

    if isinstance(value_node, ast.Constant) and isinstance(
        getattr(value_node, "value", None), str
    ):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


