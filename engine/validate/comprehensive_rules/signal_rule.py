from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.nodes.advanced_node_features import SignalDefinition, build_signal_definitions_from_package
from engine.signal import get_default_signal_repository
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import (
    build_node_map,
    extract_port_names,
    get_node_display_info,
    is_flow_port_name,
)
from engine.graph.common import (
    SIGNAL_SEND_NODE_TITLE,
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_SEND_STATIC_INPUTS,
    SIGNAL_LISTEN_STATIC_OUTPUTS,
    SIGNAL_NAME_PORT_NAME,
)

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import GraphAttachment, get_graph_snapshot, iter_all_package_graphs


MAX_SIGNAL_PARAMS = 10
MAX_SIGNAL_PARAM_NAME_LENGTH = 30


class SignalUsageRule(BaseComprehensiveRule):
    """基于包级 `signals` 字段的信号使用一致性校验（存在性 / 参数覆盖 / 常量类型 / 连线类型）。"""

    rule_id = "package.signal_usage"
    category = "信号系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_package_signal_usage(self.validator)


def validate_package_signal_usage(validator) -> List[ValidationIssue]:
    """在整个存档包范围内校验信号定义与节点图用法的一致性。"""
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    signal_definitions = build_signal_definitions_from_package(package)
    # 预构建 signal_id -> {param_name: param_type} 映射，便于后续快速查询
    signal_param_types: Dict[str, Dict[str, str]] = {}
    for signal_id, signal_def in signal_definitions.items():
        type_map: Dict[str, str] = {}
        for param in signal_def.parameters:
            type_map[param.param_name] = param.param_type
        signal_param_types[signal_id] = type_map

    issues: List[ValidationIssue] = []
    issues.extend(_validate_signal_definition_bounds(signal_definitions))

    attachments = iter_all_package_graphs(
        resource_manager,
        package.templates,
        package.instances,
        package.level_entity,
    )

    for attachment in attachments:
        # 仅对服务器节点图执行信号校验
        if attachment.graph_config.graph_type != "server":
            continue
        issues.extend(
            _validate_signals_in_single_graph(
                attachment,
                signal_definitions,
                signal_param_types,
                getattr(validator, "node_library", {}) or {},
            )
        )
    return issues


def _validate_signal_definition_bounds(
    signal_definitions: Dict[str, SignalDefinition],
) -> List[ValidationIssue]:
    """检查信号定义本身的参数数量与参数名长度边界。

    约束规则：
    - 单个信号的参数数量不得超过 MAX_SIGNAL_PARAMS；
    - 每个参数名的字符长度不得超过 MAX_SIGNAL_PARAM_NAME_LENGTH。
    """
    issues: List[ValidationIssue] = []

    if not signal_definitions:
        return issues

    repo = get_default_signal_repository()
    allowed_params_by_id = repo.get_allowed_param_names_by_id()
    all_payloads = repo.get_all_payloads()

    for signal_id in signal_definitions.keys():
        payload = all_payloads.get(signal_id) or {}
        parameters = list(allowed_params_by_id.get(signal_id, set()))
        param_count = len(parameters)
        signal_name_text = payload.get("signal_name")
        signal_name = str(signal_name_text or signal_id)
        location = f"信号定义 '{signal_name}' (ID: {signal_id})"

        if param_count > MAX_SIGNAL_PARAMS:
            detail = {
                "type": "signal_definition",
                "signal_id": signal_id,
                "signal_name": signal_name,
                "param_count": param_count,
            }
            issues.append(
                ValidationIssue(
                    level="error",
                    category="信号系统",
                    location=location,
                    message=(
                        f"信号定义包含 {param_count} 个参数，超过允许的最大数量 "
                        f"{MAX_SIGNAL_PARAMS}。"
                    ),
                    suggestion=(
                        "请精简该信号的参数（例如拆分为多个信号或改为使用结构体参数），"
                        f"确保单个信号的参数数量不超过 {MAX_SIGNAL_PARAMS} 个。"
                    ),
                    reference="信号系统设计.md:5.1 信号参数数量与命名边界",
                    detail=detail,
                )
            )

        for param_name in parameters:
            name_text = str(param_name or "")
            if not name_text:
                continue
            name_length = len(name_text)
            if name_length > MAX_SIGNAL_PARAM_NAME_LENGTH:
                detail = {
                    "type": "signal_definition",
                    "signal_id": signal_id,
                    "signal_name": signal_name,
                    "param_name": name_text,
                    "param_name_length": name_length,
                }
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="信号系统",
                        location=location,
                        message=(
                            f"信号参数名 '{param_name}' 长度为 {name_length}，"
                            f"超过允许的最大长度 {MAX_SIGNAL_PARAM_NAME_LENGTH} 字符。"
                        ),
                        suggestion=(
                            "请缩短参数名，使其在节点端口与信号管理界面中更易阅读，"
                            f"并满足不超过 {MAX_SIGNAL_PARAM_NAME_LENGTH} 个字符的要求。"
                        ),
                        reference="信号系统设计.md:5.1 信号参数数量与命名边界",
                        detail=detail,
                    )
                )

    return issues


