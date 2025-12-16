from __future__ import annotations

from typing import Any, Dict, List, Tuple

from engine.graph.common import SIGNAL_NAME_PORT_NAME
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import (
    extract_port_names,
    get_node_display_info,
    is_flow_port_name,
)

from ...comprehensive_types import ValidationIssue


def validate_signal_wire_types_for_send_node(
    node: Dict[str, Any],
    location: str,
    detail: Dict[str, Any],
    param_type_map: Dict[str, str],
    incoming_edges: Dict[Tuple[str, str], List[Tuple[str, str]]],
    node_defs_by_id: Dict[str, NodeDef],
) -> List[ValidationIssue]:
    """3.4 连线类型兼容性（发送信号节点参数输入）。"""
    issues: List[ValidationIssue] = []
    node_id, _, _ = get_node_display_info(node)
    static_inputs = {"流程入", SIGNAL_NAME_PORT_NAME, "目标实体"}
    input_names = extract_port_names(node.get("inputs", []) or [])

    for param_name, expected_type in param_type_map.items():
        if param_name not in input_names or param_name in static_inputs:
            continue
        incoming_key = (node_id, param_name)
        sources = incoming_edges.get(incoming_key) or []
        for src_node_id, src_port_name in sources:
            src_def = node_defs_by_id.get(src_node_id)
            if src_def is None:
                continue
            src_type = _get_port_type_safe(src_def, src_port_name, is_input=False)
            # 端口类型为空或属于“泛型家族”（如 泛型 / 泛型列表 / 泛型字典 等）时，不做严格比对，
            # 仅对具体类型（整数 / 字符串 / 整数列表 等）执行精确匹配。
            if _is_generic_family_type(src_type):
                continue
            if src_type != expected_type:
                node_detail = dict(detail)
                node_detail["param_name"] = param_name
                node_detail["expected_type"] = expected_type
                node_detail["source_node_id"] = src_node_id
                node_detail["source_port"] = src_port_name
                node_detail["source_type"] = src_type
                issues.append(
                    ValidationIssue(
                        level="warning",
                        category="信号系统",
                        location=location,
                        message=(
                            "信号参数端口的连线类型与信号定义不一致："
                            f"参数 '{param_name}' 期望 '{expected_type}'，"
                            f"但来自节点端口类型为 '{src_type}'。"
                        ),
                        suggestion="请调整上游节点输出类型或信号参数类型，保证两者一致。",
                        reference="信号系统设计.md:3.4 连线类型兼容性",
                        detail=node_detail,
                    )
                )
    return issues


def validate_signal_wire_types_for_listen_node(
    node: Dict[str, Any],
    location: str,
    detail: Dict[str, Any],
    param_type_map: Dict[str, str],
    outgoing_edges: Dict[Tuple[str, str], List[Tuple[str, str]]],
    node_defs_by_id: Dict[str, NodeDef],
) -> List[ValidationIssue]:
    """3.4 连线类型兼容性（监听信号节点参数输出）。"""
    issues: List[ValidationIssue] = []
    node_id, _, _ = get_node_display_info(node)
    static_outputs = {"流程出", "事件源实体", "事件源GUID", "信号来源实体"}
    output_names = extract_port_names(node.get("outputs", []) or [])

    for param_name, expected_type in param_type_map.items():
        if param_name not in output_names or param_name in static_outputs:
            continue
        src_key = (node_id, param_name)
        targets = outgoing_edges.get(src_key) or []
        for dst_node_id, dst_port_name in targets:
            dst_def = node_defs_by_id.get(dst_node_id)
            if dst_def is None:
                continue
            dst_type = _get_port_type_safe(dst_def, dst_port_name, is_input=True)
            # 同发送侧规则：当目标端口类型为空或属于“泛型家族”时，跳过严格类型检查。
            if _is_generic_family_type(dst_type):
                continue
            if dst_type != expected_type:
                node_detail = dict(detail)
                node_detail["param_name"] = param_name
                node_detail["expected_type"] = expected_type
                node_detail["target_node_id"] = dst_node_id
                node_detail["target_port"] = dst_port_name
                node_detail["target_type"] = dst_type
                issues.append(
                    ValidationIssue(
                        level="warning",
                        category="信号系统",
                        location=location,
                        message=(
                            "信号参数输出端口的连线类型与信号定义不一致："
                            f"参数 '{param_name}' 期望 '{expected_type}'，"
                            f"但下游节点端口类型为 '{dst_type}'。"
                        ),
                        suggestion="请调整下游节点输入类型或信号参数类型，保证两者一致。",
                        reference="信号系统设计.md:3.4 连线类型兼容性",
                        detail=node_detail,
                    )
                )
    return issues


def _is_generic_family_type(type_name: object) -> bool:
    """判定是否属于“泛型家族”类型名（用于连线类型宽松检查）。

    约定：
    - 与端口类型推断模块保持一致：空字符串 / "泛型" / 以 "泛型" 开头的类型名均视为泛型家族；
    - 包括但不限于："泛型"、"泛型列表"、"泛型字典" 等。
    """
    if not isinstance(type_name, str):
        return False
    text = type_name.strip()
    if text == "" or text == "泛型" or text.startswith("泛型"):
        return True
    return False


def _get_port_type_safe(node_def: NodeDef, port_name: str, is_input: bool) -> str:
    """在不抛异常的前提下获取端口类型（优先显式类型，其次动态类型，最后流程类型）。"""
    port_name_str = str(port_name)
    type_dict = node_def.input_types if is_input else node_def.output_types
    if port_name_str in type_dict:
        return type_dict[port_name_str]
    if node_def.dynamic_port_type:
        return node_def.dynamic_port_type
    if is_flow_port_name(port_name_str):
        return "流程"
    return ""


__all__ = [
    "validate_signal_wire_types_for_send_node",
    "validate_signal_wire_types_for_listen_node",
]


