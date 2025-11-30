from __future__ import annotations

import ast
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, PortModel, EdgeModel
from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext
from .edge_router import (
    is_flow_node,
    is_event_node,
    connect_sources_to_target,
)
from .branch_builder import (
    create_dual_branch_node,
    create_multi_branch_node,
)
from .loop_builder import (
    create_finite_loop_node,
    create_list_iteration_loop_node,
    analyze_for_loop,
)
from .flow_utils import (
    pick_default_flow_output_port,
    register_output_variables,
    materialize_call_node,
    handle_alias_assignment,
    warn_literal_assignment,
)


# 辅助函数已移至 branch_builder.py 和 loop_builder.py


def _connect_prev_to_new(
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    new_node: NodeModel,
    edges: List[EdgeModel],
    suppress: bool,
) -> None:
    if prev_flow_node is None or suppress:
        return
    connect_sources_to_target(prev_flow_node, new_node, edges)


def _extract_annotation_type_text(annotation_expr: ast.expr) -> str:
    """从 AnnAssign 的注解表达式中提取类型名称文本。

    当前约定：
    - 仅当注解是字符串常量时才生效（例如: \"字典\" / \"整数列表\"）；
    - 其他形式的注解（如 Name/Attribute）暂不参与端口类型覆盖。
    """
    if isinstance(annotation_expr, ast.Constant) and isinstance(annotation_expr.value, str):
        annotation_text = annotation_expr.value.strip()
        if annotation_text != "":
            return annotation_text
    return ""


def _register_port_type_override_from_annotation(
    *,
    graph_model: GraphModel,
    env: VarEnv,
    node: NodeModel,
    targets: Union[ast.Name, ast.Tuple],
    annotation_type: str,
) -> None:
    """基于带类型注解的赋值，为节点输出端口注册类型覆盖信息。

    规则简述：
    - 仅处理单变量目标（Name），忽略元组等复杂形式；
    - 通过 VarEnv 查找该变量当前映射到的 (node_id, port_name)，
      且要求 node_id 与当前节点一致，确保覆盖定位到正确的输出端口；
    - annotation_type 为非空字符串时，将其写入 GraphModel.metadata["port_type_overrides"]
      中，对应键为 {node_id: {port_name: annotation_type}}。
    """
    if not isinstance(targets, ast.Name):
        return
    variable_name = targets.id
    if not isinstance(variable_name, str) or variable_name == "":
        return
    if not isinstance(annotation_type, str) or annotation_type.strip() == "":
        return

    variable_source = env.get_variable(variable_name)
    if variable_source is None:
        return

    source_node_id, source_port_name = variable_source
    if source_node_id != node.id:
        return
    if not isinstance(source_port_name, str) or source_port_name == "":
        return

    overrides_raw = graph_model.metadata.get("port_type_overrides")
    if overrides_raw is None:
        overrides: Dict[str, Dict[str, str]] = {}
    else:
        overrides = (
            dict(overrides_raw)
            if isinstance(overrides_raw, dict)
            else {}
        )

    node_overrides = overrides.get(source_node_id)
    if node_overrides is None:
        node_overrides = {}
    else:
        node_overrides = dict(node_overrides)

    node_overrides[source_port_name] = annotation_type.strip()
    overrides[source_node_id] = node_overrides
    graph_model.metadata["port_type_overrides"] = overrides


def handle_if_statement(
    stmt: ast.If,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    suppress_prev_connection: bool = False,
) -> Tuple[List[NodeModel], List[EdgeModel], Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]]]:
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    has_elif = len(stmt.orelse) > 0 and isinstance(stmt.orelse[0], ast.If)
    if has_elif:
        line_no = getattr(stmt, 'lineno', '?')
        validators.warn(f"行{line_no}: 发现if-elif-else结构，建议使用match-case语句表示真正的多分支节点")

    branch_node, branch_nodes, branch_edges, branch_last_nodes = create_dual_branch_node(
        stmt, prev_flow_node, graph_model, env, ctx, validators, parse_method_body
    )
    if branch_node:
        nodes.append(branch_node)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

        if prev_flow_node is None and (not suppress_prev_connection):
            # 从 env.node_sequence 回溯最近流程节点，否则回退事件节点
            fallback: Optional[NodeModel] = None
            for cand in reversed(env.node_sequence):
                if is_flow_node(cand) and (not is_event_node(cand)):
                    fallback = cand
                    break
            if fallback is None:
                fallback = env.current_event_node
            prev_flow_node = fallback

        _connect_prev_to_new(prev_flow_node, branch_node, edges, suppress_prev_connection)

        return nodes, edges, branch_last_nodes if branch_last_nodes else None

    return nodes, edges, prev_flow_node