def _validate_signals_in_single_graph(
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
    node_defs_by_id = _build_node_defs_for_nodes(nodes, node_library)
    merged_edges = _merge_edges_with_connections(snapshot.edges, snapshot.connections)
    incoming_edges, outgoing_edges = _build_edge_indices(merged_edges)

    base_location = attachment.location_compact
    base_detail = dict(attachment.detail)
    base_detail["graph_id"] = attachment.graph_id
    base_detail["graph_name"] = graph_config.name

    issues: List[ValidationIssue] = []
    for node in nodes:
        node_id, node_title, _ = get_node_display_info(node)
        if not node_id or node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
            continue

        node_detail = dict(base_detail)
        node_detail["node_id"] = node_id
        node_detail["node_title"] = node_title

        node_location = f"{base_location} > 节点 '{node_title}' (ID: {node_id})"
        binding_info = signal_bindings.get(node_id) or {}
        bound_signal_id = str(binding_info.get("signal_id") or "")

        # 3.1 信号存在性校验（带“信号名”常量的智能回退）。
        if not bound_signal_id:
            inferred_signal_id = _infer_signal_id_from_constants(
                node=node,
                signal_definitions=signal_definitions,
            )
            if inferred_signal_id:
                bound_signal_id = inferred_signal_id

        if not bound_signal_id:
            message = (
                "发送信号节点未选择信号"
                if node_title == SIGNAL_SEND_NODE_TITLE
                else "监听信号节点未选择信号"
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
            _validate_signal_ports_for_node(
                node,
                node_location,
                node_detail,
                signal_def,
                incoming_edges=incoming_edges,
                outgoing_edges=outgoing_edges,
            )
        )

        # 仅对发送信号节点执行 3.3 常量类型校验与 3.4 连线类型兼容性校验
        if node_title == SIGNAL_SEND_NODE_TITLE:
            issues.extend(
                _validate_signal_constants_for_send_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                )
            )
            issues.extend(
                _validate_signal_wire_types_for_send_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                    incoming_edges,
                    node_defs_by_id,
                )
            )
        elif node_title == SIGNAL_LISTEN_NODE_TITLE:
            issues.extend(
                _validate_signal_wire_types_for_listen_node(
                    node,
                    node_location,
                    node_detail,
                    signal_param_types.get(bound_signal_id, {}),
                    outgoing_edges,
                    node_defs_by_id,
                )
            )

    return issues


def _build_node_defs_for_nodes(
    nodes: List[Dict[str, Any]],
    node_library: Dict[str, NodeDef],
) -> Dict[str, NodeDef]:
    """为图中的每个节点解析对应的 NodeDef，供类型检查使用。"""
    result: Dict[str, NodeDef] = {}
    if not node_library:
        return result
    for node in nodes:
        node_id, node_title, node_category = get_node_display_info(node)
        if not node_id:
            continue
        category_text = str(node_category or "")
        category_standard = (
            category_text if category_text.endswith("节点") else f"{category_text}节点"
        )
        candidate_key = f"{category_standard}/{node_title}"
        node_def = node_library.get(candidate_key)
        if node_def is None:
            for scope_suffix in ("#client", "#server"):
                scoped_key = f"{candidate_key}{scope_suffix}"
                scoped_def = node_library.get(scoped_key)
                if scoped_def is not None:
                    node_def = scoped_def
                    break
        if node_def is not None:
            result[node_id] = node_def
    return result


