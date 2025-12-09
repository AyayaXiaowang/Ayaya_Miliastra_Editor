from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from engine.graph.common import (
    STRUCT_BUILD_NODE_TITLE,
    STRUCT_BUILD_STATIC_INPUTS,
    STRUCT_MODIFY_NODE_TITLE,
    STRUCT_MODIFY_STATIC_INPUTS,
    STRUCT_NAME_PORT_NAME,
    STRUCT_NODE_TITLES,
    STRUCT_SPLIT_NODE_TITLE,
    STRUCT_SPLIT_STATIC_INPUTS,
    STRUCT_SPLIT_STATIC_OUTPUTS,
    STRUCT_BUILD_STATIC_OUTPUTS,
    STRUCT_MODIFY_STATIC_OUTPUTS,
)
from engine.graph.models.graph_model import NodeModel
from engine.nodes.node_definition_loader import NodeDef
from ui.dialogs.struct_definition_types import param_type_to_canonical


@dataclass(frozen=True)
class StructBindingContext:
    """结构体绑定上下文（纯数据）"""

    struct_id: str
    struct_name: str
    selected_fields: List[Tuple[str, str]]


@dataclass(frozen=True)
class StructPortSyncPlan:
    """结构体节点端口与常量的同步计划"""

    struct_id: str
    struct_name_constant: str
    add_inputs: List[str]
    add_outputs: List[str]


def _extract_struct_fields(struct_data: Mapping[str, object]) -> List[Tuple[str, str]]:
    """从结构体定义 JSON 中提取字段列表，返回 (字段名, 规范类型名)。"""
    value_entries = struct_data.get("value")
    if not isinstance(value_entries, Sequence) or isinstance(value_entries, (str, bytes)):
        return []

    fields: List[Tuple[str, str]] = []
    for entry in value_entries:
        if not isinstance(entry, Mapping):
            continue
        raw_name = entry.get("key")
        raw_param_type = entry.get("param_type")
        field_name = str(raw_name).strip() if isinstance(raw_name, str) else ""
        param_type = str(raw_param_type).strip() if isinstance(raw_param_type, str) else ""
        if not field_name or not param_type:
            continue
        canonical_type = param_type_to_canonical(param_type)
        fields.append((field_name, canonical_type))
    return fields


def resolve_struct_binding(
    binding_payload: Mapping[str, object],
    structs: Mapping[str, Mapping[str, object]],
) -> Optional[StructBindingContext]:
    """基于绑定与结构体定义，解析出可用的结构体绑定上下文。"""
    struct_id_value = binding_payload.get("struct_id") if isinstance(binding_payload, Mapping) else None
    struct_id = str(struct_id_value) if struct_id_value is not None else ""
    if not struct_id or struct_id not in structs:
        return None

    struct_data = structs[struct_id]
    all_fields = _extract_struct_fields(struct_data)
    if not all_fields:
        return None

    selected_names_value = binding_payload.get("field_names") if isinstance(binding_payload, Mapping) else None
    selected_names: List[str] = []
    if isinstance(selected_names_value, Sequence) and not isinstance(selected_names_value, (str, bytes)):
        for entry in selected_names_value:
            if isinstance(entry, str) and entry:
                selected_names.append(entry)

    if not selected_names:
        selected_names = [name for name, _ in all_fields]

    selected_set = set(selected_names)
    selected_fields: List[Tuple[str, str]] = [
        (name, type_name) for (name, type_name) in all_fields if name in selected_set
    ]
    if not selected_fields:
        return None

    raw_struct_name = binding_payload.get("struct_name") if isinstance(binding_payload, Mapping) else None
    struct_name_text = ""
    if isinstance(raw_struct_name, str) and raw_struct_name.strip():
        struct_name_text = raw_struct_name.strip()
    else:
        raw_name_from_def = struct_data.get("name")
        if isinstance(raw_name_from_def, str) and raw_name_from_def.strip():
            struct_name_text = raw_name_from_def.strip()
        else:
            struct_name_text = struct_id

    return StructBindingContext(
        struct_id=struct_id,
        struct_name=struct_name_text,
        selected_fields=selected_fields,
    )


