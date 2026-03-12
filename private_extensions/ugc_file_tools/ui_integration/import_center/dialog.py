from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from engine.utils.name_utils import generate_unique_name

from .._common import get_selected_package_id, resolve_packages_root_dir
from ..center_dialog_scaffold import (
    add_center_tabs,
    add_center_title_row,
    create_center_dialog_base,
    raise_existing_center_dialog,
)
from .controller import wire_import_center_dialog
from .dialog_types import (
    ImportCenterDialogWidgets,
    ImportCenterStep1Widgets,
    ImportCenterStep2Widgets,
    ImportCenterStep3Widgets,
)
from .plans import IMPORT_TASKS, IMPORT_TASK_GIA, IMPORT_TASK_GIL_FULL, IMPORT_TASK_GIL_SELECTED


DEFAULT_DIALOG_MIN_W = 1200
DEFAULT_DIALOG_MIN_H = 780
DEFAULT_DIALOG_FALLBACK_W = 1200
DEFAULT_DIALOG_FALLBACK_H = 800
DIALOG_SCALE_W = 0.96
DIALOG_SCALE_H = 0.92
WIZARD_MIN_HEIGHT = 520
STEP1_RIGHT_COLUMN_MIN_W = 560
STEP1_RIGHT_COLUMN_MAX_W = 820
STEP1_RIGHT_COLUMN_RATIO = 0.45

DEFAULT_GIA_DECODE_DEPTH_MIN = 8
DEFAULT_GIA_DECODE_DEPTH_MAX = 200
DEFAULT_GIA_DECODE_DEPTH_VALUE = 28


