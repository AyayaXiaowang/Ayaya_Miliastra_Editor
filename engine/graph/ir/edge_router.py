from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple, Any, Union

from engine.graph.models import NodeModel, EdgeModel
from engine.graph.common import is_branch_node_name, is_loop_node_name
from engine.nodes.port_type_system import is_flow_port_with_context as _is_flow_port_ctx
from .var_env import VarEnv
from .arg_normalizer import normalize_call_arguments, is_reserved_argument


SourceLike = Union[NodeModel, Tuple[NodeModel, str]]


def is_flow_port_ctx(node: Optional[NodeModel], port_name: str, is_source: bool) -> bool:
    return _is_flow_port_ctx(node, port_name, is_source)


def is_flow_node(node: NodeModel) -> bool:
    has_flow_out = any(is_flow_port_ctx(node, p.name, True) for p in node.outputs)
    has_flow_in = any(is_flow_port_ctx(node, p.name, False) for p in node.inputs)
    return has_flow_in or has_flow_out


def is_event_node(node: NodeModel) -> bool:
    has_flow_in = any(is_flow_port_ctx(node, p.name, False) for p in node.inputs)
    has_flow_out = any(is_flow_port_ctx(node, p.name, True) for p in node.outputs)
    return (not has_flow_in) and has_flow_out


def pick_default_flow_output_port(src_node: NodeModel) -> Optional[str]:
    """选择节点的默认流程输出端口。

    统一封装分支/循环节点与普通流程节点的默认出口选择策略，
    供流程边路由和 break 之类的控制流跳转复用。
    """
    # 1) 先按端口名称优先级选择基础默认口（兼容旧 flow_utils 行为）
    base_port_name: Optional[str] = None
    for priority_name in ("流程出", "流程", "执行"):
        for output_port in src_node.outputs:
            if output_port.name == priority_name:
                base_port_name = priority_name
                break
        if base_port_name is not None:
            break

    if base_port_name is None and src_node.outputs:
        base_port_name = src_node.outputs[0].name

    # 2) 分支与循环节点特例：覆盖基础默认口（保持与原有 break 逻辑一致）
    if is_branch_node_name(src_node.title):
        for output_port in src_node.outputs:
            if output_port.name == "默认":
                return "默认"
        # 没有“默认”出口时退回基础策略，由调用方决定是否允许自动接续
        return base_port_name

    if is_loop_node_name(src_node.title):
        for output_port in src_node.outputs:
            if output_port.name == "循环完成":
                return "循环完成"
        return base_port_name

    # 3) 普通节点：若基础端口是流程端口则直接返回，否则退化为首个流程端口/首个输出
    if base_port_name is not None:
        for output_port in src_node.outputs:
            if (
                output_port.name == base_port_name
                and is_flow_port_ctx(src_node, output_port.name, True)
            ):
                return base_port_name

    for output_port in src_node.outputs:
        if is_flow_port_ctx(src_node, output_port.name, True):
            return output_port.name

    return base_port_name


def _pick_flow_src_port(src_node: NodeModel) -> Optional[str]:
    """内部使用的默认流程出口选择。

    与 `pick_default_flow_output_port` 共用主体逻辑，但对不带“默认”出口的分支节点
    继续保持“不要自动接续后续流程”的抑制行为。
    """
    if is_branch_node_name(src_node.title):
        has_default_port = any(
            output_port.name == "默认" for output_port in src_node.outputs
        )
        if not has_default_port:
            return None
    return pick_default_flow_output_port(src_node)


def _pick_flow_dst_port(dst_node: NodeModel) -> Optional[str]:
    for p in dst_node.inputs:
        if is_flow_port_ctx(dst_node, p.name, False):
            return p.name
    return None


def create_flow_edge(src_node: NodeModel, dst_node: NodeModel) -> Optional[EdgeModel]:
    src_port = _pick_flow_src_port(src_node)
    if src_port is None:
        return None
    dst_port = _pick_flow_dst_port(dst_node)
    if dst_port is None:
        return None
    return EdgeModel(
        id=str(uuid.uuid4()),
        src_node=src_node.id,
        src_port=src_port,
        dst_node=dst_node.id,
        dst_port=dst_port,
    )


