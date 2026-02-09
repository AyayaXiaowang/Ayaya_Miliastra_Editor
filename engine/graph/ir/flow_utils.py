"""流程构建工具函数

提供 parse_method_body 中使用的公共逻辑，减少重复代码。
"""
from __future__ import annotations

import ast
from typing import Any, Dict, List, Optional, Tuple, Union

from engine.graph.models import GraphModel, NodeModel, EdgeModel
from engine.graph.common import STRUCT_SPLIT_NODE_TITLE
from .var_env import VarEnv
from .validators import Validators
from .node_factory import FactoryContext, create_node_from_call, extract_nested_nodes
from .edge_router import (
    is_flow_node,
    is_event_node,
    connect_sources_to_target,
    create_data_edges_for_node_enhanced,
    pick_default_flow_output_port,
)
from .composite_builder import create_composite_node_from_instance_call


def register_output_variables(
    node: NodeModel,
    targets: Union[ast.Name, ast.Tuple, List[ast.expr]],
    env: VarEnv,
    *,
    node_library: Optional[Dict[str, Any]] = None,
) -> None:
    """注册节点输出变量到环境中
    
    支持：
    - 单变量赋值：target_var
    - 元组拆分赋值：var1, var2, var3
    
    Args:
        node: 输出节点
        targets: 赋值目标（可以是Name、Tuple或targets列表）
        env: 变量环境
    """
    # 获取所有数据输出端口（排除流程端口）
    #
    # 注意：
    # - 不能用“端口名是否包含『流程』”来判断流程口，因为像复合节点常见的流程出口名
    #   可能是“完成/成功/失败”等，不包含“流程”关键字；
    # - 必须优先使用 node_library 中的端口类型定义（FLOW_PORT_TYPE），回退时才用名称启发式。
    from engine.nodes.port_type_system import is_flow_port_with_context

    data_output_ports = [
        port.name
        for port in (node.outputs or [])
        if not is_flow_port_with_context(node, port.name, True, node_library)
    ]

    # 对于【拆分结构体】这类“纯数据拆分”节点，若尚未声明任何数据输出端口，
    # 则根据赋值目标动态补全一组输出端口，端口名与变量名一一对应。
    if not data_output_ports and getattr(node, "title", "") == STRUCT_SPLIT_NODE_TITLE:
        def _normalize_struct_split_output_port_name(raw_name: str) -> str:
            """结构体拆分的输出端口名归一化。

            约定：
            - 生成的 Graph Code 常用变量命名：`<字段名>字段`；
            - 部分图会在变量名末尾附加 UI/语义后缀：`<字段名>字段_<后缀>`（例如 `_控件`）；
            - 但结构体语义节点的动态端口应以“真实字段名”作为端口名（与 struct_bindings/结构体定义一致）。
            """
            text = str(raw_name or "").strip()
            marker_with_suffix = "字段_"
            idx = text.rfind(marker_with_suffix)
            if idx != -1 and idx + len(marker_with_suffix) < len(text):
                candidate = text[:idx].strip()
                return candidate if candidate else text
            if text.endswith("字段"):
                candidate = text[:-2].strip()
                return candidate if candidate else text
            return text

        inferred_names: List[str] = []

        # 处理 Assign 的 targets 列表（取第一个目标）
        effective_targets: Union[ast.Name, ast.Tuple, List[ast.expr]]
        if isinstance(targets, list):
            if not targets:
                return
            effective_targets = targets[0]
        else:
            effective_targets = targets

        if isinstance(effective_targets, ast.Tuple):
            for elt in effective_targets.elts:
                if isinstance(elt, ast.Name):
                    name_text = elt.id.strip()
                    port_name = _normalize_struct_split_output_port_name(name_text)
                    if port_name and port_name not in inferred_names:
                        inferred_names.append(port_name)
        elif isinstance(effective_targets, ast.Name):
            name_text = effective_targets.id.strip()
            if name_text:
                port_name = _normalize_struct_split_output_port_name(name_text)
                if port_name:
                    inferred_names.append(port_name)

        for name in inferred_names:
            node.add_output_port(name)

        data_output_ports = [
            port.name
            for port in (node.outputs or [])
            if not is_flow_port_with_context(node, port.name, True, node_library)
        ]

    if not data_output_ports:
        return
    
    # 处理 Assign 的 targets 列表（取第一个目标）
    if isinstance(targets, list):
        if not targets:
            return
        target = targets[0]
    else:
        target = targets
    
    # 单变量赋值
    if isinstance(target, ast.Name):
        env.set_variable(target.id, node.id, data_output_ports[0])
    
    # 元组拆分赋值
    elif isinstance(target, ast.Tuple):
        for idx, elt in enumerate(target.elts):
            if isinstance(elt, ast.Name) and idx < len(data_output_ports):
                env.set_variable(elt.id, node.id, data_output_ports[idx])


