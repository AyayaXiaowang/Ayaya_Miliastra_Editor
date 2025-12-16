from __future__ import annotations

import ast
import uuid
from typing import Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, EdgeModel

from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from .flow_utils import (
    pick_default_flow_output_port,
    register_output_variables,
    materialize_call_node,
    handle_alias_assignment,
    warn_literal_assignment,
)
from .local_var_builder import (
    should_model_as_local_var,
    build_local_var_nodes,
)
from .statement_flow_builder import (
    handle_if_statement,
    handle_match_statement,
    handle_match_over_composite_call,
    handle_for_loop,
)


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


from dataclasses import dataclass
from typing import Set


@dataclass
class VariableAnalysisResult:
    """变量分析结果"""
    assignment_counts: Dict[str, int]  # 赋值次数
    assigned_in_branch: Set[str]  # 在分支结构内被赋值的变量
    used_after_branch: Set[str]  # 在分支结构后被使用的变量


def _collect_names(target: ast.expr) -> List[str]:
    """收集赋值目标中的所有变量名"""
    if isinstance(target, ast.Name):
        return [target.id]
    elif isinstance(target, ast.Tuple):
        names = []
        for elt in target.elts:
            names.extend(_collect_names(elt))
        return names
    return []


def _collect_used_names(node: ast.AST) -> Set[str]:
    """收集表达式中被读取的所有变量名（Load 上下文）"""
    used: Set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            used.add(sub.id)
    return used


