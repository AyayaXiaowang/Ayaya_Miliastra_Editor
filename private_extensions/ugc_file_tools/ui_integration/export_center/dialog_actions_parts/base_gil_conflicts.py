from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

@dataclass(slots=True)
class BaseGilConflictsScanCache:
    """base `.gil` 冲突扫描结果的惰性缓存。"""

    report: dict[str, object] | None = None
    scan_ok: bool = True


def compute_base_gil_conflicts_scan_needs_from_plan(plan_obj: object) -> tuple[bool, bool, bool, bool]:
    """从导出计划推导 base `.gil` 冲突扫描需要的扫描项集合。"""

    from ..plans import _ExportGilPlan

    if not isinstance(plan_obj, _ExportGilPlan):
        return False, False, False, False

    need_ui_layouts = bool(plan_obj.write_ui)
    need_node_graphs = bool(plan_obj.selected_graph_code_files)
    need_templates = bool(plan_obj.selected_template_json_files)
    need_instances = bool(plan_obj.selected_instance_json_files)
    return bool(need_ui_layouts), bool(need_node_graphs), bool(need_templates), bool(need_instances)


def _build_scan_failure_warning_message(*, exit_code: int, stderr_tail: Sequence[str]) -> tuple[str, str]:
    """构造“base gil 冲突扫描失败”的弹窗/日志文本。"""

    from ..base_gil_conflicts_scan import BASE_GIL_CONFLICT_SCAN_STDERR_TAIL_DIALOG_MAX_LINES

    tail = [str(x) for x in list(stderr_tail)[-int(BASE_GIL_CONFLICT_SCAN_STDERR_TAIL_DIALOG_MAX_LINES) :] if str(x).strip() != ""]
    tail_text = "\n".join(tail) if tail else "(stderr 为空)"
    warn_title = "扫描基础 .gil 冲突信息失败（已自动继续）"
    warn_message = "\n".join(
        [
            f"子进程退出码={int(exit_code)}",
            "",
            "为避免 UI 进程解析 base .gil 导致闪退，本次冲突检查改为在子进程中扫描。",
            "但该样本/环境下子进程扫描失败，因此无法自动判断“哪些资源同名已存在”。",
            "",
            "已自动继续导出：导出中心将对“已勾选”的布局/节点图/模板/实体弹出 overwrite/add/skip 选择，",
            "其中“基础GIL ID”列可能为空；建议优先选择 add/skip 以避免误覆盖。",
            "",
            "---- 子进程 stderr 末尾 ----",
            tail_text,
        ]
    ).strip()
    return str(warn_title), str(warn_message)


def ensure_base_gil_conflicts_report(
    *,
    cache: BaseGilConflictsScanCache,
    QtCore: Any,
    main_window: Any,
    workspace_root: Path,
    input_gil_path: Path,
    need_ui_layouts: bool,
    need_node_graphs: bool,
    need_templates: bool,
    need_instances: bool,
    set_busy: Callable[[bool], None],
    on_progress: Callable[[int, int, str], None] | None,
    get_progress_widget: Callable[..., Any],
    precheck_warnings: list[dict[str, str]],
) -> tuple[dict[str, object], bool]:
    """确保 base `.gil` 冲突扫描报告可用（必要时触发子进程扫描并缓存）。"""

    if cache.report is not None:
        return dict(cache.report), bool(cache.scan_ok)

    if not any([bool(need_ui_layouts), bool(need_node_graphs), bool(need_templates), bool(need_instances)]):
        cache.report = {}
        cache.scan_ok = True
        return {}, True

    from uuid import uuid4

    from ..._cli_subprocess import build_run_ugc_file_tools_command
    from ..base_gil_conflicts_scan import BASE_GIL_CONFLICT_SCAN_DECODE_MAX_DEPTH, run_base_gil_conflicts_scan_blocking

    out_dir = (Path(workspace_root).resolve() / "private_extensions" / "ugc_file_tools" / "out").resolve()
    tmp_dir = (out_dir / "_tmp_cli").resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    report_file = (tmp_dir / f"export_center_base_gil_conflicts_{uuid4().hex[:10]}.json").resolve()

    argv_scan: list[str] = [
        "tool",
        "export_center_scan_base_gil_conflicts",
        str(Path(input_gil_path).resolve()),
        "--report",
        str(report_file),
        "--decode-max-depth",
        str(int(BASE_GIL_CONFLICT_SCAN_DECODE_MAX_DEPTH)),
    ]
    if bool(need_ui_layouts):
        argv_scan.append("--scan-ui-layouts")
    if bool(need_node_graphs):
        argv_scan.append("--scan-node-graphs")
    if bool(need_templates):
        argv_scan.append("--scan-templates")
    if bool(need_instances):
        argv_scan.append("--scan-instances")

    command = build_run_ugc_file_tools_command(workspace_root=Path(workspace_root), argv=argv_scan)
    print(
        "[export_center][info] base_gil_conflicts_scan: "
        f"python={command[0]!s} "
        f"base_gil={str(Path(input_gil_path).resolve())} "
        f"report={str(Path(report_file).resolve())} "
        f"scan_ui_layouts={bool(need_ui_layouts)} "
        f"scan_node_graphs={bool(need_node_graphs)} "
        f"scan_templates={bool(need_templates)} "
        f"scan_instances={bool(need_instances)}",
        flush=True,
    )

    def _handle_progress(current: int, total: int, label: str) -> None:
        """将扫描进度转发到导出中心统一进度条。"""

        text = f"资源冲突检查：扫描基础 .gil：{str(label)}" if str(label or "").strip() else "资源冲突检查：扫描基础 .gil"
        get_progress_widget(visible=True).set_status(label=str(text), current=int(current), total=int(total))
        if on_progress is not None:
            on_progress(int(current), int(total), str(text))

    scan_result = run_base_gil_conflicts_scan_blocking(
        QtCore=QtCore,
        main_window=main_window,
        command=command,
        cwd=Path(workspace_root),
        report_file=Path(report_file),
        set_busy=set_busy,
        on_progress=_handle_progress,
    )
    if int(scan_result.exit_code) != 0:
        warn_title, warn_message = _build_scan_failure_warning_message(exit_code=int(scan_result.exit_code), stderr_tail=list(scan_result.stderr_tail))
        precheck_warnings.append({"category": "base_gil_conflicts_scan", "title": str(warn_title), "message": str(warn_message)})
        print(f"[export_center][warning] {warn_title}\n{warn_message}", flush=True)
        get_progress_widget(visible=False).set_status(label="继续（扫描失败）", current=0, total=0)
        cache.report = {}
        cache.scan_ok = False
        return {}, False

    if scan_result.report is None:
        raise RuntimeError("base gil conflicts scan succeeded but report is None")

    cache.report = dict(scan_result.report)
    cache.scan_ok = True
    return dict(cache.report), True


__all__ = [
    "BaseGilConflictsScanCache",
    "compute_base_gil_conflicts_scan_needs_from_plan",
    "ensure_base_gil_conflicts_report",
]

