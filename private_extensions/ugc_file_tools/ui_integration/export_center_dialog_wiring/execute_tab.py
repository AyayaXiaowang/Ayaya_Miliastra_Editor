from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .._common import ToolbarProgressWidgetSpec, make_toolbar_progress_widget_cls
from ..export_center.dialog_actions import start_export_center_action

from .env import ExportCenterDialogWiringEnv
from .failure_repro import build_export_failure_result_text

_MAX_PRECHECK_SKIPPED_INPUTS_SHOWN = 10
_TOOLBAR_PROGRESS_WIDTH = 220


def build_get_progress_widget(env: ExportCenterDialogWiringEnv) -> Callable[[bool], Any]:
    """构造用于显示/隐藏工具栏进度条的回调函数。"""

    ProgressWidgetCls = make_toolbar_progress_widget_cls(
        ToolbarProgressWidgetSpec(kind="export_center", initial_label="准备导出…", progress_width=_TOOLBAR_PROGRESS_WIDTH),
        QtCore=env.QtCore,
        QtWidgets=env.QtWidgets,
        Colors=env.Colors,
        Sizes=env.Sizes,
    )

    package_library_widget = getattr(env.main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法显示导出进度")
    ensure_widget = getattr(package_library_widget, "ensure_extension_toolbar_widget", None)
    if not callable(ensure_widget):
        raise RuntimeError("PackageLibraryWidget 缺少 ensure_extension_toolbar_widget，无法显示导出进度")

    def _get_progress_widget(visible: bool) -> Any:
        """获取并确保工具栏进度条 widget 存在且类型匹配。"""

        widget_obj = ensure_widget(
            "ugc_file_tools.export_center_progress",
            create_widget=lambda parent: ProgressWidgetCls(parent),
            visible=bool(visible),
        )
        if not isinstance(widget_obj, ProgressWidgetCls):
            raise TypeError(f"export center progress widget 类型不匹配（got: {type(widget_obj).__name__}）")
        return widget_obj

    return _get_progress_widget


def append_execute_log_line(env: ExportCenterDialogWiringEnv, text: str) -> None:
    """向执行页日志追加一行非空文本。"""

    t = str(text or "").strip()
    if t == "":
        return
    env.execute.log_text.appendPlainText(t)


def set_execute_progress(env: ExportCenterDialogWiringEnv, current: int, total: int, label: str) -> None:
    """更新执行页进度条与进度文案并同步写入日志。"""

    c = int(current)
    t = int(total)
    line = f"[{c}/{t}] {label}" if t > 0 else str(label)
    if t <= 0:
        env.execute.progress_bar.setRange(0, 0)
    else:
        env.execute.progress_bar.setRange(0, t + 1)
        env.execute.progress_bar.setValue(min(max(c, 0), t))
    env.execute.progress_label.setText(str(line))
    append_execute_log_line(env, str(line))


def _extract_precheck_skipped_inputs(report: dict) -> list[dict[str, object]]:
    """从 report 中提取预检阶段跳过的输入文件列表。"""

    raw = report.get("precheck_skipped_inputs") if isinstance(report, dict) else None
    if isinstance(raw, list) and raw:
        return [x for x in raw if isinstance(x, dict)]
    return []


def _append_precheck_skipped_inputs(lines: list[str], skipped_inputs: list[dict[str, object]]) -> None:
    """将预检跳过输入的摘要追加到结果文本中。"""

    if not skipped_inputs:
        return
    lines.append("")
    lines.append(f"注意：预检阶段自动跳过 {len(skipped_inputs)} 个输入文件：")
    for item in skipped_inputs[:_MAX_PRECHECK_SKIPPED_INPUTS_SHOWN]:
        fp = str(item.get("file") or "").strip()
        reason = str(item.get("reason") or "").strip()
        name = Path(fp).name if fp else "(unknown)"
        lines.append(f"- {name}：{reason}" if reason else f"- {name}")
    if len(skipped_inputs) > _MAX_PRECHECK_SKIPPED_INPUTS_SHOWN:
        lines.append(f"... 还有 {len(skipped_inputs) - _MAX_PRECHECK_SKIPPED_INPUTS_SHOWN} 个未展示")


def _format_result_text_for_gil(report: dict, skipped_inputs: list[dict[str, object]]) -> str:
    """格式化 .gil 导出完成后的结果文本。"""

    rep = report.get("report") if isinstance(report, dict) else None
    output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
    output_user = str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""
    lines = [
        "导出完成（.gil）：",
        f"- out 产物：{output_tool}",
        f"- 导出路径：{output_user}",
    ]
    _append_precheck_skipped_inputs(lines, skipped_inputs)
    return "\n".join(lines).strip()


def _format_result_text_for_repair_signals(report: dict, skipped_inputs: list[dict[str, object]]) -> str:
    """格式化“修复信号”完成后的结果文本。"""

    rep = report.get("report") if isinstance(report, dict) else None
    output_user = str(rep.get("output_gil") or "") if isinstance(rep, dict) else ""
    removed_entries = int(rep.get("removed_signal_entries") or 0) if isinstance(rep, dict) else 0
    id_remap_size = int(rep.get("id_remap_size") or 0) if isinstance(rep, dict) else 0
    node_changes = int(rep.get("node_instance_id_changes") or 0) if isinstance(rep, dict) else 0
    lines = [
        "修复完成（修复信号）：",
        f"- 输出路径：{output_user}",
        f"- 合并/移除信号条目：{removed_entries}",
        f"- 引用重绑映射条数：{id_remap_size}",
        f"- 节点引用更新次数：{node_changes}",
    ]
    _append_precheck_skipped_inputs(lines, skipped_inputs)
    return "\n".join(lines).strip()


def _format_result_text_for_merge_signal_entries(report: dict, skipped_inputs: list[dict[str, object]]) -> str:
    """格式化“合并信号条目”完成后的结果文本。"""

    rep = report.get("report") if isinstance(report, dict) else None
    output_user = str(rep.get("output_gil") or "") if isinstance(rep, dict) else ""
    removed_entries = int(rep.get("removed_signal_entries") or 0) if isinstance(rep, dict) else 0
    node_changes = int(rep.get("node_instance_id_changes") or 0) if isinstance(rep, dict) else 0
    pin_patches = int(rep.get("node_pin_patches") or 0) if isinstance(rep, dict) else 0
    lines = [
        "修复完成（合并信号条目）：",
        f"- 输出路径：{output_user}",
        f"- 移除信号条目：{removed_entries}",
        f"- 节点引用更新次数：{node_changes}",
        f"- pin 端口索引修补次数：{pin_patches}",
    ]
    _append_precheck_skipped_inputs(lines, skipped_inputs)
    return "\n".join(lines).strip()


def _format_result_text_for_gia(report: dict, skipped_inputs: list[dict[str, object]]) -> str:
    """格式化 .gia 导出完成后的结果文本。"""

    graphs_rep = report.get("graphs") if isinstance(report, dict) else None
    tpl_rep = report.get("templates") if isinstance(report, dict) else None
    tpl_bundle_rep = report.get("templates_instances_bundle") if isinstance(report, dict) else None
    tpl_missing_source = report.get("templates_missing_source_info") if isinstance(report, dict) else None
    player_tpl_rep = report.get("player_templates") if isinstance(report, dict) else None
    structs_rep = report.get("basic_structs") if isinstance(report, dict) else None
    signals_rep = report.get("signals") if isinstance(report, dict) else None

    lines: list[str] = ["导出完成（.gia）："]
    if isinstance(graphs_rep, dict):
        exported = graphs_rep.get("exported_graphs")
        lines.append(f"- 节点图：{len(exported) if isinstance(exported, list) else 0} 个（out={graphs_rep.get('output_dir','')}）")

    bundle_rep: dict | None = None
    if isinstance(tpl_bundle_rep, dict) and isinstance(tpl_bundle_rep.get("exported"), list):
        bundle_rep = dict(tpl_bundle_rep)
    elif isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported"), list) and not isinstance(tpl_rep.get("exported_templates"), list):
        bundle_rep = dict(tpl_rep)

    bundle_count = 0
    bundle_out = ""
    if isinstance(bundle_rep, dict):
        exported = bundle_rep.get("exported")
        bundle_count = len(exported) if isinstance(exported, list) else 0
        bundle_out = str(bundle_rep.get("templates_instances_dir") or bundle_rep.get("output_dir") or "").strip()

    empty_count = 0
    empty_out = ""
    if isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported_templates"), list):
        exported = tpl_rep.get("exported_templates")
        empty_count = len(exported) if isinstance(exported, list) else 0
        empty_out = str(tpl_rep.get("templates_dir") or tpl_rep.get("output_dir") or "").strip()

    if int(bundle_count) > 0 and int(empty_count) > 0:
        lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}） + {int(empty_count)} 个（模板导出，out={empty_out}）")
    elif int(bundle_count) > 0:
        lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}）")
    elif int(empty_count) > 0:
        lines.append(f"- 元件：{int(empty_count)} 个（模板导出，out={empty_out}）")

    if isinstance(tpl_missing_source, list) and tpl_missing_source:
        missing_with_decorations = 0
        for item in list(tpl_missing_source):
            if not isinstance(item, dict):
                continue
            if bool(item.get("has_decorations")):
                missing_with_decorations += 1
        if int(missing_with_decorations) > 0:
            lines.append(
                f"注意：{int(missing_with_decorations)} 个元件模板包含装饰物，但本次仅导出模板（自定义变量），装饰物实例未随 .gia 导出。"
            )

    if isinstance(structs_rep, dict):
        lines.append(f"- 基础结构体：{int(structs_rep.get('structs_total') or 0)} 个（out={structs_rep.get('output_gia_file','')}）")
    if isinstance(signals_rep, dict):
        lines.append(f"- 信号：{int(signals_rep.get('signals_total') or 0)} 个（out={signals_rep.get('output_gia_file','')}）")
    if isinstance(player_tpl_rep, dict):
        exported = player_tpl_rep.get("exported_player_templates")
        pt_count = len(exported) if isinstance(exported, list) else int(player_tpl_rep.get("player_templates_total") or 0)
        pt_out = str(player_tpl_rep.get("player_templates_dir") or player_tpl_rep.get("output_dir") or "").strip()
        lines.append(f"- 玩家模板：{int(pt_count)} 个（out={pt_out}）")

    _append_precheck_skipped_inputs(lines, skipped_inputs)
    return "\n".join(lines).strip()


