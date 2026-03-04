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
    try_format_invalid_ui_state_group_placeholder_message,
    try_load_ui_html_ui_keys_for_ctx,
)
from .component_registry_utils import (
    parse_component_key_placeholder,
)
from .entity_registry_utils import parse_entity_key_placeholder
from engine.nodes.port_type_system import can_connect_ports, FLOW_PORT_TYPE, ANY_PORT_TYPE, GENERIC_PORT_TYPE
from engine.type_registry import (
    TYPE_COMPONENT_ID_LIST,
    TYPE_CONFIG_ID_LIST,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    LIST_TYPES,
    TYPE_SUFFIX_LIST,
    TYPE_VECTOR3_LIST,
    can_convert_type,
    parse_typed_dict_alias,
)
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.validate.id_digits import is_digits_1_to_10


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


def _is_composite_instance_method_call(call: ast.Call) -> bool:
    """是否为 `self.<alias>.<method>(...)` 形式的复合节点实例方法调用。"""
    func_expr = getattr(call, "func", None)
    if not isinstance(func_expr, ast.Attribute):
        return False
    obj = getattr(func_expr, "value", None)
    if not isinstance(obj, ast.Attribute):
        return False
    owner = getattr(obj, "value", None)
    return isinstance(owner, ast.Name) and owner.id == "self"


def _extract_composite_instance_alias(call: ast.Call) -> str:
    func_expr = getattr(call, "func", None)
    if not isinstance(func_expr, ast.Attribute):
        return ""
    obj = getattr(func_expr, "value", None)
    if not isinstance(obj, ast.Attribute):
        return ""
    owner = getattr(obj, "value", None)
    if not (isinstance(owner, ast.Name) and owner.id == "self"):
        return ""
    return str(getattr(obj, "attr", "") or "")


def _collect_self_composite_instances(class_def: ast.ClassDef) -> Dict[str, str]:
    """收集 `self.<alias> = <CompositeClass>(...)`：返回 {alias: CompositeClassName}。"""
    mapping: Dict[str, str] = {}
    for item in getattr(class_def, "body", []) or []:
        if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
            continue
        for stmt in getattr(item, "body", []) or []:
            if not isinstance(stmt, ast.Assign):
                continue
            rhs = getattr(stmt, "value", None)
            if not isinstance(rhs, ast.Call):
                continue
            rhs_func = getattr(rhs, "func", None)
            if not isinstance(rhs_func, ast.Name):
                continue
            for target in getattr(stmt, "targets", []) or []:
                if not isinstance(target, ast.Attribute):
                    continue
                owner = getattr(target, "value", None)
                if not (isinstance(owner, ast.Name) and owner.id == "self"):
                    continue
                alias = str(getattr(target, "attr", "") or "")
                if alias:
                    mapping[alias] = str(rhs_func.id or "")
        break
    return mapping


def _is_digits_constant_expr(expr: ast.AST) -> bool:
    """是否为可静态识别的“数字 ID 常量”（int 或数字字符串；排除 bool）。"""
    if isinstance(expr, ast.Constant):
        return is_digits_1_to_10(getattr(expr, "value", None))
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
        operand = getattr(expr, "operand", None)
        if isinstance(operand, ast.Constant):
            return is_digits_1_to_10(getattr(operand, "value", None))
    return False


def _is_numeric_literal_expr(expr: ast.AST) -> bool:
    """是否为可静态识别的数值字面量（int/float；排除 bool；允许一元 +/-）。"""
    if isinstance(expr, ast.Constant):
        v = getattr(expr, "value", None)
        return isinstance(v, (int, float)) and (not isinstance(v, bool))
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
        operand = getattr(expr, "operand", None)
        if isinstance(operand, ast.Constant):
            v = getattr(operand, "value", None)
            return isinstance(v, (int, float)) and (not isinstance(v, bool))
    return False


_VECTOR3_COMPONENT_COUNT = 3


def _collect_module_numeric_constant_names(tree: ast.AST) -> frozenset[str]:
    """收集“模块级数值常量”名集合（仅限可静态识别的数值字面量/一元 +/- 字面量）。

    目的：允许 `(VEC_X, VEC_Y, VEC_Z)` 这类“引用模块常量的 tuple 写法”被视为三维向量常量，
    与直接写 `(1.0, 2.0, 3.0)` 保持一致。
    """
    if not isinstance(tree, ast.Module):
        return frozenset()

    names: set[str] = set()
    for stmt in list(getattr(tree, "body", []) or []):
        if isinstance(stmt, ast.Assign):
            value = getattr(stmt, "value", None)
            if not isinstance(value, ast.AST):
                continue
            for target in list(getattr(stmt, "targets", []) or []):
                if not isinstance(target, ast.Name):
                    continue
                if _is_numeric_literal_expr(value):
                    names.add(str(target.id))
                else:
                    # 若曾被识别为数值常量，但后来被赋为非字面量，则不再视为常量。
                    names.discard(str(target.id))
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            value = getattr(stmt, "value", None)
            if isinstance(target, ast.Name) and isinstance(value, ast.AST):
                if _is_numeric_literal_expr(value):
                    names.add(str(target.id))
                else:
                    names.discard(str(target.id))
    return frozenset(names)


def _is_numeric_literal_or_module_constant(
    expr: ast.AST,
    *,
    module_numeric_constant_names: frozenset[str],
) -> bool:
    """是否为数值字面量，或引用了模块级数值常量的表达式。"""
    if _is_numeric_literal_expr(expr):
        return True
    if isinstance(expr, ast.Name):
        return str(expr.id) in module_numeric_constant_names
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, (ast.UAdd, ast.USub)):
        operand = getattr(expr, "operand", None)
        if isinstance(operand, ast.Name):
            return str(operand.id) in module_numeric_constant_names
    return False


def _is_vector3_tuple_literal(
    expr: ast.AST,
    *,
    module_numeric_constant_names: frozenset[str],
) -> bool:
    """三维向量常量写法：仅允许 `(x, y, z)`，且 x/y/z 必须能静态判定为数值字面量（含模块级数值常量名）。"""
    if not isinstance(expr, ast.Tuple):
        return False
    elts = list(getattr(expr, "elts", []) or [])
    if len(elts) != _VECTOR3_COMPONENT_COUNT:
        return False
    return all(
        _is_numeric_literal_or_module_constant(e, module_numeric_constant_names=module_numeric_constant_names)
        for e in elts
    )


