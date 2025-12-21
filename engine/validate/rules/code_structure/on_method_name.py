from __future__ import annotations

from pathlib import Path
from typing import List

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
)
from ..node_index import event_node_names


def _normalize_event_name_for_on_method(event_name: str) -> str:
    """将内置事件名规约为可用于 `on_XXX` 方法名后缀的形式。"""
    return str(event_name or "").replace("/", "或")


class OnMethodNameRule(ValidationRule):
    """严格校验所有 `on_XXX` 方法名：

    - `XXX` 必须是内置事件名（事件节点列表中的名称）；或
    - `XXX` 必须是已定义的信号名称（可由信号仓库解析到 signal_id）；或
    - `XXX` 必须是已定义的信号 ID（以 `signal_` 开头且在信号仓库中存在）。

    说明：
    - 这是比“只校验 register_event_handler(...)”更严格的约束：即便用户写了但没注册，
      只要方法名以 `on_` 开头，就必须是合法事件/信号；否则立即报错。
    - 复合节点文件跳过（复合节点的事件入口由流程 pin 语义负责，不在此处约束）。
    """

    rule_id = "engine_code_on_method_name"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        builtin_event_names = event_node_names(ctx.workspace_path, scope)
        builtin_event_suffixes = {_normalize_event_name_for_on_method(name) for name in builtin_event_names}
        signal_repo = get_default_signal_repository()
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            method_name = str(getattr(method, "name", "") or "")
            if not method_name.startswith("on_"):
                continue
            suffix = method_name.removeprefix("on_").strip()
            if not suffix:
                message = f"{line_span_text(method)}: 方法名 '{method_name}' 不合法：`on_` 后必须跟随事件名或信号名。"
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        method,
                        "CODE_ON_METHOD_NAME_EMPTY",
                        message,
                    )
                )
                continue

            # 内置事件名
            if suffix in builtin_event_suffixes:
                continue

            # client 技能节点图的“节点图开始”入口并非通过事件节点库暴露，
            # 但会在运行时作为统一入口被调用；为兼容该约定，这里放行该名称。
            if scope == "client" and suffix == "节点图开始":
                continue

            # 信号名：允许使用信号“显示名称”
            if signal_repo.resolve_id_by_name(suffix):
                continue

            # 信号 ID：允许 signal_xxx，但必须存在于信号仓库
            if suffix.startswith("signal_") and signal_repo.get_payload(suffix) is not None:
                continue

            message = (
                f"{line_span_text(method)}: 方法名 '{method_name}' 不合法："
                f"`on_` 后的 '{suffix}' 既不是内置事件名，也不是已定义的信号名/信号ID。"
                f"请改为使用真实存在的事件名（例如 '实体创建时'、'定时器触发时'），"
                f"或先在信号管理中定义信号后再使用其名称。"
            )
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    method,
                    "CODE_ON_METHOD_NAME_UNKNOWN",
                    message,
                )
            )

        return issues


__all__ = ["OnMethodNameRule"]


