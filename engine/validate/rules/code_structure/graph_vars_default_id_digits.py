from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.type_registry import (
    TYPE_COMPONENT_ID,
    TYPE_COMPONENT_ID_LIST,
    TYPE_CONFIG_ID,
    TYPE_CONFIG_ID_LIST,
    TYPE_GUID,
    TYPE_GUID_LIST,
)
from engine.validate.id_digits import is_digits_1_to_10
from ..ui_key_registry_utils import (
    parse_ui_key_placeholder,
    try_format_invalid_ui_state_group_placeholder_message,
    try_load_ui_html_ui_keys_for_ctx,
)
from ..component_registry_utils import (
    parse_component_key_placeholder,
)
from ..entity_registry_utils import parse_entity_key_placeholder

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, line_span_text

_ID_TYPES: set[str] = {TYPE_GUID, TYPE_CONFIG_ID, TYPE_COMPONENT_ID}
_ID_LIST_TYPES: set[str] = {TYPE_GUID_LIST, TYPE_CONFIG_ID_LIST, TYPE_COMPONENT_ID_LIST}

def _is_ui_key_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    s = value.strip().lower()
    if s.startswith("ui_key:"):
        return s[len("ui_key:") :].strip() != ""
    if s.startswith("ui:"):
        return s[len("ui:") :].strip() != ""
    return False


def _is_component_key_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return parse_component_key_placeholder(str(value)) is not None


