from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Any, Callable

from .base_gil_conflicts import BaseGilConflictsScanCache
from .gil_node_graph_conflicts import resolve_gil_node_graph_conflicts
from .gil_template_instance_conflicts import resolve_gil_instance_conflicts, resolve_gil_template_conflicts
from .gil_ui_layout_conflicts import resolve_gil_ui_layout_conflicts
from .export_worker import start_export_center_worker
from ..state import _save_last_export_format
from .export_plan_utils import (
    call_save_now_or_raise,
    ensure_no_running_export_task_or_warn,
    inject_id_ref_overrides,
    persist_last_paths,
    validate_plan_by_format,
)
from .export_prechecks import (
    ensure_gia_plan_has_anything_or_warn,
    ensure_gil_plan_has_anything_or_warn,
    precheck_clean_gia_templates_index,
)


def _set_preflight_busy_controls(
    busy: bool,
    *,
    run_btn: Any,
    close_btn: Any,
    history_btn: Any,
    format_combo: Any,
    picker: Any,
    stacked: Any,
) -> None:
    """在冲突扫描阶段设置导出中心 busy 以避免重入。"""

    run_btn.setEnabled(not bool(busy))
    close_btn.setEnabled(not bool(busy))
    history_btn.setEnabled(not bool(busy))
    format_combo.setEnabled(not bool(busy))
    picker.setEnabled(not bool(busy))
    stacked.setEnabled(not bool(busy))


def _run_gil_conflict_preflight(
    *,
    QtCore: Any,
    dialog: Any,
    main_window: Any,
    workspace_root: Path,
    plan_obj: object,
    base_scan_cache: BaseGilConflictsScanCache,
    set_busy_for_preflight: Callable[[bool], None],
    on_progress_changed: Callable[[int, int, str], Any] | None,
    get_progress_widget: Callable[..., Any],
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
) -> object | None:
    """执行 GIL 写回的冲突检查弹窗并返回更新后的 plan。"""

    plan_obj2 = resolve_gil_ui_layout_conflicts(
        QtCore=QtCore,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        plan_obj=plan_obj,
        base_scan_cache=base_scan_cache,
        set_busy_for_preflight=set_busy_for_preflight,
        on_progress_changed=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_warnings=precheck_warnings,
    )
    if plan_obj2 is None:
        return None

    plan_obj3 = resolve_gil_template_conflicts(
        QtCore=QtCore,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        plan_obj=plan_obj2,
        base_scan_cache=base_scan_cache,
        set_busy_for_preflight=set_busy_for_preflight,
        on_progress_changed=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_skipped_inputs=precheck_skipped_inputs,
        precheck_warnings=precheck_warnings,
    )
    if plan_obj3 is None:
        return None

    plan_obj4 = resolve_gil_instance_conflicts(
        QtCore=QtCore,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        plan_obj=plan_obj3,
        base_scan_cache=base_scan_cache,
        set_busy_for_preflight=set_busy_for_preflight,
        on_progress_changed=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_skipped_inputs=precheck_skipped_inputs,
        precheck_warnings=precheck_warnings,
    )
    if plan_obj4 is None:
        return None

    return resolve_gil_node_graph_conflicts(
        QtCore=QtCore,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        plan_obj=plan_obj4,
        base_scan_cache=base_scan_cache,
        set_busy_for_preflight=set_busy_for_preflight,
        on_progress_changed=on_progress_changed,
        get_progress_widget=get_progress_widget,
        precheck_skipped_inputs=precheck_skipped_inputs,
        precheck_warnings=precheck_warnings,
    )


def _start_export_center_worker_with_context(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    fmt: str,
    plan_obj: object,
    selected_items: list[Any],
    ui_handles: tuple[Any, Any, Any, Any, Any, Any],
    runtime: tuple[Callable[..., Any], Callable[..., Any], Callable[[], Any]],
    precheck: tuple[list[dict[str, str]], list[dict[str, str]]],
    callbacks: tuple[
        Callable[[int, int, str], Any] | None,
        Callable[[dict], Any] | None,
        Callable[[str], Any] | None,
    ],
) -> None:
    """以统一参数形态启动导出中心 worker。"""

    run_btn, close_btn, history_btn, format_combo, picker, stacked = ui_handles
    get_progress_widget, append_task_history_entry, now_ts = runtime
    precheck_skipped_inputs, precheck_warnings = precheck
    on_progress_changed, on_succeeded_report, on_failed_message = callbacks

    start_export_center_worker(
        QtCore=QtCore,
        main_window=main_window,
        dialog=dialog,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        fmt=str(fmt),
        plan_obj=plan_obj,
        selected_items=list(selected_items),
        run_btn=run_btn,
        close_btn=close_btn,
        history_btn=history_btn,
        format_combo=format_combo,
        picker=picker,
        stacked=stacked,
        get_progress_widget=get_progress_widget,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
        precheck_skipped_inputs=list(precheck_skipped_inputs),
        precheck_warnings=list(precheck_warnings),
        on_progress_changed=on_progress_changed,
        on_succeeded_report=on_succeeded_report,
        on_failed_message=on_failed_message,
    )

