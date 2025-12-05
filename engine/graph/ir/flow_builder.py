from __future__ import annotations

import ast
import uuid
from typing import Any, Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, PortModel, EdgeModel
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
from .flow_utils import (
    pick_default_flow_output_port,
    register_output_variables,
    materialize_call_node,
    handle_alias_assignment,
    warn_literal_assignment,
)
from .composite_builder import create_composite_node_from_instance_call


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


def _collect_composite_flow_outputs(composite_node: NodeModel, ctx: FactoryContext) -> List[str]:
    """
    收集复合节点的所有流程输出端口名称。

    说明：
    - 优先使用节点库中的端口类型定义（NodeDef.output_types），确保像“分支为0/分支为1”这类
      不含“流程”关键字的端口也能被正确识别为流程出口；
    - 当无法在节点库中找到对应 NodeDef 时，回退到基于端口名的启发式判断。

    Args:
        composite_node: 由 create_composite_node_from_instance_call 创建的复合节点实例
        ctx: IR 工厂上下文，提供节点库
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


def handle_match_over_composite_call(
    stmt: ast.Match,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
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
    nested_nodes, nested_edges, param_node_map = extract_nested_nodes(subject_expr, ctx, validators, env)
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
    flow_output_names: List[str] = _collect_composite_flow_outputs(composite_node, ctx)
    if not flow_output_names:
        # 复合节点没有任何流程出口，无法作为“多分支控制点”使用，由上层决定是否降级处理。
        return False, [], [], prev_flow_node

    # 经过上面的检查后，确认当前 match 可以安全地由复合节点接管，
    # 这时才对 graph_model/env/nodes/edges 产生实际修改。
    nodes.append(composite_node)
    env.node_sequence.append(composite_node)

    # 将上一条流程连接到复合节点（除非显式要求抑制）
    _connect_prev_to_new(prev_flow_node, composite_node, edges, suppress_prev_connection)

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
                f"行{line_no}: match 复合节点调用仅支持字符串字面量或 '_' 作为分支标签；"
                f"当前分支将被忽略。"
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
            case_nodes, case_edges = parse_method_body(
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
        case_nodes, case_edges = parse_method_body(
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
                connect_sources_to_target((composite_node, port_name), first_flow, edges)

            last_flow = find_last_flow_node(case_nodes)
            has_ret = block_has_return(case.body)
            if last_flow and (not has_ret):
                branch_last_nodes.append(last_flow)

        env.restore(snapshot)

    # 若存在至少一个有效 case，则视为已处理该 match 语句
    return True, nodes, edges, branch_last_nodes if branch_last_nodes else None


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
            subject_expr = stmt.subject
            # 仅当 subject 明确是 self.<实例>.<入口方法>(...) 这种模式时，
            # 才尝试作为“复合节点多出口控制点”解析；否则一律走传统 match → 多分支 节点逻辑。
            is_self_composite_call = (
                isinstance(subject_expr, ast.Call)
                and isinstance(subject_expr.func, ast.Attribute)
                and isinstance(subject_expr.func.value, ast.Attribute)
                and isinstance(subject_expr.func.value.value, ast.Name)
                and subject_expr.func.value.value.id == "self"
            )

            if is_self_composite_call:
                handled, match_nodes, match_edges, prev_flow_node = handle_match_over_composite_call(
                    stmt,
                    prev_flow_node,
                    graph_model,
                    env,
                    ctx,
                    validators,
                    suppress_prev_connection=need_suppress_once,
                )
                # 若未能成功处理（例如 case 标签与复合节点流程出口均不匹配），
                # 此处不再退回到【多分支】节点，只依赖校验/日志暴露问题，避免在 UI 中
                # 误把“复合节点多出口”解析成普通多分支节点。
                if not handled:
                    match_nodes = []
                    match_edges = []
            else:
                match_nodes, match_edges, prev_flow_node = handle_match_statement(
                    stmt,
                    prev_flow_node,
                    graph_model,
                    env,
                    ctx,
                    validators,
                    suppress_prev_connection=need_suppress_once,
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



