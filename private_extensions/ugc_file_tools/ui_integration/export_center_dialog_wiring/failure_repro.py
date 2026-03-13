from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .env import ExportCenterDialogWiringEnv

_FAILURE_REPRO_JSON_INDENT = 2


def build_export_failure_result_text(env: ExportCenterDialogWiringEnv, message: str) -> str:
    """构造导出失败时执行页“结果摘要”应展示的全文文本。"""

    plan_obj = getattr(env.rt, "last_execute_plan_obj", None)
    payload = _build_execute_ui_snapshot(env)
    payload["cli"] = _build_cli_snapshot(env, plan_obj)
    payload["last_execute"] = {
        "fmt": str(getattr(env.rt, "last_execute_fmt", "") or ""),
        "precheck_skipped_inputs": list(getattr(env.rt, "last_execute_precheck_skipped_inputs", []) or []),
        "precheck_warnings": list(getattr(env.rt, "last_execute_precheck_warnings", []) or []),
        "selection_snapshot": list(getattr(env.rt, "last_execute_selection_snapshot", []) or []),
        "plan_snapshot": _build_plan_snapshot(plan_obj),
        "gil_selection_manifest": _build_gil_selection_manifest(plan_obj),
    }
    return format_export_failure_repro_text(
        payload=dict(payload),
        message=str(message),
        execute_log_text=str(env.execute.log_text.toPlainText() or ""),
    )


def _build_cli_snapshot(env: ExportCenterDialogWiringEnv, plan_obj: object | None) -> dict[str, object] | None:
    """构造用于复现的 CLI 命令模板快照。"""

    if plan_obj is None:
        return None

    from ..export_center.plans import _ExportGilPlan

    if isinstance(plan_obj, _ExportGilPlan):
        return {"gil_project_import": _build_gil_project_import_cli(env, plan_obj)}
    return None


def _build_gil_project_import_cli(env: ExportCenterDialogWiringEnv, plan_obj: object) -> dict[str, object]:
    """构造 project import（写回 .gil）的 CLI 命令模板。"""

    from .._cli_subprocess import build_run_ugc_file_tools_command
    from ..export_center.plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        raise TypeError(f"expected _ExportGilPlan, got {type(plan_obj).__name__}")

    selection_json_placeholder = "<writeback_selection.json>"
    report_json_placeholder = "<writeback_report.json>"
    id_ref_overrides_placeholder = "<id_ref_overrides.json>"

    argv: list[str] = [
        "project",
        "import",
        "--dangerous",
        "--project-archive",
        str(Path(plan_obj.project_root).resolve()),
        "--mode",
        str(plan_obj.struct_mode),
        "--templates-mode",
        str(plan_obj.templates_mode),
        "--instances-mode",
        str(plan_obj.instances_mode),
        "--signals-param-build-mode",
        str(plan_obj.signals_param_build_mode),
        "--ui-widget-templates-mode",
        str(plan_obj.ui_widget_templates_mode),
        "--selection-json",
        str(selection_json_placeholder),
        "--report",
        str(report_json_placeholder),
        str(Path(plan_obj.input_gil_path).resolve()),
        str(Path(plan_obj.output_user_path).resolve()),
    ]
    if plan_obj.ui_export_record_id is not None:
        argv.extend(["--ui-export-record", str(plan_obj.ui_export_record_id)])
    if plan_obj.id_ref_gil_file is not None:
        argv.extend(["--id-ref-gil", str(Path(plan_obj.id_ref_gil_file).resolve())])
    has_overrides = bool(plan_obj.id_ref_override_component_name_to_id or plan_obj.id_ref_override_entity_name_to_guid)
    if has_overrides:
        argv.extend(["--id-ref-overrides-json", str(id_ref_overrides_placeholder)])

    overrides_payload = {
        "version": 1,
        "component_name_to_id": dict(plan_obj.id_ref_override_component_name_to_id or {}),
        "entity_name_to_guid": dict(plan_obj.id_ref_override_entity_name_to_guid or {}),
    }

    return {
        "cwd": str(Path(env.workspace_root).resolve()),
        "selection_json_placeholder": str(selection_json_placeholder),
        "report_json_placeholder": str(report_json_placeholder),
        "id_ref_overrides_json_placeholder": str(id_ref_overrides_placeholder) if has_overrides else None,
        "id_ref_overrides_json": dict(overrides_payload) if has_overrides else None,
        "command_template": build_run_ugc_file_tools_command(workspace_root=Path(env.workspace_root), argv=argv),
        "argv_template": list(argv),
    }


