from __future__ import annotations

from pathlib import Path
from typing import cast

from .._common import get_selected_package_id
from ..center_dialog_scaffold import (
    add_center_tabs,
    add_center_title_row,
    create_center_dialog_base,
    raise_existing_center_dialog,
)
from .controller import (
    SCOPE_PROJECT_AND_SHARED,
    SCOPE_PROJECT_ONLY,
    SCOPE_SHARED_ONLY,
    SEARCH_TYPE_AUTO,
    SEARCH_TYPE_COMPOSITE,
    SEARCH_TYPE_NODE,
    SEARCH_TYPE_PLACEHOLDER,
    SEARCH_TYPE_SIGNAL,
    wire_analysis_center_dialog,
)
from .dialog_types import (
    AnalysisCenterDialogWidgets,
    AnalysisCenterStep1Widgets,
    AnalysisCenterStep2Widgets,
    AnalysisCenterStep3Widgets,
)


DEFAULT_DIALOG_MIN_W: int = 1100
DEFAULT_DIALOG_MIN_H: int = 760
DEFAULT_DIALOG_FALLBACK_W: int = 1100
DEFAULT_DIALOG_FALLBACK_H: int = 760
DIALOG_SCALE_W: float = 0.94
DIALOG_SCALE_H: float = 0.90

STEP_TITLES: tuple[str, str, str] = ("步骤1：选择范围", "步骤2：搜索与结果", "步骤3：构建索引")


