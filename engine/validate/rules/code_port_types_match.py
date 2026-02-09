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
from engine.nodes.port_type_system import can_connect_ports, FLOW_PORT_TYPE, ANY_PORT_TYPE, GENERIC_PORT_TYPE
from engine.type_registry import TYPE_GENERIC_DICT, TYPE_SUFFIX_LIST, can_convert_type, parse_typed_dict_alias
from engine.utils.graph.graph_utils import is_flow_port_name


_CONST_TYPE_MAP: Dict[type, str] = {
    int: "整数",
    float: "浮点数",
    str: "字符串",
    bool: "布尔值",
}


_TYPE_CONVERSION_NODE_FUNC_NAME = "数据类型转换"


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
        if ctx.is_composite or ctx.file_path is None:
            return []

        file_path: Path = ctx.file_path
        tree = get_cached_module(ctx)
        ui_view = try_load_ui_html_ui_keys_for_ctx(ctx)
        ui_key_set = set(ui_view.ui_keys) if ui_view is not None else set()
        scope = infer_graph_scope(ctx)
        func_names = node_function_names(ctx.workspace_path, scope)
        in_types = input_types_by_func(ctx.workspace_path, scope)
        out_types = output_types_by_func(ctx.workspace_path, scope)
        in_constraints = input_generic_constraints_by_func(ctx.workspace_path, scope)
        enum_options = input_enum_options_by_func(ctx.workspace_path, scope)

        issues: List[EngineIssue] = []

        for _, method in _iter_methods(tree):
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

                    if not can_connect_ports(n_actual, n_expected):
                        issues.append(self._issue(
                            file_path,
                            kw.value,
                            "PORT_TYPE_MISMATCH",
                            f"{line_span_text(kw.value)}: 函数 '{func_name}' 输入端口 '{port_name}' "
                            f"期望类型『{expected}』，实际传入类型『{actual}』，请使用匹配的节点或显式转换/注解"
                        ))

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
        if ctx.is_composite or ctx.file_path is None:
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


def _iter_methods(tree: ast.Module):
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    yield node, item


def _iter_calls_to_nodes(method: ast.FunctionDef, func_names: Set[str]):
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(getattr(node, "func", None), ast.Name):
            if node.func.id in func_names:
                yield node


def _collect_annotated_vars(method: ast.FunctionDef) -> Set[str]:
    annotated: Set[str] = set()
    for node in ast.walk(method):
        if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "target", None), ast.Name):
            if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                annotated.add(node.target.id)
    return annotated


def _collect_var_types(
    method: ast.FunctionDef,
    func_names: Set[str],
    out_types: Dict[str, List[str]],
) -> Dict[str, str]:
    var_types: Dict[str, str] = {}
    # 注解优先：收集注解类型
    for node in ast.walk(method):
        if isinstance(node, ast.AnnAssign) and isinstance(getattr(node, "target", None), ast.Name):
            if isinstance(getattr(node, "annotation", None), ast.Constant) and isinstance(getattr(node.annotation, "value", None), str):
                var_types[node.target.id] = str(node.annotation.value)
    # 赋值推断：单输出数据类型
    for node in ast.walk(method):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            target_name = _single_target_name(node.targets)
            if not target_name:
                continue
            f = node.value.func
            if isinstance(f, ast.Name) and (f.id in func_names):
                t = _unique_data_output_type(out_types.get(f.id, []))
                if t and t not in (FLOW_PORT_TYPE, ""):
                    var_types.setdefault(target_name, t)
    return var_types


def _single_target_name(targets: List[ast.expr]) -> Optional[str]:
    # 仅支持形如 x = ... 的简单赋值
    if len(targets) != 1:
        return None
    tgt = targets[0]
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None


def _unique_data_output_type(types: List[str]) -> str:
    if not isinstance(types, list):
        return ""
    data_types = [t for t in types if isinstance(t, str) and t and (t != FLOW_PORT_TYPE)]
    if len(data_types) == 1:
        return data_types[0]
    return ""


def _normalize_type(t: str) -> str:
    if not isinstance(t, str):
        return ""
    text = t.strip()
    if not text:
        return ""
    # 仅对“纯泛型”同义词做归一化，保留诸如“泛型字典”“泛型列表”等具象泛型类型
    if text in (GENERIC_PORT_TYPE, ANY_PORT_TYPE, "泛型"):
        return GENERIC_PORT_TYPE

    # 别名字典：统一将 “键_值字典” 规范化为 “键-值字典”，避免同义写法导致类型匹配误报
    is_typed_dict, key_type_name, value_type_name = parse_typed_dict_alias(text)
    if is_typed_dict:
        key_type_normalized = str(key_type_name or "").strip()
        value_type_normalized = str(value_type_name or "").strip()
        return f"{key_type_normalized}-{value_type_normalized}字典"
    return text


def _is_type_allowed_by_constraints(actual: str, allowed: List[str]) -> bool:
    if not isinstance(actual, str):
        return False
    if not isinstance(allowed, list):
        return True
    if actual == GENERIC_PORT_TYPE:
        # 未推断出具体类型时，不在此处阻断，交给后续规则
        return True
    return actual in allowed


def _extract_type_conversion_input_expr(call_expr: ast.Call) -> Optional[ast.expr]:
    """提取【数据类型转换】调用的“输入”表达式。

    支持形式：
    - 数据类型转换(game, 输入=...)
    - 数据类型转换(game, ...)

    说明：Graph Code 通常以关键字参数传端口名；这里额外对最常见的位置参数形式做弱支持。
    """
    # 1) 优先使用关键字参数：输入=...
    for keyword_arg in getattr(call_expr, "keywords", []) or []:
        if not isinstance(keyword_arg, ast.keyword):
            continue
        if keyword_arg.arg == "输入":
            return keyword_arg.value

    # 2) 兼容：数据类型转换(game, 输入值)
    positional_args = list(getattr(call_expr, "args", []) or [])
    if len(positional_args) >= 2:
        return positional_args[1]

    return None


def _looks_like_game_expr(expr: ast.expr) -> bool:
    """启发式判断一个表达式是否为 Graph Code 约定的 game 实参。"""
    if isinstance(expr, ast.Name) and expr.id == "game":
        return True
    if isinstance(expr, ast.Attribute):
        if isinstance(expr.value, ast.Name) and expr.value.id == "self" and expr.attr == "game":
            return True
    return False


