from __future__ import annotations

import uuid
from typing import Dict, List, Optional, Tuple, Any, Union

from engine.graph.models import NodeModel, EdgeModel
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


def _pick_flow_src_port(src_node: NodeModel) -> Optional[str]:
    # 特例：分支/循环节点的默认出口
    if src_node.title in ["双分支", "多分支"]:
        for p in src_node.outputs:
            if p.name == "默认":
                return "默认"
        # 对双分支通常不自动接续，返回 None 以抑制
        return None
    if src_node.title in ["有限循环", "列表迭代循环"]:
        for p in src_node.outputs:
            if p.name == "循环完成":
                return "循环完成"
    # 常规：选择第一个流程型输出口
    for p in src_node.outputs:
        if is_flow_port_ctx(src_node, p.name, True):
            return p.name
    # 兜底：若无任何标注为流程的输出，取第一个输出
    return src_node.outputs[0].name if src_node.outputs else None


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



