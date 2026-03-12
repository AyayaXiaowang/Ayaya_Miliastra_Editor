from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .export_success_dialogs import append_recent_artifacts, show_success_dialog


def _build_selection_snapshot(*, selected_items: list[Any]) -> list[dict[str, str]]:
    """构造用于历史记录的 selection 快照。"""

    return [
        {
            "source_root": it.source_root,
            "category": it.category,
            "relative_path": it.relative_path,
            "absolute_path": str(it.absolute_path),
        }
        for it in list(selected_items)
    ]


def _set_busy_controls(busy: bool, *, run_btn: Any, close_btn: Any, history_btn: Any, format_combo: Any, picker: Any, stacked: Any) -> None:
    """设置导出中心的 busy 状态以避免重入。"""

    run_btn.setEnabled(not bool(busy))
    close_btn.setEnabled(not bool(busy))
    history_btn.setEnabled(not bool(busy))
    format_combo.setEnabled(not bool(busy))
    picker.setEnabled(not bool(busy))
    stacked.setEnabled(not bool(busy))


def _merge_report_with_precheck(*, report: dict, precheck_skipped_inputs: list[dict[str, str]], precheck_warnings: list[dict[str, str]]) -> dict:
    """把预检信息合并进 report2 以便写入历史与成功回调。"""

    report2 = dict(report)
    if precheck_skipped_inputs:
        report2["precheck_skipped_inputs"] = list(precheck_skipped_inputs)
    if precheck_warnings:
        report2["precheck_warnings"] = list(precheck_warnings)
    return dict(report2)


def _handle_worker_progress(
    current: int,
    total: int,
    label: str,
    *,
    get_progress_widget: Callable[..., Any],
    on_progress_changed: Callable[[int, int, str], Any] | None,
) -> None:
    """转发 worker 进度到导出中心进度条与执行页回调。"""

    get_progress_widget(visible=True).set_status(label=str(label), current=int(current), total=int(total))
    if on_progress_changed is not None:
        on_progress_changed(int(current), int(total), str(label))


def _handle_worker_succeeded(
    report: dict,
    *,
    state: dict[str, bool],
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
    selection_snapshot: list[dict[str, str]],
    get_progress_widget: Callable[..., Any],
    append_task_history_entry: Callable[..., Any],
    now_ts: Callable[[], Any],
    set_busy: Callable[[bool], None],
    on_succeeded_report: Callable[[dict], Any] | None,
) -> None:
    """处理 worker succeeded 信号并展示成功弹窗。"""

    state["succeeded"] = True
    get_progress_widget(visible=False).set_status(label="完成", current=0, total=0)
    set_busy(False)

    report2 = _merge_report_with_precheck(
        report=dict(report),
        precheck_skipped_inputs=list(precheck_skipped_inputs),
        precheck_warnings=list(precheck_warnings),
    )
    fmt2 = str(report2.get("format") or "")

    append_task_history_entry(
        workspace_root=Path(workspace_root),
        entry={
            "ts": now_ts(),
            "kind": "export_center",
            "title": f"导出中心（{package_id}，{fmt2}）",
            "package_id": str(package_id),
            "format": str(fmt2),
            "selection": list(selection_snapshot),
            "report": dict(report2),
        },
    )

    append_recent_artifacts(fmt=str(fmt2), report=dict(report), report2=dict(report2), workspace_root=Path(workspace_root), package_id=str(package_id))
    show_success_dialog(
        dialog=dialog,
        fmt=str(fmt2),
        report=dict(report),
        report2=dict(report2),
        precheck_skipped_inputs=list(precheck_skipped_inputs),
        precheck_warnings=list(precheck_warnings),
        on_succeeded_report=on_succeeded_report,
    )


def _handle_worker_failed(
    message: str,
    *,
    state: dict[str, bool],
    dialog: Any,
    get_progress_widget: Callable[..., Any],
    set_busy: Callable[[bool], None],
    on_failed_message: Callable[[str], Any] | None,
) -> None:
    """处理 worker failed 信号并展示失败弹窗。"""

    from app.ui.foundation import dialog_utils

    state["failed"] = True
    get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
    set_busy(False)
    if on_failed_message is not None:
        on_failed_message(str(message or "导出失败（子进程失败）。"))
    dialog_utils.show_warning_dialog(dialog, "导出失败", str(message or "导出失败（子进程失败）。"))


