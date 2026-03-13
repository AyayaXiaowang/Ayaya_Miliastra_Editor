from __future__ import annotations

from typing import Callable

from .env import ExportCenterDialogWiringEnv


def update_format_ui(
    env: ExportCenterDialogWiringEnv,
    *,
    sync_bundle_enabled_state: Callable[[], None],
    sync_pack_enabled_state: Callable[[], None],
    sync_write_ui_effective_state: Callable[[], None],
    update_ui_export_record_ui: Callable[[], None],
    update_preview: Callable[[], None],
    sync_repair_output_default: Callable[[], None],
) -> None:
    """根据当前格式切换右侧配置页并触发相关联动刷新。"""

    fmt = str(env.format_combo.currentData() or "gia")
    if fmt == "gia":
        env.stacked.setCurrentWidget(env.gia.page)
        removed = env.picker.set_allowed_categories({"graphs", "templates", "player_templates", "mgmt_cfg"}, prune_selection=True)
        if int(removed) > 0:
            env.rt.selection_pruned_note = f"提示：切换到 GIA 模式后，已自动移除 {int(removed)} 项不支持的勾选。"
        env.run_btn.setText("开始导出")
        env.repair.repair_auto_box.setVisible(True)
        env.repair.merge_entries_box.setVisible(True)
    elif fmt == "gil":
        env.stacked.setCurrentWidget(env.gil.page)
        removed = env.picker.set_allowed_categories(
            {"graphs", "templates", "instances", "ui_src", "custom_vars", "mgmt_cfg"},
            prune_selection=True,
        )
        if int(removed) > 0:
            env.rt.selection_pruned_note = f"提示：切换到 GIL 模式后，已自动移除 {int(removed)} 项不支持的勾选。"
        env.run_btn.setText("开始导出")
        env.repair.repair_auto_box.setVisible(True)
        env.repair.merge_entries_box.setVisible(True)
    elif fmt == "repair_signals":
        env.stacked.setCurrentWidget(env.repair.page)
        removed = env.picker.set_allowed_categories({"graphs"}, prune_selection=True)
        if int(removed) > 0:
            env.rt.selection_pruned_note = f"提示：切换到『修复信号』模式后，已自动移除 {int(removed)} 项不支持的勾选。"
        env.run_btn.setText("开始修复")
        env.repair.repair_auto_box.setVisible(True)
        env.repair.merge_entries_box.setVisible(False)
        sync_repair_output_default()
    elif fmt == "merge_signal_entries":
        env.stacked.setCurrentWidget(env.repair.page)
        removed = env.picker.set_allowed_categories({"graphs"}, prune_selection=True)
        if int(removed) > 0:
            env.rt.selection_pruned_note = f"提示：切换到『合并信号条目』模式后，已自动移除 {int(removed)} 项不支持的勾选。"
        env.run_btn.setText("开始合并")
        env.repair.repair_auto_box.setVisible(False)
        env.repair.merge_entries_box.setVisible(True)
        sync_repair_output_default()
    else:
        env.stacked.setCurrentWidget(env.repair.page)
        removed = env.picker.set_allowed_categories({"graphs"}, prune_selection=True)
        if int(removed) > 0:
            env.rt.selection_pruned_note = f"提示：切换模式后，已自动移除 {int(removed)} 项不支持的勾选。"
        env.run_btn.setText("开始修复")
        env.repair.repair_auto_box.setVisible(True)
        env.repair.merge_entries_box.setVisible(True)

    sync_bundle_enabled_state()
    sync_pack_enabled_state()
    sync_write_ui_effective_state()
    update_ui_export_record_ui()
    update_preview()

