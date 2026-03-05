from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.graph.common import (
    choose_output_var_names,
    finalize_output_var_names,
    format_constant,
    is_flow_port,
    render_call_expression,
)
from engine.graph.models import GraphModel, NodeModel
from engine.graph.port_type_effective_resolver import (
    build_port_type_overrides,
    resolve_override_type_for_node_port,
)
from engine.utils.name_utils import make_valid_identifier


class _ExecutableCodegenEmitNodeCallMixin:
    def _generate_node_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
        *,
        var_types: Dict[str, str],
        graph_variable_types: Dict[str, str],
    ) -> List[str]:
        input_params = self._collect_input_params(node, graph_model, var_mapping)

        if self._signal_codegen.is_signal_send_node(node):
            return self._signal_codegen.generate_send_signal_call(node, graph_model, input_params)

        # 节点调用名：统一使用 make_valid_identifier(节点显示名) 派生（运行时会导出同名别名）。
        display_name = str(getattr(node, "title", "") or "")
        func_name = make_valid_identifier(display_name)
        if not func_name:
            raise ValueError(f"无法为节点【{display_name}】生成可执行代码：无法派生合法的函数名")

        include_game = self._call_requires_game(func_name)

        # —— 类型化常量变量：将关键类型（GUID/配置ID/元件ID/阵营）的字面量提升为带中文类型注解的变量 ——
        pre_lines: List[str] = []
        node_def_for_inputs = self._get_node_def(node)
        if node_def_for_inputs is not None:
            special_types_direct: set[str] = {"GUID", "配置ID", "元件ID", "阵营"}
            input_constants = getattr(node, "input_constants", {}) or {}
            for port in (node.inputs or []):
                port_name = str(getattr(port, "name", "") or "")
                if self._is_flow_port_name(port_name):
                    continue
                if port_name not in input_constants:
                    continue
                raw_value = input_constants.get(port_name)
                expected_type = str(node_def_for_inputs.get_port_type(port_name, is_input=True) or "").strip()

                desired_type: Optional[str] = None
                if expected_type in special_types_direct:
                    desired_type = expected_type
                else:
                    # 泛型端口：若该 int 常量在本事件中被明确作为 GUID/配置ID/元件ID 使用过，则复用其类型化变量
                    parsed_int = self._try_parse_int_literal(raw_value)
                    if isinstance(parsed_int, int):
                        inferred = self._typed_const_type_by_int_value.get(int(parsed_int))
                        if isinstance(inferred, str) and inferred:
                            desired_type = inferred

                if desired_type is None:
                    continue

                const_var, decl = self._ensure_typed_const_var(
                    type_name=desired_type,
                    raw_value=raw_value,
                    var_types=var_types,
                )
                if decl is not None:
                    pre_lines.append(decl)
                input_params[port_name] = const_var

        has_variadic_params = (
            any("~" in param_name for param_name in input_params.keys())
            or any(param_name.isdigit() for param_name in input_params.keys())
        )

        param_segments: List[str] = []
        if has_variadic_params:
            variadic_params: Dict[int, str] = {}
            normal_params: Dict[str, str] = {}
            for param_name, param_value in input_params.items():
                if param_name.isdigit():
                    variadic_params[int(param_name)] = param_value
                elif "~" in param_name:
                    continue
                else:
                    normal_params[param_name] = param_value

            for index in sorted(variadic_params.keys()):
                param_segments.append(variadic_params[index])
            for param_name, param_value in normal_params.items():
                if "~" in param_name:
                    continue
                if not self._is_safe_kwarg_name(param_name):
                    raise ValueError(
                        f"无法为节点【{node.title}】生成可执行代码：变参节点存在不合法的关键字端口名 '{param_name}'。"
                        "该生成器不允许用 dict 字面量绕过（节点图规则禁止 {} 字面量），请修改端口命名为合法标识符。"
                    )
                param_segments.append(f"{param_name}={param_value}")
        else:
            node_def = self._get_node_def(node)
            dynamic_port_type_value = str(getattr(node_def, "dynamic_port_type", "") or "") if node_def else ""
            input_defaults = dict(getattr(node_def, "input_defaults", {}) or {}) if node_def is not None else {}

            data_port_names_in_order = [p.name for p in node.inputs if not is_flow_port(node, p.name, False)]
            empty_string_literal = '""'

            connected_data_ports: set[str] = set()
            for edge in graph_model.edges.values():
                if edge.dst_node != node.id:
                    continue
                if is_flow_port(node, edge.dst_port, False):
                    continue
                connected_data_ports.add(edge.dst_port)

            def _format_constant_for_compare(value: object) -> Optional[str]:
                # 不使用 try/except：仅对常见标量类型做格式化比较，其余类型不省略（保守）。
                if value is None or isinstance(value, (bool, int, float, str)):
                    return format_constant(value)
                return None

            def _should_omit_default_port(port_name: str) -> bool:
                """当输入端口未连线、且常量值等于节点定义默认值时，允许在生成代码时省略该参数。"""
                if not input_defaults or port_name not in input_defaults:
                    return False
                if port_name in connected_data_ports:
                    return False
                if port_name not in (getattr(node, "input_constants", {}) or {}):
                    return False
                current_value = (getattr(node, "input_constants", {}) or {}).get(port_name)
                default_value = input_defaults.get(port_name)
                a = _format_constant_for_compare(current_value)
                b = _format_constant_for_compare(default_value)
                if a is None or b is None:
                    return False
                return a == b

            # 动态端口节点：静态端口使用位置参数，动态端口用关键字参数（特例：键/值成对变参节点）
            if dynamic_port_type_value and node_def is not None:
                key_value_meta = self._detect_key_value_variadic_pattern(node_def)
                if key_value_meta is not None:
                    key_prefix, value_prefix, start_index = key_value_meta
                    max_seen = int(start_index) - 1
                    for name in data_port_names_in_order:
                        text = str(name or "")
                        if text.startswith(key_prefix):
                            suffix = text[len(key_prefix) :]
                            if suffix.isdigit():
                                max_seen = max(max_seen, int(suffix))
                            continue
                        if text.startswith(value_prefix):
                            suffix = text[len(value_prefix) :]
                            if suffix.isdigit():
                                max_seen = max(max_seen, int(suffix))
                            continue

                    upper = max(max_seen, int(start_index))
                    for i in range(int(start_index), int(upper) + 1):
                        param_segments.append(input_params.get(f"{key_prefix}{i}", "0"))
                        param_segments.append(input_params.get(f"{value_prefix}{i}", "0"))

                    # 防御：保证至少一个键值对（满足 variadic_min_args 规则）
                    while len(param_segments) < 2:
                        param_segments.append("0")
                else:
                    static_port_order = [
                        name
                        for name in (getattr(node_def, "inputs", []) or [])
                        if name not in ("流程入", "流程出") and ("~" not in name)
                    ]
                    static_set = set(static_port_order)
                    dynamic_ports_in_order = [name for name in data_port_names_in_order if name not in static_set]

                    # 静态端口（位置参数）仅支持省略“尾部默认值”端口，避免位置参数错位
                    last_static_index = len(static_port_order) - 1
                    while last_static_index >= 0 and _should_omit_default_port(static_port_order[last_static_index]):
                        last_static_index -= 1
                    for i in range(last_static_index + 1):
                        port_name = static_port_order[i]
                        param_segments.append(input_params.get(port_name, empty_string_literal))

                    for port_name in dynamic_ports_in_order:
                        if _should_omit_default_port(port_name):
                            continue
                        if not self._is_safe_kwarg_name(port_name):
                            raise ValueError(
                                f"无法为节点【{node.title}】生成可执行代码：动态端口名 '{port_name}' 不是合法的关键字参数名。"
                                "节点图规则禁止使用 {} 字面量，无法通过 **{...} 传参，请重命名该端口为合法标识符。"
                            )
                        param_value = input_params.get(port_name, empty_string_literal)
                        param_segments.append(f"{port_name}={param_value}")
            else:
                # 非动态节点：若端口名可作为关键字参数，则保留 keyword= 形式；否则回退为全位置参数，避免生成语法错误。
                all_safe_as_kw = all(self._is_safe_kwarg_name(n) for n in data_port_names_in_order)
                if all_safe_as_kw:
                    for port_name in data_port_names_in_order:
                        if _should_omit_default_port(port_name):
                            continue
                        param_value = input_params.get(port_name, empty_string_literal)
                        param_segments.append(f"{port_name}={param_value}")
                else:
                    # 位置参数仅支持省略“尾部默认值”端口，避免位置参数错位
                    last_index = len(data_port_names_in_order) - 1
                    while last_index >= 0 and _should_omit_default_port(data_port_names_in_order[last_index]):
                        last_index -= 1
                    for i in range(last_index + 1):
                        port_name = data_port_names_in_order[i]
                        param_segments.append(input_params.get(port_name, empty_string_literal))

        if include_game:
            call_expr = render_call_expression(func_name, "self.game", param_segments)
        else:
            args_str = ", ".join(param_segments)
            call_expr = f"{func_name}({args_str})" if args_str else f"{func_name}()"

        lines: List[str] = []
        if pre_lines:
            lines.extend(pre_lines)

        if node.outputs:
            overrides_mapping = build_port_type_overrides(graph_model)
            data_outputs = [p for p in node.outputs if not is_flow_port(node, p.name, True)]
            output_vars: List[str] = []
            output_port_types: List[str] = []
            if data_outputs:
                raw_names = choose_output_var_names(
                    node,
                    data_outputs,
                    prefer_custom_names=False,
                    fallback="generated",
                    counter=self.var_name_counter,
                )
                output_vars = finalize_output_var_names(raw_names, counter=self.var_name_counter)
                node_def = self._get_node_def(node)
                for port, var_name in zip(data_outputs, output_vars):
                    var_mapping[(node.id, port.name)] = var_name
                    declared_type = ""
                    if node_def is not None:
                        declared_type = str(node_def.get_port_type(port.name, is_input=False))
                    override_type = resolve_override_type_for_node_port(
                        overrides_mapping,
                        node.id,
                        str(port.name),
                    )
                    if override_type:
                        declared_type = override_type
                    inferred_type = self._infer_output_type(
                        node_title=node.title,
                        declared_type=declared_type,
                        input_params=input_params,
                        var_types=var_types,
                        graph_variable_types=graph_variable_types,
                    )
                    output_port_types.append(inferred_type or declared_type)

            if output_vars:
                if len(output_vars) == 1:
                    var_name = output_vars[0]
                    port_type = (output_port_types[0] if output_port_types else "").strip()
                    if port_type and self._should_emit_type_annotation(port_type):
                        lines.append(f'{var_name}: "{port_type}" = {call_expr}')
                        var_types[var_name] = port_type
                    else:
                        lines.append(f"{var_name} = {call_expr}")
                        if port_type:
                            var_types[var_name] = port_type
                else:
                    # 多输出赋值：使用“先声明类型、再多赋值”的写法绑定端口类型，
                    # 避免泛型输出（例如 获取局部变量/拆分结构体 等）在 validate 阶段报错。
                    for var_name, port_type in zip(output_vars, output_port_types):
                        type_text = str(port_type or "").strip()
                        if type_text and self._should_emit_type_annotation(type_text):
                            lines.append(f'{var_name}: "{type_text}"')
                            var_types[var_name] = type_text
                        elif type_text:
                            var_types[var_name] = type_text
                    lines.append(f"{', '.join(output_vars)} = {call_expr}")
            else:
                lines.append(call_expr)
        else:
            lines.append(call_expr)
        return lines


__all__ = ["_ExecutableCodegenEmitNodeCallMixin"]

