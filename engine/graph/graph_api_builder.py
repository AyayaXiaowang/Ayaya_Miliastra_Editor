"""
Python API构建器 - 让用户用Python代码生成节点图

核心思路：
1. 每个节点定义对应一个Python函数
2. 函数返回值是Variable对象，追踪数据来源
3. 在全局上下文中记录节点创建和连接
4. 自动处理流程连接
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import re
from engine.graph.models import GraphModel, NodeModel
from engine.nodes.node_definition_loader import NodeDef
from engine.graph.common import (
    apply_layout_quietly,
    format_constant,
    is_branch_node_name,
    is_flow_port,
    is_loop_node_name,
)
from engine.utils.graph.graph_utils import is_flow_port_name
from engine.utils.name_utils import make_valid_identifier


@dataclass
class Variable:
    """代表节点输出端口的变量"""
    source_node_id: str
    source_port_name: str
    graph_builder: 'GraphBuilder'
    
    def __repr__(self):
        return f"Variable({self.source_node_id}.{self.source_port_name})"


class GraphBuilder:
    """图构建器 - 追踪Python代码中的节点创建"""
    
    def __init__(self, node_library: Dict[str, NodeDef]):
        self.model = GraphModel()
        self.node_library = node_library
        self.last_flow_node_id: Optional[str] = None  # 用于自动流程连接
        self.current_event_flow_active = False  # 标记是否在事件流中
        self.branch_stack: List["BranchState"] = []  # 分支栈，用于嵌套分支
        self.node_counter = 0  # 节点计数器，用于分配初始X坐标
        
    def create_node(self, 
                   category: str, 
                   node_name: str, 
                   **input_values) -> Tuple[str, List[str]]:
        """
        创建节点并返回节点ID和输出端口名列表
        
        Args:
            category: 节点类别（事件节点/执行节点/查询节点/运算节点）
            node_name: 节点名称
            **input_values: 输入参数，可以是Variable或常量值
        
        Returns:
            (节点ID, 输出端口名列表)
        """
        # 查找节点定义
        node_key = f"{category}/{node_name}"
        if node_key not in self.node_library:
            raise ValueError(f"未找到节点定义: {node_key}")
        
        node_def = self.node_library[node_key]
        
        # 创建节点并分配初始位置（按创建顺序从左到右）
        # 这样布局算法才能根据X坐标正确排序节点
        initial_x = self.node_counter * 100.0
        initial_y = 0.0
        self.node_counter += 1
        
        node = self.model.add_node(
            title=node_def.name,
            category=node_def.category,
            input_names=node_def.inputs,
            output_names=node_def.outputs,
            pos=(initial_x, initial_y)
        )
        
        # 如果是复合节点，设置 composite_id（用于精确引用）
        if node_def.is_composite and node_def.composite_id:
            node.composite_id = node_def.composite_id
        
        # 处理流程连接
        is_event_node = category == '事件节点'
        has_flow_in = any(is_flow_port_name(port) for port in node_def.inputs)
        if is_event_node:
            # 事件节点开始新的流程
            self.last_flow_node_id = node.id
            self.current_event_flow_active = True
            # 清空分支栈
            self.branch_stack.clear()
        elif has_flow_in and self.current_event_flow_active:
            self._connect_flow_edge(node.id)
            self.last_flow_node_id = node.id
        
        # 处理数据输入连接
        data_input_ports = [p for p in node_def.inputs if not is_flow_port_name(p)]
        self._connect_data_inputs(node, data_input_ports, input_values)
        
        # 返回节点ID和输出端口列表（过滤掉所有流程端口）
        data_output_ports = [p for p in node_def.outputs if not is_flow_port_name(p)]
        
        return node.id, data_output_ports

    # === 内部辅助：流程连接 ===

    def _connect_flow_edge(self, target_node_id: str) -> None:
        if not self.branch_stack:
            self._connect_from_last_flow_node(target_node_id)
            return
        branch_state = self.branch_stack[-1]
        if branch_state.is_first_node_in_branch:
            self.model.add_edge(
                branch_state.node_id,
                branch_state.branch_name,
                target_node_id,
                '流程入',
            )
            branch_state.is_first_node_in_branch = False
            if branch_state.pop_after_first_edge:
                self._discard_branch_state()
        else:
            self._connect_from_last_flow_node(target_node_id)

    def _connect_from_last_flow_node(self, target_node_id: str) -> None:
        if not self.last_flow_node_id:
            return
        flow_port = self._find_first_flow_output(self.last_flow_node_id)
        if flow_port:
            self.model.add_edge(
                self.last_flow_node_id,
                flow_port,
                target_node_id,
                '流程入',
            )

    def _find_first_flow_output(self, node_id: str) -> Optional[str]:
        node = self.model.nodes.get(node_id)
        if not node:
            return None
        for port in node.outputs:
            if is_flow_port(node, port.name, True):
                return port.name
        return None

    def open_branch_state(self, node_id: str, branch_name: str, *, pop_after_first_edge: bool = False) -> "BranchState":
        """统一入口：记录分支状态并更新 last_flow_node。"""
        state = BranchState(
            node_id=node_id,
            branch_name=branch_name,
            previous_flow_node_id=self.last_flow_node_id,
            pop_after_first_edge=pop_after_first_edge,
        )
        self.branch_stack.append(state)
        self.last_flow_node_id = node_id
        return state

    def close_branch_state(self) -> None:
        """弹出最近的分支状态并恢复上游流程节点。"""
        self._discard_branch_state()

    def _discard_branch_state(self) -> None:
        if not self.branch_stack:
            self.last_flow_node_id = None
            return
        removed = self.branch_stack.pop()
        if self.branch_stack:
            self.last_flow_node_id = self.branch_stack[-1].node_id
        else:
            self.last_flow_node_id = removed.previous_flow_node_id

    def _connect_data_inputs(
        self,
        node: NodeModel,
        data_input_ports: List[str],
        input_values: Dict[str, Any],
    ) -> None:
        for port_name in data_input_ports:
            if port_name not in input_values:
                continue
            value = input_values[port_name]
            if isinstance(value, Variable):
                self.model.add_edge(
                    value.source_node_id,
                    value.source_port_name,
                    node.id,
                    port_name,
                )
            else:
                node.input_constants[port_name] = format_constant(value)
    
    def to_graph_model(self, apply_layout: bool = False) -> GraphModel:
        """
        返回构建的图模型
        
        Args:
            apply_layout: 是否应用自动布局算法
        """
        if apply_layout:
            apply_layout_quietly(self.model)
        return self.model
    
    def validate(self) -> List[str]:
        """验证图的完整性（底层验证）
        
        注意：这只是底层的图结构验证。
        如果需要完整的存档验证（包括节点挂载、端口定义等），
        请使用 ComprehensiveValidator.validate_all()
        """
        from engine.graph.graph_code_parser import validate_graph
        return validate_graph(self.model)


# 全局上下文（单例栈）
_builder_stack: List[GraphBuilder] = []


def set_builder(builder: GraphBuilder):
    """设置当前构建器（支持嵌套调用，通过栈维护激活实例）。"""
    if builder is None:
        raise ValueError("builder 不可为 None")
    _builder_stack.append(builder)


def get_builder() -> GraphBuilder:
    """获取当前构建器"""
    if not _builder_stack:
        raise RuntimeError("没有激活的GraphBuilder，请使用 set_builder() 设置")
    return _builder_stack[-1]


def release_builder(builder: Optional[GraphBuilder] = None) -> None:
    """释放当前构建器，允许并发/嵌套场景手动恢复上一个实例。"""
    if not _builder_stack:
        return
    if builder is None or _builder_stack and _builder_stack[-1] is builder:
        _builder_stack.pop()
    else:
        # 非顶层释放：线性扫描移除匹配实例
        for index in range(len(_builder_stack) - 1, -1, -1):
            if _builder_stack[index] is builder:
                _builder_stack.pop(index)
                break


class BuilderActivation:
    """上下文管理器：确保 GraphBuilder 激活与释放成对进行。"""

    def __init__(self, builder: GraphBuilder):
        self.builder = builder

    def __enter__(self) -> GraphBuilder:
        set_builder(self.builder)
        return self.builder

    def __exit__(self, exc_type, exc_val, exc_tb):
        release_builder(self.builder)
        return False


def activate_builder(builder: GraphBuilder) -> BuilderActivation:
    """便捷入口：with activate_builder(builder): ..."""
    return BuilderActivation(builder)





def create_node_api_function(node_def: NodeDef):
    """动态创建单个节点的API函数对象
    
    这个函数用于在运行时为复合节点动态创建API函数，
    使得复合节点可以在节点图代码中被其他复合节点引用。
    
    Args:
        node_def: 节点定义
        
    Returns:
        一个Python函数对象，调用时会创建对应的节点
    """
    # 检查是否是特殊的控制流节点
    is_branch_node = is_branch_node_name(node_def.name)
    is_loop_node = is_loop_node_name(node_def.name)
    
    # 数据输出端口（排除流程出口）
    data_outputs = [o for o in node_def.outputs if not is_flow_port_name(o)]
    
        # 输入参数名称（排除流程入）
    input_params = [inp for inp in node_def.inputs if not is_flow_port_name(inp)]
    
    def node_function(**kwargs):
        """动态生成的节点API函数"""
        builder = get_builder()
        
        # 构建input_values字典
        input_values = {}
        for inp in input_params:
            param_name = make_valid_identifier(inp)
            if param_name in kwargs and kwargs[param_name] is not None:
                input_values[inp] = kwargs[param_name]
        
        # 创建节点
        node_id, output_ports = builder.create_node(
            category=node_def.category,
            node_name=node_def.name,
            **input_values
        )
        
        # 返回值 - 特殊处理控制流节点
        if is_branch_node:
            # 双分支/多分支返回BranchManager
            if node_def.name == '双分支':
                return BranchManager(builder, node_id, ["是", "否"])
            else:  # 多分支
                return BranchManager(builder, node_id, ["默认"])
        elif is_loop_node:
            # 循环节点返回LoopContext
            output_vars = {}
            for i, out_name in enumerate(data_outputs):
                output_vars[out_name] = Variable(node_id, output_ports[i], builder)
            return LoopContext(builder, node_id, output_vars)
        elif len(data_outputs) == 0:
            return None
        elif len(data_outputs) == 1:
            return Variable(node_id, output_ports[0], builder)
        else:
            return tuple(Variable(node_id, output_ports[i], builder) for i in range(len(data_outputs)))
    
    # 设置函数名称和文档
    node_function.__name__ = make_valid_identifier(node_def.name)
    node_function.__doc__ = node_def.name
    
    return node_function


# ============================================================
# 控制流支持：上下文管理器
# ============================================================

@dataclass
class BranchState:
    node_id: str
    branch_name: str
    previous_flow_node_id: Optional[str] = None
    is_first_node_in_branch: bool = True
    pop_after_first_edge: bool = False


class BranchContext:
    """分支上下文 - 用于with语句管理分支"""
    
    def __init__(self, builder: GraphBuilder, branch_node_id: str, branch_name: str):
        self.builder = builder
        self.branch_node_id = branch_node_id
        self.branch_name = branch_name  # "是"、"否"、"默认"等
        self.parent_last_flow_node = None
        
    def __enter__(self):
        """进入分支"""
        # 保存当前的流程节点
        self.builder.open_branch_state(self.branch_node_id, self.branch_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出分支"""
        self.builder.close_branch_state()
        return False


