from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence, Set, Tuple

from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.utils.graph.graph_utils import (
    build_node_map,
    get_node_display_info,
)
from engine.graph.common import (
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_NODE_TITLES,
)

from ..comprehensive_types import ValidationIssue
from .base import BaseComprehensiveRule
from .helpers import GraphAttachment, get_graph_snapshot, iter_all_package_graphs


def _extract_struct_fields_from_payload(struct_payload: Mapping[str, Any]) -> Set[str]:
    """从结构体定义 payload 中提取字段名集合。"""
    value_entries = struct_payload.get("value")
    if not isinstance(value_entries, Sequence):
        return set()

    names: Set[str] = set()
    for entry in value_entries:
        if not isinstance(entry, Mapping):
            continue
        raw_name = entry.get("key")
        field_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
        if field_name:
            names.add(field_name)
    return names


def _build_struct_definitions() -> Dict[str, Dict[str, Any]]:
    """构造 {struct_id: payload} 映射，仅包含结构体定义本身。"""
    schema_view = get_default_definition_schema_view()
    all_structs = schema_view.get_all_struct_definitions()
    result: Dict[str, Dict[str, Any]] = {}
    for struct_id, payload in all_structs.items():
        if not isinstance(struct_id, str):
            continue
        if not isinstance(payload, dict):
            continue
        result[struct_id] = dict(payload)
    return result


class StructUsageRule(BaseComprehensiveRule):
    """基于包级结构体定义的结构体节点使用一致性校验。

    覆盖范围：
    - 节点是否已经绑定结构体；
    - 绑定的结构体 ID 是否存在，且仍为合法结构体；
    - 绑定记录中的字段名是否都存在于对应结构体定义中。
    """

    rule_id = "package.struct_usage"
    category = "结构体系统"
    default_level = "error"

    def run(self, ctx) -> List[ValidationIssue]:
        return validate_package_struct_usage(self.validator)


def validate_package_struct_usage(validator) -> List[ValidationIssue]:
    """在整个存档包范围内校验结构体定义与结构体节点用法的一致性。"""
    package = getattr(validator, "package", None)
    resource_manager = getattr(validator, "resource_manager", None)
    if package is None or resource_manager is None:
        return []

    struct_definitions = _build_struct_definitions()
    field_names_by_struct_id: Dict[str, Set[str]] = {}
    for struct_id, payload in struct_definitions.items():
        field_names_by_struct_id[struct_id] = _extract_struct_fields_from_payload(payload)

    issues: List[ValidationIssue] = []

    attachments = iter_all_package_graphs(
        resource_manager,
        package.templates,
        package.instances,
        package.level_entity,
    )

    for attachment in attachments:
        # 仅对服务器节点图执行结构体节点校验
        if attachment.graph_config.graph_type != "server":
            continue
        issues.extend(
            _validate_structs_in_single_graph(
                attachment,
                struct_definitions,
                field_names_by_struct_id,
            )
        )

    return issues


