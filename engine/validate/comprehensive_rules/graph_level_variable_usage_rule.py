from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from engine.graph.common import VARIABLE_NAME_PORT_NAME
from engine.nodes.node_definition_loader import NodeDef
from engine.utils.graph.graph_utils import build_connection_map, build_node_map, get_node_display_info
from engine.validate.node_semantics import (
    SEMANTIC_CUSTOM_VAR_GET,
    SEMANTIC_CUSTOM_VAR_SET,
    is_semantic_graph_node,
)

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import get_graph_snapshot, iter_all_package_graphs


_SPECIAL_VIEW_PACKAGE_IDS = {"global_view"}


def _safe_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _normalize_variable_ref_text(text_value: object) -> str:
    """严格模式：只允许 variable_name（自定义变量键），禁止填写 variable_id 或旧展示文本格式。"""
    raw_text = _safe_text(text_value)
    if not raw_text:
        return ""
    return raw_text


def _extract_variable_id_from_display_text(raw_text: str) -> str:
    """从常见旧展示格式中提取 variable_id（仅用于报错提示，不作为兼容入口）。"""
    text = _safe_text(raw_text)
    if not text:
        return ""

    # 旧展示格式：name (variable_id)
    if text.endswith(")") and "(" in text:
        inside = text.rsplit("(", 1)[-1].rstrip(")").strip()
        if inside:
            return inside

    # 旧列表项格式：name | variable_id | ...
    if "|" in text:
        parts = [part.strip() for part in text.split("|")]
        if len(parts) >= 2 and parts[1]:
            return parts[1]

    return ""


def _build_combined_connection_map(snapshot) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """合并 connections/edges 的连线索引：key=(dst_node,dst_port) -> (src_node,src_port)。"""
    connection_map = build_connection_map(snapshot.connections)
    for edge in snapshot.edges:
        src_node = edge.get("src_node") or edge.get("source") or edge.get("from_node")
        src_port = edge.get("src_port") or edge.get("source_port") or edge.get("from_output")
        dst_node = edge.get("dst_node") or edge.get("target") or edge.get("to_node")
        dst_port = edge.get("dst_port") or edge.get("target_port") or edge.get("to_input")
        if not (src_node and src_port and dst_node and dst_port):
            continue
        key = (str(dst_node), str(dst_port))
        if key not in connection_map:
            connection_map[key] = (str(src_node), str(src_port))
    return connection_map


def _describe_connected_source(
    node_id: str,
    port_name: str,
    connection_map: Dict[Tuple[str, str], Tuple[str, str]],
    node_map: Dict[str, Dict],
) -> str:
    key = (str(node_id), str(port_name))
    if key not in connection_map:
        return ""
    src_node_id, src_port = connection_map[key]
    src_node = node_map.get(str(src_node_id)) or {}
    src_title = _safe_text(src_node.get("title")) or str(src_node_id)
    return f"{src_title}.{src_port}"


class GraphLevelVariableUsageRule(BaseComprehensiveRule):
    """校验挂载节点图中“自定义变量”相关节点对关卡变量（variable_name）的引用是否可解。"""

    rule_id = "package.graph_level_variable_usage"
    category = "资源系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_graph_level_variable_usage(self.validator)


