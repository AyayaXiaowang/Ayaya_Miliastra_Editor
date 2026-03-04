from __future__ import annotations

import ast
from typing import Dict, List, Optional, Tuple, Union

from engine.graph.models import EdgeModel, GraphModel, NodeModel
from engine.graph.common import TARGET_ENTITY_PORT_NAME, VARIABLE_NAME_PORT_NAME
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.type_registry import TYPE_GENERIC_DICT, TYPE_GENERIC_LIST, is_dict_type_name

from .arg_normalizer import is_reserved_argument
from .flow_builder_port_type_overrides import (
    extract_annotation_type_text,
    register_port_type_override_from_annotation,
)
from .flow_builder_variable_analysis import is_placeholder_annassign_overwritten_before_use
from .flow_utils import (
    handle_alias_assignment,
    materialize_call_node,
    register_output_variables,
    warn_literal_assignment,
)
from .local_var_builder import (
    LOCAL_HANDLE_PREFIX,
    build_local_var_nodes,
    should_model_as_local_var,
)
from .node_factory import FactoryContext
from .validators import Validators
from .var_env import VarEnv


def _is_name_used_in_stmt(stmt: ast.stmt, *, name: str) -> bool:
    """判断某语句中是否以“读取（Load）”方式使用了指定变量名。"""
    name_text = str(name or "").strip()
    if not name_text:
        return False
    for node in ast.walk(stmt):
        if isinstance(node, ast.Name) and node.id == name_text and isinstance(getattr(node, "ctx", None), ast.Load):
            return True
    return False


def _extract_custom_var_key_from_call(
    call: ast.Call,
    *,
    entity_port_name: str,
    var_name_port_name: str,
) -> tuple[str, str] | None:
    """从【获取/设置自定义变量】调用中提取可静态比较的 key=(目标实体, 变量名)。

    说明：
    - 目标实体：仅支持 `ast.Name`（运行期变量名）或 `self.owner_entity` 等可静态提取的字符串表达式；
    - 变量名：要求可静态提取为字符串（模块常量/字面量均可）。
    """
    if not isinstance(call, ast.Call):
        return None

    entity_expr: ast.AST | None = None
    var_name_expr: ast.AST | None = None
    for kw in list(getattr(call, "keywords", []) or []):
        if not isinstance(kw, ast.keyword):
            continue
        if kw.arg == entity_port_name:
            entity_expr = kw.value
        elif kw.arg == var_name_port_name:
            var_name_expr = kw.value

    if entity_expr is None or var_name_expr is None:
        return None

    # entity：优先支持运行期变量名（ast.Name）；其次允许静态可提取表达式（如 self.owner_entity）
    entity_key: str | None = None
    if isinstance(entity_expr, ast.Name) and isinstance(entity_expr.id, str) and entity_expr.id:
        entity_key = f"name:{entity_expr.id}"
    else:
        extracted = extract_constant_value(entity_expr)
        if extracted is NOT_EXTRACTABLE:
            return None
        entity_key = f"const:{str(extracted)}"

    # var_name：必须可静态提取为字符串（模块常量/字面量）
    extracted_var = extract_constant_value(var_name_expr)
    if extracted_var is NOT_EXTRACTABLE:
        return None
    var_name_value = str(extracted_var)
    if not var_name_value:
        return None

    return (entity_key, var_name_value)