def open_import_center_dialog(main_window: object, *, preferred_task: str | None = None) -> None:
    """打开 ugc_file_tools 导入中心（非模态三步对话框）。"""
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
    from .controller import refresh_package_library_and_select_package
    from ..export_center_dialog_footer import build_export_center_footer
    from ..export_history import append_task_history_entry, now_ts, open_task_history_dialog

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    dialog_attr = "_ugc_file_tools_import_center_dialog"
    if raise_existing_center_dialog(QtWidgets=QtWidgets, main_window=main_window, dialog_attr=str(dialog_attr)):
        return

    app_state = getattr(main_window, "app_state", None)
    if app_state is None:
        raise RuntimeError("主窗口缺少 app_state，无法打开导入中心")

    workspace_root = Path(getattr(app_state, "workspace_path")).resolve()
    packages_root = resolve_packages_root_dir(workspace_root=workspace_root).resolve()
    packages_root.mkdir(parents=True, exist_ok=True)

    package_index_manager = getattr(app_state, "package_index_manager", None)
    if package_index_manager is None:
        raise RuntimeError("主窗口缺少 package_index_manager，无法执行导入")

    sanitize_fn = getattr(package_index_manager, "sanitize_package_id", None)
    if not callable(sanitize_fn):
        raise RuntimeError("PackageIndexManager 缺少 sanitize_package_id，无法生成目录名")

    existing_names = [p.name for p in packages_root.iterdir() if p.is_dir()]
    template_package_dirname = str(getattr(package_index_manager, "TEMPLATE_PACKAGE_DIRNAME", "示例项目模板") or "").strip()
    importable_package_ids = sorted(
        [name for name in existing_names if name and name != template_package_dirname],
        key=lambda text: str(text).casefold(),
    )

    # 预选已有项目存档（优先当前选中包）
    default_existing_package_id = str(get_selected_package_id(main_window) or "").strip()
    if default_existing_package_id in {"global_view", "unclassified_view"}:
        default_existing_package_id = ""
    if default_existing_package_id not in set(importable_package_ids):
        default_existing_package_id = ""

    base = create_center_dialog_base(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        main_window=main_window,
        dialog_attr=str(dialog_attr),
        object_name="ugc_file_tools_import_center_dialog",
        window_title="导入中心",
        min_w=int(DEFAULT_DIALOG_MIN_W),
        min_h=int(DEFAULT_DIALOG_MIN_H),
        fallback_w=int(DEFAULT_DIALOG_FALLBACK_W),
        fallback_h=int(DEFAULT_DIALOG_FALLBACK_H),
        scale_w=float(DIALOG_SCALE_W),
        scale_h=float(DIALOG_SCALE_H),
    )
    dialog = base.dialog
    root_layout = base.root_layout

    add_center_title_row(QtWidgets=QtWidgets, ThemeManager=ThemeManager, base=base, title_text="导入中心")
    wizard_tabs = add_center_tabs(QtWidgets=QtWidgets, base=base, min_height=int(WIZARD_MIN_HEIGHT), document_mode=True)
    wizard_tabs.setMovable(False)
    wizard_tabs.setTabsClosable(False)

    # ===== Step1 =====
    step1_page = QtWidgets.QWidget(wizard_tabs)
    step1_layout = QtWidgets.QVBoxLayout(step1_page)
    step1_layout.setContentsMargins(0, 0, 0, 0)
    step1_layout.setSpacing(Sizes.SPACING_MEDIUM)

    config_row = QtWidgets.QWidget(step1_page)
    config_row_layout = QtWidgets.QHBoxLayout(config_row)
    config_row_layout.setContentsMargins(0, 0, 0, 0)
    config_row_layout.setSpacing(Sizes.SPACING_MEDIUM)

    task_combo = QtWidgets.QComboBox(config_row)
    task_combo.addItem("读取 .gil（整包导入为项目存档）", IMPORT_TASK_GIL_FULL)
    task_combo.addItem("读取 .gil（选择性导入）", IMPORT_TASK_GIL_SELECTED)
    task_combo.addItem("导入 .gia（写入项目存档）", IMPORT_TASK_GIA)
    config_row_layout.addWidget(QtWidgets.QLabel("任务类型：", config_row))
    config_row_layout.addWidget(task_combo, 1)
    step1_layout.addWidget(config_row)

    step1_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, step1_page)
    step1_splitter.setHandleWidth(6)
    step1_splitter.setStyleSheet(ThemeManager.splitter_style())
    step1_layout.addWidget(step1_splitter, 1)

    left_pane = QtWidgets.QWidget(step1_splitter)
    left_layout = QtWidgets.QVBoxLayout(left_pane)
    left_layout.setContentsMargins(0, 0, 0, 0)
    left_layout.setSpacing(Sizes.SPACING_MEDIUM)

    # 输入文件
    input_group = QtWidgets.QGroupBox("输入文件", left_pane)
    input_group.setStyleSheet(ThemeManager.group_box_style())
    input_group_layout = QtWidgets.QVBoxLayout(input_group)
    input_group_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    input_group_layout.setSpacing(Sizes.SPACING_SMALL)

    input_row = QtWidgets.QWidget(input_group)
    input_row_layout = QtWidgets.QHBoxLayout(input_row)
    input_row_layout.setContentsMargins(0, 0, 0, 0)
    input_row_layout.setSpacing(Sizes.SPACING_SMALL)
    input_path_edit = QtWidgets.QLineEdit(input_row)
    input_path_edit.setPlaceholderText("请选择一个 .gil 或 .gia 文件…")
    input_browse_btn = QtWidgets.QPushButton("浏览…", input_row)
    input_browse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    input_row_layout.addWidget(input_path_edit, 1)
    input_row_layout.addWidget(input_browse_btn)
    input_group_layout.addWidget(input_row)
    left_layout.addWidget(input_group)

    # 目标项目存档
    target_group = QtWidgets.QGroupBox("导入目标", left_pane)
    target_group.setStyleSheet(ThemeManager.group_box_style())
    target_group_layout = QtWidgets.QGridLayout(target_group)
    target_group_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    target_group_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    target_group_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

    target_mode_combo = QtWidgets.QComboBox(target_group)
    target_mode_combo.addItem("导入到已有项目存档（推荐）", "existing")
    target_mode_combo.addItem("新建项目存档", "new")
    if not importable_package_ids:
        idx = int(target_mode_combo.findData("new"))
        if idx >= 0:
            target_mode_combo.setCurrentIndex(int(idx))

    package_name_edit = QtWidgets.QLineEdit(target_group)
    package_name_edit.setPlaceholderText("仅新建模式使用；默认使用文件名，可自行修改")

    existing_package_combo = QtWidgets.QComboBox(target_group)
    existing_package_combo.setEditable(False)
    for pid in importable_package_ids:
        existing_package_combo.addItem(str(pid))
    if default_existing_package_id:
        idx2 = int(existing_package_combo.findText(str(default_existing_package_id)))
        if idx2 >= 0:
            existing_package_combo.setCurrentIndex(int(idx2))

    overwrite_checkbox = QtWidgets.QCheckBox("允许覆盖已存在的输出（谨慎）", target_group)
    overwrite_checkbox.setChecked(False)

    overwrite_warning_label = QtWidgets.QLabel("", target_group)
    overwrite_warning_label.setWordWrap(True)
    overwrite_warning_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")

    target_group_layout.addWidget(QtWidgets.QLabel("目标模式：", target_group), 0, 0)
    target_group_layout.addWidget(target_mode_combo, 0, 1)
    target_group_layout.addWidget(QtWidgets.QLabel("项目存档名：", target_group), 1, 0)
    target_group_layout.addWidget(package_name_edit, 1, 1)
    target_group_layout.addWidget(QtWidgets.QLabel("目标存档：", target_group), 2, 0)
    target_group_layout.addWidget(existing_package_combo, 2, 1)
    target_group_layout.addWidget(overwrite_checkbox, 3, 0, 1, 2)
    target_group_layout.addWidget(overwrite_warning_label, 4, 0, 1, 2)
    left_layout.addWidget(target_group)

    # 选项（GIL）
    options_group = QtWidgets.QGroupBox("选项", left_pane)
    options_group.setStyleSheet(ThemeManager.group_box_style())
    options_layout = QtWidgets.QVBoxLayout(options_group)
    options_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    options_layout.setSpacing(Sizes.SPACING_SMALL)

    generate_graph_code_checkbox = QtWidgets.QCheckBox("生成可识别的节点图代码（推荐）", options_group)
    generate_graph_code_checkbox.setChecked(True)
    validate_after_generate_checkbox = QtWidgets.QCheckBox("生成后自动校验（推荐）", options_group)
    validate_after_generate_checkbox.setChecked(True)
    enable_dll_dump_checkbox = QtWidgets.QCheckBox("解析并导出界面控件组（UI控件模板）", options_group)
    enable_dll_dump_checkbox.setChecked(True)
    options_layout.addWidget(generate_graph_code_checkbox)
    options_layout.addWidget(validate_after_generate_checkbox)
    options_layout.addWidget(enable_dll_dump_checkbox)
    left_layout.addWidget(options_group)

    # 预览
    preview_label = QtWidgets.QLabel("", left_pane)
    preview_label.setWordWrap(True)
    preview_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    left_layout.addWidget(preview_label)
    left_layout.addStretch(1)

    # 右侧：任务特定配置（GIL 选择性导入范围 + GIA）
    right_pane = QtWidgets.QWidget(step1_splitter)
    right_layout = QtWidgets.QVBoxLayout(right_pane)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(Sizes.SPACING_MEDIUM)
    right_pane.setMinimumWidth(int(STEP1_RIGHT_COLUMN_MIN_W))

    # GIL 选择性导入：资源段开关
    gil_selected_parts_box = QtWidgets.QGroupBox("选择性导入范围（可选）", right_pane)
    gil_selected_parts_box.setStyleSheet(ThemeManager.group_box_style())
    parts_grid = QtWidgets.QGridLayout(gil_selected_parts_box)
    parts_grid.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    parts_grid.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    parts_grid.setVerticalSpacing(Sizes.SPACING_SMALL)

    export_node_graphs_cb = QtWidgets.QCheckBox("节点图（步骤2选择）", gil_selected_parts_box)
    export_node_graphs_cb.setChecked(True)
    export_templates_cb = QtWidgets.QCheckBox("元件", gil_selected_parts_box)
    export_templates_cb.setChecked(False)
    export_instances_cb = QtWidgets.QCheckBox("实体摆放", gil_selected_parts_box)
    export_instances_cb.setChecked(False)
    export_struct_defs_cb = QtWidgets.QCheckBox("结构体定义", gil_selected_parts_box)
    export_struct_defs_cb.setChecked(False)
    export_signals_cb = QtWidgets.QCheckBox("信号定义", gil_selected_parts_box)
    export_signals_cb.setChecked(False)
    export_combat_presets_cb = QtWidgets.QCheckBox("战斗预设（玩家模板/职业）", gil_selected_parts_box)
    export_combat_presets_cb.setChecked(False)
    export_section15_cb = QtWidgets.QCheckBox("战斗/管理条目（技能/道具/关卡设置等）", gil_selected_parts_box)
    export_section15_cb.setChecked(False)
    export_raw_pyugc_cb = QtWidgets.QCheckBox("原始解析（pyugc dump/string_index）", gil_selected_parts_box)
    export_raw_pyugc_cb.setChecked(False)
    export_data_blobs_cb = QtWidgets.QCheckBox("数据块解析（原始解析/数据块 + decoded_*）", gil_selected_parts_box)
    export_data_blobs_cb.setChecked(False)

    parts_grid.addWidget(export_node_graphs_cb, 0, 0)
    parts_grid.addWidget(export_templates_cb, 0, 1)
    parts_grid.addWidget(export_instances_cb, 0, 2)
    parts_grid.addWidget(export_struct_defs_cb, 1, 0)
    parts_grid.addWidget(export_signals_cb, 1, 1)
    parts_grid.addWidget(export_combat_presets_cb, 1, 2)
    parts_grid.addWidget(export_section15_cb, 2, 0, 1, 3)
    parts_grid.addWidget(export_raw_pyugc_cb, 3, 0, 1, 3)
    parts_grid.addWidget(export_data_blobs_cb, 4, 0, 1, 3)
    right_layout.addWidget(gil_selected_parts_box)

    # GIA 配置
    gia_config_box = QtWidgets.QGroupBox("GIA 导入配置", right_pane)
    gia_config_box.setStyleSheet(ThemeManager.group_box_style())
    gia_form = QtWidgets.QFormLayout(gia_config_box)
    gia_form.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    gia_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    gia_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    gia_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

    gia_import_kind_combo = QtWidgets.QComboBox(gia_config_box)
    gia_import_kind_combo.addItem("元件 + 实体摆放（bundle.gia）", "templates_instances")
    gia_import_kind_combo.addItem("玩家模板（player_template.gia）", "player_template")
    gia_import_kind_combo.addItem("节点图（node_graph.gia）", "node_graphs")
    gia_form.addRow("导入类型：", gia_import_kind_combo)

    gia_templates_cb = QtWidgets.QCheckBox("导入元件（元件库）", gia_config_box)
    gia_templates_cb.setChecked(True)
    gia_form.addRow("", gia_templates_cb)

    gia_instances_cb = QtWidgets.QCheckBox("导入实体摆放（instances）", gia_config_box)
    gia_instances_cb.setChecked(True)
    gia_form.addRow("", gia_instances_cb)

    gia_instances_mode_row = QtWidgets.QWidget(gia_config_box)
    gia_instances_mode_layout = QtWidgets.QHBoxLayout(gia_instances_mode_row)
    gia_instances_mode_layout.setContentsMargins(0, 0, 0, 0)
    gia_instances_mode_layout.setSpacing(Sizes.SPACING_SMALL)
    gia_instances_mode_combo = QtWidgets.QComboBox(gia_instances_mode_row)
    gia_instances_mode_combo.addItem("写入对应元件（decorations_to_template）", "decorations_to_template")
    gia_instances_mode_combo.addItem("合并为装饰物载体（decorations_carrier）", "decorations_carrier")
    gia_instances_mode_combo.addItem("生成独立实体摆放（instances）", "instances")
    gia_instances_mode_layout.addWidget(gia_instances_mode_combo, 1)
    gia_form.addRow("装饰物模式：", gia_instances_mode_row)

    gia_decode_depth_spin = QtWidgets.QSpinBox(gia_config_box)
    gia_decode_depth_spin.setRange(int(DEFAULT_GIA_DECODE_DEPTH_MIN), int(DEFAULT_GIA_DECODE_DEPTH_MAX))
    gia_decode_depth_spin.setValue(int(DEFAULT_GIA_DECODE_DEPTH_VALUE))
    gia_form.addRow("解码深度：", gia_decode_depth_spin)

    gia_validate_after_import_cb = QtWidgets.QCheckBox("导入后校验项目存档（推荐）", gia_config_box)
    gia_validate_after_import_cb.setChecked(True)
    gia_form.addRow("", gia_validate_after_import_cb)

    right_layout.addWidget(gia_config_box)
    right_layout.addStretch(1)

    step1_splitter.addWidget(left_pane)
    step1_splitter.addWidget(right_pane)
    step1_splitter.setCollapsible(0, False)
    step1_splitter.setCollapsible(1, False)
    step1_splitter.setStretchFactor(0, 3)
    step1_splitter.setStretchFactor(1, 2)

    content_w = max(0, int(dialog.width() - int(Sizes.PADDING_LARGE) * 2))
    right_w = int(content_w * float(STEP1_RIGHT_COLUMN_RATIO))
    right_w = max(int(STEP1_RIGHT_COLUMN_MIN_W), min(int(STEP1_RIGHT_COLUMN_MAX_W), int(right_w)))
    left_w = max(0, int(content_w - right_w))
    step1_splitter.setSizes([int(left_w), int(right_w)])

    wizard_tabs.addTab(step1_page, "步骤1：选择与配置")

    # ===== Step2 =====
    step2_page = QtWidgets.QWidget(wizard_tabs)
    step2_layout = QtWidgets.QVBoxLayout(step2_page)
    step2_layout.setContentsMargins(0, 0, 0, 0)
    step2_layout.setSpacing(Sizes.SPACING_MEDIUM)

    step2_stacked = QtWidgets.QStackedWidget(step2_page)
    step2_layout.addWidget(step2_stacked, 1)

    default_preview_text = QtWidgets.QPlainTextEdit(step2_page)
    default_preview_text.setReadOnly(True)
    default_preview_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    default_preview_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    default_preview_text.setPlaceholderText("（完成步骤1配置后，这里会显示导入预览）")
    step2_stacked.addWidget(default_preview_text)

    gil_selected_page = QtWidgets.QWidget(step2_stacked)
    gil_selected_layout = QtWidgets.QVBoxLayout(gil_selected_page)
    gil_selected_layout.setContentsMargins(0, 0, 0, 0)
    gil_selected_layout.setSpacing(Sizes.SPACING_SMALL)

    gil_selected_action_row = QtWidgets.QWidget(gil_selected_page)
    gil_selected_action_layout = QtWidgets.QHBoxLayout(gil_selected_action_row)
    gil_selected_action_layout.setContentsMargins(0, 0, 0, 0)
    gil_selected_action_layout.setSpacing(Sizes.SPACING_SMALL)

    gil_selected_scan_btn = QtWidgets.QPushButton("分析节点图清单…", gil_selected_action_row)
    gil_selected_scan_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gil_selected_select_all_btn = QtWidgets.QPushButton("全选", gil_selected_action_row)
    gil_selected_unselect_all_btn = QtWidgets.QPushButton("全不选", gil_selected_action_row)
    gil_selected_action_layout.addWidget(gil_selected_scan_btn)
    gil_selected_action_layout.addStretch(1)
    gil_selected_action_layout.addWidget(gil_selected_select_all_btn)
    gil_selected_action_layout.addWidget(gil_selected_unselect_all_btn)
    gil_selected_layout.addWidget(gil_selected_action_row)

    gil_selected_scan_status_label = QtWidgets.QLabel("尚未分析节点图清单。", gil_selected_page)
    gil_selected_scan_status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    gil_selected_layout.addWidget(gil_selected_scan_status_label)

    gil_selected_graphs_list = QtWidgets.QListWidget(gil_selected_page)
    gil_selected_graphs_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
    gil_selected_graphs_list.setMinimumHeight(260)
    gil_selected_layout.addWidget(gil_selected_graphs_list, 1)

    gil_selected_preview_text = QtWidgets.QPlainTextEdit(gil_selected_page)
    gil_selected_preview_text.setReadOnly(True)
    gil_selected_preview_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    gil_selected_preview_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    gil_selected_preview_text.setPlaceholderText("（这里会显示导入范围与所选节点图摘要）")
    gil_selected_preview_text.setMinimumHeight(160)
    gil_selected_layout.addWidget(gil_selected_preview_text, 0)

    step2_stacked.addWidget(gil_selected_page)
    wizard_tabs.addTab(step2_page, "步骤2：预览/分析")

    # ===== Step3 =====
    step3_page = QtWidgets.QWidget(wizard_tabs)
    step3_layout = QtWidgets.QVBoxLayout(step3_page)
    step3_layout.setContentsMargins(0, 0, 0, 0)
    step3_layout.setSpacing(Sizes.SPACING_SMALL)

    log_box = QtWidgets.QGroupBox("执行日志（摘要）", step3_page)
    log_box.setStyleSheet(ThemeManager.group_box_style())
    log_layout = QtWidgets.QVBoxLayout(log_box)
    log_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    log_layout.setSpacing(Sizes.SPACING_SMALL)

    log_header = QtWidgets.QWidget(log_box)
    log_header_layout = QtWidgets.QHBoxLayout(log_header)
    log_header_layout.setContentsMargins(0, 0, 0, 0)
    log_header_layout.setSpacing(Sizes.SPACING_SMALL)
    log_header_layout.addWidget(QtWidgets.QLabel("进度事件：", log_header))
    log_header_layout.addStretch(1)
    clear_log_btn = QtWidgets.QPushButton("清空", log_header)
    clear_log_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    log_header_layout.addWidget(clear_log_btn)
    log_layout.addWidget(log_header)

    log_text = QtWidgets.QPlainTextEdit(log_box)
    log_text.setReadOnly(True)
    log_text.setPlaceholderText("（执行中会自动追加进度事件）")
    log_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    log_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    log_text.setMinimumHeight(140)
    log_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    log_layout.addWidget(log_text)
    step3_layout.addWidget(log_box, 1)

    result_box = QtWidgets.QGroupBox("结果摘要", step3_page)
    result_box.setStyleSheet(ThemeManager.group_box_style())
    result_layout = QtWidgets.QVBoxLayout(result_box)
    result_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM + 10, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
    result_layout.setSpacing(Sizes.SPACING_SMALL)

    result_header = QtWidgets.QWidget(result_box)
    result_header_layout = QtWidgets.QHBoxLayout(result_header)
    result_header_layout.setContentsMargins(0, 0, 0, 0)
    result_header_layout.setSpacing(Sizes.SPACING_SMALL)
    result_header_layout.addWidget(QtWidgets.QLabel("输出：", result_header))
    result_header_layout.addStretch(1)
    clear_result_btn = QtWidgets.QPushButton("清空", result_header)
    clear_result_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    result_header_layout.addWidget(clear_result_btn)
    result_layout.addWidget(result_header)

    result_text = QtWidgets.QPlainTextEdit(result_box)
    result_text.setReadOnly(True)
    result_text.setPlaceholderText("（执行完成后会在此显示结果摘要；失败也会显示错误堆栈）")
    result_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    result_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    result_text.setMinimumHeight(140)
    result_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    result_layout.addWidget(result_text)
    step3_layout.addWidget(result_box, 1)

    progress_row = QtWidgets.QWidget(step3_page)
    progress_row_layout = QtWidgets.QHBoxLayout(progress_row)
    progress_row_layout.setContentsMargins(0, 0, 0, 0)
    progress_row_layout.setSpacing(Sizes.SPACING_SMALL)
    progress_label = QtWidgets.QLabel("未开始。", progress_row)
    progress_label.setWordWrap(True)
    progress_label.setStyleSheet(ThemeManager.subtle_info_style())
    progress_bar = QtWidgets.QProgressBar(progress_row)
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)
    progress_row_layout.addWidget(progress_label, 1)
    progress_row_layout.addWidget(progress_bar, 2)
    step3_layout.addWidget(progress_row, 0)

    wizard_tabs.addTab(step3_page, "步骤3：执行")

    # footer
    btn_row, footer = build_export_center_footer(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        dialog=dialog,
        open_task_history_dialog=open_task_history_dialog,
        main_window=main_window,
    )
    root_layout.addLayout(cast(QtWidgets.QLayout, btn_row))

    # browse handler
    def _browse_input_file() -> None:
        task = str(task_combo.currentData() or IMPORT_TASK_GIL_FULL)
        if task == IMPORT_TASK_GIA:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(dialog, "选择 .gia 文件", "", "GIA (*.gia);;所有文件 (*)")
        else:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(dialog, "选择 .gil 文件", "", "GIL (*.gil);;所有文件 (*)")
        if not path:
            return
        input_path_edit.setText(str(Path(path).resolve()))

    input_browse_btn.clicked.connect(_browse_input_file)

    # assemble refs
    widgets = ImportCenterDialogWidgets(
        dialog=dialog,
        wizard_tabs=wizard_tabs,
        step1=ImportCenterStep1Widgets(
            task_combo=task_combo,
            input_path_edit=input_path_edit,
            input_browse_btn=input_browse_btn,
            target_mode_combo=target_mode_combo,
            package_name_edit=package_name_edit,
            existing_package_combo=existing_package_combo,
            overwrite_checkbox=overwrite_checkbox,
            overwrite_warning_label=overwrite_warning_label,
            enable_dll_dump_checkbox=enable_dll_dump_checkbox,
            generate_graph_code_checkbox=generate_graph_code_checkbox,
            validate_after_generate_checkbox=validate_after_generate_checkbox,
            gil_selected_parts_box=gil_selected_parts_box,
            export_node_graphs_cb=export_node_graphs_cb,
            export_templates_cb=export_templates_cb,
            export_instances_cb=export_instances_cb,
            export_struct_defs_cb=export_struct_defs_cb,
            export_signals_cb=export_signals_cb,
            export_combat_presets_cb=export_combat_presets_cb,
            export_section15_cb=export_section15_cb,
            export_raw_pyugc_cb=export_raw_pyugc_cb,
            export_data_blobs_cb=export_data_blobs_cb,
            gia_config_box=gia_config_box,
            gia_import_kind_combo=gia_import_kind_combo,
            gia_templates_cb=gia_templates_cb,
            gia_instances_cb=gia_instances_cb,
            gia_instances_mode_row=gia_instances_mode_row,
            gia_instances_mode_combo=gia_instances_mode_combo,
            gia_decode_depth_spin=gia_decode_depth_spin,
            gia_validate_after_import_cb=gia_validate_after_import_cb,
            preview_label=preview_label,
        ),
        step2=ImportCenterStep2Widgets(
            stacked=step2_stacked,
            default_preview_text=default_preview_text,
            gil_selected_page=gil_selected_page,
            gil_selected_scan_btn=gil_selected_scan_btn,
            gil_selected_select_all_btn=gil_selected_select_all_btn,
            gil_selected_unselect_all_btn=gil_selected_unselect_all_btn,
            gil_selected_scan_status_label=gil_selected_scan_status_label,
            gil_selected_graphs_list=gil_selected_graphs_list,
            gil_selected_preview_text=gil_selected_preview_text,
        ),
        step3=ImportCenterStep3Widgets(
            progress_label=progress_label,
            progress_bar=progress_bar,
            log_text=log_text,
            result_text=result_text,
            clear_log_btn=clear_log_btn,
            clear_result_btn=clear_result_btn,
        ),
        footer=footer,
    )

    preferred = str(preferred_task or "").strip()
    if preferred and preferred in set(IMPORT_TASKS):
        idx3 = int(task_combo.findData(preferred))
        if idx3 >= 0:
            task_combo.setCurrentIndex(int(idx3))

    wire_import_center_dialog(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        main_window=main_window,
        widgets=widgets,
        workspace_root=Path(workspace_root),
        packages_root=Path(packages_root),
        package_index_manager=package_index_manager,
        sanitize_package_id=sanitize_fn,
        template_package_dirname=str(template_package_dirname),
        importable_package_ids=list(importable_package_ids),
        existing_package_dirnames=list(existing_names),
        generate_unique_name=generate_unique_name,
        refresh_and_select_package=refresh_package_library_and_select_package,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
    )

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def _sanitize_new_package_dirname(*, sanitize_package_id: Any, raw_name: str) -> str:
    """将用户输入的项目存档名转换为可用目录名。"""
    raw = str(raw_name or "").strip()
    if raw == "":
        raw = "未命名项目存档"
    sanitized = str(sanitize_package_id(raw) or "").strip()
    return sanitized if sanitized != "" else "未命名项目存档"


def _compute_new_package_id(
    *,
    sanitize_package_id: Any,
    generate_unique_name_fn: Any,
    raw_name: str,
    existing_dirnames: list[str],
) -> str:
    """基于用户输入生成唯一的 package_id（目录名）。"""
    sanitized = _sanitize_new_package_dirname(sanitize_package_id=sanitize_package_id, raw_name=str(raw_name))
    return str(generate_unique_name_fn(str(sanitized), list(existing_dirnames)))

