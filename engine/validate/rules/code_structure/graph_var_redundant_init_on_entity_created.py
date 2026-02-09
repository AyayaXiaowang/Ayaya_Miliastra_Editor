from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.graph.common import VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.graph.utils.metadata_extractor import extract_graph_variables_from_ast
from engine.validate.node_semantics import SEMANTIC_GRAPH_VAR_SET, is_semantic_node_call

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


def _get_keyword_arg(call_node: ast.Call, keyword_name: str) -> Optional[ast.expr]:
    for keyword in call_node.keywords or []:
        if keyword.arg == keyword_name:
            return keyword.value
    return None


def _is_call_name(call_node: ast.Call, expected_name: str) -> bool:
    func = getattr(call_node, "func", None)
    return isinstance(func, ast.Name) and func.id == expected_name


def _format_constant_value(value: Any) -> str:
    if value is NOT_EXTRACTABLE:
        return "<不可静态解析>"
    return repr(value)


class GraphVarRedundantInitOnEntityCreatedRule(ValidationRule):
    """warning：on_实体创建时 中将节点图变量“设回默认值”的冗余初始化提示。

    背景：
    - 节点图变量在 GRAPH_VARIABLES 中已声明 default_value；
    - 对绝大多数变量而言，在 on_实体创建时 又无条件设置为同样的默认值，通常没有意义，只会增加图噪声；
    - 少数“必须在实体创建时动态采样”的变量（例如记录自身位置/旋转）不会命中“默认值相等”的条件，因此不会误报。

    规则（启发式，保守）：
    - 仅检查类结构节点图（非复合节点）
    - 仅检查方法名为 `on_实体创建时`
    - 仅当【设置节点图变量】的 变量名/变量值 都可静态识别，且变量值与 GRAPH_VARIABLES.default_value 相等时提示
    - 对 “列表先 clear 再写回节点图变量” 这种常见写法，额外支持识别为等价空列表（避免漏报）
    """

    rule_id = "engine_code_graph_var_redundant_init_on_entity_created"
    category = "代码规范"
    default_level = "warning"

    _METHOD_NAME = "on_实体创建时"
    _GRAPH_VAR_VALUE_PORT_NAME = "变量值"

    # list_literal_rewriter 会把 `目标列表.clear()` 改写为 `清除列表(self.game, 列表=目标列表)`
    _LIST_CLEAR_NODE_CALL_NAME = "清除列表"
    _LIST_CLEAR_PORT_NAME = "列表"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)

        declared_graph_vars = extract_graph_variables_from_ast(tree)
        default_value_by_name: Dict[str, Any] = {}
        variable_type_by_name: Dict[str, str] = {}
        for entry in declared_graph_vars:
            var_name = entry.get("name")
            if not isinstance(var_name, str) or not var_name.strip():
                continue
            normalized_name = var_name.strip()
            default_value_by_name[normalized_name] = entry.get("default_value", None)
            var_type = entry.get("variable_type")
            if isinstance(var_type, str) and var_type.strip():
                variable_type_by_name[normalized_name] = var_type.strip()

        if not default_value_by_name:
            return []

        issues: List[EngineIssue] = []

        for class_node, method in iter_class_methods(tree):
            if method.name != self._METHOD_NAME:
                continue

            known_empty_list_names: Set[str] = set()
            known_constant_locals: Dict[str, Any] = {}

            for statement in list(getattr(method, "body", []) or []):
                # ------------------------------------------------------------------
                # 1) 维护“局部变量的可静态信息”（仅做最小线性跟踪，避免复杂控制流误判）
                # ------------------------------------------------------------------
                self._update_linear_local_tracking(
                    statement,
                    known_empty_list_names=known_empty_list_names,
                    known_constant_locals=known_constant_locals,
                )

                call_node = self._extract_top_level_call(statement)
                if call_node is None:
                    continue

                call_name = getattr(getattr(call_node, "func", None), "id", None)
                if not isinstance(call_name, str):
                    continue

                if not is_semantic_node_call(
                    workspace_path=ctx.workspace_path,
                    scope=scope,
                    call_name=call_name,
                    semantic_id=SEMANTIC_GRAPH_VAR_SET,
                ):
                    continue

                var_name_expr = _get_keyword_arg(call_node, VARIABLE_NAME_PORT_NAME)
                if not (
                    isinstance(var_name_expr, ast.Constant)
                    and isinstance(getattr(var_name_expr, "value", None), str)
                ):
                    continue
                graph_var_name = str(var_name_expr.value).strip()
                if not graph_var_name:
                    continue

                declared_default_value = default_value_by_name.get(graph_var_name, None)
                # default_value 为 None 时无法区分“未提取到默认值”与“默认值就是 None”，保守跳过
                if declared_default_value is None:
                    continue

                value_expr = _get_keyword_arg(call_node, self._GRAPH_VAR_VALUE_PORT_NAME)
                if value_expr is None:
                    continue

                assigned_value = self._extract_assigned_value(
                    value_expr,
                    known_empty_list_names=known_empty_list_names,
                    known_constant_locals=known_constant_locals,
                )
                if assigned_value is NOT_EXTRACTABLE:
                    continue

                if assigned_value != declared_default_value:
                    continue

                variable_type_text = variable_type_by_name.get(graph_var_name, "")
                type_hint = f"（类型: {variable_type_text}）" if variable_type_text else ""
                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        value_expr if hasattr(value_expr, "lineno") else call_node,
                        "CODE_GRAPH_VAR_REDUNDANT_INIT_DEFAULT",
                        (
                            f"{line_span_text(value_expr if hasattr(value_expr, 'lineno') else call_node)}: "
                            f"方法 {class_node.name}.{method.name} 内对节点图变量『{graph_var_name}』{type_hint} 进行了冗余初始化："
                            f"GRAPH_VARIABLES 默认值已为 {_format_constant_value(declared_default_value)}，"
                            f"这里又设置为 {_format_constant_value(assigned_value)}。"
                            "若只是为了“初始化为默认值”，建议删除该设置；仅在你确实需要在实体创建时显式重置运行期状态时才保留。"
                        ),
                    )
                )

        return issues

    def _extract_top_level_call(self, statement: ast.stmt) -> Optional[ast.Call]:
        if not isinstance(statement, ast.Expr):
            return None
        expr_value = getattr(statement, "value", None)
        if isinstance(expr_value, ast.Call):
            return expr_value
        return None

    def _update_linear_local_tracking(
        self,
        statement: ast.stmt,
        *,
        known_empty_list_names: Set[str],
        known_constant_locals: Dict[str, Any],
    ) -> None:
        # 1) list.clear() / 清除列表(...) 这类“确定置空”
        call_node = self._extract_top_level_call(statement)
        if call_node is not None:
            # a) 语法糖原样：目标列表.clear()
            func = getattr(call_node, "func", None)
            if isinstance(func, ast.Attribute) and func.attr == "clear":
                target = getattr(func, "value", None)
                if isinstance(target, ast.Name):
                    known_empty_list_names.add(target.id)
                    known_constant_locals.pop(target.id, None)
                return

            # b) 语法糖改写：清除列表(self.game, 列表=目标列表)
            if _is_call_name(call_node, self._LIST_CLEAR_NODE_CALL_NAME):
                list_arg = _get_keyword_arg(call_node, self._LIST_CLEAR_PORT_NAME)
                if isinstance(list_arg, ast.Name):
                    known_empty_list_names.add(list_arg.id)
                    known_constant_locals.pop(list_arg.id, None)
                return

        # 2) 赋值语句：记录可静态解析的常量；若被覆盖则清理历史信息
        assigned_name, value_expr = self._extract_single_name_assignment(statement)
        if assigned_name is None:
            return

        # 覆盖赋值会使之前的“空列表/常量”信息失效
        known_empty_list_names.discard(assigned_name)
        known_constant_locals.pop(assigned_name, None)

        if value_expr is None:
            return

        extracted_value = extract_constant_value(value_expr)
        if extracted_value is NOT_EXTRACTABLE:
            return
        known_constant_locals[assigned_name] = extracted_value

    def _extract_single_name_assignment(self, statement: ast.stmt) -> Tuple[Optional[str], Optional[ast.expr]]:
        if isinstance(statement, ast.Assign):
            targets = list(getattr(statement, "targets", []) or [])
            if len(targets) != 1:
                return None, None
            target = targets[0]
            if isinstance(target, ast.Name):
                value_expr = getattr(statement, "value", None)
                return target.id, value_expr if isinstance(value_expr, ast.expr) else None
            return None, None

        if isinstance(statement, ast.AnnAssign):
            target = getattr(statement, "target", None)
            if isinstance(target, ast.Name):
                value_expr = getattr(statement, "value", None)
                return target.id, value_expr if isinstance(value_expr, ast.expr) else None
            return None, None

        return None, None

    def _extract_assigned_value(
        self,
        value_expr: ast.expr,
        *,
        known_empty_list_names: Set[str],
        known_constant_locals: Dict[str, Any],
    ) -> Any:
        if isinstance(value_expr, ast.Name):
            local_name = value_expr.id
            if local_name in known_empty_list_names:
                return []
            if local_name in known_constant_locals:
                return known_constant_locals[local_name]
            return NOT_EXTRACTABLE

        extracted_value = extract_constant_value(value_expr)
        return extracted_value


__all__ = ["GraphVarRedundantInitOnEntityCreatedRule"]