def _analyze_variable_assignments(body: List[ast.stmt]) -> VariableAnalysisResult:
    """预先扫描方法体，分析变量的赋值和使用情况。
    
    收集信息：
    1. assignment_counts: 每个变量的赋值次数
    2. assigned_in_branch: 在分支结构（if/match）内被赋值的变量
    3. used_after_branch: 在分支结构后被使用的变量
    
    判断逻辑的关键：只有当变量在分支内被赋值，且在分支后被使用时，
    才真正需要局部变量来合并不同分支的数据流。
    """
    counts: Dict[str, int] = {}
    assigned_in_branch: Set[str] = set()
    used_after_branch: Set[str] = set()

    def _scan_assignments(stmts: List[ast.stmt], in_branch: bool = False) -> None:
        """扫描赋值语句，统计赋值次数并标记分支内赋值"""
        for stmt in stmts:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    for name in _collect_names(target):
                        counts[name] = counts.get(name, 0) + 1
                        if in_branch:
                            assigned_in_branch.add(name)
            elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                for name in _collect_names(stmt.target):
                    counts[name] = counts.get(name, 0) + 1
                    if in_branch:
                        assigned_in_branch.add(name)
            elif isinstance(stmt, ast.If):
                # if/else 内部是分支结构
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.For):
                # for 循环体内也视为分支（因为可能执行 0 次或多次）
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.While):
                _scan_assignments(stmt.body, in_branch=True)
                _scan_assignments(stmt.orelse, in_branch=True)
            elif isinstance(stmt, ast.Match):
                # match/case 各分支
                for case in stmt.cases:
                    _scan_assignments(case.body, in_branch=True)

    def _scan_usage_after_branch(stmts: List[ast.stmt]) -> None:
        """扫描分支结构后的变量使用"""
        pending_branch_vars: Set[str] = set()  # 当前分支结构内赋值的变量
        
        for idx, stmt in enumerate(stmts):
            if isinstance(stmt, (ast.If, ast.Match, ast.For, ast.While)):
                # 收集该分支结构内赋值的变量
                branch_assigned: Set[str] = set()
                if isinstance(stmt, ast.If):
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            branch_assigned.add(sub.id)
                elif isinstance(stmt, ast.Match):
                    for case in stmt.cases:
                        for sub in ast.walk(case):
                            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                                branch_assigned.add(sub.id)
                elif isinstance(stmt, (ast.For, ast.While)):
                    for sub in ast.walk(stmt):
                        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                            branch_assigned.add(sub.id)
                
                pending_branch_vars.update(branch_assigned)
                
                # 检查后续语句中是否使用了这些变量
                for later_stmt in stmts[idx + 1:]:
                    used_names = _collect_used_names(later_stmt)
                    for name in pending_branch_vars:
                        if name in used_names:
                            used_after_branch.add(name)
                
                # 递归处理嵌套结构
                if isinstance(stmt, ast.If):
                    _scan_usage_after_branch(stmt.body)
                    _scan_usage_after_branch(stmt.orelse)
                elif isinstance(stmt, ast.Match):
                    for case in stmt.cases:
                        _scan_usage_after_branch(case.body)
                elif isinstance(stmt, (ast.For, ast.While)):
                    _scan_usage_after_branch(stmt.body)
                    _scan_usage_after_branch(stmt.orelse)

    _scan_assignments(body, in_branch=False)
    _scan_usage_after_branch(body)

    return VariableAnalysisResult(
        assignment_counts=counts,
        assigned_in_branch=assigned_in_branch,
        used_after_branch=used_after_branch,
    )


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
    # 预先扫描方法体，分析变量的赋值和使用情况
    # 更精确的判断：只有在分支内赋值且分支后使用的变量才需要局部变量
    if not env.assignment_counts:
        analysis_result = _analyze_variable_assignments(body)
        env.set_assignment_counts(analysis_result.assignment_counts)
        env.set_branch_assignment_info(
            analysis_result.assigned_in_branch,
            analysis_result.used_after_branch,
        )

    # 预扫描方法体内“命名常量”赋值：供后续节点调用参数引用时回填为 input_constants。
    # 约定：仅收集 target 为 Name 且右值可静态提取的赋值（Assign / AnnAssign）。
    env.local_const_values.clear()
    method_module = ast.Module(body=list(body or []), type_ignores=[])
    for stmt in ast.walk(method_module):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            value_expr = getattr(stmt, "value", None)
            if not isinstance(value_expr, ast.expr):
                continue
            const_val = extract_constant_value(value_expr)
            if const_val is NOT_EXTRACTABLE:
                continue
            env.set_local_constant(targets[0].id, const_val)
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            value_expr = getattr(stmt, "value", None)
            if not isinstance(target, ast.Name) or value_expr is None:
                continue
            if not isinstance(value_expr, ast.expr):
                continue
            const_val = extract_constant_value(value_expr)
            if const_val is NOT_EXTRACTABLE:
                continue
            env.set_local_constant(target.id, const_val)

    # 第二遍：允许“命名常量引用命名常量”（例如 B = A），只要 A 已在第一遍收集到。
    for stmt in ast.walk(method_module):
        if isinstance(stmt, ast.Assign):
            targets = list(getattr(stmt, "targets", []) or [])
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            target_name = str(targets[0].id or "").strip()
            if not target_name or env.has_local_constant(target_name):
                continue
            value_expr = getattr(stmt, "value", None)
            if isinstance(value_expr, ast.Name) and env.has_local_constant(value_expr.id):
                env.set_local_constant(target_name, env.get_local_constant(value_expr.id))
        elif isinstance(stmt, ast.AnnAssign):
            target = getattr(stmt, "target", None)
            value_expr = getattr(stmt, "value", None)
            if not isinstance(target, ast.Name) or value_expr is None:
                continue
            target_name = str(target.id or "").strip()
            if not target_name or env.has_local_constant(target_name):
                continue
            if isinstance(value_expr, ast.Name) and env.has_local_constant(value_expr.id):
                env.set_local_constant(target_name, env.get_local_constant(value_expr.id))

    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]] = event_node
    need_suppress_once = bool(suppress_initial_flow_edge)
    branch_context = isinstance(prev_flow_node, tuple) or (
        isinstance(prev_flow_node, list) and any(isinstance(x, tuple) for x in prev_flow_node)
    )

    for stmt_index, stmt in enumerate(body):
        # 表达式语句：节点调用
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            result = materialize_call_node(
                call_expr=stmt.value,
                stmt=stmt,
                prev_flow_node=prev_flow_node,
                need_suppress_once=need_suppress_once,
                graph_model=graph_model,
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

            # 若是单变量赋值（含调用/常量），优先用“获取/设置局部变量”建模
            primary_target = stmt.targets[0] if stmt.targets else None
            if isinstance(primary_target, ast.Name) and should_model_as_local_var(
                primary_target.id,
                stmt.value,
                body[stmt_index + 1:],
                env,
            ):
                handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
                    var_name=primary_target.id,
                    value_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    env=env,
                    ctx=ctx,
                    validators=validators,
                    graph_model=graph_model,
                )
                if handled:
                    nodes.extend(lv_nodes)
                    edges.extend(lv_edges)
                    continue
            
            # 处理调用节点赋值
            if isinstance(stmt.value, ast.Call):
                # 提取赋值变量名（用于后续变量环境注册）
                assigned_names: List[str] = []
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        assigned_names.append(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned_names.append(elt.id)
                
                # 说明：
                # - 这里显式关闭“未使用纯数据节点的自动剔除”（check_unused=False），
                #   原有逻辑仅在当前语句块内检查 assigned_names 是否在后续语句中被读取，
                #   在分支体/循环体等嵌套结构中，像
                #       if 条件:
                #           值1 = 获取列表对应值(...)
                #       ...
                #       结果列表 = 拼装列表(..., 值1, ...)
                #   这类“在块外部使用局部变量”的场景会被误判为未使用，
                #   从而错误地跳过生成对应的纯数据节点。
                # - 禁用该优化后，赋值右值为调用的语句始终会生成节点，
                #   再由 register_output_variables 把变量名绑定到节点输出端口，
                #   保证后续无论在当前块内还是块外引用变量，图结构都完整可追踪。
                result = materialize_call_node(
                    call_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    graph_model=graph_model,
                    ctx=ctx,
                    env=env,
                    validators=validators,
                    check_unused=False,
                    later_stmts=None,
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
            # 纯类型标注（无右值）仅用于阅读/类型提示，不应建模为任何节点。
            # 例如：`方向X: "浮点数"` 这类语句在旧逻辑中会被误判为“需要局部变量建模”，
            # 从而生成孤立的【获取局部变量】节点（无连线、无数据）。
            if stmt.value is None:
                continue
            # 处理纯别名赋值
            if handle_alias_assignment(stmt.value, stmt.target, env):
                continue

            # 单变量注解赋值优先尝试局部变量建模
            if isinstance(stmt.target, ast.Name) and should_model_as_local_var(
                stmt.target.id,
                stmt.value,
                body[stmt_index + 1:],
                env,
            ):
                handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
                    var_name=stmt.target.id,
                    value_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    env=env,
                    ctx=ctx,
                    validators=validators,
                    graph_model=graph_model,
                )
                if handled:
                    nodes.extend(lv_nodes)
                    edges.extend(lv_edges)
                    continue
            
            # 处理调用节点赋值
            if isinstance(stmt.value, ast.Call):
                # 提取赋值变量名（用于后续变量环境注册）
                assigned_names_ann: List[str] = []
                if isinstance(stmt.target, ast.Name):
                    assigned_names_ann.append(stmt.target.id)
                
                # 同上，关闭对带类型注解赋值的“未使用纯数据节点剔除”：
                # 这类变量同样可能在当前语句块之外被引用（例如在 if 分支后使用），
                # 若仅在局部块内做使用检查，会导致必要的纯数据节点被错误跳过。
                result = materialize_call_node(
                    call_expr=stmt.value,
                    stmt=stmt,
                    prev_flow_node=prev_flow_node,
                    need_suppress_once=need_suppress_once,
                    graph_model=graph_model,
                    ctx=ctx,
                    env=env,
                    validators=validators,
                    check_unused=False,
                    later_stmts=None,
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
            
            # 非调用的注解赋值若未在上方命中局部变量建模规则，则目前保持空操作

        # If
        elif isinstance(stmt, ast.If):
            if_nodes, if_edges, prev_flow_node = handle_if_statement(
                stmt,
                prev_flow_node,
                graph_model,
                env,
                ctx,
                validators,
                parse_method_body,
                suppress_prev_connection=need_suppress_once,
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
                (
                    handled,
                    match_nodes,
                    match_edges,
                    prev_flow_node,
                ) = handle_match_over_composite_call(
                    stmt,
                    prev_flow_node,
                    graph_model,
                    env,
                    ctx,
                    validators,
                    parse_method_body,
                    suppress_prev_connection=need_suppress_once,
                )
                # 若未能成功处理（例如 case 标签与复合节点流程出口均不匹配），
                # 此处不再退回到【多分支】节点，只依赖校验/日志暴露问题，避免在 UI 中
                # 误把“复合节点多出口”解析成普通多分支节点。
                if not handled:
                    match_nodes = []
                    match_edges = []
            else:
                (
                    match_nodes,
                    match_edges,
                    prev_flow_node,
                ) = handle_match_statement(
                    stmt,
                    prev_flow_node,
                    graph_model,
                    env,
                    ctx,
                    validators,
                    parse_method_body,
                    suppress_prev_connection=need_suppress_once,
                )

            if need_suppress_once:
                need_suppress_once = False
            nodes.extend(match_nodes)
            edges.extend(match_edges)

        # For
        elif isinstance(stmt, ast.For):
            for_nodes, for_edges, prev_flow_node = handle_for_loop(
                stmt,
                prev_flow_node,
                graph_model,
                env,
                ctx,
                validators,
                parse_method_body,
                suppress_prev_connection=need_suppress_once,
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
                """连接 break 语句到循环节点的【跳出循环】端口。

                默认出口选择策略统一委托给 edge_router.pick_default_flow_output_port，
                保证与通用流程连线逻辑保持一致。
                """
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