def build_struct_node_def_proxy(
    node_title: str,
    base_def: NodeDef,
    context: StructBindingContext,
) -> Optional[NodeDef]:
    """基于结构体绑定构造带字段类型的 NodeDef 代理。"""
    input_types: Dict[str, str] = dict(getattr(base_def, "input_types", {}) or {})
    output_types: Dict[str, str] = dict(getattr(base_def, "output_types", {}) or {})

    if node_title == STRUCT_SPLIT_NODE_TITLE:
        static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
        for field_name, field_type in context.selected_fields:
            if field_name in static_outputs:
                continue
            output_types.setdefault(field_name, field_type)
    elif node_title == STRUCT_BUILD_NODE_TITLE:
        static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
        for field_name, field_type in context.selected_fields:
            if field_name in static_inputs:
                continue
            input_types.setdefault(field_name, field_type)
    elif node_title == STRUCT_MODIFY_NODE_TITLE:
        static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
        for field_name, field_type in context.selected_fields:
            if field_name in static_inputs:
                continue
            input_types.setdefault(field_name, field_type)
    else:
        return None

    return NodeDef(
        name=base_def.name,
        category=base_def.category,
        inputs=list(base_def.inputs),
        outputs=list(base_def.outputs),
        description=base_def.description,
        scopes=list(base_def.scopes),
        mount_restrictions=list(base_def.mount_restrictions),
        doc_reference=base_def.doc_reference,
        input_types=input_types,
        output_types=output_types,
        input_generic_constraints=dict(base_def.input_generic_constraints),
        output_generic_constraints=dict(base_def.output_generic_constraints),
        dynamic_port_type=base_def.dynamic_port_type,
        is_composite=base_def.is_composite,
        composite_id=base_def.composite_id,
    )


def plan_struct_port_sync(node: NodeModel, context: StructBindingContext) -> StructPortSyncPlan:
    """基于结构体绑定生成端口与常量更新计划（纯数据，不落地 UI）。"""
    node_title = getattr(node, "title", "") or ""
    existing_inputs = {getattr(port, "name", "") for port in (node.inputs or []) if getattr(port, "name", "")}
    existing_outputs = {getattr(port, "name", "") for port in (node.outputs or []) if getattr(port, "name", "")}

    add_inputs: List[str] = []
    add_outputs: List[str] = []

    if node_title == STRUCT_SPLIT_NODE_TITLE:
        static_outputs = set(STRUCT_SPLIT_STATIC_OUTPUTS)
        for field_name, _ in context.selected_fields:
            if field_name in static_outputs or field_name in existing_outputs:
                continue
            add_outputs.append(field_name)
    elif node_title == STRUCT_BUILD_NODE_TITLE:
        static_inputs = set(STRUCT_BUILD_STATIC_INPUTS)
        for field_name, _ in context.selected_fields:
            if field_name in static_inputs or field_name in existing_inputs:
                continue
            add_inputs.append(field_name)
    elif node_title == STRUCT_MODIFY_NODE_TITLE:
        static_inputs = set(STRUCT_MODIFY_STATIC_INPUTS)
        for field_name, _ in context.selected_fields:
            if field_name in static_inputs or field_name in existing_inputs:
                continue
            add_inputs.append(field_name)
    else:
        return StructPortSyncPlan(
            struct_id=context.struct_id,
            struct_name_constant=context.struct_name,
            add_inputs=[],
            add_outputs=[],
        )

    return StructPortSyncPlan(
        struct_id=context.struct_id,
        struct_name_constant=context.struct_name,
        add_inputs=add_inputs,
        add_outputs=add_outputs,
    )


__all__ = [
    "StructBindingContext",
    "StructPortSyncPlan",
    "build_struct_node_def_proxy",
    "plan_struct_port_sync",
    "resolve_struct_binding",
]