def open_analysis_center_dialog(main_window: object) -> None:
    """打开 ugc_file_tools 分析中心对话框。"""
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
    from ..export_history import append_task_history_entry, now_ts, open_task_history_dialog

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    app_state = getattr(main_window, "app_state", None)
    if app_state is None:
        raise RuntimeError("主窗口缺少 app_state，无法打开分析中心")

    workspace_root = Path(getattr(app_state, "workspace_path")).resolve()
    package_id = str(get_selected_package_id(main_window) or "").strip()
    if package_id in {"global_view", "unclassified_view"}:
        package_id = ""

    dialog_attr = "_ugc_file_tools_analysis_center_dialog"
    if raise_existing_center_dialog(QtWidgets=QtWidgets, main_window=main_window, dialog_attr=str(dialog_attr)):
        return

    base = create_center_dialog_base(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        main_window=main_window,
        dialog_attr=str(dialog_attr),
        object_name="ugc_file_tools_analysis_center_dialog",
        window_title="分析中心",
        min_w=int(DEFAULT_DIALOG_MIN_W),
        min_h=int(DEFAULT_DIALOG_MIN_H),
        fallback_w=int(DEFAULT_DIALOG_FALLBACK_W),
        fallback_h=int(DEFAULT_DIALOG_FALLBACK_H),
        scale_w=float(DIALOG_SCALE_W),
        scale_h=float(DIALOG_SCALE_H),
    )
    dialog = base.dialog
    root_layout = base.root_layout

    history_btn = QtWidgets.QPushButton("查看最近任务", dialog)
    history_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    history_btn.clicked.connect(lambda: open_task_history_dialog(main_window=main_window))
    add_center_title_row(
        QtWidgets=QtWidgets,
        ThemeManager=ThemeManager,
        base=base,
        title_text="分析中心",
        right_widgets=[history_btn],
    )

    tabs = add_center_tabs(QtWidgets=QtWidgets, base=base, min_height=None, document_mode=False)

    # ===== Step1 =====
    step1 = QtWidgets.QWidget(tabs)
    step1_layout = QtWidgets.QVBoxLayout(step1)
    step1_layout.setContentsMargins(0, 0, 0, 0)
    step1_layout.setSpacing(Sizes.SPACING_MEDIUM)

    package_label = QtWidgets.QLabel(f"当前 package_id：{package_id or '（未选中）'}", step1)
    package_label.setStyleSheet(ThemeManager.subtle_info_style())
    step1_layout.addWidget(package_label)

    scope_row = QtWidgets.QHBoxLayout()
    scope_row.addWidget(QtWidgets.QLabel("扫描范围：", step1))
    scope_combo = QtWidgets.QComboBox(step1)
    scope_combo.addItem("当前项目 + 共享", SCOPE_PROJECT_AND_SHARED)
    scope_combo.addItem("仅当前项目", SCOPE_PROJECT_ONLY)
    scope_combo.addItem("仅共享", SCOPE_SHARED_ONLY)
    scope_combo.setCurrentIndex(0)
    scope_row.addWidget(scope_combo, 1)
    step1_layout.addLayout(scope_row)

    scope_hint_label = QtWidgets.QLabel("提示：可在下方资源树中勾选要扫描的节点图；留空=扫描该范围内全部节点图。", step1)
    scope_hint_label.setStyleSheet(ThemeManager.subtle_info_style())
    step1_layout.addWidget(scope_hint_label)

    picker_host = QtWidgets.QWidget(step1)
    picker_host_layout = QtWidgets.QVBoxLayout(picker_host)
    picker_host_layout.setContentsMargins(0, 0, 0, 0)
    picker_host_layout.setSpacing(Sizes.SPACING_SMALL)
    step1_layout.addWidget(picker_host, 1)

    # ===== Step2 =====
    step2 = QtWidgets.QWidget(tabs)
    step2_layout = QtWidgets.QVBoxLayout(step2)
    step2_layout.setContentsMargins(0, 0, 0, 0)
    step2_layout.setSpacing(Sizes.SPACING_MEDIUM)

    hint_label = QtWidgets.QLabel("尚未构建索引。", step2)
    hint_label.setStyleSheet(ThemeManager.subtle_info_style())
    step2_layout.addWidget(hint_label)

    search_row = QtWidgets.QHBoxLayout()
    query_edit = QtWidgets.QLineEdit(step2)
    query_edit.setPlaceholderText("搜索：节点 title / node_def_ref.key / composite_id / 信号名（静态绑定）")
    type_combo = QtWidgets.QComboBox(step2)
    type_combo.addItem("自动", SEARCH_TYPE_AUTO)
    type_combo.addItem("节点", SEARCH_TYPE_NODE)
    type_combo.addItem("复合节点", SEARCH_TYPE_COMPOSITE)
    type_combo.addItem("信号", SEARCH_TYPE_SIGNAL)
    type_combo.addItem("占位符（ui_key/entity_key/component_key）", SEARCH_TYPE_PLACEHOLDER)
    copy_btn = QtWidgets.QPushButton("复制结果(JSON)", step2)
    copy_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    search_row.addWidget(query_edit, 1)
    search_row.addWidget(type_combo)
    search_row.addWidget(copy_btn)
    step2_layout.addLayout(search_row)

    summary_label = QtWidgets.QLabel("命中行数：0", step2)
    summary_label.setStyleSheet(ThemeManager.subtle_info_style())
    step2_layout.addWidget(summary_label)

    result_table = QtWidgets.QTableWidget(step2)
    result_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    result_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    result_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    result_table.setAlternatingRowColors(True)
    step2_layout.addWidget(result_table, 1)

    # ===== Step3 =====
    step3 = QtWidgets.QWidget(tabs)
    step3_layout = QtWidgets.QVBoxLayout(step3)
    step3_layout.setContentsMargins(0, 0, 0, 0)
    step3_layout.setSpacing(Sizes.SPACING_MEDIUM)

    btn_row = QtWidgets.QHBoxLayout()
    build_btn = QtWidgets.QPushButton("开始构建索引", step3)
    build_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    cancel_btn = QtWidgets.QPushButton("取消", step3)
    cancel_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    cancel_btn.setEnabled(False)
    btn_row.addWidget(build_btn)
    btn_row.addWidget(cancel_btn)
    btn_row.addStretch(1)
    step3_layout.addLayout(btn_row)

    progress_bar = QtWidgets.QProgressBar(step3)
    progress_label = QtWidgets.QLabel("未开始", step3)
    step3_layout.addWidget(progress_bar)
    step3_layout.addWidget(progress_label)

    log_text = QtWidgets.QPlainTextEdit(step3)
    log_text.setReadOnly(True)
    log_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    log_text.setPlaceholderText("日志（可复制）")
    step3_layout.addWidget(log_text, 1)

    failures_text = QtWidgets.QPlainTextEdit(step3)
    failures_text.setReadOnly(True)
    failures_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    failures_text.setPlaceholderText("失败清单（可复制）")
    step3_layout.addWidget(failures_text, 1)

    tabs.addTab(step1, STEP_TITLES[0])
    tabs.addTab(step2, STEP_TITLES[1])
    tabs.addTab(step3, STEP_TITLES[2])

    widgets = AnalysisCenterDialogWidgets(
        tabs=tabs,
        step1=AnalysisCenterStep1Widgets(
            scope_combo=scope_combo,
            package_id_label=package_label,
            scope_hint_label=scope_hint_label,
            picker_host=picker_host,
        ),
        step2=AnalysisCenterStep2Widgets(
            query_edit=query_edit,
            type_combo=type_combo,
            result_table=result_table,
            summary_label=summary_label,
            hint_label=hint_label,
            copy_btn=copy_btn,
        ),
        step3=AnalysisCenterStep3Widgets(
            build_btn=build_btn,
            cancel_btn=cancel_btn,
            progress_bar=progress_bar,
            progress_label=progress_label,
            log_text=log_text,
            failures_text=failures_text,
        ),
    )

    wire_analysis_center_dialog(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        main_window=main_window,
        widgets=widgets,
        workspace_root=workspace_root,
        package_id=package_id,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
    )

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

