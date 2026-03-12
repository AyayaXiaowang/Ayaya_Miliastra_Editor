from __future__ import annotations

from pathlib import Path
from typing import Callable

from .._common import IdRefPlaceholderUsage
from ..export_center_dialog_plan_validators import _scan_id_ref_usage_for_graphs

from .env import ExportCenterDialogWiringEnv


def update_ui_export_record_detail_text(env: ExportCenterDialogWiringEnv) -> None:
    """刷新“UI 回填记录”详情展示文本。"""

    rid = str(env.gia.ui_export_record_combo.currentData() or "").strip()
    if rid == "":
        env.gia.ui_export_record_detail.setText("自动使用当前 UI GUID registry")
        return
    rec = env.rt.ui_export_records_by_id.get(rid)
    if rec is None:
        env.gia.ui_export_record_detail.setText("未找到记录详情")
        return
    from ..ui_export_record_picker import format_ui_export_record_detail_text

    env.gia.ui_export_record_detail.setText(format_ui_export_record_detail_text(rec))


def _reset_ui_export_record_usage_state(env: ExportCenterDialogWiringEnv) -> None:
    """清空当前选择对应的占位符扫描结果缓存。"""

    env.rt.id_ref_usage_for_selected_graphs = IdRefPlaceholderUsage(entity_names=frozenset(), component_names=frozenset())
    env.rt.ui_keys_for_selected_graphs = frozenset()
    env.rt.ui_key_layout_hints_by_key = {}


def _hide_ui_export_record_related_rows(env: ExportCenterDialogWiringEnv) -> None:
    """隐藏 UI 回填记录与占位符参考相关的配置行。"""

    env.gia.ui_export_record_row.setVisible(False)
    env.gil.gil_ui_export_record_row.setVisible(False)
    env.gia.base_gil_row.setVisible(False)
    env.gia.gia_id_ref_row.setVisible(False)
    env.gil.gil_id_ref_row.setVisible(False)


def _show_id_ref_rows(env: ExportCenterDialogWiringEnv) -> None:
    """显示占位符回填相关的配置行。"""

    env.gia.base_gil_row.setVisible(True)
    env.gia.gia_id_ref_row.setVisible(True)
    env.gil.gil_id_ref_row.setVisible(True)


def update_ui_export_record_ui(
    env: ExportCenterDialogWiringEnv,
    *,
    update_analysis_tab: Callable[[], None],
) -> None:
    """根据当前资源选择刷新“UI 回填记录”相关 UI 与占位符扫描结果。"""

    from ..export_center.backfill_inspector import scan_ui_key_placeholders_in_graph_code_files
    from ..graph_selection import build_graph_selection_from_resource_items
    from ..ui_export_record_picker import (
        graph_code_files_need_ui_export_record,
        load_ui_export_record_options,
    )

    selected_items = list(env.picker.get_selected_items())
    fmt = str(env.format_combo.currentData() or "gia")
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
    )

    if fmt in {"repair_signals", "merge_signal_entries"}:
        _reset_ui_export_record_usage_state(env)
        _hide_ui_export_record_related_rows(env)
        update_analysis_tab()
        return

    if not graph_sel.graph_code_files:
        _reset_ui_export_record_usage_state(env)
        _hide_ui_export_record_related_rows(env)
        update_analysis_tab()
        return

    _show_id_ref_rows(env)
    id_ref_usage = _scan_id_ref_usage_for_graphs(graph_code_files=list(graph_sel.graph_code_files))
    env.rt.id_ref_usage_for_selected_graphs = id_ref_usage
    env.gia.base_gil_edit.setPlaceholderText(
        "建议：选择基底 .gil（用于 entity_key/component_key 回填）"
        if bool(id_ref_usage.is_used)
        else "可选：选择基底 .gil（用于 entity_key/component_key 回填）"
    )
    env.gia.gia_id_ref_edit.setPlaceholderText(
        "可选：占位符参考 .gil（覆盖基底；留空=使用基底 .gil；缺失同名=回填为 0）"
        if bool(id_ref_usage.is_used)
        else "可选：占位符参考 .gil（覆盖基底；留空=使用基底 .gil）"
    )

    ui_usage = scan_ui_key_placeholders_in_graph_code_files(graph_code_files=list(graph_sel.graph_code_files))
    env.rt.ui_keys_for_selected_graphs = frozenset(ui_usage.ui_keys)
    env.rt.ui_key_layout_hints_by_key = dict(ui_usage.layout_hints_by_ui_key)

    need = graph_code_files_need_ui_export_record(graph_code_files=list(graph_sel.graph_code_files))
    if not bool(need):
        env.gia.ui_export_record_row.setVisible(False)
        env.gil.gil_ui_export_record_row.setVisible(False)
        update_analysis_tab()
        return

    options = load_ui_export_record_options(workspace_root=Path(env.workspace_root), package_id=str(env.package_id))

    env.rt.ui_export_records_by_id.clear()
    env.gia.ui_export_record_combo.blockSignals(True)
    env.gia.ui_export_record_combo.clear()
    env.gia.ui_export_record_combo.addItem("自动（使用最新 UI 导出记录）", "")
    for opt in list(options):
        rid = str(opt.get("record_id") or "").strip()
        label = str(opt.get("label") or "").strip()
        rec = opt.get("record")
        if rid == "" or label == "" or rec is None:
            continue
        env.gia.ui_export_record_combo.addItem(label, rid)
        env.rt.ui_export_records_by_id[rid] = rec
    if env.gia.ui_export_record_combo.count() > 1:
        env.gia.ui_export_record_combo.setCurrentIndex(1)
    env.gia.ui_export_record_combo.blockSignals(False)

    update_ui_export_record_detail_text(env)
    env.gia.ui_export_record_row.setVisible(True)

    prev_gil_rid = str(env.gil.gil_ui_export_record_combo.currentData() or "").strip()
    env.gil.gil_ui_export_record_combo.blockSignals(True)
    env.gil.gil_ui_export_record_combo.clear()
    env.gil.gil_ui_export_record_combo.addItem("（不指定）", "")
    for opt in list(options):
        rid = str(opt.get("record_id") or "").strip()
        label = str(opt.get("label") or "").strip()
        if rid == "" or label == "":
            continue
        env.gil.gil_ui_export_record_combo.addItem(label, rid)
    if prev_gil_rid != "":
        prev_idx = int(env.gil.gil_ui_export_record_combo.findData(prev_gil_rid))
        env.gil.gil_ui_export_record_combo.setCurrentIndex(prev_idx if prev_idx >= 0 else 0)
    else:
        env.gil.gil_ui_export_record_combo.setCurrentIndex(0)
    env.gil.gil_ui_export_record_combo.blockSignals(False)
    env.gil.gil_ui_export_record_row.setVisible(True)

    update_analysis_tab()

