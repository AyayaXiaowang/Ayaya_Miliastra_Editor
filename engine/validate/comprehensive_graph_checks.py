from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.graph import validate_graph_model as run_graph_model_validation
from engine.graph.common import FLOW_IN_PORT_NAMES, FLOW_OUT_PORT_NAMES, FLOW_PORT_PLACEHOLDER
from engine.graph.models.graph_model import EdgeModel, GraphModel, NodeModel, PortModel, NodeDefRef
from engine.nodes.node_registry import get_node_registry
from engine.nodes import get_canonical_node_def_key
from engine.utils.graph.graph_utils import (
    build_node_map,
    extract_port_names,
    get_node_display_info,
    normalize_graph_edges,
    normalize_graph_nodes,
)
from engine.utils.logging.logger import log_warn
from engine.validate.node_mount_validator import NodeMountValidator

from .comprehensive_types import ValidationIssue
from .issue import EngineIssue


_RANGE_PLACEHOLDER_PORT_PATTERN = re.compile(r"^(?P<prefix>.*?)(?P<start>\d+)~(?P<end>\d+)$")


def _parse_range_placeholder_port_name(port_name: str) -> tuple[str, int, int] | None:
    """解析形如 '0~99' 或 '键0~49' 的“范围占位端口”名称。

    约定：
    - 该类端口用于表达“可变数量/按序号展开”的端口集合；
    - 图数据中可能将其展开为 '0','1','2' 或 '键0','键1' 等具体端口名；
    - 端口一致性校验中应允许“占位端口 ↔ 展开端口”互相满足。
    """
    text = str(port_name or "").strip()
    if not text:
        return None
    match = _RANGE_PLACEHOLDER_PORT_PATTERN.match(text)
    if not match:
        return None
    prefix = str(match.group("prefix") or "")
    start = int(match.group("start"))
    end = int(match.group("end"))
    if start > end:
        start, end = end, start
    return prefix, start, end


def _matches_range_placeholder(actual_port_name: str, *, prefix: str, start: int, end: int) -> bool:
    """判断某个实际端口名是否可视为占位端口的展开成员。"""
    name_text = str(actual_port_name or "").strip()
    if not name_text:
        return False
    if prefix:
        if not name_text.startswith(prefix):
            return False
        suffix = name_text[len(prefix):]
    else:
        suffix = name_text
    if not suffix.isdigit():
        return False
    index = int(suffix)
    return start <= index <= end


def _append_validation_issue(
    validator: Any,
    *,
    level: str,
    category: str,
    code: str = "",
    location: str,
    message: str,
    detail: Dict[str, Any],
    suggestion: str = "",
    reference: str = "",
) -> None:
    issue = ValidationIssue(
        level=level,
        category=category,
        code=code,
        location=location,
        message=message,
        suggestion=suggestion,
        reference=reference,
        detail=detail,
    )
    if hasattr(validator, "report_issue"):
        validator.report_issue(issue)
    elif hasattr(validator, "issues"):
        validator.issues.append(issue)
    else:
        raise AttributeError("验证器缺少 report_issue/issues，用于接收验证结果")


def validate_graph_cache_data(
    validator: Any,
    graph_data: Dict,
    entity_type: str,
    location: str,
    detail: Dict,
    graph_model: Optional[GraphModel] = None,
) -> None:
    if not graph_data or "nodes" not in graph_data:
        return
    nodes, edges = _normalize_graph_components(graph_data)
    validate_node_mount_and_scope(validator, nodes, entity_type, location, detail)
    validate_graph_unified(
        validator,
        graph_data,
        location,
        detail,
        nodes=nodes,
        edges=edges,
        graph_model=graph_model,
    )
    validate_graph_structure(
        validator,
        graph_data,
        location,
        detail,
        nodes=nodes,
        edges=edges,
    )
    validate_graph_port_definitions(
        validator,
        graph_data,
        entity_type,
        location,
        detail,
        nodes=nodes,
        edges=edges,
    )


