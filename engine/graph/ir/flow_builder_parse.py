from __future__ import annotations

import ast
import uuid
from typing import List, Optional, Tuple, Union

from engine.graph.common import (
    CLIENT_BOOL_FILTER_GRAPH_DIRNAME,
    CLIENT_GRAPH_END_BOOL_NODE_TITLE,
    CLIENT_GRAPH_END_INT_NODE_TITLE,
    CLIENT_INT_FILTER_GRAPH_DIRNAME,
    CLIENT_LEGACY_LOCAL_FILTER_GRAPH_DIRNAME,
    get_graph_category_from_folder_path,
)
from engine.graph.models import EdgeModel, GraphModel, NodeDefRef, NodeModel, PortModel

from .flow_builder_assignment_handlers import (
    handle_annassign_stmt,
    handle_assign_stmt,
    handle_expr_call_stmt,
)
from .flow_builder_local_constants import scan_and_register_local_constants
from .flow_builder_variable_analysis import analyze_variable_assignments
from .flow_utils import pick_default_flow_output_port
from .node_factory import FactoryContext
from .statement_flow_builder import (
    handle_for_loop,
    handle_if_statement,
    handle_match_over_composite_call,
    handle_match_statement,
)
from .validators import Validators
from .var_env import VarEnv


def _resolve_builtin_node_def_ref_by_title(title: str, *, ctx: FactoryContext) -> NodeDefRef:
    title_text = str(title or "").strip()
    full_key = ctx.node_name_index.get(title_text)
    if not full_key:
        raise ValueError(f"无法从 node_name_index 解析节点 key：{title_text}")
    node_def = ctx.node_library.get(full_key)
    if node_def is None:
        raise KeyError(f"node_library 中未找到 NodeDef：{full_key}")
    from engine.nodes import get_canonical_node_def_key

    return NodeDefRef(kind="builtin", key=get_canonical_node_def_key(node_def))


