"""局部变量建模工具

负责将简单的赋值语句统一建模为【获取局部变量】/【设置局部变量】节点组合，
以便在图中表达局部状态的持久化与多次更新。
"""
from __future__ import annotations

import ast
from typing import List, Optional, Tuple, Union

from engine.graph.models import NodeModel, EdgeModel

from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext
from .flow_utils import materialize_call_node


LOCAL_HANDLE_PREFIX = "__local_handle__"


def _collect_assignment_targets(
    targets_expr: Union[ast.expr, List[ast.expr]]
) -> List[str]:
    """收集赋值目标中出现的所有变量名"""
    collected_names: List[str] = []

    if isinstance(targets_expr, list):
        for target_expr in targets_expr:
            collected_names.extend(_collect_assignment_targets(target_expr))
        return collected_names

    if isinstance(targets_expr, ast.Name):
        collected_names.append(targets_expr.id)
    elif isinstance(targets_expr, ast.Tuple):
        for element_expr in targets_expr.elts:
            collected_names.extend(_collect_assignment_targets(element_expr))

    return collected_names


def _has_later_assignment(
    variable_name: str,
    remaining_statements: List[ast.stmt],
) -> bool:
    """判断后续语句中是否还会为同名变量赋值"""
    for statement in remaining_statements:
        if isinstance(statement, ast.Assign):
            target_names = _collect_assignment_targets(statement.targets or [])
            if variable_name in target_names:
                return True
        elif isinstance(statement, ast.AnnAssign):
            target_names = _collect_assignment_targets(
                getattr(statement, "target", None)
            )
            if variable_name in target_names:
                return True
    return False


def should_model_as_local_var(
    variable_name: str,
    value_expr: Optional[ast.expr],
    remaining_statements: List[ast.stmt],
    env: VarEnv,
) -> bool:
    """统一判断"当前赋值是否应该建模为局部变量"。

    规则（精确分支交集判断）：
    - 只有在 if-else / match 等互斥分支**都**对同一变量赋值时，才需要局部变量节点
      来合并不同分支的数据流（由 branch_builder 计算交集并标记）；
    - 已存在局部变量句柄时，后续赋值继续复用同一局部变量；
    - 对预声明局部变量（通常由复合节点的数据输出引脚声明）仍保留
      "存在后续赋值则建模为局部变量"的策略；
    - 对只赋值一次的变量（已存在于环境中，且后续没有更多赋值），
      使用直接连线逻辑，不转化为局部变量节点；
    - 非调用右值（常量、表达式）：只有当变量后续还会被赋值时才走局部变量建模，
      否则单次常量赋值直接使用数据节点。
    """
    handle_key = f"{LOCAL_HANDLE_PREFIX}{variable_name}"
    handle_exists = env.get_variable(handle_key) is not None
    var_already_assigned = env.get_variable(variable_name) is not None
    predeclared = env.is_predeclared(variable_name)
    has_future_assignment = _has_later_assignment(variable_name, remaining_statements)
    multi_assign_hint = env.is_multi_assign_candidate(variable_name)

    # 多分支赋值场景：一旦变量被标记为"跨分支赋值候选"（由 branch_builder 计算
    # 的分支交集），当前赋值必须走局部变量建模，以便各分支通过同一局部变量句柄
    # 在合流处共享数据源。
    if multi_assign_hint:
        return True

    # 如果变量已经被赋值过（如通过元组解包或之前的调用），并且后续没有更多赋值，
    # 则不需要转换为局部变量节点，可以直接使用连线逻辑。
    # 这避免了为只使用一次的变量创建多余的【获取局部变量】+【设置局部变量】组合。
    if var_already_assigned and not has_future_assignment:
        return False

    # 已有句柄存在时，继续复用同一局部变量
    if handle_exists:
        return True

    # 预声明局部变量在有后续赋值时需要建模
    if predeclared and has_future_assignment:
        return True

    # 非调用右值（常量、表达式）：只有当后续还会赋值时才需要局部变量，
    # 单次常量赋值直接使用数据节点表示即可。
    if not isinstance(value_expr, ast.Call):
        return has_future_assignment

    # 调用右值：只有当后续还会被赋值时才需要局部变量
    return has_future_assignment


