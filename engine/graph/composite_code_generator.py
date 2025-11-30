"""复合节点代码生成器 - 从GraphModel生成函数格式的复合节点代码"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Set
from pathlib import Path

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.advanced_node_features import VirtualPinConfig, CompositeNodeConfig
from engine.graph.common import (
    collect_input_params,
    choose_output_var_names,
    finalize_output_var_names,
    PYTHON_TYPE_TO_PIN_TYPE,
    PIN_TYPE_TO_PYTHON_TYPE,
    is_flow_port,
    render_call_expression,
    VarNameCounter,
)
from engine.utils.graph.graph_algorithms import topological_sort_graph_model
from engine.utils.name_utils import make_valid_identifier


class CompositeCodeGenerator:
    """复合节点代码生成器 - 生成函数格式的复合节点代码"""
    
    def __init__(self, node_library: Optional[Dict[str, NodeDef]] = None):
        """初始化代码生成器
        
        Args:
            node_library: 节点库（键格式："分类/节点名"）
        """
        self.node_library = node_library or {}
        self._var_name_counter: VarNameCounter = VarNameCounter()
    
    def generate_code(self, composite: CompositeNodeConfig) -> str:
        """生成复合节点的函数格式代码
        
        Args:
            composite: 复合节点配置
            
        Returns:
            函数格式的Python代码
        """
        # 每次生成时重置变量命名计数器，避免跨图串值
        self._var_name_counter = VarNameCounter()

        lines = []
        
        # 1. 生成文件头（元数据docstring）
        lines.extend(self._generate_header(composite))
        
        # 2. 生成imports
        lines.append("")
        lines.append("from runtime.game_state import GameRuntime")
        lines.append("from plugins.nodes.server import *")
        
        # 3. 生成函数定义
        lines.append("")
        lines.extend(self._generate_function(composite))
        
        return '\n'.join(lines)
    
    def _generate_header(self, composite: CompositeNodeConfig) -> List[str]:
        """生成文件头部（元数据）"""
        lines = ['"""']
        lines.append(f"composite_id: {composite.composite_id}")
        lines.append(f"node_name: {composite.node_name}")
        lines.append(f"node_description: {composite.node_description}")
        lines.append(f"scope: {composite.scope}")
        lines.append(f"folder_path: {composite.folder_path}")
        lines.append('"""')
        return lines
    
    def _generate_function(self, composite: CompositeNodeConfig) -> List[str]:
        """生成函数定义"""
        lines = []
        
        # 生成函数签名
        func_signature = self._generate_function_signature(composite)
        lines.append(func_signature)
        
        # 生成docstring
        docstring = self._generate_function_docstring(composite)
        if docstring:
            lines.extend(docstring)
        
        # 生成函数体
        function_body = self._generate_function_body(composite)
        lines.extend(function_body)
        
        return lines
    
    def _generate_function_signature(self, composite: CompositeNodeConfig) -> str:
        """生成函数签名
        
        格式: def 函数名(game: GameRuntime, 参数1: 类型1, ...) -> 返回类型:
        """
        func_name = composite.node_name
        
        # 收集输入引脚（数据引脚）
        input_pins = [pin for pin in composite.virtual_pins if pin.is_input and not pin.is_flow]
        
        # 构建参数列表
        params = ["game: GameRuntime"]
        for pin in sorted(input_pins, key=lambda p: p.pin_index):
            pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, 'Any')
            params.append(f"{pin.pin_name}: {pin_type}")
        
        params_str = ", ".join(params)
        
        # 收集输出引脚（数据引脚）
        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        
        # 构建返回类型
        if not output_pins:
            return_type = "None"
        elif len(output_pins) == 1:
            pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(output_pins[0].pin_type, 'Any')
            return_type = pin_type
        else:
            # 多个返回值，使用Tuple
            types = [PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, 'Any') for pin in sorted(output_pins, key=lambda p: p.pin_index)]
            return_type = f"Tuple[{', '.join(types)}]"
        
        return f"def {func_name}({params_str}) -> {return_type}:"
    
    def _generate_function_docstring(self, composite: CompositeNodeConfig) -> List[str]:
        """生成函数的docstring"""
        lines = []
        
        # 开始docstring
        lines.append('    """' + composite.node_description if composite.node_description else '    """复合节点')
        
        # 输入引脚说明
        input_pins = [pin for pin in composite.virtual_pins if pin.is_input and not pin.is_flow]
        if input_pins:
            lines.append("    ")
            lines.append("    输入引脚:")
            for pin in sorted(input_pins, key=lambda p: p.pin_index):
                pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, 'Any')
                desc = f": {pin.description}" if pin.description else ""
                lines.append(f"        {pin.pin_name} ({pin_type}){desc}")
        
        # 输出引脚说明
        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        if output_pins:
            lines.append("    ")
            lines.append("    输出引脚:")
            for pin in sorted(output_pins, key=lambda p: p.pin_index):
                pin_type = PIN_TYPE_TO_PYTHON_TYPE.get(pin.pin_type, 'Any')
                desc = f": {pin.description}" if pin.description else ""
                lines.append(f"        {pin.pin_name} ({pin_type}){desc}")
        
        lines.append('    """')
        return lines
    
    def _generate_function_body(self, composite: CompositeNodeConfig) -> List[str]:
        """生成函数体（子图实现）"""
        lines = []
        
        # 反序列化子图
        from engine.graph.models import GraphModel
        graph_model = GraphModel.deserialize(composite.sub_graph)
        
        if not graph_model.nodes:
            # 空实现
            output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
            if output_pins:
                if len(output_pins) == 1:
                    lines.append(f"    return None  # TODO: 实现 {output_pins[0].pin_name}")
                else:
                    return_vals = ", ".join([f"None  # {pin.pin_name}" for pin in sorted(output_pins, key=lambda p: p.pin_index)])
                    lines.append(f"    return ({return_vals})")
            else:
                lines.append("    pass  # TODO: 实现函数体")
            return lines
        
        # 拓扑排序节点（统一入口）
        sorted_nodes = topological_sort_graph_model(graph_model)
        
        # 为每个节点生成代码
        var_mapping = {}  # (node_id, port_name) -> variable_name
        used_var_names: Set[str] = set()
        
        # 首先映射输入引脚到函数参数
        # 这样当节点的输入端口是输入引脚时，可以直接使用函数参数名
        for pin in composite.virtual_pins:
            if pin.is_input and not pin.is_flow:
                # 输入引脚映射到函数参数名
                # mapped_ports列表中是这个输入引脚连接到的内部节点端口
                for mapped_port in pin.mapped_ports:
                    # (内部节点ID, 内部端口名) -> 输入参数名
                    var_mapping[(mapped_port.node_id, mapped_port.port_name)] = pin.pin_name
        
        for node in sorted_nodes:
            node_lines = self._generate_node_call(node, graph_model, var_mapping, used_var_names)
            lines.extend(node_lines)
        
        # 生成return语句
        output_pins = [pin for pin in composite.virtual_pins if not pin.is_input and not pin.is_flow]
        if output_pins:
            return_line = self._generate_return_statement(output_pins, var_mapping)
            lines.append("")
            lines.append(return_line)
        
        return lines
    
    # 统一：拓扑排序改由 core.utilities.graph_algorithms 提供
    
    def _generate_node_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
        used_var_names: Set[str],
    ) -> List[str]:
        """为节点生成函数调用代码（包含变量名规整与空参处理）"""
        lines: List[str] = []
        
        # 收集输入参数
        params = self._collect_node_inputs(node, graph_model, var_mapping)
        param_segments = [f"{k}={v}" for k, v in params.items()]
        
        # 生成函数调用
        func_name = self._resolve_callable_name(node)
        call_expr = render_call_expression(func_name, "game", param_segments)
        
        # 收集输出变量
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
        
        # 生成代码行
        if output_vars:
            if len(output_vars) == 1:
                lines.append(f"    {output_vars[0]} = {call_expr}")
            else:
                vars_str = ", ".join(output_vars)
                lines.append(f"    {vars_str} = {call_expr}")
        else:
            lines.append(f"    {call_expr}")
        
        return lines
    
    def _collect_node_inputs(self, node: NodeModel, graph_model: GraphModel,
                            var_mapping: Dict[Tuple[str, str], str]) -> Dict[str, str]:
        """收集节点的输入参数（统一委托 common）。"""
        return collect_input_params(node, graph_model, var_mapping)

    def _resolve_callable_name(self, node: NodeModel) -> str:
        """根据节点定义解析可调用函数名称并规整为合法标识符。"""
        key = f"{node.category}/{node.title}"
        node_def = self.node_library.get(key)
        reference_name = node_def.name if node_def else node.title
        return make_valid_identifier(reference_name)

    def _generate_return_statement(self, output_pins: List[VirtualPinConfig],
                                   var_mapping: Dict[Tuple[str, str], str]) -> str:
        """生成return语句"""
        return_vars = []
        
        for pin in sorted(output_pins, key=lambda p: p.pin_index):
            # 从映射中查找对应的变量
            var_found = False
            for mapped_port in pin.mapped_ports:
                var_name = var_mapping.get((mapped_port.node_id, mapped_port.port_name))
                if var_name:
                    return_vars.append(var_name)
                    var_found = True
                    break
            
            if not var_found:
                # 找不到变量，使用占位符
                return_vars.append(f"None  # TODO: {pin.pin_name}")
        
        if len(return_vars) == 1:
            return f"    return {return_vars[0]}"
        else:
            return f"    return {', '.join(return_vars)}"
