from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.signal import get_default_signal_repository

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, iter_class_methods, line_span_text
from ..node_index import event_node_names


class EventNameRule(ValidationRule):
    """事件名合法性校验：register_event_handler 注册的事件名必须来源于事件节点或信号。"""

    rule_id = "engine_code_event_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        valid_event_names = event_node_names(ctx.workspace_path)
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

                if not isinstance(event_arg_node, ast.Constant):
                    continue
                event_value = getattr(event_arg_node, "value", None)
                if not isinstance(event_value, str):
                    continue

                event_name = event_value.strip()
                if not event_name:
                    continue

                # 信号 ID（signal_xxx）作为事件名时放行，由信号系统规则单独校验
                if event_name.startswith("signal_"):
                    continue

                # 显示名称为已知信号名时同样视为合法，解析为 ID 的职责交给信号系统与图解析器。
                if signal_repo.resolve_id_by_name(event_name):
                    continue

                if event_name in valid_event_names:
                    continue

                message = (
                    f"{line_span_text(event_arg_node)}: 事件名 '{event_name}' 不在当前引擎事件节点列表中；"
                    f"请检查是否拼写错误，或改为使用已有事件/信号（例如通过【监听信号】节点绑定信号后使用信号ID）。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        event_arg_node,
                        "CODE_UNKNOWN_EVENT_NAME",
                        message,
                    )
                )

        return issues


__all__ = ["EventNameRule"]


