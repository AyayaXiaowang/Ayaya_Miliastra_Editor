"""分支节点构建器

提供双分支（if-else）和多分支（match-case）的IR构建逻辑。
"""
from __future__ import annotations

import ast
import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, PortModel, EdgeModel
from .var_env import VarEnv
from .validators import Validators
from .node_factory import (
    FactoryContext,
    create_node_from_call,
    extract_nested_nodes,
    extract_constant_value,
)
from .edge_router import (
    is_flow_node,
    is_event_node,
    create_data_edges_for_node_enhanced,
)


def extract_condition_variable(test_node: ast.expr) -> Optional[str]:
    """从条件表达式中提取变量名"""
    if isinstance(test_node, ast.Name):
        return test_node.id
    if isinstance(test_node, ast.UnaryOp) and isinstance(test_node.op, ast.Not):
        return extract_condition_variable(test_node.operand)
    if isinstance(test_node, ast.Compare):
        if isinstance(test_node.left, ast.Name):
            return test_node.left.id
    return None


def extract_match_subject(subject: ast.expr) -> Optional[str]:
    """从match主题中提取变量名"""
    if isinstance(subject, ast.Name):
        return subject.id
    return None


def is_pass_only_block(body: List[ast.stmt]) -> bool:
    """判断语句块是否只包含 pass（视为“空分支体”）

    设计约定：
    - 用于 match/case 等分支结构中，将『case X: pass』视为显式写出的“空体”；
    - 这类分支在控制流图中不会生成新的节点，但对应的分支出口仍然可以继续向后接续。
    """
    if not body:
        # match/case 在语法上通常不会出现完全空体，这里出于健壮性仍按“空体”处理
        return True
    return all(isinstance(stmt, ast.Pass) for stmt in body)


def extract_case_value(pattern: ast.pattern) -> Any:
    """从case模式中提取常量值"""
    if isinstance(pattern, ast.MatchValue):
        return extract_constant_value(pattern.value)
    if isinstance(pattern, ast.MatchAs):
        if pattern.name is None:
            return "_"
        return pattern.name
    return None


def _collect_assigned_names(body: List[ast.stmt]) -> Set[str]:
    names: Set[str] = set()
    for stmt in body:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                if sub.id:
                    names.add(sub.id)
    return names


def block_has_return(body: List[ast.stmt]) -> bool:
    """检查语句块是否包含return"""
    for s in body:
        for sub in ast.walk(s):
            if isinstance(sub, ast.Return):
                return True
    return False


def find_first_flow_node(nodes: List[NodeModel]) -> Optional[NodeModel]:
    """查找列表中第一个流程节点"""
    for node in nodes:
        if is_flow_node(node):
            return node
    return None


def find_last_flow_node(nodes: List[NodeModel]) -> Optional[NodeModel]:
    """查找列表中最后一个流程节点"""
    last: Optional[NodeModel] = None
    for node in nodes:
        if is_flow_node(node):
            last = node
    return last