def _should_force_custom_var_read_snapshot_as_local_var(
    *,
    assigned_var_name: str,
    value_expr: ast.expr,
    remaining_statements: List[ast.stmt],
) -> bool:
    """判断“自定义变量读取”是否需要被物化为局部变量快照（避免节点语义下被推迟求值）。

    触发条件（保守、可静态识别）：
    - 当前赋值右值为【获取自定义变量】；
    - 后续语句中存在对同一个 (目标实体, 变量名) 的【设置自定义变量】（可能在 for/if/match 内）；
    - 且被赋值的变量在该写入之后仍会被读取使用。
    """
    var_text = str(assigned_var_name or "").strip()
    if not var_text:
        return False
    if not isinstance(value_expr, ast.Call) or not isinstance(getattr(value_expr, "func", None), ast.Name):
        return False
    if str(value_expr.func.id or "").strip() != "获取自定义变量":
        return False

    read_key = _extract_custom_var_key_from_call(
        value_expr,
        entity_port_name=TARGET_ENTITY_PORT_NAME,
        var_name_port_name=VARIABLE_NAME_PORT_NAME,
    )
    if read_key is None:
        return False

    # 记录“首次出现写入该 key 的语句索引”（以语句级顺序做保守近似）
    first_write_stmt_index: int | None = None
    for stmt_index, stmt in enumerate(list(remaining_statements or [])):
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call) or not isinstance(getattr(node, "func", None), ast.Name):
                continue
            if str(node.func.id or "").strip() != "设置自定义变量":
                continue
            write_key = _extract_custom_var_key_from_call(
                node,
                entity_port_name=TARGET_ENTITY_PORT_NAME,
                var_name_port_name=VARIABLE_NAME_PORT_NAME,
            )
            if write_key is None:
                continue
            if write_key == read_key:
                first_write_stmt_index = stmt_index
                break
        if first_write_stmt_index is not None:
            break

    if first_write_stmt_index is None:
        return False

    # 判断：在该写入之后是否仍使用 assigned_var_name（Load）
    for later_stmt in list(remaining_statements[first_write_stmt_index + 1 :] or []):
        if _is_name_used_in_stmt(later_stmt, name=var_text):
            return True
    return False


def _iter_assigned_target_names(target_expr: object) -> List[str]:
    """提取赋值目标中的变量名（仅 Name 与 Tuple 展开）。"""
    names: List[str] = []
    if isinstance(target_expr, ast.Name):
        if isinstance(target_expr.id, str) and target_expr.id:
            names.append(target_expr.id)
    elif isinstance(target_expr, ast.Tuple):
        for element in list(target_expr.elts or []):
            names.extend(_iter_assigned_target_names(element))
    return names


def _should_bypass_alias_assignment(env: VarEnv, value_expr: ast.expr, targets_obj: object) -> bool:
    """在需要局部变量建模的场景下，禁止“别名赋值快速路径”。

    背景：
    - flow_utils.handle_alias_assignment 会把 `目标 = 源变量` 直接改写为 env 映射并跳过建模；
    - 但当目标变量处于“多分支合流/已有局部变量句柄”模式时，跳过会导致：
      - 某个分支生成了【获取局部变量】（作为合流容器）
      - 另一个分支用别名赋值被跳过，未生成【设置局部变量】
      - 最终图中出现“获取局部变量但没有设置”的异常状态，且合流语义可能错误。
    """
    if not isinstance(value_expr, ast.Name):
        return False

    assigned_names: List[str] = []
    if isinstance(targets_obj, list):
        for t in targets_obj:
            assigned_names.extend(_iter_assigned_target_names(t))
    else:
        assigned_names.extend(_iter_assigned_target_names(targets_obj))

    for name in assigned_names:
        if env.is_multi_assign_candidate(name):
            return True
        handle_key = f"{LOCAL_HANDLE_PREFIX}{name}"
        if env.get_variable(handle_key) is not None:
            return True
    return False


