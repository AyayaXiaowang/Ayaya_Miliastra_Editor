from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .pipeline_templates import _load_base_gil_payload_root, _load_template_graph_sample_or_raise
from .pipeline_wire_write import write_patched_gil_by_sections_and_return_output_path


_SCOPE_MASK = 0xFF800000
_SCOPE_MASK_SERVER = 0x40000000
_SCOPE_MASK_CLIENT = 0x40800000


@dataclass(frozen=True, slots=True)
class TemplateCloneBatchContext:
    """A batch context holding decoded base payload for template-clone writeback."""

    effective_base_gil_path: Path
    base_raw_dump_object: Dict[str, Any]
    payload_root: Dict[str, Any]
    template_gil_by_scope: Dict[str, Path]
    template_graph_id_int_by_scope: Dict[str, int]
    template_library_dir_by_scope: Dict[str, Path]
    mapping_path: Path
    graph_generater_root: Path
    prefer_signal_specific_type_id: bool
    auto_sync_ui_custom_variable_defaults: bool
    auto_fill_graph_variable_defaults_from_ui_registry: bool
    ui_registry_autofill_excluded_graph_variable_names: set[str] | None
    preloaded_ui_key_to_guid_for_writeback: Dict[str, int] | None
    preloaded_component_name_to_id: Dict[str, int] | None
    preloaded_entity_name_to_guid: Dict[str, int] | None


def create_template_clone_batch_context(
    *,
    template_gil_by_scope: Dict[str, Path],
    template_graph_id_int_by_scope: Dict[str, int],
    template_library_dir_by_scope: Dict[str, Path],
    base_gil_path: Path,
    mapping_path: Path,
    graph_generater_root: Path,
    prefer_signal_specific_type_id: bool,
    auto_sync_ui_custom_variable_defaults: bool,
    auto_fill_graph_variable_defaults_from_ui_registry: bool,
    ui_registry_autofill_excluded_graph_variable_names: set[str] | None,
    preloaded_ui_key_to_guid_for_writeback: Dict[str, int] | None,
    preloaded_component_name_to_id: Dict[str, int] | None,
    preloaded_entity_name_to_guid: Dict[str, int] | None,
) -> TemplateCloneBatchContext:
    """Create a batch context by decoding the base `.gil` payload once."""

    template_any = next(iter(dict(template_gil_by_scope).values()))
    effective_base_gil_path, base_raw_dump_object, payload_root = _load_base_gil_payload_root(
        base_gil_path=Path(base_gil_path),
        template_gil_path=Path(template_any),
    )
    return TemplateCloneBatchContext(
        effective_base_gil_path=Path(effective_base_gil_path),
        base_raw_dump_object=dict(base_raw_dump_object),
        payload_root=dict(payload_root),
        template_gil_by_scope={str(k): Path(v).resolve() for k, v in dict(template_gil_by_scope).items()},
        template_graph_id_int_by_scope={str(k): int(v) for k, v in dict(template_graph_id_int_by_scope).items()},
        template_library_dir_by_scope={str(k): Path(v).resolve() for k, v in dict(template_library_dir_by_scope).items()},
        mapping_path=Path(mapping_path).resolve(),
        graph_generater_root=Path(graph_generater_root).resolve(),
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
        auto_sync_ui_custom_variable_defaults=bool(auto_sync_ui_custom_variable_defaults),
        auto_fill_graph_variable_defaults_from_ui_registry=bool(auto_fill_graph_variable_defaults_from_ui_registry),
        ui_registry_autofill_excluded_graph_variable_names=(
            set(ui_registry_autofill_excluded_graph_variable_names) if ui_registry_autofill_excluded_graph_variable_names else None
        ),
        preloaded_ui_key_to_guid_for_writeback=dict(preloaded_ui_key_to_guid_for_writeback) if preloaded_ui_key_to_guid_for_writeback else None,
        preloaded_component_name_to_id=dict(preloaded_component_name_to_id) if preloaded_component_name_to_id else None,
        preloaded_entity_name_to_guid=dict(preloaded_entity_name_to_guid) if preloaded_entity_name_to_guid else None,
    )


