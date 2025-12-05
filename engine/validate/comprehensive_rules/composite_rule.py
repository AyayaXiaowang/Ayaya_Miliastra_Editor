from __future__ import annotations

from typing import Dict, List, Tuple

from engine.nodes.composite_node_manager import get_composite_node_manager
from engine.utils.graph.graph_utils import normalize_graph_edges

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule


class CompositeNodesRule(BaseComprehensiveRule):
    rule_id = "package.composite_nodes"
    category = "复合节点"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_composite_nodes(self.validator)


def validate_composite_nodes(validator) -> List[ValidationIssue]:
    resource_manager = validator.resource_manager
    if not resource_manager:
        return []
    composite_manager = get_composite_node_manager(resource_manager.workspace_path)
    if not composite_manager.composite_nodes:
        return []
    issues: List[ValidationIssue] = []
    for composite_id, composite in composite_manager.composite_nodes.items():
        location = f"复合节点 '{composite.node_name}' ({composite_id})"
        detail = {
            "type": "composite_node",
            "composite_id": composite_id,
            "node_name": composite.node_name,
        }
        composite_manager.load_subgraph_if_needed(composite_id)
        composite = composite_manager.get_composite_node(composite_id)
        if not composite.sub_graph:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="复合节点子图",
                    location=location,
                    message="复合节点缺少子图定义",
                    suggestion="请在复合节点编辑器中添加节点逻辑。",
                    detail=detail,
                )
            )
            continue
        nodes = composite.sub_graph.get("nodes", [])
        edges = composite.sub_graph.get("edges", [])
        if not nodes:
            issues.append(
                ValidationIssue(
                    level="warning",
                    category="复合节点子图",
                    location=location,
                    message="复合节点的子图为空，没有任何节点",
                    suggestion="空的复合节点没有实际功能，请补充逻辑或删除。",
                    detail=detail,
                )
            )
        for pin in composite.virtual_pins:
            pin_location = f"{location} > 虚拟引脚 '{pin.pin_name}'"
            pin_detail = detail.copy()
            pin_detail["pin_index"] = pin.pin_index
            pin_detail["pin_name"] = pin.pin_name
            # 对于标记为 allow_unmapped 的虚拟引脚，允许其在子图中没有具体端口映射：
            # 典型场景是数据输入仅在复合节点代码的控制流条件（如 if 条件:）中使用，
            # 此时不会绑定到任何内部节点端口，但从语义上已经参与了逻辑。
            allow_unmapped = getattr(pin, "allow_unmapped", False)
            if not pin.mapped_ports and not allow_unmapped:
                issues.append(
                    ValidationIssue(
                        level="warning",
                        category="复合节点虚拟引脚",
                        location=pin_location,
                        message=f"虚拟引脚'{pin.pin_name}'没有映射到任何内部端口",
                        suggestion="请在复合节点编辑器中将虚拟引脚映射到内部端口。",
                        detail=pin_detail,
                    )
                )
                continue
            node_ids = {node.get("id") for node in nodes}
            for mapped_port in pin.mapped_ports:
                if mapped_port.node_id not in node_ids:
                    issues.append(
                        ValidationIssue(
                            level="error",
                            category="复合节点虚拟引脚",
                            location=pin_location,
                            message=f"虚拟引脚映射的节点'{mapped_port.node_id}'在子图中不存在",
                            suggestion="请重新映射或修复子图。",
                            detail=pin_detail,
                        )
                    )
        if not nodes:
            continue
        virtual_pin_mappings: Dict[Tuple[str, str], bool] = {}
        for pin in composite.virtual_pins:
            for mapped_port in pin.mapped_ports:
                virtual_pin_mappings[(mapped_port.node_id, mapped_port.port_name)] = (
                    mapped_port.is_input
                )
        issues.extend(
            validate_virtual_pin_connections(
                composite.sub_graph,
                virtual_pin_mappings,
                composite.virtual_pins,
                location,
                detail,
            )
        )
        issues.extend(
            validator.validate_graph_run_only(
                composite.sub_graph,
                location,
                detail,
                virtual_pin_mappings,
            )
        )
    return issues


def validate_virtual_pin_connections(
    graph_data: Dict,
    virtual_pin_mappings: Dict[Tuple[str, str], bool],
    virtual_pins,
    location: str,
    detail: Dict,
) -> List[ValidationIssue]:
    if not graph_data or "edges" not in graph_data:
        return []
    edges = normalize_graph_edges(graph_data.get("edges", []))
    port_to_pin = {}
    for pin in virtual_pins:
        for mapped_port in pin.mapped_ports:
            port_to_pin[(mapped_port.node_id, mapped_port.port_name)] = pin.pin_name
    issues: List[ValidationIssue] = []
    for edge in edges:
        src_node_id = edge.get("src_node", edge.get("source", ""))
        src_port = edge.get("src_port", edge.get("source_port", ""))
        dst_node_id = edge.get("dst_node", edge.get("target", ""))
        dst_port = edge.get("dst_port", edge.get("target_port", ""))
        src_key = (src_node_id, src_port)
        if src_key in virtual_pin_mappings and not virtual_pin_mappings[src_key]:
            pin_name = port_to_pin.get(src_key, "未知虚拟引脚")
            edge_detail = detail.copy()
            edge_detail["edge_id"] = edge.get("id", "")
            edge_detail["node_id"] = src_node_id
            edge_detail["port_name"] = src_port
            edge_detail["pin_name"] = pin_name
            issues.append(
                ValidationIssue(
                    level="error",
                    category="复合节点虚拟引脚",
                    location=f"{location} > 节点 {src_node_id}",
                    message=f"端口 '{src_port}' 已映射到虚拟输出引脚 '{pin_name}'，不能再有额外的连线",
                    suggestion="请删除多余连线或取消该端口的虚拟引脚映射。",
                    detail=edge_detail,
                )
            )
        dst_key = (dst_node_id, dst_port)
        if dst_key in virtual_pin_mappings and virtual_pin_mappings[dst_key]:
            pin_name = port_to_pin.get(dst_key, "未知虚拟引脚")
            edge_detail = detail.copy()
            edge_detail["edge_id"] = edge.get("id", "")
            edge_detail["node_id"] = dst_node_id
            edge_detail["port_name"] = dst_port
            edge_detail["pin_name"] = pin_name
            issues.append(
                ValidationIssue(
                    level="error",
                    category="复合节点虚拟引脚",
                    location=f"{location} > 节点 {dst_node_id}",
                    message=f"端口 '{dst_port}' 已映射到虚拟输入引脚 '{pin_name}'，不能再有额外的连线",
                    suggestion="请删除多余连线或取消该端口的虚拟引脚映射。",
                    detail=edge_detail,
                )
            )
    return issues


__all__ = ["CompositeNodesRule"]