def create_dual_branch_node(
    stmt: ast.If,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,  # 避免循环导入
) -> Tuple[Optional[NodeModel], List[NodeModel], List[EdgeModel], List[Union[NodeModel, Tuple[NodeModel, str]]]]:
    """创建双分支节点（if-else）
    
    Args:
        stmt: if语句AST节点
        prev_flow_node: 前驱流程节点
        graph_model: 图模型
        env: 变量环境
        ctx: 工厂上下文
        validators: 验证器
        parse_method_body_func: 解析方法体的函数（避免循环导入）
        
    Returns:
        (分支节点, 所有子节点, 所有边, 分支出口节点列表)
    """
    branch_nodes: List[NodeModel] = []
    branch_edges: List[EdgeModel] = []
    branch_last_nodes: List[Union[NodeModel, Tuple[NodeModel, str]]] = []

    condition_var = extract_condition_variable(stmt.test)

    branch_node_id = f"node_双分支_{uuid.uuid4().hex[:8]}"
    input_ports = [PortModel(name="流程入", is_input=True), PortModel(name="条件", is_input=True)]
    output_ports = [PortModel(name="是", is_input=False), PortModel(name="否", is_input=False)]
    branch_node = NodeModel(
        id=branch_node_id,
        title="双分支",
        category="流程控制节点",
        pos=(0.0, 0.0),
        inputs=input_ports,
        outputs=output_ports,
    )
    # 源码行号：来自 if 语句本身
    branch_node.source_lineno = getattr(stmt, 'lineno', 0)
    branch_node.source_end_lineno = getattr(stmt, 'end_lineno', getattr(stmt, 'lineno', 0))

    # 条件输入连接
    if condition_var:
        source = env.get_variable(condition_var)
        if source:
            src_node_id, src_port = source
            branch_edges.append(EdgeModel(
                id=str(uuid.uuid4()),
                src_node=src_node_id,
                src_port=src_port,
                dst_node=branch_node_id,
                dst_port="条件",
            ))
    elif isinstance(stmt.test, ast.Call):
        nested_nodes, nested_edges, param_node_map = extract_nested_nodes(stmt.test, ctx, validators, env)
        branch_nodes.extend(nested_nodes)
        branch_edges.extend(nested_edges)
        cond_node = create_node_from_call(stmt.test, ctx, validators)
        if cond_node:
            branch_nodes.append(cond_node)
            data_edges = create_data_edges_for_node_enhanced(cond_node, stmt.test, param_node_map, ctx.node_library, ctx.node_name_index, env)
            branch_edges.extend(data_edges)
            cond_out: Optional[str] = None
            for p in cond_node.outputs:
                if p.name.find('流程') == -1:
                    cond_out = p.name
                    break
            if cond_out:
                branch_edges.append(EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=cond_node.id,
                    src_port=cond_out,
                    dst_node=branch_node_id,
                    dst_port="条件",
                ))

    # 是分支体
    if stmt.body:
        snapshot = env.snapshot()
        assigned_true = _collect_assigned_names(stmt.body)
        assigned_false = _collect_assigned_names(stmt.orelse) if stmt.orelse else set()
        # 只有在多个分支中都被赋值的变量才需要标记为多分支赋值候选，
        # 避免为只在单一分支中赋值并使用的变量创建不必要的局部变量节点
        combined_assigned = assigned_true & assigned_false
        env.push_multi_assign(combined_assigned)
        true_nodes, true_edges = parse_method_body_func(stmt.body, (branch_node, "是"), graph_model, False, env, ctx, validators)
        env.pop_multi_assign()
        branch_nodes.extend(true_nodes)
        branch_edges.extend(true_edges)

        # 检测该分支是否包含 break（仅当处于循环体内时才有意义）
        has_break_true: bool = False
        if getattr(env, "loop_stack", None):
            loop_node_obj = env.loop_stack[-1] if env.loop_stack else None
            if loop_node_obj:
                loop_id = getattr(loop_node_obj, "id", "")
                for _e in true_edges:
                    if _e.dst_node == loop_id and _e.dst_port == "跳出循环":
                        has_break_true = True
                        break

        if true_nodes:
            last_flow = find_last_flow_node(true_nodes)
            has_ret = block_has_return(stmt.body)
            if last_flow and (not has_ret):
                branch_last_nodes.append(last_flow)
            elif (not last_flow) and (not has_ret) and (not has_break_true):
                branch_last_nodes.append((branch_node, "是"))
        env.restore(snapshot)
    else:
        # 空分支体：仅当未出现 break 时才允许从“是”继续向后接续
        has_break_true = False
        # 空体不可能产出 true_edges；但为了一致性，仍按照“未检测到break”处理
        if not block_has_return(stmt.body) and (not has_break_true):
            branch_last_nodes.append((branch_node, "是"))

    # 否分支体
    if stmt.orelse:
        snapshot = env.snapshot()
        assigned_true = _collect_assigned_names(stmt.body) if stmt.body else set()
        assigned_false = _collect_assigned_names(stmt.orelse)
        # 只有在多个分支中都被赋值的变量才需要标记为多分支赋值候选
        combined_assigned = assigned_true & assigned_false
        env.push_multi_assign(combined_assigned)
        false_nodes, false_edges = parse_method_body_func(stmt.orelse, (branch_node, "否"), graph_model, False, env, ctx, validators)
        env.pop_multi_assign()
        branch_nodes.extend(false_nodes)
        branch_edges.extend(false_edges)

        # 检测该分支是否包含 break（仅当处于循环体内时才有意义）
        has_break_false: bool = False
        if getattr(env, "loop_stack", None):
            loop_node_obj = env.loop_stack[-1] if env.loop_stack else None
            if loop_node_obj:
                loop_id = getattr(loop_node_obj, "id", "")
                for _e in false_edges:
                    if _e.dst_node == loop_id and _e.dst_port == "跳出循环":
                        has_break_false = True
                        break

        if false_nodes:
            last_flow = find_last_flow_node(false_nodes)
            has_ret2 = block_has_return(stmt.orelse)
            if last_flow and (not has_ret2):
                branch_last_nodes.append(last_flow)
            elif (not last_flow) and (not has_ret2) and (not has_break_false):
                branch_last_nodes.append((branch_node, "否"))
        env.restore(snapshot)
    else:
        # 空分支体：允许从“否”接续（该分支无 break）
        branch_last_nodes.append((branch_node, "否"))

    return branch_node, branch_nodes, branch_edges, branch_last_nodes