def validate_graph_structure(
    validator: Any,
    graph_data: Dict,
    location: str,
    detail: Dict,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if nodes is None or edges is None:
        nodes, edges = _normalize_graph_components(graph_data, nodes, edges)
    else:
        nodes = list(nodes)
        edges = list(edges)
    if not nodes:
        return
    event_nodes: List[str] = []
    for node in nodes:
        _, node_name, node_category = get_node_display_info(node)
        if node_category == "事件节点":
            event_nodes.append(node_name)
    if not event_nodes:
        _append_validation_issue(
            validator,
            level="warning",
            category="节点图结构",
            code="GRAPH_NO_EVENT_NODES",
            location=location,
            message="节点图中没有事件节点（入口点）",
            suggestion="请至少保留一个事件节点作为执行入口，例如'进入游戏'或'定时器'。",
            detail=detail,
        )
    if not edges:
        return
    connected_nodes = set()
    for edge in edges:
        src_node, _ = _extract_edge_endpoint(edge, True)
        dst_node, _ = _extract_edge_endpoint(edge, False)
        if src_node:
            connected_nodes.add(src_node)
        if dst_node:
            connected_nodes.add(dst_node)
    for node in nodes:
        node_id, node_name, _ = get_node_display_info(node)
        if node_id and node_id not in connected_nodes:
            node_detail = detail.copy()
            node_detail["node_id"] = node_id
            node_detail["node_name"] = node_name
            _append_validation_issue(
                validator,
                level="warning",
                category="节点图结构",
                code="GRAPH_NODE_ISOLATED",
                location=f"{location} > 节点 '{node_name}'",
                message=f"节点'{node_name}'没有任何连接，是孤立的",
                suggestion="孤立节点不会被执行，如果不需要请删除，否则请建立连线。",
                detail=node_detail,
            )


def validate_node_mount_and_scope(
    validator: Any,
    nodes: List[Dict[str, Any]],
    entity_type: str,
    location: str,
    detail: Dict[str, Any],
) -> None:
    for node in nodes:
        node_id, node_name, node_category = get_node_display_info(node)
        mount_errors = NodeMountValidator.validate_node_mount(node_name, entity_type)
        for error in mount_errors:
            node_detail = detail.copy()
            node_detail["node_id"] = node_id
            node_detail["node_name"] = node_name
            _append_validation_issue(
                validator,
                level=error.level or "error",
                category=error.category or "节点挂载",
                code=error.code or "",
                location=f"{location} > 节点 '{node_name}'",
                message=error.message,
                reference=error.reference or "",
                detail=node_detail,
            )
        scope_errors = NodeMountValidator.validate_composite_node_scope(
            node_category, entity_type, node_name
        )
        for error in scope_errors:
            node_detail = detail.copy()
            node_detail["node_id"] = node_id
            node_detail["node_name"] = node_name
            node_detail["node_category"] = node_category
            _append_validation_issue(
                validator,
                level=error.level or "error",
                category=error.category or "复合节点作用域",
                code=error.code or "",
                location=f"{location} > 节点 '{node_name}'",
                message=error.message,
                reference=error.reference or "",
                detail=node_detail,
            )


def _run_structural_validation_errors(
    graph_data: Dict,
    *,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    virtual_pin_mappings: Optional[Dict] = None,
    graph_model: Optional[GraphModel] = None,
    workspace_path: Optional[Path] = None,
    node_library: Optional[Dict[str, Any]] = None,
) -> List[str]:
    normalized_nodes, normalized_edges = _normalize_graph_components(graph_data, nodes, edges)
    incomplete_edge_errors = _collect_incomplete_edge_errors(normalized_edges)
    model = graph_model or build_graph_model(
        graph_data,
        nodes=normalized_nodes,
        edges=normalized_edges,
    )
    structural_errors = run_graph_model_validation(
        model,
        virtual_pin_mappings,
        workspace_path=workspace_path,
        node_library=node_library,
    )
    return incomplete_edge_errors + structural_errors


def validate_graph_unified(
    validator: Any,
    graph_data: Dict,
    location: str,
    detail: Dict,
    virtual_pin_mappings: Optional[Dict] = None,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
    graph_model: Optional[GraphModel] = None,
) -> None:
    node_library = _ensure_node_library(validator)
    workspace_path = _resolve_workspace_path(validator)
    errors = _run_structural_validation_errors(
        graph_data,
        nodes=nodes,
        edges=edges,
        virtual_pin_mappings=virtual_pin_mappings,
        graph_model=graph_model,
        workspace_path=workspace_path,
        node_library=node_library,
    )
    for error in errors:
        category, suggestion, code = describe_graph_error(error)
        _append_validation_issue(
            validator,
            level="error",
            category=category,
            code=code,
            location=location,
            message=error,
            suggestion=suggestion,
            detail=detail,
        )


def validate_graph_port_definitions(
    validator: Any,
    graph_data: Dict,
    entity_type: str,
    location: str,
    detail: Dict,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> None:
    if not graph_data or "nodes" not in graph_data:
        return
    if nodes is None or edges is None:
        nodes, edges = _normalize_graph_components(graph_data, nodes, edges)
    else:
        nodes = list(nodes)
        edges = list(edges)
    nodes_by_id = build_node_map(nodes)
    node_library = _ensure_node_library(validator)
    for node in nodes:
        validate_node_port_consistency(
            validator,
            node,
            location,
            detail,
            node_library=node_library,
        )
    for edge in edges:
        validate_edge_port_references(validator, edge, nodes_by_id, location, detail)


def validate_node_port_consistency(
    validator: Any,
    node: Dict,
    location: str,
    detail: Dict,
    node_library: Optional[Dict[str, Any]] = None,
) -> None:
    node_id, node_title, node_category = get_node_display_info(node)
    if node_category in {"复合节点", "复合"}:
        return
    if node.get("is_virtual_pin", False):
        return
    library = node_library or _ensure_node_library(validator)
    node_def_ref_raw = node.get("node_def_ref")
    if node_def_ref_raw is None:
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        _append_validation_issue(
            validator,
            level="error",
            category="节点端口定义",
            code="NODE_DEF_REF_MISSING",
            location=f"{location} > 节点 '{node_title}'",
            message="节点缺少 node_def_ref：不允许继续使用 title/category 定位 NodeDef。",
            suggestion="请删除旧 graph_cache 并触发重建（重新解析 Graph Code 产出新 GraphModel）。",
            detail=node_detail,
        )
        return

    node_def_ref = NodeDefRef.from_dict(node_def_ref_raw)
    if node_def_ref.kind == "composite":
        return
    # 事件节点：kind=event 不参与 NodeDef 解析与端口对齐校验
    if node_def_ref.kind == "event":
        return
    if node_def_ref.kind != "builtin":
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        node_detail["node_def_ref"] = node_def_ref.to_dict()
        _append_validation_issue(
            validator,
            level="error",
            category="节点端口定义",
            code="NODE_DEF_REF_KIND_INVALID",
            location=f"{location} > 节点 '{node_title}'",
            message=f"非法 node_def_ref.kind：{node_def_ref.kind!r}",
            suggestion="请删除旧 graph_cache 并触发重建（重新解析 Graph Code 产出新 GraphModel）。",
            detail=node_detail,
        )
        return

    node_def = library.get(str(node_def_ref.key))
    if node_def is None:
        if validator.verbose:
            log_warn("⚠️ 未找到节点定义: node_def_ref={}", str(node_def_ref.key))
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        _append_validation_issue(
            validator,
            level="warning",
            category="节点端口定义",
            code="NODE_DEF_MISSING",
            location=f"{location} > 节点 '{node_title}'",
            message="节点定义缺失，无法校验端口，请确认节点库或工作区路径配置正确。",
            suggestion="请刷新节点库或重新导出节点定义后再运行校验。",
            detail=node_detail,
        )
        return
    node_def_key = get_canonical_node_def_key(node_def)
    actual_inputs = node.get("inputs", [])
    actual_outputs = node.get("outputs", [])
    actual_input_names = extract_port_names(actual_inputs)
    actual_output_names = extract_port_names(actual_outputs)
    expected_input_names = set(node_def.inputs)
    expected_output_names = set(node_def.outputs)
    missing_inputs = expected_input_names - actual_input_names

    # 可变端口占位符兼容：例如节点定义使用 '0~99'，但图数据展开为 '0','1','2'。
    # 此时不应视为“缺少占位端口”。
    if missing_inputs:
        for expected_name in list(missing_inputs):
            parsed = _parse_range_placeholder_port_name(expected_name)
            if parsed is None:
                continue
            prefix, start, end = parsed
            if any(
                _matches_range_placeholder(actual_name, prefix=prefix, start=start, end=end)
                for actual_name in actual_input_names
            ):
                missing_inputs.discard(expected_name)
    if missing_inputs:
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        node_detail["missing_ports"] = list(missing_inputs)
        _append_validation_issue(
            validator,
            level="error",
            category="节点端口定义",
            code="NODE_PORTS_MISSING_INPUTS",
            location=f"{location} > 节点 '{node_title}'",
            message=f"节点缺少输入端口: {', '.join(sorted(missing_inputs))}",
            suggestion=f"根据节点定义（{node_def_key}）补全输入端口。",
            reference=getattr(node_def, "doc_reference", ""),
            detail=node_detail,
        )
    missing_outputs = expected_output_names - actual_output_names
    if missing_outputs:
        node_detail = detail.copy()
        node_detail["node_id"] = node_id
        node_detail["node_name"] = node_title
        node_detail["missing_ports"] = list(missing_outputs)
        _append_validation_issue(
            validator,
            level="error",
            category="节点端口定义",
            code="NODE_PORTS_MISSING_OUTPUTS",
            location=f"{location} > 节点 '{node_title}'",
            message=f"节点缺少输出端口: {', '.join(sorted(missing_outputs))}",
            suggestion=f"根据节点定义（{node_def_key}）补全输出端口。",
            reference=getattr(node_def, "doc_reference", ""),
            detail=node_detail,
        )


def validate_edge_port_references(
    validator: Any,
    edge: Dict,
    nodes_by_id: Dict,
    location: str,
    detail: Dict,
) -> None:
    edge_id = edge.get("id", "")
    src_node_id, src_port = _extract_edge_endpoint(edge, True)
    dst_node_id, dst_port = _extract_edge_endpoint(edge, False)
    if src_node_id not in nodes_by_id:
        edge_detail = detail.copy()
        edge_detail["edge_id"] = edge_id
        edge_detail["src_node_id"] = src_node_id
        _append_validation_issue(
            validator,
            level="error",
            category="节点图连接",
            code="EDGE_SRC_NODE_MISSING",
            location=f"{location} > 边 '{edge_id}'",
            message=f"边引用的源节点'{src_node_id}'不存在",
            suggestion="请确保源节点存在于节点列表中。",
            detail=edge_detail,
        )
        return
    if dst_node_id not in nodes_by_id:
        edge_detail = detail.copy()
        edge_detail["edge_id"] = edge_id
        edge_detail["dst_node_id"] = dst_node_id
        _append_validation_issue(
            validator,
            level="error",
            category="节点图连接",
            code="EDGE_DST_NODE_MISSING",
            location=f"{location} > 边 '{edge_id}'",
            message=f"边引用的目标节点'{dst_node_id}'不存在",
            suggestion="请确保目标节点存在于节点列表中。",
            detail=edge_detail,
        )
        return
    src_node = nodes_by_id[src_node_id]
    dst_node = nodes_by_id[dst_node_id]
    src_outputs = src_node.get("outputs", [])
    dst_inputs = dst_node.get("inputs", [])
    src_output_names = extract_port_names(src_outputs)
    dst_input_names = extract_port_names(dst_inputs)
    if src_port not in src_output_names:
        if src_port == FLOW_PORT_PLACEHOLDER:
            flow_ports = set(FLOW_OUT_PORT_NAMES)
            if not (src_output_names & flow_ports):
                _emit_missing_port_issue(
                    validator,
                    edge_id,
                    location,
                    detail,
                    src_node_id,
                    src_node,
                    src_port,
                    True,
                )
        else:
            _emit_missing_port_issue(
                validator,
                edge_id,
                location,
                detail,
                src_node_id,
                src_node,
                src_port,
                True,
            )
    if dst_port not in dst_input_names:
        if dst_port == FLOW_PORT_PLACEHOLDER:
            if not (dst_input_names & set(FLOW_IN_PORT_NAMES)):
                _emit_missing_port_issue(
                    validator,
                    edge_id,
                    location,
                    detail,
                    dst_node_id,
                    dst_node,
                    dst_port,
                    False,
                )
        else:
            _emit_missing_port_issue(
                validator,
                edge_id,
                location,
                detail,
                dst_node_id,
                dst_node,
                dst_port,
                False,
            )


def _emit_missing_port_issue(
    validator: Any,
    edge_id: str,
    location: str,
    detail: Dict,
    node_id: str,
    node_data: Dict,
    port_name: str,
    is_source: bool,
) -> None:
    role = "源" if is_source else "目标"
    node_title = node_data.get("title", node_id)
    node_ports = node_data.get("outputs" if is_source else "inputs", [])
    readable_ports = extract_port_names(node_ports)
    issue_detail = detail.copy()
    issue_detail["edge_id"] = edge_id
    issue_detail["node_id"] = node_id
    issue_detail["port_name"] = port_name
    _append_validation_issue(
        validator,
        level="error",
        category="节点图连接",
        code="EDGE_PORT_MISSING",
        location=f"{location} > 边 '{edge_id}'",
        message=f"边引用的{role}端口'{port_name}'在节点'{node_title}'中不存在",
        suggestion=f"{role}节点的可用端口: {', '.join(sorted(readable_ports)) or '(无)'}",
        detail=issue_detail,
    )


def validate_graph_structure_only(
    validator: Any,
    graph_data: Dict,
    location: str,
    detail: Dict,
    graph_model: Optional[GraphModel] = None,
) -> None:
    if not graph_data or "nodes" not in graph_data:
        return
    nodes, edges = _normalize_graph_components(graph_data)
    validate_graph_unified(
        validator,
        graph_data,
        location,
        detail,
        nodes=nodes,
        edges=edges,
        graph_model=graph_model,
    )
    validate_graph_structure(
        validator,
        graph_data,
        location,
        detail,
        nodes=nodes,
        edges=edges,
    )


def build_graph_model(
    graph_data: Dict,
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> GraphModel:
    normalized_nodes, normalized_edges = _normalize_graph_components(graph_data, nodes, edges)
    graph_model = GraphModel()
    for node in normalized_nodes:
        node_id = node.get("id", "")
        if not node_id:
            continue
        node_def_ref_raw = node.get("node_def_ref")
        node_model = NodeModel(
            id=node_id,
            title=node.get("title", node.get("name", "")),
            category=node.get("category", ""),
            node_def_ref=NodeDefRef.from_dict(node_def_ref_raw) if node_def_ref_raw is not None else None,
            pos=node.get("position", node.get("pos", (0, 0))),
            composite_id=str(node.get("composite_id", "") or ""),
        )
        # 恢复可选的源码行范围（若存在则用于错误定位）
        node_model.source_lineno = int(node.get("source_lineno", 0) or 0)
        node_model.source_end_lineno = int(
            node.get("source_end_lineno", node_model.source_lineno or 0) or 0
        )
        for node_input in node.get("inputs", []):
            port_name = node_input if isinstance(node_input, str) else node_input.get("name", "")
            if port_name:
                node_model.inputs.append(PortModel(name=port_name, is_input=True))
        for node_output in node.get("outputs", []):
            port_name = node_output if isinstance(node_output, str) else node_output.get("name", "")
            if port_name:
                node_model.outputs.append(PortModel(name=port_name, is_input=False))
        input_constants = node.get("input_constants", {})
        if input_constants:
            node_model.input_constants = input_constants
        graph_model.nodes[node_id] = node_model

    for idx, edge in enumerate(normalized_edges):
        edge_id = edge.get("id") or f"edge[{idx}]"
        src_node, src_port = _extract_edge_endpoint(edge, True)
        dst_node, dst_port = _extract_edge_endpoint(edge, False)
        if not (src_node and src_port and dst_node and dst_port):
            continue
        graph_model.edges[edge_id] = EdgeModel(
            id=edge_id,
            src_node=src_node,
            src_port=src_port,
            dst_node=dst_node,
            dst_port=dst_port,
        )
    return graph_model


def describe_graph_error(error: str) -> Tuple[str, str, str]:
    """统一将底层图校验错误映射为分类与建议。"""
    if "跨事件连接错误" in error or "跨逻辑子图" in error:
        return (
            "跨事件连接",
            "每个节点只能属于一个事件流，跨事件通信请使用变量或事件。",
            "CONNECTION_CROSS_SUBGRAPH",
        )
    if "端口类型不匹配" in error:
        return (
            "端口类型匹配",
            "流程端口只能连接流程端口，数据端口只能连接数据端口。",
            "CONNECTION_TYPE_MISMATCH",
        )
    if ("流程入口" in error and "未连接" in error) or "flow" in error.lower():
        return (
            "流程连接",
            "每个流程节点的流程入口必须连接。",
            "CONNECTION_FLOW_ENTRY",
        )
    if "缺少数据来源" in error:
        return (
            "节点数据输入",
            "数据输入端口需要连接或配置常量。",
            "CONNECTION_DATA_INPUT",
        )
    if "环" in error or "cycle" in error.lower():
        return (
            "节点图结构",
            "请移除形成环路的连线，节点图禁止出现循环依赖。",
            "CONNECTION_CYCLE_DETECTED",
        )
    return ("节点图结构", "", "CONNECTION_STRUCTURE")


def structural_errors_to_engine_issues(errors: Iterable[str]) -> List[EngineIssue]:
    issues: List[EngineIssue] = []
    for error in errors:
        category, suggestion, code = describe_graph_error(error)
        message = error if not suggestion else f"{error}\n建议：{suggestion}"
        issues.append(
            EngineIssue(
                level="error",
                category=category,
                code=code,
                message=message,
            )
        )
    return issues


def _normalize_edges_with_connections(
    graph_data: Dict[str, Any],
    edges: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    normalized = list(edges or [])
    seen_signatures = {
        _extract_edge_signature(edge)
        for edge in normalized
    }
    connections_raw = graph_data.get("connections") or []
    connection_items = normalize_graph_edges(connections_raw)
    for idx, connection in enumerate(connection_items):
        src_node, src_port = _extract_edge_endpoint(connection, True)
        dst_node, dst_port = _extract_edge_endpoint(connection, False)
        signature = (src_node, src_port, dst_node, dst_port)
        if not all(signature) or signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        normalized.append(
            {
                "id": connection.get("id") or f"connection_{idx}",
                "src_node": src_node,
                "src_port": src_port,
                "dst_node": dst_node,
                "dst_port": dst_port,
            }
        )
    return normalized


def _normalize_graph_components(
    graph_data: Dict[str, Any],
    nodes: Optional[List[Dict[str, Any]]] = None,
    edges: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    normalized_nodes = nodes if nodes is not None else normalize_graph_nodes(
        graph_data.get("nodes", [])
    )
    if edges is not None:
        normalized_edges = list(edges)
    else:
        base_edges = normalize_graph_edges(graph_data.get("edges", []))
        normalized_edges = _normalize_edges_with_connections(graph_data, base_edges)
    return normalized_nodes, normalized_edges


def _edge_identifier(edge: Dict[str, Any], index: int) -> str:
    edge_id = edge.get("id")
    if isinstance(edge_id, str) and edge_id:
        return edge_id
    return f"edge[{index}]"


def _missing_edge_fields(edge: Dict[str, Any]) -> List[str]:
    missing: List[str] = []
    src_node, src_port = _extract_edge_endpoint(edge, True)
    dst_node, dst_port = _extract_edge_endpoint(edge, False)
    if not src_node:
        missing.append("src_node")
    if not src_port:
        missing.append("src_port")
    if not dst_node:
        missing.append("dst_node")
    if not dst_port:
        missing.append("dst_port")
    return missing


def _collect_incomplete_edge_errors(edges: List[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    for idx, edge in enumerate(edges):
        missing = _missing_edge_fields(edge)
        if missing:
            label = _edge_identifier(edge, idx)
            errors.append(f"边'{label}'缺少必填字段: {', '.join(missing)}")
    return errors


def _extract_edge_endpoint(edge: Dict[str, Any], is_source: bool) -> Tuple[str, str]:
    node_keys = ("src_node", "source", "from_node") if is_source else ("dst_node", "target", "to_node")
    port_keys = ("src_port", "source_port", "from_output") if is_source else ("dst_port", "target_port", "to_input")
    node_id = ""
    port_name = ""
    for key in node_keys:
        value = edge.get(key)
        if value:
            node_id = value
            break
    for key in port_keys:
        value = edge.get(key)
        if value:
            port_name = value
            break
    return node_id, port_name


def _extract_edge_signature(edge: Dict[str, Any]) -> Tuple[str, str, str, str]:
    src_node, src_port = _extract_edge_endpoint(edge, True)
    dst_node, dst_port = _extract_edge_endpoint(edge, False)
    return (src_node, src_port, dst_node, dst_port)


def _ensure_node_library(validator: Any) -> Dict[str, Any]:
    library = getattr(validator, "node_library", None) or {}
    if library:
        return library
    workspace_path = _resolve_workspace_path(validator)
    registry = get_node_registry(workspace_path, include_composite=True)
    library = registry.get_library()
    if hasattr(validator, "node_library"):
        validator.node_library = library
    return library


def _resolve_workspace_path(validator: Any) -> Path:
    resource_manager = getattr(validator, "resource_manager", None)
    if resource_manager and hasattr(resource_manager, "workspace_path"):
        workspace = getattr(resource_manager, "workspace_path")
        if workspace:
            return Path(workspace)
    workspace_attr = getattr(validator, "workspace_path", None)
    if workspace_attr:
        return Path(workspace_attr)
    return Path(".")

