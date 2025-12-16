"""复合节点代码生成器（应用层）。

说明：
- 输入为 `engine.nodes.advanced_node_features.CompositeNodeConfig`（中立产物）
- 输出为复合节点 Python 源码（函数格式）
- 生成代码使用 `runtime.engine.graph_prelude_*` 作为最小运行时/节点导入预设（不再硬编码 `app.runtime`）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from engine.graph.common import (
    PIN_TYPE_TO_PYTHON_TYPE,
    VarNameCounter,
    choose_output_var_names,
    collect_input_params,
    finalize_output_var_names,
    is_flow_port,
    render_call_expression,
)
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_algorithms import topological_sort_graph_model
from engine.utils.name_utils import make_valid_identifier


class CompositeCodeGenerator:
    """复合节点代码生成器 - 生成函数格式的复合节点代码（应用层）。"""

    def __init__(self, node_library: Optional[Dict[str, NodeDef]] = None):
        self.node_library = node_library or {}
        self._var_name_counter: VarNameCounter = VarNameCounter()

    def generate_code(self, composite: CompositeNodeConfig) -> str:
        self._var_name_counter = VarNameCounter()
        lines: List[str] = []

        lines.extend(self._generate_header(composite))
        lines.append("")
        lines.extend(self._generate_imports(composite))
        lines.append("")
        lines.extend(self._generate_function(composite))
        return "\n".join(lines)

    def _generate_header(self, composite: CompositeNodeConfig) -> List[str]:
        lines = ['"""']
        lines.append(f"composite_id: {composite.composite_id}")
        lines.append(f"node_name: {composite.node_name}")
        lines.append(f"node_description: {composite.node_description}")
        lines.append(f"scope: {composite.scope}")
        lines.append(f"folder_path: {composite.folder_path}")
        lines.append('"""')
        return lines

    def _generate_imports(self, composite: CompositeNodeConfig) -> List[str]:
        scope = (composite.scope or "server").lower()
        prelude_module = "runtime.engine.graph_prelude_client" if scope == "client" else "runtime.engine.graph_prelude_server"

        lines: List[str] = []
        lines.append("from __future__ import annotations")
        lines.append("")
        lines.append("import sys")
        lines.append("from pathlib import Path")
        lines.append("")
        lines.append("# 注入 project_root/app/assets 到 sys.path，保证 runtime、plugins 与资源库可导入")
        lines.append("PROJECT_ROOT = Path(__file__).resolve()")
        lines.append("for _ in range(12):")
        lines.append("    if (PROJECT_ROOT / 'pyrightconfig.json').exists():")
        lines.append("        break")
        lines.append("    if (PROJECT_ROOT / 'engine').exists() and (PROJECT_ROOT / 'app').exists():")
        lines.append("        break")
        lines.append("    PROJECT_ROOT = PROJECT_ROOT.parent")
        lines.append("APP_DIR = PROJECT_ROOT / 'app'")
        lines.append("ASSETS_ROOT = PROJECT_ROOT / 'assets'")
        lines.append("if str(APP_DIR) not in sys.path:")
        lines.append("    sys.path.insert(0, str(APP_DIR))")
        lines.append("if str(PROJECT_ROOT) not in sys.path:")
        lines.append("    sys.path.insert(1, str(PROJECT_ROOT))")
        lines.append("if str(ASSETS_ROOT) not in sys.path:")
        lines.append("    sys.path.insert(2, str(ASSETS_ROOT))")
        lines.append("")
        lines.append(f"from {prelude_module} import *  # noqa: F401,F403")
        return lines

    def _generate_function(self, composite: CompositeNodeConfig) -> List[str]:
        lines: List[str] = []
        lines.append(self._generate_function_signature(composite))
        docstring = self._generate_function_docstring(composite)
        if docstring:
            lines.extend(docstring)
        lines.extend(self._generate_function_body(composite))
        return lines

    def _generate_function_signature(self, composite: CompositeNodeConfig) -> str:
        func_name = composite.node_name
        input_pins = [pin for pin in composite.virtual_pins if pin.is_input and not pin.is_flow]

        params: List[str] = ["game: GameRuntime"]
        for pin in sorted(input_pins, key=lambda pin_cfg: pin_cfg.pin_index):
            pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, "Any")
            params.append(f"{pin.pin_name}: {pin_type}")
        params_str = ", ".join(params)

        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        if not output_pins:
            return_type = "None"
        elif len(output_pins) == 1:
            return_type = PIN_TYPE_TO_PYTHON_TYPE.get(output_pins[0].pin_type, "Any")
        else:
            types = [
                PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, "Any")
                for pin in sorted(output_pins, key=lambda pin_cfg: pin_cfg.pin_index)
            ]
            return_type = f"Tuple[{', '.join(types)}]"

        return f"def {func_name}({params_str}) -> {return_type}:"

    def _generate_function_docstring(self, composite: CompositeNodeConfig) -> List[str]:
        lines: List[str] = []
        lines.append('    """' + composite.node_description if composite.node_description else '    """复合节点')

        input_pins = [pin for pin in composite.virtual_pins if pin.is_input and not pin.is_flow]
        if input_pins:
            lines.append("    ")
            lines.append("    输入引脚:")
            for pin in sorted(input_pins, key=lambda pin_cfg: pin_cfg.pin_index):
                pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, "Any")
                desc = f": {pin.description}" if pin.description else ""
                lines.append(f"        {pin.pin_name} ({pin_type}){desc}")

        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        if output_pins:
            lines.append("    ")
            lines.append("    输出引脚:")
            for pin in sorted(output_pins, key=lambda pin_cfg: pin_cfg.pin_index):
                pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, "Any")
                desc = f": {pin.description}" if pin.description else ""
                lines.append(f"        {pin.pin_name} ({pin_type}){desc}")

        lines.append('    """')
        return lines

    def _generate_function_body(self, composite: CompositeNodeConfig) -> List[str]:
        lines: List[str] = []
        graph_model = GraphModel.deserialize(composite.sub_graph)

        if not graph_model.nodes:
            output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
            if output_pins:
                if len(output_pins) == 1:
                    lines.append(f"    return None  # TODO: 实现 {output_pins[0].pin_name}")
                else:
                    return_vals = ", ".join(
                        [f"None  # {pin.pin_name}" for pin in sorted(output_pins, key=lambda pin_cfg: pin_cfg.pin_index)]
                    )
                    lines.append(f"    return ({return_vals})")
            else:
                lines.append("    pass  # TODO: 实现函数体")
            return lines

        sorted_nodes = topological_sort_graph_model(graph_model)
        var_mapping: Dict[Tuple[str, str], str] = {}
        used_var_names: Set[str] = set()

        for pin in composite.virtual_pins:
            if pin.is_input and not pin.is_flow:
                for mapped_port in pin.mapped_ports:
                    var_mapping[(mapped_port.node_id, mapped_port.port_name)] = pin.pin_name

        for node in sorted_nodes:
            lines.extend(self._generate_node_call(node, graph_model, var_mapping, used_var_names))

        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        if output_pins:
            lines.append("")
            lines.append(self._generate_return_statement(output_pins, var_mapping))
        return lines

    def _generate_node_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: Set[str],
    ) -> List[str]:
        lines: List[str] = []
        params = self._collect_node_inputs(node, graph_model, var_mapping)
        param_segments = [f"{key}={value}" for key, value in params.items()]

        func_name = self._resolve_callable_name(node)
        call_expr = render_call_expression(func_name, "game", param_segments)

        data_outputs = [port for port in node.outputs if not is_flow_port(node, port.name, True)]
        output_vars: List[str] = []
        if data_outputs:
            raw_names = choose_output_var_names(
                node,
                data_outputs,
                prefer_custom_names=True,
                fallback="port_name",
            )
            safe_names = finalize_output_var_names(
                raw_names,
                used_names=used_var_names,
                counter=self._var_name_counter,
            )
            for port, safe in zip(data_outputs, safe_names):
                var_mapping[(node.id, port.name)] = safe
            output_vars = safe_names

        if output_vars:
            if len(output_vars) == 1:
                lines.append(f"    {output_vars[0]} = {call_expr}")
            else:
                lines.append(f"    {', '.join(output_vars)} = {call_expr}")
        else:
            lines.append(f"    {call_expr}")
        return lines

    def _collect_node_inputs(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> Dict[str, str]:
        return collect_input_params(node, graph_model, var_mapping)

    def _resolve_callable_name(self, node: NodeModel) -> str:
        key = f"{node.category}/{node.title}"
        node_def = self.node_library.get(key)
        reference_name = node_def.name if node_def else node.title
        return make_valid_identifier(reference_name)

    def _generate_return_statement(
        self,
        output_pins: List[VirtualPinConfig],
        var_mapping: Dict[Tuple[str, str], str],
    ) -> str:
        return_vars: List[str] = []

        for pin in sorted(output_pins, key=lambda pin_cfg: pin_cfg.pin_index):
            var_name: Optional[str] = None
            for mapped_port in pin.mapped_ports:
                mapped_var = var_mapping.get((mapped_port.node_id, mapped_port.port_name))
                if mapped_var:
                    var_name = mapped_var
                    break
            if var_name is None:
                return_vars.append(f"None  # TODO: {pin.pin_name}")
            else:
                return_vars.append(var_name)

        if len(return_vars) == 1:
            return f"    return {return_vars[0]}"
        return f"    return {', '.join(return_vars)}"