class MaterializedNodeResult:
    """节点物化结果
    
    封装节点创建、流程连接、数据边生成的完整结果。
    """
    
    def __init__(self):
        self.node: Optional[NodeModel] = None
        self.nested_nodes: List[NodeModel] = []
        self.edges: List[EdgeModel] = []
        self.is_composite: bool = False
        self.should_skip: bool = False
        self.new_prev_flow_node: Optional[NodeModel] = None
        self.new_suppress_flag: bool = False


def materialize_call_node(
    call_expr: ast.Call,
    stmt: ast.stmt,
    prev_flow_node: Optional[Union[NodeModel, List[Union[NodeModel, Tuple[NodeModel, str]]]]],
    need_suppress_once: bool,
    graph_model: GraphModel,
    ctx: FactoryContext,
    env: VarEnv,
    validators: Validators,
    check_unused: bool = False,
    later_stmts: Optional[List[ast.stmt]] = None,
    assigned_names: Optional[List[str]] = None,
) -> MaterializedNodeResult:
    """物化调用节点的通用逻辑
    
    处理：
    1. 识别复合节点调用（self.xxx.yyy()）
    2. 识别普通属性调用并警告
    3. 创建普通节点（含嵌套调用展开）
    4. 流程连接
    5. 数据边生成
    
    Args:
        call_expr: 调用表达式AST节点
        stmt: 包含该调用的语句（用于获取行号）
        prev_flow_node: 前驱流程节点
        need_suppress_once: 是否需要抑制首条流程边
        ctx: 工厂上下文
        env: 变量环境
        validators: 验证器
        check_unused: 是否检查未使用的赋值（用于优化）
        later_stmts: 后续语句列表（用于检查变量是否被使用）
        assigned_names: 赋值的变量名列表（用于未使用检查）
        
    Returns:
        MaterializedNodeResult 对象，包含创建的节点、边、流程状态等信息
    """
    result = MaterializedNodeResult()
    line_no = getattr(stmt, 'lineno', '?')
    
    # 1. 检查是否是复合节点实例方法调用
    if isinstance(call_expr.func, ast.Attribute):
        composite_node = create_composite_node_from_instance_call(call_expr, ctx.node_library, env)
        
        if composite_node:
            # 这是复合节点调用
            result.node = composite_node
            result.is_composite = True
            result.nested_nodes = []
            
            # 流程连接
            if is_flow_node(composite_node):
                if prev_flow_node:
                    if not need_suppress_once:
                        connect_sources_to_target(prev_flow_node, composite_node, result.edges)
                result.new_prev_flow_node = composite_node
                result.new_suppress_flag = False
            
            # 数据边：复合节点调用同样需要支持参数内的嵌套节点（如 `右值=加法运算(...)`）。
            nested_nodes, nested_edges, param_node_map = extract_nested_nodes(
                call_expr,
                ctx,
                validators,
                env,
            )
            result.nested_nodes = nested_nodes
            result.edges.extend(nested_edges)

            data_edges = create_data_edges_for_node_enhanced(
                composite_node,
                call_expr,
                param_node_map,
                ctx.node_library,
                ctx.node_name_index,
                env,
            )
            result.edges.extend(data_edges)
            
            return result
        
        # 不是复合节点调用，发出警告
        obj_name = ast.unparse(call_expr.func.value) if hasattr(ast, 'unparse') else '?'
        method_name = call_expr.func.attr
        validators.error(
            f"行{line_no}: 发现Python原生方法调用 {obj_name}.{method_name}()；该写法无法可靠解析为节点图语义，请改用节点替代"
        )
        result.should_skip = True
        return result
    
    # 2. 预判：纯数据节点的未使用检查
    preview = create_node_from_call(call_expr, ctx, validators, env=env)
    if preview and check_unused and assigned_names and later_stmts is not None:
        if (not is_flow_node(preview)) and (not is_event_node(preview)):
            # 检查赋值变量是否被后续使用
            if not any(_is_name_used_in_stmts(later_stmts, name) for name in assigned_names):
                result.should_skip = True
                return result
    
    # 3. 裸表达式的纯数据节点跳过（check_unused=False 且 assigned_names 为空时）
    if preview and not check_unused and not assigned_names:
        if (not is_flow_node(preview)) and (not is_event_node(preview)):
            result.should_skip = True
            return result
    
    # 4. 提取嵌套节点
    nested_nodes, nested_edges, param_node_map = extract_nested_nodes(call_expr, ctx, validators, env)
    result.nested_nodes = nested_nodes
    result.edges.extend(nested_edges)
    
    # 5. 创建节点
    node = preview or create_node_from_call(call_expr, ctx, validators, env=env)
    if not node:
        result.should_skip = True
        return result
    
    result.node = node
    
    # 6. 流程连接
    if is_flow_node(node):
        is_event = is_event_node(node)
        if prev_flow_node and (not is_event):
            if not need_suppress_once:
                connect_sources_to_target(prev_flow_node, node, result.edges)
        result.new_prev_flow_node = node
        result.new_suppress_flag = False
    else:
        # 非流程节点，保持原流程状态
        result.new_prev_flow_node = prev_flow_node
        result.new_suppress_flag = need_suppress_once
    
    # 7. 数据边
    data_edges = create_data_edges_for_node_enhanced(
        node, call_expr, param_node_map, ctx.node_library, ctx.node_name_index, env
    )
    result.edges.extend(data_edges)
    
    return result