def _is_dict_inplace_mutated_later(variable_name: str, later_stmts: List[ast.stmt]) -> bool:
    """判断变量在后续语句中是否作为“字典原地修改”的目标字典被传入。

    用途：当字典来自【拼装字典/建立字典】这类纯运算构造节点时，后续若对其做多次原地修改，
    在“无局部变量固定引用”的语义下容易变成“每次都是新字典”，需要提示用户改写。
    """
    name_text = str(variable_name or "").strip()
    if not name_text:
        return False

    dict_mutation_nodes: Dict[str, Tuple[str, ...]] = {
        "对字典设置或新增键值对": ("字典",),
        "以键对字典移除键值对": ("字典",),
        "清空字典": ("字典",),
    }

    for statement in list(later_stmts or []):
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            func = getattr(node, "func", None)
            if not isinstance(func, ast.Name):
                continue
            node_name = str(func.id or "").strip()
            port_names = dict_mutation_nodes.get(node_name)
            if not port_names:
                continue

            # 1) 关键字参数优先
            for kw in list(getattr(node, "keywords", []) or []):
                if kw.arg not in port_names:
                    continue
                value_expr = getattr(kw, "value", None)
                if isinstance(value_expr, ast.Name) and value_expr.id == name_text:
                    return True

            # 2) 位置参数兜底：这些节点的“目标字典”均为第一个非保留实参
            non_reserved_args: List[ast.AST] = []
            for arg in list(getattr(node, "args", []) or []):
                if is_reserved_argument(arg):
                    continue
                non_reserved_args.append(arg)
            if non_reserved_args and isinstance(non_reserved_args[0], ast.Name):
                if non_reserved_args[0].id == name_text:
                    return True

    return False


def handle_expr_call_stmt(
    *,
    stmt: ast.Expr,
    prev_flow_node: object,
    need_suppress_once: bool,
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    nodes: List[NodeModel],
    edges: List[EdgeModel],
) -> tuple[bool, object, bool]:
    """处理表达式语句（节点调用）。"""
    if not (isinstance(stmt, ast.Expr) and isinstance(getattr(stmt, "value", None), ast.Call)):
        return False, prev_flow_node, need_suppress_once

    result = materialize_call_node(
        call_expr=stmt.value,
        stmt=stmt,
        prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
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
        return True, prev_flow_node, need_suppress_once

    if result.node:
        nodes.append(result.node)
        env.node_sequence.append(result.node)

    nodes.extend(result.nested_nodes)
    edges.extend(result.edges)

    if result.new_prev_flow_node is not None:
        prev_flow_node = result.new_prev_flow_node
        need_suppress_once = result.new_suppress_flag

    return True, prev_flow_node, need_suppress_once


def handle_assign_stmt(
    *,
    stmt: ast.Assign,
    stmt_index: int,
    body: List[ast.stmt],
    prev_flow_node: object,
    need_suppress_once: bool,
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    nodes: List[NodeModel],
    edges: List[EdgeModel],
) -> tuple[bool, object, bool]:
    """处理赋值语句（Assign）。"""
    if not isinstance(stmt, ast.Assign):
        return False, prev_flow_node, need_suppress_once

    # 处理纯别名赋值
    if (not _should_bypass_alias_assignment(env, stmt.value, stmt.targets)) and handle_alias_assignment(
        stmt.value,
        stmt.targets,
        env,
        graph_model=graph_model,
    ):
        return True, prev_flow_node, need_suppress_once

    # 发出字面量赋值警告
    warn_literal_assignment(stmt.value, stmt.targets, stmt, validators)

    # 若是单变量赋值（含调用/常量），优先用“获取/设置局部变量”建模
    primary_target = stmt.targets[0] if stmt.targets else None
    if isinstance(primary_target, ast.Name) and (not env.get_var_type(primary_target.id)):
        # 为“局部变量建模/字典禁用”等策略补充轻量类型信息：
        # - 列表/字典拼装节点的输出为容器类型，若后续存在原地修改或分支合流，
        #   需要提前知道它是“列表”还是“字典”。
        if isinstance(stmt.value, ast.Call) and isinstance(getattr(stmt.value, "func", None), ast.Name):
            call_name = str(stmt.value.func.id or "").strip()
            if call_name == "拼装列表":
                env.set_var_type(primary_target.id, TYPE_GENERIC_LIST)
            elif call_name in {"拼装字典", "建立字典"}:
                env.set_var_type(primary_target.id, TYPE_GENERIC_DICT)

    # 字典：不支持【获取局部变量】固定引用；若来源是“拼装/建立字典”并且后续要原地修改，
    # 必须提示用户该写法并非“连续修改同一字典”。
    if (
        isinstance(primary_target, ast.Name)
        and is_dict_type_name(env.get_var_type(primary_target.id))
        and isinstance(stmt.value, ast.Call)
        and isinstance(getattr(stmt.value, "func", None), ast.Name)
    ):
        call_name = str(stmt.value.func.id or "").strip()
        if call_name in {"拼装字典", "建立字典"} and _is_dict_inplace_mutated_later(
            primary_target.id,
            body[stmt_index + 1 :],
        ):
            line_no = getattr(stmt, "lineno", "?")
            validators.warn(
                "行"
                + str(line_no)
                + ": 发现字典变量 '"
                + str(primary_target.id)
                + "' 来源于【"
                + call_name
                + "】且后续存在对字典的连续原地修改；"
                + "由于【获取局部变量】不支持字典，这种写法在节点图语义下不是“持续修改同一个字典”，"
                + "而更像每次都在重新构造的新字典上修改。请改为一次性拼装出最终字典，或将字典状态放入自定义变量/节点图变量后再更新。"
            )

    # 工程化：自定义变量读取快照（修复“代码含义=先读旧值”但节点语义可能推迟求值的漂移）
    if isinstance(primary_target, ast.Name) and _should_force_custom_var_read_snapshot_as_local_var(
        assigned_var_name=primary_target.id,
        value_expr=stmt.value,
        remaining_statements=body[stmt_index + 1 :],
    ):
        handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
            var_name=primary_target.id,
            value_expr=stmt.value,
            stmt=stmt,
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
            need_suppress_once=need_suppress_once,
            env=env,
            ctx=ctx,
            validators=validators,
            graph_model=graph_model,
            force_materialize_first_write=True,
        )
        if handled:
            nodes.extend(lv_nodes)
            edges.extend(lv_edges)
            return True, prev_flow_node, need_suppress_once

    if isinstance(primary_target, ast.Name) and should_model_as_local_var(
        primary_target.id,
        stmt.value,
        body[stmt_index + 1 :],
        env,
    ):
        handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
            var_name=primary_target.id,
            value_expr=stmt.value,
            stmt=stmt,
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
            need_suppress_once=need_suppress_once,
            env=env,
            ctx=ctx,
            validators=validators,
            graph_model=graph_model,
        )
        if handled:
            nodes.extend(lv_nodes)
            edges.extend(lv_edges)
            return True, prev_flow_node, need_suppress_once

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
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
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
            return True, prev_flow_node, need_suppress_once

        if result.node:
            nodes.append(result.node)
            env.node_sequence.append(result.node)

            # 注册输出变量
            register_output_variables(
                result.node,
                stmt.targets,
                env,
                node_library=ctx.node_library,
            )

        nodes.extend(result.nested_nodes)
        edges.extend(result.edges)

        if result.new_prev_flow_node is not None:
            prev_flow_node = result.new_prev_flow_node
            need_suppress_once = result.new_suppress_flag

    return True, prev_flow_node, need_suppress_once