def _merge_edges_with_connections(
    edges: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """将 edges 与 connections 统一合并为标准边列表。"""
    normalized: List[Dict[str, Any]] = list(edges or [])
    seen_signatures: List[Tuple[str, str, str, str]] = []
    for edge in normalized:
        signature = _extract_edge_signature(edge)
        if signature not in seen_signatures:
            seen_signatures.append(signature)

    for index, connection in enumerate(connections or []):
        src_node, src_port = _extract_edge_endpoint(connection, True)
        dst_node, dst_port = _extract_edge_endpoint(connection, False)
        signature = (src_node, src_port, dst_node, dst_port)
        if not (src_node and src_port and dst_node and dst_port):
            continue
        if signature in seen_signatures:
            continue
        seen_signatures.append(signature)
        normalized.append(
            {
                "id": connection.get("id") or f"connection_{index}",
                "src_node": src_node,
                "src_port": src_port,
                "dst_node": dst_node,
                "dst_port": dst_port,
            }
        )
    return normalized


def _extract_edge_endpoint(edge: Dict[str, Any], is_source: bool) -> Tuple[str, str]:
    node_keys = ("src_node", "source", "from_node") if is_source else (
        "dst_node",
        "target",
        "to_node",
    )
    port_keys = ("src_port", "source_port", "from_output") if is_source else (
        "dst_port",
        "target_port",
        "to_input",
    )
    node_id = ""
    port_name = ""
    for key in node_keys:
        value = edge.get(key)
        if value:
            node_id = str(value)
            break
    for key in port_keys:
        value = edge.get(key)
        if value:
            port_name = str(value)
            break
    return node_id, port_name


def _extract_edge_signature(edge: Dict[str, Any]) -> Tuple[str, str, str, str]:
    src_node, src_port = _extract_edge_endpoint(edge, True)
    dst_node, dst_port = _extract_edge_endpoint(edge, False)
    return (src_node, src_port, dst_node, dst_port)


def _build_edge_indices(
    edges: List[Dict[str, Any]],
) -> Tuple[Dict[Tuple[str, str], List[Tuple[str, str]]], Dict[Tuple[str, str], List[Tuple[str, str]]]]:
    """构建入边/出边索引：便于按节点+端口快速查询连线。"""
    incoming: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    outgoing: Dict[Tuple[str, str], List[Tuple[str, str]]] = {}
    for edge in edges:
        src_node, src_port = _extract_edge_endpoint(edge, True)
        dst_node, dst_port = _extract_edge_endpoint(edge, False)
        if src_node and src_port and dst_node and dst_port:
            dst_key = (dst_node, dst_port)
            src_key = (src_node, src_port)
            if dst_key not in incoming:
                incoming[dst_key] = []
            incoming[dst_key].append(src_key)
            if src_key not in outgoing:
                outgoing[src_key] = []
            outgoing[src_key].append(dst_key)
    return incoming, outgoing


def _validate_signal_ports_for_node(
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
    
    present_param_names: set[str] = set()
    
    if node_title == SIGNAL_SEND_NODE_TITLE:
        inputs_raw = node.get("inputs", []) or []
        input_names = extract_port_names(inputs_raw)
        constants_map = node.get("input_constants", {}) or {}
        
        for param_name in expected_param_names:
            if param_name in static_inputs:
                continue
            # 1) 显式输入端口
            if param_name in input_names:
                present_param_names.add(param_name)
                continue
            # 2) 存在针对该参数名的入边
            incoming_key = (node_id, param_name)
            if incoming_edges.get(incoming_key):
                present_param_names.add(param_name)
                continue
            # 3) input_constants 中存在对应键
            if param_name in constants_map:
                present_param_names.add(param_name)
                continue
    else:
        outputs_raw = node.get("outputs", []) or []
        output_names = extract_port_names(outputs_raw)
        
        for param_name in expected_param_names:
            if param_name in static_outputs:
                continue
            # 1) 显式输出端口
            if param_name in output_names:
                present_param_names.add(param_name)
                continue
            # 2) 存在从该参数端口发出的出边
            src_key = (node_id, param_name)
            if outgoing_edges.get(src_key):
                present_param_names.add(param_name)
                continue
    
    missing = expected_param_names - present_param_names
    extra = present_param_names - expected_param_names

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


def _validate_signal_constants_for_send_node(
    node: Dict[str, Any],
    location: str,
    detail: Dict[str, Any],
    param_type_map: Dict[str, str],
) -> List[ValidationIssue]:
    """3.3 参数值类型校验：发送信号节点上常量值是否符合信号参数类型。"""
    issues: List[ValidationIssue] = []
    input_constants = node.get("input_constants", {}) or {}
    if not isinstance(input_constants, dict):
        return issues

    for param_name, expected_type in param_type_map.items():
        if param_name not in input_constants:
            continue
        raw_value = input_constants[param_name]
        value_str = str(raw_value)
        if _is_value_compatible_with_type(value_str, expected_type):
            continue
        node_detail = dict(detail)
        node_detail["param_name"] = param_name
        node_detail["expected_type"] = expected_type
        node_detail["current_value"] = value_str
        issues.append(
            ValidationIssue(
                level="error",
                category="信号系统",
                location=location,
                message=(
                    "[信号参数错误] 节点的参数 "
                    f"'{param_name}' 期望类型 '{expected_type}'，"
                    f"当前填入 '{value_str}'。"
                ),
                suggestion="请根据信号参数类型修正常量格式，例如数值/向量/列表的书写方式。",
                reference="信号系统设计.md:3.3 参数值类型校验",
                detail=node_detail,
            )
        )

    return issues


def _validate_signal_wire_types_for_send_node(
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


def _validate_signal_wire_types_for_listen_node(
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


def _infer_signal_id_from_constants(
    node: Dict[str, Any],
    signal_definitions: Dict[str, SignalDefinition],
) -> str:
    """根据节点上的“信号名”输入常量推断信号 ID。

    约定：
    - 常量文本被视为信号的“显示名称”（SignalDefinition.signal_name）；
    - 不再接受直接填写信号 ID，ID 仅通过绑定或 register_handlers 传入；
    - 只在节点本身尚未绑定 signal_id 时作为智能回退使用。
    """
    if not signal_definitions:
        return ""

    input_constants = node.get("input_constants", {}) or {}
    if not isinstance(input_constants, dict):
        return ""

    raw_value = input_constants.get(SIGNAL_NAME_PORT_NAME)
    if raw_value is None:
        return ""

    text = str(raw_value).strip()
    if not text:
        return ""

    # 按 signal_name 匹配到对应的 ID
    for signal_id, signal_def in signal_definitions.items():
        signal_name_value = getattr(signal_def, "signal_name", None)
        if str(signal_name_value or "").strip() == text:
            return str(signal_id)

    return ""


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


def _strip_quotes(text: str) -> str:
    value = text.strip()
    if len(value) >= 2:
        left = value[0]
        right = value[-1]
        if (left == "'" and right == "'") or (left == '"' and right == '"'):
            return value[1:-1].strip()
    return value


def _is_int_literal(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if value[0] in "+-":
        body = value[1:]
    else:
        body = value
    return body.isdigit() and body != ""


def _is_float_literal(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    if _is_int_literal(value):
        return True
    if value[0] in "+-":
        body = value[1:]
    else:
        body = value
    parts = body.split(".")
    if len(parts) != 2:
        return False
    left = parts[0]
    right = parts[1]
    if left != "" and not left.isdigit():
        return False
    if right != "" and not right.isdigit():
        return False
    return left != "" or right != ""


def _is_bool_literal(text: str) -> bool:
    value = text.strip()
    return value in {"True", "False", "true", "false", "是", "否", "0", "1"}


def _split_vector_components(text: str) -> List[str]:
    raw = text.strip()
    if len(raw) >= 2:
        left = raw[0]
        right = raw[-1]
        if (left == "(" and right == ")") or (left == "[" and right == "]"):
            raw = raw[1:-1].strip()
    raw = raw.replace("，", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    if len(parts) < 3:
        more = [p.strip() for p in raw.split() if p.strip() != ""]
        parts = more
    return parts


def _is_vector3_literal(text: str) -> bool:
    components = _split_vector_components(text)
    if len(components) != 3:
        return False
    for component in components:
        if not (_is_int_literal(component) or _is_float_literal(component)):
            return False
    return True


def _split_list_items(text: str) -> List[str]:
    raw = text.strip()
    if not raw:
        return []
    if len(raw) >= 2:
        left = raw[0]
        right = raw[-1]
        if (left == "[" and right == "]") or (left == "{" and right == "}"):
            raw = raw[1:-1].strip()
    raw = raw.replace("，", ",")
    parts = [p.strip() for p in raw.split(",") if p.strip() != ""]
    return parts


def _is_value_compatible_with_type(value_str: str, expected_type: str) -> bool:
    """根据信号参数类型的语义，粗略判断常量字符串是否兼容。"""
    type_name = expected_type.strip()
    plain_value = _strip_quotes(value_str)

    # 字符串类型不过滤，避免误报（格式通常由上游规则约束）
    if type_name in {"字符串", "字符串列表"}:
        return True

    if type_name == "整数":
        return _is_int_literal(plain_value)
    if type_name == "浮点数":
        return _is_float_literal(plain_value)
    if type_name == "布尔值":
        return _is_bool_literal(plain_value)
    if type_name == "三维向量":
        return _is_vector3_literal(plain_value)
    if type_name in {"GUID", "实体", "元件ID", "配置ID"}:
        return _is_int_literal(plain_value)

    items = _split_list_items(plain_value)
    if type_name == "整数列表":
        return all(_is_int_literal(item) for item in items) or not items
    if type_name == "浮点数列表":
        return all(_is_float_literal(item) for item in items) or not items
    if type_name == "布尔值列表":
        return all(_is_bool_literal(item) for item in items) or not items
    if type_name == "三维向量列表":
        return all(_is_vector3_literal(item) for item in items) or not items
    if type_name in {"GUID列表", "实体列表", "元件ID列表", "配置ID列表"}:
        return all(_is_int_literal(item) for item in items) or not items

    # 未识别的类型：保持宽松，视为兼容，避免误报
    return True


__all__ = ["SignalUsageRule"]


