from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..prechecks import (
    _run_postcheck_graph_variable_writeback_contract_or_raise,
    _run_precheck_node_template_coverage_or_raise,
)

from .pipeline_graph_model_loader import _load_graph_model_writeback_inputs
from .pipeline_mode_pure_json import write_graph_model_to_gil_pure_json
from .pipeline_mode_template_clone import write_graph_model_to_gil
from .pipeline_ui_registry_legacy import _try_load_ui_key_to_guid_registry_for_graph_model


def run_precheck_and_write_and_postcheck(
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
    skip_precheck: bool,
    prefer_signal_specific_type_id: bool = False,
    auto_sync_ui_custom_variable_defaults: bool = True,
    auto_fill_graph_variable_defaults_from_ui_registry: bool = True,
    ui_registry_autofill_excluded_graph_variable_names: set[str] | None = None,
) -> Tuple[Dict[str, Any], Optional[Path], Optional[Path]]:
    precheck_report_path: Optional[Path] = None
    postcheck_report_path: Optional[Path] = None

    if not bool(skip_precheck):
        inputs = _load_graph_model_writeback_inputs(
            graph_model_json_path=Path(graph_model_json_path),
            scope_graph_id_int=int(template_graph_id_int),
            scope_graph_id_label="template_graph_id_int",
            scope_hint_label="template_scope",
            forbid_id_ref_placeholders=False,
        )
        precheck_report_path = _run_precheck_node_template_coverage_or_raise(
            graph_model_json_path=Path(graph_model_json_path),
            template_gil_path=Path(template_gil_path),
            base_gil_path=(Path(base_gil_path) if base_gil_path is not None else None),
            template_graph_id_int=int(template_graph_id_int),
            template_library_dir=(Path(template_library_dir) if template_library_dir is not None else None),
            mapping_path=Path(mapping_path),
            default_scope=str(inputs.scope),
            output_gil_path=Path(output_gil_path),
            graph_generater_root=Path(graph_generater_root),
        )

    report = write_graph_model_to_gil(
        graph_model_json_path=Path(graph_model_json_path),
        template_gil_path=Path(template_gil_path),
        base_gil_path=(Path(base_gil_path) if base_gil_path is not None else None),
        template_library_dir=(Path(template_library_dir) if template_library_dir is not None else None),
        output_gil_path=Path(output_gil_path),
        template_graph_id_int=int(template_graph_id_int),
        new_graph_name=str(new_graph_name),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
        mapping_path=Path(mapping_path),
        graph_generater_root=Path(graph_generater_root),
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
        auto_sync_ui_custom_variable_defaults=bool(auto_sync_ui_custom_variable_defaults),
        auto_fill_graph_variable_defaults_from_ui_registry=bool(auto_fill_graph_variable_defaults_from_ui_registry),
        ui_registry_autofill_excluded_graph_variable_names=(
            set(ui_registry_autofill_excluded_graph_variable_names) if ui_registry_autofill_excluded_graph_variable_names else None
        ),
    )

    if not bool(skip_precheck):
        output_gil_written = Path(str(report.get("output_gil") or "")).resolve()
        if str(output_gil_written) == "" or not output_gil_written.is_file():
            raise FileNotFoundError(f"写回产物不存在，无法执行合约校验：{str(output_gil_written)!r}")
        raw_focus_graph_id_int = report.get("new_graph_id_int")
        if not isinstance(raw_focus_graph_id_int, int):
            raise ValueError(f"写回报告缺少 new_graph_id_int：{raw_focus_graph_id_int!r}")
        focus_graph_id_int = int(raw_focus_graph_id_int)
        postcheck_report_path = _run_postcheck_graph_variable_writeback_contract_or_raise(
            output_gil_path=output_gil_written,
            focus_graph_id_int=int(focus_graph_id_int),
        )

    return report, precheck_report_path, postcheck_report_path


def run_write_and_postcheck_pure_json(
    *,
    graph_model_json_path: Path,
    base_gil_path: Path,
    output_gil_path: Path,
    scope_graph_id_int: int,
    new_graph_name: str,
    new_graph_id_int: Optional[int],
    mapping_path: Path,
    graph_generater_root: Path,
    skip_postcheck: bool,
    prefer_signal_specific_type_id: bool = False,
    auto_sync_ui_custom_variable_defaults: bool = True,
) -> Tuple[Dict[str, Any], Optional[Path]]:
    report = write_graph_model_to_gil_pure_json(
        graph_model_json_path=Path(graph_model_json_path),
        base_gil_path=Path(base_gil_path),
        output_gil_path=Path(output_gil_path),
        scope_graph_id_int=int(scope_graph_id_int),
        new_graph_name=str(new_graph_name),
        new_graph_id_int=(int(new_graph_id_int) if new_graph_id_int is not None else None),
        mapping_path=Path(mapping_path),
        graph_generater_root=Path(graph_generater_root),
        prefer_signal_specific_type_id=bool(prefer_signal_specific_type_id),
        auto_sync_ui_custom_variable_defaults=bool(auto_sync_ui_custom_variable_defaults),
    )

    postcheck_report_path: Optional[Path] = None
    if not bool(skip_postcheck):
        output_gil_written = Path(str(report.get("output_gil") or "")).resolve()
        if str(output_gil_written) == "" or not output_gil_written.is_file():
            raise FileNotFoundError(f"写回产物不存在，无法执行合约校验：{str(output_gil_written)!r}")
        raw_focus_graph_id_int = report.get("new_graph_id_int")
        if not isinstance(raw_focus_graph_id_int, int):
            raise ValueError(f"写回报告缺少 new_graph_id_int：{raw_focus_graph_id_int!r}")
        focus_graph_id_int = int(raw_focus_graph_id_int)
        postcheck_report_path = _run_postcheck_graph_variable_writeback_contract_or_raise(
            output_gil_path=output_gil_written,
            focus_graph_id_int=int(focus_graph_id_int),
        )

    return report, postcheck_report_path


__all__ = [
    "_try_load_ui_key_to_guid_registry_for_graph_model",
    "write_graph_model_to_gil",
    "write_graph_model_to_gil_pure_json",
    "run_precheck_and_write_and_postcheck",
    "run_write_and_postcheck_pure_json",
]

