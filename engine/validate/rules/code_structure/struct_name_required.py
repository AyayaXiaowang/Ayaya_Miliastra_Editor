from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set

from engine.graph.common import STRUCT_NAME_PORT_NAME, STRUCT_NODE_TITLES
from engine.resources.definition_schema_view import get_default_definition_schema_view

from ...context import ValidationContext
from ...issue import EngineIssue
from ...pipeline import ValidationRule
from ..ast_utils import create_rule_issue, get_cached_module, iter_class_methods, line_span_text


@lru_cache(maxsize=1)
def _known_struct_ids() -> Set[str]:
    """返回当前工程内所有结构体定义的 STRUCT_ID 集合（basic + ingame_save）。"""
    schema_view = get_default_definition_schema_view()
    all_structs = schema_view.get_all_struct_definitions()
    result: Set[str] = set()
    for struct_id in (all_structs.keys() if isinstance(all_structs, dict) else []):
        if isinstance(struct_id, str):
            stripped = struct_id.strip()
            if stripped:
                result.add(stripped)
    return result


def _collect_module_constant_strings(tree: ast.AST) -> Dict[str, str]:
    """收集模块顶层的字符串常量声明（支持普通与注解赋值）。"""
    constant_strings: Dict[str, str] = {}
    module_body = getattr(tree, "body", []) or []
    for node in module_body:
        target_names: List[str] = []
        value_node = None
        if isinstance(node, ast.Assign):
            value_node = getattr(node, "value", None)
            for target in getattr(node, "targets", []) or []:
                if isinstance(target, ast.Name):
                    target_names.append(target.id)
        elif isinstance(node, ast.AnnAssign):
            value_node = getattr(node, "value", None)
            target = getattr(node, "target", None)
            if isinstance(target, ast.Name):
                target_names.append(target.id)
        if not target_names or not isinstance(value_node, ast.Constant):
            continue
        if not isinstance(getattr(value_node, "value", None), str):
            continue
        constant_text = value_node.value.strip()
        if not constant_text:
            continue
        for target_name in target_names:
            if target_name and target_name not in constant_strings:
                constant_strings[target_name] = constant_text
    return constant_strings


def _extract_struct_name_from_value(
    value_node: ast.AST | None, constant_strings: Dict[str, str]
) -> str:
    """解析“结构体名”参数的取值：直接字面量或顶层命名常量。"""
    if isinstance(value_node, ast.Constant) and isinstance(
        getattr(value_node, "value", None), str
    ):
        return value_node.value.strip()
    if isinstance(value_node, ast.Name):
        referenced_text = constant_strings.get(value_node.id, "")
        return referenced_text.strip()
    return ""


class StructNameRequiredRule(ValidationRule):
    """结构体相关节点：“结构体名”参数的值必须可静态解析且指向有效结构体定义。

    目标：
    - 对 `结构体名` 的内容做强校验（非空、可解析、存在于结构体定义中），避免拼写错误被静默忽略；
    - “缺少必填入参”的情况由通用规则 `RequiredInputsRule` 统一处理，此规则不再重复报错。
    """

    rule_id = "engine_code_struct_name_required"
    category = "结构体系统"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_constant_strings = _collect_module_constant_strings(tree)
        known_struct_ids = _known_struct_ids()

        issues: List[EngineIssue] = []

        for _, method in iter_class_methods(tree):
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                func = getattr(node, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                node_title = func.id
                if node_title not in STRUCT_NODE_TITLES:
                    continue

                struct_kw_value_node = None
                for kw in getattr(node, "keywords", []) or []:
                    if kw.arg == STRUCT_NAME_PORT_NAME:
                        struct_kw_value_node = getattr(kw, "value", None)
                        break

                if struct_kw_value_node is None:
                    # 缺参由通用必填入参规则负责
                    continue

                struct_name = _extract_struct_name_from_value(
                    struct_kw_value_node, module_constant_strings
                )

                if not struct_name:
                    msg = (
                        f"{line_span_text(node)}: 【{node_title}】的“{STRUCT_NAME_PORT_NAME}”必须是非空字符串字面量，"
                        f"或引用模块顶层字符串常量；不允许使用运行期表达式。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_STRUCT_NAME_INVALID",
                            msg,
                        )
                    )
                    continue

                if known_struct_ids and struct_name not in known_struct_ids:
                    msg = (
                        f"{line_span_text(node)}: 【{node_title}】的“{STRUCT_NAME_PORT_NAME}”取值 '{struct_name}' "
                        f"在当前工程的结构体定义中不存在；请在“管理配置/结构体定义”中确认 STRUCT_ID，"
                        f"并修正为有效结构体名称。"
                    )
                    issues.append(
                        create_rule_issue(
                            self,
                            file_path,
                            node,
                            "CODE_STRUCT_NAME_UNKNOWN",
                            msg,
                        )
                    )

        return issues


__all__ = ["StructNameRequiredRule"]


