from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExportCenterContext:
    workspace_root: Path
    package_id: str
    show_import: bool
    export_enabled: bool

    packages_root: Path
    resource_library_root: Path
    shared_root: Path
    project_root: Path


@dataclass(frozen=True, slots=True)
class ExportCenterLeftPane:
    pane: Any
    picker: Any

    selected_summary_label: Any
    selected_list: Any
    selected_remove_btn: Any
    selected_clear_btn: Any

    persist_expanded_state: Any


@dataclass(frozen=True, slots=True)
class ExportCenterBackfillPanel:
    """
    导出中心：节点图回填识别面板（GIL 识别对比表）。

    注意：该结构仅保存 widget refs；更新逻辑由 controller 统一编排。
    """

    box: Any
    target_label: Any
    identify_btn: Any
    tabs: Any
    missing_table: Any
    ready_table: Any

    # 底部固定进度条（不随滚动）
    progress_row: Any
    progress_label: Any
    progress_bar: Any


@dataclass(frozen=True, slots=True)
class ExportCenterAnalysisTab:
    """
    导出中心：步骤 2「回填分析」页（回填依赖清单与识别对比合并到同一张表格）。
    """

    page: Any
    strategy_text: Any
    backfill_panel: ExportCenterBackfillPanel


@dataclass(frozen=True, slots=True)
class ExportCenterExecuteTab:
    """
    导出中心：步骤 3「执行」页（计划预览 + 进度/日志 + 结果摘要）。
    """

    page: Any
    plan_preview_text: Any
    run_btn: Any
    progress_label: Any
    progress_bar: Any
    log_text: Any
    result_text: Any
    clear_log_btn: Any
    clear_result_btn: Any


@dataclass(frozen=True, slots=True)
class ExportCenterGiaPage:
    page: Any
    out_dir_edit: Any
    copy_dir_edit: Any

    base_gil_row: Any
    base_gil_edit: Any
    player_template_base_gia_row: Any
    player_template_base_gia_edit: Any

    gia_advanced_toggle: Any
    gia_advanced_box: Any

    allow_unresolved_ui_keys_cb: Any

    ui_export_record_row: Any
    ui_export_record_combo: Any
    ui_export_record_detail: Any

    gia_id_ref_row: Any
    gia_id_ref_edit: Any

    bundle_enabled_cb: Any
    bundle_include_signals_cb: Any
    bundle_include_ui_guid_cb: Any

    pack_graphs_cb: Any
    pack_name_edit: Any

    base_gia_edit: Any
    decode_depth_spin: Any


@dataclass(frozen=True, slots=True)
class ExportCenterGilPage:
    page: Any

    input_gil_edit: Any
    input_gil_browse_btn: Any
    output_gil_edit: Any

    use_builtin_empty_base_cb: Any
    builtin_empty_base_hint: Any

    recent_combo: Any
    recent_use_btn: Any
    recent_refresh_btn: Any

    gil_advanced_toggle: Any
    gil_advanced_box: Any

    struct_mode_combo: Any
    templates_mode_combo: Any
    instances_mode_combo: Any
    signals_mode_combo: Any
    prefer_signal_specific_type_id_cb: Any
    ui_mode_combo: Any

    gil_ui_export_record_row: Any
    gil_ui_export_record_combo: Any
    gil_ui_export_record_refresh_btn: Any

    gil_id_ref_row: Any
    gil_id_ref_edit: Any

    write_ui_cb: Any
    write_ui_hint: Any
    ui_auto_sync_vars_cb: Any

    selected_level_custom_variable_ids: list[str]
    level_custom_variable_meta_by_id: dict[str, dict[str, str]]
    level_vars_preview: Any
    level_vars_select_btn: Any
    level_vars_clear_btn: Any


@dataclass(frozen=True, slots=True)
class ExportCenterRepairPage:
    page: Any
    repair_input_gil_edit: Any
    repair_output_gil_edit: Any
    repair_auto_box: Any
    repair_prune_orphans_cb: Any
    # 合并信号 entry 模式（merge_gil_signal_entries）
    merge_entries_box: Any
    merge_keep_signal_edit: Any
    merge_remove_signal_edit: Any
    merge_rename_keep_to_edit: Any
    merge_patch_cpi_cb: Any


@dataclass(frozen=True, slots=True)
class ExportCenterRightPane:
    # Step1：配置区（仅右侧配置，不含资源选择）
    config_pane: Any

    # Step2/3：整页 tabs（由外层导出向导使用）
    analysis: ExportCenterAnalysisTab
    execute: ExportCenterExecuteTab

    format_combo: Any
    format_desc: Any
    stacked: Any

    gia: ExportCenterGiaPage
    gil: ExportCenterGilPage
    repair: ExportCenterRepairPage


@dataclass(frozen=True, slots=True)
class ExportCenterPreview:
    frame: Any
    preview: Any

    id_ref_usage_sep: Any
    id_ref_usage_label: Any
    id_ref_usage_text: Any


@dataclass(frozen=True, slots=True)
class ExportCenterFooter:
    history_btn: Any
    back_btn: Any
    next_btn: Any
    close_btn: Any

