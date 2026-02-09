from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.utils.ast_utils import collect_module_constants
from engine.type_registry import TYPE_COMPONENT_ID, TYPE_CONFIG_ID, TYPE_GUID
from engine.validate.id_digits import is_digits_1_to_10

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import get_cached_module, infer_graph_scope, iter_class_methods, line_span_text
from ..node_index import input_types_by_func
from ..ui_key_registry_utils import (
    parse_ui_key_placeholder,
    try_load_ui_html_ui_keys_for_ctx,
)

_ID_TYPES: Set[str] = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}


def _is_ui_key_guid_placeholder(value: object) -> bool:
    """允许在 GUID 端口上使用 ui_key 占位符（编译期替换为真实 guid）。"""
    if not isinstance(value, str):
        return False
    s = value.strip().lower()
    return s.startswith("ui_key:") or s.startswith("ui:")


def _extract_literal_value(expr: ast.AST | None) -> object | None:
    """提取“字面量表达式”的 Python 值（仅支持 Constant 与一元正负号包裹的整数 Constant）。"""
    if expr is None:
        return None
    if isinstance(expr, ast.Constant):
        return getattr(expr, "value", None)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
        operand = getattr(expr, "operand", None)
        if not isinstance(operand, ast.Constant):
            return None
        operand_value = getattr(operand, "value", None)
        # bool 是 int 的子类，这里显式排除，避免 True/False 被当作数字 ID
        if isinstance(operand_value, bool) or not isinstance(operand_value, int):
            return None
        if isinstance(expr.op, ast.UAdd):
            return int(operand_value)
        return -int(operand_value)
    return None


def _resolve_constant_value(expr: ast.AST | None, module_constants: Dict[str, object]) -> object | None:
    if isinstance(expr, ast.Name) and isinstance(getattr(expr, "id", None), str):
        name = str(expr.id)
        if name in module_constants:
            return module_constants[name]
    return _extract_literal_value(expr)


class IdPortLiteralTenDigitsRule(ValidationRule):
    """当节点输入端口期望 GUID/配置ID/元件ID 时，传入的常量必须为 1~10 位纯数字。

    说明：
    - 覆盖“直接在节点调用中写字面量常量”的场景（例如 配置ID=123 / 配置ID="0001"）。
    - 若值来自运行期变量/节点输出等无法静态解析的表达式，则跳过（由上游规则/运行期负责）。
    """

    rule_id = "engine_code_id_port_literal_digits_1_to_10"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        ui_view = try_load_ui_html_ui_keys_for_ctx(ctx)
        ui_key_set = set(ui_view.ui_keys) if ui_view is not None else set()

        expected_types_by_func = input_types_by_func(ctx.workspace_path, scope)
        module_constants = collect_module_constants(tree)

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for call in ast.walk(method):
                if not isinstance(call, ast.Call):
                    continue
                func = getattr(call, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                func_name = str(func.id or "").strip()
                if not func_name:
                    continue

                expect_map = expected_types_by_func.get(func_name, {})
                if not isinstance(expect_map, dict) or not expect_map:
                    continue

                for kw in getattr(call, "keywords", []) or []:
                    port_name = getattr(kw, "arg", None)
                    if not isinstance(port_name, str) or not port_name:
                        continue
                    expected = expect_map.get(port_name)
                    if not isinstance(expected, str) or not expected:
                        continue
                    if expected not in _ID_TYPES:
                        continue

                    value_node = getattr(kw, "value", None)
                    resolved = _resolve_constant_value(value_node, module_constants)
                    if resolved is None:
                        continue

                    # 工程化：允许 GUID 端口使用 ui_key 占位符，写回阶段会解析为真实 GUID
                    if expected == TYPE_GUID and _is_ui_key_guid_placeholder(resolved):
                        ui_key = parse_ui_key_placeholder(str(resolved))
                        if ui_key is not None:
                            if ui_view is not None and (not ui_view.html_files):
                                issues.append(
                                    EngineIssue(
                                        level=self.default_level,
                                        category=self.category,
                                        code="CODE_UI_HTML_SOURCES_NOT_FOUND",
                                        message=(
                                            f"{line_span_text(value_node or call)}: 函数『{func_name}』输入端口『{port_name}』"
                                            f"期望类型『{expected}』时允许使用 ui_key/ui: 占位符，"
                                            "但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                            "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。"
                                        ),
                                        file=str(file_path),
                                        line_span=line_span_text(value_node or call),
                                        port=str(port_name),
                                        detail={
                                            "func_name": func_name,
                                            "port_name": port_name,
                                            "expected_type": expected,
                                            "resolved_value": resolved,
                                        },
                                    )
                                )
                                continue
                            if ui_view is not None and ui_key not in ui_key_set:
                                issues.append(
                                    EngineIssue(
                                        level=self.default_level,
                                        category=self.category,
                                        code="CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                        message=(
                                            f"{line_span_text(value_node or call)}: 函数『{func_name}』输入端口『{port_name}』"
                                            f"期望类型『{expected}』时使用的 ui_key 占位符不存在：{str(resolved)!r}。"
                                            "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。"
                                        ),
                                        file=str(file_path),
                                        line_span=line_span_text(value_node or call),
                                        port=str(port_name),
                                        detail={
                                            "func_name": func_name,
                                            "port_name": port_name,
                                            "expected_type": expected,
                                            "resolved_value": resolved,
                                        },
                                    )
                                )
                                continue
                            continue
                        # 非占位符字符串：继续走数字 ID 约束

                    if is_digits_1_to_10(resolved):
                        continue

                    current_text = ast.unparse(value_node) if isinstance(value_node, ast.AST) else "<?>"
                    issues.append(
                        EngineIssue(
                            level=self.default_level,
                            category=self.category,
                            code="CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                            message=(
                                f"{line_span_text(value_node or call)}: 函数『{func_name}』输入端口『{port_name}』"
                                f"期望类型『{expected}』时，常量必须是 1~10 位纯数字（例如 0、1234567890 或 \"0001\"）；"
                                f"当前写法为 {current_text}"
                            ),
                            file=str(file_path),
                            line_span=line_span_text(value_node or call),
                            port=str(port_name),
                            detail={
                                "func_name": func_name,
                                "port_name": port_name,
                                "expected_type": expected,
                                "resolved_value": resolved,
                            },
                        )
                    )

        return issues


__all__ = ["IdPortLiteralTenDigitsRule"]