def handle_match_statement(
    stmt: ast.Match,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    suppress_prev_connection: bool = False,
) -> Tuple[List[NodeModel], List[EdgeModel], Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]]]:
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    branch_node, branch_nodes, branch_edges, branch_last_nodes = create_multi_branch_node(
        stmt, prev_flow_node, graph_model, env, ctx, validators, parse_method_body
    )
    if branch_node:
        nodes.append(branch_node)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)
        _connect_prev_to_new(prev_flow_node, branch_node, edges, suppress_prev_connection)
        return nodes, edges, branch_last_nodes if branch_last_nodes else None

    return nodes, edges, prev_flow_node


def handle_for_loop(
    stmt: ast.For,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    suppress_prev_connection: bool = False,
) -> Tuple[List[NodeModel], List[EdgeModel], Optional[NodeModel]]:
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    is_range, loop_var, iter_var = analyze_for_loop(stmt)
    if is_range:
        loop_node, loop_nodes, loop_edges = create_finite_loop_node(stmt, prev_flow_node, loop_var, graph_model, env, ctx, validators, parse_method_body)
    else:
        loop_node, loop_nodes, loop_edges = create_list_iteration_loop_node(stmt, prev_flow_node, loop_var, iter_var, graph_model, env, ctx, validators, parse_method_body)

    if loop_node:
        nodes.append(loop_node)
        nodes.extend(loop_nodes)
        edges.extend(loop_edges)
        _connect_prev_to_new(prev_flow_node, loop_node, edges, suppress_prev_connection)
        return nodes, edges, loop_node

    return nodes, edges, prev_flow_node


