from __future__ import annotations

from pathlib import Path

from .export_center.state import (
    _load_last_base_gil_path,
    _load_last_base_player_template_gia_path,
    _load_last_export_format,
    _load_last_repair_input_gil_path,
    _load_last_use_builtin_empty_base_gil,
)
from .export_center_dialog_types import (
    ExportCenterAnalysisTab,
    ExportCenterBackfillPanel,
    ExportCenterExecuteTab,
    ExportCenterGiaPage,
    ExportCenterGilPage,
    ExportCenterRepairPage,
    ExportCenterRightPane,
)


def build_export_center_right_pane(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    workspace_root: Path,
    package_id: str,
) -> ExportCenterRightPane:
    from ugc_file_tools.beyond_local_export import get_beyond_local_export_dir

    config_pane = QtWidgets.QWidget()
    config_layout = QtWidgets.QVBoxLayout(config_pane)
    config_layout.setContentsMargins(0, 0, 0, 0)
    config_layout.setSpacing(Sizes.SPACING_MEDIUM)

    # 右侧配置列：宽度由外层 splitter 控制，不设 maxWidth 以允许用户拖宽。
    # 设 minWidth 保证 GIL 写回配置行（label + QLineEdit + 浏览按钮）始终可见（避免首次打开就要拖拽分割条）。
    config_column = QtWidgets.QWidget(config_pane)
    config_column.setMinimumWidth(520)
    config_column_layout = QtWidgets.QVBoxLayout(config_column)
    config_column_layout.setContentsMargins(0, 0, 0, 0)
    config_column_layout.setSpacing(Sizes.SPACING_MEDIUM)

    format_group = QtWidgets.QGroupBox("输出格式", config_column)
    format_group.setStyleSheet(ThemeManager.group_box_style())
    format_group_layout = QtWidgets.QVBoxLayout(format_group)
    format_group_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )

    format_combo = QtWidgets.QComboBox(format_group)
    format_combo.addItem("导出 .gia", "gia")
    format_combo.addItem("导出 .gil", "gil")
    format_combo.addItem("修复信号", "repair_signals")
    format_combo.addItem("合并信号条目", "merge_signal_entries")
    format_combo.setToolTip(
        "导出 .gia：标准模组导出格式\n"
        "导出 .gil：用于将改动写回现有项目文件\n"
        "修复信号：基于所选节点图导出的 .gia 自动修复目标 .gil 的信号重复/串号/残留\n"
        "合并信号条目：显式指定 keep/remove 信号名，合并两条 signal entry 并重绑引用（适合处理导入后生成的 信号_3 等占位符）"
    )
    format_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    format_combo.setMinimumContentsLength(10)
    last_fmt = _load_last_export_format(workspace_root=Path(workspace_root))
    if last_fmt != "":
        idx = int(format_combo.findData(str(last_fmt)))
        if idx >= 0:
            format_combo.setCurrentIndex(idx)
    format_group_layout.addWidget(format_combo)

    format_desc = QtWidgets.QLabel("", format_group)
    format_desc.setWordWrap(True)
    format_desc.setStyleSheet(ThemeManager.subtle_info_style())
    format_group_layout.addWidget(format_desc)

    def _update_format_desc() -> None:
        fmt = str(format_combo.currentData() or "")
        if fmt == "gia":
            format_desc.setText("导出为标准模组格式（.gia）。适合分发/导入；可选 UIKey 回填、注入、bundle 等高级选项。")
        elif fmt == "gil":
            format_desc.setText("基于基地 .gil 执行选择式写回导出（.gil）。适合把项目存档的变更回写到真源文件。")
        elif fmt == "repair_signals":
            format_desc.setText("基于所选节点图导出的临时 .gia，对目标 .gil 执行信号修复（去重/重绑/清理残留）。不会覆盖原文件。")
        elif fmt == "merge_signal_entries":
            format_desc.setText("显式合并两条 signal entry（keep/remove，可选重命名 keep），并重绑节点图引用（不会覆盖原文件）。")
        else:
            format_desc.setText("")

    format_combo.currentIndexChanged.connect(_update_format_desc)
    _update_format_desc()

    config_column_layout.addWidget(format_group)

    # 右侧配置内容可能很长（尤其是 GIL 模式），若直接堆叠在对话框中会把最小高度撑得很大，
    # 导致用户无法把对话框“缩短”。这里将格式配置页放入滚动区，保证窗口可自由调整高度。
    pages_scroll = QtWidgets.QScrollArea(config_column)
    pages_scroll.setWidgetResizable(True)
    pages_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    pages_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    pages_scroll.setStyleSheet(
        """
        QScrollArea { background: transparent; border: none; }
        QScrollArea > QWidget { background: transparent; }
        QScrollArea > QWidget > QWidget { background: transparent; }
        """
    )

    stacked = QtWidgets.QStackedWidget()
    pages_scroll.setWidget(stacked)
    config_column_layout.addWidget(pages_scroll, 1)
    config_layout.addWidget(config_column, 1)

    gia = _build_gia_page(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        default_copy_dir=Path(get_beyond_local_export_dir()).resolve(),
        stacked=stacked,
    )
    gil = _build_gil_page(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
        dialog_parent=config_pane,
        stacked=stacked,
    )
    repair = _build_repair_page(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        workspace_root=Path(workspace_root),
        stacked=stacked,
    )

    # Step2/3 页由外层向导 tabs 承载；这里仅构建并返回 widget refs
    analysis = _build_analysis_tab(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        parent=None,
    )

    execute = _build_execute_tab(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        parent=None,
    )
    return ExportCenterRightPane(
        config_pane=config_pane,
        analysis=analysis,
        execute=execute,
        format_combo=format_combo,
        format_desc=format_desc,
        stacked=stacked,
        gia=gia,
        gil=gil,
        repair=repair,
    )


def _build_analysis_tab(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    parent: object,
) -> ExportCenterAnalysisTab:
    container = QtWidgets.QWidget(parent)
    container_layout = QtWidgets.QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(Sizes.SPACING_SMALL)

    scroll = QtWidgets.QScrollArea(container)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setStyleSheet(
        """
        QScrollArea { background: transparent; border: none; }
        QScrollArea > QWidget { background: transparent; }
        QScrollArea > QWidget > QWidget { background: transparent; }
        """
    )

    page = QtWidgets.QWidget(scroll)
    scroll.setWidget(page)
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Sizes.SPACING_MEDIUM)

    strategy_box = QtWidgets.QGroupBox("来源与处理策略（重要）", page)
    strategy_box.setStyleSheet(ThemeManager.group_box_style())
    strategy_layout = QtWidgets.QVBoxLayout(strategy_box)
    strategy_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    strategy_layout.setSpacing(Sizes.SPACING_SMALL)

    strategy_text = QtWidgets.QPlainTextEdit(strategy_box)
    strategy_text.setReadOnly(True)
    strategy_text.setPlaceholderText("请先在“步骤1：配置”选择输出格式与参考文件。")
    strategy_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    strategy_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    strategy_text.setMaximumHeight(160)
    strategy_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    strategy_layout.addWidget(strategy_text)
    # 导出中心回填分析页：不展示“来源与处理策略（重要）”区块（避免占用过多空间）。
    strategy_box.setVisible(False)

    backfill_panel = _build_backfill_panel(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        parent=page,
        footer_parent=container,
        title="回填依赖与识别对比（基于 .gil）",
    )
    layout.addWidget(backfill_panel.box, 1)

    container_layout.addWidget(scroll, 1)
    container_layout.addWidget(backfill_panel.progress_row, 0)

    return ExportCenterAnalysisTab(
        page=container,
        strategy_text=strategy_text,
        backfill_panel=backfill_panel,
    )


