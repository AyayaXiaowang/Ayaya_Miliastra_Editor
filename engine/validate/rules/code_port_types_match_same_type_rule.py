from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..context import ValidationContext
from ..issue import EngineIssue
from ..pipeline import ValidationRule
from .ast_utils import get_cached_module, infer_graph_scope, line_span_text
from .node_index import (
    node_function_names,
    callable_node_defs_by_name,
    input_types_by_func,
    output_types_by_func,
    input_generic_constraints_by_func,
    input_enum_options_by_func,
)
from .ui_key_registry_utils import (
    parse_ui_key_placeholder,
    try_load_ui_html_ui_keys_for_ctx,
)
from .component_registry_utils import (
    parse_component_key_placeholder,
)
from .entity_registry_utils import parse_entity_key_placeholder
from engine.nodes.port_type_system import can_connect_ports, FLOW_PORT_TYPE, ANY_PORT_TYPE, GENERIC_PORT_TYPE
from engine.type_registry import TYPE_GENERIC_DICT, TYPE_SUFFIX_LIST, can_convert_type, parse_typed_dict_alias
from engine.utils.graph.graph_utils import is_flow_port_name


from .code_port_types_match_shared import (
    _CONST_TYPE_MAP,
    _TYPE_CONVERSION_NODE_FUNC_NAME,
    collect_annotated_vars as _collect_annotated_vars,
    collect_var_types as _collect_var_types,
    extract_call_port_expr as _extract_call_port_expr,
    extract_type_conversion_input_expr as _extract_type_conversion_input_expr,
    is_type_allowed_by_constraints as _is_type_allowed_by_constraints,
    iter_calls_to_nodes as _iter_calls_to_nodes,
    iter_methods as _iter_methods,
    looks_like_game_expr as _looks_like_game_expr,
    normalize_type as _normalize_type,
    single_target_name as _single_target_name,
    unique_data_output_type as _unique_data_output_type,
)


