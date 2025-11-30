"""循环节点构建器

提供有限循环（range）和列表迭代循环的IR构建逻辑。
"""
from __future__ import annotations

import ast
import uuid
from typing import List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, PortModel, EdgeModel
from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext, extract_constant_value
from .edge_router import is_flow_node, is_event_node
from .branch_builder import find_first_flow_node, find_last_flow_node, block_has_return


def extract_range_params(iter_node: ast.Call) -> Tuple[Union[int, str, None], Union[int, str, None]]:
    """从range()调用中提取起始和结束值
    
    Returns:
        (起始值, 结束值)
        - 常量：返回int/float类型的值
        - 变量：返回变量名（str）
        - 无法提取：返回None
    """
    if not isinstance(iter_node, ast.Call):
        return 0, 0
    args = iter_node.args
    if len(args) == 1:
        end_node = args[0]
        # 尝试提取常量
        end = extract_constant_value(end_node)
        if isinstance(end, (int, float)):
            return 0, end
        # 尝试提取变量名
        if isinstance(end_node, ast.Name):
            return 0, end_node.id
        return 0, 0
    if len(args) >= 2:
        start_node = args[0]
        end_node = args[1]
        # 尝试提取起始值（常量或变量）
        start = extract_constant_value(start_node)
        if not isinstance(start, (int, float)):
            if isinstance(start_node, ast.Name):
                start = start_node.id
            else:
                start = 0
        # 尝试提取结束值（常量或变量）
        end = extract_constant_value(end_node)
        if not isinstance(end, (int, float)):
            if isinstance(end_node, ast.Name):
                end = end_node.id
            else:
                end = 0
        return start, end
    return 0, 0


def analyze_for_loop(stmt: ast.For) -> Tuple[bool, str, Optional[str]]:
    """分析for循环类型
    
    Returns:
        (是否是range循环, 循环变量名, 迭代变量名或None)
    """
    loop_var = stmt.target.id if isinstance(stmt.target, ast.Name) else "item"
    if isinstance(stmt.iter, ast.Call):
        if isinstance(stmt.iter.func, ast.Name) and stmt.iter.func.id == 'range':
            return True, loop_var, None
    iter_var = stmt.iter.id if isinstance(stmt.iter, ast.Name) else None
    return False, loop_var, iter_var


def create_finite_loop_node(
    stmt: ast.For,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    loop_var: str,
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,  # 避免循环导入
) -> Tuple[Optional[NodeModel], List[NodeModel], List[EdgeModel]]:
    """创建有限循环节点（range循环）
    
    Args:
        stmt: for语句AST节点
        prev_flow_node: 前驱流程节点
        loop_var: 循环变量名
        graph_model: 图模型
        env: 变量环境
        ctx: 工厂上下文
        validators: 验证器
        parse_method_body_func: 解析方法体的函数（避免循环导入）
        
    Returns:
        (循环节点, 所有子节点, 所有边)
    """
    loop_nodes: List[NodeModel] = []
    loop_edges: List[EdgeModel] = []

    loop_node_id = f"node_有限循环_{uuid.uuid4().hex[:8]}"
    start_val, end_val = extract_range_params(stmt.iter)
    input_ports = [
        PortModel(name="流程入", is_input=True),
        PortModel(name="跳出循环", is_input=True),
        PortModel(name="循环起始值", is_input=True),
        PortModel(name="循环终止值", is_input=True),
    ]
    output_ports = [
        PortModel(name="循环体", is_input=False),
        PortModel(name="循环完成", is_input=False),
        PortModel(name="当前循环值", is_input=False),
    ]
    
    # 构建input_constants：只对常量参数设置
    input_constants = {}
    if isinstance(start_val, (int, float)):
        input_constants["循环起始值"] = str(start_val)
    if isinstance(end_val, (int, float)):
        input_constants["循环终止值"] = str(end_val)
    
    loop_node = NodeModel(
        id=loop_node_id,
        title="有限循环",
        category="流程控制节点",
        pos=(0.0, 0.0),
        inputs=input_ports,
        outputs=output_ports,
        input_constants=input_constants,
    )
    # 源码行号：来自 for 语句本身
    loop_node.source_lineno = getattr(stmt, 'lineno', 0)
    loop_node.source_end_lineno = getattr(stmt, 'end_lineno', getattr(stmt, 'lineno', 0))

    # 为变量参数创建数据边
    if isinstance(start_val, str):
        # start_val 是变量名，查找其来源并创建数据边
        src = env.get_variable(start_val)
        if src:
            src_node_id, src_port = src
            loop_edges.append(EdgeModel(
                id=str(uuid.uuid4()),
                src_node=src_node_id,
                src_port=src_port,
                dst_node=loop_node_id,
                dst_port="循环起始值",
            ))
    
    if isinstance(end_val, str):
        # end_val 是变量名，查找其来源并创建数据边
        src = env.get_variable(end_val)
        if src:
            src_node_id, src_port = src
            loop_edges.append(EdgeModel(
                id=str(uuid.uuid4()),
                src_node=src_node_id,
                src_port=src_port,
                dst_node=loop_node_id,
                dst_port="循环终止值",
            ))

    # 循环变量注册
    env.set_variable(loop_var, loop_node_id, "当前循环值")

    # 解析循环体（为 break 建立上下文：入栈当前循环；并以“循环体”作为前驱）
    snapshot = env.snapshot()
    env.push_loop(loop_node)
    body_nodes, body_edges = parse_method_body_func(stmt.body, (loop_node, "循环体"), graph_model, False, env, ctx, validators)
    loop_nodes.extend(body_nodes)
    loop_edges.extend(body_edges)

    # 循环体入口连线已由 parse_method_body_func 基于前驱 (loop_node, "循环体") 自动完成。
    # 注意：不再为“自然结束”的循环体最后一个流程节点自动回连到循环节点的“流程入”，
    # 以避免在图中制造额外的回边；循环的重复执行由“有限循环”节点本身的语义表示。
    
    env.pop_loop()
    env.restore(snapshot)

    return loop_node, loop_nodes, loop_edges


