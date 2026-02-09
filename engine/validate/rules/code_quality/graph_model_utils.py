"""GraphModel 解析与图遍历辅助函数（供 code_quality 规则复用）。

说明：
- validate 阶段需要“尽力解析”（strict=False），以便在源码不完全合规时仍尽可能产出更多规则问题；
- 复用 validate 流程中已改写（rewrite）过的 AST，避免同一套改写逻辑跑两遍。
"""

from __future__ import annotations

import ast
from typing import Dict, List, Optional, Set, Tuple

from engine.graph.common import TARGET_ENTITY_PORT_NAME, VARIABLE_NAME_PORT_NAME
from engine.graph.graph_code_parser import GraphCodeParser
from engine.utils.graph.graph_utils import is_flow_port_name

from ...context import ValidationContext
from ..ast_utils import get_cached_module


def _get_or_parse_graph_model(ctx: ValidationContext):
    cached = getattr(ctx, "graph_model", None)
    if cached is not None:
        return cached
    if ctx.file_path is None:
        return None
    # validate 阶段需要“尽力解析”以便产出尽可能多的规则问题；不能启用严格 fail-closed。
    parser = GraphCodeParser(ctx.workspace_path, strict=False)
    # 复用 validate 流程中已被 rewrite 规则改写过的 AST，避免“同一套改写逻辑跑两遍”。
    rewritten_tree = get_cached_module(ctx)
    model, _ = parser.parse_file(
        ctx.file_path,
        tree=rewritten_tree,
        assume_tree_already_rewritten=True,
    )
    ctx.graph_model = model
    return model


def _build_incoming_data_edge_index(graph_model) -> Dict[str, Dict[str, object]]:
    incoming: Dict[str, Dict[str, object]] = {}
    for edge in graph_model.edges.values():
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if is_flow_port_name(dst_port):
            continue
        dst_node = str(getattr(edge, "dst_node", "") or "")
        if not dst_node:
            continue
        per_node = incoming.setdefault(dst_node, {})
        # 多源输入由更底层结构规则处理；这里仅取第一条作为“定位辅助”
        if dst_port not in per_node:
            per_node[dst_port] = edge
    return incoming


def _build_flow_next_index(graph_model) -> Dict[str, List[str]]:
    next_map: Dict[str, List[str]] = {}
    for edge in graph_model.edges.values():
        dst_port = str(getattr(edge, "dst_port", "") or "")
        if not is_flow_port_name(dst_port):
            continue
        src_node = str(getattr(edge, "src_node", "") or "")
        dst_node = str(getattr(edge, "dst_node", "") or "")
        if not src_node or not dst_node:
            continue
        next_map.setdefault(src_node, []).append(dst_node)
    return next_map


def _collect_downstream_flow_nodes(flow_next_map: Dict[str, List[str]], start_node_id: str) -> Set[str]:
    visited: Set[str] = set()
    queue: List[str] = [start_node_id]
    while queue:
        current = queue.pop()
        for next_node_id in flow_next_map.get(current, []):
            if next_node_id in visited:
                continue
            visited.add(next_node_id)
            queue.append(next_node_id)
    visited.discard(start_node_id)
    return visited


def _describe_input_source(
    graph_model,
    incoming_data_edges: Dict[str, Dict[str, object]],
    node_id: str,
    port_name: str,
) -> Tuple[str, str]:
    node = graph_model.nodes.get(node_id)
    incoming = incoming_data_edges.get(node_id, {}).get(port_name)
    if incoming is not None:
        src_node_id = str(getattr(incoming, "src_node", "") or "")
        src_port = str(getattr(incoming, "src_port", "") or "")
        src_node = graph_model.nodes.get(src_node_id)
        src_title = src_node.title if src_node else src_node_id
        return f"{src_title}.{src_port}", f"edge:{src_node_id}:{src_port}"
    if node is not None and port_name in (node.input_constants or {}):
        raw = node.input_constants.get(port_name)
        value_text = str(raw)
        return f"常量({value_text})", f"const:{value_text}"
    return "未绑定", "unbound"


def _custom_var_key(
    graph_model,
    incoming_data_edges: Dict[str, Dict[str, object]],
    node_id: str,
) -> Optional[Tuple[str, str]]:
    node = graph_model.nodes.get(node_id)
    if node is None:
        return None
    # 仅支持“获取/设置自定义变量”的标准端口名
    _entity_description, entity_source_key = _describe_input_source(
        graph_model, incoming_data_edges, node_id, TARGET_ENTITY_PORT_NAME
    )
    _var_name_description, variable_name_source_key = _describe_input_source(
        graph_model, incoming_data_edges, node_id, VARIABLE_NAME_PORT_NAME
    )
    if entity_source_key == "unbound" or variable_name_source_key == "unbound":
        return None
    return (entity_source_key, variable_name_source_key)


def _span_for_graph_nodes(graph_model, node_ids: List[str]) -> Optional[str]:
    points: List[int] = []
    for node_id in node_ids:
        node = graph_model.nodes.get(node_id)
        if node is None:
            continue
        start_line = getattr(node, "source_lineno", 0) or 0
        end_line = getattr(node, "source_end_lineno", 0) or 0
        if isinstance(start_line, int) and start_line > 0:
            points.append(start_line)
        if isinstance(end_line, int) and end_line > 0:
            points.append(end_line)
    if not points:
        return None
    return f"{min(points)}~{max(points)}"


def _canonicalize_node_id(graph_model, node_id: str) -> str:
    """将数据节点副本（copy）规约到其 original_node_id。

    说明：
    - 布局层可能为跨块共享的数据节点创建副本（node.is_data_node_copy=True），
      以提升可读性；这些副本在结构上仍代表“同一数据源”。
    - 本规则希望识别“同一读取节点实例”的复用风险，因此需要将副本规约回原始节点，
      否则在 for/match 等多块结构中会出现漏报。
    """
    current = str(node_id or "")
    depth = 0
    while current and depth < 8:
        node = graph_model.nodes.get(current) if hasattr(graph_model, "nodes") else None
        if node is None:
            break
        if not bool(getattr(node, "is_data_node_copy", False)):
            break
        origin = str(getattr(node, "original_node_id", "") or "")
        if not origin:
            break
        current = origin
        depth += 1
    return current


def _single_target_name(targets: List[ast.expr]) -> str | None:
    """获取赋值目标名称（仅支持单个名称）"""
    if len(targets) != 1:
        return None
    tgt = targets[0]
    if isinstance(tgt, ast.Name):
        return tgt.id
    return None


