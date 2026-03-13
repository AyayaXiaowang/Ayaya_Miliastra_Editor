from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .constants import PRECHECK_PREVIEW_MAX_ITEMS


def _format_precheck_skipped_inputs(*, precheck_skipped_inputs: list[dict[str, str]]) -> list[str]:
    """将预检跳过清单格式化为对话框文本行。"""

    if not precheck_skipped_inputs:
        return []
    lines: list[str] = []
    lines.append("")
    lines.append(f"注意：预检阶段自动跳过 {len(precheck_skipped_inputs)} 个输入文件：")
    for item in precheck_skipped_inputs[: int(PRECHECK_PREVIEW_MAX_ITEMS)]:
        fp = str(item.get("file") or "").strip()
        reason = str(item.get("reason") or "").strip()
        name = Path(fp).name if fp else "(unknown)"
        lines.append(f"- {name}：{reason}" if reason else f"- {name}")
    if len(precheck_skipped_inputs) > int(PRECHECK_PREVIEW_MAX_ITEMS):
        lines.append(f"... 还有 {len(precheck_skipped_inputs) - int(PRECHECK_PREVIEW_MAX_ITEMS)} 个未展示")
    return list(lines)


def _format_precheck_warnings(*, precheck_warnings: list[dict[str, str]]) -> list[str]:
    """将预检告警清单格式化为对话框文本行。"""

    if not precheck_warnings:
        return []
    lines: list[str] = []
    lines.append("")
    lines.append(f"注意：预检阶段产生 {len(precheck_warnings)} 条告警（见导出中心历史/报告）：")
    for item in precheck_warnings[: int(PRECHECK_PREVIEW_MAX_ITEMS)]:
        title0 = str(item.get("title") or "").strip() or "(warning)"
        lines.append(f"- {title0}")
    if len(precheck_warnings) > int(PRECHECK_PREVIEW_MAX_ITEMS):
        lines.append(f"... 还有 {len(precheck_warnings) - int(PRECHECK_PREVIEW_MAX_ITEMS)} 个未展示")
    return list(lines)


def _extract_gil_report_outputs(*, report: dict) -> tuple[str, str]:
    """从 GIL report 中抽取 out 产物与导出路径。"""

    rep = report.get("report") if isinstance(report, dict) else None
    output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
    output_user = str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""
    return str(output_tool), str(output_user)


def _extract_gil_skipped_graphs_and_instances(*, report: dict) -> tuple[list[dict[str, object]], list[str], bool]:
    """从 GIL report 中抽取 skipped_graphs 与 instances_missing。"""

    rep = report.get("report") if isinstance(report, dict) else None
    skipped_graphs: list[dict[str, object]] = []
    instances_missing: list[str] = []
    instances_filtered_by_selection = False
    if isinstance(rep, dict):
        steps = rep.get("steps")
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if str(step.get("kind") or "") == "instances":
                    inst_rep = step.get("report")
                    if isinstance(inst_rep, dict):
                        instances_filtered_by_selection = bool(inst_rep.get("filtered_by_selection") or False)
                        raw_missing = inst_rep.get("instances_missing_in_target")
                        if isinstance(raw_missing, list) and raw_missing:
                            instances_missing = [str(x).strip() for x in raw_missing if str(x).strip() != ""]
                    continue
                if str(step.get("kind") or "") != "node_graphs":
                    continue
                node_graphs_rep = step.get("report")
                raw_skipped = node_graphs_rep.get("skipped_graphs") if isinstance(node_graphs_rep, dict) else None
                if isinstance(raw_skipped, list) and raw_skipped:
                    skipped_graphs = [x for x in raw_skipped if isinstance(x, dict)]
                continue
    return list(skipped_graphs), list(instances_missing), bool(instances_filtered_by_selection)