def _build_execute_tab(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    parent: object,
) -> ExportCenterExecuteTab:
    container = QtWidgets.QWidget(parent)
    container_layout = QtWidgets.QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(Sizes.SPACING_SMALL)

    scroll = QtWidgets.QScrollArea(container)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setStyleSheet(
        """
        QScrollArea { background: transparent; border: none; }
        QScrollArea > QWidget { background: transparent; }
        QScrollArea > QWidget > QWidget { background: transparent; }
        """
    )

    page = QtWidgets.QWidget(scroll)
    scroll.setWidget(page)
    layout = QtWidgets.QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Sizes.SPACING_MEDIUM)

    # 执行页不展示“计划预览/提示文案”，但保留 widget ref 以兼容 controller/测试契约。
    plan_preview_text = QtWidgets.QPlainTextEdit(container)
    plan_preview_text.setReadOnly(True)
    plan_preview_text.setPlaceholderText("（执行页已隐藏计划预览）")
    plan_preview_text.setVisible(False)

    run_btn = QtWidgets.QPushButton("开始导出", container)
    run_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    run_btn.setDefault(False)
    # 导出中心交互约束：执行动作统一由 footer 的“下一步→开始导出/开始修复”按钮承载。
    # 这里保留一个隐藏按钮仅作为内部 widget ref（便于复用既有 controller/测试契约），避免在页面内出现两个“开始”入口。
    run_btn.setVisible(False)
    run_btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {Colors.PRIMARY};
            color: {Colors.TEXT_ON_PRIMARY};
            border: none;
            padding: 6px 20px;
            border-radius: 4px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {Colors.PRIMARY_DARK};
        }}
        QPushButton:pressed {{
            background-color: {Colors.PRIMARY_DARK};
        }}
        QPushButton:disabled {{
            background-color: {Colors.BG_DISABLED};
            color: {Colors.TEXT_DISABLED};
        }}
    """)

    log_box = QtWidgets.QGroupBox("执行日志（摘要）", page)
    log_box.setStyleSheet(ThemeManager.group_box_style())
    log_layout = QtWidgets.QVBoxLayout(log_box)
    log_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
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
    log_text.setMinimumHeight(120)
    log_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    log_layout.addWidget(log_text)
    layout.addWidget(log_box)

    result_box = QtWidgets.QGroupBox("结果摘要", page)
    result_box.setStyleSheet(ThemeManager.group_box_style())
    result_layout = QtWidgets.QVBoxLayout(result_box)
    result_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
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
    result_text.setPlaceholderText("（执行完成后会在此显示输出路径与摘要）")
    result_text.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
    result_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    result_text.setMinimumHeight(120)
    result_text.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY};"
        f"background-color: {Colors.BG_MAIN};"
        f"border: 1px solid {Colors.BORDER_LIGHT};"
        "border-radius: 4px;"
        "font-size: 11px;"
    )
    result_layout.addWidget(result_text)
    layout.addWidget(result_box)

    layout.addStretch(1)

    # 底部固定执行进度（不随滚动）
    progress_row = QtWidgets.QWidget(container)
    progress_row_layout = QtWidgets.QHBoxLayout(progress_row)
    progress_row_layout.setContentsMargins(0, 0, 0, 0)
    progress_row_layout.setSpacing(Sizes.SPACING_SMALL)

    progress_label = QtWidgets.QLabel("", progress_row)
    progress_label.setWordWrap(True)
    progress_label.setStyleSheet(ThemeManager.subtle_info_style())
    progress_label.setText("未开始。")

    progress_bar = QtWidgets.QProgressBar(progress_row)
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)

    progress_row_layout.addWidget(progress_label, 1)
    progress_row_layout.addWidget(progress_bar, 2)

    container_layout.addWidget(scroll, 1)
    container_layout.addWidget(progress_row, 0)

    return ExportCenterExecuteTab(
        page=container,
        plan_preview_text=plan_preview_text,
        run_btn=run_btn,
        progress_label=progress_label,
        progress_bar=progress_bar,
        log_text=log_text,
        result_text=result_text,
        clear_log_btn=clear_log_btn,
        clear_result_btn=clear_result_btn,
    )


def _build_backfill_panel(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    parent: object,
    footer_parent: object,
    title: str,
) -> ExportCenterBackfillPanel:
    box = QtWidgets.QGroupBox(str(title), parent)
    box.setStyleSheet(ThemeManager.group_box_style())
    box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
    layout = QtWidgets.QVBoxLayout(box)
    layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    layout.setSpacing(Sizes.SPACING_SMALL)

    action_row = QtWidgets.QWidget(box)
    action_layout = QtWidgets.QHBoxLayout(action_row)
    action_layout.setContentsMargins(0, 0, 0, 0)
    action_layout.setSpacing(Sizes.SPACING_SMALL)

    target_label = QtWidgets.QLabel("", action_row)
    target_label.setWordWrap(True)
    target_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")

    identify_btn = QtWidgets.QPushButton("识别", action_row)
    identify_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    identify_btn.setEnabled(False)

    action_layout.addWidget(target_label, 1)
    action_layout.addWidget(identify_btn)
    layout.addWidget(action_row)

    tabs = QtWidgets.QTabWidget(box)
    tabs.setDocumentMode(True)
    tabs.setStyleSheet("QTabWidget::pane { border: none; }")
    tabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)

    def _mk_table(tab_parent: object) -> object:
        table = QtWidgets.QTableWidget(tab_parent)
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["类别", "依赖项", "值(来自GIL)", "状态", "备注"])
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.setMinimumHeight(420)
        return table

    missing_tab = QtWidgets.QWidget(tabs)
    missing_layout = QtWidgets.QVBoxLayout(missing_tab)
    missing_layout.setContentsMargins(0, 0, 0, 0)
    missing_layout.setSpacing(0)
    missing_table = _mk_table(missing_tab)
    missing_layout.addWidget(missing_table)

    ready_tab = QtWidgets.QWidget(tabs)
    ready_layout = QtWidgets.QVBoxLayout(ready_tab)
    ready_layout.setContentsMargins(0, 0, 0, 0)
    ready_layout.setSpacing(0)
    ready_table = _mk_table(ready_tab)
    ready_layout.addWidget(ready_table)

    tabs.addTab(missing_tab, "缺失/待修复 (0)")
    tabs.addTab(ready_tab, "已就绪 (0)")
    layout.addWidget(tabs, 1)

    # 底部固定进度条（不随滚动）
    progress_row = QtWidgets.QWidget(footer_parent)
    progress_layout = QtWidgets.QHBoxLayout(progress_row)
    progress_layout.setContentsMargins(0, 0, 0, 0)
    progress_layout.setSpacing(Sizes.SPACING_SMALL)

    progress_label = QtWidgets.QLabel("", progress_row)
    progress_label.setWordWrap(True)
    progress_label.setStyleSheet(ThemeManager.subtle_info_style())
    progress_label.setText("")

    progress_bar = QtWidgets.QProgressBar(progress_row)
    progress_bar.setRange(0, 1)
    progress_bar.setValue(0)

    progress_layout.addWidget(progress_label, 1)
    progress_layout.addWidget(progress_bar, 2)
    progress_row.setVisible(False)

    return ExportCenterBackfillPanel(
        box=box,
        target_label=target_label,
        identify_btn=identify_btn,
        tabs=tabs,
        missing_table=missing_table,
        ready_table=ready_table,
        progress_row=progress_row,
        progress_label=progress_label,
        progress_bar=progress_bar,
    )


def _build_gia_page(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    workspace_root: Path,
    package_id: str,
    default_copy_dir: Path,
    stacked: object,
) -> ExportCenterGiaPage:
    gia_page = QtWidgets.QWidget(stacked)
    gia_layout = QtWidgets.QVBoxLayout(gia_page)
    gia_layout.setContentsMargins(0, 0, 0, 0)
    gia_layout.setSpacing(Sizes.SPACING_MEDIUM)

    gia_basic_group = QtWidgets.QGroupBox("基本设置", gia_page)
    gia_basic_group.setStyleSheet(ThemeManager.group_box_style())
    gia_form = QtWidgets.QFormLayout(gia_basic_group)
    gia_form.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    gia_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    gia_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    gia_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

    out_dir_edit = QtWidgets.QLineEdit(gia_page)
    out_dir_edit.setPlaceholderText(f"默认为 {package_id}_export")
    out_dir_edit.setText(f"{package_id}_export")
    out_dir_edit.setMaximumWidth(360)
    gia_form.addRow("输出子目录:", out_dir_edit)

    copy_row = QtWidgets.QWidget(gia_page)
    copy_layout = QtWidgets.QHBoxLayout(copy_row)
    copy_layout.setContentsMargins(0, 0, 0, 0)
    copy_layout.setSpacing(Sizes.SPACING_SMALL)

    copy_dir_edit = QtWidgets.QLineEdit(copy_row)
    copy_dir_edit.setPlaceholderText("可选：复制到指定目录...")
    copy_dir_edit.setText(str(default_copy_dir))

    copy_browse_btn = QtWidgets.QPushButton("浏览...", copy_row)
    copy_browse_btn.setFixedWidth(60)
    copy_browse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    copy_browse_btn.clicked.connect(
        lambda: (
            (lambda d: copy_dir_edit.setText(str(Path(d).resolve())) if d else None)(
                QtWidgets.QFileDialog.getExistingDirectory(gia_page, "选择复制目录", "")
            )
        )
    )
    copy_layout.addWidget(copy_dir_edit, 1)
    copy_layout.addWidget(copy_browse_btn)
    gia_form.addRow("复制到:", copy_row)

    base_gil_row = QtWidgets.QWidget(gia_page)
    base_gil_layout = QtWidgets.QHBoxLayout(base_gil_row)
    base_gil_layout.setContentsMargins(0, 0, 0, 0)
    base_gil_layout.setSpacing(Sizes.SPACING_SMALL)

    base_gil_edit = QtWidgets.QLineEdit(base_gil_row)
    base_gil_edit.setPlaceholderText("可选：基底 .gil（用于节点图 entity_key/component_key 占位符回填）")
    last_base_gil_path = _load_last_base_gil_path(workspace_root=Path(workspace_root))
    if last_base_gil_path != "":
        base_gil_edit.setText(str(last_base_gil_path))

    base_gil_browse_btn = QtWidgets.QPushButton("浏览...", base_gil_row)
    base_gil_browse_btn.setFixedWidth(60)
    base_gil_browse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    base_gil_browse_btn.clicked.connect(
        lambda: (
            (lambda p: base_gil_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gia_page, "选择基底文件（.gil）", "", "GIL (*.gil)")[0]
            )
        )
    )

    base_gil_clear_btn = QtWidgets.QPushButton("清空", base_gil_row)
    base_gil_clear_btn.setFixedWidth(60)
    base_gil_clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    base_gil_clear_btn.clicked.connect(lambda: base_gil_edit.setText(""))

    base_gil_layout.addWidget(base_gil_edit, 1)
    base_gil_layout.addWidget(base_gil_browse_btn)
    base_gil_layout.addWidget(base_gil_clear_btn)
    base_gil_row.setVisible(False)
    gia_form.addRow("基底 .gil:", base_gil_row)

    player_template_base_gia_row = QtWidgets.QWidget(gia_page)
    player_template_base_gia_layout = QtWidgets.QHBoxLayout(player_template_base_gia_row)
    player_template_base_gia_layout.setContentsMargins(0, 0, 0, 0)
    player_template_base_gia_layout.setSpacing(Sizes.SPACING_SMALL)

    player_template_base_gia_edit = QtWidgets.QLineEdit(player_template_base_gia_row)
    player_template_base_gia_edit.setPlaceholderText("必选：玩家模板 base .gia（player_template.gia；用于结构克隆）")
    player_template_base_gia_edit.setToolTip(
        "说明：玩家模板导出采用 template-driven（基于真源导出的 base 玩家模板 .gia 克隆结构再补丁）。"
    )
    last_player_template_base_gia_path = _load_last_base_player_template_gia_path(workspace_root=Path(workspace_root))
    if last_player_template_base_gia_path != "":
        player_template_base_gia_edit.setText(str(last_player_template_base_gia_path))
    player_template_base_gia_browse_btn = QtWidgets.QPushButton("浏览...", player_template_base_gia_row)
    player_template_base_gia_browse_btn.setFixedWidth(60)
    player_template_base_gia_browse_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    player_template_base_gia_browse_btn.clicked.connect(
        lambda: (
            (lambda p: player_template_base_gia_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gia_page, "选择玩家模板 base .gia", "", "GIA (*.gia)")[0]
            )
        )
    )

    player_template_base_gia_clear_btn = QtWidgets.QPushButton("清空", player_template_base_gia_row)
    player_template_base_gia_clear_btn.setFixedWidth(60)
    player_template_base_gia_clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    player_template_base_gia_clear_btn.clicked.connect(lambda: player_template_base_gia_edit.setText(""))

    player_template_base_gia_layout.addWidget(player_template_base_gia_edit, 1)
    player_template_base_gia_layout.addWidget(player_template_base_gia_browse_btn)
    player_template_base_gia_layout.addWidget(player_template_base_gia_clear_btn)
    player_template_base_gia_row.setVisible(False)
    gia_form.addRow("玩家模板 base .gia:", player_template_base_gia_row)

    gia_layout.addWidget(gia_basic_group)

    gia_advanced_toggle = QtWidgets.QCheckBox("显示高级选项", gia_page)
    gia_layout.addWidget(gia_advanced_toggle)

    gia_advanced_box = QtWidgets.QGroupBox("高级选项", gia_page)
    gia_advanced_box.setVisible(False)
    gia_advanced_box.setStyleSheet(ThemeManager.group_box_style())

    gia_adv_layout = QtWidgets.QVBoxLayout(gia_advanced_box)
    gia_adv_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    gia_adv_layout.setSpacing(Sizes.SPACING_SMALL)

    allow_unresolved_ui_keys_cb = QtWidgets.QCheckBox("允许缺失 UIKey (回填为 0)", gia_advanced_box)
    gia_adv_layout.addWidget(allow_unresolved_ui_keys_cb)

    ui_export_record_row = QtWidgets.QWidget(gia_advanced_box)
    ui_export_record_layout = QtWidgets.QVBoxLayout(ui_export_record_row)
    ui_export_record_layout.setContentsMargins(0, 0, 0, 0)
    ui_export_record_layout.setSpacing(Sizes.SPACING_SMALL)

    ui_label_row = QtWidgets.QHBoxLayout()
    ui_label = QtWidgets.QLabel("UI 回填记录:", ui_export_record_row)
    ui_export_record_combo = QtWidgets.QComboBox(ui_export_record_row)
    ui_label_row.addWidget(ui_label)
    ui_label_row.addWidget(ui_export_record_combo, 1)
    ui_export_record_layout.addLayout(ui_label_row)

    ui_export_record_detail = QtWidgets.QLabel("", ui_export_record_row)
    ui_export_record_detail.setWordWrap(True)
    ui_export_record_detail.setStyleSheet(
        f"color: {Colors.TEXT_SECONDARY}; font-size: 11px; margin-left: 10px;"
    )
    ui_export_record_layout.addWidget(ui_export_record_detail)
    ui_export_record_row.setVisible(False)
    gia_adv_layout.addWidget(ui_export_record_row)

    gia_id_ref_row = QtWidgets.QWidget(gia_advanced_box)
    gia_id_ref_layout = QtWidgets.QHBoxLayout(gia_id_ref_row)
    gia_id_ref_layout.setContentsMargins(0, 0, 0, 0)
    gia_id_ref_layout.setSpacing(Sizes.SPACING_SMALL)
    gia_id_ref_label = QtWidgets.QLabel("占位符参考:", gia_id_ref_row)
    gia_id_ref_label.setMinimumWidth(90)
    gia_id_ref_edit = QtWidgets.QLineEdit(gia_id_ref_row)
    gia_id_ref_edit.setPlaceholderText("可选：占位符参考 .gil（用于 entity_key/component_key 回填）")
    gia_id_ref_browse = QtWidgets.QPushButton("浏览...", gia_id_ref_row)
    gia_id_ref_browse.setFixedWidth(60)
    gia_id_ref_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gia_id_ref_browse.clicked.connect(
        lambda: (
            (lambda p: gia_id_ref_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gia_page, "选择占位符参考文件（.gil）", "", "GIL (*.gil)")[0]
            )
        )
    )
    gia_id_ref_clear = QtWidgets.QPushButton("清空", gia_id_ref_row)
    gia_id_ref_clear.setFixedWidth(60)
    gia_id_ref_clear.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gia_id_ref_clear.clicked.connect(lambda: gia_id_ref_edit.setText(""))
    gia_id_ref_layout.addWidget(gia_id_ref_label)
    gia_id_ref_layout.addWidget(gia_id_ref_edit, 1)
    gia_id_ref_layout.addWidget(gia_id_ref_browse)
    gia_id_ref_layout.addWidget(gia_id_ref_clear)
    gia_id_ref_row.setVisible(False)
    gia_adv_layout.addWidget(gia_id_ref_row)

    bundle_enabled_cb = QtWidgets.QCheckBox("导出 Bundle (包含管理配置)", gia_advanced_box)
    gia_adv_layout.addWidget(bundle_enabled_cb)

    bundle_sub_layout = QtWidgets.QVBoxLayout()
    bundle_sub_layout.setContentsMargins(20, 0, 0, 0)
    bundle_include_signals_cb = QtWidgets.QCheckBox("包含信号定义", gia_advanced_box)
    bundle_include_ui_guid_cb = QtWidgets.QCheckBox("包含 UI GUID 映射", gia_advanced_box)
    bundle_include_ui_guid_cb.setChecked(True)
    bundle_sub_layout.addWidget(bundle_include_signals_cb)
    bundle_sub_layout.addWidget(bundle_include_ui_guid_cb)
    gia_adv_layout.addLayout(bundle_sub_layout)

    pack_graphs_cb = QtWidgets.QCheckBox("打包合并 (.gia)", gia_advanced_box)
    gia_adv_layout.addWidget(pack_graphs_cb)

    pack_name_edit = QtWidgets.QLineEdit(gia_advanced_box)
    pack_name_edit.setPlaceholderText(f"可选：打包文件名（留空=默认 {package_id}_packed_graphs.gia）")
    pack_name_edit.setContentsMargins(20, 0, 0, 0)
    gia_adv_layout.addWidget(pack_name_edit)

    templates_sep = QtWidgets.QFrame()
    templates_sep.setFrameShape(QtWidgets.QFrame.Shape.HLine)
    templates_sep.setStyleSheet(f"color: {Colors.BORDER_LIGHT};")
    gia_adv_layout.addWidget(templates_sep)

    templates_label = QtWidgets.QLabel("元件设置", gia_advanced_box)
    templates_label.setStyleSheet("font-weight: bold;")
    gia_adv_layout.addWidget(templates_label)

    tpl_form = QtWidgets.QFormLayout()
    tpl_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)

    base_gia_row = QtWidgets.QWidget(gia_advanced_box)
    base_gia_layout = QtWidgets.QHBoxLayout(base_gia_row)
    base_gia_layout.setContentsMargins(0, 0, 0, 0)
    base_gia_edit = QtWidgets.QLineEdit(base_gia_row)
    base_gia_edit.setPlaceholderText("可选：元件模板 base .gia（仅模板导出链路使用）")
    base_gia_edit.setToolTip("提示：节点图的 entity_key/component_key 占位符回填只读取 .gil。\n请在“基本设置 → 基底 .gil”里选择。")
    base_gia_browse = QtWidgets.QPushButton("...", base_gia_row)
    base_gia_browse.setFixedWidth(30)
    base_gia_browse.clicked.connect(
        lambda: (
            (lambda p: base_gia_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gia_page, "选择 base .gia", "", "GIA (*.gia)")[0]
            )
        )
    )
    base_gia_layout.addWidget(base_gia_edit, 1)
    base_gia_layout.addWidget(base_gia_browse)
    tpl_form.addRow("模板 base .gia:", base_gia_row)

    decode_depth_spin = QtWidgets.QSpinBox(gia_advanced_box)
    decode_depth_spin.setRange(4, 64)
    decode_depth_spin.setValue(24)
    tpl_form.addRow("Decode 深度:", decode_depth_spin)

    gia_adv_layout.addLayout(tpl_form)
    gia_layout.addWidget(gia_advanced_box)
    gia_layout.addStretch(1)

    stacked.addWidget(gia_page)

    return ExportCenterGiaPage(
        page=gia_page,
        out_dir_edit=out_dir_edit,
        copy_dir_edit=copy_dir_edit,
        base_gil_row=base_gil_row,
        base_gil_edit=base_gil_edit,
        player_template_base_gia_row=player_template_base_gia_row,
        player_template_base_gia_edit=player_template_base_gia_edit,
        gia_advanced_toggle=gia_advanced_toggle,
        gia_advanced_box=gia_advanced_box,
        allow_unresolved_ui_keys_cb=allow_unresolved_ui_keys_cb,
        ui_export_record_row=ui_export_record_row,
        ui_export_record_combo=ui_export_record_combo,
        ui_export_record_detail=ui_export_record_detail,
        gia_id_ref_row=gia_id_ref_row,
        gia_id_ref_edit=gia_id_ref_edit,
        bundle_enabled_cb=bundle_enabled_cb,
        bundle_include_signals_cb=bundle_include_signals_cb,
        bundle_include_ui_guid_cb=bundle_include_ui_guid_cb,
        pack_graphs_cb=pack_graphs_cb,
        pack_name_edit=pack_name_edit,
        base_gia_edit=base_gia_edit,
        decode_depth_spin=decode_depth_spin,
    )


def _build_gil_page(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    workspace_root: Path,
    package_id: str,
    dialog_parent: object,
    stacked: object,
) -> ExportCenterGilPage:
    gil_page = QtWidgets.QWidget(stacked)
    gil_layout = QtWidgets.QVBoxLayout(gil_page)
    gil_layout.setContentsMargins(0, 0, 0, 0)
    gil_layout.setSpacing(Sizes.SPACING_MEDIUM)

    gil_settings_box = QtWidgets.QGroupBox("写回配置", gil_page)
    gil_settings_box.setStyleSheet(ThemeManager.group_box_style())
    gil_grid = QtWidgets.QGridLayout(gil_settings_box)
    gil_grid.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    gil_grid.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    gil_grid.setVerticalSpacing(Sizes.SPACING_MEDIUM)
    gil_grid.setColumnStretch(1, 1)
    gil_grid.setColumnStretch(3, 1)
    _r = 0

    input_row = QtWidgets.QWidget(gil_page)
    input_layout = QtWidgets.QHBoxLayout(input_row)
    input_layout.setContentsMargins(0, 0, 0, 0)
    input_layout.setSpacing(Sizes.SPACING_SMALL)
    input_gil_edit = QtWidgets.QLineEdit(input_row)
    input_gil_edit.setPlaceholderText("选择基础 .gil...")
    last_base_gil_path = _load_last_base_gil_path(workspace_root=Path(workspace_root))
    if last_base_gil_path != "":
        input_gil_edit.setText(str(last_base_gil_path))
    input_browse = QtWidgets.QPushButton("浏览", input_row)
    input_browse.setFixedWidth(60)
    input_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    input_browse.clicked.connect(
        lambda: (
            (lambda p: input_gil_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gil_page, "选择基础 .gil", "", "GIL (*.gil)")[0]
            )
        )
    )
    input_layout.addWidget(input_gil_edit, 1)
    input_layout.addWidget(input_browse)
    lb_input = QtWidgets.QLabel("基础文件:", gil_settings_box)
    lb_input.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_grid.addWidget(lb_input, _r, 0)
    gil_grid.addWidget(input_row, _r, 1, 1, 3)

    # --- 内置空存档 base ---
    builtin_row = QtWidgets.QWidget(gil_page)
    builtin_layout = QtWidgets.QVBoxLayout(builtin_row)
    builtin_layout.setContentsMargins(0, 0, 0, 0)
    builtin_layout.setSpacing(2)

    use_builtin_empty_base_cb = QtWidgets.QCheckBox("使用内置空存档（默认布局）", builtin_row)
    use_builtin_empty_base_cb.setToolTip(
        "勾选后无需选择基础 .gil。\n"
        "工具会以程序内置的“空存档（仅默认布局）”作为 base 进行增量写回导出。"
    )
    use_builtin_empty_base_cb.setChecked(bool(_load_last_use_builtin_empty_base_gil(workspace_root=Path(workspace_root))))
    builtin_hint = QtWidgets.QLabel(
        "提示：该模式用于“导出为空存档”（在空存档的基础上写回你勾选的资源）。",
        builtin_row,
    )
    builtin_hint.setWordWrap(True)
    builtin_hint.setStyleSheet(ThemeManager.subtle_info_style())
    builtin_layout.addWidget(use_builtin_empty_base_cb)
    builtin_layout.addWidget(builtin_hint)

    _r = _r + 1
    lb_builtin = QtWidgets.QLabel("空存档:", gil_settings_box)
    lb_builtin.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignTop)
    gil_grid.addWidget(lb_builtin, _r, 0)
    gil_grid.addWidget(builtin_row, _r, 1, 1, 3)

    recent_row = QtWidgets.QWidget(gil_page)
    recent_layout = QtWidgets.QHBoxLayout(recent_row)
    recent_layout.setContentsMargins(0, 0, 0, 0)
    recent_combo = QtWidgets.QComboBox(recent_row)
    recent_use_btn = QtWidgets.QPushButton("使用", recent_row)
    recent_use_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    recent_refresh_btn = QtWidgets.QPushButton("刷新", recent_row)
    recent_refresh_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    recent_layout.addWidget(recent_combo, 1)
    recent_layout.addWidget(recent_use_btn)
    recent_layout.addWidget(recent_refresh_btn)
    _r = _r + 1
    lb_recent = QtWidgets.QLabel("最近导出:", gil_settings_box)
    lb_recent.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_grid.addWidget(lb_recent, _r, 0)
    gil_grid.addWidget(recent_row, _r, 1, 1, 3)

    def _load_recent_gils_into_combo() -> None:
        from ugc_file_tools.recent_artifacts import load_recent_exported_gils

        recent_combo.clear()
        recent_combo.addItem("（选择最近导出的 .gil）", "")
        items = load_recent_exported_gils(workspace_root=Path(workspace_root), keep_missing=False, limit=12)
        for it in items:
            label = f"{it.ts}  {Path(it.path).name}"
            recent_combo.addItem(label, str(it.path))

    def _use_selected_recent() -> None:
        p = str(recent_combo.currentData() or "").strip()
        if p:
            input_gil_edit.setText(str(Path(p).resolve()))

    recent_use_btn.clicked.connect(_use_selected_recent)
    recent_refresh_btn.clicked.connect(_load_recent_gils_into_combo)
    _load_recent_gils_into_combo()

    output_row = QtWidgets.QWidget(gil_page)
    output_layout = QtWidgets.QHBoxLayout(output_row)
    output_layout.setContentsMargins(0, 0, 0, 0)
    output_layout.setSpacing(Sizes.SPACING_SMALL)
    output_gil_edit = QtWidgets.QLineEdit(output_row)
    output_gil_edit.setPlaceholderText(f"{package_id}.gil")
    output_gil_edit.setText(f"{package_id}.gil")
    output_browse = QtWidgets.QPushButton("浏览", output_row)
    output_browse.setFixedWidth(60)
    output_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    output_browse.clicked.connect(
        lambda: (
            (lambda p: output_gil_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getSaveFileName(gil_page, "选择输出路径", str(output_gil_edit.text()), "GIL (*.gil)")[0]
            )
        )
    )
    output_layout.addWidget(output_gil_edit, 1)
    output_layout.addWidget(output_browse)
    _r = _r + 1
    lb_output = QtWidgets.QLabel("输出文件:", gil_settings_box)
    lb_output.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_grid.addWidget(lb_output, _r, 0)
    gil_grid.addWidget(output_row, _r, 1, 1, 3)

    struct_mode_combo = QtWidgets.QComboBox(gil_page)
    struct_mode_combo.addItem("Merge (保留旧字段)", "merge")
    struct_mode_combo.addItem("Overwrite (覆盖)", "overwrite")
    struct_mode_combo.setMaximumWidth(260)

    templates_mode_combo = QtWidgets.QComboBox(gil_page)
    templates_mode_combo.addItem("Overwrite (覆盖名称；缺失会新增)", "overwrite")
    templates_mode_combo.addItem("Merge (保留旧的；缺失会新增)", "merge")
    templates_mode_combo.setMaximumWidth(260)

    instances_mode_combo = QtWidgets.QComboBox(gil_page)
    instances_mode_combo.addItem("Overwrite (覆盖位置/名字/引用元件等)", "overwrite")
    instances_mode_combo.addItem("Merge (保留旧的)", "merge")
    instances_mode_combo.setMaximumWidth(260)

    signals_mode_combo = QtWidgets.QComboBox(gil_page)
    signals_mode_combo.addItem("Semantic (语义匹配)", "semantic")
    signals_mode_combo.addItem("Template (模板克隆)", "template")
    signals_mode_combo.setMaximumWidth(260)

    ui_mode_combo = QtWidgets.QComboBox(gil_page)
    ui_mode_combo.addItem("Merge (保留旧布局)", "merge")
    ui_mode_combo.addItem("Overwrite (覆盖)", "overwrite")
    ui_mode_combo.setMaximumWidth(260)

    gil_ui_export_record_row = QtWidgets.QWidget(gil_page)
    gil_ui_export_record_layout = QtWidgets.QHBoxLayout(gil_ui_export_record_row)
    gil_ui_export_record_layout.setContentsMargins(0, 0, 0, 0)
    gil_ui_export_record_layout.setSpacing(Sizes.SPACING_SMALL)
    gil_ui_export_record_combo = QtWidgets.QComboBox(gil_ui_export_record_row)
    gil_ui_export_record_refresh_btn = QtWidgets.QPushButton("刷新", gil_ui_export_record_row)
    gil_ui_export_record_refresh_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gil_ui_export_record_layout.addWidget(gil_ui_export_record_combo, 1)
    gil_ui_export_record_layout.addWidget(gil_ui_export_record_refresh_btn)
    _r = _r + 1
    lb_gil_ui_record = QtWidgets.QLabel("UI 回填记录:", gil_settings_box)
    lb_gil_ui_record.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_grid.addWidget(lb_gil_ui_record, _r, 0)
    gil_grid.addWidget(gil_ui_export_record_row, _r, 1, 1, 3)
    gil_ui_export_record_row.setVisible(False)

    gil_id_ref_row = QtWidgets.QWidget(gil_page)
    gil_id_ref_layout = QtWidgets.QHBoxLayout(gil_id_ref_row)
    gil_id_ref_layout.setContentsMargins(0, 0, 0, 0)
    gil_id_ref_layout.setSpacing(Sizes.SPACING_SMALL)
    gil_id_ref_edit = QtWidgets.QLineEdit(gil_id_ref_row)
    gil_id_ref_edit.setPlaceholderText("可选：占位符参考 .gil（留空=使用基础 .gil）")
    gil_id_ref_browse = QtWidgets.QPushButton("浏览", gil_id_ref_row)
    gil_id_ref_browse.setFixedWidth(60)
    gil_id_ref_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gil_id_ref_browse.clicked.connect(
        lambda: (
            (lambda p: gil_id_ref_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(gil_page, "选择占位符参考文件（.gil）", "", "GIL (*.gil)")[0]
            )
        )
    )
    gil_id_ref_clear = QtWidgets.QPushButton("清空", gil_id_ref_row)
    gil_id_ref_clear.setFixedWidth(60)
    gil_id_ref_clear.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    gil_id_ref_clear.clicked.connect(lambda: gil_id_ref_edit.setText(""))
    gil_id_ref_layout.addWidget(gil_id_ref_edit, 1)
    gil_id_ref_layout.addWidget(gil_id_ref_browse)
    gil_id_ref_layout.addWidget(gil_id_ref_clear)
    _r = _r + 1
    lb_gil_id_ref = QtWidgets.QLabel("占位符参考:", gil_settings_box)
    lb_gil_id_ref.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_grid.addWidget(lb_gil_id_ref, _r, 0)
    gil_grid.addWidget(gil_id_ref_row, _r, 1, 1, 3)
    gil_id_ref_row.setVisible(False)

    gil_layout.addWidget(gil_settings_box)

    gil_advanced_toggle = QtWidgets.QCheckBox("显示高级写回策略", gil_page)
    gil_layout.addWidget(gil_advanced_toggle)

    gil_advanced_box = QtWidgets.QGroupBox("高级写回策略", gil_page)
    gil_advanced_box.setVisible(False)
    gil_advanced_box.setStyleSheet(ThemeManager.group_box_style())
    gil_adv_grid = QtWidgets.QGridLayout(gil_advanced_box)
    gil_adv_grid.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    gil_adv_grid.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    gil_adv_grid.setVerticalSpacing(Sizes.SPACING_MEDIUM)
    gil_adv_grid.setColumnStretch(1, 1)
    gil_adv_grid.setColumnStretch(3, 1)
    _ar = 0

    lb_struct_adv = QtWidgets.QLabel("结构体模式:", gil_advanced_box)
    lb_struct_adv.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_adv_grid.addWidget(lb_struct_adv, _ar, 0)
    gil_adv_grid.addWidget(struct_mode_combo, _ar, 1)
    lb_signals_adv = QtWidgets.QLabel("信号模式:", gil_advanced_box)
    lb_signals_adv.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_adv_grid.addWidget(lb_signals_adv, _ar, 2)
    gil_adv_grid.addWidget(signals_mode_combo, _ar, 3)

    _ar = _ar + 1
    prefer_signal_specific_type_id_cb = QtWidgets.QCheckBox("信号节点使用专用 type_id（signal-specific，固定）", gil_advanced_box)
    # 固定开启：对齐真源端口展开/绑定口径；仅在满足“静态绑定 + base 映射可用”时才会实际切换。
    prefer_signal_specific_type_id_cb.setChecked(True)
    prefer_signal_specific_type_id_cb.setEnabled(False)
    prefer_signal_specific_type_id_cb.setToolTip(
        "固定策略：当节点图中的信号节点满足“静态绑定”（__signal_id 存在 + 信号名为常量且无入边），并且基础 .gil 可提供映射时，\n"
        "将节点 type_id 从通用 runtime（300000/300001/300002）提升为 signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx；由 base 的 node_def_id 0x4000xxxx/0x4080xxxx 推导），更贴近真源结构。\n"
        "提示：该策略不会影响“动态信号名”（信号名端口有入边）的节点。"
    )
    gil_adv_grid.addWidget(prefer_signal_specific_type_id_cb, _ar, 0, 1, 4)

    _ar = _ar + 1
    lb_tpl_adv = QtWidgets.QLabel("元件模式:", gil_advanced_box)
    lb_tpl_adv.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_adv_grid.addWidget(lb_tpl_adv, _ar, 0)
    gil_adv_grid.addWidget(templates_mode_combo, _ar, 1)
    lb_ui_adv = QtWidgets.QLabel("UI 模式:", gil_advanced_box)
    lb_ui_adv.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_adv_grid.addWidget(lb_ui_adv, _ar, 2)
    gil_adv_grid.addWidget(ui_mode_combo, _ar, 3)

    _ar = _ar + 1
    lb_inst_adv = QtWidgets.QLabel("实体摆放模式:", gil_advanced_box)
    lb_inst_adv.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    gil_adv_grid.addWidget(lb_inst_adv, _ar, 0)
    gil_adv_grid.addWidget(instances_mode_combo, _ar, 1)

    gil_layout.addWidget(gil_advanced_box)

    gil_ui_box = QtWidgets.QGroupBox("UI 写回选项", gil_page)
    gil_ui_box.setStyleSheet(ThemeManager.group_box_style())
    gil_ui_layout = QtWidgets.QVBoxLayout(gil_ui_box)
    gil_ui_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )

    write_ui_cb = QtWidgets.QCheckBox("启用 UI 写回 (界面)", gil_ui_box)
    write_ui_cb.setToolTip(
        "提示：当选择了“UI源码”资源时，UI 写回会被自动强制开启（用于保证写回内容完整且便于节点图 ui_key 回填）。\n"
        "若希望真正关闭 UI 写回，请不要选择 UI源码。"
    )
    gil_ui_layout.addWidget(write_ui_cb)

    write_ui_hint = QtWidgets.QLabel("", gil_ui_box)
    write_ui_hint.setWordWrap(True)
    write_ui_hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    write_ui_hint.setVisible(False)
    gil_ui_layout.addWidget(write_ui_hint)

    ui_auto_sync_vars_cb = QtWidgets.QCheckBox("自动同步自定义变量", gil_ui_box)
    ui_auto_sync_vars_cb.setChecked(True)
    ui_auto_sync_vars_cb.setToolTip("根据 UI 引用自动补齐关卡/玩家变量")
    gil_ui_layout.addWidget(ui_auto_sync_vars_cb)

    gil_layout.addWidget(gil_ui_box)

    selected_level_custom_variable_ids: list[str] = []
    level_custom_variable_meta_by_id: dict[str, dict[str, str]] = {}

    gil_level_vars_box = QtWidgets.QGroupBox("关卡实体自定义变量（全部）", gil_page)
    gil_level_vars_box.setStyleSheet(ThemeManager.group_box_style())
    gil_level_vars_layout = QtWidgets.QVBoxLayout(gil_level_vars_box)
    gil_level_vars_layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    gil_level_vars_layout.setSpacing(Sizes.SPACING_SMALL)

    level_vars_hint = QtWidgets.QLabel(
        "在左侧资源树勾选『关卡实体自定义变量（全部）』后，将自动全量补齐写入输出 .gil 的【关卡实体】override_variables（group_id=1）。\n"
        "- 仅补齐缺失变量；不修改已存在同名变量的当前值\n"
        "- 若存档中已存在同名但类型不同的变量：默认不覆盖（会在报告中列出）",
        gil_level_vars_box,
    )
    level_vars_hint.setWordWrap(True)
    level_vars_hint.setStyleSheet(ThemeManager.subtle_info_style())
    gil_level_vars_layout.addWidget(level_vars_hint)

    level_vars_preview = QtWidgets.QLabel("", gil_level_vars_box)
    level_vars_preview.setWordWrap(True)
    level_vars_preview.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    gil_level_vars_layout.addWidget(level_vars_preview)

    level_vars_btn_row = QtWidgets.QWidget(gil_level_vars_box)
    level_vars_btn_layout = QtWidgets.QHBoxLayout(level_vars_btn_row)
    level_vars_btn_layout.setContentsMargins(0, 0, 0, 0)
    level_vars_btn_layout.setSpacing(Sizes.SPACING_SMALL)
    level_vars_btn_layout.addStretch(1)
    level_vars_select_btn = QtWidgets.QPushButton("选择…", level_vars_btn_row)
    level_vars_select_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    level_vars_clear_btn = QtWidgets.QPushButton("清空", level_vars_btn_row)
    level_vars_clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    level_vars_btn_layout.addWidget(level_vars_select_btn)
    level_vars_btn_layout.addWidget(level_vars_clear_btn)
    gil_level_vars_layout.addWidget(level_vars_btn_row)

    # 选择器已迁移到左侧资源树勾选：右侧不再提供“逐个选择/清空”的按钮，避免用户误解。
    level_vars_btn_row.setVisible(False)
    level_vars_select_btn.setEnabled(False)
    level_vars_clear_btn.setEnabled(False)

    def _refresh_level_vars_preview() -> None:
        if not selected_level_custom_variable_ids:
            level_vars_preview.setText("未选择任何关卡变量。导出时不会修改关卡实体自定义变量。")
            return
        names: list[str] = []
        for vid in list(selected_level_custom_variable_ids):
            meta = level_custom_variable_meta_by_id.get(str(vid))
            n = str(meta.get("variable_name") or "").strip() if isinstance(meta, dict) else ""
            names.append(n if n != "" else str(vid))
        shown = ", ".join(names[:8])
        suffix = "" if len(names) <= 8 else f" …（共 {len(names)} 个）"
        level_vars_preview.setText(f"已选择 {len(names)} 个：{shown}{suffix}")

    def _open_level_vars_picker_dialog() -> None:
        from .export_center_level_vars_picker import open_level_custom_variable_picker_dialog

        res = open_level_custom_variable_picker_dialog(
            QtCore=QtCore,
            QtWidgets=QtWidgets,
            Colors=Colors,
            Sizes=Sizes,
            parent_dialog=dialog_parent,
            package_id=str(package_id),
            preselected_ids=list(selected_level_custom_variable_ids),
        )
        level_custom_variable_meta_by_id.clear()
        level_custom_variable_meta_by_id.update(dict(res.meta_by_id))
        if res.picked_ids is None:
            return
        selected_level_custom_variable_ids[:] = list(res.picked_ids)
        _refresh_level_vars_preview()

    def _clear_level_vars_selection() -> None:
        selected_level_custom_variable_ids[:] = []
        _refresh_level_vars_preview()

    level_vars_select_btn.clicked.connect(_open_level_vars_picker_dialog)
    level_vars_clear_btn.clicked.connect(_clear_level_vars_selection)
    _refresh_level_vars_preview()

    gil_layout.addWidget(gil_level_vars_box)
    gil_layout.addStretch(1)

    stacked.addWidget(gil_page)

    return ExportCenterGilPage(
        page=gil_page,
        input_gil_edit=input_gil_edit,
        input_gil_browse_btn=input_browse,
        output_gil_edit=output_gil_edit,
        use_builtin_empty_base_cb=use_builtin_empty_base_cb,
        builtin_empty_base_hint=builtin_hint,
        recent_combo=recent_combo,
        recent_use_btn=recent_use_btn,
        recent_refresh_btn=recent_refresh_btn,
        gil_advanced_toggle=gil_advanced_toggle,
        gil_advanced_box=gil_advanced_box,
        struct_mode_combo=struct_mode_combo,
        templates_mode_combo=templates_mode_combo,
        instances_mode_combo=instances_mode_combo,
        signals_mode_combo=signals_mode_combo,
        prefer_signal_specific_type_id_cb=prefer_signal_specific_type_id_cb,
        ui_mode_combo=ui_mode_combo,
        gil_ui_export_record_row=gil_ui_export_record_row,
        gil_ui_export_record_combo=gil_ui_export_record_combo,
        gil_ui_export_record_refresh_btn=gil_ui_export_record_refresh_btn,
        gil_id_ref_row=gil_id_ref_row,
        gil_id_ref_edit=gil_id_ref_edit,
        write_ui_cb=write_ui_cb,
        write_ui_hint=write_ui_hint,
        ui_auto_sync_vars_cb=ui_auto_sync_vars_cb,
        selected_level_custom_variable_ids=selected_level_custom_variable_ids,
        level_custom_variable_meta_by_id=level_custom_variable_meta_by_id,
        level_vars_preview=level_vars_preview,
        level_vars_select_btn=level_vars_select_btn,
        level_vars_clear_btn=level_vars_clear_btn,
    )


def _build_repair_page(
    *,
    QtCore: object,
    QtWidgets: object,
    Colors: object,
    Sizes: object,
    ThemeManager: object,
    workspace_root: Path,
    stacked: object,
) -> ExportCenterRepairPage:
    repair_page = QtWidgets.QWidget(stacked)
    repair_layout = QtWidgets.QVBoxLayout(repair_page)
    repair_layout.setContentsMargins(0, 0, 0, 0)
    repair_layout.setSpacing(Sizes.SPACING_MEDIUM)

    repair_info = QtWidgets.QLabel(
        "信号修复/合并均以 wire-level 最小补丁执行，不会覆盖原文件。\n"
        "- 修复信号：基于所选节点图导出的临时 .gia，自动去重/重绑/清理残留\n"
        "- 合并信号条目：显式指定 keep/remove 信号名，合并两条 signal entry 并重绑引用（适合处理导入后生成的占位符信号）",
        repair_page,
    )
    repair_info.setStyleSheet(ThemeManager.subtle_info_style())
    repair_info.setWordWrap(True)
    repair_layout.addWidget(repair_info)

    repair_box = QtWidgets.QGroupBox("修复信号（自动）", repair_page)
    repair_box.setStyleSheet(ThemeManager.group_box_style())
    repair_grid = QtWidgets.QGridLayout(repair_box)
    repair_grid.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    repair_grid.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    repair_grid.setVerticalSpacing(Sizes.SPACING_MEDIUM)
    repair_grid.setColumnStretch(1, 1)
    _rr = 0

    repair_input_row = QtWidgets.QWidget(repair_box)
    repair_input_layout = QtWidgets.QHBoxLayout(repair_input_row)
    repair_input_layout.setContentsMargins(0, 0, 0, 0)
    repair_input_layout.setSpacing(Sizes.SPACING_SMALL)
    repair_input_gil_edit = QtWidgets.QLineEdit(repair_input_row)
    repair_input_gil_edit.setPlaceholderText("选择需要修复的 .gil 文件…")
    last_repair_input = _load_last_repair_input_gil_path(workspace_root=Path(workspace_root))
    if last_repair_input != "":
        repair_input_gil_edit.setText(str(last_repair_input))
    repair_input_browse = QtWidgets.QPushButton("浏览", repair_input_row)
    repair_input_browse.setFixedWidth(60)
    repair_input_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    repair_input_browse.clicked.connect(
        lambda: (
            (lambda p: repair_input_gil_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(repair_page, "选择需要修复的 .gil", "", "GIL (*.gil)")[0]
            )
        )
    )
    repair_input_layout.addWidget(repair_input_gil_edit, 1)
    repair_input_layout.addWidget(repair_input_browse)
    lb_repair_input = QtWidgets.QLabel("目标文件:", repair_box)
    lb_repair_input.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    repair_grid.addWidget(lb_repair_input, _rr, 0)
    repair_grid.addWidget(repair_input_row, _rr, 1)

    repair_output_row = QtWidgets.QWidget(repair_box)
    repair_output_layout = QtWidgets.QHBoxLayout(repair_output_row)
    repair_output_layout.setContentsMargins(0, 0, 0, 0)
    repair_output_layout.setSpacing(Sizes.SPACING_SMALL)
    repair_output_gil_edit = QtWidgets.QLineEdit(repair_output_row)
    repair_output_gil_edit.setPlaceholderText("输出路径（默认生成在同目录旁边）")
    repair_output_browse = QtWidgets.QPushButton("浏览", repair_output_row)
    repair_output_browse.setFixedWidth(60)
    repair_output_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    repair_output_browse.clicked.connect(
        lambda: (
            (lambda p: repair_output_gil_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getSaveFileName(
                    repair_page,
                    "选择输出路径（修复后的 .gil）",
                    str(repair_output_gil_edit.text()),
                    "GIL (*.gil)",
                )[0]
            )
        )
    )
    repair_output_layout.addWidget(repair_output_gil_edit, 1)
    repair_output_layout.addWidget(repair_output_browse)
    _rr = _rr + 1
    lb_repair_output = QtWidgets.QLabel("输出文件:", repair_box)
    lb_repair_output.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    repair_grid.addWidget(lb_repair_output, _rr, 0)
    repair_grid.addWidget(repair_output_row, _rr, 1)

    repair_prune_orphans_cb = QtWidgets.QCheckBox("清理未引用的占位信号残留（推荐）", repair_box)
    repair_prune_orphans_cb.setChecked(True)
    _rr = _rr + 1
    repair_grid.addWidget(repair_prune_orphans_cb, _rr, 0, 1, 2)

    repair_layout.addWidget(repair_box)

    # ===== 合并信号条目（显式 keep/remove） =====
    merge_box = QtWidgets.QGroupBox("合并信号条目（显式）", repair_page)
    merge_box.setStyleSheet(ThemeManager.group_box_style())
    merge_grid = QtWidgets.QGridLayout(merge_box)
    merge_grid.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    merge_grid.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    merge_grid.setVerticalSpacing(Sizes.SPACING_MEDIUM)
    merge_grid.setColumnStretch(1, 1)
    _mr = 0

    keep_edit = QtWidgets.QLineEdit(merge_box)
    keep_edit.setPlaceholderText("keep：要保留的信号名（通常是占位符，如 信号_3）")
    lb_keep = QtWidgets.QLabel("keep:", merge_box)
    lb_keep.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    merge_grid.addWidget(lb_keep, _mr, 0)
    merge_grid.addWidget(keep_edit, _mr, 1)

    _mr += 1
    remove_edit = QtWidgets.QLineEdit(merge_box)
    remove_edit.setPlaceholderText("remove：要移除的信号名（通常是正式信号名）")
    lb_remove = QtWidgets.QLabel("remove:", merge_box)
    lb_remove.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    merge_grid.addWidget(lb_remove, _mr, 0)
    merge_grid.addWidget(remove_edit, _mr, 1)

    _mr += 1
    rename_edit = QtWidgets.QLineEdit(merge_box)
    rename_edit.setPlaceholderText("可选：将 keep 重命名为该名字（常用=remove）")
    lb_rename = QtWidgets.QLabel("rename:", merge_box)
    lb_rename.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
    merge_grid.addWidget(lb_rename, _mr, 0)
    merge_grid.addWidget(rename_edit, _mr, 1)

    _mr += 1
    patch_cpi_cb = QtWidgets.QCheckBox("同步修补 compositePinIndex（推荐，避免端口解释错位）", merge_box)
    patch_cpi_cb.setChecked(True)
    merge_grid.addWidget(patch_cpi_cb, _mr, 0, 1, 2)

    repair_layout.addWidget(merge_box)
    repair_layout.addStretch(1)

    stacked.addWidget(repair_page)

    return ExportCenterRepairPage(
        page=repair_page,
        repair_input_gil_edit=repair_input_gil_edit,
        repair_output_gil_edit=repair_output_gil_edit,
        repair_auto_box=repair_box,
        repair_prune_orphans_cb=repair_prune_orphans_cb,
        merge_entries_box=merge_box,
        merge_keep_signal_edit=keep_edit,
        merge_remove_signal_edit=remove_edit,
        merge_rename_keep_to_edit=rename_edit,
        merge_patch_cpi_cb=patch_cpi_cb,
    )

