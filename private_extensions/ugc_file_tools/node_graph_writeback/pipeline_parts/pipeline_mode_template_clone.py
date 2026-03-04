from __future__ import annotations

import copy
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
from ..gil_dump import _choose_next_graph_id, _collect_existing_graph_ids, _ensure_list, _first_dict
from ..node_build import _build_nodes_list_from_templates
from ..node_index import _build_graph_node_id_maps
from ..record_codec import sort_node_pin_records_inplace
from ..struct_node_type_map import build_struct_node_writeback_maps_from_payload_root
from ..template_library import build_template_library
from ..type_id_map import build_node_def_key_to_type_id as _build_node_def_key_to_type_id
from ..type_id_map import build_node_name_to_type_id as _build_node_name_to_type_id
from ..ui_custom_variable_sync import (
    apply_ui_placeholder_custom_variables_to_payload_root,
    try_infer_project_ui_source_dir_from_any_path,
)
from ..writeback_feature_flags import is_writeback_feature_enabled

from .pipeline_after_game_alignment import prune_assembly_list_unused_high_index_inparam_pins_inplace
from .pipeline_entry_ops import (
    _try_find_existing_graph_entry_in_groups_list,
    apply_overwrite_policy_and_append_if_needed_for_template_clone,
)
from .pipeline_graph_model_loader import _load_graph_model_writeback_inputs
from .pipeline_graph_variables_autofill import _maybe_autofill_graph_variables_from_ui_registry
from .pipeline_graph_variables_merge import _normalize_graph_variable_def_table_inplace, build_graph_variables_table_for_entry
from .pipeline_placeholders import (
    _classify_component_key_placeholder_policy_for_writeback,
    _classify_entity_key_placeholder_policy_for_writeback,
    _reset_placeholder_registries_after_writeback,
    _resolve_component_id_registry_for_writeback,
    _resolve_entity_id_registry_for_writeback,
    _set_placeholder_registries_for_writeback,
)
from .pipeline_port_types import (
    _ensure_graph_model_enriched_port_types_inplace,
    _repair_and_validate_dict_mutation_port_types_or_raise,
    _write_port_type_gap_report_and_fail_if_any_or_raise,
)
from .pipeline_signals import _extract_signal_node_def_id_maps_from_payload_root
from .pipeline_templates import _load_base_gil_payload_root, _load_template_graph_sample_or_raise
from .pipeline_ui_keys import _prepare_ui_key_to_guid_registry_for_writeback, _validate_required_ui_keys_or_raise
from .pipeline_ui_registry_legacy import _try_load_ui_key_to_guid_registry_for_graph_model
from .pipeline_wire_write import maybe_write_missing_enum_constants_report, write_patched_gil_by_sections_and_return_output_path


def _merge_ui_guid_registry_legacy_inplace(
    *, graph_model_json_path: Path, required_ui_keys: set[str], ui_key_to_guid_registry: Dict[str, int]
) -> str | None:
    loaded_legacy = _try_load_ui_key_to_guid_registry_for_graph_model(
        graph_model_json_path=Path(graph_model_json_path),
        required_ui_keys=set(required_ui_keys),
    )
    if loaded_legacy is None:
        return None
    legacy_mapping, legacy_path = loaded_legacy
    for k, v in dict(legacy_mapping).items():
        kk = str(k)
        if kk == "" or kk in ui_key_to_guid_registry:
            continue
        if isinstance(v, int):
            ui_key_to_guid_registry[kk] = int(v)
    return str(Path(legacy_path).resolve())


def _ensure_node_graph_section_from_template_if_missing_inplace(
    *, payload_root: Dict[str, Any], template_section: Dict[str, Any]
) -> Dict[str, Any]:
    section = payload_root.get("10")
    if isinstance(section, dict):
        return section
    section = copy.deepcopy(template_section)
    section["1"] = []
    section["7"] = 0
    payload_root["10"] = section
    return section


def _sort_nodes_or_raise(*, graph_model: Dict[str, Any]) -> List[Any]:
    nodes = _normalize_nodes_list(graph_model)
    if not nodes:
        raise ValueError("graph_model.nodes 为空，无法生成节点图")
    return _sort_graph_nodes_for_stable_ids(nodes)