def parse_method_body(
    body: List[ast.stmt],
    event_node: Optional[NodeModel],
    graph_model: GraphModel,
    suppress_initial_flow_edge: bool,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
) -> Tuple[
    List[NodeModel],
    List[EdgeModel],
    Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
]:
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
        (节点列表, 边列表, 最终流程续接点)
    """
    # 预先扫描方法体，分析变量的赋值和使用情况
    # 更精确的判断：只有在分支内赋值且分支后使用的变量才需要局部变量
    if not env.assignment_counts:
        analysis_result = analyze_variable_assignments(body)
        env.set_assignment_counts(analysis_result.assignment_counts)
        env.set_branch_assignment_info(
            analysis_result.assigned_in_branch,
            analysis_result.used_after_branch,
        )

    # 预扫描方法体内“命名常量”赋值：供后续节点调用参数引用时回填为 input_constants。
    scan_and_register_local_constants(env=env, body=list(body or []))

    nodes: List[NodeModel] = []
    edges: List[EdgeModel] = []
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]] = event_node
    need_suppress_once = bool(suppress_initial_flow_edge)

    for stmt_index, stmt in enumerate(body):
        # 表达式语句：节点调用
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            handled, prev_flow_node, need_suppress_once = handle_expr_call_stmt(
                stmt=stmt,
                prev_flow_node=prev_flow_node,
                need_suppress_once=need_suppress_once,
                graph_model=graph_model,
                env=env,
                ctx=ctx,
                validators=validators,
                nodes=nodes,
                edges=edges,
            )
            if handled:
                continue

        # 赋值语句
        if isinstance(stmt, ast.Assign):
            handled, prev_flow_node, need_suppress_once = handle_assign_stmt(
                stmt=stmt,
                stmt_index=stmt_index,
                body=body,
                prev_flow_node=prev_flow_node,
                need_suppress_once=need_suppress_once,
                graph_model=graph_model,
                env=env,
                ctx=ctx,
                validators=validators,
                nodes=nodes,
                edges=edges,
            )
            if handled:
                continue

        # 带类型注解的赋值语句（AnnAssign）
        if isinstance(stmt, ast.AnnAssign):
            handled, prev_flow_node, need_suppress_once = handle_annassign_stmt(
                stmt=stmt,
                stmt_index=stmt_index,
                body=body,
                prev_flow_node=prev_flow_node,
                need_suppress_once=need_suppress_once,
                graph_model=graph_model,
                env=env,
                ctx=ctx,
                validators=validators,
                nodes=nodes,
                edges=edges,
            )
            if handled:
                continue

        # If
        if isinstance(stmt, ast.If):
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
            continue

        # Match
        if isinstance(stmt, ast.Match):
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
            continue

        # For
        if isinstance(stmt, ast.For):
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
            continue

        # Return：终止当前语句块
        #
        # 说明：
        # - return 在节点图中代表“提前结束当前事件/入口方法的流程”；后续语句不可达；
        # - 分支构建器会用 block_has_return 决定分支出口是否可继续接续；
        # - 在 IR 层显式停止解析，避免把 return 后的语句错误连到图中。
        #
        # client 过滤器图约定：
        # - `return <表达式>` 代表把结果输入到【节点图结束（布尔型/整数）】并终止；
        # - 结束节点为纯数据节点（无流程口），但其输入端“结果”必须有数据来源（连线或常量）。
        if isinstance(stmt, ast.Return):
            return_value = getattr(stmt, "value", None)
            if return_value is None:
                break

            folder_path_text = str(getattr(ctx, "graph_folder_path", "") or "")
            graph_category = get_graph_category_from_folder_path(folder_path_text)
            end_node_title = ""
            if graph_category == CLIENT_INT_FILTER_GRAPH_DIRNAME:
                end_node_title = CLIENT_GRAPH_END_INT_NODE_TITLE
            elif graph_category in (CLIENT_BOOL_FILTER_GRAPH_DIRNAME, CLIENT_LEGACY_LOCAL_FILTER_GRAPH_DIRNAME):
                end_node_title = CLIENT_GRAPH_END_BOOL_NODE_TITLE

            # 非 client 过滤器图：保持旧行为（仅终止解析，不物化返回节点）。
            if not end_node_title:
                break

            end_node = NodeModel(
                id=f"graph_end_{uuid.uuid4().hex[:8]}",
                title=end_node_title,
                category="其他节点",
                node_def_ref=_resolve_builtin_node_def_ref_by_title(end_node_title, ctx=ctx),
                pos=(0.0, 0.0),
                inputs=[PortModel(name="结果", is_input=True)],
                outputs=[],
            )

            # Return 值 → end_node.结果
            bound = False
            if isinstance(return_value, ast.Constant):
                end_node.input_constants["结果"] = getattr(return_value, "value", None)
                bound = True
            elif isinstance(return_value, ast.Name):
                var_name = str(getattr(return_value, "id", "") or "")
                if env.has_local_constant(var_name):
                    end_node.input_constants["结果"] = env.get_local_constant(var_name)
                    bound = True
                else:
                    source = env.get_variable(var_name)
                    if source is not None:
                        src_node_id, src_port_name = source
                        edges.append(
                            EdgeModel(
                                id=str(uuid.uuid4()),
                                src_node=src_node_id,
                                src_port=src_port_name,
                                dst_node=end_node.id,
                                dst_port="结果",
                            )
                        )
                        bound = True

            if not bound:
                line_no = getattr(stmt, "lineno", "?")
                validators.error(
                    f"行{line_no}: client 过滤器节点图的 return 值无法建模为【{end_node_title}】输入；"
                    "请返回一个已赋值的变量（如 `return 结果`）或常量（如 `return True/False/0/1`）"
                )

            nodes.append(end_node)
            break

        # Break
        if isinstance(stmt, ast.Break):
            if not env.loop_stack:
                line_no = getattr(stmt, "lineno", "?")
                validators.error(f"行{line_no}: 发现 break 但不在循环体内；该写法无法可靠解析为节点图语义")
                continue
            target_loop = env.loop_stack[-1]

            break_node = NodeModel(
                id=f"node_跳出循环_{uuid.uuid4().hex[:8]}",
                title="跳出循环",
                category="执行节点",
                node_def_ref=_resolve_builtin_node_def_ref_by_title("跳出循环", ctx=ctx),
                pos=(0.0, 0.0),
                inputs=[PortModel(name="流程入", is_input=True)],
                outputs=[PortModel(name="流程出", is_input=False)],
            )
            break_node.source_lineno = getattr(stmt, "lineno", 0)
            break_node.source_end_lineno = getattr(stmt, "end_lineno", getattr(stmt, "lineno", 0))

            nodes.append(break_node)
            env.node_sequence.append(break_node)

            def _connect_break_from_source(
                source_obj: Union[NodeModel, Tuple[NodeModel, str]],
                *,
                break_loop_node: NodeModel,
            ) -> None:
                """连接 break 的流程来源到【跳出循环】节点的【流程入】端口。"""
                if isinstance(source_obj, tuple) and len(source_obj) == 2:
                    src_node, forced_src_port = source_obj
                    edges.append(
                        EdgeModel(
                            id=str(uuid.uuid4()),
                            src_node=src_node.id,
                            src_port=forced_src_port,
                            dst_node=break_loop_node.id,
                            dst_port="流程入",
                        )
                    )
                    return

                src_node = source_obj
                src_port = pick_default_flow_output_port(src_node)
                edges.append(
                    EdgeModel(
                        id=str(uuid.uuid4()),
                        src_node=src_node.id,
                        src_port=src_port or "流程出",
                        dst_node=break_loop_node.id,
                        dst_port="流程入",
                    )
                )

            # 【跳出循环】节点的输出再连到循环节点的【跳出循环】输入
            edges.append(
                EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=break_node.id,
                    src_port="流程出",
                    dst_node=target_loop.id,
                    dst_port="跳出循环",
                )
            )

            if prev_flow_node:
                if isinstance(prev_flow_node, list):
                    for source in prev_flow_node:
                        _connect_break_from_source(source, break_loop_node=break_node)
                else:
                    _connect_break_from_source(prev_flow_node, break_loop_node=break_node)
            break

        # While（不转换）
        if isinstance(stmt, ast.While):
            pass

    return nodes, edges, prev_flow_node

