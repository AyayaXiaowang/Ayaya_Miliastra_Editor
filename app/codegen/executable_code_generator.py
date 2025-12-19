"""可执行/可运行 Python 代码生成器（应用层）。

说明：
- 输入为 `engine.graph.models.GraphModel`（中立产物）
- 输出为可运行的 Graph Code（类结构 Python）
- “运行时导入/插件导入/是否自动校验”由上层通过参数决定
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import inspect
import keyword
import re

from engine.graph.common import (
    VarNameCounter,
    choose_output_var_names,
    collect_input_params as collect_input_params_common,
    finalize_output_var_names,
    group_by_event_with_topo_order as group_by_event,
    is_flow_port,
    render_call_expression,
)
from engine.graph.ir.event_utils import get_event_param_names_from_node
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.signal import SignalCodegenAdapter
from engine.utils.name_utils import make_valid_identifier, sanitize_class_name


@dataclass(frozen=True, slots=True)
class ExecutableCodegenOptions:
    """可执行代码生成选项（上层决定运行时导入与校验策略）。"""

    import_mode: str = "local_prelude"
    """导入模式：
    - local_prelude：生成 `from _prelude import *`，由同目录的 `_prelude.py` 负责注入 sys.path 与 runtime/节点占位类型
    - workspace_bootstrap：在生成文件内注入 sys.path（project_root/assets；不要注入 app），再导入 `runtime.engine.graph_prelude_*`
    """

    enable_auto_validate: bool = True
    """是否为生成的节点图类添加 `@validate_node_graph` 装饰器。

    说明：
    - 仅影响“生成的源码是否携带校验钩子”，不会强制开启校验；
    - 实际是否执行校验由 `settings.RUNTIME_NODE_GRAPH_VALIDATION_ENABLED` 决定。
    """

    prelude_module_server: str = "runtime.engine.graph_prelude_server"
    prelude_module_client: str = "runtime.engine.graph_prelude_client"
    """workspace_bootstrap 模式下使用的 prelude 模块路径。"""

    validator_import_path: str = "engine.validate.node_graph_validator"
    """校验器模块路径（推荐使用引擎侧统一入口）。

    备注：`runtime.engine.node_graph_validator` 仍会 re-export 引擎入口，旧代码可继续使用。
    """


class ExecutableCodeGenerator:
    """可执行/可运行 Python 代码生成器（应用层）。"""

    def __init__(
        self,
        workspace_path: Path,
        node_library: Optional[Dict[str, NodeDef]] = None,
        *,
        options: Optional[ExecutableCodegenOptions] = None,
    ) -> None:
        self.workspace_path = workspace_path
        if node_library is None:
            registry = get_node_registry(workspace_path, include_composite=True)
            self.node_library = registry.get_library()
        else:
            self.node_library = node_library

        self.options = options or ExecutableCodegenOptions()
        self.var_name_counter = VarNameCounter(0)
        self._signal_codegen = SignalCodegenAdapter()
        self._current_graph_type: str = "server"
        self._runtime_exports_by_scope: Dict[str, Dict[str, Callable[..., object]]] = {}
        self._requires_game_cache: Dict[Tuple[str, str], bool] = {}

    def generate_code(self, graph_model: GraphModel, metadata: Optional[Dict[str, Any]] = None) -> str:
        """生成可运行的节点图类结构 Python 源码。"""
        if metadata is None:
            metadata = {}

        lines: List[str] = []
        lines.extend(self._generate_executable_header(graph_model, metadata))

        graph_type = metadata.get("graph_type", "server")
        self._current_graph_type = str(graph_type or "server")
        lines.extend(self._generate_executable_imports(graph_type))

        lines.append("")
        lines.extend(self._generate_graph_class(graph_model))
        return "\n".join(lines)

    def _generate_executable_header(self, graph_model: GraphModel, metadata: Dict[str, Any]) -> List[str]:
        """生成 Graph Code 头部 docstring（资源库/校验器可读的 key: value 格式）。"""
        graph_id = str(metadata.get("graph_id") or getattr(graph_model, "graph_id", "") or "")
        graph_name = str(metadata.get("graph_name") or graph_model.graph_name or "")
        graph_type = str(metadata.get("graph_type") or "server")
        folder_path = str(metadata.get("folder_path") or "")
        description = str(metadata.get("description") or graph_model.description or "")

        lines = ['"""']
        if graph_id:
            lines.append(f"graph_id: {graph_id}")
        if graph_name:
            lines.append(f"graph_name: {graph_name}")
        if graph_type:
            lines.append(f"graph_type: {graph_type}")
        if folder_path:
            lines.append(f"folder_path: {folder_path}")
        if description:
            lines.append(f"description: {description}")
        lines.append('"""')
        return lines

    def _generate_executable_imports(self, graph_type: str = "server") -> List[str]:
        options = self.options
        lines: List[str] = [""]

        if options.import_mode == "local_prelude":
            lines.append("# 最小化导入：使用同目录的 _prelude 透出运行时、节点函数与占位类型")
            lines.append("from _prelude import *")
            if options.enable_auto_validate:
                lines.append(f"from {options.validator_import_path} import validate_node_graph")
            return lines

        if options.import_mode != "workspace_bootstrap":
            raise ValueError(f"未知 import_mode: {options.import_mode}")

        prelude_module = (
            options.prelude_module_client if graph_type == "client" else options.prelude_module_server
        )

        lines.append("# 让该文件可在任意工作目录下直接运行：注入 project_root/assets 到 sys.path（不要注入 app 目录）")
        lines.append("import sys")
        lines.append("from pathlib import Path")
        lines.append("")
        lines.append("PROJECT_ROOT = Path(__file__).resolve()")
        lines.append("for _ in range(12):")
        lines.append("    if (PROJECT_ROOT / 'pyrightconfig.json').exists():")
        lines.append("        break")
        lines.append("    if (PROJECT_ROOT / 'engine').exists() and (PROJECT_ROOT / 'app').exists():")
        lines.append("        break")
        lines.append("    PROJECT_ROOT = PROJECT_ROOT.parent")
        lines.append("ASSETS_ROOT = PROJECT_ROOT / 'assets'")
        lines.append("if str(PROJECT_ROOT) not in sys.path:")
        lines.append("    sys.path.insert(0, str(PROJECT_ROOT))")
        lines.append("if str(ASSETS_ROOT) not in sys.path:")
        lines.append("    sys.path.insert(1, str(ASSETS_ROOT))")
        lines.append("")
        lines.append(f"from {prelude_module} import *  # noqa: F401,F403")
        lines.append(f"from {prelude_module} import GameRuntime")
        if options.enable_auto_validate:
            lines.append(f"from {options.validator_import_path} import validate_node_graph")
        return lines

    def _collect_input_params(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> Dict[str, str]:
        return collect_input_params_common(node, graph_model, var_mapping)

    def _sanitize_class_name(self, name: str) -> str:
        return sanitize_class_name(name)

    def _get_node_def(self, node: NodeModel) -> Optional[NodeDef]:
        """按 NodeModel 尝试在节点库中解析对应 NodeDef。

        兼容带作用域后缀的键（如 `...#server/#client`）。
        """
        base_key = f"{node.category}/{node.title}"
        direct = self.node_library.get(base_key)
        if direct is not None:
            return direct
        for suffix in ("#server", "#client"):
            scoped = self.node_library.get(f"{base_key}{suffix}")
            if scoped is not None:
                return scoped
        return None

    @staticmethod
    def _is_safe_kwarg_name(name: str) -> bool:
        """判断字符串能否作为 Python 关键字参数名（不引入 dict 字面量绕路）。"""
        text = str(name or "").strip()
        return bool(text) and text.isidentifier() and (not keyword.iskeyword(text))

    def _ensure_graph_scope(self) -> str:
        scope = str(getattr(self, "_current_graph_type", "") or "").strip().lower()
        return scope if scope in {"server", "client"} else "server"

    def _get_runtime_exports_for_scope(self) -> Dict[str, Callable[..., object]]:
        """加载并缓存当前作用域下的运行时节点函数导出表。

        说明：
        - 该生成器需要输出“可运行”代码，因此必须知道节点函数是否接受 `game` 作为第一个参数；
        - 统一委托 runtime 层的 V2 实现加载器（无 try/except，失败直接抛出）。
        """
        scope = self._ensure_graph_scope()
        cached = self._runtime_exports_by_scope.get(scope)
        if cached is not None:
            return cached
        from app.runtime.engine.node_impl_loader import load_node_exports_for_scope

        exports = load_node_exports_for_scope(scope)
        self._runtime_exports_by_scope[scope] = exports
        return exports

    def _call_requires_game(self, func_name: str) -> bool:
        """判断节点函数调用是否需要传入 `self.game`。"""
        scope = self._ensure_graph_scope()
        key = (scope, str(func_name or ""))
        if key in self._requires_game_cache:
            return self._requires_game_cache[key]

        exports = self._get_runtime_exports_for_scope()
        target = exports.get(func_name)
        if target is None:
            raise ValueError(
                f"无法生成可执行代码：运行时未找到节点函数 '{func_name}'（scope={scope}）。"
                "请确认节点实现可被 V2 清单发现，且 prelude 已正确导出。"
            )

        sig = inspect.signature(target)
        params = list(sig.parameters.values())
        requires = bool(params) and (params[0].name == "game")
        self._requires_game_cache[key] = requires
        return requires

    def _generate_graph_class(self, graph_model: GraphModel) -> List[str]:
        options = self.options
        lines: List[str] = []

        class_name = self._sanitize_class_name(graph_model.graph_name)
        if options.enable_auto_validate:
            lines.append("@validate_node_graph")
        lines.append(f"class {class_name}:")
        lines.append(f'    """节点图类：{graph_model.graph_name}"""')
        lines.append("")

        lines.append("    def __init__(self, game: GameRuntime, owner_entity):")
        lines.append('        """初始化节点图')
        lines.append("        ")
        lines.append("        Args:")
        lines.append("            game: 游戏运行时")
        lines.append("            owner_entity: 挂载的实体（自身实体）")
        lines.append('        """')
        lines.append("        self.game = game")
        lines.append("        self.owner_entity = owner_entity")
        lines.append("")

        event_flows = self._group_nodes_by_event(graph_model, verbose=False)
        if event_flows:
            for event_node_id, flow_nodes in event_flows.items():
                event_node = graph_model.nodes[event_node_id]
                lines.extend(
                    self._generate_event_handler_method(event_node, flow_nodes, graph_model)
                )
                lines.append("")

        lines.extend(self._generate_register_handlers(event_flows, graph_model))
        return lines

    def _generate_event_handler_method(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
    ) -> List[str]:
        lines: List[str] = []
        event_name = self._signal_codegen.get_event_name_for_node(graph_model, event_node.id) or event_node.title
        handler_suffix = make_valid_identifier(event_name)
        if not handler_suffix:
            handler_suffix = "event"

        if self._signal_codegen.is_signal_listen_node(event_node):
            lines.append(f"    def on_{handler_suffix}(self, **event_kwargs):")
        else:
            param_names = get_event_param_names_from_node(event_node)
            signature_parts = ["self", *param_names]
            lines.append(f"    def on_{handler_suffix}({', '.join(signature_parts)}):")

        lines.append(f'        """事件处理器：{event_name}"""')

        use_event_kwargs = self._signal_codegen.is_signal_listen_node(event_node)
        body_lines = self._generate_event_flow_body(
            event_node,
            flow_nodes,
            graph_model,
            use_event_kwargs=use_event_kwargs,
        )

        if not body_lines or all(not line.strip() for line in body_lines):
            lines.append("        pass")
            return lines

        for line in body_lines:
            if line:
                lines.append("        " + line)
            else:
                lines.append("")
        return lines

    def _get_event_output_params(self, event_node: NodeModel) -> List[str]:
        param_names = get_event_param_names_from_node(event_node)
        normalized: List[str] = []
        data_index = 0
        for output_port in event_node.outputs:
            if is_flow_port(event_node, output_port.name, True):
                normalized.append("")
                continue
            if data_index < len(param_names):
                normalized.append(param_names[data_index])
            else:
                fallback = make_valid_identifier(output_port.name)
                normalized.append(fallback or f"event_param_{data_index}")
            data_index += 1
        return normalized

    def _generate_event_flow_body(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
        *,
        use_event_kwargs: bool = False,
    ) -> List[str]:
        lines: List[str] = []
        var_mapping: Dict[Tuple[str, str], str] = {}
        var_types: Dict[str, str] = {}

        graph_variable_types: Dict[str, str] = {}
        for entry in getattr(graph_model, "graph_variables", []) or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or "").strip()
            var_type = str(entry.get("variable_type") or "").strip()
            if name and var_type:
                graph_variable_types[name] = var_type

        event_params = self._get_event_output_params(event_node)
        event_mapping = self._signal_codegen.build_listen_signal_output_mapping(
            event_node,
            use_event_kwargs=use_event_kwargs,
            event_param_names=event_params,
        )
        var_mapping.update(event_mapping)

        processed_nodes: set[str] = {event_node.id}
        for node_id in flow_nodes:
            if node_id == event_node.id or node_id in processed_nodes:
                continue
            node = graph_model.nodes[node_id]
            lines.extend(
                self._generate_node_call(
                    node,
                    graph_model,
                    var_mapping,
                    var_types=var_types,
                    graph_variable_types=graph_variable_types,
                )
            )
            processed_nodes.add(node_id)
        return lines

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

            data_port_names_in_order = [
                p.name for p in node.inputs if not is_flow_port(node, p.name, False)
            ]

            # 动态端口节点：静态端口使用位置参数（不依赖端口名可作为标识符），动态端口必须用关键字参数
            if dynamic_port_type_value and node_def is not None:
                static_port_order = [
                    name
                    for name in (getattr(node_def, "inputs", []) or [])
                    if name not in ("流程入", "流程出") and ("~" not in name)
                ]
                static_set = set(static_port_order)
                dynamic_ports_in_order = [
                    name for name in data_port_names_in_order if name not in static_set
                ]

                for port_name in static_port_order:
                    param_segments.append(input_params.get(port_name, '""'))

                for port_name in dynamic_ports_in_order:
                    if not self._is_safe_kwarg_name(port_name):
                        raise ValueError(
                            f"无法为节点【{node.title}】生成可执行代码：动态端口名 '{port_name}' 不是合法的关键字参数名。"
                            "节点图规则禁止使用 {} 字面量，无法通过 **{...} 传参，请重命名该端口为合法标识符。"
                        )
                    param_segments.append(f"{port_name}={input_params.get(port_name, '\"\"')}")
            else:
                # 非动态节点：若端口名可作为关键字参数，则保留 keyword= 形式；否则回退为全位置参数，避免生成语法错误。
                all_safe_as_kw = all(self._is_safe_kwarg_name(n) for n in data_port_names_in_order)
                if all_safe_as_kw:
                    for port_name in data_port_names_in_order:
                        param_segments.append(f"{port_name}={input_params.get(port_name, '\"\"')}")
                else:
                    for port_name in data_port_names_in_order:
                        param_segments.append(input_params.get(port_name, '""'))

        if include_game:
            call_expr = render_call_expression(func_name, "self.game", param_segments)
        else:
            args_str = ", ".join(param_segments)
            call_expr = f"{func_name}({args_str})" if args_str else f"{func_name}()"

        lines: List[str] = []
        if node.outputs:
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
                    if port_type:
                        lines.append(f'{var_name}: "{port_type}" = {call_expr}')
                        var_types[var_name] = port_type
                    else:
                        lines.append(f"{var_name} = {call_expr}")
                else:
                    # 多输出赋值不支持逐个注解；保持原样，必要时由上层/用户补齐注解
                    lines.append(f"{', '.join(output_vars)} = {call_expr}")
            else:
                lines.append(call_expr)
        else:
            lines.append(call_expr)
        return lines

    @staticmethod
    def _strip_string_literal(expr: str) -> str:
        text = str(expr or "").strip()
        if (len(text) >= 2) and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
            return text[1:-1]
        return text

    @staticmethod
    def _infer_expr_type(expr: str, *, var_types: Dict[str, str]) -> str:
        text = str(expr or "").strip()
        if not text:
            return ""
        if (len(text) >= 2) and ((text[0] == text[-1] == '"') or (text[0] == text[-1] == "'")):
            return "字符串"
        if text in ("True", "False"):
            return "布尔值"
        # 数字（不使用 try/except，避免吞错）：仅识别常见的十进制字面量
        if re.fullmatch(r"-?\d+\.\d+", text):
            return "浮点数"
        if re.fullmatch(r"-?\d+", text):
            return "整数"
        # 变量
        if text.isidentifier():
            return var_types.get(text, "")
        return ""

    def _infer_output_type(
        self,
        *,
        node_title: str,
        declared_type: str,
        input_params: Dict[str, str],
        var_types: Dict[str, str],
        graph_variable_types: Dict[str, str],
    ) -> str:
        declared = str(declared_type or "").strip()

        # 1) 获取自定义变量：用图变量声明推断类型
        if node_title == "获取自定义变量":
            var_name_expr = input_params.get("变量名", "")
            var_name = self._strip_string_literal(var_name_expr)
            inferred = graph_variable_types.get(var_name, "")
            return inferred or declared

        # 2) 拼装列表：根据元素类型推断列表具体类型（字符串列表/整数列表/浮点数列表/布尔值列表）
        if node_title == "拼装列表":
            element_types: List[str] = []
            for key, value in input_params.items():
                if key.isdigit():
                    element_types.append(self._infer_expr_type(value, var_types=var_types))
            normalized = [t for t in element_types if t]
            if not normalized:
                return declared
            unique = set(normalized)
            # int + float -> float
            if unique.issubset({"整数", "浮点数"}):
                return "浮点数列表" if "浮点数" in unique else "整数列表"
            if len(unique) == 1:
                only = next(iter(unique))
                if only == "字符串":
                    return "字符串列表"
                if only == "整数":
                    return "整数列表"
                if only == "浮点数":
                    return "浮点数列表"
                if only == "布尔值":
                    return "布尔值列表"
            return declared

        # 3) 加法/减法/乘法/除法：根据左右输入推断数值类型
        if node_title in {"加法运算", "减法运算", "乘法运算", "除法运算"}:
            left_expr = input_params.get("左值", "")
            right_expr = input_params.get("右值", "")
            left_type = self._infer_expr_type(left_expr, var_types=var_types)
            right_type = self._infer_expr_type(right_expr, var_types=var_types)
            if left_type or right_type:
                if "浮点数" in (left_type, right_type):
                    return "浮点数"
                if (left_type == "整数") and (right_type == "整数"):
                    return "整数"
            return declared

        return declared

    def _group_nodes_by_event(self, graph_model: GraphModel, verbose: bool = False) -> Dict[str, List[str]]:
        flows = group_by_event(graph_model, include_data_dependencies=True)
        if verbose:
            print(f"  找到 {len(flows)} 个事件流")
        return flows

    def _generate_register_handlers(
        self,
        event_flows: Dict[str, List[str]],
        graph_model: GraphModel,
    ) -> List[str]:
        lines: List[str] = []
        lines.append("    def register_handlers(self):")
        lines.append('        """注册所有事件处理器"""')

        if not event_flows:
            lines.append("        pass")
            return lines

        for event_node_id in event_flows:
            event_node = graph_model.nodes[event_node_id]
            event_name = self._signal_codegen.get_event_name_for_node(graph_model, event_node_id)
            handler_suffix = make_valid_identifier(event_name)
            if not handler_suffix:
                handler_suffix = "event"
            lines.append("        self.game.register_event_handler(")
            lines.append(f'            "{event_name}",')
            lines.append(f"            self.on_{handler_suffix},")
            lines.append("            owner=self.owner_entity")
            lines.append("        )")

        return lines