def _start_export_center_action_impl(
    *,
    fmt: str,
    QtCore: Any, main_window: Any, dialog: Any,
    workspace_root: Path, package_id: str, project_root: Path,
    gia: Any, gil: Any, repair: Any,
    rt: Any,
    ui_handles: tuple[Any, Any, Any, Any, Any, Any],
    runtime: tuple[Any, Any, Any],
    callbacks: tuple[Any, Any, Any],
) -> None:
    """运行导出中心导出动作主流程。"""

    run_btn, close_btn, history_btn, format_combo, picker, stacked = ui_handles
    get_progress_widget, append_task_history_entry, now_ts = runtime
    on_progress_changed, on_succeeded_report, on_failed_message = callbacks

    if not ensure_no_running_export_task_or_warn(main_window=main_window):
        return

    call_save_now_or_raise(main_window=main_window)

    validate_kwargs = {
        "main_window": main_window,
        "workspace_root": Path(workspace_root),
        "package_id": str(package_id),
        "project_root": Path(project_root),
        "picker": picker,
        "gia": gia,
        "gil": gil,
        "repair": repair,
    }

    plan_obj = validate_plan_by_format(fmt=str(fmt), **validate_kwargs)
    if plan_obj is None:
        return

    _save_last_export_format(workspace_root=Path(workspace_root), export_format=str(fmt))
    selected_items = list(picker.get_selected_items())

    precheck_skipped_inputs: list[dict[str, str]] = []
    precheck_warnings: list[dict[str, str]] = []

    plan_obj = precheck_clean_gia_templates_index(plan_obj=plan_obj, precheck_skipped_inputs=precheck_skipped_inputs)
    persist_last_paths(workspace_root=Path(workspace_root), plan_obj=plan_obj, gia=gia)

    busy_kwargs = {
        "run_btn": run_btn,
        "close_btn": close_btn,
        "history_btn": history_btn,
        "format_combo": format_combo,
        "picker": picker,
        "stacked": stacked,
    }
    set_busy_for_preflight = partial(_set_preflight_busy_controls, **busy_kwargs)
    base_scan_cache = BaseGilConflictsScanCache()

    preflight_kwargs = {
        "QtCore": QtCore,
        "dialog": dialog,
        "main_window": main_window,
        "workspace_root": Path(workspace_root),
        "base_scan_cache": base_scan_cache,
        "set_busy_for_preflight": set_busy_for_preflight,
        "on_progress_changed": on_progress_changed,
        "get_progress_widget": get_progress_widget,
        "precheck_skipped_inputs": precheck_skipped_inputs,
        "precheck_warnings": precheck_warnings,
    }
    plan_obj = _run_gil_conflict_preflight(plan_obj=plan_obj, **preflight_kwargs)
    if plan_obj is None:
        return

    ok = ensure_gia_plan_has_anything_or_warn(
        main_window=main_window,
        plan_obj=plan_obj,
        precheck_skipped_inputs=precheck_skipped_inputs,
    ) and ensure_gil_plan_has_anything_or_warn(
        main_window=main_window,
        plan_obj=plan_obj,
        precheck_skipped_inputs=precheck_skipped_inputs,
    )
    if not bool(ok):
        return

    plan_obj = inject_id_ref_overrides(plan_obj=plan_obj, rt=rt)
    rt.last_execute_fmt = str(fmt)
    rt.last_execute_plan_obj = plan_obj
    rt.last_execute_precheck_skipped_inputs = list(precheck_skipped_inputs)
    rt.last_execute_precheck_warnings = list(precheck_warnings)
    rt.last_execute_selection_snapshot = [
        {
            "key": str(getattr(it, "key", "") or ""),
            "source_root": str(getattr(it, "source_root", "") or ""),
            "category": str(getattr(it, "category", "") or ""),
            "relative_path": str(getattr(it, "relative_path", "") or ""),
            "absolute_path": str(getattr(it, "absolute_path", "") or ""),
        }
        for it in list(selected_items)
    ]
    _start_export_center_worker_with_context(
        QtCore=QtCore,
        main_window=main_window,
        dialog=dialog,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        fmt=str(fmt),
        plan_obj=plan_obj,
        selected_items=list(selected_items),
        ui_handles=(run_btn, close_btn, history_btn, format_combo, picker, stacked),
        runtime=(get_progress_widget, append_task_history_entry, now_ts),
        precheck=(precheck_skipped_inputs, precheck_warnings),
        callbacks=(on_progress_changed, on_succeeded_report, on_failed_message),
    )


def start_export_center_action(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    picker: Any,
    gia: Any,
    gil: Any,
    repair: Any,
    format_combo: Any,
    rt: Any,
    stacked: Any,
    run_btn: Any,
    close_btn: Any,
    history_btn: Any,
    get_progress_widget: Callable[..., Any],
    append_task_history_entry: Callable[..., Any],
    now_ts: Callable[[], Any],
    on_progress_changed: Callable[[int, int, str], Any] | None = None,
    on_succeeded_report: Callable[[dict], Any] | None = None,
    on_failed_message: Callable[[str], Any] | None = None,
) -> None:
    """导出中心：点击“开始导出/开始修复”的动作入口（UI 层编排）。"""

    fmt = str(format_combo.currentData() or "gia")
    _start_export_center_action_impl(
        fmt=str(fmt),
        QtCore=QtCore,
        main_window=main_window,
        dialog=dialog,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        project_root=Path(project_root),
        gia=gia,
        gil=gil,
        repair=repair,
        rt=rt,
        ui_handles=(run_btn, close_btn, history_btn, format_combo, picker, stacked),
        runtime=(get_progress_widget, append_task_history_entry, now_ts),
        callbacks=(on_progress_changed, on_succeeded_report, on_failed_message),
    )


__all__ = [
    "start_export_center_action",
]