def _resolve_scope_from_template_graph_id_int(template_graph_id_int: int) -> str:
    """Resolve scope text from a template graph id int mask."""

    scope_mask = int(template_graph_id_int) & int(_SCOPE_MASK)
    if int(scope_mask) == int(_SCOPE_MASK_SERVER):
        return "server"
    if int(scope_mask) == int(_SCOPE_MASK_CLIENT):
        return "client"
    raise ValueError(f"unsupported template_graph_id_int scope mask: {hex(scope_mask)}")


def apply_graph_model_json_template_clone_inplace(
    *,
    ctx: TemplateCloneBatchContext,
    graph_model_json_path: Path,
    template_graph_id_int: int,
    new_graph_name: str,
    new_graph_id_int: Optional[int],
    output_gil_path: Path,
) -> Dict[str, Any]:
    """Apply a single graph writeback into ctx.payload_root without writing output bytes."""

    from .pipeline_template_clone_inplace import apply_template_clone_graph_writeback_inplace

    scope = _resolve_scope_from_template_graph_id_int(int(template_graph_id_int))
    template_gil_path = Path(ctx.template_gil_by_scope[scope]).resolve()
    template_graph_id_int_effective = int(ctx.template_graph_id_int_by_scope[scope])
    template_library_dir = Path(ctx.template_library_dir_by_scope[scope]).resolve()

    template_sample = _load_template_graph_sample_or_raise(
        template_gil_path=Path(template_gil_path),
        template_graph_id_int=int(template_graph_id_int_effective),
    )
    report = apply_template_clone_graph_writeback_inplace(
        graph_model_json_path=Path(graph_model_json_path),
        template_sample=template_sample,
        template_library_dir=Path(template_library_dir),
        effective_base_gil_path=Path(ctx.effective_base_gil_path),
        base_raw_dump_object=dict(ctx.base_raw_dump_object),
        payload_root=ctx.payload_root,
        output_gil_path=Path(output_gil_path),
        template_graph_id_int=int(template_graph_id_int_effective),
        new_graph_name=str(new_graph_name),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
        mapping_path=Path(ctx.mapping_path),
        graph_generater_root=Path(ctx.graph_generater_root),
        preloaded_ui_key_to_guid_for_writeback=(dict(ctx.preloaded_ui_key_to_guid_for_writeback) if ctx.preloaded_ui_key_to_guid_for_writeback else None),
        preloaded_component_name_to_id=(dict(ctx.preloaded_component_name_to_id) if ctx.preloaded_component_name_to_id else None),
        preloaded_entity_name_to_guid=(dict(ctx.preloaded_entity_name_to_guid) if ctx.preloaded_entity_name_to_guid else None),
        prefer_signal_specific_type_id=bool(ctx.prefer_signal_specific_type_id),
        auto_fill_graph_variable_defaults_from_ui_registry=bool(ctx.auto_fill_graph_variable_defaults_from_ui_registry),
        ui_registry_autofill_excluded_graph_variable_names=(
            set(ctx.ui_registry_autofill_excluded_graph_variable_names) if ctx.ui_registry_autofill_excluded_graph_variable_names else None
        ),
    )
    return {"write_report": dict(report)}


def finalize_template_clone_batch_and_write_output(
    *,
    ctx: TemplateCloneBatchContext,
    output_gil_path: Path,
    include_section5: bool,
) -> Path:
    """Finalize the batch writeback by writing the patched `.gil` once at wire-level."""

    from .pipeline_mode_template_clone import _sync_ui_custom_variable_defaults_if_enabled

    ui_custom_variable_sync_report = _sync_ui_custom_variable_defaults_if_enabled(
        enabled=bool(ctx.auto_sync_ui_custom_variable_defaults),
        payload_root=ctx.payload_root,
        effective_base_gil_path=Path(ctx.effective_base_gil_path),
    )
    return write_patched_gil_by_sections_and_return_output_path(
        effective_base_gil_path=Path(ctx.effective_base_gil_path),
        output_gil_path=Path(output_gil_path),
        payload_root=dict(ctx.payload_root),
        include_section5=bool(include_section5 or bool(ui_custom_variable_sync_report.get("applied"))),
    )


__all__ = [
    "TemplateCloneBatchContext",
    "create_template_clone_batch_context",
    "apply_graph_model_json_template_clone_inplace",
    "finalize_template_clone_batch_and_write_output",
]

