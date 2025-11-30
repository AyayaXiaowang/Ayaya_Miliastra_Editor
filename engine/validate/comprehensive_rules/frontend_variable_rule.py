from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from engine.utils.graph.graph_utils import build_connection_map, build_node_map, get_node_display_info

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import get_graph_snapshot, iter_all_package_graphs


class FrontendVariableRule(BaseComprehensiveRule):
    rule_id = "package.frontend_variable_usage"
    category = "前端变量使用限制"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_frontend_variable_usage(self.validator)


def validate_frontend_variable_usage(validator) -> List[ValidationIssue]:
    if not validator.resource_manager:
        return []
    issues: List[ValidationIssue] = []
    attachments = iter_all_package_graphs(
        validator.resource_manager,
        validator.package.templates,
        validator.package.instances,
        validator.package.level_entity,
    )
    for attachment in attachments:
        if not attachment.entity_type:
            continue
        is_self_allowed = attachment.entity_type in {"玩家", "关卡"}
        issues.extend(
            check_frontend_variable_in_graph(
                attachment.graph_config.data,
                attachment.location_compact,
                attachment.detail,
                is_self_allowed,
                cache_key=attachment.graph_id,
            )
        )
    return issues


def check_frontend_variable_in_graph(
    graph_data: Dict,
    location: str,
    detail: Dict,
    is_self_allowed: bool,
    cache_key: Optional[str] = None,
) -> List[ValidationIssue]:
    if not graph_data or "nodes" not in graph_data:
        return []
    snapshot = get_graph_snapshot(graph_data, cache_key)
    nodes = snapshot.nodes
    if not _is_client_side_graph(nodes):
        return []
    connection_map = _build_combined_connection_map(snapshot)
    node_map = build_node_map(nodes)
    node_issues: List[ValidationIssue] = []
    for node in nodes:
        node_id, node_title, _ = get_node_display_info(node)
        if node_title != "获取自定义变量":
            continue
        entity_source = _trace_entity_source(
            node_id,
            "目标实体",
            connection_map,
            node_map,
        )
        if not entity_source:
            continue
        source_title = entity_source.get("title", "")
        if source_title == "获取自身实体" and is_self_allowed:
            continue
        allowed_sources = ["获取关卡实体", "获取玩家实体", "获取本地玩家"]
        if is_self_allowed:
            allowed_sources.append("获取自身实体")
        if source_title in allowed_sources:
            continue
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        node_detail["violation_type"] = "frontend_variable_restriction"
        node_detail["source_title"] = source_title or "未知实体"
        node_issues.append(
            ValidationIssue(
                level="error",
                category="前端变量使用限制",
                location=f"{location} > 节点 '{node_title}' (ID: {node_id})",
                message=(
                    "客户端节点图不能读取非关卡/玩家实体的自定义变量。"
                    f"当前读取来源：{source_title or '未知实体'}"
                ),
                suggestion="请将需要在前端显示的变量存储在关卡或玩家实体上。",
                reference="前端变量使用规则.md",
                detail=node_detail,
            )
        )
    return node_issues


def _is_client_side_graph(nodes: List[Dict]) -> bool:
    client_only_nodes = {
        "播放限时特效",
        "定点发射投射物",
        "定点位移",
        "显示UI",
        "隐藏UI",
        "设置UI文本",
        "客户端",
    }
    for node in nodes:
        _, node_title, node_category = get_node_display_info(node)
        if node_title in client_only_nodes:
            return True
        if "客户端" in node_category:
            return True
    return False


def _build_combined_connection_map(snapshot) -> Dict[Tuple[str, str], Tuple[str, str]]:
    connection_map = build_connection_map(snapshot.connections)
    for edge in snapshot.edges:
        src_node = edge.get("src_node") or edge.get("source") or edge.get("from_node")
        src_port = edge.get("src_port") or edge.get("source_port") or edge.get("from_output")
        dst_node = edge.get("dst_node") or edge.get("target") or edge.get("to_node")
        dst_port = edge.get("dst_port") or edge.get("target_port") or edge.get("to_input")
        if not (src_node and src_port and dst_node and dst_port):
            continue
        key = (dst_node, dst_port)
        if key not in connection_map:
            connection_map[key] = (src_node, src_port)
    return connection_map


def _trace_entity_source(
    node_id: str,
    port_name: str,
    connection_map: Dict[Tuple[str, str], Tuple[str, str]],
    node_map: Dict[str, Dict],
) -> Optional[Dict]:
    visited: set[Tuple[str, str]] = set()
    stack: List[Tuple[str, str]] = [(node_id, port_name)]
    entity_query_nodes = {
        "获取自身实体",
        "获取关卡实体",
        "获取玩家实体",
        "获取本地玩家",
        "获取实体位置",
        "遍历实体列表",
        "获取单位标签的实体列表",
    }
    step_limit = max(len(connection_map), 1) * 2
    steps = 0
    while stack and steps < step_limit:
        current_node_id, current_port = stack.pop()
        steps += 1
        conn_key = (current_node_id, current_port)
        if conn_key not in connection_map:
            continue
        from_node_id, from_port = connection_map[conn_key]
        if (from_node_id, from_port) in visited:
            continue
        visited.add((from_node_id, from_port))
        source_node = node_map.get(from_node_id)
        if not source_node:
            continue
        source_title = source_node.get("title", "")
        if source_title in entity_query_nodes:
            return source_node
        if source_title == "遍历实体列表":
            stack.append((from_node_id, "实体列表"))
            continue
        stack.append((from_node_id, from_port or ""))
    return None


__all__ = ["FrontendVariableRule"]