def _allocate_graph_id(*, payload_root: Dict[str, Any], template_graph_id_int: int, new_graph_id_int: Optional[int]) -> int:
    existing_graph_ids = _collect_existing_graph_ids(payload_root)
    scope_mask = int(template_graph_id_int) & 0xFF800000
    return int(new_graph_id_int) if new_graph_id_int is not None else _choose_next_graph_id(
        existing_graph_ids=existing_graph_ids,
        scope_mask=scope_mask,
    )


def _build_new_entry_from_template(
    *,
    template_entry: Dict[str, Any],
    allocated_graph_id: int,
    new_graph_name: str,
    new_nodes_list: List[Any],
) -> Dict[str, Any]:
    new_entry = copy.deepcopy(template_entry)
    header = _first_dict(new_entry.get("1"))
    if not isinstance(header, dict):
        raise ValueError("模板 entry 缺少 header")
    header["5"] = int(allocated_graph_id)
    new_entry["2"] = [str(new_graph_name).strip()]
    new_entry["3"] = list(new_nodes_list)
    _normalize_graph_variable_def_table_inplace(new_entry.get("6"))
    return new_entry


def _write_edges_and_sort_pins_inplace(
    *,
    edges: List[Dict[str, Any]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_title_by_graph_node_id: Dict[str, str],
    graph_node_by_graph_node_id: Dict[str, Any],
    node_defs_by_name: Dict[str, Any],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    template_lib: Any,
    merged_record_id_by_type_and_inparam: Dict[int, Dict[int, int]],
    scope: str,
    graph_variable_type_text_by_name: Dict[str, str],
    signal_maps: Any,
    new_nodes_list: List[Any],
) -> Dict[str, Any]:
    edge_counts = write_edges_inplace(
        edges=edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        data_link_record_template_by_dst_type_id_and_slot_index=template_lib.data_link_record_template_by_dst_type_id_and_slot_index,
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
    return dict(edge_counts)


def _sync_ui_custom_variable_defaults_if_enabled(
    *, enabled: bool, payload_root: Dict[str, Any], effective_base_gil_path: Path
) -> Dict[str, Any]:
    if not bool(enabled):
        return {"applied": False, "reason": "disabled"}
    ui_source_dir = try_infer_project_ui_source_dir_from_any_path(Path(effective_base_gil_path))
    if ui_source_dir is None:
        return {"applied": False, "reason": "ui_source_dir_not_found"}
    return apply_ui_placeholder_custom_variables_to_payload_root(payload_root=payload_root, ui_source_dir=ui_source_dir)


def _apply_constants_and_maybe_prune_assembly_list(
    *,
    sorted_nodes: List[Any],
    edges: List[Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    template_lib: Any,
    merged_record_id_by_type_and_inparam: Dict[int, Dict[int, int]],
    signal_maps: Any,
    scope: str,
    graph_variable_type_text_by_name: Dict[str, str],
    prune_enabled: bool,
) -> Any:
    constants_result = apply_input_constants_and_outparam_types(
        sorted_nodes=sorted_nodes,
        edges=edges,
        node_defs_by_name=node_defs_by_name,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_object_by_node_id_int=node_object_by_node_id_int,
        outparam_record_template_by_type_id_and_index_and_var_type=template_lib.outparam_record_template_by_type_id_and_index_and_var_type,
        record_id_by_node_type_id_and_inparam_index=merged_record_id_by_type_and_inparam,
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
    if bool(prune_enabled):
        prune_assembly_list_unused_high_index_inparam_pins_inplace(
            sorted_nodes=list(sorted_nodes),
            edges=list(edges),
            node_id_int_by_graph_node_id=dict(node_id_int_by_graph_node_id),
            node_object_by_node_id_int=dict(node_object_by_node_id_int),
        )
    return constants_result


def _build_node_id_maps_and_defs(
    *,
    sorted_nodes: List[Any],
    mapping_path: Path,
    scope: str,
    graph_generater_root: Path,
    struct_node_maps: Any,
    signal_maps: Any,
    prefer_signal_specific_type_id: bool,
) -> Tuple[Dict[str, int], Dict[str, int], Dict[str, str], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    name_to_type_id = _build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(scope))
    node_def_key_to_type_id = _build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(scope),
        graph_generater_root=Path(graph_generater_root),
    )
    node_defs_by_name = _load_node_defs_by_scope(graph_generater_root=Path(graph_generater_root), scope=str(scope))
    # 写回需要能定位复合节点 NodeDef（用于端口方向/流程口判定等语义）；仅靠 Graph_Generater NodeDef 目录不包含复合节点。
    node_defs_by_name.update(
        _load_node_defs_by_name_from_registry(workspace_root=Path(graph_generater_root), scope=str(scope))
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
        struct_node_type_id_by_title_and_struct_id=struct_node_maps.node_type_id_by_title_and_struct_id,
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
    )
    return (
        dict(node_id_int_by_graph_node_id),
        dict(node_type_id_by_graph_node_id),
        dict(node_title_by_graph_node_id),
        dict(graph_node_by_graph_node_id),
        dict(node_defs_by_name),
        dict(node_def_key_to_type_id),
    )


def write_graph_model_to_gil(
    *,
    graph_model_json_path: Path,
    template_gil_path: Path,
    base_gil_path: Optional[Path],
    template_library_dir: Optional[Path],
    output_gil_path: Path,
    template_graph_id_int: int,
    new_graph_name: str,
    new_graph_id_int: Optional[int],
    mapping_path: Path,
    graph_generater_root: Path,
    auto_sync_ui_custom_variable_defaults: bool = True,
    auto_fill_graph_variable_defaults_from_ui_registry: bool = True,
    ui_registry_autofill_excluded_graph_variable_names: set[str] | None = None,
    preloaded_ui_key_to_guid_for_writeback: Dict[str, int] | None = None,
    preloaded_component_name_to_id: Dict[str, int] | None = None,
    preloaded_entity_name_to_guid: Dict[str, int] | None = None,
    prefer_signal_specific_type_id: bool = False,
) -> Dict[str, Any]:
    ui_key_to_guid_registry: Dict[str, int] = dict(preloaded_ui_key_to_guid_for_writeback or {})
    inputs = _load_graph_model_writeback_inputs(
        graph_model_json_path=Path(graph_model_json_path),
        scope_graph_id_int=int(template_graph_id_int),
        scope_graph_id_label="template_graph_id_int",
        scope_hint_label="template_scope",
        forbid_id_ref_placeholders=False,
    )
    graph_json_object = inputs.graph_json_object
    placeholders = inputs.placeholders
    required_ui_keys = set(inputs.required_ui_keys)
    layout_name_hint = inputs.layout_name_hint
    graph_model = inputs.graph_model
    graph_variables = list(inputs.graph_variables)
    graph_variable_type_text_by_name = dict(inputs.graph_variable_type_text_by_name)
    scope = str(inputs.scope)

    ui_guid_registry_legacy_source = _merge_ui_guid_registry_legacy_inplace(
        graph_model_json_path=Path(graph_model_json_path),
        required_ui_keys=set(required_ui_keys),
        ui_key_to_guid_registry=ui_key_to_guid_registry,
    )

    component_name_to_id, _component_registry_path = _resolve_component_id_registry_for_writeback(
        graph_model_json_path=Path(graph_model_json_path),
        preloaded_component_name_to_id=preloaded_component_name_to_id,
    )
    allow_unresolved_component_keys, missing_component_names = _classify_component_key_placeholder_policy_for_writeback(
        required_component_names=set(placeholders.required_component_names),
        component_name_to_id=component_name_to_id,
    )
    entity_name_to_guid = _resolve_entity_id_registry_for_writeback(preloaded_entity_name_to_guid=preloaded_entity_name_to_guid)
    allow_unresolved_entity_keys, missing_entity_names = _classify_entity_key_placeholder_policy_for_writeback(
        required_entity_names=set(placeholders.required_entity_names),
        entity_name_to_guid=entity_name_to_guid,
    )

    template_sample = _load_template_graph_sample_or_raise(
        template_gil_path=Path(template_gil_path),
        template_graph_id_int=int(template_graph_id_int),
    )
    template_section = template_sample.template_section
    template_group = template_sample.template_group
    template_entry = template_sample.template_entry
    template_nodes = template_sample.template_nodes
    template_node_id_set = template_sample.template_node_id_set

    effective_base_gil_path, base_raw_dump_object, payload_root = _load_base_gil_payload_root(
        base_gil_path=(Path(base_gil_path) if base_gil_path is not None else None),
        template_gil_path=Path(template_gil_path),
    )

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

    struct_node_maps = build_struct_node_writeback_maps_from_payload_root(payload_root)
    signal_maps = _extract_signal_node_def_id_maps_from_payload_root(payload_root=payload_root)

    section = _ensure_node_graph_section_from_template_if_missing_inplace(payload_root=payload_root, template_section=template_section)
    groups_list = _ensure_list(section, "1")

    template_lib = build_template_library(
        template_nodes=template_nodes,
        template_node_id_set=set(template_node_id_set),
        template_library_dir=template_library_dir,
        effective_base_gil_path=effective_base_gil_path,
    )

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

    merged_record_id_by_type_and_inparam = dict(struct_node_maps.record_id_by_node_type_id_and_inparam_index or {})
    for k, v in dict(composite_artifacts.record_id_by_node_type_id_and_inparam_index).items():
        merged_record_id_by_type_and_inparam.setdefault(int(k), {}).update(dict(v))

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
    planned_graph_id_int = int(new_graph_id_int) if new_graph_id_int is not None else int(template_graph_id_int)
    _write_port_type_gap_report_and_fail_if_any_or_raise(
        graph_model=graph_model,
        graph_scope=str(scope),
        graph_name=str(new_graph_name),
        graph_id_int=int(planned_graph_id_int),
        output_gil_path=Path(output_gil_path),
    )

    sorted_nodes = _sort_nodes_or_raise(graph_model=graph_model)

    (
        node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id,
        node_title_by_graph_node_id,
        graph_node_by_graph_node_id,
    ) = _build_graph_node_id_maps(
        sorted_nodes=sorted_nodes,
        name_to_type_id=name_to_type_id,
        node_def_key_to_type_id=node_def_key_to_type_id,
        struct_node_type_id_by_title_and_struct_id=struct_node_maps.node_type_id_by_title_and_struct_id,
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
    )

    edges = _normalize_edges_list(graph_model)
    inferred_output_port_type_by_src_node_and_port = _infer_output_port_type_by_src_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
    )

    transform_pos = _build_pos_transform(
        graph_json_object=graph_json_object,
        template_entry=template_entry,
        sorted_nodes=sorted_nodes,
    )
    new_nodes_list, node_object_by_node_id_int, missing_node_templates = _build_nodes_list_from_templates(
        sorted_nodes=sorted_nodes,
        transform_pos=transform_pos,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_template_by_type_id=template_lib.node_template_by_type_id,
        inferred_output_port_type_by_src_node_and_port=inferred_output_port_type_by_src_node_and_port,
    )
    if missing_node_templates:
        raise ValueError("模板 .gil 未包含以下节点类型的节点样本，无法克隆写回：\n- " + "\n- ".join(missing_node_templates))

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
        component_name_to_id=component_name_to_id,
        allow_unresolved_component_keys=bool(allow_unresolved_component_keys),
        entity_name_to_guid=entity_name_to_guid,
        allow_unresolved_entity_keys=bool(allow_unresolved_entity_keys),
    )
    constants_result = _apply_constants_and_maybe_prune_assembly_list(
        sorted_nodes=sorted_nodes,
        edges=edges,
        node_defs_by_name=node_defs_by_name,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_object_by_node_id_int=node_object_by_node_id_int,
        template_lib=template_lib,
        merged_record_id_by_type_and_inparam=merged_record_id_by_type_and_inparam,
        signal_maps=signal_maps,
        scope=str(scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        prune_enabled=is_writeback_feature_enabled("prune_assembly_list_unused_high_index_inparam_pins"),
    )

    allocated_graph_id = _allocate_graph_id(
        payload_root=payload_root,
        template_graph_id_int=int(template_graph_id_int),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
    )

    base_existing_entry = _try_find_existing_graph_entry_in_groups_list(groups=groups_list, graph_id_int=int(allocated_graph_id))
    base_existing_graph_variables_table = base_existing_entry.get("6") if isinstance(base_existing_entry, dict) else None

    new_entry = _build_new_entry_from_template(
        template_entry=template_entry,
        allocated_graph_id=int(allocated_graph_id),
        new_graph_name=str(new_graph_name),
        new_nodes_list=list(new_nodes_list),
    )
    built_table = build_graph_variables_table_for_entry(
        graph_variables=list(graph_variables),
        payload_root=payload_root,
        base_existing_graph_variables_table=base_existing_graph_variables_table,
        preserve_base_existing_table_enabled=is_writeback_feature_enabled("graph_variables_preserve_base_existing_table"),
    )
    if built_table is not None:
        new_entry["6"] = built_table
    _reset_placeholder_registries_after_writeback()

    edge_counts = _write_edges_and_sort_pins_inplace(
        edges=edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        template_lib=template_lib,
        merged_record_id_by_type_and_inparam=merged_record_id_by_type_and_inparam,
        scope=str(scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        signal_maps=signal_maps,
        new_nodes_list=list(new_nodes_list),
    )

    replaced_existing_graph_entries, replaced_existing_graph_groups, _replaced_in_place = apply_overwrite_policy_and_append_if_needed_for_template_clone(
        section=section,
        groups_list=groups_list,
        template_group=template_group,
        allocated_graph_id=int(allocated_graph_id),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
        new_entry=dict(new_entry),
    )

    enum_constants_skipped_report_path = maybe_write_missing_enum_constants_report(
        output_gil_path=Path(output_gil_path),
        skipped_enum_constants=getattr(constants_result, "skipped_enum_constants", None),
    )

    ui_custom_variable_sync_report = _sync_ui_custom_variable_defaults_if_enabled(
        enabled=bool(auto_sync_ui_custom_variable_defaults),
        payload_root=payload_root,
        effective_base_gil_path=Path(effective_base_gil_path),
    )

    output_path = write_patched_gil_by_sections_and_return_output_path(
        effective_base_gil_path=Path(effective_base_gil_path),
        output_gil_path=Path(output_gil_path),
        payload_root=payload_root,
        include_section5=bool(ui_custom_variable_sync_report.get("applied")),
    )

    return {
        "template_gil": str(Path(template_gil_path).resolve()),
        "base_gil": str(Path(effective_base_gil_path).resolve()),
        "output_gil": str(output_path),
        "template_graph_id_int": int(template_graph_id_int),
        "new_graph_id_int": int(allocated_graph_id),
        "new_graph_name": str(new_graph_name).strip(),
        "replaced_existing_graph_entries": int(replaced_existing_graph_entries),
        "replaced_existing_graph_groups": int(replaced_existing_graph_groups),
        "nodes_written": len(new_nodes_list),
        **edge_counts,
        "graph_variables_ui_autofill": dict(graph_variables_ui_autofill_report),
        "ui_custom_variable_sync": dict(ui_custom_variable_sync_report),
        "ui_key_allow_unresolved_effective": bool(allow_unresolved_ui_keys),
        "ui_guid_registry_legacy_source": ui_guid_registry_legacy_source,
        "optional_hidden_missing_ui_keys": list(optional_hidden_missing_ui_keys),
        "component_key_allow_unresolved_effective": bool(allow_unresolved_component_keys),
        "component_key_missing_components": list(missing_component_names),
        "entity_key_allow_unresolved_effective": bool(allow_unresolved_entity_keys),
        "entity_key_missing_entities": list(missing_entity_names),
        "enum_constants_total": int(getattr(constants_result, "enum_constants_total", 0)),
        "enum_constants_written": int(getattr(constants_result, "enum_constants_written", 0)),
        "enum_constants_skipped": int(len(getattr(constants_result, "skipped_enum_constants", []) or [])),
        "enum_constants_skipped_report": enum_constants_skipped_report_path,
        "note": "flow edges 按 gia.proto(NodePin/NodeConnection) 构造最小 flow link record 写回（不依赖模板 flow record）。data edges 优先使用模板 record 克隆；若模板缺失对应 dst 输入槽位(slot_index)样本，则按 schema 构造最小 data-link pin record 写入。src 的 data 输出选择使用 OutParam.index=data_output_index(0-based)。多分支会同步写回分支值列表 record（缺样本时也可按 schema 构造）。",
    }