def _handle_worker_finished(
    *,
    main_window: Any,
    state: dict[str, bool],
    dialog: Any,
    get_progress_widget: Callable[..., Any],
    set_busy: Callable[[bool], None],
    on_failed_message: Callable[[str], Any] | None,
) -> None:
    """处理 worker finished 信号并在缺少 succeeded/failed 时提示用户。"""

    setattr(main_window, "_export_center_worker", None)
    _handle_worker_finished_fallback(
        state=state,
        dialog=dialog,
        get_progress_widget=get_progress_widget,
        set_busy=set_busy,
        on_failed_message=on_failed_message,
    )


def _handle_worker_finished_fallback(
    *,
    state: dict[str, bool],
    dialog: Any,
    get_progress_widget: Callable[..., Any],
    set_busy: Callable[[bool], None],
    on_failed_message: Callable[[str], Any] | None,
) -> None:
    """在缺少 succeeded/failed 时展示统一失败提示。"""

    from app.ui.foundation import dialog_utils

    if state["succeeded"] or state["failed"]:
        return
    get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
    set_busy(False)
    if on_failed_message is not None:
        on_failed_message("导出失败（请查看控制台错误）。")
    dialog_utils.show_warning_dialog(dialog, "导出失败", "导出失败（请查看控制台错误）。")


def start_export_center_worker(
    *,
    QtCore: Any,
    main_window: Any,
    dialog: Any,
    workspace_root: Path,
    package_id: str,
    fmt: str,
    plan_obj: object,
    selected_items: list[Any],
    run_btn: Any,
    close_btn: Any,
    history_btn: Any,
    format_combo: Any,
    picker: Any,
    stacked: Any,
    get_progress_widget: Callable[..., Any],
    append_task_history_entry: Callable[..., Any],
    now_ts: Callable[[], Any],
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
    on_progress_changed: Callable[[int, int, str], Any] | None = None,
    on_succeeded_report: Callable[[dict], Any] | None = None,
    on_failed_message: Callable[[str], Any] | None = None,
) -> None:
    """启动导出中心 worker 并连接 UI 回调。"""

    from ...export_center_worker import make_export_center_worker_cls

    from functools import partial

    selection_snapshot = _build_selection_snapshot(selected_items=list(selected_items))

    set_busy = partial(
        _set_busy_controls,
        run_btn=run_btn,
        close_btn=close_btn,
        history_btn=history_btn,
        format_combo=format_combo,
        picker=picker,
        stacked=stacked,
    )
    set_busy(True)

    WorkerCls = make_export_center_worker_cls(QtCore=QtCore)
    worker = WorkerCls(
        plan=plan_obj,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        fmt=str(fmt),
        parent=main_window,
    )
    setattr(main_window, "_export_center_worker", worker)

    state = {"succeeded": False, "failed": False}

    worker.progress_changed.connect(
        partial(_handle_worker_progress, get_progress_widget=get_progress_widget, on_progress_changed=on_progress_changed)
    )
    worker.succeeded.connect(
        partial(
            _handle_worker_succeeded,
            state=state,
            dialog=dialog,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            precheck_skipped_inputs=list(precheck_skipped_inputs),
            precheck_warnings=list(precheck_warnings),
            selection_snapshot=list(selection_snapshot),
            get_progress_widget=get_progress_widget,
            append_task_history_entry=append_task_history_entry,
            now_ts=now_ts,
            set_busy=set_busy,
            on_succeeded_report=on_succeeded_report,
        )
    )
    worker.failed.connect(
        partial(
            _handle_worker_failed,
            state=state,
            dialog=dialog,
            get_progress_widget=get_progress_widget,
            set_busy=set_busy,
            on_failed_message=on_failed_message,
        )
    )
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(
        partial(
            _handle_worker_finished,
            main_window=main_window,
            state=state,
            dialog=dialog,
            get_progress_widget=get_progress_widget,
            set_busy=set_busy,
            on_failed_message=on_failed_message,
        )
    )
    get_progress_widget(visible=True).set_status(label="准备导出…", current=0, total=0)
    worker.start()


__all__ = [
    "start_export_center_worker",
]

