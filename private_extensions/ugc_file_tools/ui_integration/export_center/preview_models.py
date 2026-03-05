from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportCenterPreviewTexts:
    preview_text: str
    summary_text: str
    summary_tooltip: str


def build_gia_preview_texts(
    *,
    package_id: str,
    graphs_count: int,
    templates_count: int,
    mgmt_cfg_count: int,
    signal_ids_total: int,
    basic_struct_ids_total: int,
    ingame_struct_ids_total: int,
    out_dir_name: str,
    copy_dir: str,
    base_gil_row_visible: bool,
    base_gil_text: str,
    id_ref_row_visible: bool,
    id_ref_text: str,
    id_ref_is_used: bool,
    player_templates_count: int = 0,
    player_template_base_gia_row_visible: bool = False,
    player_template_base_gia_text: str = "",
) -> ExportCenterPreviewTexts:
    out_dir = str(out_dir_name or "").strip() or f"{package_id}_export"
    copy_dir2 = str(copy_dir or "").strip()

    lines = [
        f"项目存档：{package_id}",
        (
            "资源选择："
            f"节点图={int(graphs_count)} 元件={int(templates_count)} 玩家模板={int(player_templates_count)} 管理配置文件={int(mgmt_cfg_count)}"
        ),
        f"解析：信号={int(signal_ids_total)} 基础结构体={int(basic_struct_ids_total)} 局内存档结构体={int(ingame_struct_ids_total)}",
        f"输出：ugc_file_tools/out/{out_dir}/",
        f"复制到：{copy_dir2 if copy_dir2 else '<不复制>'}",
    ]
    if bool(player_template_base_gia_row_visible):
        base_pt = str(player_template_base_gia_text or "").strip()
        lines.append(f"玩家模板 base .gia：{base_pt if base_pt else '<未选择>'}")
    base = str(base_gil_text or "").strip()
    ref = str(id_ref_text or "").strip()
    if bool(base_gil_row_visible):
        lines.append(f"基底 .gil：{base if base else '<未选择>'}")
    if bool(id_ref_row_visible):
        if ref:
            lines.append(f"占位符参考：{ref}")
        else:
            lines.append(
                "占位符参考：<留空=使用基底 .gil>"
                if base
                else ("占位符参考：<未选择；占位符将回填为 0>" if bool(id_ref_is_used) else "占位符参考：<未选择>")
            )
    if int(ingame_struct_ids_total) > 0:
        lines.append("提示：局内存档结构体当前不支持导出为 .gia（仅用于 .gil 写回）。")

    preview_text = "\n".join(lines)

    placeholder_warn = ""
    if bool(id_ref_is_used) and base == "" and ref == "":
        placeholder_warn = "（检测到占位符：未选参考将回填为 0）"
    summary_text = (
        f"导出 .gia：节点图={int(graphs_count)} 元件={int(templates_count)} 玩家模板={int(player_templates_count)} 管理配置={int(mgmt_cfg_count)}  {placeholder_warn}"
    ).strip()

    return ExportCenterPreviewTexts(
        preview_text=str(preview_text),
        summary_text=str(summary_text),
        summary_tooltip=str(preview_text),
    )


