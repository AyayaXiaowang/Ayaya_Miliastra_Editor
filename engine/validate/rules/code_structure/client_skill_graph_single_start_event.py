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


class ClientSkillGraphSingleStartEventRule(ValidationRule):
    """client 技能节点图事件入口规则：

    - 必须且只能包含一个事件入口：`on_节点图开始`
    - 禁止出现其它 `on_XXX` 事件方法（包括监听信号/其它内置事件）
    """

    rule_id = "engine_code_client_skill_graph_single_start_event"
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
        if "/节点图/client/技能节点图/" not in normalized_path:
            return []

        tree = get_cached_module(ctx)

        graph_class: ast.ClassDef | None = None
        for node in list(getattr(tree, "body", []) or []):
            if isinstance(node, ast.ClassDef):
                graph_class = node
                break
        if graph_class is None:
            return []

        event_methods: List[ast.FunctionDef] = []
        for item in list(getattr(graph_class, "body", []) or []):
            if isinstance(item, ast.FunctionDef) and item.name.startswith("on_"):
                event_methods.append(item)

        event_suffixes = [m.name[3:] for m in event_methods if len(m.name) > 3]
        if (len(event_suffixes) == 1) and (event_suffixes[0] == "节点图开始"):
            return []

        found_text = ", ".join(f"on_{name}" for name in event_suffixes) if event_suffixes else "<无>"
        message = (
            f"{line_span_text(graph_class)}: client 技能节点图必须且只能包含一个事件入口 `on_节点图开始`；"
            f"当前发现事件入口：{found_text}。"
        )
        return [
            create_rule_issue(
                self,
                file_path,
                graph_class,
                "CODE_CLIENT_SKILL_GRAPH_EVENT_ENTRY_INVALID",
                message,
            )
        ]


__all__ = ["ClientSkillGraphSingleStartEventRule"]


