from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.common import VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import collect_module_constants
from engine.validate.node_semantics import (
    SEMANTIC_CUSTOM_VAR_GET,
    SEMANTIC_CUSTOM_VAR_SET,
    is_semantic_node_call,
)

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


def _resolve_string_constant(expr: ast.AST | None, module_constants: dict) -> str | None:
    if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), str):
        return str(expr.value).strip()
    if isinstance(expr, ast.Name):
        constant_value = module_constants.get(expr.id)
        if isinstance(constant_value, str):
            return constant_value.strip()
    return None


_CUSTOM_VAR_NAME_MAX_LEN = 20


class CustomVarNameRequiredRule(ValidationRule):
    """自定义变量节点：『变量名』必须提供且可静态解析为非空字符串。

    适用范围：
    - 普通节点图（类结构 Graph Code）
    - 复合节点文件（类格式/载荷格式的源码部分）

    说明：
    - 若变量名来自运行期表达式，校验器无法静态判断其合法性：降级为 warning。
    """

    rule_id = "engine_code_custom_var_name_required"
    category = "自定义变量"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        module_constants = collect_module_constants(tree)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                call_name = str(func.id or "").strip()
                if not call_name:
                    continue

                is_custom_var_node = (
                    is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_CUSTOM_VAR_GET,
                    )
                    or is_semantic_node_call(
                        workspace_path=ctx.workspace_path,
                        scope=scope,
                        call_name=call_name,
                        semantic_id=SEMANTIC_CUSTOM_VAR_SET,
                    )
                )
                if not is_custom_var_node:
                    continue

                var_kw = None
                for kw in getattr(node, "keywords", []) or []:
                    if kw.arg == VARIABLE_NAME_PORT_NAME:
                        var_kw = kw
                        break
                if var_kw is None:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_CUSTOM_VAR_NAME_REQUIRED",
                            f"{line_span_text(node)}: 【{call_name}】必须提供参数『{VARIABLE_NAME_PORT_NAME}』，且为字符串常量（或模块顶层字符串常量引用）",
                        )
                    )
                    continue

                resolved = _resolve_string_constant(getattr(var_kw, "value", None), module_constants)
                if resolved is None:
                    target = getattr(var_kw, "value", None) or node
                    issues.append(
                        EngineIssue(
                            level="warning",
                            category=self.category,
                            code="CODE_CUSTOM_VAR_NAME_DYNAMIC",
                            message=(
                                f"{line_span_text(target)}: 【{call_name}】的参数『{VARIABLE_NAME_PORT_NAME}』来自运行期表达式，"
                                "校验器无法静态判断其是否为有效变量名；已跳过『变量名』强校验。"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(target),
                        )
                    )
                    continue

                if not resolved:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            getattr(var_kw, "value", None) or node,
                            "CODE_CUSTOM_VAR_NAME_EMPTY",
                            f"{line_span_text(node)}: 【{call_name}】的参数『{VARIABLE_NAME_PORT_NAME}』不能为空字符串",
                        )
                    )
                    continue

                if len(resolved) > _CUSTOM_VAR_NAME_MAX_LEN:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            getattr(var_kw, "value", None) or node,
                            "CODE_CUSTOM_VAR_NAME_TOO_LONG",
                            (
                                f"{line_span_text(node)}: 自定义变量名过长：{resolved!r} "
                                f"（len={len(resolved)}，上限={_CUSTOM_VAR_NAME_MAX_LEN}）。"
                                "请压缩变量名（<=20）。"
                            ),
                        )
                    )

        return issues


__all__ = ["CustomVarNameRequiredRule"]


