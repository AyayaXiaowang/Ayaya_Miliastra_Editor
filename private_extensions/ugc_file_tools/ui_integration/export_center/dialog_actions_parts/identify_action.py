from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .constants import UI_HTML_FILE_SUFFIXES
from ..write_ui_policy import compute_write_ui_effective_policy
from ...export_center_gil_identify_worker import make_export_center_gil_identify_worker_cls
from ...graph_selection import build_graph_selection_from_resource_items


def _ensure_has_selected_graphs_or_warn(*, dialog: Any, fmt: str, graph_code_files: list[Path]) -> bool:
    """确保识别前已勾选至少 1 个节点图且模式支持识别。"""

    from app.ui.foundation import dialog_utils

    if not graph_code_files:
        dialog_utils.show_warning_dialog(dialog, "提示", "请先在左侧勾选至少 1 个节点图，再执行识别。")
        return False
    if str(fmt) not in {"gia", "gil"}:
        dialog_utils.show_warning_dialog(dialog, "提示", "当前模式不支持识别。")
        return False
    return True


def _resolve_identify_text_inputs(
    *,
    fmt: str,
    workspace_root: Path,
    package_id: str,
    gia: Any,
    gil: Any,
) -> tuple[str, str, str | None]:
    """解析识别所需的 base/id_ref 文本输入与 UI 回填记录 ID。"""

    base_gil_text = ""
    id_ref_gil_text = ""
    ui_export_record_id: str | None = None

    if str(fmt) == "gia":
        base_gil_text = str(gia.base_gil_edit.text() or "").strip()
        id_ref_gil_text = str(gia.gia_id_ref_edit.text() or "").strip()
        if not gia.ui_export_record_row.isHidden():
            rid0 = str(gia.ui_export_record_combo.currentData() or "").strip()
            ui_export_record_id = str(rid0) if rid0 != "" else None

        if base_gil_text == "" and ui_export_record_id is not None:
            from ugc_file_tools.ui.export_records import try_get_ui_export_record_by_id

            rec0 = try_get_ui_export_record_by_id(
                workspace_root=Path(workspace_root),
                package_id=str(package_id),
                record_id=str(ui_export_record_id),
            )
            if rec0 is not None:
                base2 = str(rec0.payload.get("output_gil_file") or "").strip()
                if base2 != "":
                    base_gil_text = str(base2)

        if base_gil_text == "" and id_ref_gil_text != "":
            base_gil_text = str(id_ref_gil_text)
    else:
        use_builtin_empty_base = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
        if use_builtin_empty_base:
            from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

            base_gil_text = str(get_builtin_empty_base_gil_path())
        else:
            base_gil_text = str(gil.input_gil_edit.text() or "").strip()
        id_ref_gil_text = str(gil.gil_id_ref_edit.text() or "").strip()
        if not gil.gil_ui_export_record_row.isHidden():
            rid1 = str(gil.gil_ui_export_record_combo.currentData() or "").strip()
            ui_export_record_id = str(rid1) if rid1 != "" else None

    return str(base_gil_text), str(id_ref_gil_text), (str(ui_export_record_id) if ui_export_record_id is not None else None)


def _validate_gil_paths_or_warn(
    *,
    dialog: Any,
    base_gil_text: str,
    id_ref_gil_text: str,
) -> tuple[Path, Path | None] | None:
    """校验 base/id_ref `.gil` 路径并在失败时弹窗返回 None。"""

    from app.ui.foundation import dialog_utils

    if str(base_gil_text).strip() == "":
        dialog_utils.show_warning_dialog(dialog, "提示", "请先选择一个用于识别的基础 .gil（或选择 UI 回填记录）。")
        return None

    base_gil_path = Path(str(base_gil_text)).resolve()
    if (not base_gil_path.is_file()) or base_gil_path.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(dialog, "提示", f"基础 .gil 文件不存在或格式不正确：{str(base_gil_path)}")
        return None

    id_ref_gil_path: Path | None = None
    if str(id_ref_gil_text).strip() != "":
        p0 = Path(str(id_ref_gil_text)).resolve()
        if (not p0.is_file()) or p0.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(dialog, "提示", f"占位符参考 .gil 文件不存在或格式不正确：{str(p0)}")
            return None
        id_ref_gil_path = Path(p0)

    return Path(base_gil_path), (Path(id_ref_gil_path) if id_ref_gil_path is not None else None)


def _ensure_no_running_identify_worker_or_warn(*, dialog: Any, main_window: Any) -> bool:
    """确保当前没有识别任务在运行。"""

    from app.ui.foundation import dialog_utils

    existing_worker = getattr(main_window, "_export_center_gil_identify_worker", None)
    is_running = getattr(existing_worker, "isRunning", None)
    if callable(is_running) and bool(is_running()):
        dialog_utils.show_warning_dialog(dialog, "提示", "已有一个识别任务正在运行，请等待完成后再开始新的识别。")
        return False
    return True