def _is_entity_key_placeholder(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return parse_entity_key_placeholder(str(value)) is not None


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


class GraphVarsDefaultIdDigitsRule(ValidationRule):
    """GRAPH_VARIABLES 中 ID 类型默认值必须为 1~10 位纯数字（int 或数字字符串）。

    覆盖：
    - GUID / 配置ID / 元件ID
    - GUID列表 / 配置ID列表 / 元件ID列表（逐元素检查）

    说明：
    - 仅对 GraphVariableConfig(..., default_value=...) 的静态常量默认值做校验；
    - 若 default_value 使用了无法静态提取的表达式，将直接报错（无法保证满足数字 ID 约束）。
    """

    rule_id = "engine_code_graph_vars_default_id_digits"
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

                if not variable_type_text:
                    continue
                if variable_type_text not in _ID_TYPES and variable_type_text not in _ID_LIST_TYPES:
                    continue
                if not has_default_value_kw or default_value_node is None:
                    # 未显式指定 default_value：按 GraphVariableConfig 默认值语义处理，不在此处强制。
                    continue

                extracted = extract_constant_value(default_value_node)
                if extracted is NOT_EXTRACTABLE:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                "default_value 必须是可静态解析的 1~10 位纯数字（int 或数字字符串）；"
                                f"当前写法为 {ast.unparse(default_value_node) if isinstance(default_value_node, ast.AST) else '<?>'}"
                            ),
                        )
                    )
                    continue

                # 单值 ID：直接检查
                if variable_type_text in _ID_TYPES:
                    # 工程化：GUID 图变量允许 ui_key 占位符（编译期替换为真实整数 ID）
                    if variable_type_text == TYPE_GUID and _is_ui_key_placeholder(extracted):
                        ui_key = parse_ui_key_placeholder(str(extracted))
                        if ui_key is not None:
                            if ui_view is not None and (not ui_view.html_files):
                                issues.append(
                                    create_rule_issue(
                                        self,
                                        file_path,
                                        default_value_node,
                                        "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                        (
                                            f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                            f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                            "允许使用 ui_key/ui: 占位符，但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                            "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。"
                                        ),
                                    )
                                )
                                continue
                            if ui_view is not None and ui_key not in ui_key_set:
                                invalid_msg = try_format_invalid_ui_state_group_placeholder_message(str(extracted))
                                if invalid_msg is not None:
                                    issues.append(
                                        create_rule_issue(
                                            self,
                                            file_path,
                                            default_value_node,
                                            "CODE_UI_STATE_GROUP_PLACEHOLDER_INVALID_FORMAT",
                                            (
                                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                                f"{invalid_msg} 当前写法为 {str(extracted)!r}"
                                            ),
                                        )
                                    )
                                    continue
                                issues.append(
                                    create_rule_issue(
                                        self,
                                        file_path,
                                        default_value_node,
                                        "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                        (
                                            f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                            f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                            f"占位符不存在：{str(extracted)!r}。"
                                            "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。"
                                        ),
                                    )
                                )
                                continue
                            continue

                    # 工程化：GUID 图变量允许 entity_key 占位符（写回/导出阶段替换为真实实体 GUID/ID）
                    if variable_type_text == TYPE_GUID and _is_entity_key_placeholder(extracted):
                        continue
                    if is_digits_1_to_10(extracted):
                        continue

                    # 工程化：元件ID 图变量允许 component_key 占位符（编译期替换为真实元件ID）
                    if variable_type_text == TYPE_COMPONENT_ID and _is_component_key_placeholder(extracted):
                        # 校验阶段不做“元件名存在性”校验（参考 GIL 在导出/写回阶段才由用户选择）。
                        continue

                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                "default_value 必须是 1~10 位纯数字（int 或数字字符串，例如 0、1234567890 或 \"0001\"）；"
                                f"当前值为 {repr(extracted)}"
                            ),
                        )
                    )
                    continue

                # 列表 ID：逐元素检查
                if variable_type_text in _ID_LIST_TYPES:
                    if not isinstance(extracted, (list, tuple)):
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                default_value_node,
                                "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                    "default_value 必须为列表/元组，且每个元素都为 1~10 位纯数字（int 或数字字符串）；"
                                    f"当前值为 {repr(extracted)}"
                                ),
                            )
                        )
                        continue
                    items = list(extracted)
                    invalid_items: List[object] = []
                    missing_ui_keys: List[str] = []
                    if variable_type_text == TYPE_GUID_LIST:
                        for item in items:
                            if is_digits_1_to_10(item):
                                continue
                            if _is_ui_key_placeholder(item):
                                ui_key = parse_ui_key_placeholder(str(item))
                                if ui_key is None:
                                    invalid_items.append(item)
                                    continue
                                if ui_view is not None and (not ui_view.html_files):
                                    # UI源码缺失：只要存在占位符就报错（一次即可）
                                    issues.append(
                                        create_rule_issue(
                                            self,
                                            file_path,
                                            default_value_node,
                                            "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                            (
                                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                                "允许使用 ui_key/ui: 占位符，但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                                "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。"
                                            ),
                                        )
                                    )
                                    invalid_items = []
                                    missing_ui_keys = []
                                    break
                                if ui_view is not None and ui_key not in ui_key_set:
                                    invalid_msg2 = try_format_invalid_ui_state_group_placeholder_message(str(item))
                                    if invalid_msg2 is not None:
                                        issues.append(
                                            create_rule_issue(
                                                self,
                                                file_path,
                                                default_value_node,
                                                "CODE_UI_STATE_GROUP_PLACEHOLDER_INVALID_FORMAT",
                                                (
                                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                                    f"{invalid_msg2} 当前写法为 {str(item)!r}"
                                                ),
                                            )
                                        )
                                        invalid_items = []
                                        missing_ui_keys = []
                                        break
                                    missing_ui_keys.append(str(item))
                                continue
                            if _is_entity_key_placeholder(item):
                                continue
                            invalid_items.append(item)
                    elif variable_type_text == TYPE_COMPONENT_ID_LIST:
                        for item in items:
                            if is_digits_1_to_10(item):
                                continue
                            if _is_component_key_placeholder(item):
                                continue
                            invalid_items.append(item)
                    else:
                        invalid_items = [item for item in items if not is_digits_1_to_10(item)]

                    if missing_ui_keys:
                        preview_keys = ", ".join(repr(x) for x in missing_ui_keys[:6])
                        more_keys = "..." if len(missing_ui_keys) > 6 else ""
                        issues.append(
                            create_rule_issue(
                                self,
                                file_path,
                                default_value_node,
                                "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                (
                                    f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                    f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                    "default_value 中存在未在 UI源码(HTML) 中声明的 ui_key 占位符："
                                    f"{preview_keys}{more_keys}。"
                                    "请检查 HTML 中是否声明了对应 data-ui-key / data-ui-state-group，或修正占位符 key。"
                                ),
                            )
                        )
                        continue

                    if not invalid_items:
                        continue

                    preview = ", ".join(repr(x) for x in invalid_items[:6])
                    more = "..." if len(invalid_items) > 6 else ""
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_ID_LITERAL_DIGITS_1_TO_10_REQUIRED",
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的类型为『{variable_type_text}』时，"
                                "default_value 的每个元素都必须为 1~10 位纯数字；"
                                f"发现不合法元素：{preview}{more}"
                            ),
                        )
                    )

        return issues


__all__ = ["GraphVarsDefaultIdDigitsRule"]


