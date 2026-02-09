from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from engine.nodes.advanced_node_features import SignalDefinition
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import (
    build_node_map,
    get_node_display_info,
)
from engine.graph.common import SIGNAL_NAME_PORT_NAME
from engine.validate.node_semantics import (
    SEMANTIC_SIGNAL_LISTEN,
    SEMANTIC_SIGNAL_SEND,
    is_semantic_graph_node,
)

from ...comprehensive_types import ValidationIssue
from ..helpers import GraphAttachment, get_graph_snapshot
from .constants_type import validate_signal_constants_for_send_node
from .edge_index import build_edge_indices, merge_edges_with_connections
from .node_def_resolver import build_node_defs_for_nodes
from .port_coverage import validate_signal_ports_for_node
from .signal_binding import infer_signal_id_from_constants
from .wire_types import (
    validate_signal_wire_types_for_listen_node,
    validate_signal_wire_types_for_send_node,
)


def validate_signals_in_single_graph(
    workspace_path: Path,
    attachment: GraphAttachment,
    signal_definitions: Dict[str, SignalDefinition],
    signal_param_types: Dict[str, Dict[str, str]],
    node_library: Dict[str, NodeDef],
) -> List[ValidationIssue]:
    graph_config = attachment.graph_config
    graph_data = graph_config.data or {}
    if "nodes" not in graph_data:
        return []

    snapshot = get_graph_snapshot(graph_data, cache_key=attachment.graph_id)
    nodes = snapshot.nodes
    if not nodes:
        return []

    signal_bindings = (graph_data.get("metadata") or {}).get("signal_bindings") or {}
    nodes_by_id = build_node_map(nodes)
    node_defs_by_id = build_node_defs_for_nodes(
        nodes,
        node_library,
        scope_text=str(getattr(graph_config, "graph_type", "") or "server"),
    )
    merged_edges = merge_edges_with_connections(snapshot.edges, snapshot.connections)
    incoming_edges, outgoing_edges = build_edge_indices(merged_edges)

    base_location = attachment.location_compact
    base_detail = dict(attachment.detail)
    base_detail["graph_id"] = attachment.graph_id
    base_detail["graph_name"] = graph_config.name

    issues: List[ValidationIssue] = []
    for node in nodes:
        node_id, node_title, node_category = get_node_display_info(node)
        if not node_id:
            continue

        is_send_node = is_semantic_graph_node(
            workspace_path=workspace_path,
            node_library=node_library,
            node_category=str(node_category or ""),
            node_title=str(node_title or ""),
            scope_text=str(getattr(graph_config, "graph_type", "") or "server"),
            semantic_id=SEMANTIC_SIGNAL_SEND,
        )
        is_listen_node = is_semantic_graph_node(
            workspace_path=workspace_path,
            node_library=node_library,
            node_category=str(node_category or ""),
            node_title=str(node_title or ""),
            scope_text=str(getattr(graph_config, "graph_type", "") or "server"),
            semantic_id=SEMANTIC_SIGNAL_LISTEN,
        )
        if not (is_send_node or is_listen_node):
            continue

        node_detail = dict(base_detail)
        node_detail["node_id"] = node_id
        node_detail["node_title"] = node_title

        node_location = f"{base_location} > 节点 '{node_title}' (ID: {node_id})"
        binding_info = signal_bindings.get(node_id) or {}
        bound_signal_id = str(binding_info.get("signal_id") or "")

        # 3.1 信号存在性校验（带“信号名”常量的智能回退）。
        if not bound_signal_id:
            inferred_signal_id = infer_signal_id_from_constants(
                node=node,
                signal_definitions=signal_definitions,
            )
            if inferred_signal_id:
                bound_signal_id = inferred_signal_id

        if not bound_signal_id:
            message = (
                "发送信号节点未选择信号" if is_send_node else "监听信号节点未选择信号"
            )
            issues.append(
                ValidationIssue(
                    level="error",
                    category="信号系统",
                    location=node_location,
                    message=message,
                    suggestion="请在节点上选择有效的信号定义，或在信号管理中先创建所需信号。",
                    reference="信号系统设计.md:3.1 信号存在性校验",
                    detail=node_detail,
                )
            )
            continue

        node_detail["signal_id"] = bound_signal_id
        signal_def = signal_definitions.get(bound_signal_id)
        if signal_def is None:
            signal_name_constant = ""
            input_constants = node.get("input_constants", {}) or {}
            if isinstance(input_constants, dict) and SIGNAL_NAME_PORT_NAME in input_constants:
                signal_name_constant = str(input_constants.get(SIGNAL_NAME_PORT_NAME) or "")
            if signal_name_constant:
                node_detail["signal_name"] = signal_name_constant
            issues.append(
                ValidationIssue(
                    level="error",
                    category="信号系统",
                    location=node_location,
                    message="节点引用了在当前存档中不存在的信号（可能已被删除）。",
                    suggestion="请在信号管理中重新创建该信号，或在节点上选择一个现有的信号。",
                    reference="信号系统设计.md:3.1 信号存在性校验",
                    detail=node_detail,
                )
            )
            continue

        # 3.2 参数列表一致性校验（端口覆盖情况）
        issues.extend(
            validate_signal_ports_for_node(
                node,
                node_location,
                node_detail,
                signal_def,
                incoming_edges=incoming_edges,
                outgoing_edges=outgoing_edges,
            )
        )

        # 仅对发送信号节点执行 3.3 常量类型校验与 3.4 连线类型兼容性校验
        if is_send_node:
            issues.extend(
                validate_signal_constants_for_send_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                )
            )
            issues.extend(
                validate_signal_wire_types_for_send_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                    incoming_edges,
                    node_defs_by_id,
                )
            )
        elif is_listen_node:
            issues.extend(
                validate_signal_wire_types_for_listen_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                    outgoing_edges,
                    node_defs_by_id,
                )
            )

    return issues


__all__ = ["validate_signals_in_single_graph"]