def connect_source_to_target(source: SourceLike, target: NodeModel, edges: List[EdgeModel]) -> None:
    if isinstance(source, tuple) and len(source) == 2:
        src_node, forced_src_port = source
        dst_port = _pick_flow_dst_port(target)
        if dst_port is None:
            return
        edges.append(EdgeModel(
            id=str(uuid.uuid4()),
            src_node=src_node.id,
            src_port=forced_src_port,
            dst_node=target.id,
            dst_port=dst_port,
        ))
        return
    edge = create_flow_edge(source, target)
    if edge:
        edges.append(edge)


def connect_sources_to_target(sources: Union[SourceLike, List[SourceLike]], target: NodeModel, edges: List[EdgeModel]) -> None:
    if isinstance(sources, list):
        for s in sources:
            connect_source_to_target(s, target, edges)
    else:
        connect_source_to_target(sources, target, edges)


def create_data_edges_for_node(node: NodeModel, call_node: Any, var_env: VarEnv) -> List[EdgeModel]:
    """基础版本：仅处理关键字参数中的变量引用。"""
    import ast
    edges: List[EdgeModel] = []
    if not isinstance(call_node, ast.Call):
        return edges
    for keyword in call_node.keywords:
        param_name = keyword.arg
        if isinstance(keyword.value, ast.Name):
            var_name = keyword.value.id
            if var_name in ['self', 'game', 'owner_entity']:
                continue
            src = var_env.get_variable(var_name)
            if src:
                src_node_id, src_port = src
                edges.append(EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=src_node_id,
                    src_port=src_port,
                    dst_node=node.id,
                    dst_port=param_name,
                ))
    return edges


def create_data_edges_for_node_enhanced(
    node: NodeModel,
    call_node: Any,
    param_node_map: Dict[str, NodeModel],
    node_library: Dict[str, Any],
    node_name_index: Dict[str, str],
    var_env: VarEnv,
) -> List[EdgeModel]:
    """增强版本：支持位置/关键字参数与嵌套调用的出入边生成。"""
    import ast
    edges: List[EdgeModel] = []
    if not isinstance(call_node, ast.Call):
        return edges

    func_key = node_name_index.get(node.title)
    node_def = node_library.get(func_key) if func_key else None
    if not node_def:
        return edges

    norm = normalize_call_arguments(call_node, node_def)

    # 位置参数：根据归一化映射生成连线
    for dst_port, expr in norm.positional:
        if isinstance(expr, ast.Name):
            if is_reserved_argument(expr):
                continue
            var_name = expr.id
            src = var_env.get_variable(var_name)
            if src:
                src_node_id, src_port_name = src
                edges.append(EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=src_node_id,
                    src_port=src_port_name,
                    dst_node=node.id,
                    dst_port=dst_port,
                ))
        elif isinstance(expr, ast.Call):
            nested_node = param_node_map.get(dst_port)
            if nested_node:
                out_name: Optional[str] = None
                for p in nested_node.outputs:
                    if not is_flow_port_ctx(nested_node, p.name, True):
                        out_name = p.name
                        break
                if out_name:
                    edges.append(EdgeModel(
                        id=str(uuid.uuid4()),
                        src_node=nested_node.id,
                        src_port=out_name,
                        dst_node=node.id,
                        dst_port=dst_port,
                    ))

    # 关键字参数
    for param_name, value_expr in norm.keywords.items():
        if isinstance(value_expr, ast.Name):
            if is_reserved_argument(value_expr):
                continue
            var_name = value_expr.id
            src = var_env.get_variable(var_name)
            if src:
                src_node_id, src_port_name = src
                edges.append(EdgeModel(
                    id=str(uuid.uuid4()),
                    src_node=src_node_id,
                    src_port=src_port_name,
                    dst_node=node.id,
                    dst_port=param_name,
                ))
        elif isinstance(value_expr, ast.Call):
            nested_node = param_node_map.get(param_name)
            if nested_node:
                out_name2: Optional[str] = None
                for p in nested_node.outputs:
                    if not is_flow_port_ctx(nested_node, p.name, True):
                        out_name2 = p.name
                        break
                if out_name2:
                    edges.append(EdgeModel(
                        id=str(uuid.uuid4()),
                        src_node=nested_node.id,
                        src_port=out_name2,
                        dst_node=node.id,
                        dst_port=param_name,
                    ))

    return edges



