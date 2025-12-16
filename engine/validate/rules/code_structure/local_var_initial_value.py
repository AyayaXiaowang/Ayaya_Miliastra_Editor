from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.ir.arg_normalizer import is_reserved_argument

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, iter_class_methods, line_span_text


class LocalVarInitialValueRule(ValidationRule):
    """【获取局部变量】初始值校验：显式调用时必须提供『初始值』。

    场景：
    - 在 Graph Code 或复合节点类格式中，程序员可以直接调用【获取局部变量】；
    - 若未为参数『初始值』提供值（既无关键字“初始值=...”，也无非保留位置参数），
      则局部变量在首次写入前处于未定义状态，容易导致后续逻辑依赖空值。

    规则：
    - 针对代码中显式出现的【获取局部变量(...)】调用：
      - 必须提供关键字参数 `初始值=...`，或在保留参数（self/game/owner_entity/self.game/self.owner_entity）之后
        传入一个非 None 的位置参数；
      - 显式传入 None（例如 `初始值=None` 或第二个参数为 `None`）视为未配置初始值。
    """

    rule_id = "engine_code_local_var_initial"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name) or func.id != "获取局部变量":
                    continue

                if self._has_valid_initial_arg(node):
                    continue

                msg = (
                    f"{line_span_text(node)}: 【获取局部变量】必须为参数『初始值』提供有效的默认值；"
                    "请使用关键字形式“初始值=...”或在保留参数之后提供一个非 None 的数据参数，"
                    "避免在首次使用前局部变量为未定义值。"
                )
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        node,
                        "CODE_LOCAL_VAR_INITIAL_REQUIRED",
                        msg,
                    )
                )

        return issues

    def _has_valid_initial_arg(self, call: ast.Call) -> bool:
        """判断【获取局部变量】调用是否为『初始值』提供了有效参数。"""
        # 1) 优先检查关键字参数 “初始值”
        for kw in getattr(call, "keywords", []) or []:
            if kw.arg != "初始值":
                continue
            value = getattr(kw, "value", None)
            # 显式 None 视为未设置
            if isinstance(value, ast.Constant) and getattr(value, "value", None) is None:
                return False
            return True

        # 2) 若无关键字参数，检查是否存在非保留的位置参数
        for arg in getattr(call, "args", []) or []:
            if is_reserved_argument(arg):
                continue
            # 显式 None 视为未配置初始值
            if isinstance(arg, ast.Constant) and getattr(arg, "value", None) is None:
                return False
            return True

        # 既没有“初始值”关键字，也没有任何非保留数据参数 → 视为未提供初始值
        return False


__all__ = ["LocalVarInitialValueRule"]


