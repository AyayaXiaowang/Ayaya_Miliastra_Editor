from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import (
    build_parent_map,
    create_rule_issue,
    get_cached_module,
    iter_class_methods,
    line_span_text,
)


class LocalVarUsageRule(ValidationRule):
    """【获取局部变量】调用规范校验：

    - 调用结果必须显式选择输出：
      - 二元解包：`局部句柄, 当前值 = 获取局部变量(self.game, 初始值=0)`
      - 或下标取值：`当前值 = 获取局部变量(self.game, 初始值=0)[1]`
    """

    rule_id = "engine_code_local_var_usage"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        parent_map = build_parent_map(tree)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name) or func.id != "获取局部变量":
                    continue

                selection_issue = self._build_output_selection_issue(
                    file_path, node, parent_map
                )
                if selection_issue is not None:
                    issues.append(selection_issue)

        return issues

    def _build_output_selection_issue(
        self,
        file_path: Path,
        call: ast.Call,
        parent_map: dict[ast.AST, ast.AST],
    ) -> EngineIssue | None:
        parent = parent_map.get(call)

        # 1) 允许下标选择：获取局部变量(...)[0] / [1]
        if isinstance(parent, ast.Subscript) and getattr(parent, "value", None) is call:
            index_value = self._extract_constant_index(parent)
            if index_value in {0, 1}:
                return None
            msg = (
                f"{line_span_text(parent)}: 【获取局部变量】下标选择仅允许索引 0 或 1（0=局部变量句柄，1=值）。"
                "推荐写法：`当前值 = 获取局部变量(self.game, 初始值=0)[1]`。"
            )
            return create_rule_issue(
                self,
                file_path,
                parent,
                "CODE_LOCAL_VAR_OUTPUT_INDEX_INVALID",
                msg,
            )

        # 2) 允许二元解包：句柄, 值 = 获取局部变量(...)
        if isinstance(parent, ast.Assign) and getattr(parent, "value", None) is call:
            if self._is_two_target_unpack(parent):
                return None
            msg = (
                f"{line_span_text(parent)}: 【获取局部变量】有 2 个输出（局部变量句柄, 值），"
                "必须使用二元解包（`句柄, 当前值 = 获取局部变量(...)`），"
                "或显式下标取值（`获取局部变量(...)[0/1]`）。"
            )
            return create_rule_issue(
                self,
                file_path,
                parent,
                "CODE_LOCAL_VAR_OUTPUT_SELECTION_REQUIRED",
                msg,
            )

        # 3) 其余上下文视为未显式选择输出
        msg = (
            f"{line_span_text(call)}: 【获取局部变量】有 2 个输出（局部变量句柄, 值），"
            "调用结果必须二元解包或显式下标取值；"
            "禁止直接把调用结果当作单个值使用。"
        )
        return create_rule_issue(
            self,
            file_path,
            call,
            "CODE_LOCAL_VAR_OUTPUT_SELECTION_REQUIRED",
            msg,
        )

    def _extract_constant_index(self, subscript: ast.Subscript) -> int | None:
        slice_node = getattr(subscript, "slice", None)
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, int):
            return int(slice_node.value)
        return None

    def _is_two_target_unpack(self, assign: ast.Assign) -> bool:
        targets = list(getattr(assign, "targets", []) or [])
        if len(targets) != 1:
            return False
        target = targets[0]
        if not isinstance(target, (ast.Tuple, ast.List)):
            return False
        elts = list(getattr(target, "elts", []) or [])
        if len(elts) != 2:
            return False
        return all(isinstance(elt, ast.Name) and bool(getattr(elt, "id", "")) for elt in elts)


__all__ = ["LocalVarUsageRule"]