def create_multi_branch_node(
    stmt: ast.Match,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    parse_method_body_func,  # 避免循环导入
) -> Tuple[
    Optional[NodeModel],
    List[NodeModel],
    List[EdgeModel],
    List[Union[NodeModel, Tuple[NodeModel, str]]],
]:
    """创建多分支节点（match-case）
    
    Args:
        stmt: match语句AST节点
        prev_flow_node: 前驱流程节点
        graph_model: 图模型
        env: 变量环境
        ctx: 工厂上下文
        validators: 验证器
        parse_method_body_func: 解析方法体的函数（避免循环导入）
        
    Returns:
        (分支节点, 所有子节点, 所有边, 分支出口节点列表)
    """
    branch_nodes: List[NodeModel] = []
    branch_edges: List[EdgeModel] = []
    # 分支出口集合：
    # - 对于非空分支体：记录该分支体中的“最后一个流程节点”；
    # - 对于仅包含 pass 的分支体：记录 (多分支节点, 对应分支端口名)，表示从该端口可直接接续到后续语句。
    branch_last_nodes: List[Union[NodeModel, Tuple[NodeModel, str]]] = []

    control_var = extract_match_subject(stmt.subject)
    branch_node_id = f"node_多分支_{uuid.uuid4().hex[:8]}"

    input_ports = [
        PortModel(name="流程入", is_input=True),
        PortModel(name="控制表达式", is_input=True),
    ]

    output_ports = [PortModel(name="默认", is_input=False)]
    case_values: List[Any] = []
    for case in stmt.cases:
        case_value = extract_case_value(case.pattern)
        if case_value is not None and case_value != "_":
            case_values.append(case_value)
            output_ports.append(PortModel(name=str(case_value), is_input=False))

    # 校验（仅记录，不中断）
    if case_values:
        found_int = any(isinstance(v, int) for v in case_values)
        found_str = any(isinstance(v, str) for v in case_values)
        has_unsupported = any((not isinstance(v, int)) and (not isinstance(v, str)) for v in case_values)
        if has_unsupported:
            validators.warn("多分支仅支持整数或字符串作为分支值；请将 case 常量改为整数或字符串")
        if found_int and found_str:
            validators.warn("多分支的所有 case 值必须同为整数或同为字符串，禁止混用")

    branch_node = NodeModel(
        id=branch_node_id,
        title="多分支",
        category="流程控制节点",
        pos=(0.0, 0.0),
        inputs=input_ports,
        outputs=output_ports,
    )
    # 源码行号：来自 match 语句本身
    branch_node.source_lineno = getattr(stmt, 'lineno', 0)
    branch_node.source_end_lineno = getattr(stmt, 'end_lineno', getattr(stmt, 'lineno', 0))

    if control_var:
        src = env.get_variable(control_var)
        if src:
            src_node_id, src_port = src
            branch_edges.append(EdgeModel(
                id=str(uuid.uuid4()),
                src_node=src_node_id,
                src_port=src_port,
                dst_node=branch_node_id,
                dst_port="控制表达式",
            ))

    # 只有在多个分支中都被赋值的变量才需要标记为多分支赋值候选，
    # 用交集来确定哪些变量在所有分支中都被赋值
    all_case_assigned = [_collect_assigned_names(case.body) for case in stmt.cases]
    if len(all_case_assigned) > 1:
        combined_assigned: Set[str] = all_case_assigned[0].copy()
        for other_assigned in all_case_assigned[1:]:
            combined_assigned &= other_assigned
    else:
        combined_assigned = set()

    for case in stmt.cases:
        case_value = extract_case_value(case.pattern)
        branch_port = "默认" if case_value in ("_", None) else str(case_value)
        snapshot = env.snapshot()
        env.push_multi_assign(combined_assigned)
        case_nodes, case_edges = parse_method_body_func(
            case.body,
            None,
            graph_model,
            False,
            env,
            ctx,
            validators,
        )
        env.pop_multi_assign()
        branch_nodes.extend(case_nodes)
        branch_edges.extend(case_edges)

        if case_nodes:
            first_flow = find_first_flow_node(case_nodes)
            if first_flow and (not is_event_node(first_flow)):
                branch_edges.append(
                    EdgeModel(
                        id=str(uuid.uuid4()),
                        src_node=branch_node_id,
                        src_port=branch_port,
                        dst_node=first_flow.id,
                        dst_port="流程入",
                    )
                )
            last_flow = find_last_flow_node(case_nodes)
            has_ret = block_has_return(case.body)
            if last_flow and (not has_ret):
                branch_last_nodes.append(last_flow)
        else:
            # 分支体未生成任何节点：
            # - 若仅包含 pass，则视为“显式空体”，对应的分支端口仍然可以继续向后接续；
            # - 若包含 return 等提前终止语句，则不应继续接续（例如 `case _: return`）。
            if is_pass_only_block(case.body) and (not block_has_return(case.body)):
                branch_last_nodes.append((branch_node, branch_port))

        env.restore(snapshot)

    return branch_node, branch_nodes, branch_edges, branch_last_nodes