def _jsonable(value: object) -> object:
    """将对象转换为可 JSON 序列化的基本类型。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(x) for x in list(value)]
    return str(value)


def _snapshot_combo(combo: object) -> dict[str, object]:
    """提取 QComboBox 的可选项与当前选择快照。"""

    count = int(getattr(combo, "count")())
    current_index = int(getattr(combo, "currentIndex")())
    current_text = str(getattr(combo, "currentText")() or "")
    current_data = _jsonable(getattr(combo, "currentData")())
    options: list[dict[str, object]] = []
    for i in range(count):
        options.append(
            {
                "index": int(i),
                "text": str(getattr(combo, "itemText")(int(i)) or ""),
                "data": _jsonable(getattr(combo, "itemData")(int(i))),
            }
        )
    return {
        "count": int(count),
        "current_index": int(current_index),
        "current_text": str(current_text),
        "current_data": current_data,
        "options": list(options),
    }


def _snapshot_line_edit(edit: object) -> str:
    """提取 QLineEdit 当前文本快照。"""

    return str(getattr(edit, "text")() or "")


def _snapshot_checkbox(cb: object) -> bool:
    """提取 QCheckBox 当前选中状态快照。"""

    return bool(getattr(cb, "isChecked")())


def _snapshot_spin(spin: object) -> int:
    """提取 QSpinBox/QDoubleSpinBox 当前值的整型快照。"""

    return int(getattr(spin, "value")())


def _snapshot_resource_item(it: object, *, include_display_text: bool, picker: object) -> dict[str, object]:
    """提取资源选择条目的可复制快照。"""

    out: dict[str, object] = {
        "key": str(getattr(it, "key", "") or ""),
        "source_root": str(getattr(it, "source_root", "") or ""),
        "category": str(getattr(it, "category", "") or ""),
        "relative_path": str(getattr(it, "relative_path", "") or ""),
        "absolute_path": str(getattr(it, "absolute_path", "") or ""),
    }
    if include_display_text:
        out["display_text"] = str(getattr(picker, "get_item_display_text")(it))
    return out


def _build_export_gil_plan_snapshot(plan_obj: object) -> dict[str, object]:
    """构造 _ExportGilPlan 的可序列化快照。"""

    from ..export_center.plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        raise TypeError(f"expected _ExportGilPlan, got {type(plan_obj).__name__}")

    return {
        "type": "_ExportGilPlan",
        "package_id": str(plan_obj.package_id),
        "project_root": str(Path(plan_obj.project_root).resolve()),
        "input_gil_path": str(Path(plan_obj.input_gil_path).resolve()),
        "use_builtin_empty_base": bool(plan_obj.use_builtin_empty_base),
        "output_user_path": str(Path(plan_obj.output_user_path).resolve()),
        "struct_mode": str(plan_obj.struct_mode),
        "templates_mode": str(plan_obj.templates_mode),
        "instances_mode": str(plan_obj.instances_mode),
        "signals_param_build_mode": str(plan_obj.signals_param_build_mode),
        "prefer_signal_specific_type_id": bool(plan_obj.prefer_signal_specific_type_id),
        "ui_widget_templates_mode": str(plan_obj.ui_widget_templates_mode),
        "write_ui": bool(plan_obj.write_ui),
        "ui_auto_sync_custom_variables": bool(plan_obj.ui_auto_sync_custom_variables),
        "selected_ui_html_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_ui_html_files or [])],
        "ui_workbench_bundle_update_html_files": [
            str(Path(p).resolve()) for p in list(plan_obj.ui_workbench_bundle_update_html_files or [])
        ],
        "ui_layout_conflict_resolutions": [dict(x) for x in list(plan_obj.ui_layout_conflict_resolutions or [])],
        "node_graph_conflict_resolutions": [dict(x) for x in list(plan_obj.node_graph_conflict_resolutions or [])],
        "template_conflict_resolutions": [dict(x) for x in list(plan_obj.template_conflict_resolutions or [])],
        "instance_conflict_resolutions": [dict(x) for x in list(plan_obj.instance_conflict_resolutions or [])],
        "selected_custom_variable_refs": [dict(x) for x in list(plan_obj.selected_custom_variable_refs or [])],
        "selected_level_custom_variable_ids": [str(x) for x in list(plan_obj.selected_level_custom_variable_ids or [])],
        "selected_template_json_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_template_json_files or [])],
        "selected_instance_json_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_instance_json_files or [])],
        "selected_graph_code_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_graph_code_files or [])],
        "selected_struct_ids": [str(x) for x in list(plan_obj.selected_struct_ids or [])],
        "selected_ingame_struct_ids": [str(x) for x in list(plan_obj.selected_ingame_struct_ids or [])],
        "selected_signal_ids": [str(x) for x in list(plan_obj.selected_signal_ids or [])],
        "graph_source_roots": [str(Path(p).resolve()) for p in list(plan_obj.graph_source_roots or [])],
        "ui_export_record_id": str(plan_obj.ui_export_record_id) if plan_obj.ui_export_record_id is not None else None,
        "id_ref_gil_file": str(Path(plan_obj.id_ref_gil_file).resolve()) if plan_obj.id_ref_gil_file is not None else None,
        "id_ref_override_component_name_to_id": dict(plan_obj.id_ref_override_component_name_to_id or {}),
        "id_ref_override_entity_name_to_guid": dict(plan_obj.id_ref_override_entity_name_to_guid or {}),
    }


def _build_repair_signals_plan_snapshot(plan_obj: object) -> dict[str, object]:
    """构造 _RepairSignalsPlan 的可序列化快照。"""

    from ..export_center.plans import _RepairSignalsPlan

    if not isinstance(plan_obj, _RepairSignalsPlan):
        raise TypeError(f"expected _RepairSignalsPlan, got {type(plan_obj).__name__}")

    return {
        "type": "_RepairSignalsPlan",
        "package_id": str(plan_obj.package_id),
        "project_root": str(Path(plan_obj.project_root).resolve()),
        "input_gil_path": str(Path(plan_obj.input_gil_path).resolve()),
        "output_gil_path": str(Path(plan_obj.output_gil_path).resolve()),
        "selected_graph_code_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_graph_code_files or [])],
        "graph_source_roots": [str(Path(p).resolve()) for p in list(plan_obj.graph_source_roots or [])],
        "prune_placeholder_orphans": bool(plan_obj.prune_placeholder_orphans),
    }


def _build_merge_signal_entries_plan_snapshot(plan_obj: object) -> dict[str, object]:
    """构造 _MergeSignalEntriesPlan 的可序列化快照。"""

    from ..export_center.plans import _MergeSignalEntriesPlan

    if not isinstance(plan_obj, _MergeSignalEntriesPlan):
        raise TypeError(f"expected _MergeSignalEntriesPlan, got {type(plan_obj).__name__}")

    return {
        "type": "_MergeSignalEntriesPlan",
        "package_id": str(plan_obj.package_id),
        "project_root": str(Path(plan_obj.project_root).resolve()),
        "input_gil_path": str(Path(plan_obj.input_gil_path).resolve()),
        "output_gil_path": str(Path(plan_obj.output_gil_path).resolve()),
        "keep_signal_name": str(plan_obj.keep_signal_name),
        "remove_signal_name": str(plan_obj.remove_signal_name),
        "rename_keep_to": str(plan_obj.rename_keep_to),
        "patch_composite_pin_index": bool(plan_obj.patch_composite_pin_index),
    }


def _build_export_gia_plan_snapshot(plan_obj: object) -> dict[str, object]:
    """构造 _ExportGiaPlan 的可序列化快照。"""

    from ..export_center.plans import _ExportGiaPlan

    if not isinstance(plan_obj, _ExportGiaPlan):
        raise TypeError(f"expected _ExportGiaPlan, got {type(plan_obj).__name__}")

    graph_sel = plan_obj.graph_selection
    graph_files = [str(Path(p).resolve()) for p in list(getattr(graph_sel, "graph_code_files", []) or [])]
    graph_roots = [str(Path(p).resolve()) for p in list(getattr(graph_sel, "graph_source_roots", []) or [])]
    return {
        "type": "_ExportGiaPlan",
        "package_id": str(plan_obj.package_id),
        "project_root": str(Path(plan_obj.project_root).resolve()),
        "graph_selection": {"graph_code_files": list(graph_files), "graph_source_roots": list(graph_roots)},
        "template_json_files": [str(Path(p).resolve()) for p in list(plan_obj.template_json_files or [])],
        "player_template_json_files": [str(Path(p).resolve()) for p in list(plan_obj.player_template_json_files or [])],
        "selected_signal_ids": [str(x) for x in list(plan_obj.selected_signal_ids or [])],
        "selected_basic_struct_ids": [str(x) for x in list(plan_obj.selected_basic_struct_ids or [])],
        "selected_ingame_struct_ids": [str(x) for x in list(plan_obj.selected_ingame_struct_ids or [])],
        "output_dir_name_in_out": str(plan_obj.output_dir_name_in_out),
        "output_user_dir": str(Path(plan_obj.output_user_dir).resolve()) if plan_obj.output_user_dir is not None else None,
        "node_pos_scale": float(plan_obj.node_pos_scale),
        "allow_unresolved_ui_keys": bool(plan_obj.allow_unresolved_ui_keys),
        "ui_export_record_id": str(plan_obj.ui_export_record_id) if plan_obj.ui_export_record_id is not None else None,
        "id_ref_gil_file": str(Path(plan_obj.id_ref_gil_file).resolve()) if plan_obj.id_ref_gil_file is not None else None,
        "bundle_enabled": bool(plan_obj.bundle_enabled),
        "bundle_include_signals": bool(plan_obj.bundle_include_signals),
        "bundle_include_ui_guid_registry": bool(plan_obj.bundle_include_ui_guid_registry),
        "pack_graphs_to_single_gia": bool(plan_obj.pack_graphs_to_single_gia),
        "pack_output_gia_file_name": str(plan_obj.pack_output_gia_file_name),
        "base_template_gia_file": str(Path(plan_obj.base_template_gia_file).resolve()) if plan_obj.base_template_gia_file is not None else None,
        "base_player_template_gia_file": (
            str(Path(plan_obj.base_player_template_gia_file).resolve()) if plan_obj.base_player_template_gia_file is not None else None
        ),
        "template_base_decode_max_depth": int(plan_obj.template_base_decode_max_depth),
        "player_template_base_decode_max_depth": int(plan_obj.player_template_base_decode_max_depth),
        "id_ref_override_component_name_to_id": dict(plan_obj.id_ref_override_component_name_to_id or {}),
        "id_ref_override_entity_name_to_guid": dict(plan_obj.id_ref_override_entity_name_to_guid or {}),
    }


def _build_plan_snapshot(plan_obj: object | None) -> dict[str, object] | None:
    """将导出中心 plan 归一化为 JSON 可序列化快照。"""

    if plan_obj is None:
        return None

    from ..export_center.plans import _ExportGiaPlan, _ExportGilPlan, _MergeSignalEntriesPlan, _RepairSignalsPlan

    if isinstance(plan_obj, _ExportGilPlan):
        return _build_export_gil_plan_snapshot(plan_obj)
    if isinstance(plan_obj, _RepairSignalsPlan):
        return _build_repair_signals_plan_snapshot(plan_obj)
    if isinstance(plan_obj, _MergeSignalEntriesPlan):
        return _build_merge_signal_entries_plan_snapshot(plan_obj)
    if isinstance(plan_obj, _ExportGiaPlan):
        return _build_export_gia_plan_snapshot(plan_obj)
    return {"type": type(plan_obj).__name__, "repr": str(plan_obj)}


def _build_gil_selection_manifest(plan_obj: object | None) -> dict[str, object] | None:
    """按导出中心子进程口径构造 selection-json 内容快照。"""

    if plan_obj is None:
        return None

    from ..export_center.plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        return None

    manifest: dict[str, object] = {
        "selected_struct_ids": [str(x) for x in list(plan_obj.selected_struct_ids)],
        "selected_ingame_struct_ids": [str(x) for x in list(plan_obj.selected_ingame_struct_ids)],
        "selected_signal_ids": [str(x) for x in list(plan_obj.selected_signal_ids)],
        "selected_custom_variable_refs": [dict(x) for x in list(plan_obj.selected_custom_variable_refs)],
        "selected_level_custom_variable_ids": [str(x) for x in list(plan_obj.selected_level_custom_variable_ids)],
        "selected_graph_code_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_graph_code_files)],
        "selected_template_json_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_template_json_files)],
        "selected_instance_json_files": [str(Path(p).resolve()) for p in list(plan_obj.selected_instance_json_files)],
        "graph_source_roots": [str(Path(p).resolve()) for p in list(plan_obj.graph_source_roots)],
        "write_ui": bool(plan_obj.write_ui),
        "ui_auto_sync_custom_variables": bool(plan_obj.ui_auto_sync_custom_variables),
        "ui_layout_conflict_resolutions": list(plan_obj.ui_layout_conflict_resolutions),
        "node_graph_conflict_resolutions": list(plan_obj.node_graph_conflict_resolutions),
        "template_conflict_resolutions": list(plan_obj.template_conflict_resolutions),
        "instance_conflict_resolutions": list(plan_obj.instance_conflict_resolutions),
        "prefer_signal_specific_type_id": bool(plan_obj.prefer_signal_specific_type_id),
    }
    selected_ui_layout_names = [str(Path(p).stem).strip() for p in list(plan_obj.selected_ui_html_files or [])]
    selected_ui_layout_names = [x for x in selected_ui_layout_names if x]
    if selected_ui_layout_names:
        manifest["selected_ui_layout_names"] = list(selected_ui_layout_names)
    return dict(manifest)


def _build_execute_ui_snapshot(env: ExportCenterDialogWiringEnv) -> dict[str, object]:
    """提取执行页“可选项/已选项”与关键输入控件的快照。"""

    picker = env.picker
    selected_now = list(getattr(picker, "get_selected_items")())
    all_items = list(getattr(picker, "get_all_items")())
    selected_snap = [_snapshot_resource_item(it, include_display_text=True, picker=picker) for it in selected_now]
    all_items_snap = [_snapshot_resource_item(it, include_display_text=False, picker=picker) for it in all_items]

    return {
        "workspace_root": str(Path(env.workspace_root).resolve()),
        "package_id": str(env.package_id),
        "project_root": str(Path(env.project_root).resolve()),
        "format_combo": _snapshot_combo(env.format_combo),
        "picker": {
            "selected_items_now": list(selected_snap),
            "all_items": list(all_items_snap),
        },
        "runtime": {
            "id_ref_override_component_name_to_id": dict(env.rt.id_ref_override_component_name_to_id or {}),
            "id_ref_override_entity_name_to_guid": dict(env.rt.id_ref_override_entity_name_to_guid or {}),
            "ui_auto_selected_custom_var_keys": sorted([str(x) for x in list(env.rt.ui_auto_selected_custom_var_keys or set())]),
            "asset_auto_selected_custom_var_keys": sorted([str(x) for x in list(env.rt.asset_auto_selected_custom_var_keys or set())]),
        },
        "ui": {
            "gia": {
                "out_dir": _snapshot_line_edit(env.gia.out_dir_edit),
                "copy_dir": _snapshot_line_edit(env.gia.copy_dir_edit),
                "base_gil": _snapshot_line_edit(env.gia.base_gil_edit),
                "player_template_base_gia": _snapshot_line_edit(env.gia.player_template_base_gia_edit),
                "allow_unresolved_ui_keys": _snapshot_checkbox(env.gia.allow_unresolved_ui_keys_cb),
                "ui_export_record_combo": _snapshot_combo(env.gia.ui_export_record_combo),
                "id_ref_gil": _snapshot_line_edit(env.gia.gia_id_ref_edit),
                "bundle_enabled": _snapshot_checkbox(env.gia.bundle_enabled_cb),
                "bundle_include_signals": _snapshot_checkbox(env.gia.bundle_include_signals_cb),
                "bundle_include_ui_guid_registry": _snapshot_checkbox(env.gia.bundle_include_ui_guid_cb),
                "pack_graphs": _snapshot_checkbox(env.gia.pack_graphs_cb),
                "pack_file_name": _snapshot_line_edit(env.gia.pack_name_edit),
                "base_gia": _snapshot_line_edit(env.gia.base_gia_edit),
                "decode_depth": _snapshot_spin(env.gia.decode_depth_spin),
            },
            "gil": {
                "input_gil": _snapshot_line_edit(env.gil.input_gil_edit),
                "output_gil": _snapshot_line_edit(env.gil.output_gil_edit),
                "use_builtin_empty_base": _snapshot_checkbox(env.gil.use_builtin_empty_base_cb),
                "recent_combo": _snapshot_combo(env.gil.recent_combo),
                "struct_mode_combo": _snapshot_combo(env.gil.struct_mode_combo),
                "templates_mode_combo": _snapshot_combo(env.gil.templates_mode_combo),
                "instances_mode_combo": _snapshot_combo(env.gil.instances_mode_combo),
                "signals_mode_combo": _snapshot_combo(env.gil.signals_mode_combo),
                "prefer_signal_specific_type_id": _snapshot_checkbox(env.gil.prefer_signal_specific_type_id_cb),
                "ui_mode_combo": _snapshot_combo(env.gil.ui_mode_combo),
                "gil_ui_export_record_combo": _snapshot_combo(env.gil.gil_ui_export_record_combo),
                "id_ref_gil": _snapshot_line_edit(env.gil.gil_id_ref_edit),
                "write_ui": _snapshot_checkbox(env.gil.write_ui_cb),
                "ui_auto_sync_custom_variables": _snapshot_checkbox(env.gil.ui_auto_sync_vars_cb),
                "selected_level_custom_variable_ids": [str(x) for x in list(env.gil.selected_level_custom_variable_ids or [])],
            },
            "repair": {
                "repair_input_gil": _snapshot_line_edit(env.repair.repair_input_gil_edit),
                "repair_output_gil": _snapshot_line_edit(env.repair.repair_output_gil_edit),
                "repair_prune_placeholder_orphans": _snapshot_checkbox(env.repair.repair_prune_orphans_cb),
                "merge_keep_signal_name": _snapshot_line_edit(env.repair.merge_keep_signal_edit),
                "merge_remove_signal_name": _snapshot_line_edit(env.repair.merge_remove_signal_edit),
                "merge_rename_keep_to": _snapshot_line_edit(env.repair.merge_rename_keep_to_edit),
                "merge_patch_composite_pin_index": _snapshot_checkbox(env.repair.merge_patch_cpi_cb),
            },
        },
    }


def _format_export_failure_repro_text(*, payload: dict[str, object], message: str, execute_log_text: str) -> str:
    """将失败信息与复现快照格式化为可复制文本。"""

    msg = str(message or "导出失败（请查看控制台错误）。").strip()
    log_text = str(execute_log_text or "").strip()
    json_text = json.dumps(_jsonable(payload), ensure_ascii=False, indent=_FAILURE_REPRO_JSON_INDENT)

    lines: list[str] = []
    lines.append("导出失败：")
    lines.append(msg)
    lines.append("")
    lines.append("===== 复现信息（请整段复制） =====")
    lines.append(json_text)
    lines.append("")
    lines.append("===== 执行页进度事件（UI） =====")
    lines.append(log_text if log_text != "" else "（空）")
    return "\n".join(lines).rstrip()

def format_export_failure_repro_text(*, payload: dict[str, object], message: str, execute_log_text: str) -> str:
    """格式化导出失败复现信息文本。"""

    return _format_export_failure_repro_text(payload=dict(payload), message=str(message), execute_log_text=str(execute_log_text))


__all__ = ["build_export_failure_result_text", "format_export_failure_repro_text"]