def format_export_result_text(report: dict) -> str:
    """根据 report 内容生成执行页的结果摘要文本。"""

    fmt = str(report.get("format") or "")
    skipped_inputs = _extract_precheck_skipped_inputs(report)
    if fmt == "gil":
        return _format_result_text_for_gil(report, skipped_inputs)
    if fmt == "repair_signals":
        return _format_result_text_for_repair_signals(report, skipped_inputs)
    if fmt == "merge_signal_entries":
        return _format_result_text_for_merge_signal_entries(report, skipped_inputs)
    return _format_result_text_for_gia(report, skipped_inputs)


def handle_export_succeeded_report(
    env: ExportCenterDialogWiringEnv,
    report: dict,
    *,
    sync_step_nav: Callable[[], None],
) -> None:
    """处理导出成功并在 UI 上展示结果摘要。"""

    env.execute.progress_bar.setRange(0, 1)
    env.execute.progress_bar.setValue(1)
    env.execute.progress_label.setText("完成")
    env.execute.result_text.setPlainText(format_export_result_text(dict(report)))
    sync_step_nav()


def handle_export_failed_message(
    env: ExportCenterDialogWiringEnv,
    message: str,
    *,
    sync_step_nav: Callable[[], None],
) -> None:
    """处理导出失败并在 UI 上展示失败原因。"""

    env.execute.progress_bar.setRange(0, 1)
    env.execute.progress_bar.setValue(0)
    env.execute.progress_label.setText("失败")
    env.execute.result_text.setPlainText(build_export_failure_result_text(env, str(message)))
    sync_step_nav()


