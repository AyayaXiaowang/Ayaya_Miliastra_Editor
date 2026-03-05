from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List

from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, line_span_text
from ..ui_key_registry_utils import (
    parse_ui_key_placeholder,
    try_format_invalid_ui_state_group_placeholder_message,
    try_load_ui_html_ui_keys_for_ctx,
)
from ..entity_registry_utils import parse_entity_key_placeholder


def _iter_graph_variables_list_nodes(tree: ast.AST) -> List[ast.List]:
    if not isinstance(tree, ast.Module):
        return []
    results: List[ast.List] = []
    for node in getattr(tree, "body", []) or []:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == "GRAPH_VARIABLES" for t in getattr(node, "targets", []) or []):
                if isinstance(getattr(node, "value", None), ast.List):
                    results.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if isinstance(getattr(node, "target", None), ast.Name) and node.target.id == "GRAPH_VARIABLES":
                if isinstance(getattr(node, "value", None), ast.List):
                    results.append(node.value)
    return results


def _is_ui_key_placeholder(text: str) -> bool:
    s = str(text or "").strip().lower()
    if s.startswith("ui_key:"):
        return s[len("ui_key:") :].strip() != ""
    if s.startswith("ui:"):
        return s[len("ui:") :].strip() != ""
    return False


def _is_entity_key_placeholder(text: str) -> bool:
    return parse_entity_key_placeholder(text) is not None


_NUMBER_TEXT_RE = re.compile(r"[+-]?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?\Z")


