"""类格式解析器

提供复合节点类格式（新格式）的解析能力。
"""

from __future__ import annotations
import ast
import uuid
from typing import Dict, List, Any, Optional, Tuple

from engine.nodes.node_definition_loader import NodeDef
from engine.nodes.advanced_node_features import VirtualPinConfig, MappedPort
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.graph.ir.node_factory import FactoryContext as IRFactoryContext, create_event_node, register_event_outputs
from engine.graph.ir.var_env import VarEnv as IRVarEnv
from engine.graph.ir.validators import Validators as IRValidators
from engine.graph.ir.flow_builder import parse_method_body as ir_parse_method_body
from engine.graph.common import node_name_index_from_library
from engine.graph.models import GraphModel, NodeModel
from engine.graph.composite.param_usage_tracker import ParamUsageTracker


class ClassFormatParser:
    """类格式复合节点解析器（新格式）"""
    
    def __init__(self, node_library: Dict[str, NodeDef], verbose: bool = False):
        """初始化解析器
        
        Args:
            node_library: 节点库
            verbose: 是否输出详细日志
        """
        self.node_library = node_library
        self.verbose = verbose
        self.node_name_index = node_name_index_from_library(node_library)
        self._factory_ctx = IRFactoryContext(
            node_library,
            self.node_name_index,
            verbose,
        )
        # 实例字段别名映射：attr_name -> 入口形参名（例如 "_定时器标识" -> "定时器标识"）
        self._state_attr_aliases: Dict[str, str] = {}
    
    def parse_class_methods(
        self,
        class_def: ast.ClassDef,
        virtual_pins: List[VirtualPinConfig]
    ) -> GraphModel:
        """解析类的所有装饰方法，生成合并的子图
        
        Args:
            class_def: 类定义AST节点
            virtual_pins: 虚拟引脚列表
            
        Returns:
            合并后的GraphModel
        """
        # 创建合并的图模型
        merged_graph = GraphModel()
        merged_graph.graph_name = class_def.name
        merged_graph.graph_id = str(uuid.uuid4())

        # 延迟导入以避免循环依赖
        from engine.graph.ir.virtual_pin_builder import (
            extract_method_spec_from_decorators,
            _apply_auto_pin_configuration,
        )

        # 预先收集类内实例字段与入口形参之间的简单别名关系，供跨方法虚拟引脚映射使用
        # 例如：在某个入口方法中出现 `self._定时器标识 = 定时器标识`
        # 则记录映射 {"_定时器标识": "定时器标识"}
        self._state_attr_aliases = self._collect_state_attr_aliases(class_def)
        
        # 遍历类的所有方法
        for item in class_def.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            
            # 跳过 __init__ 等特殊方法
            if item.name.startswith('__'):
                continue
            
            # 检查方法的装饰器
            method_spec = extract_method_spec_from_decorators(item)
            if not method_spec:
                continue

            # 应用自动推断，确保 inputs/outputs 与虚拟引脚保持一致
            method_spec = _apply_auto_pin_configuration(item, method_spec)
            
            if self.verbose:
                print(f"  解析方法: {item.name} (类型: {method_spec['type']})")
            
            # 解析方法体生成子图
            method_graph = self._parse_method_body_for_class(item, method_spec, virtual_pins)
            
            # 合并子图到总图
            self._merge_graph(merged_graph, method_graph)
            
            # 如果是事件处理器，记录事件节点到 event_flow_order 和 event_flow_titles
            if method_spec['type'] == 'event_handler':
                # 找到事件节点
                for node in method_graph.nodes.values():
                    if node.category == "事件节点":
                        merged_graph.event_flow_order.append(node.id)
                        merged_graph.event_flow_titles.append(node.title)
                        break
        
        return merged_graph
    
    def _parse_method_body_for_class(
        self,
        method_def: ast.FunctionDef,
        method_spec: Dict[str, Any],
        virtual_pins: List[VirtualPinConfig]
    ) -> GraphModel:
        """解析类方法的函数体，生成子图
        
        Args:
            method_def: 方法定义AST节点
            method_spec: 方法规范字典
            virtual_pins: 虚拟引脚列表
            
        Returns:
            方法的子图GraphModel
        """
        # 创建方法子图
        method_graph = GraphModel()
        method_graph.graph_name = method_def.name
        method_graph.graph_id = str(uuid.uuid4())
        
        # 记录方法参数名（跳过self）
        param_names = [arg.arg for arg in method_def.args.args[1:]]
        
        # 创建参数使用追踪器（可感知 self.xxx ← 入口形参 的别名关系，用于跨方法虚拟引脚映射）
        tracker = ParamUsageTracker(
            param_names,
            self.node_name_index,
            self.node_library,
            self.verbose,
            state_attr_to_param=self._state_attr_aliases,
        )
        
        # 如果是事件处理器，需要先创建事件节点
        event_node = None
        if method_spec['type'] == 'event_handler':
            event_name = method_spec.get('event_name', method_def.name)
            # 创建事件节点
            event_node = create_event_node(event_name, method_def, self._factory_ctx)
            method_graph.nodes[event_node.id] = event_node
            
            # 注册事件节点的输出到环境（用于后续方法体引用）
            ir_env_temp = IRVarEnv()
            register_event_outputs(event_node, method_def, ir_env_temp)
        
        # 使用 IR 管线解析方法体
        ir_env = IRVarEnv()
        data_output_var_map = method_spec.get('data_output_var_map', {}) or {}
        predeclared_locals: List[str] = []
        for pin_name, pin_type in method_spec.get('outputs', []):
            if pin_type == "流程":
                continue
            var_name = data_output_var_map.get(pin_name, pin_name)
            if isinstance(var_name, str) and var_name:
                predeclared_locals.append(var_name)
        ir_env.add_predeclared_locals(predeclared_locals)
        
        # 如果是事件处理器，将事件参数输出注册到环境
        if event_node:
            register_event_outputs(event_node, method_def, ir_env)
        
        ir_validators = IRValidators()
        nodes, edges = ir_parse_method_body(
            method_def.body,
            event_node,
            method_graph,
            False,
            ir_env,
            self._factory_ctx,
            ir_validators
        )
        
        for node in nodes:
            method_graph.nodes[node.id] = node
        for edge in edges:
            method_graph.edges[edge.id] = edge
        
        # ===== 类格式：采集"方法形参使用" → 构建数据入虚拟引脚映射 =====
        # 按节点标题建立队列（用于与 AST 调用顺序配对）
        title_to_queue_for_match: Dict[str, List[NodeModel]] = {}
        for created_node in nodes:
            self._enqueue_aliases_for_match(created_node.title, created_node, title_to_queue_for_match)
        
        # 采集别名、常量和参数使用
        tracker.collect_aliases(method_def.body)
        tracker.collect_constants(method_def.body)
        tracker.collect_usage_from_calls(method_def.body, title_to_queue_for_match)
        tracker.collect_control_flow_usage(method_def.body)
        
        # 建立虚拟引脚映射（含数据入；类格式额外支持通过实例字段引用入口形参的场景）
        self._build_virtual_pin_mappings_for_method(
            method_def,
            method_spec,
            virtual_pins,
            method_graph,
            tracker.input_param_usage,
            dict(ir_env.var_map),
            tracker.state_pin_usage,
            tracker.control_flow_usage,
        )
        
        return method_graph
    
    def _build_virtual_pin_mappings_for_method(
        self,
        method_def: ast.FunctionDef,
        method_spec: Dict[str, Any],
        virtual_pins: List[VirtualPinConfig],
        method_graph: GraphModel,
        input_param_usage: Dict[str, List[Tuple[str, str]]],
        var_env_snapshot: Dict[str, Tuple[str, str]],
        state_pin_usage: Dict[str, List[Tuple[str, str]]],
        control_flow_usage: Dict[str, bool],
    ) -> None:
        """为方法的虚拟引脚建立映射
        
        Args:
            method_def: 方法定义AST节点
            method_spec: 方法规范字典
            virtual_pins: 虚拟引脚列表
            method_graph: 方法子图
            input_param_usage: 输入参数使用记录
        """
        # 根据方法类型建立不同的映射
        method_type = method_spec['type']

        data_output_var_map = method_spec.get('data_output_var_map', {})

        if method_type == 'flow_entry':
            # 流程入口：需要映射输入引脚和输出引脚
            for pin_name, pin_type in method_spec['inputs']:
                vpin = next((p for p in virtual_pins if p.pin_name == pin_name and p.is_input), None)
                if not vpin:
                    continue
                
                if pin_type == "流程":
                    # 流程入：映射到方法中第一个无入边的流程入口节点
                    self._map_flow_entry_pin(vpin, method_graph)
                else:
                    # 数据入：映射到使用该参数的节点端口
                    usage = input_param_usage.get(pin_name, [])
                    if usage:
                        vpin.mapped_ports = [
                            MappedPort(
                                node_id=node_id,
                                port_name=port_name,
                                is_input=True,
                                is_flow=False,
                            )
                            for (node_id, port_name) in usage
                        ]

            # 对于仅在控制流条件（if/match）中使用的数据输入引脚，尝试映射到分支节点的条件输入端口；
            # 若无法找到明确的分支节点端口，再退回到 allow_unmapped 标记。
            for pin_name, pin_type in method_spec['inputs']:
                if pin_type == "流程":
                    continue
                virtual_pin = next(
                    (
                        pin
                        for pin in virtual_pins
                        if pin.pin_name == pin_name and pin.is_input and not pin.is_flow
                    ),
                    None,
                )
                if not virtual_pin:
                    continue
                # 已有显式映射则不再处理
                if virtual_pin.mapped_ports:
                    continue
                if not control_flow_usage.get(pin_name):
                    continue

                # 优先：为控制流条件引脚寻找一个分支节点的“条件 / 控制表达式”输入端口作为映射锚点，
                # 这样在画布上可以看到清晰的角标，而非仅作为“允许未映射”的纯逻辑参与者。
                condition_target_ids: List[Tuple[str, str]] = []
                for node in method_graph.nodes.values():
                    title = getattr(node, "title", "")
                    # 双分支节点：title == "双分支"，条件端口名固定为 "条件"
                    if title == "双分支":
                        cond_port = next(
                            (p for p in node.inputs if getattr(p, "name", "") == "条件"),
                            None,
                        )
                        if cond_port:
                            condition_target_ids.append((node.id, cond_port.name))
                    # 多分支节点：title == "多分支"，控制表达式端口名固定为 "控制表达式"
                    elif title == "多分支":
                        ctrl_port = next(
                            (p for p in node.inputs if getattr(p, "name", "") == "控制表达式"),
                            None,
                        )
                        if ctrl_port:
                            condition_target_ids.append((node.id, ctrl_port.name))

                if condition_target_ids:
                    # 目前约定：一个入口形参通常只驱动单个条件分支节点；
                    # 若出现多个候选，仅选择第一个，以保持映射稳定可预期。
                    target_node_id, target_port_name = condition_target_ids[0]
                    virtual_pin.mapped_ports.append(
                        MappedPort(
                            node_id=target_node_id,
                            port_name=target_port_name,
                            is_input=True,
                            is_flow=False,
                        )
                    )
                else:
                    # 找不到合适的分支节点锚点时，退回到“允许未映射”的保守策略：
                    # 保证验证不过度报错，同时在 UI 预览中仍然列出该虚拟引脚。
                    virtual_pin.allow_unmapped = True

            # 在输出映射前，尝试识别“分支出口”场景：
            # 若方法体中存在双分支/多分支节点，优先将复合节点的流程输出虚拟引脚绑定到这些分支端口。
            # 理想情况：所有流程出口均未连接到后续节点（纯分支出口），此时可以一一对应。
            # 实际上，即便分支出口后还有少量局部变量设置节点，仍然希望在 UI 中把流程出口锚定到分支节点本身，
            # 而不是尾部的“设置局部变量”等技术性节点。
            branch_exit_targets: List[Tuple[str, str]] = []
            primary_branch_flow_outputs: List[Tuple[str, str]] = []
            for node in method_graph.nodes.values():
                title = getattr(node, "title", "")
                if title in ("双分支", "多分支"):
                    # 双分支节点：显式的“是/否”流程出口；
                    # 多分支节点：所有输出端口均表示不同的流程出口（默认 + 各 case 分支）。
                    if title == "双分支":
                        flow_outputs = [
                            p.name for p in node.outputs if is_flow_port_name(getattr(p, "name", ""))
                        ]
                    else:
                        flow_outputs = [p.name for p in node.outputs]
                    if not flow_outputs:
                        continue
                    # 记录第一个分支节点及其所有流程出口，作为兜底锚点：
                    if not primary_branch_flow_outputs:
                        primary_branch_flow_outputs = [(node.id, port_name) for port_name in flow_outputs]
                    has_branch_out_edges = False
                    for edge in method_graph.edges.values():
                        if edge.src_node != node.id:
                            continue
                        if any(edge.src_port == port_name for port_name in flow_outputs):
                            has_branch_out_edges = True
                            break
                    if not has_branch_out_edges:
                        # 所有分支出口都未接后续节点：视为“直接出口”，用于与虚拟流程出口一一对应
                        for port_name in flow_outputs:
                            branch_exit_targets.append((node.id, port_name))
                    break

            # 若存在分支节点但其流程出口后仍接有节点（例如仅用于设置局部变量并立即返回），
            # 则退回到以分支节点为锚点的简化策略：仍按分支端口顺序绑定流程虚拟引脚，
            # 避免将流程出口映射到语义上次要的“设置局部变量”等尾节点。
            if (not branch_exit_targets) and primary_branch_flow_outputs:
                branch_exit_targets = primary_branch_flow_outputs

            # 输出引脚：流程出 + 数据出
            branch_exit_index = 0
            for pin_name, pin_type in method_spec['outputs']:
                vpin = next((p for p in virtual_pins if p.pin_name == pin_name and not p.is_input), None)
                if not vpin:
                    continue
                
                if pin_type == "流程":
                    if branch_exit_targets and branch_exit_index < len(branch_exit_targets):
                        target_node_id, target_port_name = branch_exit_targets[branch_exit_index]
                        vpin.mapped_ports.append(
                            MappedPort(
                                node_id=target_node_id,
                                port_name=target_port_name,
                                is_input=False,
                                is_flow=True,
                            )
                        )
                        branch_exit_index += 1
                    else:
                        # 通用路径：流程出映射到方法中最后的流程出口节点
                        self._map_flow_exit_pin(vpin, method_graph)
                else:
                    self._map_data_output_pin(vpin, pin_name, data_output_var_map, var_env_snapshot)

        elif method_type == 'event_handler':
            # 事件处理器：输出引脚映射
            for pin_name, pin_type in method_spec['outputs']:
                vpin = next((p for p in virtual_pins if p.pin_name == pin_name and not p.is_input), None)
                if not vpin:
                    continue
                
                if pin_type == "流程":
                    self._map_flow_exit_pin(vpin, method_graph)
                else:
                    self._map_data_output_pin(vpin, pin_name, data_output_var_map, var_env_snapshot)

            # 事件处理器：处理通过实例字段引用的入口形参（例如 self._定时器标识）
            # 这些字段在入口方法中已通过 self.xxx = 入口形参 绑定，这里将其视作对应虚拟输入引脚的使用点。
            for pin_name, usage_list in (state_pin_usage or {}).items():
                if not usage_list:
                    continue
                vpin = next(
                    (p for p in virtual_pins if p.pin_name == pin_name and p.is_input and not p.is_flow),
                    None,
                )
                if not vpin:
                    continue
                for node_id, port_name in usage_list:
                    vpin.mapped_ports.append(
                        MappedPort(
                            node_id=node_id,
                            port_name=port_name,
                            is_input=True,
                            is_flow=False,
                        )
                    )
    
    def _map_flow_entry_pin(self, vpin: VirtualPinConfig, graph: GraphModel) -> None:
        """映射流程入虚拟引脚到图中的流程入口节点
        
        Args:
            vpin: 虚拟引脚配置
            graph: 图模型
        """
        candidates: List[Tuple[NodeModel, str]] = []
        for node in graph.nodes.values():
            flow_in_port = next((p for p in node.inputs if is_flow_port_name(p.name)), None)
            if not flow_in_port:
                continue
            has_incoming_flow = False
            for edge in graph.edges.values():
                if edge.dst_node == node.id and edge.dst_port == flow_in_port.name:
                    has_incoming_flow = True
                    break
            if has_incoming_flow:
                continue
            candidates.append((node, flow_in_port.name))

        if not candidates:
            return

        def _priority(item: Tuple[NodeModel, str]) -> Tuple[int, float]:
            node, _ = item
            title = getattr(node, "title", "")
            # 优先使用双分支/多分支作为首个流程节点，其次保持插入顺序
            if title in ("双分支", "多分支"):
                return (0, 0.0)
            return (1, node.pos[0] if node.pos else 0.0)

        best_node, best_port = sorted(candidates, key=_priority)[0]
        vpin.mapped_ports.append(MappedPort(
            node_id=best_node.id,
            port_name=best_port,
            is_input=True,
            is_flow=True
        ))
    
    def _map_flow_exit_pin(self, vpin: VirtualPinConfig, graph: GraphModel) -> None:
        """映射流程出虚拟引脚到图中的流程出口节点
        
        Args:
            vpin: 虚拟引脚配置
            graph: 图模型
        """
        # 查找无出边的流程出口节点（最后的流程节点）
        candidates = []
        for node in graph.nodes.values():
            flow_out_ports = [p for p in node.outputs if is_flow_port_name(p.name)]
            if not flow_out_ports:
                continue
            
            # 检查是否有流程出边
            has_outgoing_flow = False
            for edge in graph.edges.values():
                if edge.src_node == node.id and any(p.name == edge.src_port for p in flow_out_ports):
                    has_outgoing_flow = True
                    break
            
            if not has_outgoing_flow:
                candidates.append((node, flow_out_ports))
        
        if candidates:
            # 选择最靠右的节点（pos.x 最大）
            best_node, best_ports = max(candidates, key=lambda x: x[0].pos[0] if x[0].pos else 0)
            port_name = best_ports[0].name
            vpin.mapped_ports.append(MappedPort(
                node_id=best_node.id,
                port_name=port_name,
                is_input=False,
                is_flow=True
            ))
    
    def _map_data_output_pin(
        self,
        vpin: VirtualPinConfig,
        pin_name: str,
        data_var_map: Dict[str, str],
        var_env_snapshot: Dict[str, Tuple[str, str]]
    ) -> None:
        """将数据出引脚映射到变量绑定的节点端口"""
        var_name = data_var_map.get(pin_name, pin_name)
        binding = var_env_snapshot.get(var_name)
        if not binding:
            return
        node_id, port_name = binding
        vpin.mapped_ports.append(MappedPort(
            node_id=node_id,
            port_name=port_name,
            is_input=False,
            is_flow=False,
        ))
    
    def _merge_graph(self, target: GraphModel, source: GraphModel) -> None:
        """将源图合并到目标图
        
        Args:
            target: 目标图（会被修改）
            source: 源图
        """
        id_mapping: Dict[str, str] = {}
        for node_id, node in source.nodes.items():
            new_id = self._ensure_unique_id(node_id, target.nodes)
            if new_id != node_id:
                id_mapping[node_id] = new_id
                node.id = new_id
            target.nodes[new_id] = node
        
        for edge_id, edge in source.edges.items():
            if edge.src_node in id_mapping:
                edge.src_node = id_mapping[edge.src_node]
            if edge.dst_node in id_mapping:
                edge.dst_node = id_mapping[edge.dst_node]
            new_edge_id = self._ensure_unique_id(edge_id, target.edges)
            if new_edge_id != edge_id:
                edge.id = new_edge_id
            target.edges[edge.id] = edge
    
    def _enqueue_aliases_for_match(self, title: str, the_node: NodeModel, queue_dict: Dict[str, List[NodeModel]]) -> None:
        """将节点加入队列（含同义键）"""
        queue_dict.setdefault(title, []).append(the_node)
        if '/' in title:
            queue_dict.setdefault(title.replace('/', ''), []).append(the_node)

    def _ensure_unique_id(self, original_id: str, container: Dict[str, Any]) -> str:
        if original_id not in container:
            return original_id
        suffix = 1
        while True:
            candidate = f"{original_id}_{suffix}"
            if candidate not in container:
                return candidate
            suffix += 1

    def _collect_state_attr_aliases(self, class_def: ast.ClassDef) -> Dict[str, str]:
        """收集类内“实例字段 ← 入口形参”的简单别名关系。
        
        当前仅支持形如：
            self.xxx = 参数名
            self.xxx: 类型 = 参数名
        的直接赋值形式，并要求 参数名 是对应方法（通常为入口方法）的形参之一。
        
        返回：{字段名（不含 self.）: 入口形参名}
        """
        alias_map: Dict[str, str] = {}
        
        for item in class_def.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            
            # 方法形参（跳过 self）
            param_names = [arg.arg for arg in item.args.args[1:]]
            if not param_names:
                continue
            param_set = set(param_names)
            
            for node in ast.walk(item):
                assign_value = None
                targets: List[ast.expr] = []
                
                if isinstance(node, ast.Assign):
                    assign_value = node.value
                    targets = list(node.targets or [])
                elif isinstance(node, ast.AnnAssign):
                    assign_value = getattr(node, "value", None)
                    tgt = getattr(node, "target", None)
                    if tgt is not None:
                        targets = [tgt]
                
                if not isinstance(assign_value, ast.Name):
                    continue
                src_name = assign_value.id
                if src_name not in param_set:
                    continue
                
                for tgt in targets:
                    if isinstance(tgt, ast.Attribute):
                        owner = tgt.value
                        if isinstance(owner, ast.Name) and owner.id == "self":
                            # 简单策略：同一个字段名以“首次绑定”为准，后续重复绑定不覆盖
                            alias_map.setdefault(tgt.attr, src_name)
        
        return alias_map


