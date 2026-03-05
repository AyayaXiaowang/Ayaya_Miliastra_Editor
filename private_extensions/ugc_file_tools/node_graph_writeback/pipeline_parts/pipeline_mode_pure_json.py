from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import ugc_file_tools.node_graph_writeback.composite_writeback as _composite_writeback
from ugc_file_tools.graph.port_types import load_node_defs_by_name_from_registry as _load_node_defs_by_name_from_registry
from ugc_file_tools.node_graph_semantics.graph_generater import load_node_defs_by_scope as _load_node_defs_by_scope
from ugc_file_tools.node_graph_semantics.graph_model import (
    normalize_edges_list as _normalize_edges_list,
    normalize_nodes_list as _normalize_nodes_list,
)
from ugc_file_tools.node_graph_semantics.layout import (
    build_pos_transform as _build_pos_transform,
    sort_graph_nodes_for_stable_ids as _sort_graph_nodes_for_stable_ids,
)
from ugc_file_tools.node_graph_semantics.type_inference import (
    infer_output_port_type_by_src_node_and_port as _infer_output_port_type_by_src_node_and_port,
)

from ..constants_writeback import apply_input_constants_and_outparam_types
from ..edges_writeback import write_edges_inplace
from ..gil_dump import _choose_next_graph_id, _collect_existing_graph_ids, _dump_gil_to_raw_json_object, _ensure_list, _get_payload_root
from ..graph_variables import _build_graph_variable_def_item_from_metadata, _extract_struct_defs_from_payload_root
from ..node_build import _build_nodes_list_from_templates
from ..node_index import _build_graph_node_id_maps
from ..record_codec import sort_node_pin_records_inplace
from ..type_id_map import build_node_def_key_to_type_id as _build_node_def_key_to_type_id
from ..type_id_map import build_node_name_to_type_id as _build_node_name_to_type_id
from ..writeback_feature_flags import is_writeback_feature_enabled

from .pipeline_entry_ops import apply_overwrite_policy_and_append_if_needed_for_pure_json
from .pipeline_gil_payload import _bootstrap_node_graph_section_inplace
from .pipeline_graph_model_loader import _load_graph_model_writeback_inputs
from .pipeline_graph_variables_autofill import _maybe_autofill_graph_variables_from_ui_registry
from .pipeline_placeholders import _reset_placeholder_registries_after_writeback, _set_placeholder_registries_for_writeback
from .pipeline_port_types import (
    _ensure_graph_model_enriched_port_types_inplace,
    _repair_and_validate_dict_mutation_port_types_or_raise,
    _write_port_type_gap_report_and_fail_if_any_or_raise,
)
from .pipeline_signals import _extract_signal_node_def_id_maps_from_payload_root
from .pipeline_ui_keys import _prepare_ui_key_to_guid_registry_for_writeback, _validate_required_ui_keys_or_raise
from .pipeline_ui_registry_legacy import _try_load_ui_key_to_guid_registry_for_graph_model
from .pipeline_wire_write import maybe_write_missing_enum_constants_report, write_patched_gil_by_sections_and_return_output_path
from ..ui_custom_variable_sync import (
    apply_ui_placeholder_custom_variables_to_payload_root,
    try_infer_project_ui_source_dir_from_any_path,
)