def _format_skipped_graphs(*, skipped_graphs: list[dict[str, object]]) -> list[str]:
    """将 skipped_graphs 格式化为对话框文本行。"""

    if not skipped_graphs:
        return []
    lines: list[str] = []
    lines.append("")
    lines.append(f"注意：节点图写回跳过 {len(skipped_graphs)} 个：")
    for item in skipped_graphs[: int(PRECHECK_PREVIEW_MAX_ITEMS)]:
        code_file = str(item.get("graph_code_file") or "").strip()
        display_name = (
            Path(code_file).name if code_file else (str(item.get("graph_name") or item.get("graph_key") or "").strip() or "(unknown)")
        )
        reason = str(item.get("reason") or "").strip()
        err_text = str(item.get("error") or "").strip()
        detail = reason
        if err_text:
            non_empty = [ln.strip() for ln in err_text.splitlines() if ln.strip() != ""]
            bullet = next((ln for ln in non_empty if ln.startswith("- ")), (non_empty[0] if non_empty else ""))
            if bullet:
                detail = bullet
        lines.append(f"- {display_name}：{detail}" if detail else f"- {display_name}")
    if len(skipped_graphs) > int(PRECHECK_PREVIEW_MAX_ITEMS):
        lines.append(f"... 还有 {len(skipped_graphs) - int(PRECHECK_PREVIEW_MAX_ITEMS)} 个未展示")
    return list(lines)


def _format_instances_missing(*, instances_missing: list[str], instances_filtered_by_selection: bool) -> list[str]:
    """将 instances_missing_in_target 格式化为对话框文本行。"""

    if not bool(instances_filtered_by_selection) or not instances_missing:
        return []
    lines: list[str] = []
    lines.append("")
    lines.append(f"提示：本次勾选的实体中，有 {len(instances_missing)} 个在 base 存档里不存在，已按“新增实例”写入输出：")
    for iid in instances_missing[: int(PRECHECK_PREVIEW_MAX_ITEMS)]:
        lines.append(f"- {iid}")
    if len(instances_missing) > int(PRECHECK_PREVIEW_MAX_ITEMS):
        lines.append(f"... 还有 {len(instances_missing) - int(PRECHECK_PREVIEW_MAX_ITEMS)} 个未展示")
    return list(lines)


def _show_gil_success_dialog(
    *,
    dialog: Any,
    report: dict,
    report2: dict,
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
    on_succeeded_report: Callable[[dict], Any] | None,
) -> None:
    """展示 GIL 导出完成弹窗并触发回调。"""

    from app.ui.foundation import dialog_utils

    output_tool, output_user = _extract_gil_report_outputs(report=report2)
    skipped_graphs, instances_missing, instances_filtered_by_selection = _extract_gil_skipped_graphs_and_instances(report=report)

    gil_lines: list[str] = [
        "已生成 .gil：",
        f"- out 产物：{output_tool}",
        f"- 导出路径：{output_user}",
    ]
    gil_lines.extend(_format_precheck_skipped_inputs(precheck_skipped_inputs=precheck_skipped_inputs))
    gil_lines.extend(_format_precheck_warnings(precheck_warnings=precheck_warnings))
    gil_lines.extend(_format_skipped_graphs(skipped_graphs=skipped_graphs))
    gil_lines.extend(
        _format_instances_missing(instances_missing=instances_missing, instances_filtered_by_selection=bool(instances_filtered_by_selection))
    )

    dialog_utils.show_info_dialog(dialog, "导出完成", "\n".join(gil_lines))
    if on_succeeded_report is not None:
        on_succeeded_report(dict(report2))


def _show_repair_signals_success_dialog(*, dialog: Any, report: dict, on_succeeded_report: Callable[[dict], Any] | None) -> None:
    """展示 repair_signals 完成弹窗并触发回调。"""

    from app.ui.foundation import dialog_utils

    rep3 = report.get("report") if isinstance(report, dict) else None
    output_user3 = str(rep3.get("output_gil") or "") if isinstance(rep3, dict) else ""
    removed_entries = int(rep3.get("removed_signal_entries") or 0) if isinstance(rep3, dict) else 0
    id_remap_size = int(rep3.get("id_remap_size") or 0) if isinstance(rep3, dict) else 0
    node_changes = int(rep3.get("node_instance_id_changes") or 0) if isinstance(rep3, dict) else 0
    dialog_utils.show_info_dialog(
        dialog,
        "修复完成",
        "\n".join(
            [
                "已生成修复版 .gil：",
                f"- 输出路径：{output_user3}",
                f"- 合并/移除信号条目：{removed_entries}",
                f"- 引用重绑映射条数：{id_remap_size}",
                f"- 节点引用更新次数：{node_changes}",
            ]
        ),
    )
    if on_succeeded_report is not None:
        on_succeeded_report(dict(report))


