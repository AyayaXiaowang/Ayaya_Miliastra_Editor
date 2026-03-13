from __future__ import annotations

from pathlib import Path
from typing import Any

from .analysis_tab import update_analysis_tab as _update_analysis_tab_impl
from .analysis_tab import wire_analysis_tab
from .basic_sync import (
    sync_bundle_enabled_state,
    sync_builtin_empty_base_ui_state,
    sync_pack_enabled_state,
    sync_write_ui_effective_state,
    wire_basic_sync_connections,
)
from .env import build_export_center_dialog_wiring_env
from .execute_tab import build_get_progress_widget, wire_execute_tab
from .format_ui import update_format_ui
from .preview import update_preview as _update_preview_impl
from .repair_sync import sync_repair_output_default, wire_repair_output_sync
from .step_nav import sync_step_nav as _sync_step_nav_impl
from .step_nav import wire_step_navigation
from .ui_export_record import update_ui_export_record_detail_text, update_ui_export_record_ui


def wire_export_center_dialog(
    *,
    QtCore: Any,
    QtWidgets: Any,
    Colors: Any,
    Sizes: Any,
    ThemeManager: Any,
    dialog: Any,
    main_window: Any,
    workspace_root: Path,
    package_id: str,
    project_root: Path,
    left: Any,
    right: Any,
    wizard_tabs: Any,
    footer: Any,
    open_task_history_dialog: Any,
    append_task_history_entry: Any,
    now_ts: Any,
) -> None:
    """组装并连接导出中心对话框的全部 UI wiring。"""

    env = build_export_center_dialog_wiring_env(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        dialog=dialog,
        main_window=main_window,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        project_root=Path(project_root),
        left=left,
        right=right,
        wizard_tabs=wizard_tabs,
        footer=footer,
        open_task_history_dialog=open_task_history_dialog,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
    )

    def _sync_step_nav() -> None:
        """触发步骤导航区域的状态同步。"""

        _sync_step_nav_impl(env)

    def _update_analysis_tab() -> None:
        """触发回填分析页的联动刷新。"""

        _update_analysis_tab_impl(env)

    def _update_preview(*_args: object) -> None:
        """触发步骤3预览与摘要的联动刷新。"""

        _update_preview_impl(env, update_analysis_tab=_update_analysis_tab)

    def _update_ui_export_record_ui(*_args: object) -> None:
        """触发 UI 回填记录选项与占位符扫描结果的刷新。"""

        update_ui_export_record_ui(env, update_analysis_tab=_update_analysis_tab)

    def _sync_bundle_enabled_state(*_args: object) -> None:
        """触发 GIA 打包子选项状态同步。"""

        sync_bundle_enabled_state(env)

    def _sync_pack_enabled_state(*_args: object) -> None:
        """触发“打包合并(.gia)”可用性状态同步。"""

        sync_pack_enabled_state(env)

    def _sync_write_ui_effective_state(*_args: object) -> None:
        """触发“UI 写回”强制策略状态同步。"""

        sync_write_ui_effective_state(env)

    def _sync_repair_output_default(*_args: object) -> None:
        """触发修复输出路径的默认值同步。"""

        sync_repair_output_default(env)

    def _sync_left_selected_list() -> None:
        """将资源树当前选中项同步到左侧“已选清单”。"""

        env.left.selected_list.clear()
        for it in sorted(list(env.picker.get_selected_items()), key=lambda x: str(getattr(x, "key", "")).casefold()):
            prefix = "项目" if getattr(it, "source_root", "") == "project" else "共享"
            display = str(getattr(env.picker, "get_item_display_text")(it))
            text = f"[{prefix}] {display} — {getattr(it, 'relative_path', '')}"
            item = env.QtWidgets.QListWidgetItem(text)
            item.setToolTip(str(getattr(it, "absolute_path", "")))
            item.setData(env.QtCore.Qt.ItemDataRole.UserRole, str(getattr(it, "key", "")))
            env.left.selected_list.addItem(item)

    def _remove_selected_from_left_list() -> None:
        """从左侧“已选清单”移除选中项并同步取消勾选。"""

        keys = [
            str(x.data(env.QtCore.Qt.ItemDataRole.UserRole) or "").strip()
            for x in env.left.selected_list.selectedItems()
        ]
        keys = [k for k in keys if k]
        if keys:
            env.picker.remove_keys(keys)

    def _clear_left_selection() -> None:
        """清空左侧资源树的勾选状态。"""

        env.picker.clear_selection()

    env.left.selected_remove_btn.clicked.connect(_remove_selected_from_left_list)
    env.left.selected_clear_btn.clicked.connect(_clear_left_selection)
    env.picker.selection_changed.connect(_sync_left_selected_list)

    def _on_picker_selection_changed() -> None:
        """处理资源选择变化并触发相关联动刷新。"""

        _sync_pack_enabled_state()
        _sync_write_ui_effective_state()
        _update_ui_export_record_ui()
        _update_preview()
        _sync_step_nav()

    env.picker.selection_changed.connect(_on_picker_selection_changed)

    wire_basic_sync_connections(env, update_preview=lambda: _update_preview())
    wire_repair_output_sync(env, update_preview=lambda: _update_preview())
    env.gil.gil_ui_export_record_refresh_btn.clicked.connect(_update_ui_export_record_ui)
    env.gia.ui_export_record_combo.currentIndexChanged.connect(lambda *_: update_ui_export_record_detail_text(env))

    env.gia.out_dir_edit.textChanged.connect(_update_preview)
    env.gia.copy_dir_edit.textChanged.connect(_update_preview)
    env.gia.gia_id_ref_edit.textChanged.connect(_update_preview)
    env.gia.player_template_base_gia_edit.textChanged.connect(_update_preview)

    env.gil.input_gil_edit.textChanged.connect(_update_preview)
    env.gil.output_gil_edit.textChanged.connect(_update_preview)
    env.gil.struct_mode_combo.currentIndexChanged.connect(_update_preview)
    env.gil.instances_mode_combo.currentIndexChanged.connect(_update_preview)
    env.gil.signals_mode_combo.currentIndexChanged.connect(_update_preview)
    env.gil.prefer_signal_specific_type_id_cb.toggled.connect(_update_preview)
    env.gil.ui_mode_combo.currentIndexChanged.connect(_update_preview)
    env.gil.ui_auto_sync_vars_cb.toggled.connect(_update_preview)
    env.gil.gil_ui_export_record_combo.currentIndexChanged.connect(_update_preview)
    env.gil.gil_id_ref_edit.textChanged.connect(_update_preview)

    env.repair.repair_output_gil_edit.textChanged.connect(_update_preview)
    env.repair.repair_prune_orphans_cb.toggled.connect(_update_preview)
    env.repair.merge_keep_signal_edit.textChanged.connect(_update_preview)
    env.repair.merge_remove_signal_edit.textChanged.connect(_update_preview)
    env.repair.merge_rename_keep_to_edit.textChanged.connect(_update_preview)
    env.repair.merge_patch_cpi_cb.toggled.connect(_update_preview)

    get_progress_widget = build_get_progress_widget(env)
    run = wire_execute_tab(env, get_progress_widget=get_progress_widget, sync_step_nav=_sync_step_nav)
    wire_step_navigation(env, on_run_clicked=run, update_preview=lambda: _update_preview())
    wire_analysis_tab(env, update_analysis_tab=_update_analysis_tab)

    env.format_combo.currentIndexChanged.connect(
        lambda *_: update_format_ui(
            env,
            sync_bundle_enabled_state=_sync_bundle_enabled_state,
            sync_pack_enabled_state=_sync_pack_enabled_state,
            sync_write_ui_effective_state=_sync_write_ui_effective_state,
            update_ui_export_record_ui=_update_ui_export_record_ui,
            update_preview=lambda: _update_preview(),
            sync_repair_output_default=_sync_repair_output_default,
        )
    )

    _sync_repair_output_default()
    update_format_ui(
        env,
        sync_bundle_enabled_state=_sync_bundle_enabled_state,
        sync_pack_enabled_state=_sync_pack_enabled_state,
        sync_write_ui_effective_state=_sync_write_ui_effective_state,
        update_ui_export_record_ui=_update_ui_export_record_ui,
        update_preview=lambda: _update_preview(),
        sync_repair_output_default=_sync_repair_output_default,
    )
    _sync_left_selected_list()
    sync_builtin_empty_base_ui_state(env)
    _sync_step_nav()