def _extract_build_list_elements(expr: ast.AST) -> Optional[List[ast.expr]]:
    """从【拼装列表】调用中提取元素表达式列表（剔除 game/self.game 这类保留首参）。"""
    if not isinstance(expr, ast.Call):
        return None
    func = getattr(expr, "func", None)
    if not (isinstance(func, ast.Name) and func.id == "拼装列表"):
        return None

    element_exprs: List[ast.expr] = []
    has_game_keyword = False
    for one_kw in getattr(expr, "keywords", []) or []:
        if not isinstance(one_kw, ast.keyword):
            continue
        if one_kw.arg == "game":
            has_game_keyword = True
            continue
        if isinstance(one_kw.value, ast.expr):
            element_exprs.append(one_kw.value)
    positional = list(getattr(expr, "args", []) or [])
    if positional and (not has_game_keyword) and _looks_like_game_expr(positional[0]):
        positional = positional[1:]
    element_exprs = positional + element_exprs
    return element_exprs


def _is_vector3_expr(
    expr: ast.expr,
    *,
    var_types: Dict[str, str],
    infer_expr_type: object,
    func_names: Set[str],
    out_types: Dict[str, List[str]],
    module_numeric_constant_names: frozenset[str],
) -> bool:
    """判断表达式是否可被视为三维向量值（字面量/创建节点/带类型变量）。"""
    if _is_vector3_tuple_literal(expr, module_numeric_constant_names=module_numeric_constant_names):
        return True
    if isinstance(expr, ast.Call):
        func = getattr(expr, "func", None)
        if isinstance(func, ast.Name) and str(func.id or "").strip() == "创建三维向量":
            return True
    if isinstance(expr, ast.Name):
        t = str(var_types.get(expr.id, "") or "").strip()
        if _normalize_type(t) == "三维向量":
            return True
    if callable(infer_expr_type):
        t2 = infer_expr_type(expr, var_types, func_names, out_types)  # type: ignore[misc]
        if _normalize_type(t2) == "三维向量":
            return True
    return False