def on_run_clicked(
    env: ExportCenterDialogWiringEnv,
    trigger_btn: object,
    *,
    get_progress_widget: Callable[[bool], Any],
    sync_step_nav: Callable[[], None],
) -> None:
    """进入执行页并启动导出/修复 action。"""

    env.tabs.setCurrentIndex(2)
    sync_step_nav()
    env.execute.progress_label.setText("准备导出…")
    env.execute.progress_bar.setRange(0, 0)
    env.execute.log_text.setPlainText("")
    env.execute.result_text.setPlainText("")
    start_export_center_action(
        QtCore=env.QtCore,
        main_window=env.main_window,
        dialog=env.dialog,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
        project_root=Path(env.project_root),
        picker=env.picker,
        gia=env.gia,
        gil=env.gil,
        repair=env.repair,
        format_combo=env.format_combo,
        rt=env.rt,
        stacked=env.stacked,
        run_btn=trigger_btn,
        close_btn=env.close_btn,
        history_btn=env.history_btn,
        get_progress_widget=lambda *, visible: get_progress_widget(bool(visible)),
        append_task_history_entry=env.append_task_history_entry,
        now_ts=env.now_ts,
        on_progress_changed=lambda c, t, label: set_execute_progress(env, c, t, label),
        on_succeeded_report=lambda rep: handle_export_succeeded_report(env, dict(rep), sync_step_nav=sync_step_nav),
        on_failed_message=lambda msg: handle_export_failed_message(env, str(msg), sync_step_nav=sync_step_nav),
    )


def wire_execute_tab(
    env: ExportCenterDialogWiringEnv,
    *,
    get_progress_widget: Callable[[bool], Any],
    sync_step_nav: Callable[[], None],
) -> Callable[[object], None]:
    """连接执行页按钮并返回可复用的“开始执行”回调。"""

    env.execute.clear_log_btn.clicked.connect(lambda: env.execute.log_text.setPlainText(""))
    env.execute.clear_result_btn.clicked.connect(lambda: env.execute.result_text.setPlainText(""))
    env.execute.copy_result_btn.clicked.connect(
        lambda: env.QtWidgets.QApplication.clipboard().setText(str(env.execute.result_text.toPlainText() or ""))
    )

    def _run(trigger_btn: object) -> None:
        """以指定按钮作为触发入口启动执行。"""

        on_run_clicked(env, trigger_btn, get_progress_widget=get_progress_widget, sync_step_nav=sync_step_nav)

    env.run_btn.clicked.connect(lambda: _run(env.run_btn))
    return _run