def _show_merge_signal_entries_success_dialog(*, dialog: Any, report: dict, on_succeeded_report: Callable[[dict], Any] | None) -> None:
    """展示 merge_signal_entries 完成弹窗并触发回调。"""

    from app.ui.foundation import dialog_utils

    repm2 = report.get("report") if isinstance(report, dict) else None
    output_user_m2 = str(repm2.get("output_gil") or "") if isinstance(repm2, dict) else ""
    removed_entries_m2 = int(repm2.get("removed_signal_entries") or 0) if isinstance(repm2, dict) else 0
    node_changes_m2 = int(repm2.get("node_instance_id_changes") or 0) if isinstance(repm2, dict) else 0
    pin_patches_m2 = int(repm2.get("node_pin_patches") or 0) if isinstance(repm2, dict) else 0
    dialog_utils.show_info_dialog(
        dialog,
        "修复完成",
        "\n".join(
            [
                "已生成修复版 .gil：",
                f"- 输出路径：{output_user_m2}",
                f"- 移除信号条目：{removed_entries_m2}",
                f"- 节点引用更新次数：{node_changes_m2}",
                f"- pin 端口索引修补次数：{pin_patches_m2}",
            ]
        ),
    )
    if on_succeeded_report is not None:
        on_succeeded_report(dict(report))


def _show_gia_success_dialog(
    *,
    dialog: Any,
    report: dict,
    report2: dict,
    precheck_skipped_inputs: list[dict[str, str]],
    on_succeeded_report: Callable[[dict], Any] | None,
) -> None:
    """展示 GIA 导出完成弹窗并触发回调。"""

    from app.ui.foundation import dialog_utils

    graphs_rep = report.get("graphs") if isinstance(report, dict) else None
    tpl_rep = report.get("templates") if isinstance(report, dict) else None
    tpl_bundle_rep = report.get("templates_instances_bundle") if isinstance(report, dict) else None
    tpl_missing_source = report.get("templates_missing_source_info") if isinstance(report, dict) else None
    player_tpl_rep = report.get("player_templates") if isinstance(report, dict) else None
    structs_rep = report.get("basic_structs") if isinstance(report, dict) else None
    signals_rep = report.get("signals") if isinstance(report, dict) else None

    gia_lines: list[str] = ["已导出 .gia："]
    if precheck_skipped_inputs:
        gia_lines.append(f"注意：预检阶段自动跳过 {len(precheck_skipped_inputs)} 个输入文件（见导出中心历史/执行页结果）。")
    if isinstance(graphs_rep, dict):
        exported = graphs_rep.get("exported_graphs")
        gia_lines.append(f"- 节点图：{len(exported) if isinstance(exported, list) else 0} 个（out={graphs_rep.get('output_dir','')}）")

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
        gia_lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}） + {int(empty_count)} 个（模板导出，out={empty_out}）")
    elif int(bundle_count) > 0:
        gia_lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}）")
    elif int(empty_count) > 0:
        gia_lines.append(f"- 元件：{int(empty_count)} 个（模板导出，out={empty_out}）")

    if isinstance(player_tpl_rep, dict):
        exported = player_tpl_rep.get("exported_player_templates")
        pt_count = len(exported) if isinstance(exported, list) else int(player_tpl_rep.get("player_templates_total") or 0)
        pt_out = str(player_tpl_rep.get("player_templates_dir") or player_tpl_rep.get("output_dir") or "").strip()
        gia_lines.append(f"- 玩家模板：{int(pt_count)} 个（out={pt_out}）")

    if isinstance(tpl_missing_source, list) and tpl_missing_source:
        missing_with_decorations = 0
        for item in list(tpl_missing_source):
            if not isinstance(item, dict):
                continue
            if bool(item.get("has_decorations")):
                missing_with_decorations += 1
        if int(missing_with_decorations) > 0:
            gia_lines.append(f"注意：{int(missing_with_decorations)} 个元件模板包含装饰物，但本次仅导出模板（自定义变量），装饰物实例未随 .gia 导出。")

    if isinstance(structs_rep, dict):
        gia_lines.append(f"- 基础结构体：{int(structs_rep.get('structs_total') or 0)} 个（out={structs_rep.get('output_gia_file','')}）")
    if isinstance(signals_rep, dict):
        gia_lines.append(f"- 信号：{int(signals_rep.get('signals_total') or 0)} 个（out={signals_rep.get('output_gia_file','')}）")

    dialog_utils.show_info_dialog(dialog, "导出完成", "\n".join(gia_lines))
    if on_succeeded_report is not None:
        on_succeeded_report(dict(report2))