def _validate_structs_in_single_graph(
    attachment: GraphAttachment,
    struct_definitions: Dict[str, Dict[str, Any]],
    field_names_by_struct_id: Dict[str, Set[str]],
) -> List[ValidationIssue]:
    graph_config = attachment.graph_config
    graph_data = graph_config.data or {}
    if "nodes" not in graph_data:
        return []

    snapshot = get_graph_snapshot(graph_data, cache_key=attachment.graph_id)
    nodes = snapshot.nodes
    if not nodes:
        return []

    metadata = graph_data.get("metadata") or {}
    struct_bindings_raw = metadata.get("struct_bindings") or {}
    struct_bindings: Dict[str, Dict[str, Any]] = (
        struct_bindings_raw if isinstance(struct_bindings_raw, dict) else {}
    )

    nodes_by_id = build_node_map(nodes)

    base_location = attachment.location_compact
    base_detail = dict(attachment.detail)
    base_detail["graph_id"] = attachment.graph_id
    base_detail["graph_name"] = graph_config.name

    issues: List[ValidationIssue] = []

    for node in nodes:
        node_id, node_title, _ = get_node_display_info(node)
        if not node_id or node_title not in STRUCT_NODE_TITLES:
            continue

        node_detail = dict(base_detail)
        node_detail["node_id"] = node_id
        node_detail["node_title"] = node_title

        node_location = f"{base_location} > 节点 '{node_title}' (ID: {node_id})"

        binding = struct_bindings.get(node_id) or {}
        struct_id = ""
        raw_struct_id = binding.get("struct_id")
        if isinstance(raw_struct_id, str):
            struct_id = raw_struct_id.strip()
        elif raw_struct_id is not None:
            struct_id = str(raw_struct_id)

        # 1) 结构体存在性校验（节点必须绑定一个基础结构体）
        if not struct_id:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=node_location,
                    message="结构体节点未选择结构体。",
                    suggestion="请在编辑器中为该节点选择一个基础结构体，局内存档结构体不支持直接绑定到结构体节点。",
                    reference="节点图变量声明设计.md: 结构体节点绑定约定",
                    detail=node_detail,
                )
            )
            continue

        struct_payload = struct_definitions.get(struct_id)
        if struct_payload is None:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=node_location,
                    message="结构体节点引用了在当前工程中不存在的结构体定义（可能已被删除或重命名）。",
                    suggestion="请在“管理配置/结构体定义”中确认该结构体是否仍然存在，必要时在节点上重新选择一个有效的基础结构体。",
                    reference="节点图变量声明设计.md: 结构体定义与节点绑定",
                    detail={**node_detail, "struct_id": struct_id},
                )
            )
            continue

        struct_type_value = struct_payload.get("struct_ype")
        struct_type = str(struct_type_value).strip() if isinstance(struct_type_value, str) else ""
        if struct_type and struct_type != "basic":
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=node_location,
                    message="结构体节点绑定的目标不是基础结构体（例如绑定到了局内存档结构体）。",
                    suggestion="请在结构体定义中确认 struct_ype 字段为 'basic'，并在节点上重新选择一个基础结构体。",
                    reference="节点图变量声明设计.md: 结构体类型约束",
                    detail={**node_detail, "struct_id": struct_id, "struct_ype": struct_type or "<empty>"},
                )
            )
            continue

        # 2) 字段列表一致性校验：绑定记录中的字段名必须存在于结构体定义里
        bound_field_names_value = binding.get("field_names") or []
        bound_field_names: List[str] = []
        if isinstance(bound_field_names_value, Sequence) and not isinstance(
            bound_field_names_value, (str, bytes)
        ):
            for entry in bound_field_names_value:
                if isinstance(entry, str) and entry:
                    bound_field_names.append(entry)

        defined_fields = field_names_by_struct_id.get(struct_id) or set()
        if not defined_fields:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=node_location,
                    message="结构体定义中未声明任何字段，无法用于当前结构体节点。",
                    suggestion="请在“管理配置/结构体定义”中为该结构体添加至少一个字段，或在节点图中移除对该结构体的依赖。",
                    reference="节点图变量声明设计.md: 结构体字段声明",
                    detail={**node_detail, "struct_id": struct_id},
                )
            )
            continue

        # 若绑定中未显式记录字段列表，视为“使用全部字段”，与 UI 行为保持一致。
        if not bound_field_names:
            bound_field_names = sorted(defined_fields)

        invalid_fields: List[str] = []
        for field_name in bound_field_names:
            if field_name not in defined_fields:
                invalid_fields.append(field_name)

        if invalid_fields:
            issues.append(
                ValidationIssue(
                    level="error",
                    category="结构体系统",
                    location=node_location,
                    message="结构体节点绑定的字段在目标结构体定义中不存在。",
                    suggestion="请在结构体定义中确认字段是否已被重命名或移除，并在节点的“配置结构体与字段”对话框中重新勾选有效字段。",
                    reference="节点图变量声明设计.md: 结构体字段一致性",
                    detail={
                        **node_detail,
                        "struct_id": struct_id,
                        "invalid_fields": list(invalid_fields),
                    },
                )
            )

    return issues


__all__ = ["StructUsageRule", "validate_package_struct_usage"]