class BranchManager:
    """分支管理器 - 提供分支属性访问"""
    
    def __init__(self, builder: GraphBuilder, branch_node_id: str, branch_names: List[str]):
        self.builder = builder
        self.branch_node_id = branch_node_id
        self.branch_names = branch_names
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 退出分支管理器时，所有分支都应该已经处理完
        return False
    
    def __getattr__(self, name: str):
        """动态访问分支名称，如 branch.是、branch.否"""
        if name in self.branch_names:
            return BranchContext(self.builder, self.branch_node_id, name)
        raise AttributeError(f"分支 '{name}' 不存在，可用分支: {self.branch_names}")


class LoopContext:
    """循环上下文 - 用于with语句管理循环"""
    
    def __init__(self, builder: GraphBuilder, loop_node_id: str, output_vars: Dict[str, Variable]):
        self.builder = builder
        self.loop_node_id = loop_node_id
        self.output_vars = output_vars  # 循环输出变量（如当前循环值）
        self.parent_last_flow_node = None
        
    def __enter__(self):
        """进入循环体"""
        self.builder.open_branch_state(self.loop_node_id, '循环体')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出循环体"""
        self.builder.close_branch_state()
        self.builder.open_branch_state(self.loop_node_id, '循环完成', pop_after_first_edge=True)
        return False
    
    def __getattr__(self, name: str):
        """访问循环输出变量，如 loop.当前循环值"""
        if name in self.output_vars:
            return self.output_vars[name]
        raise AttributeError(f"循环输出变量 '{name}' 不存在")