class GraphVarsDefaultIntegerPlaceholderRule(ValidationRule):
    """GRAPH_VARIABLES 中“整数/整数列表”类型 default_value 允许使用 ui_key 占位符（或数字常量）。

    说明：
    - 支持：int/float、数字字符串、或 ui_key/ui: 占位符字符串；
    - 整数列表支持逐元素：数字/数字字符串/ui_key/ui: 占位符；
    - 若 default_value 无法静态提取，将直接报错（无法保证写回阶段可解析）。
    """

    rule_id = "engine_code_graph_vars_default_integer_placeholder"
    category = "节点图变量"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        ui_view = try_load_ui_html_ui_keys_for_ctx(ctx)
        ui_key_set = set(ui_view.ui_keys) if ui_view is not None else set()

        issues: List[EngineIssue] = []
        list_nodes = _iter_graph_variables_list_nodes(tree)
        if not list_nodes:
            return issues

        for list_node in list_nodes:
            for element in getattr(list_node, "elts", []) or []:
                if not isinstance(element, ast.Call):
                    continue
                func = getattr(element, "func", None)
                if not (isinstance(func, ast.Name) and func.id == "GraphVariableConfig"):
                    continue

                name_text = ""
                variable_type_text = ""
                default_value_node: ast.AST | None = None
                has_default_value_kw = False

                for kw in getattr(element, "keywords", []) or []:
                    key = getattr(kw, "arg", None)
                    value_node = getattr(kw, "value", None)
                    if key == "name" and isinstance(value_node, ast.Constant) and isinstance(getattr(value_node, "value", None), str):
                        name_text = str(value_node.value).strip()
                        continue
                    if key == "variable_type" and isinstance(value_node, ast.Constant) and isinstance(getattr(value_node, "value", None), str):
                        variable_type_text = str(value_node.value).strip()
                        continue
                    if key == "default_value":
                        has_default_value_kw = True
                        default_value_node = value_node

                if variable_type_text not in {"整数", "整数列表"}:
                    continue
                if not has_default_value_kw or default_value_node is None:
                    continue

                extracted = extract_constant_value(default_value_node)
                if extracted is NOT_EXTRACTABLE:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_GRAPH_VAR_DEFAULT_VALUE_INVALID",
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数』时，"
                                "default_value 必须是可静态解析的数字（int/float/数字字符串）或 ui_key/ui: 占位符字符串；"
                                f"当前写法为 {ast.unparse(default_value_node) if isinstance(default_value_node, ast.AST) else '<?>'}"
                            ),
                        )
                    )
                    continue
                var_type_display = variable_type_text

                def _report_default_invalid(msg: str) -> None:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_GRAPH_VAR_DEFAULT_VALUE_INVALID",
                            msg,
                        )
                    )

                def _check_ui_key_exists_or_report(placeholder_text: str) -> bool:
                    ui_key = parse_ui_key_placeholder(placeholder_text)
                    if ui_key is None:
                        return True
                    # 仅当节点图位于资源库目录结构下时才强制存在性
                    if ui_view is not None and (not ui_view.html_files):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                default_value_node,
                                "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『{var_type_display}』时，"
                                    "允许使用 ui_key/ui: 占位符，但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                    "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。"
                                ),
                            )
                        )
                        return False
                    if ui_view is not None and ui_key not in ui_key_set:
                        invalid_msg = try_format_invalid_ui_state_group_placeholder_message(str(placeholder_text))
                        if invalid_msg is not None:
                            issues.append(
                                create_rule_issue(
                                    self,
                                    file_path,
                                    default_value_node,
                                    "CODE_UI_STATE_GROUP_PLACEHOLDER_INVALID_FORMAT",
                                    (
                                        f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                        f"{('『' + name_text + '』') if name_text else ''} 的类型为『{var_type_display}』时，"
                                        f"{invalid_msg} 当前写法为 {placeholder_text!r}"
                                    ),
                                )
                            )
                            return False
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                default_value_node,
                                "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『{var_type_display}』时，"
                                    f"占位符不存在：{placeholder_text!r}。"
                                    "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。"
                                ),
                            )
                        )
                        return False
                    return True

                # ===== 整数 =====
                if variable_type_text == "整数":
                    # 数字类型：允许（float 会在写回阶段转 int）
                    if isinstance(extracted, bool):
                        _report_default_invalid(
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数』时，"
                                "default_value 不允许为布尔值；请写 0/1 或 ui_key/ui: 占位符。"
                            )
                        )
                        continue
                    if isinstance(extracted, (int, float)):
                        continue
                    if isinstance(extracted, str):
                        s = extracted.strip()
                        if _is_ui_key_placeholder(s):
                            if _check_ui_key_exists_or_report(s):
                                continue
                            continue
                        if _is_entity_key_placeholder(s):
                            continue
                        if _NUMBER_TEXT_RE.fullmatch(s):
                            continue
                        _report_default_invalid(
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数』时，"
                                "default_value 只能是数字（例如 0、10、\"10\"、\"0.0\"）或 ui_key/ui: 占位符；"
                                f"当前值为 {repr(extracted)}"
                            )
                        )
                        continue
                    _report_default_invalid(
                        (
                            f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                            f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数』时，"
                            "default_value 必须为数字或 ui_key/ui: 占位符；"
                            f"当前值为 {repr(extracted)}"
                        )
                    )
                    continue

                # ===== 整数列表 =====
                if variable_type_text == "整数列表":
                    if not isinstance(extracted, (list, tuple)):
                        _report_default_invalid(
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数列表』时，"
                                "default_value 必须为列表/元组，且每个元素都为数字或 ui_key/ui: 占位符；"
                                f"当前值为 {repr(extracted)}"
                            )
                        )
                        continue
                    for item in list(extracted):
                        if isinstance(item, bool):
                            _report_default_invalid(
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数列表』时，"
                                    "default_value 的列表元素不允许为布尔值；请写 0/1 或 ui_key/ui: 占位符。"
                                )
                            )
                            break
                        if isinstance(item, (int, float)):
                            continue
                        if isinstance(item, str):
                            s = item.strip()
                            if _is_ui_key_placeholder(s):
                                if not _check_ui_key_exists_or_report(s):
                                    break
                                continue
                            if _is_entity_key_placeholder(s):
                                continue
                            if _NUMBER_TEXT_RE.fullmatch(s):
                                continue
                            _report_default_invalid(
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数列表』时，"
                                    "default_value 的每个元素都必须为数字（例如 0、\"10\"、\"0.0\"）或 ui_key/ui: 占位符；"
                                    f"发现不合法元素：{repr(item)}"
                                )
                            )
                            break
                        _report_default_invalid(
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『整数列表』时，"
                                "default_value 的每个元素都必须为数字或 ui_key/ui: 占位符；"
                                f"发现不合法元素：{repr(item)}"
                            )
                        )
                        break

        return issues


__all__ = ["GraphVarsDefaultIntegerPlaceholderRule"]