def append_recent_artifacts(
    *,
    fmt: str,
    report: dict,
    report2: dict,
    workspace_root: Path,
    package_id: str,
) -> None:
    """按导出格式将产物路径追加到 recent artifacts。"""

    if str(fmt) == "gil":
        rep = report2.get("report") if isinstance(report2, dict) else None
        output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
        output_user = str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""
        from ugc_file_tools.recent_artifacts import append_recent_exported_gil

        append_recent_exported_gil(
            workspace_root=Path(workspace_root),
            gil_path=str(output_user or output_tool),
            source="export_center",
            title=f"export_center:{package_id}",
        )
        return

    if str(fmt) == "repair_signals":
        rep2 = report.get("report") if isinstance(report, dict) else None
        output_user2 = str(rep2.get("output_gil") or "") if isinstance(rep2, dict) else ""
        if output_user2:
            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=Path(workspace_root),
                gil_path=str(output_user2),
                source="export_center",
                title=f"export_center:{package_id}:repair_signals",
            )
        return

    if str(fmt) == "merge_signal_entries":
        repm = report.get("report") if isinstance(report, dict) else None
        output_user_m = str(repm.get("output_gil") or "") if isinstance(repm, dict) else ""
        if output_user_m:
            from ugc_file_tools.recent_artifacts import append_recent_exported_gil

            append_recent_exported_gil(
                workspace_root=Path(workspace_root),
                gil_path=str(output_user_m),
                source="export_center",
                title=f"export_center:{package_id}:merge_signal_entries",
            )


def show_success_dialog(
    *,
    dialog: Any,
    fmt: str,
    report: dict,
    report2: dict,
    precheck_skipped_inputs: list[dict[str, str]],
    precheck_warnings: list[dict[str, str]],
    on_succeeded_report: Callable[[dict], Any] | None,
) -> None:
    """按 fmt 展示导出成功弹窗并触发回调。"""

    if str(fmt) == "gil":
        _show_gil_success_dialog(
            dialog=dialog,
            report=dict(report),
            report2=dict(report2),
            precheck_skipped_inputs=list(precheck_skipped_inputs),
            precheck_warnings=list(precheck_warnings),
            on_succeeded_report=on_succeeded_report,
        )
        return

    if str(fmt) == "repair_signals":
        _show_repair_signals_success_dialog(dialog=dialog, report=dict(report), on_succeeded_report=on_succeeded_report)
        return

    if str(fmt) == "merge_signal_entries":
        _show_merge_signal_entries_success_dialog(dialog=dialog, report=dict(report), on_succeeded_report=on_succeeded_report)
        return

    _show_gia_success_dialog(
        dialog=dialog,
        report=dict(report),
        report2=dict(report2),
        precheck_skipped_inputs=list(precheck_skipped_inputs),
        on_succeeded_report=on_succeeded_report,
    )


__all__ = [
    "append_recent_artifacts",
    "show_success_dialog",
]