class PortTypesMatchRule(ValidationRule):
    """端口类型匹配校验
    
    能力：
    - 常量 → 中文类型映射（int/float/str/bool）
    - 嵌套节点单输出类型推断（仅当唯一非流程输出）
    - 变量类型追踪（字符串注解形式：“整数/字符串列表/实体”等）
    - 泛型输出：要求变量赋值时显式注解（否则报错）
    """

    rule_id = "engine_code_port_types_match"
    category = "代码规范"
    default_level = "error"

    def apply(self, ctx: ValidationContext) -> List[EngineIssue]:
        # 端口类型匹配同样适用于复合节点源码（类格式复合节点的方法体也是 Graph Code）。
        # 过去复合节点规则集未启用该规则，因此这里不应再按 is_composite 跳过。
        if ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        module_numeric_constant_names = _collect_module_numeric_constant_names(tree)
        ui_view = try_load_ui_html_ui_keys_for_ctx(ctx)
        ui_key_set = set(ui_view.ui_keys) if ui_view is not None else set()
        scope = infer_graph_scope(ctx)
        func_names = node_function_names(ctx.workspace_path, scope)
        in_types = input_types_by_func(ctx.workspace_path, scope)
        out_types = output_types_by_func(ctx.workspace_path, scope)
        in_constraints = input_generic_constraints_by_func(ctx.workspace_path, scope)
        enum_options = input_enum_options_by_func(ctx.workspace_path, scope)

        issues: List[EngineIssue] = []

        # 复合节点实例方法调用需要复合节点 NodeDef（端口类型来自复合节点虚拟引脚/映射成品）。
        from engine.nodes.node_registry import get_node_registry

        registry = get_node_registry(ctx.workspace_path, include_composite=True)
        node_library_all = registry.get_library()

        for class_def, method in _iter_methods(tree):
            annotated_vars: Set[str] = _collect_annotated_vars(method)
            var_types: Dict[str, str] = _collect_var_types(method, func_names, out_types)

            # 1) 泛型输出需注解（仅针对简单“单变量 = 调用()”的赋值）
            for node in ast.walk(method):
                if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                    target_name = _single_target_name(node.targets)
                    if not target_name:
                        continue
                    f = node.value.func
                    if isinstance(f, ast.Name) and (f.id in out_types):
                        outs = _unique_data_output_type(out_types.get(f.id, []))
                        if outs == GENERIC_PORT_TYPE and (target_name not in annotated_vars):
                            issues.append(self._issue(
                                file_path,
                                node,
                                "CODE_GENERIC_OUTPUT_NEEDS_ANNOTATION",
                                f"{line_span_text(node)}: 函数 '{f.id}' 的输出为『泛型』，"
                                f"变量 '{target_name}' 需要显式中文类型注解（例如：x: \"整数\" = ...）以确定端口类型"
                            ))

            # 1.2) 以键查询字典值：注解类型必须与“字典值类型”一致
            # 说明：
            # - 避免 `x: "GUID" = 以键查询字典值(..., 字典=整数-整数字典, ...)` 这类“注解覆盖真实类型”导致漏报；
            # - 仅在“字典入参可静态确定为别名字典类型”时生效，无法推断时不阻断。
            for node in ast.walk(method):
                if not (
                    isinstance(node, ast.AnnAssign)
                    and isinstance(getattr(node, "target", None), ast.Name)
                    and isinstance(getattr(node, "value", None), ast.Call)
                ):
                    continue

                annotation_text = ""
                if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                    annotation_text = str(node.annotation.value)
                normalized_annotation = _normalize_type(annotation_text)
                if (not normalized_annotation) or normalized_annotation == GENERIC_PORT_TYPE:
                    continue

                call_expr = node.value
                if not (isinstance(getattr(call_expr, "func", None), ast.Name) and call_expr.func.id == "以键查询字典值"):
                    continue

                dict_expr = _extract_call_port_expr(call_expr, port_name="字典", positional_index=1)
                if dict_expr is None:
                    continue
                inferred_dict_type = self._infer_expr_type(dict_expr, var_types, func_names, out_types)
                normalized_dict_type = _normalize_type(inferred_dict_type)
                is_typed_dict, _, dict_value_type = parse_typed_dict_alias(normalized_dict_type)
                if not is_typed_dict:
                    continue

                normalized_dict_value_type = _normalize_type(str(dict_value_type or ""))
                if (not normalized_dict_value_type) or normalized_dict_value_type == GENERIC_PORT_TYPE:
                    continue
                if normalized_annotation == normalized_dict_value_type:
                    continue

                issues.append(
                    self._issue(
                        file_path,
                        node,
                        "CODE_DICT_QUERY_ANNOTATION_TYPE_MISMATCH",
                        f"{line_span_text(node)}: 变量 '{node.target.id}' 的类型注解为『{annotation_text}』，"
                        f"但函数 '以键查询字典值' 的字典入参类型为『{normalized_dict_type}』，其值类型应为『{normalized_dict_value_type}』；"
                        "请将注解改为字典值类型，或修正字典变量的类型注解。"
                    )
                )

            # 1.5) 数据类型转换：输入/输出类型联动校验（仅在输入类型与输出类型均可静态推断时生效）
            # 说明：端口层面的“泛型约束”只能限制输入/输出集合，无法表达“输出类型反过来限制输入类型”。
            #      这里以 `engine.type_registry.TYPE_CONVERSIONS` 为权威转换表做补充校验。
            for node in ast.walk(method):
                call_expr: ast.Call | None = None
                output_type_text = ""

                if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "target", None), ast.Name):
                    if isinstance(getattr(node, "value", None), ast.Call):
                        call_expr = node.value
                    if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                        output_type_text = str(node.annotation.value)

                elif isinstance(node, ast.Assign) and isinstance(getattr(node, "value", None), ast.Call):
                    call_expr = node.value
                    target_name = _single_target_name(node.targets)
                    if target_name:
                        output_type_text = str(var_types.get(target_name, "") or "")

                if call_expr is None:
                    continue
                if not (isinstance(getattr(call_expr, "func", None), ast.Name) and call_expr.func.id == _TYPE_CONVERSION_NODE_FUNC_NAME):
                    continue

                normalized_output_type = _normalize_type(output_type_text)
                if (not normalized_output_type) or normalized_output_type == GENERIC_PORT_TYPE:
                    continue

                input_expr = _extract_type_conversion_input_expr(call_expr)
                if input_expr is None:
                    continue
                inferred_input_type = self._infer_expr_type(input_expr, var_types, func_names, out_types)
                normalized_input_type = _normalize_type(inferred_input_type)
                if (not normalized_input_type) or normalized_input_type == GENERIC_PORT_TYPE:
                    continue

                can_convert, _ = can_convert_type(normalized_input_type, normalized_output_type)
                if not can_convert:
                    issues.append(self._issue(
                        file_path,
                        call_expr,
                        "PORT_TYPE_CONVERSION_NOT_ALLOWED",
                        f"{line_span_text(call_expr)}: 数据类型转换不支持『{inferred_input_type}』→『{output_type_text}』；"
                        f"布尔值/浮点数仅支持从整数转换，整数仅支持从布尔值/浮点数转换，字符串支持从整数/实体/GUID/布尔值/浮点数/三维向量/阵营转换"
                    ))

            # 1.6) 强类型列表：当变量显式注解为“具体列表类型”（如『浮点数列表』）时，
            # 若右侧表达式可静态提取为列表元素（列表字面量或【拼装列表】调用），则要求元素类型与 base_type 一致。
            #
            # 说明：
            # - 列表字面量通常会被语法糖改写为 `拼装列表(self.game, ...)`，其输出为“泛型列表”；
            #   若只依赖端口连线规则，则“泛型列表 → 具体列表类型”会被放行，导致 `整数` 塞进 `浮点数列表` 这类错误漏报。
            # - 仅对“元素类型可静态推断”为具体类型的情况生效；无法推断/仍为泛型时不在此处阻断，避免误报。
            for node in ast.walk(method):
                if not isinstance(node, ast.AnnAssign):
                    continue
                annotation_text = ""
                if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                    annotation_text = str(node.annotation.value)
                normalized_list_type = _normalize_type(annotation_text)
                base_type = self._typed_list_base_type(normalized_list_type)
                if not base_type:
                    continue
                value_expr = getattr(node, "value", None)
                if not isinstance(value_expr, ast.expr):
                    continue
                elems = self._extract_list_elements(value_expr)
                if elems is None:
                    continue
                bad_elem = self._first_mismatched_typed_list_elem(
                    elems,
                    expected_base_type=base_type,
                    var_types=var_types,
                    func_names=func_names,
                    out_types=out_types,
                )
                if bad_elem is not None:
                    issues.append(
                        self._issue(
                            file_path,
                            bad_elem,
                            "PORT_TYPED_LIST_ELEMENT_TYPE_MISMATCH",
                            (
                                f"{line_span_text(bad_elem)}: 变量注解为『{annotation_text}』时，"
                                f"列表元素类型必须为『{base_type}』；但当前元素类型不匹配。"
                                "请将元素改为匹配类型的字面量（例如 1.0），或使用【数据类型转换】显式转换后再拼装列表。"
                            ),
                        )
                    )

            # 2) 端口类型匹配
            for call in _iter_calls_to_nodes(method, func_names):
                func_name = call.func.id  # 已保证是 ast.Name
                expect_map = in_types.get(func_name, {})
                if not expect_map:
                    continue
                for kw in getattr(call, "keywords", []) or []:
                    port_name = getattr(kw, "arg", None)
                    if not isinstance(port_name, str):
                        continue
                    expected = expect_map.get(port_name)
                    if not isinstance(expected, str):
                        continue
                    # 流程端口不在本规则检查范围
                    if expected == FLOW_PORT_TYPE:
                        continue

                    # 三维向量常量：允许用 (x, y, z) 直接作为端口常量；禁止使用 [x,y,z]（会被改写为 拼装列表 导致多余节点/类型漂移）。
                    if _normalize_type(expected) == "三维向量":
                        if isinstance(kw.value, ast.Tuple):
                            if not _is_vector3_tuple_literal(
                                kw.value,
                                module_numeric_constant_names=module_numeric_constant_names,
                            ):
                                issues.append(
                                    self._issue(
                                        file_path,
                                        kw.value,
                                        "CODE_VECTOR3_LITERAL_INVALID",
                                        (
                                            f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                            "期望类型『三维向量』时，仅允许使用三维向量常量写法 `(x, y, z)`，且 x/y/z 必须为数值字面量。"
                                        ),
                                    )
                                )
                                continue
                            # 合法向量常量：类型视为三维向量，直接放行后续连线校验
                            continue
                        if isinstance(kw.value, ast.Call) and isinstance(getattr(kw.value, "func", None), ast.Name) and kw.value.func.id == "拼装列表":
                            issues.append(
                                self._issue(
                                    file_path,
                                    kw.value,
                                    "CODE_VECTOR3_LITERAL_LIST_FORBIDDEN",
                                    (
                                        f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' 期望类型『三维向量』时，"
                                        "禁止使用列表字面量 `[x, y, z]`（会改写为【拼装列表】并引入多余节点/类型漂移）。"
                                        "请改用三维向量常量写法 `(x, y, z)`，或显式调用 `创建三维向量(...)`。"
                                    ),
                                )
                            )
                            continue

                    # 三维向量列表：允许列表字面量/拼装列表，但元素必须是“三维向量值”（tuple 常量/创建三维向量/三维向量变量）。
                    if _normalize_type(expected) == TYPE_VECTOR3_LIST:
                        elems: Optional[List[ast.expr]] = None
                        if isinstance(kw.value, ast.List):
                            elems = [e for e in (kw.value.elts or []) if isinstance(e, ast.expr)]
                        else:
                            elems = _extract_build_list_elements(kw.value)
                        if elems is not None:
                            bad_elem = next(
                                (
                                    e
                                    for e in elems
                                    if not _is_vector3_expr(
                                        e,
                                        var_types=var_types,
                                        infer_expr_type=self._infer_expr_type,
                                        func_names=func_names,
                                        out_types=out_types,
                                        module_numeric_constant_names=module_numeric_constant_names,
                                    )
                                ),
                                None,
                            )
                            if bad_elem is not None:
                                issues.append(
                                    self._issue(
                                        file_path,
                                        bad_elem,
                                        "PORT_VECTOR3_LIST_ELEMENT_INVALID",
                                        (
                                            f"{line_span_text(bad_elem)}: 函数 '{func_name}' 输入端口 '{port_name}' 期望类型『{expected}』，"
                                            "但列表元素不是有效的三维向量值。"
                                            "允许的元素写法：`(x, y, z)`（括号 tuple 常量）、`创建三维向量(...)`、或类型为『三维向量』的变量。"
                                            "禁止写法示例：`[x, y, z]`（列表形式的向量）。"
                                        ),
                                    )
                                )
                                continue

                    # 强类型列表：当端口期望具体列表类型（如“浮点数列表/整数列表/字符串列表/实体列表”等）时，
                    # 若实参可静态提取为列表元素（列表字面量或【拼装列表】调用），则要求元素类型与 base_type 一致。
                    base_type = self._typed_list_base_type(_normalize_type(expected))
                    if base_type:
                        elems2 = self._extract_list_elements(kw.value)
                        if elems2 is not None:
                            bad_elem2 = self._first_mismatched_typed_list_elem(
                                elems2,
                                expected_base_type=base_type,
                                var_types=var_types,
                                func_names=func_names,
                                out_types=out_types,
                            )
                            if bad_elem2 is not None:
                                issues.append(
                                    self._issue(
                                        file_path,
                                        bad_elem2,
                                        "PORT_TYPED_LIST_ELEMENT_TYPE_MISMATCH",
                                        (
                                            f"{line_span_text(bad_elem2)}: 函数 '{func_name}' 输入端口 '{port_name}' 期望类型『{expected}』，"
                                            f"其列表元素类型必须为『{base_type}』；但当前元素类型不匹配。"
                                            "请将元素改为匹配类型的字面量（例如 1.0），或使用【数据类型转换】显式转换后再拼装列表。"
                                        ),
                                    )
                                )
                                continue

                    actual = self._infer_expr_type(kw.value, var_types, func_names, out_types)
                    if not actual:
                        # 无法推断类型时暂不报错，由运行时或后续规则处理
                        continue
                    n_actual = _normalize_type(actual)
                    n_expected = _normalize_type(expected)

                    # 算术类运算节点（基础加减乘除）：禁止把『布尔值』当作数值参与运算。
                    # 说明：部分节点历史上声明为『泛型』以复用“整数/浮点数”实现，但这不应放行布尔值。
                    if (func_name in {"乘法运算", "减法运算", "除法运算", "加法运算"}) and (port_name in {"左值", "右值"}):
                        if n_actual == "布尔值":
                            issues.append(self._issue(
                                file_path,
                                kw.value,
                                "PORT_ARITHMETIC_BOOL_NOT_ALLOWED",
                                f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' 禁止传入类型『布尔值』；"
                                f"布尔值不能参与算术运算，请改用数值变量或显式转换/重写分支逻辑"
                            ))
                            continue
                    allowed_types = (
                        (in_constraints.get(func_name, {}) or {}).get(port_name)
                        if func_name in in_constraints
                        else None
                    )
                    if allowed_types:
                        if not _is_type_allowed_by_constraints(n_actual, allowed_types):
                            allowed_display = "、".join(allowed_types)
                            issues.append(self._issue(
                                file_path,
                                kw.value,
                                "PORT_GENERIC_CONSTRAINT_VIOLATION",
                                f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                f"仅允许类型『{allowed_display}』，实际传入类型『{actual}』"
                            ))
                            continue
                    # 宽松兼容 + 枚举字面量校验：
                    # 当期望为『枚举』且传入是字符串常量：
                    # - 若节点定义为该端口声明了枚举候选项，则要求字面量必须落在候选集合内；
                    # - 若未声明候选项，则保持旧行为：仅按类型层面放行该字符串常量。
                    if (n_expected == "枚举") and isinstance(kw.value, ast.Constant) and isinstance(getattr(kw.value, "value", None), str):
                        enum_for_func = enum_options.get(func_name) or {}
                        enum_candidates = enum_for_func.get(port_name)
                        literal_value = str(getattr(kw.value, "value", ""))
                        if isinstance(enum_candidates, list) and len(enum_candidates) > 0:
                            if literal_value not in enum_candidates:
                                allowed_display = "、".join(enum_candidates)
                                issues.append(self._issue(
                                    file_path,
                                    kw.value,
                                    "ENUM_LITERAL_NOT_IN_OPTIONS",
                                    f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                    f"期望枚举值之一『{allowed_display}』，实际传入『{literal_value}』"
                                ))
                            # 无论枚举值是否匹配，均不再进入后续类型连线校验
                            continue
                        # 未配置候选项时，保持旧的“字符串常量视为可接受”的行为
                        continue

                    # 数据类型转换：当端口期望具体类型且传入为【数据类型转换(...)】时，检查输入类型是否可转换到期望类型
                    if (
                        isinstance(kw.value, ast.Call)
                        and isinstance(getattr(kw.value, "func", None), ast.Name)
                        and kw.value.func.id == _TYPE_CONVERSION_NODE_FUNC_NAME
                        and n_expected
                        and n_expected != GENERIC_PORT_TYPE
                    ):
                        conversion_input_expr = _extract_type_conversion_input_expr(kw.value)
                        if conversion_input_expr is not None:
                            inferred_input_type = self._infer_expr_type(conversion_input_expr, var_types, func_names, out_types)
                            normalized_input_type = _normalize_type(inferred_input_type)
                            if normalized_input_type and normalized_input_type != GENERIC_PORT_TYPE:
                                can_convert, _ = can_convert_type(normalized_input_type, n_expected)
                                if not can_convert:
                                    issues.append(self._issue(
                                        file_path,
                                        kw.value,
                                        "PORT_TYPE_CONVERSION_NOT_ALLOWED",
                                        f"{line_span_text(kw.value)}: 数据类型转换不支持『{inferred_input_type}』→『{expected}』；"
                                        f"请按转换规则改写（例如：先转整数再转布尔/浮点，或转为字符串）"
                                    ))
                                    continue

                    # 别名字典强类型约束：当端口期望形如“键类型-值类型字典”时，禁止用“泛型/泛型字典”绕过，
                    # 并对可静态识别的字典构造表达式（拼装字典/建立字典/字典字面量）执行键/值类型校验。
                    is_expected_typed_dict, expected_key_type, expected_value_type = parse_typed_dict_alias(
                        n_expected
                    )
                    if is_expected_typed_dict:
                        typed_dict_error = self._check_typed_dict_alias_argument(
                            kw.value,
                            expected_dict_type=expected,
                            expected_key_type=expected_key_type,
                            expected_value_type=expected_value_type,
                            var_types=var_types,
                            func_names=func_names,
                            out_types=out_types,
                        )
                        if typed_dict_error:
                            issues.append(
                                self._issue(
                                    file_path,
                                    kw.value,
                                    "PORT_TYPED_DICT_ALIAS_MISMATCH",
                                    f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                                    f"期望类型『{expected}』，{typed_dict_error}",
                                )
                            )
                            continue

                    # 工程化：GUID/整数 端口允许使用 ui_key 占位符（编译期替换为真实整数 ID）
                    if (
                        n_expected in {"GUID", "整数"}
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(getattr(kw.value, "value", None), str)
                    ):
                        placeholder_text = str(getattr(kw.value, "value", "")).strip()
                        ui_key = parse_ui_key_placeholder(placeholder_text)
                        if ui_key is not None:
                            # 仅当节点图位于资源库目录结构下时，才做“真实存在性”校验；
                            # tests/ 临时文件等不做强制存在性约束（否则无法定义“当前项目”的 registry）。
                            if ui_view is not None and (not ui_view.html_files):
                                issues.append(
                                    self._issue(
                                        file_path,
                                        kw.value,
                                        "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                        f"{line_span_text(kw.value)}: 端口期望类型『{expected}』时允许使用 ui_key/ui: 占位符，"
                                        "但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                        "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。",
                                    )
                                )
                                continue
                            if ui_view is not None and ui_key not in ui_key_set:
                                invalid_msg = try_format_invalid_ui_state_group_placeholder_message(str(placeholder_text))
                                if invalid_msg is not None:
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            kw.value,
                                            "CODE_UI_STATE_GROUP_PLACEHOLDER_INVALID_FORMAT",
                                            f"{line_span_text(kw.value)}: {invalid_msg} 当前写法为 {placeholder_text!r}",
                                        )
                                    )
                                    continue
                                issues.append(
                                    self._issue(
                                        file_path,
                                        kw.value,
                                        "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                        f"{line_span_text(kw.value)}: 端口期望类型『{expected}』时使用的 ui_key 占位符不存在：{placeholder_text!r}。"
                                        "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。",
                                    )
                                )
                                continue
                            continue
                        # 非占位符字符串：继续进入后续类型匹配逻辑

                        entity_name = parse_entity_key_placeholder(placeholder_text)
                        if entity_name is not None:
                            # 校验阶段不做实体名存在性校验（参考 GIL 在导出/写回时选择）
                            continue

                    # 工程化：元件ID 端口允许使用 component_key/component: 占位符（编译期替换为真实元件ID）
                    if (
                        n_expected in {"元件ID"}
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(getattr(kw.value, "value", None), str)
                    ):
                        placeholder_text = str(getattr(kw.value, "value", "")).strip()
                        comp_name = parse_component_key_placeholder(placeholder_text)
                        if comp_name is not None:
                            # 校验阶段不做“元件名存在性”校验（参考 GIL 在导出/写回阶段才由用户选择）。
                            continue
                        # 非占位符字符串：继续进入后续类型匹配逻辑

                    # 工程化：GUID列表/整数列表 端口允许列表元素使用 ui_key/ui: 占位符（编译期替换）
                    if n_expected in {"GUID列表", "整数列表"} and isinstance(kw.value, ast.Call):
                        call_func = getattr(kw.value, "func", None)
                        if isinstance(call_func, ast.Name) and call_func.id == "拼装列表":
                            element_exprs: List[ast.expr] = []
                            has_game_keyword = False
                            for one_kw in getattr(kw.value, "keywords", []) or []:
                                if not isinstance(one_kw, ast.keyword):
                                    continue
                                if one_kw.arg == "game":
                                    has_game_keyword = True
                                    continue
                                element_exprs.append(one_kw.value)
                            positional = list(getattr(kw.value, "args", []) or [])
                            if positional and (not has_game_keyword) and _looks_like_game_expr(positional[0]):
                                positional = positional[1:]
                            element_exprs = positional + element_exprs

                            for elem in element_exprs:
                                if not (isinstance(elem, ast.Constant) and isinstance(getattr(elem, "value", None), str)):
                                    continue
                                text = str(getattr(elem, "value", "")).strip()
                                ui_key = parse_ui_key_placeholder(text)
                                if ui_key is None:
                                    entity_name = parse_entity_key_placeholder(text)
                                    if entity_name is not None:
                                        continue
                                    continue
                                if ui_view is not None and (not ui_view.html_files):
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            elem,
                                            "CODE_UI_HTML_SOURCES_NOT_FOUND",
                                            f"{line_span_text(elem)}: 端口期望类型『{expected}』的列表元素允许使用 ui_key/ui: 占位符，"
                                            "但当前项目未找到任何 UI源码(HTML)，无法校验占位符是否真实存在。"
                                        "请先在 管理配置/UI源码 下放置 .html，并确保包含对应 data-ui-key / data-ui-state-group。",
                                        )
                                    )
                                    continue
                                if ui_view is not None and ui_key not in ui_key_set:
                                    invalid_msg2 = try_format_invalid_ui_state_group_placeholder_message(str(text))
                                    if invalid_msg2 is not None:
                                        issues.append(
                                            self._issue(
                                                file_path,
                                                elem,
                                                "CODE_UI_STATE_GROUP_PLACEHOLDER_INVALID_FORMAT",
                                                f"{line_span_text(elem)}: {invalid_msg2} 当前写法为 {text!r}",
                                            )
                                        )
                                        continue
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            elem,
                                            "CODE_UI_KEY_NOT_FOUND_IN_UI_HTML",
                                            f"{line_span_text(elem)}: 端口期望类型『{expected}』的列表元素占位符不存在：{text!r}。"
                                        "请检查 HTML 中是否声明了该 ui_key（data-ui-key / data-ui-state-group），或修正占位符 key。",
                                        )
                                    )
                            # 无论是否存在占位符，拼装列表 的类型匹配仍由后续逻辑负责

                    # 工程化：元件ID列表 端口允许列表元素使用 component_key/component: 占位符（编译期替换）
                    if n_expected in {"元件ID列表"} and isinstance(kw.value, ast.Call):
                        call_func = getattr(kw.value, "func", None)
                        if isinstance(call_func, ast.Name) and call_func.id == "拼装列表":
                            element_exprs: List[ast.expr] = []
                            has_game_keyword = False
                            for one_kw in getattr(kw.value, "keywords", []) or []:
                                if not isinstance(one_kw, ast.keyword):
                                    continue
                                if one_kw.arg == "game":
                                    has_game_keyword = True
                                    continue
                                element_exprs.append(one_kw.value)
                            positional = list(getattr(kw.value, "args", []) or [])
                            if positional and (not has_game_keyword) and _looks_like_game_expr(positional[0]):
                                positional = positional[1:]
                            element_exprs = positional + element_exprs

                            for elem in element_exprs:
                                if not (isinstance(elem, ast.Constant) and isinstance(getattr(elem, "value", None), str)):
                                    continue
                                text = str(getattr(elem, "value", "")).strip()
                                comp_name = parse_component_key_placeholder(text)
                                if comp_name is None:
                                    continue
                            # 无论是否存在占位符，拼装列表 的类型匹配仍由后续逻辑负责

                    # ID/阵营字面量兼容：允许用“数字常量”直接传入（常量本身无法携带中文类型，但语义上是 ID/枚举值）。
                    if n_expected in {"GUID", "配置ID", "元件ID", "阵营"} and _is_digits_constant_expr(kw.value):
                        continue

                    if not can_connect_ports(n_actual, n_expected):
                        issues.append(self._issue(
                            file_path,
                            kw.value,
                            "PORT_TYPE_MISMATCH",
                            f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                            f"期望类型『{expected}』，实际传入类型『{actual}』，请使用匹配的节点或显式转换/注解"
                        ))

            # 2.2) 复合节点实例方法调用：同样按端口类型做匹配校验
            # 说明：Graph Code 允许写作 `self.复合实例.入口方法(...)`，解析器会将其建模为复合节点调用；
            #      校验阶段也必须覆盖该调用形态，避免 “复合节点参数类型错误” 漏报。
            composite_instance_alias_to_class = _collect_self_composite_instances(class_def)
            if composite_instance_alias_to_class:
                for call in ast.walk(method):
                    if not isinstance(call, ast.Call):
                        continue
                    if not _is_composite_instance_method_call(call):
                        continue

                    alias = _extract_composite_instance_alias(call)
                    composite_class_name = composite_instance_alias_to_class.get(alias, "")
                    if not composite_class_name:
                        continue

                    node_def = node_library_all.get(f"复合节点/{composite_class_name}")
                    if node_def is None:
                        continue

                    expect_map = getattr(node_def, "input_types", {}) or {}
                    if not isinstance(expect_map, dict) or not expect_map:
                        continue

                    for kw in getattr(call, "keywords", []) or []:
                        port_name = getattr(kw, "arg", None)
                        if not isinstance(port_name, str):
                            continue
                        expected = expect_map.get(port_name)
                        if not isinstance(expected, str) or not expected:
                            continue
                        if expected == FLOW_PORT_TYPE:
                            continue

                        if _normalize_type(expected) == "三维向量":
                            if isinstance(kw.value, ast.Tuple):
                                if not _is_vector3_tuple_literal(
                                    kw.value,
                                    module_numeric_constant_names=module_numeric_constant_names,
                                ):
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            kw.value,
                                            "CODE_VECTOR3_LITERAL_INVALID",
                                            (
                                                f"{line_span_text(kw.value)}: 复合节点 '{composite_class_name}' 输入端口 '{port_name}' "
                                                "期望类型『三维向量』时，仅允许使用三维向量常量写法 `(x, y, z)`，且 x/y/z 必须为数值字面量。"
                                            ),
                                        )
                                    )
                                    continue
                                continue
                            if isinstance(kw.value, ast.Call) and isinstance(getattr(kw.value, "func", None), ast.Name) and kw.value.func.id == "拼装列表":
                                issues.append(
                                    self._issue(
                                        file_path,
                                        kw.value,
                                        "CODE_VECTOR3_LITERAL_LIST_FORBIDDEN",
                                        (
                                            f"{line_span_text(kw.value)}: 复合节点 '{composite_class_name}' 输入端口 '{port_name}' 期望类型『三维向量』时，"
                                            "禁止使用列表字面量 `[x, y, z]`（会改写为【拼装列表】并引入多余节点/类型漂移）。"
                                            "请改用三维向量常量写法 `(x, y, z)`，或显式调用 `创建三维向量(...)`。"
                                        ),
                                    )
                                )
                                continue

                        if _normalize_type(expected) == TYPE_VECTOR3_LIST:
                            elems2: Optional[List[ast.expr]] = None
                            if isinstance(kw.value, ast.List):
                                elems2 = [e for e in (kw.value.elts or []) if isinstance(e, ast.expr)]
                            else:
                                elems2 = _extract_build_list_elements(kw.value)
                            if elems2 is not None:
                                bad_elem2 = next(
                                    (
                                        e
                                        for e in elems2
                                        if not _is_vector3_expr(
                                            e,
                                            var_types=var_types,
                                            infer_expr_type=self._infer_expr_type,
                                            func_names=func_names,
                                            out_types=out_types,
                                            module_numeric_constant_names=module_numeric_constant_names,
                                        )
                                    ),
                                    None,
                                )
                                if bad_elem2 is not None:
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            bad_elem2,
                                            "PORT_VECTOR3_LIST_ELEMENT_INVALID",
                                            (
                                                f"{line_span_text(bad_elem2)}: 复合节点 '{composite_class_name}' 输入端口 '{port_name}' 期望类型『{expected}』，"
                                                "但列表元素不是有效的三维向量值。"
                                                "允许的元素写法：`(x, y, z)`（括号 tuple 常量）、`创建三维向量(...)`、或类型为『三维向量』的变量。"
                                                "禁止写法示例：`[x, y, z]`（列表形式的向量）。"
                                            ),
                                        )
                                    )
                                    continue

                        # 强类型列表：当端口期望具体列表类型（如“浮点数列表/整数列表/字符串列表/实体列表”等）时，
                        # 若实参可静态提取为列表元素（列表字面量或【拼装列表】调用），则要求元素类型与 base_type 一致。
                        base_type2 = self._typed_list_base_type(_normalize_type(expected))
                        if base_type2:
                            elems3 = self._extract_list_elements(kw.value)
                            if elems3 is not None:
                                bad_elem3 = self._first_mismatched_typed_list_elem(
                                    elems3,
                                    expected_base_type=base_type2,
                                    var_types=var_types,
                                    func_names=func_names,
                                    out_types=out_types,
                                )
                                if bad_elem3 is not None:
                                    issues.append(
                                        self._issue(
                                            file_path,
                                            bad_elem3,
                                            "PORT_TYPED_LIST_ELEMENT_TYPE_MISMATCH",
                                            (
                                                f"{line_span_text(bad_elem3)}: 复合节点 '{composite_class_name}' 输入端口 '{port_name}' "
                                                f"期望类型『{expected}』，其列表元素类型必须为『{base_type2}』；但当前元素类型不匹配。"
                                                "请将元素改为匹配类型的字面量（例如 1.0），或使用【数据类型转换】显式转换后再拼装列表。"
                                            ),
                                        )
                                    )
                                    continue

                        actual = self._infer_expr_type(kw.value, var_types, func_names, out_types)
                        if not actual:
                            continue
                        n_actual = _normalize_type(actual)
                        n_expected = _normalize_type(expected)

                        if n_expected in {"GUID", "配置ID", "元件ID", "阵营"} and _is_digits_constant_expr(kw.value):
                            continue

                        if not can_connect_ports(n_actual, n_expected):
                            issues.append(
                                self._issue(
                                    file_path,
                                    kw.value,
                                    "PORT_TYPE_MISMATCH",
                                    (
                                        f"{line_span_text(kw.value)}: 复合节点 '{composite_class_name}' 输入端口 '{port_name}' "
                                        f"期望类型『{expected}』，实际传入类型『{actual}』，请使用匹配的节点或显式转换/注解"
                                    ),
                                )
                            )

        return issues

    def _check_typed_dict_alias_argument(
        self,
        expr: ast.AST,
        *,
        expected_dict_type: str,
        expected_key_type: str,
        expected_value_type: str,
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
    ) -> str:
        """当端口期望别名字典类型（如：配置ID-整数字典）时，对入参表达式做额外校验。

        返回：
        - 空字符串：表示通过校验；
        - 非空字符串：表示失败原因（用于拼接到 issue message）。
        """
        expected_key_type_normalized = str(expected_key_type or "").strip()
        expected_value_type_normalized = str(expected_value_type or "").strip()
        expected_key_list_type = f"{expected_key_type_normalized}{TYPE_SUFFIX_LIST}"
        expected_value_list_type = f"{expected_value_type_normalized}{TYPE_SUFFIX_LIST}"

        if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
            call_name = expr.func.id

            # 1) 字典字面量语法糖会被改写为：拼装字典(self.game, k0, v0, k1, v1, ...)
            if call_name == "拼装字典":
                positional_args = list(getattr(expr, "args", []) or [])
                if len(positional_args) < 3:
                    return "但传入的【拼装字典】调用缺少键值对（至少需要 1 对键和值）"
                key_value_exprs = positional_args[1:]  # 跳过 game/self.game
                if len(key_value_exprs) % 2 != 0:
                    return "但传入的【拼装字典】调用键值对数量异常（不是偶数个参数）"

                for pair_index in range(0, len(key_value_exprs), 2):
                    key_expr = key_value_exprs[pair_index]
                    value_expr = key_value_exprs[pair_index + 1]

                    inferred_key_type = _normalize_type(
                        self._infer_expr_type(key_expr, var_types, func_names, out_types)
                    )
                    if (not inferred_key_type) or inferred_key_type == GENERIC_PORT_TYPE:
                        return (
                            f"但该字典的第 {pair_index // 2 + 1} 对键值中，键类型无法静态确定；"
                            f"请使用带中文类型注解的变量，并确保键类型为『{expected_key_type_normalized}』"
                        )
                    if inferred_key_type != expected_key_type_normalized:
                        return (
                            f"但该字典的第 {pair_index // 2 + 1} 对键值中，键类型为『{inferred_key_type}』，"
                            f"期望键类型为『{expected_key_type_normalized}』"
                        )

                    inferred_value_type = _normalize_type(
                        self._infer_expr_type(value_expr, var_types, func_names, out_types)
                    )
                    if (not inferred_value_type) or inferred_value_type == GENERIC_PORT_TYPE:
                        return (
                            f"但该字典的第 {pair_index // 2 + 1} 对键值中，值类型无法静态确定；"
                            f"请使用带中文类型注解的变量，并确保值类型为『{expected_value_type_normalized}』"
                        )
                    if inferred_value_type != expected_value_type_normalized:
                        return (
                            f"但该字典的第 {pair_index // 2 + 1} 对键值中，值类型为『{inferred_value_type}』，"
                            f"期望值类型为『{expected_value_type_normalized}』"
                        )

                return ""

            # 2) 建立字典(game, 键列表=..., 值列表=...)
            if call_name == "建立字典":
                key_list_expr: ast.expr | None = None
                value_list_expr: ast.expr | None = None

                for keyword_arg in getattr(expr, "keywords", []) or []:
                    if not isinstance(keyword_arg, ast.keyword):
                        continue
                    if keyword_arg.arg == "键列表":
                        key_list_expr = keyword_arg.value
                    elif keyword_arg.arg == "值列表":
                        value_list_expr = keyword_arg.value

                positional_args = list(getattr(expr, "args", []) or [])
                if key_list_expr is None and len(positional_args) >= 2:
                    key_list_expr = positional_args[1]
                if value_list_expr is None and len(positional_args) >= 3:
                    value_list_expr = positional_args[2]

                if key_list_expr is None or value_list_expr is None:
                    return "但传入的【建立字典】调用缺少『键列表/值列表』入参，无法校验键/值类型"

                inferred_key_list_type = _normalize_type(
                    self._infer_expr_type(key_list_expr, var_types, func_names, out_types)
                )
                if (not inferred_key_list_type) or inferred_key_list_type == GENERIC_PORT_TYPE:
                    return (
                        "但传入的【建立字典】调用中『键列表』类型无法静态确定；"
                        f"请确保其类型为『{expected_key_list_type}』"
                    )
                if inferred_key_list_type != expected_key_list_type:
                    return (
                        "但传入的【建立字典】调用中『键列表』类型为"
                        f"『{inferred_key_list_type}』，期望为『{expected_key_list_type}』"
                    )

                inferred_value_list_type = _normalize_type(
                    self._infer_expr_type(value_list_expr, var_types, func_names, out_types)
                )
                if (not inferred_value_list_type) or inferred_value_list_type == GENERIC_PORT_TYPE:
                    return (
                        "但传入的【建立字典】调用中『值列表』类型无法静态确定；"
                        f"请确保其类型为『{expected_value_list_type}』"
                    )
                if inferred_value_list_type != expected_value_list_type:
                    return (
                        "但传入的【建立字典】调用中『值列表』类型为"
                        f"『{inferred_value_list_type}』，期望为『{expected_value_list_type}』"
                    )

                return ""

        # 3) 变量/其它表达式：必须能静态确定为“同构的别名字典类型”；禁止泛型/泛型字典兜底
        inferred_type = _normalize_type(self._infer_expr_type(expr, var_types, func_names, out_types))
        inferred_type_for_display = inferred_type or "（无法推断）"

        is_actual_typed_dict, actual_key_type, actual_value_type = parse_typed_dict_alias(inferred_type)
        if is_actual_typed_dict:
            # 若已显式注解为别名字典，但 key/value 不匹配，则交给后续 can_connect_ports 产出 PORT_TYPE_MISMATCH
            if (
                str(actual_key_type or "").strip() == expected_key_type_normalized
                and str(actual_value_type or "").strip() == expected_value_type_normalized
            ):
                return ""
            return ""

        # 注意：TYPE_GENERIC_DICT 会被 can_connect_ports 视为“任意字典类型可连”，因此这里必须阻断。
        if inferred_type in {GENERIC_PORT_TYPE, TYPE_GENERIC_DICT, ""}:
            return (
                f"但实际传入类型为『{inferred_type_for_display}』，无法静态确定字典键/值类型；"
                f"该端口仅接受『{expected_dict_type}』。"
                "请将字典先落到变量并显式中文类型注解为对应别名字典，"
                "或直接使用字典字面量/【拼装字典】/【建立字典】构造满足键/值类型的字典。"
            )

        return ""

    def _typed_list_base_type(self, normalized_list_type: str) -> str:
        """返回强类型列表的 base_type；非强类型列表返回空字符串。"""
        if not isinstance(normalized_list_type, str):
            return ""
        t = normalized_list_type.strip()
        if not t:
            return ""
        if t == TYPE_VECTOR3_LIST:
            # 三维向量列表有更强的“元素形态”规则（tuple/创建节点/变量），由专用逻辑处理。
            return ""
        info = LIST_TYPES.get(t)
        if not isinstance(info, dict):
            return ""
        return str(info.get("base_type", "") or "").strip()

    def _extract_list_elements(self, expr: ast.AST) -> Optional[List[ast.expr]]:
        """从表达式中提取列表元素（支持列表字面量与【拼装列表】调用）。"""
        if isinstance(expr, ast.List):
            return [e for e in (expr.elts or []) if isinstance(e, ast.expr)]
        if isinstance(expr, ast.Call):
            return _extract_build_list_elements(expr)
        return None

    def _first_mismatched_typed_list_elem(
        self,
        elems: List[ast.expr],
        *,
        expected_base_type: str,
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
    ) -> Optional[ast.expr]:
        """返回第一个与期望 base_type 不匹配的元素；无法推断/泛型元素不在此处阻断。"""
        expected_norm = _normalize_type(expected_base_type)
        if (not expected_norm) or expected_norm == GENERIC_PORT_TYPE:
            return None
        for e in elems:
            inferred = self._infer_expr_type(e, var_types, func_names, out_types)
            actual_norm = _normalize_type(inferred)
            if (not actual_norm) or actual_norm == GENERIC_PORT_TYPE:
                continue
            if actual_norm != expected_norm:
                return e
        return None

    def _infer_expr_type(
        self,
        expr: ast.AST,
        var_types: Dict[str, str],
        func_names: Set[str],
        out_types: Dict[str, List[str]],
    ) -> str:
        # 常量
        if isinstance(expr, ast.Constant):
            py_type = type(getattr(expr, "value", None))
            return _CONST_TYPE_MAP.get(py_type, "")
        # 变量
        if isinstance(expr, ast.Name):
            return var_types.get(expr.id, "")
        # 调用（仅支持节点函数名调用）
        if isinstance(expr, ast.Call) and isinstance(getattr(expr, "func", None), ast.Name):
            fname = expr.func.id
            if fname in func_names:
                return _unique_data_output_type(out_types.get(fname, []))
        return ""

    def _issue(self, file_path: Path, at: ast.AST, code: str, msg: str) -> EngineIssue:
        return EngineIssue(
            level=self.default_level,
            category=self.category,
            code=code,
            message=msg,
            file=str(file_path),
            line_span=line_span_text(at),
        )