def parse_method_body(
    body: List[ast.stmt],
    event_node: Optional[NodeModel],
    graph_model: GraphModel,
    suppress_initial_flow_edge: bool,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
) -> Tuple[List[NodeModel], List[EdgeModel]]:
    """解析方法体，生成节点和边
    
    Args:
        body: 方法体语句列表
        event_node: 事件节点（作为初始前驱）
        graph_model: 图模型
        suppress_initial_flow_edge: 是否抑制首条流程边
        env: 变量环境
        ctx: 工厂上下文
        validators: 验证器
        
    Returns:
        (节点列表, 边列表)
    """
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]] = event_node
    need_suppress_once = bool(suppress_initial_flow_edge)

    for stmt_index, stmt in enumerate(body):
        # 表达式语句：节点调用
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            result = materialize_call_node(
                call_expr=stmt.value,
                stmt=stmt,
                prev_flow_node=prev_flow_node,
                need_suppress_once=need_suppress_once,
                ctx=ctx,
                env=env,
                validators=validators,
                check_unused=False,
                later_stmts=None,
                assigned_names=None,
            )
            
            if result.should_skip:
                continue
            
            if result.node:
                nodes.append(result.node)
                env.node_sequence.append(result.node)
            
            nodes.extend(result.nested_nodes)
            edges.extend(result.edges)
            
            if result.new_prev_flow_node is not None:
                prev_flow_node = result.new_prev_flow_node
                need_suppress_once = result.new_suppress_flag

        # 赋值语句
        elif isinstance(stmt, ast.Assign):
            # 处理纯别名赋值
            if handle_alias_assignment(stmt.value, stmt.targets, env):
                continue
            
            # 发出字面量赋值警告
            warn_literal_assignment(stmt.value, stmt.targets, stmt, validators)
            
            # 处理调用节点赋值
            if isinstance(stmt.value, ast.Call):
                # 提取赋值变量名（用于未使用检查）
                assigned_names: List[str] = []
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        assigned_names.append(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned_names.append(elt.id)
                
                result = materialize_call_node(
                    call_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    ctx=ctx,
                    env=env,
                    validators=validators,
                    check_unused=True,
                    later_stmts=body[stmt_index + 1:],
                    assigned_names=assigned_names,
                )
                
                if result.should_skip:
                    continue
                
                if result.node:
                    nodes.append(result.node)
                    env.node_sequence.append(result.node)
                    
                    # 注册输出变量
                    register_output_variables(result.node, stmt.targets, env)
                
                nodes.extend(result.nested_nodes)
                edges.extend(result.edges)
                
                if result.new_prev_flow_node is not None:
                    prev_flow_node = result.new_prev_flow_node
                    need_suppress_once = result.new_suppress_flag

        # 带类型注解的赋值语句（AnnAssign）
        elif isinstance(stmt, ast.AnnAssign):
            # 处理纯别名赋值
            if handle_alias_assignment(stmt.value, stmt.target, env):
                continue
            
            # 处理调用节点赋值
            if isinstance(stmt.value, ast.Call):
                # 提取赋值变量名（用于未使用检查）
                assigned_names_ann: List[str] = []
                if isinstance(stmt.target, ast.Name):
                    assigned_names_ann.append(stmt.target.id)
                
                result = materialize_call_node(
                    call_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    ctx=ctx,
                    env=env,
                    validators=validators,
                    check_unused=True,
                    later_stmts=body[stmt_index + 1:],
                    assigned_names=assigned_names_ann,
                )
                
                if result.should_skip:
                    continue
                
                if result.node:
                    nodes.append(result.node)
                    env.node_sequence.append(result.node)

                    # 注册输出变量
                    register_output_variables(result.node, stmt.target, env)

                    # 基于类型注解为对应输出端口记录类型覆盖信息
                    annotation_type_text = _extract_annotation_type_text(stmt.annotation)
                    if annotation_type_text:
                        _register_port_type_override_from_annotation(
                            graph_model=graph_model,
                            env=env,
                            node=result.node,
                            targets=stmt.target,
                            annotation_type=annotation_type_text,
                        )

                nodes.extend(result.nested_nodes)
                edges.extend(result.edges)
                
                if result.new_prev_flow_node is not None:
                    prev_flow_node = result.new_prev_flow_node
                    need_suppress_once = result.new_suppress_flag

        # If
        elif isinstance(stmt, ast.If):
            if_nodes, if_edges, prev_flow_node = handle_if_statement(
                stmt, prev_flow_node, graph_model, env, ctx, validators, suppress_prev_connection=need_suppress_once
            )
            if need_suppress_once:
                need_suppress_once = False
            nodes.extend(if_nodes)
            edges.extend(if_edges)

        # Match
        elif isinstance(stmt, ast.Match):
            match_nodes, match_edges, prev_flow_node = handle_match_statement(
                stmt, prev_flow_node, graph_model, env, ctx, validators, suppress_prev_connection=need_suppress_once
            )
            if need_suppress_once:
                need_suppress_once = False
            nodes.extend(match_nodes)
            edges.extend(match_edges)

        # For
        elif isinstance(stmt, ast.For):
            for_nodes, for_edges, prev_flow_node = handle_for_loop(
                stmt, prev_flow_node, graph_model, env, ctx, validators, suppress_prev_connection=need_suppress_once
            )
            if need_suppress_once:
                need_suppress_once = False
            nodes.extend(for_nodes)
            edges.extend(for_edges)

        # Break
        elif isinstance(stmt, ast.Break):
            if not env.loop_stack:
                line_no = getattr(stmt, 'lineno', '?')
                validators.warn(f"行{line_no}: 发现 break 但不在循环体内，将被忽略")
                continue
            target_loop = env.loop_stack[-1]

            def _connect_break_from_source(source_obj: Union[NodeModel, Tuple[NodeModel, str]], loop_node: NodeModel) -> None:
                """连接break语句到循环节点的跳出循环端口"""
                if isinstance(source_obj, tuple) and len(source_obj) == 2:
                    src_node, forced_src_port = source_obj
                    edges.append(EdgeModel(
                        id=str(uuid.uuid4()),
                        src_node=src_node.id,
                        src_port=forced_src_port,
                        dst_node=loop_node.id,
                        dst_port="跳出循环",
                    ))
                    return
                
                src_node = source_obj
                src_port = pick_default_flow_output_port(src_node)
                
                # 特殊处理：分支和循环节点的默认出口
                if src_node.title in ["双分支", "多分支"]:
                    for p in src_node.outputs:
                        if p.name == "默认":
                            src_port = "默认"
                            break
                elif src_node.title in ["有限循环", "列表迭代循环"]:
                    for p in src_node.outputs:
                        if p.name == "循环完成":
                            src_port = "循环完成"
                            break
                
                edges.append(EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=src_node.id,
                    src_port=src_port or "流程出",
                    dst_node=loop_node.id,
                    dst_port="跳出循环",
                ))

            if prev_flow_node:
                if isinstance(prev_flow_node, list):
                    for source in prev_flow_node:
                        _connect_break_from_source(source, target_loop)
                else:
                    _connect_break_from_source(prev_flow_node, target_loop)
            break

        # While（不转换）
        elif isinstance(stmt, ast.While):
            pass

    return nodes, edges