def _collect_required_level_custom_variables(*, fmt: str, gil: Any) -> list[dict[str, str]]:
    """收集识别所需的“关卡实体自定义变量（全部）”诊断输入。"""

    if str(fmt) != "gil":
        return []

    required_level_custom_vars: list[dict[str, str]] = []
    for vid in list(getattr(gil, "selected_level_custom_variable_ids", []) or []):
        meta = getattr(gil, "level_custom_variable_meta_by_id", {}).get(str(vid))
        if isinstance(meta, dict):
            required_level_custom_vars.append(
                {
                    "variable_id": str(meta.get("variable_id") or vid),
                    "variable_name": str(meta.get("variable_name") or ""),
                    "variable_type": str(meta.get("variable_type") or ""),
                    "source": str(meta.get("source") or ""),
                }
            )
        else:
            required_level_custom_vars.append({"variable_id": str(vid), "variable_name": "", "variable_type": "", "source": ""})
    return list(required_level_custom_vars)


def _compute_ui_placeholder_scan_params(
    *,
    fmt: str,
    project_root: Path,
    selected_items: list[Any],
    gil: Any,
    rt: Any,
) -> tuple[bool, Path | None, list[str]]:
    """计算 UI 占位符变量扫描参数（仅 GIL 模式且启用 UI 写回+自动同步）。"""

    if str(fmt) != "gil":
        return False, None, []

    ui_src_selected = any(it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items)
    policy = compute_write_ui_effective_policy(fmt="gil", ui_src_selected=bool(ui_src_selected), user_choice=bool(rt.write_ui_user_choice))
    scan_ui_placeholder_vars = bool(bool(policy.effective_write_ui) and bool(gil.ui_auto_sync_vars_cb.isChecked()))
    ui_dir = (Path(project_root) / "管理配置" / "UI源码").resolve()
    ui_source_dir = ui_dir if (bool(policy.effective_write_ui) and ui_dir.is_dir()) else None

    ui_selected_html_stems: list[str] = []
    for it in list(selected_items):
        if str(getattr(it, "category", "")) != "ui_src":
            continue
        p = Path(getattr(it, "absolute_path", "")).resolve()
        if p.is_file() and p.suffix.lower() in set(UI_HTML_FILE_SUFFIXES):
            ui_selected_html_stems.append(str(p.stem))
    return bool(scan_ui_placeholder_vars), ui_source_dir, list(ui_selected_html_stems)


def _merge_pending_rows(*, pending_rows: list[dict[str, object]], new_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """将识别结果 rows 与 pending_rows（双击缺失行手动选择）按 (category,key) 合并。"""

    def _row_key(d: object) -> tuple[str, str]:
        """提取行的 (category,key) 作为合并键。"""
        if not isinstance(d, dict):
            return "", ""
        return str(d.get("category") or ""), str(d.get("key") or "")

    merged_by_key: dict[tuple[str, str], dict[str, object]] = {}
    ordered: list[tuple[str, str]] = []
    for r0 in list(pending_rows):
        k0 = _row_key(r0)
        if k0 == ("", ""):
            continue
        merged_by_key[k0] = dict(r0)
        ordered.append(k0)
    for r1 in list(new_rows):
        k1 = _row_key(r1)
        if k1 == ("", ""):
            continue
        if k1 in merged_by_key:
            merged_by_key[k1].update(dict(r1))
        else:
            merged_by_key[k1] = dict(r1)
            ordered.append(k1)
    return [merged_by_key[k] for k in ordered if k in merged_by_key]


def _start_identify_worker(
    *,
    QtCore: Any,
    main_window: Any,
    panel: Any,
    rt: Any,
    worker: Any,
    dialog: Any,
    set_backfill_table_rows: Callable[..., Any],
    update_backfill_panels: Callable[..., Any],
) -> None:
    """启动识别 worker 并连接 UI 回调。"""

    from app.ui.foundation import dialog_utils

    setattr(main_window, "_export_center_gil_identify_worker", worker)

    state = {"succeeded": False, "failed": False}
    panel.identify_btn.setEnabled(False)
    panel.progress_label.setText("识别中…")
    panel.progress_row.setVisible(True)
    panel.progress_bar.setRange(0, 0)
    panel.progress_bar.setValue(0)

    progress_state = {"last_total": 0}

    def _on_progress(current: int, total: int, label: str) -> None:
        """处理识别进度回调并更新进度条。"""
        c = int(current)
        t = int(total)
        progress_state["last_total"] = int(t)
        if t <= 0:
            panel.progress_bar.setRange(0, 0)
        else:
            panel.progress_bar.setRange(0, t + 1)
            panel.progress_bar.setValue(min(max(c, 0), t))

    def _on_identify_succeeded(report: dict) -> None:
        """处理识别成功回调并合并表格行与隐藏进度区域。"""
        state["succeeded"] = True
        setattr(rt, "backfill_last_identify_report", dict(report))
        last_total = int(progress_state.get("last_total") or 0)
        if last_total > 0:
            panel.progress_bar.setRange(0, last_total + 1)
            panel.progress_bar.setValue(last_total + 1)
        else:
            panel.progress_bar.setRange(0, 1)
            panel.progress_bar.setValue(1)

        rows_list = list(report.get("rows") or []) if isinstance(report.get("rows"), list) else []
        pending_list = list(getattr(rt, "backfill_pending_rows", None) or []) if isinstance(getattr(rt, "backfill_pending_rows", None), list) else []
        merged_rows = _merge_pending_rows(pending_rows=pending_list, new_rows=rows_list)
        set_backfill_table_rows(panel, rows=merged_rows)
        update_backfill_panels()
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)

    def _on_identify_failed(message: str) -> None:
        """处理识别失败回调并重置进度区域与提示用户。"""
        state["failed"] = True
        panel.progress_bar.setRange(0, 1)
        panel.progress_bar.setValue(0)
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)
        dialog_utils.show_warning_dialog(dialog, "识别失败", str(message or "识别失败。"))
        update_backfill_panels()

    def _on_identify_finished() -> None:
        """处理识别 finished 回调并在异常结束时做统一 UI 收尾。"""
        setattr(main_window, "_export_center_gil_identify_worker", None)
        if state["succeeded"] or state["failed"]:
            return
        panel.progress_bar.setRange(0, 1)
        panel.progress_bar.setValue(0)
        panel.progress_label.setText("")
        panel.progress_row.setVisible(False)
        update_backfill_panels()

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_identify_succeeded)
    worker.failed.connect(_on_identify_failed)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_identify_finished)
    worker.start()