def create_list_iteration_loop_node(
    stmt: ast.For,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    loop_var: str,
    iter_var: Optional[str],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,  # 避免循环导入
) -> Tuple[Optional[NodeModel], List[NodeModel], List[EdgeModel]]:
    """创建列表迭代循环节点
    
    Args:
        stmt: for语句AST节点
        prev_flow_node: 前驱流程节点
        loop_var: 循环变量名
        iter_var: 迭代列表变量名
        graph_model: 图模型
        env: 变量环境
        ctx: 工厂上下文
        validators: 验证器
        parse_method_body_func: 解析方法体的函数（避免循环导入）
        
    Returns:
        (循环节点, 所有子节点, 所有边)
    """
    loop_nodes: List[NodeModel] = []
    loop_edges: List[EdgeModel] = []

    loop_node_id = f"node_列表迭代循环_{uuid.uuid4().hex[:8]}"
    input_ports = [
        PortModel(name="流程入", is_input=True),
        PortModel(name="跳出循环", is_input=True),
        PortModel(name="列表", is_input=True),
    ]
    output_ports = [
        PortModel(name="循环体", is_input=False),
        PortModel(name="循环完成", is_input=False),
        PortModel(name="迭代值", is_input=False),
    ]
    loop_node = NodeModel(
        id=loop_node_id,
        title="列表迭代循环",
        category="流程控制节点",
        pos=(0.0, 0.0),
        inputs=input_ports,
        outputs=output_ports,
    )
    # 源码行号：来自 for 语句本身
    loop_node.source_lineno = getattr(stmt, 'lineno', 0)
    loop_node.source_end_lineno = getattr(stmt, 'end_lineno', getattr(stmt, 'lineno', 0))

    # 连接迭代列表输入
    if iter_var:
        src = env.get_variable(iter_var)
        if src:
            src_node_id, src_port = src
            loop_edges.append(EdgeModel(
                id=str(uuid.uuid4()),
                src_node=src_node_id,
                src_port=src_port,
                dst_node=loop_node_id,
                dst_port="列表",
            ))

    # 循环变量注册
    env.set_variable(loop_var, loop_node_id, "迭代值")

    # 解析循环体（为 break 建立上下文：入栈当前循环；并以“循环体”作为前驱）
    snapshot = env.snapshot()
    env.push_loop(loop_node)
    body_nodes, body_edges = parse_method_body_func(stmt.body, (loop_node, "循环体"), graph_model, False, env, ctx, validators)
    loop_nodes.extend(body_nodes)
    loop_edges.extend(body_edges)

    # 循环体入口连线已由 parse_method_body_func 基于前驱 (loop_node, "循环体") 自动完成。
    # 同样不再为自然结束的循环体构造回到循环节点“流程入”的自动回边，避免在图中产生多余的回路。
    
    env.pop_loop()
    env.restore(snapshot)

    return loop_node, loop_nodes, loop_edges



