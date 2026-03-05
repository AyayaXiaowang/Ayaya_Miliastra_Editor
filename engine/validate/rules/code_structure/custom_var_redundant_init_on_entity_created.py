from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from engine.graph.common import VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, collect_module_constants, extract_constant_value
from engine.validate.node_semantics import SEMANTIC_CUSTOM_VAR_SET, is_semantic_node_call

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


class CustomVarRedundantInitOnEntityCreatedRule(ValidationRule):
    """warning：on_实体创建时 中对【设置自定义变量】写入“常量初始值”的冗余初始化提示。

    背景：
    - 自定义变量应在实体/模板的变量定义中声明默认值（实体创建时自动完成初始化）；
    - 在 on_实体创建时 再无条件写入常量值，通常属于无意义初始化，只会增加图噪声。

    规则（启发式，保守）：
    - 仅检查类结构节点图（非复合节点）
    - 仅检查方法名为 `on_实体创建时`
    - 仅当【设置自定义变量】的 变量名/变量值 都可静态识别，且变量值为常量（含“列表 clear 后写回空列表”）时提示
    """

    rule_id = "engine_code_custom_var_redundant_init_on_entity_created"
    category = "代码规范"
    default_level = "warning"

    _METHOD_NAME = "on_实体创建时"
    _CUSTOM_VAR_VALUE_PORT_NAME = "变量值"

    # list_literal_rewriter 会把 `目标列表.clear()` 改写为 `清除列表(self.game, 列表=目标列表)`
    _LIST_CLEAR_NODE_CALL_NAME = "清除列表"
    _LIST_CLEAR_PORT_NAME = "列表"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)

        module_constants: Dict[str, Any] = collect_module_constants(tree)

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
                    module_constants=module_constants,
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
                    semantic_id=SEMANTIC_CUSTOM_VAR_SET,
                ):
                    continue

                var_name_expr = _get_keyword_arg(call_node, VARIABLE_NAME_PORT_NAME)
                if var_name_expr is None:
                    continue

                custom_var_name = self._extract_string_constant(
                    var_name_expr,
                    module_constants=module_constants,
                    known_constant_locals=known_constant_locals,
                )
                if custom_var_name is None:
                    continue
                custom_var_name = custom_var_name.strip()
                if not custom_var_name:
                    continue

                value_expr = _get_keyword_arg(call_node, self._CUSTOM_VAR_VALUE_PORT_NAME)
                if value_expr is None:
                    continue

                assigned_value = self._extract_assigned_value(
                    value_expr,
                    known_empty_list_names=known_empty_list_names,
                    known_constant_locals=known_constant_locals,
                    module_constants=module_constants,
                )
                if assigned_value is NOT_EXTRACTABLE:
                    continue

                issues.append(
                    create_rule_issue(
                        self,
                        file_path,
                        value_expr if hasattr(value_expr, "lineno") else call_node,
                        "CODE_CUSTOM_VAR_REDUNDANT_INIT_ON_ENTITY_CREATED",
                        (
                            f"{line_span_text(value_expr if hasattr(value_expr, 'lineno') else call_node)}: "
                            f"方法 {class_node.name}.{method.name} 内在实体创建时对自定义变量『{custom_var_name}』写入了常量值 "
                            f"{_format_constant_value(assigned_value)}，疑似无意义的默认值初始化。"
                            "自定义变量的初始值应在实体/模板的变量定义中设置；若只是为了“初始化为默认值”，建议删除该写入以减少图噪声。"
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

    def _extract_string_constant(
        self,
        expr: ast.expr,
        *,
        module_constants: Dict[str, Any],
        known_constant_locals: Dict[str, Any],
    ) -> Optional[str]:
        if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), str):
            return str(expr.value)

        if isinstance(expr, ast.Name):
            local_value = known_constant_locals.get(expr.id, NOT_EXTRACTABLE)
            if isinstance(local_value, str):
                return local_value
            module_value = module_constants.get(expr.id, NOT_EXTRACTABLE)
            if isinstance(module_value, str):
                return module_value

        return None

    def _update_linear_local_tracking(
        self,
        statement: ast.stmt,
        *,
        known_empty_list_names: Set[str],
        known_constant_locals: Dict[str, Any],
        module_constants: Dict[str, Any],
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

        extracted_value = self._extract_simple_constant(
            value_expr,
            module_constants=module_constants,
        )
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
        module_constants: Dict[str, Any],
    ) -> Any:
        if isinstance(value_expr, ast.Name):
            local_name = value_expr.id
            if local_name in known_empty_list_names:
                return []
            if local_name in known_constant_locals:
                return known_constant_locals[local_name]
            if local_name in module_constants:
                return module_constants[local_name]
            return NOT_EXTRACTABLE

        # self.xxx 属性访问在常量提取中会返回 "self.xxx" 字符串；这里保守视为不可静态解析
        if isinstance(value_expr, ast.Attribute):
            return NOT_EXTRACTABLE

        extracted_value = self._extract_simple_constant(
            value_expr,
            module_constants=module_constants,
        )
        return extracted_value

    def _extract_simple_constant(self, value_expr: ast.expr, *, module_constants: Dict[str, Any]) -> Any:
        """提取“常量初始值”形态（保守）。

        说明：
        - 仅接受字面量/容器字面量/一元数值常量，以及模块级常量名引用；
        - 不接受函数调用/下标/属性访问等运行期表达式，避免误报。
        """
        if isinstance(value_expr, ast.Name):
            return module_constants.get(value_expr.id, NOT_EXTRACTABLE)

        extracted = extract_constant_value(value_expr)
        return extracted


__all__ = ["CustomVarRedundantInitOnEntityCreatedRule"]


