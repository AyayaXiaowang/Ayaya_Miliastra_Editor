from __future__ import annotations

import ast
import uuid
from typing import Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, EdgeModel, PortModel, NodeDefRef

from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext
from engine.graph.utils.ast_utils import NOT_EXTRACTABLE, extract_constant_value
from engine.type_registry import TYPE_GENERIC_DICT, TYPE_GENERIC_LIST, is_dict_type_name
from engine.graph.common import (
    get_graph_category_from_folder_path,
    CLIENT_INT_FILTER_GRAPH_DIRNAME,
    CLIENT_BOOL_FILTER_GRAPH_DIRNAME,
    CLIENT_LEGACY_LOCAL_FILTER_GRAPH_DIRNAME,
    CLIENT_GRAPH_END_INT_NODE_TITLE,
    CLIENT_GRAPH_END_BOOL_NODE_TITLE,
)
from .flow_utils import (
    pick_default_flow_output_port,
    register_output_variables,
    materialize_call_node,
    handle_alias_assignment,
    warn_literal_assignment,
)
from .arg_normalizer import is_reserved_argument
from .local_var_builder import (
    should_model_as_local_var,
    build_local_var_nodes,
    LOCAL_HANDLE_PREFIX,
)
from .statement_flow_builder import (
    handle_if_statement,
    handle_match_statement,
    handle_match_over_composite_call,
    handle_for_loop,
)


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


def _stmt_assigns_to_name(stmt: ast.stmt, name: str) -> bool:
    """判断某条语句是否会为指定变量名赋值（Store）。

    说明：
    - 仅用于“占位初始化是否会被后续赋值覆盖”的线性判定；
    - 分支/循环等复杂结构由调用方选择保守处理。
    """
    name_text = str(name or "")
    if name_text == "":
        return False
    if isinstance(stmt, ast.Assign):
        for target in list(getattr(stmt, "targets", []) or []):
            if name_text in _collect_names(target):
                return True
        return False
    if isinstance(stmt, ast.AnnAssign):
        return name_text in _collect_names(getattr(stmt, "target", None))
    if isinstance(stmt, ast.AugAssign):
        return name_text in _collect_names(getattr(stmt, "target", None))
    if isinstance(stmt, ast.For):
        return name_text in _collect_names(getattr(stmt, "target", None))
    return False


def _is_placeholder_annassign_overwritten_before_use(
    *,
    var_name: str,
    remaining_statements: List[ast.stmt],
) -> bool:
    """判断“带类型注解的常量占位初始化”是否会在被使用前被后续赋值覆盖。

    典型代码模式（仅用于声明/类型提示）：
      x: "整数" = 0
      x = 某个节点输出 / 解包赋值(...)[...]

    这类占位初始化在节点图语义中应被视为“声明”，不应触发【获取局部变量】建模，
    否则会在画布上产生大量零散的“获取局部变量”纯数据节点（且多数无实际连线意义）。
    """
    name_text = str(var_name or "").strip()
    if name_text == "":
        return False
    for stmt in list(remaining_statements or []):
        # 遇到复杂控制流：保守处理，避免误删真正需要的初始化
        if isinstance(stmt, (ast.If, ast.Match, ast.For, ast.While, ast.Try)):
            return False
        used_names = _collect_used_names(stmt)
        if name_text in used_names:
            return False
        if _stmt_assigns_to_name(stmt, name_text):
            return True
    return False


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
    #
    # 重要：parse_method_body 会被递归用于 if/match/for 的分支体解析。
    # 若在递归入口清空 local_const_values，会导致“外层已声明的命名常量”在分支体内失效，
    # 从而出现节点输入端口无法回填常量、进而触发“缺少数据来源”的结构误报。
    #
    # 因此这里不清空已有常量，而是在当前作用域基础上增量补充/覆盖：
    # - 外层常量在分支体内仍可被引用；
    # - 分支体内新增/覆盖的常量在该次解析过程中可用。
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

    def _should_bypass_alias_assignment(value_expr: ast.expr, targets_obj: object) -> bool:
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
            if (not _should_bypass_alias_assignment(stmt.value, stmt.targets)) and handle_alias_assignment(
                stmt.value, stmt.targets, env, graph_model=graph_model
            ):
                continue
            
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
                    body[stmt_index + 1:],
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
            
        # 带类型注解的赋值语句（AnnAssign）
        elif isinstance(stmt, ast.AnnAssign):
            # 纯类型标注（无右值）仅用于阅读/类型提示，不应建模为任何节点。
            # 例如：`方向X: "浮点数"` 这类语句在旧逻辑中会被误判为“需要局部变量建模”，
            # 从而生成孤立的【获取局部变量】节点（无连线、无数据）。
            if stmt.value is None:
                continue

            # 记录中文类型注解（用于“字典禁用局部变量/列表引用策略”等）
            if isinstance(stmt.target, ast.Name):
                declared_type_text = _extract_annotation_type_text(stmt.annotation)
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
                    body[stmt_index + 1:],
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
            if (not _should_bypass_alias_assignment(stmt.value, stmt.target)) and handle_alias_assignment(
                stmt.value,
                stmt.target,
                env,
                graph_model=graph_model,
                annotation_type=_extract_annotation_type_text(stmt.annotation),
            ):
                continue

            # 单变量注解赋值优先尝试局部变量建模
            if isinstance(stmt.target, ast.Name) and should_model_as_local_var(
                stmt.target.id,
                stmt.value,
                body[stmt_index + 1:],
                env,
            ):
                # 占位初始化特判：若当前 AnnAssign 只是“声明/类型提示”，且会在被读取前被后续赋值覆盖，
                # 则不应触发【获取局部变量】建模（否则会产生大量零散局部变量节点）。
                if isinstance(stmt.value, ast.Constant) and _is_placeholder_annassign_overwritten_before_use(
                    var_name=stmt.target.id,
                    remaining_statements=body[stmt_index + 1:],
                ):
                    continue
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
                    register_output_variables(
                        result.node,
                        stmt.target,
                        env,
                        node_library=ctx.node_library,
                    )

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
        elif isinstance(stmt, ast.Return):
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
        elif isinstance(stmt, ast.Break):
            if not env.loop_stack:
                line_no = getattr(stmt, 'lineno', '?')
                validators.error(f"行{line_no}: 发现 break 但不在循环体内；该写法无法可靠解析为节点图语义")
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