def _ensure_location(node: ast.AST, ref: ast.AST) -> ast.AST:
    """为新建 AST 节点补充位置信息，便于错误行号保持一致。"""
    return ast.copy_location(node, ref)


def build_local_var_nodes(
    *,
    var_name: str,
    value_expr: ast.expr,
    stmt: ast.stmt,
    prev_flow_node: Optional[
        Union[
            NodeModel,
            List[Union[NodeModel, Tuple[NodeModel, str]]],
        ]
    ],
    need_suppress_once: bool,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
) -> Tuple[
    bool,
    List[NodeModel],
    List[EdgeModel],
    Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    bool,
]:
    """将“变量赋值”转换为【获取局部变量】+【设置局部变量】组合。

    规则：
    - 首次遇到变量：生成“获取局部变量”(初始值=value_expr)，建立句柄与值的持久映射。
    - 后续赋值：复用句柄生成“设置局部变量”，保持变量映射指向首次获取节点的“值”端口。
    - 句柄缺失时会自动回退到生成“获取局部变量”节点。
    """
    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []
    new_prev = prev_flow_node
    new_suppress = need_suppress_once
    handle_key = f"{LOCAL_HANDLE_PREFIX}{var_name}"

    predeclared = env.is_predeclared(var_name)
    handle_src = env.get_variable(handle_key)
    value_src = env.get_variable(var_name)

    # 首次：创建获取局部变量节点
    if handle_src is None:
        initial_value_expr = value_expr
        if predeclared:
            initial_value_expr = ast.Constant(value=None)
            initial_value_expr = _ensure_location(
                initial_value_expr, value_expr or stmt
            )

        get_call = ast.Call(
            func=ast.Name(id="获取局部变量", ctx=ast.Load()),
            args=[initial_value_expr],
            keywords=[],
        )
        get_call = _ensure_location(get_call, value_expr or stmt)

        result = materialize_call_node(
            call_expr=get_call,
            stmt=stmt,
            prev_flow_node=new_prev,
            need_suppress_once=new_suppress,
            ctx=ctx,
            env=env,
            validators=validators,
            check_unused=False,
            later_stmts=None,
            assigned_names=[var_name],
        )

        if result.should_skip:
            return False, nodes, edges, new_prev, new_suppress

        if result.node:
            nodes.append(result.node)
            env.node_sequence.append(result.node)
            env.set_variable_persistent(handle_key, result.node.id, "局部变量")
            env.set_variable_persistent(var_name, result.node.id, "值")

        nodes.extend(result.nested_nodes)
        edges.extend(result.edges)

        if result.new_prev_flow_node is not None:
            new_prev = result.new_prev_flow_node
            new_suppress = result.new_suppress_flag

        if not predeclared:
            return True, nodes, edges, new_prev, new_suppress

        handle_src = env.get_variable(handle_key)
        value_src = env.get_variable(var_name)
        if handle_src is None:
            return False, nodes, edges, new_prev, new_suppress

    # 已有句柄：生成设置局部变量节点
    handle_expr = ast.Name(id=handle_key, ctx=ast.Load())
    handle_expr = _ensure_location(handle_expr, stmt)

    set_call = ast.Call(
        func=ast.Name(id="设置局部变量", ctx=ast.Load()),
        args=[],
        keywords=[
            ast.keyword(arg="局部变量", value=handle_expr),
            ast.keyword(arg="值", value=value_expr),
        ],
    )
    set_call = _ensure_location(set_call, value_expr or stmt)

    result = materialize_call_node(
        call_expr=set_call,
        stmt=stmt,
        prev_flow_node=new_prev,
        need_suppress_once=new_suppress,
        ctx=ctx,
        env=env,
        validators=validators,
        check_unused=False,
        later_stmts=None,
        assigned_names=[var_name],
    )

    if result.should_skip:
        return False, nodes, edges, new_prev, new_suppress

    if result.node:
        nodes.append(result.node)
        env.node_sequence.append(result.node)
        # 若当前作用域缺少值映射，回填持久映射中的值端口
        if value_src:
            env.set_variable_persistent(var_name, value_src[0], value_src[1])

    nodes.extend(result.nested_nodes)
    edges.extend(result.edges)

    if result.new_prev_flow_node is not None:
        new_prev = result.new_prev_flow_node
        new_suppress = result.new_suppress_flag

    return True, nodes, edges, new_prev, new_suppress