class SameTypeInputsRule(ValidationRule):
    """同型输入约束：对部分比较/数值比较/二元运算/选择节点，要求指定输入端口的数据类型严格一致。

    设计目的：
    - 避免在“泛型”端口上混用类型导致静态校验漏掉明显错误（例如 GUID vs 字符串、整数 vs 浮点数）。
    - 本规则只在两侧类型均可静态推断且均为具体类型时生效；无法推断或为“泛型”时不阻断。

    约定：
    - 整数与浮点数视为两种不同类型，不做隐式兼容。
    """

    rule_id = "engine_code_port_same_type_inputs"
    category = "代码规范"
    default_level = "error"

    _SAME_TYPE_PORT_GROUPS: Dict[str, Tuple[Tuple[str, ...], ...]] = {
        # 比较
        "是否相等": (("输入1", "输入2"),),
        "枚举是否相等": (("枚举1", "枚举2"),),
        # 数值比较
        "数值大于": (("左值", "右值"),),
        "数值小于": (("左值", "右值"),),
        "数值大于等于": (("左值", "右值"),),
        "数值小于等于": (("左值", "右值"),),
        # 二元选择
        "取较大值": (("输入1", "输入2"),),
        "取较小值": (("输入1", "输入2"),),
        # 三元同型：输入/上下限必须一致
        "范围限制运算": (("输入", "下限", "上限"),),
        # 二元数值运算：要求左右值类型一致（整数≠浮点数）
        "加法运算": (("左值", "右值"),),
        "减法运算": (("左值", "右值"),),
        "乘法运算": (("左值", "右值"),),
        "除法运算": (("左值", "右值"),),
    }

    # 变参节点：所有提供的值必须同型
    _VARIADIC_VALUES_SAME_TYPE: Set[str] = {"拼装列表"}

    # 键值对变参节点：键同型、值同型（如【拼装字典】）
    _VARIADIC_KEY_VALUE_PAIRS_SAME_TYPE: Set[str] = {"拼装字典"}

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        # 同型输入约束同样适用于复合节点源码（类格式复合节点的方法体也是 Graph Code）。
        # 过去复合节点规则集未启用该规则，因此这里不应再按 is_composite 跳过。
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        scope = infer_graph_scope(ctx)
        func_names = node_function_names(ctx.workspace_path, scope)
        out_types = output_types_by_func(ctx.workspace_path, scope)
        node_defs_by_name = callable_node_defs_by_name(
            ctx.workspace_path, scope, include_composite=True
        )

        issues: List[EngineIssue] = []

        for _, method in _iter_methods(tree):
            var_types: Dict[str, str] = _collect_var_types(method, func_names, out_types)

            for call in _iter_calls_to_nodes(method, func_names):
                func = getattr(call, "func", None)
                if not isinstance(func, ast.Name):
                    continue
                function_name = func.id

                if (
                    function_name not in self._SAME_TYPE_PORT_GROUPS
                    and function_name not in self._VARIADIC_VALUES_SAME_TYPE
                    and function_name not in self._VARIADIC_KEY_VALUE_PAIRS_SAME_TYPE
                ):
                    continue

                if function_name in self._VARIADIC_VALUES_SAME_TYPE:
                    element_exprs = self._collect_variadic_value_exprs(call)
                    issues.extend(
                        self._check_exprs_same_type(
                            file_path=file_path,
                            at=call,
                            function_name=function_name,
                            label="变参值",
                            exprs=element_exprs,
                            var_types=var_types,
                            func_names=func_names,
                            out_types=out_types,
                        )
                    )
                    continue

                if function_name in self._VARIADIC_KEY_VALUE_PAIRS_SAME_TYPE:
                    node_def = node_defs_by_name.get(function_name)
                    positional_exprs = self._collect_variadic_positional_value_exprs(call)
                    key_exprs = positional_exprs[0::2]
                    value_exprs = positional_exprs[1::2]

                    issues.extend(
                        self._check_exprs_same_type(
                            file_path=file_path,
                            at=call,
                            function_name=function_name,
                            label="键",
                            exprs=key_exprs,
                            var_types=var_types,
                            func_names=func_names,
                            out_types=out_types,
                        )
                    )
                    issues.extend(
                        self._check_exprs_same_type(
                            file_path=file_path,
                            at=call,
                            function_name=function_name,
                            label="值",
                            exprs=value_exprs,
                            var_types=var_types,
                            func_names=func_names,
                            out_types=out_types,
                        )
                    )

                    # 泛型约束：对【拼装字典】的键/值分别做允许类型检查（只在类型可推断且为具体类型时生效）
                    if node_def is not None:
                        constraints_map = dict(getattr(node_def, "input_generic_constraints", {}) or {})
                        key_constraint_port = next(
                            (p for p in constraints_map.keys() if isinstance(p, str) and ("~" in p) and p.startswith("键")),
                            None,
                        )
                        value_constraint_port = next(
                            (p for p in constraints_map.keys() if isinstance(p, str) and ("~" in p) and p.startswith("值")),
                            None,
                        )
                        key_allowed = list(constraints_map.get(key_constraint_port) or []) if key_constraint_port else []
                        value_allowed = list(constraints_map.get(value_constraint_port) or []) if value_constraint_port else []

                        if key_allowed:
                            allowed_display = "、".join(key_allowed)
                            for expr in key_exprs:
                                inferred = self._infer_expr_type(expr, var_types, func_names, out_types)
                                actual = _normalize_type(inferred)
                                if not actual or actual == GENERIC_PORT_TYPE:
                                    continue
                                if not _is_type_allowed_by_constraints(actual, key_allowed):
                                    issues.append(
                                        EngineIssue(
                                            level=self.default_level,
                                            category=self.category,
                                            code="PORT_GENERIC_CONSTRAINT_VIOLATION",
                                            message=(
                                                f"{line_span_text(expr)}: 函数 '{function_name}' 输入端口 '{key_constraint_port or '键'}' "
                                                f"仅允许类型『{allowed_display}』，实际传入类型『{inferred}』"
                                            ),
                                            file=str(file_path),
                                            line_span=line_span_text(expr),
                                        )
                                    )

                        if value_allowed:
                            allowed_display = "、".join(value_allowed)
                            for expr in value_exprs:
                                inferred = self._infer_expr_type(expr, var_types, func_names, out_types)
                                actual = _normalize_type(inferred)
                                if not actual or actual == GENERIC_PORT_TYPE:
                                    continue
                                if not _is_type_allowed_by_constraints(actual, value_allowed):
                                    issues.append(
                                        EngineIssue(
                                            level=self.default_level,
                                            category=self.category,
                                            code="PORT_GENERIC_CONSTRAINT_VIOLATION",
                                            message=(
                                                f"{line_span_text(expr)}: 函数 '{function_name}' 输入端口 '{value_constraint_port or '值'}' "
                                                f"仅允许类型『{allowed_display}』，实际传入类型『{inferred}』"
                                            ),
                                            file=str(file_path),
                                            line_span=line_span_text(expr),
                                        )
                                    )

                    continue

                node_def = node_defs_by_name.get(function_name)
                port_exprs = self._collect_port_exprs(call, node_def=node_def)
                for port_group in self._SAME_TYPE_PORT_GROUPS.get(function_name, ()):
                    group_exprs: List[ast.expr] = []
                    missing_ports: List[str] = []
                    for port_name in port_group:
                        expr_value = port_exprs.get(port_name)
                        if expr_value is None:
                            missing_ports.append(port_name)
                            continue
                        group_exprs.append(expr_value)
                    # 缺失端口由 RequiredInputsRule 等规则负责；这里不重复报错
                    if missing_ports:
                        continue

                    issues.extend(
                        self._check_exprs_same_type(
                            file_path=file_path,
                            at=call,
                            function_name=function_name,
                            label="、".join(port_group),
                            exprs=group_exprs,
                            var_types=var_types,
                            func_names=func_names,
                            out_types=out_types,
                            port_names=list(port_group),
                        )
                    )

        return issues

    def _collect_port_exprs(self, call: ast.Call, *, node_def: object | None) -> Dict[str, ast.expr]:
        """从 Call 中收集端口入参表达式（支持关键字参数与位置参数）。"""
        expr_by_port_name: Dict[str, ast.expr] = {}

        has_game_keyword = False
        for keyword_arg in getattr(call, "keywords", []) or []:
            if not isinstance(keyword_arg, ast.keyword):
                continue
            if not isinstance(getattr(keyword_arg, "arg", None), str):
                continue
            if keyword_arg.arg == "game":
                has_game_keyword = True
                continue
            expr_by_port_name[keyword_arg.arg] = keyword_arg.value

        if node_def is None:
            return expr_by_port_name

        positional_args: List[ast.expr] = list(getattr(call, "args", []) or [])
        if positional_args and (not has_game_keyword) and self._looks_like_game_expr(positional_args[0]):
            positional_args = positional_args[1:]

        input_ports_in_order: List[str] = [
            str(port_name)
            for port_name in (getattr(node_def, "inputs", []) or [])
            if port_name and (not is_flow_port_name(str(port_name)))
        ]
        for position_index, value_expr in enumerate(positional_args):
            if position_index >= len(input_ports_in_order):
                break
            port_name = input_ports_in_order[position_index]
            if port_name not in expr_by_port_name:
                expr_by_port_name[port_name] = value_expr

        return expr_by_port_name

    def _collect_variadic_value_exprs(self, call: ast.Call) -> List[ast.expr]:
        """收集变参节点提供的所有值表达式（排除 game）。"""
        has_game_keyword = False
        keyword_values: List[ast.expr] = []
        for keyword_arg in getattr(call, "keywords", []) or []:
            if not isinstance(keyword_arg, ast.keyword):
                continue
            if not isinstance(getattr(keyword_arg, "arg", None), str):
                continue
            if keyword_arg.arg == "game":
                has_game_keyword = True
                continue
            keyword_values.append(keyword_arg.value)

        positional_args: List[ast.expr] = list(getattr(call, "args", []) or [])
        if positional_args and (not has_game_keyword) and self._looks_like_game_expr(positional_args[0]):
            positional_args = positional_args[1:]

        return positional_args + keyword_values

    def _collect_variadic_positional_value_exprs(self, call: ast.Call) -> List[ast.expr]:
        """收集变参节点的**位置参数**值表达式（排除 game），用于需要稳定“成对顺序”的场景（如拼装字典）。"""
        has_game_keyword = False
        for keyword_arg in getattr(call, "keywords", []) or []:
            if not isinstance(keyword_arg, ast.keyword):
                continue
            if not isinstance(getattr(keyword_arg, "arg", None), str):
                continue
            if keyword_arg.arg == "game":
                has_game_keyword = True
                break

        positional_args: List[ast.expr] = list(getattr(call, "args", []) or [])
        if positional_args and (not has_game_keyword) and self._looks_like_game_expr(positional_args[0]):
            positional_args = positional_args[1:]
        return positional_args

    def _looks_like_game_expr(self, expr: ast.expr) -> bool:
        """启发式判断一个表达式是否为 Graph Code 约定的 game 实参。"""
        if isinstance(expr, ast.Name) and expr.id == "game":
            return True
        if isinstance(expr, ast.Attribute):
            if isinstance(expr.value, ast.Name) and expr.value.id == "self" and expr.attr == "game":
                return True
        return False

    def _check_exprs_same_type(
        self,
        *,
        file_path: Path,
        at: ast.AST,
        function_name: str,
        label: str,
        exprs: List[ast.expr],
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
        port_names: Optional[List[str]] = None,
    ) -> List[EngineIssue]:
        if len(exprs) < 2:
            return []

        inferred_types: List[str] = [
            self._infer_expr_type(expr, var_types, func_names, out_types) for expr in exprs
        ]
        normalized_types: List[str] = [_normalize_type(type_name) for type_name in inferred_types]

        # 只在“均可推断且均为具体类型”时生效；泛型/未知不阻断，避免误报
        if any((not type_name) or (type_name == GENERIC_PORT_TYPE) for type_name in normalized_types):
            return []

        unique_types = sorted(set(normalized_types))
        if len(unique_types) <= 1:
            return []

        if port_names and len(port_names) == len(normalized_types):
            pairs_display = "，".join(
                f"{port_name}={type_name}"
                for port_name, type_name in zip(port_names, normalized_types, strict=True)
            )
        else:
            pairs_display = "，".join(
                f"参数[{index}]={type_name}"
                for index, type_name in enumerate(normalized_types)
            )

        message = (
            f"{line_span_text(at)}: 函数 '{function_name}' 要求 {label} 的数据类型必须完全一致，"
            f"但当前为：{pairs_display}。"
            "整数与浮点数视为不同类型；如确需比较/运算，请先用【数据类型转换】或显式类型注解将两侧统一为同一类型。"
        )
        return [
            EngineIssue(
                level=self.default_level,
                category=self.category,
                code="PORT_SAME_TYPE_REQUIRED",
                message=message,
                file=str(file_path),
                line_span=line_span_text(at),
            )
        ]

    def _infer_expr_type(
        self,
        expr: ast.AST,
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
    ) -> str:
        # 常量
        if isinstance(expr, ast.Constant):
            python_value_type = type(getattr(expr, "value", None))
            return _CONST_TYPE_MAP.get(python_value_type, "")
        # 变量
        if isinstance(expr, ast.Name):
            return var_types.get(expr.id, "")
        # 调用（仅支持节点函数名调用）
        if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
            called_name = expr.func.id
            if called_name in func_names:
                return _unique_data_output_type(out_types.get(called_name, []))
        return ""
