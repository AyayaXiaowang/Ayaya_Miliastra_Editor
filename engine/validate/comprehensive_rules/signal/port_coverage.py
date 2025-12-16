from __future__ import annotations

from typing import Any, Dict, List, Tuple

from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
)
from engine.nodes.advanced_node_features import SignalDefinition
from engine.utils.graph.graph_utils import extract_port_names, get_node_display_info

from ...comprehensive_types import ValidationIssue


def validate_signal_ports_for_node(
    node: Dict[str, Any],
    location: str,
    detail: Dict[str, Any],
    signal_def: SignalDefinition,
    *,
    incoming_edges: Dict[Tuple[str, str], List[Tuple[str, str]]],
    outgoing_edges: Dict[Tuple[str, str], List[Tuple[str, str]]],
) -> List[ValidationIssue]:
    """3.2 参数列表一致性：信号参数与节点端口覆盖是否一致。

    端口覆盖的判定同时考虑三种来源：
    - 节点自身的动态端口列表（inputs/outputs）；
    - 参数常量键（input_constants）；
    - 图中的连线端口名（入边/出边的端口）。
    """
    node_id, node_title, _ = get_node_display_info(node)
    issues: List[ValidationIssue] = []

    expected_param_names = {param.param_name for param in signal_def.parameters}
    static_inputs = set(SIGNAL_SEND_STATIC_INPUTS)
    static_outputs = set(SIGNAL_LISTEN_STATIC_OUTPUTS)

    # === 1. 计算当前图中实际出现的“非静态参数名”集合 ===
    present_param_names: set[str] = set()

    if node_title == SIGNAL_SEND_NODE_TITLE:
        # 发送信号：关注非静态输入端口 + 常量键 + 入边端口名
        inputs_raw = node.get("inputs", []) or []
        input_names = extract_port_names(inputs_raw)
        constants_map = node.get("input_constants", {}) or {}

        for name in input_names:
            if name in static_inputs:
                continue
            present_param_names.add(name)

        for const_name in (constants_map.keys() if isinstance(constants_map, dict) else []):
            if const_name in static_inputs:
                continue
            present_param_names.add(str(const_name))

        for (dst_node_id, dst_port_name), sources in incoming_edges.items():
            if not sources:
                continue
            if dst_node_id != node_id:
                continue
            if dst_port_name in static_inputs:
                continue
            present_param_names.add(dst_port_name)
    elif node_title == SIGNAL_LISTEN_NODE_TITLE:
        # 监听信号：关注非静态输出端口 + 出边端口名
        outputs_raw = node.get("outputs", []) or []
        output_names = extract_port_names(outputs_raw)

        for name in output_names:
            if name in static_outputs:
                continue
            present_param_names.add(name)

        for (src_node_id, src_port_name), targets in outgoing_edges.items():
            if not targets:
                continue
            if src_node_id != node_id:
                continue
            if src_port_name in static_outputs:
                continue
            present_param_names.add(src_port_name)

    # 期望的“信号参数名集合”本身不包含静态端口名，这里统一减去以防未来扩展。
    expected_non_static = expected_param_names - static_inputs - static_outputs

    missing = expected_non_static - present_param_names
    extra = present_param_names - expected_non_static

    if missing:
        node_detail = dict(detail)
        node_detail["missing_params"] = sorted(missing)
        issues.append(
            ValidationIssue(
                level="error",
                category="信号系统",
                location=location,
                message="信号参数端口不完整，缺少参数端口: " + ", ".join(sorted(missing)),
                suggestion="请根据信号定义在节点上补全对应的参数端口。",
                reference="信号系统设计.md:3.2 参数列表一致性校验",
                detail=node_detail,
            )
        )

    if extra:
        node_detail = dict(detail)
        node_detail["extra_params"] = sorted(extra)
        issues.append(
            ValidationIssue(
                level="error",
                category="信号系统",
                location=location,
                message="检测到多余的信号参数端口: " + ", ".join(sorted(extra)),
                suggestion=(
                    "多出的端口在运行时不会收到任何信号值，通常意味着使用了已从信号定义中移除的参数名或拼写错误；"
                    "请删掉这些端口，或在信号定义中补充对应参数。"
                ),
                reference="信号系统设计.md:3.2 参数列表一致性校验",
                detail=node_detail,
            )
        )

    return issues


__all__ = ["validate_signal_ports_for_node"]


