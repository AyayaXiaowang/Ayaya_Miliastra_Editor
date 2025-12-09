"""流程语句构建器

负责将 if/match/for 等 Python 语句转换为流程控制相关的 IR 节点，
并处理与前驱流程节点之间的连线策略。
"""
from __future__ import annotations

import ast
from typing import Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.nodes.port_type_system import FLOW_PORT_TYPE

from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext, extract_nested_nodes
from .edge_router import (
    is_flow_node,
    is_event_node,
    connect_sources_to_target,
    create_data_edges_for_node_enhanced,
    is_flow_port_ctx,
)
from .branch_builder import (
    create_dual_branch_node,
    create_multi_branch_node,
    extract_case_value,
    find_first_flow_node,
    find_last_flow_node,
    block_has_return,
)
from .loop_builder import (
    create_finite_loop_node,
    create_list_iteration_loop_node,
    analyze_for_loop,
)
from .composite_builder import create_composite_node_from_instance_call


def _connect_prev_to_new(
    prev_flow_node: Optional[
        Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]
    ],
    new_node: NodeModel,
    edges: List[EdgeModel],
    suppress: bool,
) -> None:
    """在不抑制的前提下，将前驱流程节点连到新节点。"""
    if prev_flow_node is None or suppress:
        return
    connect_sources_to_target(prev_flow_node, new_node, edges)


def _collect_composite_flow_outputs(
    composite_node: NodeModel,
    ctx: FactoryContext,
) -> List[str]:
    """
    收集复合节点的所有流程输出端口名称。

    说明：
    - 优先使用节点库中的端口类型定义（NodeDef.output_types），确保像“分支为0/分支为1”
      这类不含“流程”关键字的端口也能被正确识别为流程出口；
    - 当无法在节点库中找到对应 NodeDef 时，回退到基于端口名的启发式判断。
    """
    flow_output_names: List[str] = []

    # 复合节点在节点库中的键统一为 "复合节点/<节点名>"
    node_title = getattr(composite_node, "title", "")
    node_def = ctx.node_library.get(f"复合节点/{node_title}")

    if node_def is not None:
        for port in composite_node.outputs:
            port_type = node_def.output_types.get(port.name)
            if port_type == FLOW_PORT_TYPE:
                flow_output_names.append(port.name)
    else:
        # 兜底：退回到名称规则（旧行为）
        flow_output_names = [
            port.name
            for port in composite_node.outputs
            if is_flow_port_ctx(composite_node, port.name, True)
        ]

    return flow_output_names


def handle_if_statement(
    stmt: ast.If,
    prev_flow_node: Optional[
        Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]
    ],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,
    suppress_prev_connection: bool = False,
) -> Tuple[
    List[NodeModel],
    List[EdgeModel],
    Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
]:
    """处理 if 语句并生成双分支节点及其子图。"""
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    has_elif = len(stmt.orelse) > 0 and isinstance(stmt.orelse[0], ast.If)
    if has_elif:
        line_no = getattr(stmt, "lineno", "?")
        validators.warn(
            f"行{line_no}: 发现if-elif-else结构，建议使用match-case语句表示真正的多分支节点"
        )

    # 在解析分支体前记录已有的流程节点，用于后续兜底回溯。
    # 这样可以避免在 prev_flow_node 缺失时，误把“刚刚在分支体内部创建的流程节点”
    # 当作 if 的前驱，从而产生自循环。
    flow_nodes_before_if = list(env.node_sequence)

    branch_node, branch_nodes, branch_edges, branch_last_nodes = create_dual_branch_node(
        stmt,
        prev_flow_node,
        graph_model,
        env,
        ctx,
        validators,
        parse_method_body_func,
    )
    if branch_node:
        nodes.append(branch_node)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)

        effective_prev = prev_flow_node
        if effective_prev is None and (not suppress_prev_connection):
            # 从 env.node_sequence 回溯最近流程节点，否则回退事件节点
            fallback: Optional[NodeModel] = None
            for candidate_node in reversed(flow_nodes_before_if):
                if is_flow_node(candidate_node) and (not is_event_node(candidate_node)):
                    fallback = candidate_node
                    break
            if fallback is None:
                fallback = env.current_event_node
            effective_prev = fallback

        _connect_prev_to_new(
            effective_prev,
            branch_node,
            edges,
            suppress_prev_connection,
        )

        return nodes, edges, branch_last_nodes if branch_last_nodes else None

    return nodes, edges, prev_flow_node