def write_graph_model_to_gil_pure_json(
    *,
    graph_model_json_path: Path,
    base_gil_path: Path,
    output_gil_path: Path,
    scope_graph_id_int: int,
    new_graph_name: str,
    new_graph_id_int: Optional[int],
    mapping_path: Path,
    graph_generater_root: Path,
    auto_sync_ui_custom_variable_defaults: bool = True,
    auto_fill_graph_variable_defaults_from_ui_registry: bool = True,
    ui_registry_autofill_excluded_graph_variable_names: set[str] | None = None,
    preloaded_ui_key_to_guid_for_writeback: Dict[str, int] | None = None,
    prefer_signal_specific_type_id: bool = False,
) -> Dict[str, Any]:
    """
    纯 JSON 写回（不克隆任何现有 `.gil` 的 node/record 模板）：
    - 输入：GraphModel(JSON, typed)（通常由 Graph_Generater graph_cache 导出）
    - 输出：在 base_gil 中自举创建节点图段，并写入一张新 GraphEntry
    """
    ui_key_to_guid_registry: Dict[str, int] = dict(preloaded_ui_key_to_guid_for_writeback or {})
    inputs = _load_graph_model_writeback_inputs(
        graph_model_json_path=Path(graph_model_json_path),
        scope_graph_id_int=int(scope_graph_id_int),
        scope_graph_id_label="scope_graph_id_int",
        scope_hint_label="scope_hint",
        forbid_id_ref_placeholders=True,
    )
    graph_json_object = inputs.graph_json_object
    required_ui_keys = set(inputs.required_ui_keys)
    layout_name_hint = inputs.layout_name_hint
    graph_model = inputs.graph_model
    graph_variables = list(inputs.graph_variables)
    graph_variable_type_text_by_name = dict(inputs.graph_variable_type_text_by_name)
    scope = str(inputs.scope)

    effective_base_gil_path = Path(base_gil_path).resolve()
    base_raw_dump_object = _dump_gil_to_raw_json_object(effective_base_gil_path)
    payload_root = _get_payload_root(base_raw_dump_object)

    ui_guid_registry_legacy_source: str | None = None
    loaded_legacy = _try_load_ui_key_to_guid_registry_for_graph_model(
        graph_model_json_path=Path(graph_model_json_path),
        required_ui_keys=set(required_ui_keys),
    )
    if loaded_legacy is not None:
        legacy_mapping, legacy_path = loaded_legacy
        for k, v in dict(legacy_mapping).items():
            kk = str(k)
            if kk == "" or kk in ui_key_to_guid_registry:
                continue
            if isinstance(v, int):
                ui_key_to_guid_registry[kk] = int(v)
        ui_guid_registry_legacy_source = str(Path(legacy_path).resolve())

    ui_key_to_guid_registry = _prepare_ui_key_to_guid_registry_for_writeback(
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry or {}),
        required_ui_keys=set(required_ui_keys),
        base_raw_dump_object=base_raw_dump_object,
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
    )

    graph_variables, graph_variables_ui_autofill_report = _maybe_autofill_graph_variables_from_ui_registry(
        graph_variables=list(graph_variables),
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry),
        enabled=bool(auto_fill_graph_variable_defaults_from_ui_registry),
        excluded_names=(
            set(ui_registry_autofill_excluded_graph_variable_names)
            if ui_registry_autofill_excluded_graph_variable_names is not None
            else None
        ),
        base_raw_dump_object=base_raw_dump_object,
    )

    section = _bootstrap_node_graph_section_inplace(payload_root=payload_root)
    groups_list = _ensure_list(section, "1")
    signal_maps = _extract_signal_node_def_id_maps_from_payload_root(payload_root=payload_root)

    name_to_type_id = _build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope))
    node_def_key_to_type_id = _build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )
    active_package_id = graph_json_object.get("active_package_id")
    if not isinstance(active_package_id, str) or active_package_id.strip() == "":
        meta = graph_json_object.get("metadata")
        if isinstance(meta, dict):
            v = meta.get("active_package_id")
            if isinstance(v, str) and v.strip() != "":
                active_package_id = v.strip()
        if not isinstance(active_package_id, str):
            active_package_id = None
    set_active = getattr(import_module("engine.utils.runtime_scope"), "set_active_package_id")
    set_active(str(active_package_id).strip() if isinstance(active_package_id, str) and active_package_id.strip() else None)

    node_defs_by_name = _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope=str(scope))
    # 写回需要能定位复合节点 NodeDef（用于端口方向/流程口判定等语义）；仅靠 Graph_Generater NodeDef 目录不包含复合节点。
    node_defs_by_name.update(_load_node_defs_by_name_from_registry(workspace_root=Path(graph_generater_root), scope=str(scope)))

    composite_artifacts = _composite_writeback.build_composite_writeback_artifacts(
        graph_model=graph_model,
        graph_scope=str(scope),
        workspace_root=Path(graph_generater_root),
        graph_generater_root=Path(graph_generater_root),
        mapping_path=Path(mapping_path),
        node_defs_by_name=dict(node_defs_by_name),
        signal_maps=signal_maps,
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        active_package_id=(str(active_package_id) if isinstance(active_package_id, str) and active_package_id.strip() != "" else None),
    )
    _composite_writeback.apply_composite_artifacts_to_payload_root_inplace(payload_root=payload_root, artifacts=composite_artifacts)
    merged_record_id_by_type_and_inparam: Dict[int, Dict[int, int]] = {}
    for k, v in dict(composite_artifacts.record_id_by_node_type_id_and_inparam_index).items():
        merged_record_id_by_type_and_inparam.setdefault(int(k), {}).update(dict(v))

    nodes = _normalize_nodes_list(graph_model)
    if not nodes:
        raise ValueError("graph_model.nodes 为空，无法生成节点图")
    sorted_nodes = _sort_graph_nodes_for_stable_ids(nodes)

    transform_pos = _build_pos_transform(
        graph_json_object=graph_json_object,
        template_entry={},
        sorted_nodes=sorted_nodes,
    )

    (
        node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id,
        node_title_by_graph_node_id,
        graph_node_by_graph_node_id,
    ) = _build_graph_node_id_maps(
        sorted_nodes=sorted_nodes,
        name_to_type_id=name_to_type_id,
        node_def_key_to_type_id=node_def_key_to_type_id,
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
    )

    _ensure_graph_model_enriched_port_types_inplace(
        graph_model=graph_model,
        graph_variables=list(graph_variables),
        graph_generater_root=Path(graph_generater_root),
        scope=str(scope),
    )
    _repair_and_validate_dict_mutation_port_types_or_raise(
        graph_model=graph_model,
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
    )
    planned_graph_id_int = int(new_graph_id_int) if new_graph_id_int is not None else int(scope_graph_id_int)
    _write_port_type_gap_report_and_fail_if_any_or_raise(
        graph_model=graph_model,
        graph_scope=str(scope),
        graph_name=str(new_graph_name),
        graph_id_int=int(planned_graph_id_int),
        output_gil_path=Path(output_gil_path),
    )

    edges = _normalize_edges_list(graph_model)
    inferred_output_port_type_by_src_node_and_port = _infer_output_port_type_by_src_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
    )

    new_nodes_list, node_object_by_node_id_int, _missing = _build_nodes_list_from_templates(
        sorted_nodes=sorted_nodes,
        transform_pos=transform_pos,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_template_by_type_id={},
        inferred_output_port_type_by_src_node_and_port=inferred_output_port_type_by_src_node_and_port,
    )

    allow_unresolved_ui_keys, optional_hidden_missing_ui_keys = _validate_required_ui_keys_or_raise(
        graph_model_json_path=Path(graph_model_json_path),
        graph_json_object=dict(graph_json_object),
        required_ui_keys=set(required_ui_keys),
        ui_key_to_guid_registry=ui_key_to_guid_registry,
        base_gil_path=Path(effective_base_gil_path),
        base_raw_dump_object=base_raw_dump_object,
        layout_name_hint=(str(layout_name_hint).strip() if layout_name_hint else None),
    )

    _set_placeholder_registries_for_writeback(
        ui_key_to_guid_registry=dict(ui_key_to_guid_registry),
        allow_unresolved_ui_keys=bool(allow_unresolved_ui_keys),
        component_name_to_id=None,
        allow_unresolved_component_keys=False,
        entity_name_to_guid=None,
        allow_unresolved_entity_keys=False,
    )
    constants_result = apply_input_constants_and_outparam_types(
        sorted_nodes=sorted_nodes,
        edges=edges,
        node_defs_by_name=node_defs_by_name,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_object_by_node_id_int=node_object_by_node_id_int,
        outparam_record_template_by_type_id_and_index_and_var_type={},
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_send_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        signal_send_signal_name_port_index_by_signal_name=signal_maps.send_signal_name_port_index_by_signal_name,
        signal_send_param_port_indices_by_signal_name=signal_maps.send_param_port_indices_by_signal_name,
        signal_listen_signal_name_port_index_by_signal_name=signal_maps.listen_signal_name_port_index_by_signal_name,
        signal_listen_param_port_indices_by_signal_name=signal_maps.listen_param_port_indices_by_signal_name,
        signal_server_send_signal_name_port_index_by_signal_name=signal_maps.server_send_signal_name_port_index_by_signal_name,
        signal_server_send_param_port_indices_by_signal_name=signal_maps.server_send_param_port_indices_by_signal_name,
        signal_param_var_type_ids_by_signal_name=signal_maps.param_var_type_ids_by_signal_name,
        signal_index_by_signal_name=signal_maps.signal_index_by_signal_name,
        graph_scope=str(scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
    )
    _reset_placeholder_registries_after_writeback()

    existing_graph_ids = _collect_existing_graph_ids(payload_root)
    scope_mask = int(scope_graph_id_int) & 0xFF800000
    allocated_graph_id = int(new_graph_id_int) if new_graph_id_int is not None else _choose_next_graph_id(
        existing_graph_ids=existing_graph_ids, scope_mask=scope_mask
    )

    replaced_existing_graph_entries = 0
    replaced_existing_graph_groups = 0

    new_entry: Dict[str, Any] = {
        "1": [{"5": int(allocated_graph_id)}],
        "2": [str(new_graph_name).strip()],
        "3": list(new_nodes_list),
    }
    if graph_variables:
        struct_defs = _extract_struct_defs_from_payload_root(payload_root)
        new_entry["6"] = [_build_graph_variable_def_item_from_metadata(v, struct_defs=struct_defs) for v in graph_variables]

    edge_counts = write_edges_inplace(
        edges=edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        data_link_record_template_by_dst_type_id_and_slot_index={},
        record_id_by_node_type_id_and_inparam_index=merged_record_id_by_type_and_inparam,
        graph_scope=str(scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        signal_send_signal_name_port_index_by_signal_name=signal_maps.send_signal_name_port_index_by_signal_name,
        signal_listen_signal_name_port_index_by_signal_name=signal_maps.listen_signal_name_port_index_by_signal_name,
        signal_server_send_signal_name_port_index_by_signal_name=signal_maps.server_send_signal_name_port_index_by_signal_name,
        signal_send_param_port_indices_by_signal_name=signal_maps.send_param_port_indices_by_signal_name,
        signal_listen_param_port_indices_by_signal_name=signal_maps.listen_param_port_indices_by_signal_name,
        signal_server_send_param_port_indices_by_signal_name=signal_maps.server_send_param_port_indices_by_signal_name,
        signal_param_var_type_ids_by_signal_name=signal_maps.param_var_type_ids_by_signal_name,
    )

    for node_obj in list(new_nodes_list):
        if isinstance(node_obj, dict):
            sort_node_pin_records_inplace(node_obj)

    replaced_existing_graph_entries, replaced_existing_graph_groups, _replaced_in_place = apply_overwrite_policy_and_append_if_needed_for_pure_json(
        section=section,
        groups_list=groups_list,
        allocated_graph_id=int(allocated_graph_id),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
        new_entry=dict(new_entry),
    )

    ui_custom_variable_sync_report: Dict[str, Any] = {"applied": False, "reason": "disabled"}
    if bool(auto_sync_ui_custom_variable_defaults):
        ui_source_dir = try_infer_project_ui_source_dir_from_any_path(Path(effective_base_gil_path))
        if ui_source_dir is None:
            ui_custom_variable_sync_report = {"applied": False, "reason": "ui_source_dir_not_found"}
        else:
            ui_custom_variable_sync_report = apply_ui_placeholder_custom_variables_to_payload_root(
                payload_root=payload_root,
                ui_source_dir=ui_source_dir,
            )

    output_path = write_patched_gil_by_sections_and_return_output_path(
        effective_base_gil_path=Path(effective_base_gil_path),
        output_gil_path=Path(output_gil_path),
        payload_root=payload_root,
        include_section5=bool(ui_custom_variable_sync_report.get("applied")),
    )

    enum_constants_skipped_report_path = maybe_write_missing_enum_constants_report(
        output_gil_path=Path(output_gil_path),
        skipped_enum_constants=getattr(constants_result, "skipped_enum_constants", None),
    )

    return {
        "mode": "pure_json",
        "base_gil": str(Path(effective_base_gil_path).resolve()),
        "output_gil": str(output_path),
        "scope_graph_id_int": int(scope_graph_id_int),
        "new_graph_id_int": int(allocated_graph_id),
        "new_graph_name": str(new_graph_name).strip(),
        "replaced_existing_graph_entries": int(replaced_existing_graph_entries),
        "replaced_existing_graph_groups": int(replaced_existing_graph_groups),
        "nodes_written": len(new_nodes_list),
        **dict(edge_counts),
        "graph_variables_ui_autofill": dict(graph_variables_ui_autofill_report),
        "ui_custom_variable_sync": dict(ui_custom_variable_sync_report),
        "ui_key_allow_unresolved_effective": bool(allow_unresolved_ui_keys),
        "ui_guid_registry_legacy_source": ui_guid_registry_legacy_source,
        "optional_hidden_missing_ui_keys": list(optional_hidden_missing_ui_keys),
        "enum_constants_total": int(getattr(constants_result, "enum_constants_total", 0)),
        "enum_constants_written": int(getattr(constants_result, "enum_constants_written", 0)),
        "enum_constants_skipped": int(len(getattr(constants_result, "skipped_enum_constants", []) or [])),
        "enum_constants_skipped_report": enum_constants_skipped_report_path,
        "note": "纯 JSON 写回：不克隆任何现有 .gil 的节点/record 模板；节点/常量/连线均由 GraphModel(JSON)+Graph_Generater NodeDef 推导并按 schema 写入。",
    }