def validate_graph_level_variable_usage(validator) -> List[ValidationIssue]:
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    package_id = _safe_text(getattr(package, "package_id", ""))
    if not package_id or package_id in _SPECIAL_VIEW_PACKAGE_IDS:
        return []

    package_name = _safe_text(getattr(package, "name", "")) or package_id

    workspace_path = Path(getattr(resource_manager, "workspace_path"))
    node_library: Dict[str, NodeDef] = getattr(validator, "node_library", {}) or {}

    management = getattr(package, "management", None)
    referenced_variables = getattr(management, "level_variables", None) if management is not None else None
    available_variables: Dict[str, Dict[str, Any]] = (
        referenced_variables if isinstance(referenced_variables, dict) else {}
    )

    # 预构建 “variable_name -> [variable_id,...]” 与 “variable_id -> variable_name”
    ids_by_variable_name: Dict[str, List[str]] = {}
    variable_name_by_id: Dict[str, str] = {}
    for variable_id, payload in available_variables.items():
        if not isinstance(payload, dict):
            continue
        name_text = _safe_text(payload.get("variable_name"))
        if not name_text:
            continue
        variable_id_text = str(variable_id)
        ids_by_variable_name.setdefault(name_text, []).append(variable_id_text)
        variable_name_by_id.setdefault(variable_id_text, name_text)

    issues: List[ValidationIssue] = []

    attachments = iter_all_package_graphs(
        resource_manager,
        getattr(package, "templates", {}) or {},
        getattr(package, "instances", {}) or {},
        getattr(package, "level_entity", None),
        getattr(package, "combat_presets", None),
    )

    for attachment in attachments:
        graph_data = attachment.graph_config.data
        if not graph_data or "nodes" not in graph_data:
            continue

        scope_text = str(getattr(attachment.graph_config, "graph_type", "") or "")
        snapshot = get_graph_snapshot(graph_data, cache_key=attachment.graph_id)
        node_map = build_node_map(snapshot.nodes)
        connection_map = _build_combined_connection_map(snapshot)

        for node in snapshot.nodes:
            node_id, node_title, node_category = get_node_display_info(node)
            node_id_text = _safe_text(node_id)
            node_title_text = _safe_text(node_title)
            node_category_text = _safe_text(node_category)

            if not node_id_text:
                continue

            is_custom_var_node = (
                is_semantic_graph_node(
                    workspace_path=workspace_path,
                    node_library=node_library,
                    node_category=node_category_text,
                    node_title=node_title_text,
                    scope_text=scope_text,
                    semantic_id=SEMANTIC_CUSTOM_VAR_GET,
                )
                or is_semantic_graph_node(
                    workspace_path=workspace_path,
                    node_library=node_library,
                    node_category=node_category_text,
                    node_title=node_title_text,
                    scope_text=scope_text,
                    semantic_id=SEMANTIC_CUSTOM_VAR_SET,
                )
            )
            if not is_custom_var_node:
                continue

            # 变量名允许来自连线：
            # - 若来自连线且无法静态解析为明确的 variable_name，则跳过“引用存在性”强校验（降级为 warning）。
            # - 若为常量（input_constants）则继续按 strict 规则校验。
            connected_source = _describe_connected_source(
                node_id_text,
                VARIABLE_NAME_PORT_NAME,
                connection_map,
                node_map,
            )
            if connected_source:
                issues.append(
                    ValidationIssue(
                        level="warning",
                        category="资源系统",
                        location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                        message=(
                            f"『{VARIABLE_NAME_PORT_NAME}』来自连线（{connected_source}），无法静态解析为明确的 variable_name；"
                            "已跳过关卡变量引用存在性校验。"
                        ),
                        suggestion=(
                            "若希望启用严格校验，请将该端口改为常量并填写关卡变量的 variable_name（建议通过选择器写入）；"
                            "若必须保持动态连线，请确保运行期产出的 variable_name 一定存在于当前存档引用的变量集合内。"
                        ),
                        reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                        detail={
                            **(attachment.detail or {}),
                            "type": "graph_level_variable_dynamic_reference_not_validated",
                            "package_id": package_id,
                            "node_id": node_id_text,
                            "node_title": node_title_text,
                            "port_name": VARIABLE_NAME_PORT_NAME,
                            "source": connected_source,
                        },
                    )
                )
                continue

            constants = node.get("input_constants") or {}
            if not isinstance(constants, dict):
                constants = {}

            raw_value = constants.get(VARIABLE_NAME_PORT_NAME)
            raw_text = _safe_text(raw_value)
            if not raw_text:
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="资源系统",
                        location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                        message=f"节点缺少常量『{VARIABLE_NAME_PORT_NAME}』，无法解析关卡变量引用。",
                        suggestion=(
                            f"请为该端口填写关卡变量的 variable_name（推荐通过选择器写入），"
                            "并确保当前存档索引已引用对应变量文件。"
                        ),
                        reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                        detail={
                            **(attachment.detail or {}),
                            "type": "graph_level_variable_missing_constant",
                            "package_id": package_id,
                            "node_id": node_id_text,
                            "node_title": node_title_text,
                            "port_name": VARIABLE_NAME_PORT_NAME,
                        },
                    )
                )
                continue

            normalized_candidate = _normalize_variable_ref_text(raw_text)

            # 1) 严格模式：只接受 variable_name（自定义变量键）
            matched_ids = ids_by_variable_name.get(normalized_candidate, [])
            if len(matched_ids) == 1:
                continue

            if len(matched_ids) > 1:
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="资源系统",
                        location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                        message=(
                            f"『{VARIABLE_NAME_PORT_NAME}』为变量名，但在当前存档引用的关卡变量集合内出现重复定义：{raw_text}"
                        ),
                        suggestion=(
                            "请确保关卡变量定义中的 variable_name 全局唯一（运行期自定义变量以该键存取）；"
                            f"当前匹配到的 variable_id: {', '.join(sorted(matched_ids))}"
                        ),
                        reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                        detail={
                            **(attachment.detail or {}),
                            "type": "graph_level_variable_duplicate_variable_name",
                            "package_id": package_id,
                            "node_id": node_id_text,
                            "node_title": node_title_text,
                            "raw_value": raw_text,
                            "matched_variable_ids": list(sorted(matched_ids)),
                        },
                    )
                )
                continue

            # 2) 若填了 variable_id：给出“应填 variable_name”的明确提示
            if normalized_candidate in available_variables:
                suggested_name = _safe_text(variable_name_by_id.get(normalized_candidate))
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="资源系统",
                        location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                        message=(
                            f"『{VARIABLE_NAME_PORT_NAME}』填写了 variable_id，严格模式下已禁止：{raw_text}"
                        ),
                        suggestion=(
                            f"请改为填写 variable_name：{suggested_name}" if suggested_name else "请改为填写该变量的 variable_name（自定义变量键）"
                        ),
                        reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                        detail={
                            **(attachment.detail or {}),
                            "type": "graph_level_variable_id_forbidden",
                            "package_id": package_id,
                            "node_id": node_id_text,
                            "node_title": node_title_text,
                            "raw_value": raw_text,
                            "variable_id": normalized_candidate,
                            "suggested_variable_name": suggested_name,
                        },
                    )
                )
                continue

            # 3) 旧展示文本里带了 variable_id：严格模式下禁止
            extracted_id = _extract_variable_id_from_display_text(raw_text)
            if extracted_id and extracted_id in available_variables:
                suggested_name = _safe_text(variable_name_by_id.get(extracted_id))
                issues.append(
                    ValidationIssue(
                        level="error",
                        category="资源系统",
                        location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                        message=(
                            f"『{VARIABLE_NAME_PORT_NAME}』使用了旧展示文本格式，严格模式下已禁止：{raw_text}"
                        ),
                        suggestion=(
                            f"请直接填写 variable_name：{suggested_name}"
                            if suggested_name
                            else "请直接填写该变量的 variable_name（自定义变量键）"
                        ),
                        reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                        detail={
                            **(attachment.detail or {}),
                            "type": "graph_level_variable_display_text_forbidden",
                            "package_id": package_id,
                            "node_id": node_id_text,
                            "node_title": node_title_text,
                            "raw_value": raw_text,
                            "extracted_variable_id": extracted_id,
                            "suggested_variable_name": suggested_name,
                        },
                    )
                )
                continue

            # 4) 未匹配到 variable_name：给出统一的“变量不存在/未被引用”提示
            hint = normalized_candidate
            issues.append(
                ValidationIssue(
                    level="error",
                    category="资源系统",
                    location=f"{attachment.location_compact} > 节点 '{node_title_text}' (ID: {node_id_text})",
                    message=(
                        f"关卡变量引用无法解析：{hint}（该 variable_name 不存在或未被当前存档引用）"
                    ),
                    suggestion=(
                        "请确认：\n"
                        "1) 该 variable_name 在关卡变量代码定义中存在；\n"
                        "2) 当前存档索引 resources.management.level_variables 已引用包含该变量的变量文件；\n"
                        "3) 节点端口写入的是 variable_name（自定义变量键），不要填写 variable_id。"
                    ),
                    reference="资源系统_统一解析层与GUID作用域.md: Phase 4.2",
                    detail={
                        **(attachment.detail or {}),
                        "type": "graph_level_variable_unresolved",
                        "package_id": package_id,
                        "package_name": package_name,
                        "node_id": node_id_text,
                        "node_title": node_title_text,
                        "raw_value": raw_text,
                        "normalized_candidate": normalized_candidate,
                        "port_name": VARIABLE_NAME_PORT_NAME,
                    },
                )
            )

    return issues


__all__ = ["GraphLevelVariableUsageRule", "validate_graph_level_variable_usage"]


