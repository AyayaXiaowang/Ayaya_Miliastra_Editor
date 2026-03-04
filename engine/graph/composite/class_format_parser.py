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
from engine.graph.common import node_name_index_from_library, is_loop_node_name
from engine.graph.models import GraphModel, NodeModel
from engine.graph.composite.param_usage_tracker import ParamUsageTracker
from engine.graph.semantic import GraphSemanticPass
from engine.graph.utils.composite_instance_utils import iter_composite_instance_pairs


class ClassFormatParser:
    """类格式复合节点解析器（新格式）"""

    # 复合节点引脚声明辅助函数：仅作为“虚拟引脚声明标记”，不生成 IR 节点。
    # 这里用于在输出映射阶段通过 AST 反推“哪个控制流出口”对应某个虚拟流程出。
    _FLOW_OUT_MARKER_FUNCTIONS = {"流程出", "流程出引脚"}
    _FLOW_OUT_NAME_KEYWORDS = ("名称", "名字", "name", "pin_name")
    
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
        # 复合实例映射：alias -> composite_id（来自 __init__ 的 self.xxx = CompositeClass(...)）
        self._composite_instances: Dict[str, str] = {}
        # 复合类名 -> NodeDef（用于解析 __init__ 中的实例声明）
        self._composite_defs_by_class: Dict[str, NodeDef] = {}
        for _, node_def in (node_library or {}).items():
            if getattr(node_def, "is_composite", False):
                self._composite_defs_by_class[str(getattr(node_def, "name", "") or "")] = node_def
    
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

        # 复合节点定义文件中允许“复合内嵌套复合”时，必须从 __init__ 提取复合实例声明，
        # 否则方法体内的 `self.<实例>.<入口>(...)` 会被当作普通 Python 方法调用而无法建模为 IR 节点。
        self._composite_instances = self._collect_composite_instances_from_init(class_def)
        
        # 语义元数据（signal_bindings/struct_bindings）不在解析过程中多点写入，
        # 统一在方法合并完成后由 GraphSemanticPass 覆盖式生成。

        # 遍历类的所有方法
        pin_cursor = 0
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

            # 跳过内部方法（不对外暴露）；并保持与 build_virtual_pins_from_class 的顺序一致
            if method_spec.get("internal", False):
                continue

            # 为当前方法切出对应的虚拟引脚片段，避免“多入口同名引脚”导致映射互相覆盖
            method_type = method_spec.get("type")
            if method_type == "flow_entry":
                method_pin_count = len(method_spec.get("inputs", []) or []) + len(method_spec.get("outputs", []) or [])
            elif method_type == "event_handler":
                expose_event_params = bool(method_spec.get("expose_event_params", False))
                event_param_count = len(item.args.args[1:]) if expose_event_params else 0
                method_pin_count = event_param_count + len(method_spec.get("outputs", []) or [])
            else:
                method_pin_count = len(method_spec.get("inputs", []) or []) + len(method_spec.get("outputs", []) or [])

            method_virtual_pins = virtual_pins[pin_cursor: pin_cursor + method_pin_count]
            pin_cursor += method_pin_count
            
            if self.verbose:
                print(f"  解析方法: {item.name} (类型: {method_spec['type']})")
            
            # 解析方法体生成子图
            method_graph = self._parse_method_body_for_class(item, method_spec, method_virtual_pins, virtual_pins)
            
            # 合并子图到总图
            id_mapping = self._merge_graph(merged_graph, method_graph)
            # 合并阶段可能因 ID 冲突而重命名节点/连线：必须同步回写到虚拟引脚映射，
            # 否则后续结构校验会拿着“旧 node_id”判断，导致误报“缺少数据来源”。
            if id_mapping:
                for pin in virtual_pins:
                    for mapped in pin.mapped_ports:
                        mapped_node_id = str(getattr(mapped, "node_id", "") or "")
                        if mapped_node_id in id_mapping:
                            mapped.node_id = id_mapping[mapped_node_id]
            
            # 如果是事件处理器，记录事件节点到 event_flow_order 和 event_flow_titles
            if method_spec['type'] == 'event_handler':
                # 找到事件节点
                for node in method_graph.nodes.values():
                    if node.category == "事件节点":
                        merged_graph.event_flow_order.append(node.id)
                        merged_graph.event_flow_titles.append(node.title)
                        break
        
        # 语义元数据统一生成（单点写入）
        GraphSemanticPass.apply(merged_graph)
        return merged_graph
    
    def _parse_method_body_for_class(
        self,
        method_def: ast.FunctionDef,
        method_spec: Dict[str, Any],
        virtual_pins: List[VirtualPinConfig],
        all_virtual_pins: List[VirtualPinConfig],
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
        # 将 __init__ 中识别到的复合实例映射注入到 IR 环境，支持“复合内调用复合”建模。
        ir_env.composite_instances = dict(self._composite_instances)
        data_output_var_map = method_spec.get('data_output_var_map', {}) or {}
        predeclared_locals: List[str] = []
        for pin_name, pin_type in method_spec.get('outputs', []):
            if pin_type == "流程":
                continue
            var_name = data_output_var_map.get(pin_name, pin_name)
            if isinstance(var_name, str) and var_name:
                predeclared_locals.append(var_name)
                # 关键：预声明的“数据出变量”需要同步记录类型，
                # 否则局部变量建模（获取/设置局部变量）无法基于 VarEnv.var_types 写入 port_type_overrides，
                # 最终在 strict 结构校验中会表现为“端口类型仍为泛型”。
                if isinstance(pin_type, str) and pin_type.strip():
                    ir_env.set_var_type(var_name, pin_type)
        ir_env.add_predeclared_locals(predeclared_locals)
        
        # 如果是事件处理器，将事件参数输出注册到环境
        if event_node:
            register_event_outputs(event_node, method_def, ir_env)
        
        ir_validators = IRValidators()
        nodes, edges, _final_prev = ir_parse_method_body(
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
        tracker.collect_usage_from_param_assignments(method_def.body, nodes)
        tracker.collect_control_flow_usage(method_def.body)
        
        # 建立虚拟引脚映射（含数据入；类格式额外支持通过实例字段引用入口形参的场景）
        self._build_virtual_pin_mappings_for_method(
            method_def,
            method_spec,
            virtual_pins,
            all_virtual_pins,
            method_graph,
            tracker.input_param_usage,
            dict(ir_env.var_map),
            tracker.state_pin_usage,
            tracker.control_flow_usage,
        )
        
        return method_graph

    def _collect_composite_instances_from_init(self, class_def: ast.ClassDef) -> Dict[str, str]:
        """从 __init__ 中提取复合节点实例映射：alias -> composite_id。

        约定：仅识别 `self.<alias> = <CompositeClassName>(...)` 赋值语句。
        """
        instances: Dict[str, str] = {}
        for alias, class_name in iter_composite_instance_pairs(class_def):
            node_def = self._composite_defs_by_class.get(str(class_name))
            if not node_def:
                continue
            composite_id = str(getattr(node_def, "composite_id", "") or "").strip()
            if not composite_id:
                continue
            instances[str(alias)] = composite_id
        return instances
    
    def _build_virtual_pin_mappings_for_method(
        self,
        method_def: ast.FunctionDef,
        method_spec: Dict[str, Any],
        virtual_pins: List[VirtualPinConfig],
        all_virtual_pins: List[VirtualPinConfig],
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

            # 输出映射：优先基于 AST 反推“每个流程出对应的控制流出口（双分支/多分支端口）”，
            # 避免把“继续执行的分支出口”误当成流程出口绑定到虚拟流程出引脚上。
            flow_output_anchor_by_name = self._infer_flow_output_anchors_from_ast(
                method_def=method_def,
                method_graph=method_graph,
            )

            # 输出引脚：流程出 + 数据出
            for pin_name, pin_type in method_spec['outputs']:
                vpin = next((p for p in virtual_pins if p.pin_name == pin_name and not p.is_input), None)
                if not vpin:
                    continue
                
                if pin_type == "流程":
                    anchor = flow_output_anchor_by_name.get(pin_name)
                    if anchor is not None:
                        target_node_id, target_port_name = anchor
                        vpin.mapped_ports = [
                            MappedPort(
                                node_id=target_node_id,
                                port_name=target_port_name,
                                is_input=False,
                                is_flow=True,
                            )
                        ]
                    else:
                        # 通用路径：流程出映射到方法中最后的流程出口节点
                        self._map_flow_exit_pin(vpin, method_graph)
                else:
                    self._map_data_output_pin(vpin, pin_name, data_output_var_map, var_env_snapshot)

        elif method_type == 'event_handler':
            # 事件处理器：输出引脚映射
            flow_output_anchor_by_name = self._infer_flow_output_anchors_from_ast(
                method_def=method_def,
                method_graph=method_graph,
            )
            for pin_name, pin_type in method_spec['outputs']:
                vpin = next((p for p in virtual_pins if p.pin_name == pin_name and not p.is_input), None)
                if not vpin:
                    continue
                
                if pin_type == "流程":
                    anchor = flow_output_anchor_by_name.get(pin_name)
                    if anchor is not None:
                        target_node_id, target_port_name = anchor
                        vpin.mapped_ports = [
                            MappedPort(
                                node_id=target_node_id,
                                port_name=target_port_name,
                                is_input=False,
                                is_flow=True,
                            )
                        ]
                    else:
                        self._map_flow_exit_pin(vpin, method_graph)
                else:
                    self._map_data_output_pin(vpin, pin_name, data_output_var_map, var_env_snapshot)

            # 事件处理器：处理通过实例字段引用的入口形参（例如 self._定时器标识）
            # 这些字段在入口方法中已通过 self.xxx = 入口形参 绑定，这里将其视作对应虚拟输入引脚的使用点。
            for pin_name, usage_list in (state_pin_usage or {}).items():
                if not usage_list:
                    continue
                # 注意：事件处理器本身通常不声明数据入虚拟引脚；这些输入引脚来自其他 flow_entry 方法。
                # 因此这里必须在“全量虚拟引脚列表”中查找对应输入引脚，避免因方法切片导致找不到而误报缺线。
                vpin = next(
                    (p for p in all_virtual_pins if p.pin_name == pin_name and p.is_input and not p.is_flow),
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
    
    @classmethod
    def _extract_call_name(cls, node: ast.Call) -> Optional[str]:
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None

    @classmethod
    def _extract_constant_str(cls, expr: ast.expr) -> Optional[str]:
        if isinstance(expr, ast.Constant) and isinstance(getattr(expr, "value", None), str):
            return expr.value
        return None

    @classmethod
    def _extract_flow_out_pin_name(cls, node: ast.Call) -> Optional[str]:
        # keyword 优先，其次第 0 个位置参数
        for keyword in (node.keywords or []):
            if keyword.arg in cls._FLOW_OUT_NAME_KEYWORDS:
                return cls._extract_constant_str(keyword.value)
        if len(node.args or []) >= 1:
            return cls._extract_constant_str(node.args[0])
        return None

    @staticmethod
    def _block_has_direct_return_after(statement_block: List[ast.stmt], start_index: int) -> bool:
        """判断在同一语句块中，当前位置后是否存在直接的 return 语句。

        设计约定：复合节点的 `流程出("出口名")` 通常紧随 return（或在同一块内最终 return）。
        这里仅检查“同级 return”，避免把条件 return 等不确定写法误判为稳定出口。
        """
        if start_index < 0:
            return False
        for stmt in statement_block[start_index + 1:]:
            if isinstance(stmt, ast.Return):
                return True
        return False

    @staticmethod
    def _infer_match_case_port_name(case: ast.match_case) -> str:
        from engine.graph.ir.branch_builder import extract_case_value

        case_value = extract_case_value(case.pattern)
        if case_value in ("_", None):
            return "默认"
        return str(case_value)

    def _infer_flow_output_anchors_from_ast(
        self,
        *,
        method_def: ast.FunctionDef,
        method_graph: GraphModel,
    ) -> Dict[str, Tuple[str, str]]:
        """基于 AST 推断“流程出虚拟引脚 → 子图内部流程出口锚点”。

        目标：
        - 对 `if/match` + `流程出("出口名")` + `return` 的写法，精确把虚拟流程出口
          绑定到对应的【双分支/多分支】节点出口端口，而不是按顺序粗暴绑定到第一个分支节点。
        - 对无法推断的流程出口（例如无 return 的尾部流程出），回退到 `_map_flow_exit_pin` 路径。
        """
        anchors: Dict[str, Tuple[str, str]] = {}

        # 建立“源码行号 → 控制流节点”的索引，用于从 AST if/match 定位到 IR 生成的分支节点。
        control_nodes_by_title_and_lineno: Dict[Tuple[str, int], List[NodeModel]] = {}
        for node in method_graph.nodes.values():
            title = str(getattr(node, "title", "") or "")
            if title not in ("双分支", "多分支"):
                continue
            lineno = int(getattr(node, "source_lineno", 0) or 0)
            control_nodes_by_title_and_lineno.setdefault((title, lineno), []).append(node)

        def _pick_control_node_id(
            *,
            title: str,
            lineno: int,
            end_lineno: int,
        ) -> Optional[str]:
            candidates = control_nodes_by_title_and_lineno.get((title, lineno), [])
            if not candidates:
                return None
            for candidate in candidates:
                candidate_end = int(getattr(candidate, "source_end_lineno", 0) or 0)
                if candidate_end == end_lineno:
                    return candidate.id
            return candidates[0].id

        def _resolve_anchor_from_control_context(
            *,
            context_kind: str,
            control_node: ast.AST,
            control_port_name: str,
        ) -> Optional[Tuple[str, str]]:
            if context_kind == "if":
                expected_title = "双分支"
            elif context_kind == "match":
                expected_title = "多分支"
            else:
                return None

            lineno = int(getattr(control_node, "lineno", 0) or 0)
            end_lineno = int(getattr(control_node, "end_lineno", lineno) or lineno)
            node_id = _pick_control_node_id(title=expected_title, lineno=lineno, end_lineno=end_lineno)
            if node_id is None:
                return None
            node_model = method_graph.nodes.get(node_id)
            if node_model is None:
                return None
            if not any(getattr(port, "name", "") == control_port_name for port in (node_model.outputs or [])):
                return None
            return (node_id, control_port_name)

        # 栈帧：(kind, control_node_ast, control_port_name, allow_anchor_without_direct_return)
        #
        # allow_anchor_without_direct_return 用于支持一种常见写法：
        # - 在 if/match 分支体内仅写 `流程出("出口名")`（不写 return）；
        # - 控制语句本身在同级块内被“立刻 return”终止（例如入口方法末尾统一 `return 数据出...`）。
        # 在这种写法下，分支体内的流程出标记语义上仍是稳定出口，应锚定到双分支/多分支端口。
        control_flow_stack: List[Tuple[str, ast.AST, str, bool]] = []

        def _walk_statement_block(statement_block: List[ast.stmt]) -> None:
            for stmt_index, stmt in enumerate(statement_block or []):
                # 与 IR 解析一致：return 之后的语句不可达，停止扫描当前块
                if isinstance(stmt, ast.Return):
                    break

                # 捕获：流程出("xxx")（语句级调用）
                if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                    call_node = stmt.value
                    call_name = self._extract_call_name(call_node)
                    if call_name in self._FLOW_OUT_MARKER_FUNCTIONS:
                        pin_name = self._extract_flow_out_pin_name(call_node)
                        if pin_name and (pin_name not in anchors):
                            if not control_flow_stack:
                                continue

                            (
                                context_kind,
                                control_node,
                                control_port_name,
                                allow_without_return,
                            ) = control_flow_stack[-1]
                            has_direct_return_after = self._block_has_direct_return_after(statement_block, stmt_index)
                            marker_is_last_in_block = (stmt_index == (len(statement_block or []) - 1))

                            if has_direct_return_after or (allow_without_return and marker_is_last_in_block):
                                resolved = _resolve_anchor_from_control_context(
                                    context_kind=context_kind,
                                    control_node=control_node,
                                    control_port_name=control_port_name,
                                )
                                if resolved is not None:
                                    anchors[pin_name] = resolved

                # 分支：if → 双分支（是/否）
                if isinstance(stmt, ast.If):
                    # 若 if 语句在同级块内“立刻 return”，则允许分支体内的流程出标记
                    # 在无 return 的情况下仍被视为稳定出口（典型：入口方法最后统一 return 数据出）。
                    allow_without_return = (
                        (
                            (stmt_index + 1) < len(statement_block or [])
                            and isinstance(statement_block[stmt_index + 1], ast.Return)
                        )
                        # 额外支持：if 为方法/语句块的最后一条语句时，分支体内的 `流程出(...)` 即为稳定出口
                        # （常见模板：仅用 if/match 分支选择流程出口，不额外写 return）。
                        or (stmt_index == (len(statement_block or []) - 1))
                    )

                    control_flow_stack.append(("if", stmt, "是", allow_without_return))
                    _walk_statement_block(list(stmt.body or []))
                    control_flow_stack.pop()

                    control_flow_stack.append(("if", stmt, "否", allow_without_return))
                    _walk_statement_block(list(stmt.orelse or []))
                    control_flow_stack.pop()
                    continue

                # 分支：match → 多分支（默认/各 case）
                if isinstance(stmt, ast.Match):
                    allow_without_return = (
                        (
                            (stmt_index + 1) < len(statement_block or [])
                            and isinstance(statement_block[stmt_index + 1], ast.Return)
                        )
                        # 额外支持：match 为方法/语句块的最后一条语句时，case body 内的 `流程出(...)` 即为稳定出口
                        # （典型：match-case 仅用于分支选择，不额外写 return）。
                        or (stmt_index == (len(statement_block or []) - 1))
                    )
                    for case in (stmt.cases or []):
                        port_name = self._infer_match_case_port_name(case)
                        control_flow_stack.append(("match", stmt, port_name, allow_without_return))
                        _walk_statement_block(list(case.body or []))
                        control_flow_stack.pop()
                    continue

                # 循环体：递归扫描其 body/orelse（不改变控制流上下文）
                if isinstance(stmt, (ast.For, ast.While)):
                    _walk_statement_block(list(getattr(stmt, "body", []) or []))
                    _walk_statement_block(list(getattr(stmt, "orelse", []) or []))
                    continue

        _walk_statement_block(list(method_def.body or []))
        return anchors

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
        # 查找“终止流程端口”：输出流程端口没有任何出边的端口。
        #
        # 背景：
        # - IR 解析在遇到 `return` 时会终止当前语句块解析（return 后不可达）；
        # - 若 return 前存在 if/match 等分支结构且分支体内未出现显式的“流程出 + return”锚点写法，
        #   子图往往会出现多个“无出边的终止流程节点/端口”（例如 if/else 各自以一个执行节点结束）。
        # - 旧实现仅挑选“最靠右”的一个端口作为流程出映射，会导致其它分支无法从该虚拟流程出口继续连线。
        #
        # 新策略：
        # - 将同一个流程出虚拟引脚映射到所有终止流程端口；
        # - 这等价于支持“同一个流程出出口在多个分支上汇合后继续执行”的语义。
        #
        # 额外注意：循环节点（有限循环/列表迭代循环）内部的控制流“继续下一轮”并不会以显式回边呈现，
        # 因此循环体内某些端口会表现为“无出边”。这些端口语义上属于“本次迭代自然结束”，
        # 不应被当作方法级流程出口来绑定到虚拟流程出引脚上。
        loop_body_node_ids = self._collect_loop_body_node_ids(graph)
        candidate_ports: List[Tuple[NodeModel, str]] = []
        for node in graph.nodes.values():
            for output_port in (node.outputs or []):
                port_name = str(getattr(output_port, "name", "") or "")
                if not port_name:
                    continue
                if not is_flow_port_name(port_name):
                    continue

                # 循环节点的“循环体”是内部入口，不是方法出口
                if is_loop_node_name(str(getattr(node, "title", "") or "")) and port_name == "循环体":
                    continue

                # 循环体可达范围内的“终止流程端口”语义上属于 continue（本次迭代结束）
                if str(node.id) in loop_body_node_ids:
                    continue

                has_outgoing_flow = any(
                    (edge.src_node == node.id) and (edge.src_port == port_name)
                    for edge in graph.edges.values()
                )
                if has_outgoing_flow:
                    continue
                candidate_ports.append((node, port_name))

        if not candidate_ports:
            return

        # 去重并保持稳定顺序（按生成顺序优先）
        seen: set[Tuple[str, str]] = set()
        for node, port_name in candidate_ports:
            key = (str(node.id), str(port_name))
            if key in seen:
                continue
            seen.add(key)
            vpin.mapped_ports.append(
                MappedPort(
                    node_id=str(node.id),
                    port_name=str(port_name),
                    is_input=False,
                    is_flow=True,
                )
            )

    def _collect_loop_body_node_ids(self, graph: GraphModel) -> set[str]:
        """收集所有位于循环体（从循环节点的“循环体”出口可达）的节点 ID。

        背景：循环节点的“重复执行”由代码生成器语义承载，图结构通常不会显式创建“回到循环节点”的回边；
        因此循环体末尾的某些流程端口会呈现为“无出边”。这些端口不应被当作方法出口。
        """
        flow_edges_by_src: Dict[str, List[Any]] = {}
        for edge in graph.edges.values():
            src_port = str(getattr(edge, "src_port", "") or "")
            dst_port = str(getattr(edge, "dst_port", "") or "")
            if not src_port or not dst_port:
                continue
            if not is_flow_port_name(src_port):
                continue
            if not is_flow_port_name(dst_port):
                continue
            flow_edges_by_src.setdefault(str(edge.src_node), []).append(edge)

        loop_body_node_ids: set[str] = set()
        for node in graph.nodes.values():
            node_title = str(getattr(node, "title", "") or "")
            if not is_loop_node_name(node_title):
                continue
            loop_node_id = str(node.id)
            start_edges = [
                edge
                for edge in flow_edges_by_src.get(loop_node_id, [])
                if str(getattr(edge, "src_port", "") or "") == "循环体"
            ]
            pending_node_ids: List[str] = [str(edge.dst_node) for edge in start_edges]
            while pending_node_ids:
                current_node_id = pending_node_ids.pop()
                if current_node_id in loop_body_node_ids:
                    continue
                loop_body_node_ids.add(current_node_id)
                for next_edge in flow_edges_by_src.get(current_node_id, []):
                    next_dst_node_id = str(getattr(next_edge, "dst_node", "") or "")
                    # break 跳转会连回循环节点（跳出循环），不纳入循环体的可达范围。
                    if next_dst_node_id == loop_node_id:
                        continue
                    pending_node_ids.append(next_dst_node_id)

        return loop_body_node_ids
    
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
    
    def _merge_graph(self, target: GraphModel, source: GraphModel) -> Dict[str, str]:
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

        # 合并 GraphModel.metadata（仅合并可叠加的子域；避免覆盖语义 pass 的单点写入字段）
        #
        # 关键：IR 的局部变量建模（local_var_builder）会把“中文类型注解”写入 source.metadata["port_type_overrides"]，
        # 若合并阶段丢失该字段，会在后续结构校验/端口类型推断中表现为“端口类型仍为泛型”。
        source_meta = getattr(source, "metadata", None) or {}
        if isinstance(source_meta, dict):
            source_overrides = source_meta.get("port_type_overrides")
            if isinstance(source_overrides, dict) and source_overrides:
                target_meta = getattr(target, "metadata", None) or {}
                if not isinstance(target_meta, dict):
                    target_meta = {}
                target_overrides_raw = target_meta.get("port_type_overrides")
                target_overrides: Dict[str, Any] = dict(target_overrides_raw) if isinstance(target_overrides_raw, dict) else {}
                for old_node_id, mapping in source_overrides.items():
                    if not isinstance(mapping, dict):
                        continue
                    new_node_id = id_mapping.get(str(old_node_id), str(old_node_id))
                    # 同一 node_id 不应跨方法冲突；若冲突，以后写入者覆盖（避免残留旧 mapping）
                    target_overrides[str(new_node_id)] = dict(mapping)
                target_meta["port_type_overrides"] = target_overrides
                target.metadata = target_meta
        
        for edge_id, edge in source.edges.items():
            if edge.src_node in id_mapping:
                edge.src_node = id_mapping[edge.src_node]
            if edge.dst_node in id_mapping:
                edge.dst_node = id_mapping[edge.dst_node]
            new_edge_id = self._ensure_unique_id(edge_id, target.edges)
            if new_edge_id != edge_id:
                edge.id = new_edge_id
            target.edges[edge.id] = edge
        return id_mapping
    
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


