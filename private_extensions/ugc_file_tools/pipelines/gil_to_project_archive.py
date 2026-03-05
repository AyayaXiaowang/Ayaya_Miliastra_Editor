from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional


ProgressCallback = Callable[[int, int, str], None]


def _emit_progress(cb: ProgressCallback | None, current: int, total: int, label: str) -> None:
    if cb is None:
        return
    cb(int(current), int(total), str(label or ""))


def _set_last_opened_package(*, graph_generater_root: Path, package_id: str) -> None:
    state_file = Path(graph_generater_root).resolve() / "app" / "runtime" / "package_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    if state_file.exists():
        obj = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(obj, dict):
            obj = {}
    else:
        obj = {}
    obj["last_opened_package_id"] = str(package_id)
    state_file.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class GilToProjectArchivePlan:
    input_gil_file_path: Path
    output_package_root: Path
    package_id: str

    enable_dll_dump: bool = False
    dtype_path: Path | None = None
    parse_status_root: Path | None = None
    data_blob_min_bytes_for_decode: int = 512
    generic_scan_min_bytes: int = 256
    focus_graph_id: int | None = None
    # 可选：仅导入指定的节点图（graph_id_int）。留空则导入全部。
    selected_node_graph_id_ints: list[int] | None = None

    # ===== 选择性导入：资源段开关（默认全开，保持旧行为不变） =====
    export_raw_pyugc_dump: bool = True
    export_node_graphs: bool = True
    export_templates: bool = True
    export_instances: bool = True
    export_combat_presets: bool = True
    export_section15: bool = True
    export_struct_definitions: bool = True
    export_signals: bool = True
    export_data_blobs: bool = True
    export_decoded_dtype_type3: bool = True
    export_decoded_generic: bool = True

    ensure_package_structure_fn: Callable[[str], None] | None = None

    generate_graph_code: bool = True
    overwrite_graph_code: bool = False
    validate_graph_code_after_generate: bool = True

    graph_generater_root_for_validation: Path | None = None
    set_last_opened: bool = False