def handle_match_statement(
    stmt: ast.Match,
    prev_flow_node: Optional[
        Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]
    ],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,
    suppress_prev_connection: bool = False,
) -> Tuple[
    List[NodeModel],
    List[EdgeModel],
    Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
]:
    """处理普通 match 语句并生成多分支节点。"""
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    (
        branch_node,
        branch_nodes,
        branch_edges,
        branch_last_nodes,
    ) = create_multi_branch_node(
        stmt,
        prev_flow_node,
        graph_model,
        env,
        ctx,
        validators,
        parse_method_body_func,
    )
    if branch_node:
        nodes.append(branch_node)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)
        _connect_prev_to_new(
            prev_flow_node,
            branch_node,
            edges,
            suppress_prev_connection,
        )
        return nodes, edges, branch_last_nodes if branch_last_nodes else None

    return nodes, edges, prev_flow_node


def handle_match_over_composite_call(
    stmt: ast.Match,
    prev_flow_node: Optional[
        Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]
    ],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,
    suppress_prev_connection: bool = False,
) -> Tuple[
    bool,
    List[NodeModel],
    List[EdgeModel],
    Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
]:
    """处理形如 `match self.<复合实例>.<入口方法>(...)` 的语句。

    语义约定：
    - subject 必须是复合节点实例方法调用（create_composite_node_from_instance_call 可识别的形式）；
    - case 分支使用字符串字面量表示要连接的流程出口名称：
        match self.复合.入口(...):
            case "出口A":
                ...  # 从复合节点的流程出口“出口A”流出后要执行的逻辑
            case "出口B":
                ...
            case _:
                ...  # 可选：当复合节点有名为“默认”的流程出口时，`_` 映射到“默认”出口
    - 本函数仅在成功识别为复合节点调用时返回 handled=True；否则保持兼容旧逻辑，交由 handle_match_statement 处理。
    """
    # 仅处理 subject 为函数调用的情况
    subject_expr = stmt.subject
    if not isinstance(subject_expr, ast.Call):
        return False, [], [], prev_flow_node

    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    # 先展开参数中的嵌套节点（与普通调用保持一致）
    (
        nested_nodes,
        nested_edges,
        param_node_map,
    ) = extract_nested_nodes(subject_expr, ctx, validators, env)
    nodes.extend(nested_nodes)
    edges.extend(nested_edges)

    # 再尝试将 subject 识别为复合节点实例方法调用
    composite_node = create_composite_node_from_instance_call(
        subject_expr,
        ctx.node_library,
        env,
    )
    if not composite_node or not is_flow_node(composite_node):
        # 非复合节点调用：回退到默认 match → 多分支 逻辑（由调用方决定是否兜底）。
        # 注意：本分支不对 graph_model 与 env 产生副作用。
        return False, [], [], prev_flow_node

    # 收集复合节点的所有流程输出端口名称（在决定“接管 match”之前只做只读查询）
    flow_output_names: List[str] = _collect_composite_flow_outputs(
        composite_node,
        ctx,
    )
    if not flow_output_names:
        # 复合节点没有任何流程出口，无法作为“多分支控制点”使用，由上层决定是否降级处理。
        return False, [], [], prev_flow_node

    # 经过上面的检查后，确认当前 match 可以安全地由复合节点接管，
    # 这时才对 graph_model/env/nodes/edges 产生实际修改。
    nodes.append(composite_node)
    env.node_sequence.append(composite_node)

    # 将上一条流程连接到复合节点（除非显式要求抑制）
    _connect_prev_to_new(
        prev_flow_node,
        composite_node,
        edges,
        suppress_prev_connection,
    )

    # 为复合节点补充数据入边（位置/关键字参数与嵌套节点调用保持一致）
    data_edges = create_data_edges_for_node_enhanced(
        composite_node,
        subject_expr,
        param_node_map,
        ctx.node_library,
        ctx.node_name_index,
        env,
    )
    edges.extend(data_edges)

    # 建立 case 索引 → 流程出口名 映射
    case_index_to_port: Dict[int, str] = {}
    has_any_valid_case = False

    for index, case in enumerate(stmt.cases):
        raw_value = extract_case_value(case.pattern)

        # 字符串字面量：视为显式流程出口名
        if isinstance(raw_value, str) and raw_value != "_":
            label_text = raw_value.strip()
            if not label_text:
                continue
            if label_text not in flow_output_names:
                line_no = getattr(case, "lineno", getattr(stmt, "lineno", "?"))
                validators.warn(
                    f"行{line_no}: match 复合节点调用的 case \"{label_text}\" 未找到同名流程出口，"
                    f"可用的流程出口包括：{', '.join(flow_output_names)}"
                )
                continue
            case_index_to_port[index] = label_text
            has_any_valid_case = True

        # `_`：仅当存在名为“默认”的流程出口时视为默认分支
        elif raw_value == "_" or raw_value is None:
            if "默认" not in flow_output_names:
                line_no = getattr(case, "lineno", getattr(stmt, "lineno", "?"))
                validators.warn(
                    f"行{line_no}: case _ 用于 match 复合节点调用时，仅当复合节点存在名为“默认”的流程出口时才生效；"
                    f"当前可用的流程出口包括：{', '.join(flow_output_names)}"
                )
                continue
            case_index_to_port[index] = "默认"
            has_any_valid_case = True

        else:
            line_no = getattr(case, "lineno", getattr(stmt, "lineno", "?"))
            validators.warn(
                "行"
                + str(line_no)
                + ": match 复合节点调用仅支持字符串字面量或 '_' 作为分支标签；当前分支将被忽略。"
            )

    if not has_any_valid_case:
        # 所有 case 要么未能解析，要么标签与任何流程出口都不匹配，回退默认逻辑
        return False, [], [], prev_flow_node

    branch_last_nodes: List[NodeModel] = []

    # 逐个 case 构建分支体，并从对应流程出口连接到分支体的第一个流程节点
    for index, case in enumerate(stmt.cases):
        port_name = case_index_to_port.get(index)
        if not port_name:
            # 未能映射到流程出口的分支：其内部节点仍会被解析，但没有来自复合节点的流程边
            snapshot_unmapped = env.snapshot()
            case_nodes, case_edges = parse_method_body_func(
                case.body,
                None,
                graph_model,
                False,
                env,
                ctx,
                validators,
            )
            nodes.extend(case_nodes)
            edges.extend(case_edges)
            env.restore(snapshot_unmapped)
            continue

        snapshot = env.snapshot()
        case_nodes, case_edges = parse_method_body_func(
            case.body,
            None,
            graph_model,
            False,
            env,
            ctx,
            validators,
        )
        nodes.extend(case_nodes)
        edges.extend(case_edges)

        if case_nodes:
            first_flow = find_first_flow_node(case_nodes)
            if first_flow and (not is_event_node(first_flow)):
                # 从指定的流程出口连接到分支体的第一个流程节点
                connect_sources_to_target(
                    (composite_node, port_name),
                    first_flow,
                    edges,
                )

            last_flow = find_last_flow_node(case_nodes)
            has_ret = block_has_return(case.body)
            if last_flow and (not has_ret):
                branch_last_nodes.append(last_flow)

        env.restore(snapshot)

    # 若存在至少一个有效 case，则视为已处理该 match 语句
    return True, nodes, edges, branch_last_nodes if branch_last_nodes else None


def handle_for_loop(
    stmt: ast.For,
    prev_flow_node: Optional[
        Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]
    ],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,
    suppress_prev_connection: bool = False,
) -> Tuple[List[NodeModel], List[EdgeModel], Optional[NodeModel]]:
    """处理 for 语句并生成循环节点及其子图。"""
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []

    is_range_loop, loop_var, iter_var = analyze_for_loop(stmt)
    if is_range_loop:
        loop_node, loop_nodes, loop_edges = create_finite_loop_node(
            stmt,
            prev_flow_node,
            loop_var,
            graph_model,
            env,
            ctx,
            validators,
            parse_method_body_func,
        )
    else:
        loop_node, loop_nodes, loop_edges = create_list_iteration_loop_node(
            stmt,
            prev_flow_node,
            loop_var,
            iter_var,
            graph_model,
            env,
            ctx,
            validators,
            parse_method_body_func,
        )

    if loop_node:
        nodes.append(loop_node)
        nodes.extend(loop_nodes)
        edges.extend(loop_edges)
        _connect_prev_to_new(
            prev_flow_node,
            loop_node,
            edges,
            suppress_prev_connection,
        )
        return nodes, edges, loop_node

    return nodes, edges, prev_flow_node



