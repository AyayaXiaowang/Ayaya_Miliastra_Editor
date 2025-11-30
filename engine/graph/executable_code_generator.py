"""可执行Python代码生成器 - 从GraphModel生成可直接运行的Python代码"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from datetime import datetime
from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.node_registry import get_node_registry
from engine.graph.common import (
    group_by_event_with_topo_order as group_by_event,
    collect_input_params as collect_input_params_common,
    finalize_output_var_names,
    VarNameCounter,
    choose_output_var_names,
    is_flow_port,
    render_call_expression,
)
from engine.graph.ir.event_utils import get_event_param_names_from_node
from engine.utils.name_utils import sanitize_class_name


class ExecutableCodeGenerator:
    """可执行Python代码生成器 - 生成可直接运行的Python代码"""
    
    def __init__(self, workspace_path: Path, node_library: Optional[Dict[str, NodeDef]] = None):
        """初始化可执行代码生成器"""
        self.workspace_path = workspace_path
        if node_library is None:
            registry = get_node_registry(workspace_path, include_composite=True)
            self.node_library = registry.get_library()
        else:
            self.node_library = node_library
        # 统一变量命名计数器（使用公共实现，避免策略分叉）
        self.var_name_counter = VarNameCounter(0)
    
    def generate_code(self, graph_model: GraphModel, metadata: Optional[Dict[str, Any]] = None) -> str:
        """生成可执行的Python代码（节点图类结构）
        
        Args:
            graph_model: 节点图模型
            metadata: 元数据字典（可选）
            
        Returns:
            可执行的Python代码
        """
        if metadata is None:
            metadata = {}
        
        lines = []
        
        # 1. 生成文件头
        lines.extend(self._generate_executable_header(graph_model, metadata))
        
        # 2. 生成imports（根据节点图类型）
        graph_type = metadata.get('graph_type', 'server')
        lines.extend(self._generate_executable_imports(graph_type))
        
        # 3. 生成节点图类
        lines.append("")
        lines.extend(self._generate_graph_class(graph_model))
        
        return '\n'.join(lines)
    
    def _generate_executable_header(self, graph_model: GraphModel, metadata: Dict[str, Any]) -> List[str]:
        """生成可执行文件的头部"""
        lines = ['"""']
        lines.append(f"节点图: {graph_model.graph_name or '未命名'}")
        lines.append(f"类型: {metadata.get('graph_type', 'server')}")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if graph_model.description:
            lines.append("")
            lines.append(graph_model.description)
        
        lines.append('"""')
        return lines
    
    def _generate_executable_imports(self, graph_type: str = "server") -> List[str]:
        """生成可执行代码的imports
        
        Args:
            graph_type: 节点图类型 ("server" 或 "client")
        """
        lines = []
        lines.append("")
        lines.append("# 导入运行时系统")
        lines.append("from runtime.game_state import GameRuntime")
        lines.append("")
        # 根据节点图类型，只导入对应的节点（一行就够！）
        if graph_type == "client":
            lines.append("# 导入所有client端节点（一行就够了！）")
            lines.append("from plugins.nodes.client import *")
        else:  # 默认server
            lines.append("# 导入所有server端节点（一行就够了！）")
            lines.append("from plugins.nodes.server import *")
        return lines
    
    def _collect_input_params(self, node: NodeModel, graph_model: GraphModel,
                              var_mapping: Dict[Tuple[str, str], str]) -> Dict[str, str]:
        """统一入口：委托 common.collect_input_params。"""
        return collect_input_params_common(node, graph_model, var_mapping)

    # 删除未使用的 _get_default_value，避免误导
    
    # ========== 节点图类生成方法 ==========
    
    def _sanitize_class_name(self, name: str) -> str:
        """将名称转换为有效的Python类名（统一委托工具模块）。"""
        return sanitize_class_name(name)
    
    def _generate_graph_class(self, graph_model: GraphModel) -> List[str]:
        """生成节点图类
        
        Args:
            graph_model: 节点图模型
            
        Returns:
            生成的代码行列表
        """
        lines = []
        
        # 类名
        class_name = self._sanitize_class_name(graph_model.graph_name)
        lines.append(f"class {class_name}:")
        lines.append(f'    """节点图类：{graph_model.graph_name}"""')
        lines.append("")
        
        # __init__方法
        lines.append("    def __init__(self, game: GameRuntime, owner_entity):")
        lines.append('        """初始化节点图')
        lines.append('        ')
        lines.append('        Args:')
        lines.append('            game: 游戏运行时')
        lines.append('            owner_entity: 挂载的实体（自身实体）')
        lines.append('        """')
        lines.append("        self.game = game")
        lines.append("        self.owner_entity = owner_entity")
        lines.append("        ")
        lines.append("        # 自动验证节点图代码规范")
        lines.append("        from runtime.engine.node_graph_validator import validate_node_graph")
        lines.append("        validate_node_graph(self.__class__)")
        lines.append("")
        
        # 生成事件处理方法
        event_flows = self._group_nodes_by_event(graph_model, verbose=False)
        
        if event_flows:
            for event_node_id, flow_nodes in event_flows.items():
                event_node = graph_model.nodes[event_node_id]
                method_lines = self._generate_event_handler_method(
                    event_node, flow_nodes, graph_model
                )
                lines.extend(method_lines)
                lines.append("")
        
        # register_handlers方法
        lines.extend(self._generate_register_handlers(event_flows, graph_model))
        
        return lines
    
    def _generate_event_handler_method(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
    ) -> List[str]:
        """生成事件处理方法
        
        Args:
            event_node: 事件节点
            flow_nodes: 该事件流中的节点ID列表
            graph_model: 节点图模型
            
        Returns:
            生成的方法代码行
        """
        lines = []

        event_name = event_node.title

        # 监听信号节点：使用事件上下文 kwargs，以便承载动态参数
        from engine.graph.common import SIGNAL_LISTEN_NODE_TITLE

        if event_node.title == SIGNAL_LISTEN_NODE_TITLE:
            lines.append(f"    def on_{event_name}(self, **event_kwargs):")
        else:
            params = get_event_param_names_from_node(event_node)
            # 方法签名
            signature_parts = ["self"]
            signature_parts.extend(params)
            param_section = ", ".join(signature_parts)
            lines.append(f"    def on_{event_name}({param_section}):")

        lines.append(f'        """事件处理器：{event_name}"""')

        # 生成方法体
        use_event_kwargs = event_node.title == SIGNAL_LISTEN_NODE_TITLE
        body_lines = self._generate_event_flow_body(
            event_node,
            flow_nodes,
            graph_model,
            use_event_kwargs=use_event_kwargs,
        )
        
        if not body_lines or all(not line.strip() for line in body_lines):
            lines.append("        pass")
        else:
            for line in body_lines:
                if line:
                    lines.append("        " + line)
                else:
                    lines.append("")
        
        return lines
    
    def _get_event_output_params(self, event_node: NodeModel) -> List[str]:
        """为事件节点的输出端口生成参数名列表，保持与端口顺序对齐。"""
        param_names = get_event_param_names_from_node(event_node)
        normalized: List[str] = []
        data_index = 0
        for port in event_node.outputs:
            if is_flow_port(event_node, port.name, True):
                normalized.append("")
                continue
            if data_index < len(param_names):
                normalized.append(param_names[data_index])
            else:
                fallback = port.name.replace(":", "").strip()
                normalized.append(fallback or f"event_param_{data_index}")
            data_index += 1
        return normalized

    def _generate_event_flow_body(
        self,
        event_node: NodeModel,
        flow_nodes: List[str],
        graph_model: GraphModel,
        use_event_kwargs: bool = False,
    ) -> List[str]:
        """生成事件流的方法体代码
        
        Args:
            event_node: 事件节点
            flow_nodes: 事件流中的节点ID列表
            graph_model: 节点图模型
            
        Returns:
            方法体代码行
        """
        lines = []
        
        # 变量映射（节点输出 -> Python变量名/表达式）
        var_mapping: Dict[Tuple[str, str], str] = {}

        # 将事件节点的输出映射到参数
        if use_event_kwargs and event_node.title == "监听信号":
            # 监听信号节点：从事件上下文中按名称提取参数
            for output_port in event_node.outputs:
                if is_flow_port(event_node, output_port.name, True):
                    continue
                param_name = output_port.name.replace(":", "").strip()
                if not param_name:
                    continue
                var_mapping[(event_node.id, output_port.name)] = f'event_kwargs.get("{param_name}")'
        else:
            event_params = self._get_event_output_params(event_node)
            for i, output_port in enumerate(event_node.outputs):
                if i < len(event_params):
                    param_name = event_params[i]
                    if param_name:
                        var_mapping[(event_node.id, output_port.name)] = param_name
        
        # 生成节点执行代码
        processed_nodes = set()
        processed_nodes.add(event_node.id)  # 事件节点已处理
        
        # 按照拓扑顺序处理节点
        for node_id in flow_nodes:
            if node_id == event_node.id:
                continue  # 跳过事件节点本身
            
            if node_id in processed_nodes:
                continue
            
            node = graph_model.nodes[node_id]
            node_lines = self._generate_node_call(node, graph_model, var_mapping)
            lines.extend(node_lines)
            processed_nodes.add(node_id)
        
        return lines
    
    def _generate_node_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> List[str]:
        """生成节点调用代码（使用 self.game 和 self.owner_entity）。"""
        # 发送信号节点使用统一的 emit_signal 代码路径
        from engine.graph.common import SIGNAL_SEND_NODE_TITLE

        if node.title == SIGNAL_SEND_NODE_TITLE:
            return self._generate_send_signal_call(node, graph_model, var_mapping)

        lines: List[str] = []

        # 收集输入参数
        input_params = self._collect_input_params(node, graph_model, var_mapping)

        # 对于自定义变量相关的节点，自动注入 owner_entity
        if node.title in ["设置自定义变量", "获取自定义变量"]:
            if "目标实体" not in input_params:
                input_params["目标实体"] = "self.owner_entity"

        func_name = node.title

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

            for idx in sorted(variadic_params.keys()):
                param_segments.append(variadic_params[idx])
            for param_name, param_value in normal_params.items():
                if "~" in param_name:
                    continue
                param_segments.append(f"{param_name}={param_value}")
        else:
            for param_name, param_value in input_params.items():
                param_segments.append(f"{param_name}={param_value}")

        call_expr = render_call_expression(func_name, "self.game", param_segments)

        if node.outputs:
            data_outputs = [p for p in node.outputs if not is_flow_port(node, p.name, True)]
            output_vars: List[str] = []
            if data_outputs:
                raw_names = choose_output_var_names(
                    node,
                    data_outputs,
                    prefer_custom_names=False,
                    fallback="generated",
                    counter=self.var_name_counter,
                )
                output_vars = finalize_output_var_names(
                    raw_names,
                    counter=self.var_name_counter,
                )
                for port, var_name in zip(data_outputs, output_vars):
                    var_mapping[(node.id, port.name)] = var_name

            if output_vars:
                if len(output_vars) == 1:
                    lines.append(f"{output_vars[0]} = {call_expr}")
                else:
                    outputs_str = ", ".join(output_vars)
                    lines.append(f"{outputs_str} = {call_expr}")
            else:
                lines.append(f"{call_expr}")
        else:
            lines.append(f"{call_expr}")

        return lines

    def _generate_send_signal_call(
        self,
        node: NodeModel,
        graph_model: GraphModel,
        var_mapping: Dict[Tuple[str, str], str],
    ) -> List[str]:
        """为【发送信号】节点生成统一的 emit_signal 调用代码。"""
        lines: List[str] = []

        # 基于通用逻辑收集所有数据输入
        input_params = self._collect_input_params(node, graph_model, var_mapping)

        # 解析信号绑定（优先使用 GraphModel.metadata["signal_bindings"]）
        bindings = (graph_model.metadata or {}).get("signal_bindings") or {}
        binding_info = bindings.get(node.id) or {}
        bound_signal_id = binding_info.get("signal_id") or ""

        if bound_signal_id:
            signal_id_expr = f'"{bound_signal_id}"'
        else:
            # 回退：使用“信号名”输入端口常量/表达式
            signal_id_expr = input_params.get("信号名", '""')

        # 目标实体：若未显式提供则回退为 owner_entity
        target_entity_expr = input_params.get("目标实体", "self.owner_entity")

        # 构造参数字典：排除静态输入（目标实体/信号名）
        entries: List[str] = []
        for param_name, param_value in input_params.items():
            if param_name in ("目标实体", "信号名"):
                continue
            entries.append(f'"{param_name}": {param_value}')

        params_expr = "{ " + ", ".join(entries) + " }" if entries else "{}"

        lines.append(
            f"self.game.emit_signal({signal_id_expr}, params={params_expr}, target_entity={target_entity_expr})"
        )
        return lines
    
    # 常量格式化逻辑统一在 engine.graph.common.format_constant
    
    # 流程端口判定统一入口：engine.graph.common.is_flow_port
    
    def _group_nodes_by_event(self, graph_model: GraphModel, verbose: bool = False) -> Dict[str, List[str]]:
        """将节点按事件流分组（统一入口）。"""
        flows = group_by_event(graph_model, include_data_dependencies=True)
        if verbose:
            print(f"  找到 {len(flows)} 个事件流")
        return flows
    
    
    
    
    def _generate_register_handlers(
        self,
        event_flows: Dict[str, List[str]],
        graph_model: GraphModel,
    ) -> List[str]:
        """生成register_handlers方法
        
        Args:
            event_flows: 事件流字典
            graph_model: 节点图模型
            
        Returns:
            register_handlers方法代码行
        """
        lines = []
        lines.append("    def register_handlers(self):")
        lines.append('        """注册所有事件处理器"""')

        if not event_flows:
            lines.append("        pass")
            return lines

        signal_bindings = (graph_model.metadata or {}).get("signal_bindings") or {}

        from engine.graph.common import SIGNAL_LISTEN_NODE_TITLE

        for event_node_id in event_flows:
            event_node = graph_model.nodes[event_node_id]
            event_name = event_node.title

            # 监听信号节点：按绑定的 signal_id 注册事件名
            if event_node.title == SIGNAL_LISTEN_NODE_TITLE:
                binding_info = signal_bindings.get(event_node_id) or {}
                bound_signal_id = binding_info.get("signal_id") or ""
                if bound_signal_id:
                    event_name = bound_signal_id

            lines.append("        self.game.register_event_handler(")
            lines.append(f'            "{event_name}",')
            lines.append(f"            self.on_{event_name},")
            lines.append("            owner=self.owner_entity")
            lines.append("        )")

        return lines