def start_export_center_backfill_identify_action(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: Any,
    format_combo: Any,
    gia: Any,
    gil: Any,
    panel: Any,
    rt: Any,
    set_backfill_table_rows: Callable[..., Any],
    update_backfill_panels: Callable[..., Any],
) -> None:
    """导出中心：点击“识别”的动作入口（UI 层编排）。"""

    fmt = str(format_combo.currentData() or "gia")
    selected_items = list(picker.get_selected_items())
    graph_sel0 = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )
    graph_files = [Path(p).resolve() for p in list(getattr(graph_sel0, "graph_code_files", []) or [])]
    if not _ensure_has_selected_graphs_or_warn(dialog=dialog, fmt=str(fmt), graph_code_files=list(graph_files)):
        return

    base_text, id_ref_text, ui_export_record_id = _resolve_identify_text_inputs(
        fmt=str(fmt),
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        gia=gia,
        gil=gil,
    )
    setattr(rt, "backfill_last_identify_report", None)

    validated = _validate_gil_paths_or_warn(dialog=dialog, base_gil_text=str(base_text), id_ref_gil_text=str(id_ref_text))
    if validated is None:
        return
    base_gil_path, id_ref_gil_path = validated

    if not _ensure_no_running_identify_worker_or_warn(dialog=dialog, main_window=main_window):
        return

    required_level_custom_vars = _collect_required_level_custom_variables(fmt=str(fmt), gil=gil)
    scan_ui_placeholder_vars, ui_source_dir, ui_selected_html_stems = _compute_ui_placeholder_scan_params(
        fmt=str(fmt),
        project_root=Path(project_root),
        selected_items=list(selected_items),
        gil=gil,
        rt=rt,
    )

    WorkerCls = make_export_center_gil_identify_worker_cls(QtCore=QtCore)
    worker = WorkerCls(
        base_gil_file_path=Path(base_gil_path),
        id_ref_gil_file_path=(Path(id_ref_gil_path) if id_ref_gil_path is not None else None),
        use_base_as_id_ref_fallback=bool(str(fmt) in {"gia", "gil"}),
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
        required_entity_names=frozenset(rt.id_ref_usage_for_selected_graphs.entity_names),
        required_component_names=frozenset(rt.id_ref_usage_for_selected_graphs.component_names),
        required_ui_keys=frozenset(rt.ui_keys_for_selected_graphs),
        ui_key_layout_hints_by_key=dict(rt.ui_key_layout_hints_by_key),
        required_level_custom_variables=list(required_level_custom_vars),
        scan_ui_placeholder_variables=bool(scan_ui_placeholder_vars),
        ui_source_dir=ui_source_dir,
        ui_selected_html_stems=list(ui_selected_html_stems),
        parent=main_window,
    )

    _start_identify_worker(
        QtCore=QtCore,
        main_window=main_window,
        panel=panel,
        rt=rt,
        worker=worker,
        dialog=dialog,
        set_backfill_table_rows=set_backfill_table_rows,
        update_backfill_panels=update_backfill_panels,
    )


__all__ = [
    "start_export_center_backfill_identify_action",
]