def run_gil_to_project_archive(
    *,
    plan: GilToProjectArchivePlan,
    progress_cb: ProgressCallback | None = None,
) -> Dict[str, object]:
    input_gil_path = Path(plan.input_gil_file_path).resolve()
    if not input_gil_path.is_file():
        raise FileNotFoundError(str(input_gil_path))

    output_package_root = Path(plan.output_package_root).resolve()
    output_package_root.parent.mkdir(parents=True, exist_ok=True)

    if bool(plan.validate_graph_code_after_generate) and (not bool(plan.generate_graph_code)):
        raise ValueError("validate_graph_code_after_generate=True 需要同时启用 generate_graph_code=True")

    from ugc_file_tools.gil_package_exporter.paths import resolve_default_dtype_path, resolve_parse_status_root_path
    from ugc_file_tools.gil_package_exporter.runner import export_gil_to_package

    dtype_path = Path(plan.dtype_path).resolve() if plan.dtype_path is not None else Path(resolve_default_dtype_path()).resolve()
    parse_status_root = (
        Path(plan.parse_status_root).resolve() if plan.parse_status_root is not None else Path(resolve_parse_status_root_path()).resolve()
    )

    total_steps = 1  # 导出 .gil → 项目存档
    if callable(plan.ensure_package_structure_fn):
        total_steps += 1
    if bool(plan.generate_graph_code):
        total_steps += 1
        if bool(plan.validate_graph_code_after_generate):
            total_steps += 1
    if bool(plan.set_last_opened):
        total_steps += 1

    current_step = 0
    _emit_progress(progress_cb, current_step, total_steps, "准备导入…")

    current_step += 1
    _emit_progress(progress_cb, current_step, total_steps, "正在导入 .gil → 项目存档…")
    export_gil_to_package(
        input_gil_file_path=input_gil_path,
        output_package_root=output_package_root,
        dtype_path=dtype_path,
        enable_dll_dump=bool(plan.enable_dll_dump),
        data_blob_min_bytes_for_decode=int(plan.data_blob_min_bytes_for_decode),
        generic_scan_min_bytes=int(plan.generic_scan_min_bytes),
        focus_graph_id=(int(plan.focus_graph_id) if plan.focus_graph_id is not None else None),
        parse_status_root=parse_status_root,
        export_raw_pyugc_dump=bool(plan.export_raw_pyugc_dump),
        export_node_graphs=bool(plan.export_node_graphs),
        selected_node_graph_id_ints=(list(plan.selected_node_graph_id_ints) if plan.selected_node_graph_id_ints is not None else None),
        export_templates=bool(plan.export_templates),
        export_instances=bool(plan.export_instances),
        export_combat_presets=bool(plan.export_combat_presets),
        export_section15=bool(plan.export_section15),
        export_struct_definitions=bool(plan.export_struct_definitions),
        export_signals=bool(plan.export_signals),
        export_data_blobs=bool(plan.export_data_blobs),
        export_decoded_dtype_type3=bool(plan.export_decoded_dtype_type3),
        export_decoded_generic=bool(plan.export_decoded_generic),
    )

    if callable(plan.ensure_package_structure_fn):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在补齐项目存档目录结构…")
        plan.ensure_package_structure_fn(str(plan.package_id))

    validation_summary: object = None
    if bool(plan.generate_graph_code):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在生成可识别的节点图代码…")
        from ugc_file_tools.graph.code_generation import generate_graph_code_for_package_root

        generate_graph_code_for_package_root(
            output_package_root,
            overwrite=bool(plan.overwrite_graph_code),
        )

        if bool(plan.validate_graph_code_after_generate):
            current_step += 1
            _emit_progress(progress_cb, current_step, total_steps, "正在校验节点图代码…")
            from ugc_file_tools.gil_package_exporter.graph_validation import (
                find_graph_generater_root_from_output_package_root,
                validate_graph_generater_single_package,
            )

            gg_root = (
                Path(plan.graph_generater_root_for_validation).resolve()
                if plan.graph_generater_root_for_validation is not None
                else find_graph_generater_root_from_output_package_root(output_package_root)
            )
            if gg_root is None:
                raise ValueError(f"无法定位 Graph_Generater 根目录用于校验：output_package_root={str(output_package_root)}")
            validation_summary = validate_graph_generater_single_package(graph_generater_root=Path(gg_root), package_id=str(plan.package_id))

    if bool(plan.set_last_opened):
        current_step += 1
        _emit_progress(progress_cb, current_step, total_steps, "正在设置最近打开存档…")

        from ugc_file_tools.gil_package_exporter.graph_validation import find_graph_generater_root_from_output_package_root

        gg_root = (
            Path(plan.graph_generater_root_for_validation).resolve()
            if plan.graph_generater_root_for_validation is not None
            else find_graph_generater_root_from_output_package_root(output_package_root)
        )
        if gg_root is None:
            raise ValueError(f"无法定位 Graph_Generater 根目录用于写入 package_state.json：output_package_root={str(output_package_root)}")
        _set_last_opened_package(graph_generater_root=Path(gg_root), package_id=str(plan.package_id))

    return {
        "input_gil": str(input_gil_path),
        "output_package_root": str(output_package_root),
        "dtype_path": str(dtype_path),
        "parse_status_root": str(parse_status_root),
        "enable_dll_dump": bool(plan.enable_dll_dump),
        "generate_graph_code": bool(plan.generate_graph_code),
        "overwrite_graph_code": bool(plan.overwrite_graph_code),
        "validate_graph_code_after_generate": bool(plan.validate_graph_code_after_generate),
        "validation_summary": validation_summary,
        "set_last_opened": bool(plan.set_last_opened),
        "package_id": str(plan.package_id),
    }


