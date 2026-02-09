from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.type_registry import TYPE_STRUCT, TYPE_STRUCT_LIST

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, line_span_text


def _iter_graph_variables_list_nodes(tree: ast.AST) -> List[ast.List]:
    if not isinstance(tree, ast.Module):
        return []
    results: List[ast.List] = []
    for node in getattr(tree, "body", []) or []:
        if isinstance(node, ast.Assign):
            if any(
                isinstance(t, ast.Name) and t.id == "GRAPH_VARIABLES"
                for t in getattr(node, "targets", []) or []
            ):
                if isinstance(getattr(node, "value", None), ast.List):
                    results.append(node.value)
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(getattr(node, "target", None), ast.Name)
                and node.target.id == "GRAPH_VARIABLES"
            ):
                if isinstance(getattr(node, "value", None), ast.List):
                    results.append(node.value)
    return results


def _collect_known_struct_names() -> Set[str]:
    schema_view = get_default_definition_schema_view()
    struct_payloads = schema_view.get_all_struct_definitions()
    known: Set[str] = set()
    if isinstance(struct_payloads, dict):
        for _, payload in struct_payloads.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("struct_name")
            if isinstance(value, str) and value.strip():
                known.add(value.strip())
    return known


class GraphVarsStructNameRequiredRule(ValidationRule):
    """GRAPH_VARIABLES 中结构体类型图变量：当默认值非空时，必须提供有效 struct_name。

    说明：
    - 常见写法是 `default_value=None`（或结构体列表的 `default_value=[]`），由运行期通过【拼装结构体】赋值；
      这种场景允许不填写 struct_name。
    - 一旦给出非空默认值，写回存档/编辑器解析需要依赖“已存在的结构体定义”，因此强制要求 struct_name
      可静态解析且存在于当前作用域的结构体定义中。
    """

    rule_id = "engine_code_graph_vars_struct_name_required"
    category = "节点图变量"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)

        list_nodes = _iter_graph_variables_list_nodes(tree)
        if not list_nodes:
            return []

        known_struct_names = _collect_known_struct_names()

        issues: List[EngineIssue] = []
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
                struct_name_text = ""
                struct_name_node: ast.AST | None = None

                for kw in getattr(element, "keywords", []) or []:
                    key = getattr(kw, "arg", None)
                    value_node = getattr(kw, "value", None)
                    if key == "name" and isinstance(value_node, ast.Constant) and isinstance(
                        getattr(value_node, "value", None), str
                    ):
                        name_text = str(value_node.value).strip()
                        continue
                    if key == "variable_type" and isinstance(value_node, ast.Constant) and isinstance(
                        getattr(value_node, "value", None), str
                    ):
                        variable_type_text = str(value_node.value).strip()
                        continue
                    if key == "default_value":
                        has_default_value_kw = True
                        default_value_node = value_node
                        continue
                    if key == "struct_name":
                        struct_name_node = value_node
                        if isinstance(value_node, ast.Constant) and isinstance(
                            getattr(value_node, "value", None), str
                        ):
                            struct_name_text = str(value_node.value).strip()
                        continue

                if variable_type_text not in {TYPE_STRUCT, TYPE_STRUCT_LIST}:
                    continue

                # 未显式指定 default_value：按默认 None/空列表语义处理，不在此处强制 struct_name
                if not has_default_value_kw or default_value_node is None:
                    continue

                extracted = extract_constant_value(default_value_node)
                if extracted is NOT_EXTRACTABLE:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            default_value_node,
                            "CODE_GRAPH_VAR_STRUCT_DEFAULT_NOT_STATIC",
                            (
                                f"{line_span_text(default_value_node)}: GRAPH_VARIABLES 中结构体类型图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的 default_value 必须可静态解析为常量；"
                                f"当前写法为 {ast.unparse(default_value_node)}"
                            ),
                        )
                    )
                    continue

                is_empty_default = False
                if variable_type_text == TYPE_STRUCT:
                    is_empty_default = extracted is None
                else:
                    if extracted is None:
                        is_empty_default = True
                    elif isinstance(extracted, (list, tuple)) and len(extracted) == 0:
                        is_empty_default = True

                if is_empty_default:
                    continue

                # 非空默认值：必须提供 struct_name 且为非空字符串字面量
                if not struct_name_text:
                    target = struct_name_node if struct_name_node is not None else element
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            target,
                            "CODE_GRAPH_VAR_STRUCT_NAME_REQUIRED",
                            (
                                f"{line_span_text(target)}: GRAPH_VARIABLES 中结构体类型图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 给出了非空 default_value，"
                                "必须同时提供非空字符串字面量参数 struct_name，并指向已存在的结构体定义。"
                            ),
                        )
                    )
                    continue

                if known_struct_names and struct_name_text not in known_struct_names:
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            struct_name_node if struct_name_node is not None else element,
                            "CODE_GRAPH_VAR_STRUCT_NAME_UNKNOWN",
                            (
                                f"{line_span_text(struct_name_node if struct_name_node is not None else element)}: "
                                f"GRAPH_VARIABLES 中结构体类型图变量"
                                f"{('『' + name_text + '』') if name_text else ''} 的 struct_name='{struct_name_text}' "
                                "在当前工程的结构体定义中不存在；请在“管理配置/结构体定义”中确认 struct_name 并修正。"
                            ),
                        )
                    )

        return issues


__all__ = ["GraphVarsStructNameRequiredRule"]