def handle_annassign_stmt(
    *,
    stmt: ast.AnnAssign,
    stmt_index: int,
    body: List[ast.stmt],
    prev_flow_node: object,
    need_suppress_once: bool,
    graph_model: GraphModel,
    env: VarEnv,
    ctx: FactoryContext,
    validators: Validators,
    nodes: List[NodeModel],
    edges: List[EdgeModel],
) -> tuple[bool, object, bool]:
    """处理带类型注解的赋值语句（AnnAssign）。"""
    if not isinstance(stmt, ast.AnnAssign):
        return False, prev_flow_node, need_suppress_once

    # 纯类型标注（无右值）仅用于阅读/类型提示，不应建模为任何节点。
    # 例如：`方向X: "浮点数"` 这类语句在旧逻辑中会被误判为“需要局部变量建模”，
    # 从而生成孤立的【获取局部变量】节点（无连线、无数据）。
    if stmt.value is None:
        return True, prev_flow_node, need_suppress_once

    # 记录中文类型注解（用于“字典禁用局部变量/列表引用策略”等）
    if isinstance(stmt.target, ast.Name):
        declared_type_text = extract_annotation_type_text(stmt.annotation)
        if declared_type_text:
            env.set_var_type(stmt.target.id, declared_type_text)

    # 字典：不支持【获取局部变量】固定引用；若来源是“拼装/建立字典”并且后续要原地修改，提示用户改写
    if (
        isinstance(stmt.target, ast.Name)
        and is_dict_type_name(env.get_var_type(stmt.target.id))
        and isinstance(stmt.value, ast.Call)
        and isinstance(getattr(stmt.value, "func", None), ast.Name)
    ):
        call_name = str(stmt.value.func.id or "").strip()
        if call_name in {"拼装字典", "建立字典"} and _is_dict_inplace_mutated_later(
            stmt.target.id,
            body[stmt_index + 1 :],
        ):
            line_no = getattr(stmt, "lineno", "?")
            validators.warn(
                "行"
                + str(line_no)
                + ": 发现字典变量 '"
                + str(stmt.target.id)
                + "' 来源于【"
                + call_name
                + "】且后续存在对字典的连续原地修改；"
                + "由于【获取局部变量】不支持字典，这种写法在节点图语义下不是“持续修改同一个字典”，"
                + "而更像每次都在重新构造的新字典上修改。请改为一次性拼装出最终字典，或将字典状态放入自定义变量/节点图变量后再更新。"
            )

    # 处理纯别名赋值
    if (not _should_bypass_alias_assignment(env, stmt.value, stmt.target)) and handle_alias_assignment(
        stmt.value,
        stmt.target,
        env,
        graph_model=graph_model,
        annotation_type=extract_annotation_type_text(stmt.annotation),
    ):
        return True, prev_flow_node, need_suppress_once

    # 单变量注解赋值优先尝试局部变量建模
    if isinstance(stmt.target, ast.Name) and _should_force_custom_var_read_snapshot_as_local_var(
        assigned_var_name=stmt.target.id,
        value_expr=stmt.value,
        remaining_statements=body[stmt_index + 1 :],
    ):
        handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
            var_name=stmt.target.id,
            value_expr=stmt.value,
            stmt=stmt,
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
            need_suppress_once=need_suppress_once,
            env=env,
            ctx=ctx,
            validators=validators,
            graph_model=graph_model,
            force_materialize_first_write=True,
        )
        if handled:
            nodes.extend(lv_nodes)
            edges.extend(lv_edges)
            return True, prev_flow_node, need_suppress_once

    if isinstance(stmt.target, ast.Name) and should_model_as_local_var(
        stmt.target.id,
        stmt.value,
        body[stmt_index + 1 :],
        env,
    ):
        # 占位初始化特判：若当前 AnnAssign 只是“声明/类型提示”，且会在被读取前被后续赋值覆盖，
        # 则不应触发【获取局部变量】建模（否则会产生大量零散局部变量节点）。
        if isinstance(stmt.value, ast.Constant) and is_placeholder_annassign_overwritten_before_use(
            var_name=stmt.target.id,
            remaining_statements=body[stmt_index + 1 :],
        ):
            return True, prev_flow_node, need_suppress_once
        handled, lv_nodes, lv_edges, prev_flow_node, need_suppress_once = build_local_var_nodes(
            var_name=stmt.target.id,
            value_expr=stmt.value,
            stmt=stmt,
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
            need_suppress_once=need_suppress_once,
            env=env,
            ctx=ctx,
            validators=validators,
            graph_model=graph_model,
        )
        if handled:
            nodes.extend(lv_nodes)
            edges.extend(lv_edges)
            return True, prev_flow_node, need_suppress_once

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
            prev_flow_node=prev_flow_node,  # type: ignore[arg-type]
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
            return True, prev_flow_node, need_suppress_once

        if result.node:
            nodes.append(result.node)
            env.node_sequence.append(result.node)

            # 注册输出变量
            register_output_variables(
                result.node,
                stmt.target,
                env,
                node_library=ctx.node_library,
            )

            # 基于类型注解为对应输出端口记录类型覆盖信息
            annotation_type_text = extract_annotation_type_text(stmt.annotation)
            if annotation_type_text:
                register_port_type_override_from_annotation(
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

    return True, prev_flow_node, need_suppress_once

