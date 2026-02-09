from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.type_registry import TYPE_COMPONENT_ID, TYPE_CONFIG_ID, TYPE_GUID
from engine.validate.id_digits import is_digits_1_to_10

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, line_span_text
from ..ui_key_registry_utils import (
    parse_ui_key_placeholder,
    try_load_ui_html_ui_keys_for_ctx,
)

_ID_TYPES: set[str] = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}


def _is_ui_key_guid_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip().lower()
    return s.startswith("ui_key:") or s.startswith("ui:")


def _extract_type_name(annotation: ast.AST | None) -> str:
    if not isinstance(annotation, ast.Constant) or not isinstance(getattr(annotation, "value", None), str):
        return ""
    return str(annotation.value).strip()


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


class IdLiteralTenDigitsRule(ValidationRule):
    """GUID/配置ID/元件ID 的字面量格式校验：必须为 1~10 位纯数字。

    适用范围：
    - 普通节点图与复合节点文件。

    说明：
    - 仅对“带中文类型注解的字面量赋值”（AnnAssign）生效；
    - 对运行期变量/节点输出等非字面量来源不做推断。
    """

    rule_id = "engine_code_id_literal_digits_1_to_10"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        ui_view = try_load_ui_html_ui_keys_for_ctx(ctx)
        ui_key_set = set(ui_view.ui_keys) if ui_view is not None else set()
        issues: List[EngineIssue] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign):
                continue

            type_name = _extract_type_name(getattr(node, "annotation", None))
            if type_name not in _ID_TYPES:
                continue

            value_node = getattr(node, "value", None)
            value = _extract_literal_value(value_node)
            if value is None:
                continue

            # 工程化：允许 GUID 常量用 ui_key 占位符（写回阶段解析为真实 guid）
            if type_name == TYPE_GUID and _is_ui_key_guid_placeholder(value):
                ui_key = parse_ui_key_placeholder(str(value))
                if ui_key is not None:
                    if ui_view is not None and (not ui_view.html_files):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                (
                                    f"{line_span_text(node)}: 变量的类型注解为『{type_name}』时允许使用 ui_key/ui: 占位符，"
                                    "但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                    f"请先在 {', '.join(str(p) for p in (ui_view.ui_source_dirs if ui_view is not None else ())) } 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。"
                                ),
                            )
                        )
                        continue
                    if ui_view is not None and ui_key not in ui_key_set:
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                node,
                                "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                (
                                    f"{line_span_text(node)}: 变量的类型注解为『{type_name}』时使用的 ui_key 占位符不存在：{str(value)!r}。"
                                    "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。"
                                ),
                            )
                        )
                        continue
                    continue

            if is_digits_1_to_10(value):
                continue

            target = getattr(node, "target", None)
            var_name = getattr(target, "id", "") if isinstance(target, ast.Name) else ""
            var_label = f"变量『{var_name}』" if var_name else "该变量"
            current_text = ast.unparse(value_node) if isinstance(value_node, ast.AST) else "<?>"
            message = (
                f"{line_span_text(node)}: {var_label}的类型注解为『{type_name}』时，"
                "字面量必须是 1~10 位纯数字（例如 0、1234567890 或 \"0001\"）；"
                f"当前写法为 {current_text}"
            )
            issues.append(
                create_rule_issue(
                    self,
                    file_path,
                    node,
                    "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                    message,
                )
            )

        return issues


__all__ = ["IdLiteralTenDigitsRule"]