def _is_name_used_in_stmts(stmts: List[ast.stmt], name: str) -> bool:
    """检查变量名是否在语句列表中被使用（Load上下文）
    
    Args:
        stmts: 语句列表
        name: 变量名
        
    Returns:
        True表示被使用，False表示未被使用
    """
    for stmt in stmts:
        for sub in ast.walk(stmt):
            if isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load):
                return True
    return False


def handle_alias_assignment(
    value_expr: ast.expr,
    targets: Union[ast.Name, List[ast.expr]],
    env: VarEnv,
    *,
    graph_model: GraphModel | None = None,
    annotation_type: str = "",
) -> bool:
    """处理纯别名赋值（变量到变量的直接赋值）
    
    例如：new_var = old_var 或 new_var: "类型" = old_var
    
    Args:
        value_expr: 赋值右侧表达式
        targets: 赋值目标（Name 或 targets 列表）
        env: 变量环境
        
    Returns:
        True 表示成功处理了别名赋值，False 表示不是别名赋值
    """
    if not isinstance(value_expr, ast.Name):
        return False
    
    src_name = value_expr.id
    if src_name in ['self', 'game', 'owner_entity']:
        return False
    
    src = env.get_variable(src_name)
    if not src:
        return False
    
    src_node_id, src_port = src

    # 带类型注解的“纯别名赋值”在 Graph Code 中常用于“绑定事件/信号的泛型输出端口类型”：
    #
    # 例如（监听信号事件回调）：
    #   整数参数别名: "整数" = 整数参数
    #
    # 其中 `整数参数` 的数据来源是事件节点的输出端口（在图上通常声明为“泛型”），
    # 作者通过注解明确该参数的具体类型。为了让画布与结构校验也能得到确定类型，
    # 需要把该注解写回到 GraphModel.metadata["port_type_overrides"]，从而实例化端口类型。
    annotation_text = str(annotation_type or "").strip()
    if graph_model is not None and annotation_text and annotation_text != "泛型":
        overrides_raw = graph_model.metadata.get("port_type_overrides")
        overrides: Dict[str, Dict[str, str]] = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}
        node_overrides = overrides.get(src_node_id)
        node_overrides = dict(node_overrides) if isinstance(node_overrides, dict) else {}
        # 仅当来源端口当前未被更具体的覆盖绑定时才写入（避免覆盖已有确定类型）
        existing = str(node_overrides.get(src_port, "") or "").strip()
        if not existing:
            node_overrides[src_port] = annotation_text
            overrides[src_node_id] = node_overrides
            graph_model.metadata["port_type_overrides"] = overrides
    
    # 处理 Assign 的 targets 列表
    if isinstance(targets, list):
        for target in targets:
            if isinstance(target, ast.Name):
                env.set_variable(target.id, src_node_id, src_port)
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        env.set_variable(elt.id, src_node_id, src_port)
    # 处理 AnnAssign 的单个 target
    elif isinstance(targets, ast.Name):
        env.set_variable(targets.id, src_node_id, src_port)
    
    return True


def warn_literal_assignment(
    value_expr: ast.expr,
    targets: Union[ast.Name, List[ast.expr]],
    stmt: ast.stmt,
    validators: Validators,
) -> None:
    """对字面量赋值发出警告
    
    检测：
    - f-string 赋值
    - 列表字面量赋值
    - 字典字面量赋值
    
    Args:
        value_expr: 赋值右侧表达式
        targets: 赋值目标
        stmt: 赋值语句（用于获取行号）
        validators: 验证器
    """
    line_no = getattr(stmt, 'lineno', '?')
    
    # 获取变量名
    var_name = '?'
    if isinstance(targets, list) and targets:
        if isinstance(targets[0], ast.Name):
            var_name = targets[0].id
    elif isinstance(targets, ast.Name):
        var_name = targets.id
    
    # 检查不同类型的字面量
    if isinstance(value_expr, ast.JoinedStr):
        validators.error(
            f"行{line_no}: 发现f-string赋值 ({var_name})；该写法无法可靠解析为节点图语义，请改用字符串操作节点"
        )
    elif isinstance(value_expr, ast.List):
        validators.error(
            f"行{line_no}: 发现列表字面量赋值 ({var_name})；该写法无法可靠解析为节点图语义，请改用拼装列表节点"
        )
    elif isinstance(value_expr, ast.Dict):
        validators.error(
            f"行{line_no}: 发现字典字面量赋值 ({var_name})；该写法无法可靠解析为节点图语义，请改用建立字典节点"
        )






