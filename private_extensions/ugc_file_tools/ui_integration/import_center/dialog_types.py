from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ImportCenterStep1Widgets:
    """保存导入中心步骤1（选择与配置）的 widget 引用。"""

    task_combo: Any

    # 公共：输入文件
    input_path_edit: Any
    input_browse_btn: Any

    # 公共：目标项目存档
    target_mode_combo: Any
    package_name_edit: Any
    existing_package_combo: Any
    overwrite_checkbox: Any
    overwrite_warning_label: Any

    # GIL（整包/选择性）通用选项
    enable_dll_dump_checkbox: Any
    generate_graph_code_checkbox: Any
    validate_after_generate_checkbox: Any

    # GIL（选择性）导入范围（资源段）
    gil_selected_parts_box: Any
    export_node_graphs_cb: Any
    export_templates_cb: Any
    export_instances_cb: Any
    export_struct_defs_cb: Any
    export_signals_cb: Any
    export_combat_presets_cb: Any
    export_section15_cb: Any
    export_raw_pyugc_cb: Any
    export_data_blobs_cb: Any

    # GIA 导入配置
    gia_config_box: Any
    gia_import_kind_combo: Any
    gia_templates_cb: Any
    gia_instances_cb: Any
    gia_instances_mode_row: Any
    gia_instances_mode_combo: Any
    gia_decode_depth_spin: Any
    gia_validate_after_import_cb: Any

    preview_label: Any


@dataclass(frozen=True, slots=True)
class ImportCenterStep2Widgets:
    """保存导入中心步骤2（预览/分析）的 widget 引用。"""

    stacked: Any
    default_preview_text: Any

    # GIL 选择性导入：节点图清单
    gil_selected_page: Any
    gil_selected_scan_btn: Any
    gil_selected_select_all_btn: Any
    gil_selected_unselect_all_btn: Any
    gil_selected_scan_status_label: Any
    gil_selected_graphs_list: Any
    gil_selected_preview_text: Any


@dataclass(frozen=True, slots=True)
class ImportCenterStep3Widgets:
    """保存导入中心步骤3（执行）的 widget 引用。"""

    progress_label: Any
    progress_bar: Any
    log_text: Any
    result_text: Any
    clear_log_btn: Any
    clear_result_btn: Any


@dataclass(frozen=True, slots=True)
class ImportCenterDialogWidgets:
    """保存导入中心对话框的 widget 引用集合。"""

    dialog: Any
    wizard_tabs: Any
    step1: ImportCenterStep1Widgets
    step2: ImportCenterStep2Widgets
    step3: ImportCenterStep3Widgets
    footer: Any

