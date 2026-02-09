"""局部变量建模工具

负责将简单的赋值语句统一建模为【获取局部变量】/【设置局部变量】节点组合，
以便在图中表达局部状态的持久化与多次更新。
"""
from __future__ import annotations

import ast
from typing import List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.type_registry import (
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    is_dict_type_name,
    is_list_type_name,
    normalize_type_text,
)

from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext
from .flow_utils import materialize_call_node
from .arg_normalizer import is_reserved_argument


LOCAL_HANDLE_PREFIX = "__local_handle__"

_LIST_INPLACE_MUTATION_NODES: dict[str, tuple[str, ...]] = {
    # list_literal_rewriter 归一化目标
    "对列表修改值": ("列表",),
    "对列表移除值": ("列表",),
    "对列表插入值": ("列表",),
    "清除列表": ("列表",),
    "拼接列表": ("目标列表",),
    # 其他常见原地修改节点
    "列表排序": ("列表",),
}

_BUILD_LIST_NODE_CALL_NAME = "拼装列表"
_BUILD_DICT_NODE_CALL_NAME = "拼装字典"
_BUILD_DICT_FROM_LISTS_NODE_CALL_NAME = "建立字典"


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
    def _loop_stmt_has_assignment(loop_stmt: ast.stmt) -> bool:
        """循环语句（for/while）内部是否对变量赋值。

        背景：
        - 循环体解析会对 VarEnv 做 snapshot/restore；
        - 若变量会在循环体内被更新，必须提前触发“局部变量建模”，否则更新会在 restore 后丢失。
        """
        for node in ast.walk(loop_stmt):
            if isinstance(node, ast.Assign):
                target_names = _collect_assignment_targets(node.targets or [])
                if variable_name in target_names:
                    return True
            elif isinstance(node, ast.AnnAssign):
                target_names = _collect_assignment_targets(getattr(node, "target", None))
                if variable_name in target_names:
                    return True
            elif isinstance(node, ast.For):
                # for 的 loop var 本身也是一种“赋值”
                target_names = _collect_assignment_targets(getattr(node, "target", None))
                if variable_name in target_names:
                    return True
        return False

    for statement in remaining_statements:
        if isinstance(statement, ast.Assign):
            target_names = _collect_assignment_targets(statement.targets or [])
            if variable_name in target_names:
                return True
        elif isinstance(statement, ast.AnnAssign):
            target_names = _collect_assignment_targets(getattr(statement, "target", None))
            if variable_name in target_names:
                return True
        elif isinstance(statement, (ast.If, ast.Match)):
            # 分支结构同样会触发 VarEnv snapshot/restore：
            # 若变量在后续 if/match 的分支体内会被赋值，需要提前触发“局部变量建模”，
            # 否则会出现“句柄在某个分支内首次创建、另一分支只能引用该句柄”的错误建模。
            if _loop_stmt_has_assignment(statement):
                return True
        elif isinstance(statement, (ast.For, ast.While)):
            if _loop_stmt_has_assignment(statement):
                return True
    return False