def build_gil_preview_texts(
    *,
    package_id: str,
    templates_count: int,
    instances_count: int,
    graphs_total: int,
    level_custom_variables_total: int,
    signal_ids_total: int,
    basic_struct_ids_total: int,
    ingame_struct_ids_total: int,
    input_gil_text: str,
    output_gil_text: str,
    forced_ui: bool,
    write_ui_effective: bool,
    ui_auto_sync_enabled: bool,
    prefer_signal_specific_type_id: bool,
    id_ref_row_visible: bool,
    id_ref_text: str,
    ui_export_record_row_visible: bool,
    ui_export_record_id: str,
) -> ExportCenterPreviewTexts:
    input_text = str(input_gil_text or "").strip()
    output_text = str(output_gil_text or "").strip() or f"{package_id}.gil"

    ui_text = "是（因 UI源码 强制开启）" if bool(forced_ui) else ("是" if bool(write_ui_effective) else "否")
    auto_sync_text = str(bool(ui_auto_sync_enabled)) if bool(write_ui_effective) else "（UI未写回）"

    lines2 = [
        f"项目存档：{package_id}",
        f"基础 .gil：{input_text if input_text else '<未选择>'}",
        f"输出路径：{output_text}",
        (
            f"写回：元件={int(templates_count)} 实体摆放={int(instances_count)} 节点图={int(graphs_total)} "
            f"信号={int(signal_ids_total)} 基础结构体={int(basic_struct_ids_total)} 局内存档结构体={int(ingame_struct_ids_total)} "
            f"UI={ui_text} 自定义变量同步={auto_sync_text}"
        ),
        (
            "关卡实体自定义变量（全部）："
            + (f"{int(level_custom_variables_total)} 个" if int(level_custom_variables_total) > 0 else "<未选择>")
        ),
        "信号节点 type_id：静态绑定且 base 映射可用时自动使用 signal-specific runtime_id（0x6000xxxx/0x6080xxxx）；否则保持通用 runtime（300000/300001/300002）",
    ]
    if bool(id_ref_row_visible):
        ref = str(id_ref_text or "").strip()
        lines2.append(f"占位符参考：{ref if ref else '<留空=使用基础 .gil>'}")
    if bool(ui_export_record_row_visible):
        rid = str(ui_export_record_id or "").strip()
        lines2.append(f"UI 回填记录：{rid if rid else '<不指定>'}")

    preview_text2 = "\n".join(lines2)

    structs_total = int(basic_struct_ids_total) + int(ingame_struct_ids_total)
    summary_text = (
        f"写回 .gil：元件={int(templates_count)} 实体={int(instances_count)} 节点图={int(graphs_total)} "
        f"信号={int(signal_ids_total)} 结构体={int(structs_total)} UI={ui_text}"
        + (
            f" 关卡实体变量={int(level_custom_variables_total)}"
            if int(level_custom_variables_total) > 0
            else ""
        )
    )

    return ExportCenterPreviewTexts(
        preview_text=str(preview_text2),
        summary_text=str(summary_text),
        summary_tooltip=str(preview_text2),
    )


def build_repair_signals_preview_texts(
    *,
    package_id: str,
    graphs_total: int,
    input_gil_text: str,
    output_gil_text: str,
    prune_placeholder_orphans: bool,
) -> ExportCenterPreviewTexts:
    input_text3 = str(input_gil_text or "").strip()
    output_text3 = str(output_gil_text or "").strip()
    prune_text = "是" if bool(prune_placeholder_orphans) else "否"

    lines3 = [
        f"项目存档：{package_id}",
        f"节点图：{int(graphs_total)} 个（用于提取信号名称并生成修复依据 .gia）",
        f"目标 .gil：{input_text3 if input_text3 else '<未选择>'}",
        f"输出 .gil：{output_text3 if output_text3 else '<未填写>'}",
        f"清理占位残留：{prune_text}",
        "提示：将生成修复版 .gil（不覆盖原文件）。",
    ]
    preview_text3 = "\n".join(lines3)

    summary_text = f"修复信号：节点图={int(graphs_total)} 清理占位残留={prune_text}"

    return ExportCenterPreviewTexts(
        preview_text=str(preview_text3),
        summary_text=str(summary_text),
        summary_tooltip=str(preview_text3),
    )


def build_merge_signal_entries_preview_texts(
    *,
    package_id: str,
    input_gil_text: str,
    output_gil_text: str,
    keep_signal_name: str,
    remove_signal_name: str,
    rename_keep_to: str,
    patch_composite_pin_index: bool,
) -> ExportCenterPreviewTexts:
    input_text = str(input_gil_text or "").strip()
    output_text = str(output_gil_text or "").strip()
    keep = str(keep_signal_name or "").strip()
    remove = str(remove_signal_name or "").strip()
    rename = str(rename_keep_to or "").strip()
    patch_text = "是" if bool(patch_composite_pin_index) else "否"

    lines = [
        f"项目存档：{package_id}",
        f"目标 .gil：{input_text if input_text else '<未选择>'}",
        f"输出 .gil：{output_text if output_text else '<未填写>'}",
        f"keep：{keep if keep else '<未填写>'}",
        f"remove：{remove if remove else '<未填写>'}",
        f"rename：{rename if rename else '<不重命名>'}",
        f"修补 compositePinIndex：{patch_text}",
        "提示：将生成新的 .gil（不覆盖原文件）。",
    ]
    preview_text = "\n".join(lines)
    summary_text = "合并信号条目：" + (f"{keep} -> {rename}" if (keep and rename) else "执行合并")

    return ExportCenterPreviewTexts(
        preview_text=str(preview_text),
        summary_text=str(summary_text),
        summary_tooltip=str(preview_text),
    )


__all__ = [
    "ExportCenterPreviewTexts",
    "build_gia_preview_texts",
    "build_gil_preview_texts",
    "build_repair_signals_preview_texts",
    "build_merge_signal_entries_preview_texts",
]