def _is_list_inplace_mutated_later(
    variable_name: str,
    remaining_statements: List[ast.stmt],
) -> bool:
    """判断变量在后续语句中是否作为“列表原地修改”的目标列表被传入。

    说明：
    - Graph Code 在解析前会把 `列表[序号]=值`/`del 列表[序号]`/`列表.insert/extend/clear`
      等语法糖改写为对应的执行节点调用，因此这里主要扫描节点调用。
    - 仅对“明确会原地修改列表”的节点生效（见 `_LIST_INPLACE_MUTATION_NODES`）。
    """
    var_text = str(variable_name or "").strip()
    if not var_text:
        return False

    for statement in list(remaining_statements or []):
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            func = getattr(node, "func", None)
            if not isinstance(func, ast.Name):
                continue
            node_name = str(func.id or "").strip()
            if node_name not in _LIST_INPLACE_MUTATION_NODES:
                continue

            list_port_names = _LIST_INPLACE_MUTATION_NODES.get(node_name, ())
            # 1) 关键字参数优先
            for kw in list(getattr(node, "keywords", []) or []):
                if kw.arg not in list_port_names:
                    continue
                if isinstance(getattr(kw, "value", None), ast.Name) and kw.value.id == var_text:
                    return True

            # 2) 位置参数兜底：这些节点的“目标列表”均为第一个非保留实参
            non_reserved_args: List[ast.AST] = []
            for arg in list(getattr(node, "args", []) or []):
                if is_reserved_argument(arg):
                    continue
                non_reserved_args.append(arg)
            if non_reserved_args and isinstance(non_reserved_args[0], ast.Name):
                if non_reserved_args[0].id == var_text:
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
    var_type_text = env.get_var_type(variable_name)
    if not var_type_text:
        # 轻量推断：对常见拼装节点补一个“泛型列表/泛型字典”类型占位，供后续策略使用。
        if isinstance(value_expr, ast.Call) and isinstance(getattr(value_expr, "func", None), ast.Name):
            fn = str(value_expr.func.id or "").strip()
            if fn == _BUILD_LIST_NODE_CALL_NAME:
                var_type_text = TYPE_GENERIC_LIST
            elif fn in {_BUILD_DICT_NODE_CALL_NAME, _BUILD_DICT_FROM_LISTS_NODE_CALL_NAME}:
                var_type_text = TYPE_GENERIC_DICT

    # 约束：字典不支持局部变量建模（含别名字典与泛型字典）。
    if is_dict_type_name(var_type_text):
        return False

    is_list_type = is_list_type_name(var_type_text) or (var_type_text == TYPE_GENERIC_LIST)
    handle_key = f"{LOCAL_HANDLE_PREFIX}{variable_name}"
    handle_exists = env.get_variable(handle_key) is not None
    var_already_assigned = env.get_variable(variable_name) is not None
    predeclared = env.is_predeclared(variable_name)
    has_future_assignment = _has_later_assignment(variable_name, remaining_statements)
    multi_assign_hint = env.is_multi_assign_candidate(variable_name)

    # 列表引用：当列表由【拼装列表】等纯运算节点构造，且后续存在“原地修改列表”的执行节点时，
    # 需要用一次【获取局部变量】把列表引用固定下来，避免后续“拉取式重复求值”导致拿到不同的列表实例。
    if (
        is_list_type
        and (not handle_exists)
        and (not var_already_assigned)
        and (not has_future_assignment)
        and (not multi_assign_hint)
        and isinstance(value_expr, ast.Call)
        and isinstance(getattr(value_expr, "func", None), ast.Name)
        and str(value_expr.func.id or "").strip() == _BUILD_LIST_NODE_CALL_NAME
        and _is_list_inplace_mutated_later(variable_name, remaining_statements)
    ):
        return True

    # 多分支赋值场景：一旦变量被标记为"跨分支赋值候选"（由 branch_builder 计算
    # 的分支交集），当前赋值必须走局部变量建模，以便各分支通过同一局部变量句柄
    # 在合流处共享数据源。
    if multi_assign_hint:
        return True

    # 已存在句柄时：必须继续复用同一局部变量。
    #
    # 特别说明：
    # - 循环体解析会对 VarEnv 做 snapshot/restore，循环体内的“赋值”不能依赖 env 的
    #   直接连线映射来表达跨迭代/跨块的状态更新；
    # - 一旦变量已进入【获取/设置局部变量】建模模式（句柄存在），后续赋值若不生成
    #   【设置局部变量】，将导致计算节点输出无人消费（UI 显示“未被数据链引用”），
    #   且运行语义丢失（局部状态不会被写回）。
    if handle_exists:
        return True

    # 如果变量已经被赋值过（如通过元组拆分赋值或之前的调用），并且后续没有更多赋值，
    # 则不需要转换为局部变量节点，可以直接使用连线逻辑。
    # 这避免了为只使用一次的变量创建多余的【获取局部变量】+【设置局部变量】组合。
    if var_already_assigned and not has_future_assignment:
        return False

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
    graph_model: GraphModel,
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

    normalized_scope = str(getattr(ctx, "graph_scope", "server") or "server").strip().lower()
    is_client_scope = normalized_scope == "client"

    # client 作用域：局部变量节点为“按变量名读写”的变体（端口名与 server 不兼容）。
    # - 获取局部变量：inputs=["变量名"] outputs=["变量值"]
    # - 设置局部变量：inputs=["流程入","变量名","变量值"] outputs=["流程出"]
    #
    # IR 层的局部变量建模需要在首次赋值时也执行一次“写入”，否则仅创建读取节点会导致值未初始化。
    if is_client_scope:
        get_out_port = "变量值"

        # 1) 确保存在“读取节点”（用于后续把变量作为数据来源引用）
        if handle_src is None:
            var_name_expr = ast.Constant(value=str(var_name))
            var_name_expr = _ensure_location(var_name_expr, stmt)

            get_call = ast.Call(
                func=ast.Name(id="获取局部变量", ctx=ast.Load()),
                args=[var_name_expr],
                keywords=[],
            )
            get_call = _ensure_location(get_call, value_expr or stmt)

            result = materialize_call_node(
                call_expr=get_call,
                stmt=stmt,
                prev_flow_node=new_prev,
                need_suppress_once=new_suppress,
                graph_model=graph_model,
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
                # 标记“已进入局部变量建模模式”：handle_key 仅作为哨兵，供 flow_builder 禁用别名赋值快速路径
                env.set_variable_persistent(handle_key, result.node.id, get_out_port)
                env.set_variable_persistent(var_name, result.node.id, get_out_port)

            nodes.extend(result.nested_nodes)
            edges.extend(result.edges)

            if result.new_prev_flow_node is not None:
                new_prev = result.new_prev_flow_node
                new_suppress = result.new_suppress_flag

            handle_src = env.get_variable(handle_key)
            value_src = env.get_variable(var_name)
            if handle_src is None:
                return False, nodes, edges, new_prev, new_suppress

        # 2) 写入：每次赋值都物化为【设置局部变量】流程节点（按变量名写入）
        # 约定：变量名使用常量端口回填，不通过数据连线表达。
        name_const = ast.Constant(value=str(var_name))
        name_const = _ensure_location(name_const, stmt)

        set_call = ast.Call(
            func=ast.Name(id="设置局部变量", ctx=ast.Load()),
            args=[],
            keywords=[
                ast.keyword(arg="变量名", value=name_const),
                ast.keyword(arg="变量值", value=value_expr),
            ],
        )
        set_call = _ensure_location(set_call, value_expr or stmt)

        result = materialize_call_node(
            call_expr=set_call,
            stmt=stmt,
            prev_flow_node=new_prev,
            need_suppress_once=new_suppress,
            graph_model=graph_model,
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
            # 变量的“读取映射”保持指向首次创建的获取节点输出
            if value_src:
                env.set_variable_persistent(var_name, value_src[0], value_src[1])

        nodes.extend(result.nested_nodes)
        edges.extend(result.edges)

        if result.new_prev_flow_node is not None:
            new_prev = result.new_prev_flow_node
            new_suppress = result.new_suppress_flag

        return True, nodes, edges, new_prev, new_suppress

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
            graph_model=graph_model,
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

            # 端口类型覆盖：若变量存在中文类型注解（VarEnv.var_types），则把类型写入 overrides，
            # 避免“初始值常量字符串化”导致画布/推断把该局部变量误显示为字符串。
            var_type_text = normalize_type_text(env.get_var_type(var_name))
            if var_type_text and (not var_type_text.startswith(TYPE_GENERIC)) and (not is_dict_type_name(var_type_text)):
                meta = getattr(graph_model, "metadata", None)
                if meta is None:
                    graph_model.metadata = {}
                    meta = graph_model.metadata
                overrides_raw = meta.get("port_type_overrides")
                overrides = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}
                node_overrides = overrides.get(result.node.id)
                node_overrides = dict(node_overrides) if isinstance(node_overrides, dict) else {}
                # server 获取局部变量：初始值→值 同型透传
                node_overrides["初始值"] = var_type_text
                node_overrides["值"] = var_type_text
                overrides[result.node.id] = node_overrides
                meta["port_type_overrides"] = overrides

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
        graph_model=graph_model,
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

        # 端口类型覆盖：为“设置局部变量”的输入端口写入同型覆盖，保证 UI/推断口径一致。
        var_type_text = normalize_type_text(env.get_var_type(var_name))
        if var_type_text and (not var_type_text.startswith(TYPE_GENERIC)) and (not is_dict_type_name(var_type_text)):
            meta = getattr(graph_model, "metadata", None)
            if meta is None:
                graph_model.metadata = {}
                meta = graph_model.metadata
            overrides_raw = meta.get("port_type_overrides")
            overrides = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}
            node_overrides = overrides.get(result.node.id)
            node_overrides = dict(node_overrides) if isinstance(node_overrides, dict) else {}
            node_overrides["值"] = var_type_text
            overrides[result.node.id] = node_overrides
            meta["port_type_overrides"] = overrides

    nodes.extend(result.nested_nodes)
    edges.extend(result.edges)

    if result.new_prev_flow_node is not None:
        new_prev = result.new_prev_flow_node
        new_suppress = result.new_suppress_flag

    return True, nodes, edges, new_prev, new_suppress



