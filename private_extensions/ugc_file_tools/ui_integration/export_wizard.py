from __future__ import annotations


from pathlib import Path

from ._common import get_selected_package_id, resolve_packages_root_dir


def on_open_import_export_center_clicked(main_window: object) -> None:
    """打开 ugc_file_tools 导入/导出中心（PACKAGES 页入口）。"""
    _open_import_export_center_dialog(main_window=main_window, show_import=True, preferred_format=None)


def on_open_export_center_clicked(main_window: object, *, preferred_format: str | None = None) -> None:
    """打开 ugc_file_tools 导出中心（仅导出；顶部工具栏入口使用）。"""
    _open_import_export_center_dialog(
        main_window=main_window,
        show_import=False,
        preferred_format=(str(preferred_format).strip() if preferred_format is not None else None),
    )


def _open_import_export_center_dialog(
    *,
    main_window: object,
    show_import: bool,
    preferred_format: str | None,
) -> None:
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
    from engine.utils.resource_library_layout import get_shared_root_dir
    from typing import cast

    from .export_history import append_task_history_entry, now_ts, open_task_history_dialog
    from .export_center_dialog_controller import wire_export_center_dialog
    from .export_center_dialog_footer import build_export_center_footer
    from .export_center_dialog_left import build_export_center_left_pane
    from .export_center_dialog_right import build_export_center_right_pane

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    workspace_root = Path(getattr(main_window, "app_state").workspace_path).resolve()
    package_id = str(get_selected_package_id(main_window) or "").strip()
    export_enabled = bool(package_id) and package_id not in {"global_view", "unclassified_view"}

    # 导出中心弹窗应允许底层页面继续操作：必须是非模态（show，而不是 exec）。
    dialog_attr = "_ugc_file_tools_import_export_center_dialog" if show_import else "_ugc_file_tools_export_center_dialog"
    existing_dialog = getattr(main_window, dialog_attr, None)
    if isinstance(existing_dialog, QtWidgets.QDialog):
        existing_dialog.show()
        existing_dialog.raise_()
        existing_dialog.activateWindow()
        return

    dialog = QtWidgets.QDialog(main_window)
    dialog.setObjectName("ugc_file_tools_export_center_dialog" if not show_import else "ugc_file_tools_import_export_center_dialog")
    dialog.setWindowTitle("导入/导出中心" if show_import else "导出中心")
    # 允许用户自由调整窗口大小（尤其是高度）。某些平台/样式组合下 QDialog 容易表现为“只能变长不能缩短”：
    # - 内容布局撑高最小高度；
    # - Windows 固定大小 hint 导致无法拖拽缩放；
    # 因此这里显式开启 size grip，并尽量移除固定大小提示。
    dialog.setSizeGripEnabled(True)
    fixed_size_hint = getattr(QtCore.Qt.WindowType, "MSWindowsFixedSizeDialogHint", None)
    if fixed_size_hint is not None:
        dialog.setWindowFlag(fixed_size_hint, False)
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.setWindowModality(QtCore.Qt.WindowModality.NonModal)
    dialog.setModal(False)
    # 初始尺寸：默认不超过主程序窗口（避免“比主程序还大”的观感），同时尽量保证右侧“写回配置”的浏览按钮可见。
    screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
    if screen is not None:
        avail = screen.availableGeometry()
        cap_w = min(int(avail.width()), int(main_window.width()))
        cap_h = min(int(avail.height()), int(main_window.height()))
        # 预期主程序窗口已在屏幕内；若拿到异常的小值，则回退到屏幕可用尺寸。
        if cap_w <= 0:
            cap_w = int(avail.width())
        if cap_h <= 0:
            cap_h = int(avail.height())

        target_w = max(1200, int(cap_w * 0.96))
        target_h = max(780, int(cap_h * 0.92))
        target_w = min(target_w, int(cap_w))
        target_h = min(target_h, int(cap_h))
        dialog.resize(target_w, target_h)
    else:
        cap_w = int(main_window.width())
        cap_h = int(main_window.height())
        if cap_w > 0 and cap_h > 0:
            dialog.resize(min(1200, cap_w), min(800, cap_h))
        else:
            dialog.resize(1200, 800)

    setattr(main_window, dialog_attr, dialog)
    dialog.destroyed.connect(lambda *_: setattr(main_window, dialog_attr, None))

    # Apply dialog styling
    dialog.setStyleSheet(f"""
        QDialog {{
            background-color: {Colors.BG_MAIN};
        }}
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}
    """)

    root_layout = QtWidgets.QVBoxLayout(dialog)
    root_layout.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root_layout.setSpacing(Sizes.SPACING_LARGE)

    # ===== 标题行（保持极简，但提供可测/可定位的标题控件） =====
    title_row = QtWidgets.QHBoxLayout()
    title_text = "导入/导出中心" if show_import else "导出中心"
    title_label = QtWidgets.QLabel(title_text, dialog)
    title_label.setStyleSheet(ThemeManager.heading(level=3))
    title_row.addWidget(title_label)
    title_row.addStretch(1)
    root_layout.addLayout(title_row)

    # ===== 导入（可选显示） =====
    if show_import:
        from .read_gia import on_read_clicked as on_read_gia_clicked
        from .read_gil import on_read_clicked as on_read_gil_clicked
        from .read_gil_selected import on_read_clicked as on_read_gil_selected_clicked

        import_frame = QtWidgets.QFrame(dialog)
        import_frame.setStyleSheet(ThemeManager.card_style())
        import_layout = QtWidgets.QHBoxLayout(import_frame)
        import_layout.setContentsMargins(Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM, Sizes.PADDING_MEDIUM)
        
        import_info = QtWidgets.QLabel("导入项目存档 (.gil/.gia)", import_frame)
        import_info.setStyleSheet("font-weight: bold;")
        
        import_gil_btn = QtWidgets.QPushButton("读取 .gil 文件…", import_frame)
        import_gil_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        import_gil_btn.setToolTip("选择一个 .gil 文件导入为项目存档（后台执行）")
        import_gil_btn.clicked.connect(lambda: (dialog.accept(), on_read_gil_clicked(main_window)))

        import_gil_selected_btn = QtWidgets.QPushButton("读取 .gil（选择）…", import_frame)
        import_gil_selected_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        import_gil_selected_btn.setToolTip("选择一个 .gil 文件→分析节点图清单→勾选导入（适合只导入部分图）")
        import_gil_selected_btn.clicked.connect(
            lambda: (dialog.accept(), on_read_gil_selected_clicked(main_window))
        )

        import_gia_btn = QtWidgets.QPushButton("导入 .gia 文件…", import_frame)
        import_gia_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        import_gia_btn.setToolTip("选择一个 .gia 文件并导入到项目存档（元件/实体摆放/玩家模板）")
        import_gia_btn.clicked.connect(lambda: (dialog.accept(), on_read_gia_clicked(main_window)))
        
        import_layout.addWidget(import_info)
        import_layout.addStretch(1)
        import_layout.addWidget(import_gil_btn)
        import_layout.addWidget(import_gil_selected_btn)
        import_layout.addWidget(import_gia_btn)
        
        root_layout.addWidget(import_frame)

    # ===== 导出（主区域） =====
    # 导出向导：三步标签页覆盖整个导出区域（包含“资源选择”）。
    # - 步骤1：选择与配置（资源选择 + 格式与参数）
    # - 步骤2：回填分析（依赖清单 + 识别对比）
    # - 步骤3：执行（进度/日志/结果）

    if not export_enabled:
        no_export_widget = QtWidgets.QWidget()
        no_export_layout = QtWidgets.QVBoxLayout(no_export_widget)
        no_export_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        warn_label = QtWidgets.QLabel("未选择有效的项目存档", no_export_widget)
        warn_label.setStyleSheet(ThemeManager.heading(level=3))

        hint_label = QtWidgets.QLabel(
            "请先在“项目存档”页选择一个具体的项目（不要停留在 <共享资源> 视图）。",
            no_export_widget,
        )
        hint_label.setStyleSheet(ThemeManager.subtle_info_style())

        no_export_layout.addWidget(warn_label)
        no_export_layout.addWidget(hint_label)

        root_layout.addWidget(no_export_widget, 1)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)
        history_btn = QtWidgets.QPushButton("查看最近任务", dialog)
        history_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        history_btn.clicked.connect(lambda: open_task_history_dialog(main_window=main_window))
        close_btn = QtWidgets.QPushButton("关闭", dialog)
        close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(history_btn)
        btn_row.addWidget(close_btn)
        root_layout.addLayout(btn_row)

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        return

    packages_root = resolve_packages_root_dir(workspace_root=workspace_root).resolve()
    resource_library_root = (workspace_root / "assets" / "资源库").resolve()
    shared_root = get_shared_root_dir(resource_library_root).resolve()
    project_root = (packages_root / str(package_id)).resolve()
    if not project_root.is_dir():
        raise FileNotFoundError(str(project_root))

    left = build_export_center_left_pane(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        dialog=dialog,
        workspace_root=Path(workspace_root),
        project_root=Path(project_root),
        shared_root=Path(shared_root),
    )
    right = build_export_center_right_pane(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
        ThemeManager=ThemeManager,
        workspace_root=Path(workspace_root),
        package_id=str(package_id),
    )

    wizard_tabs = QtWidgets.QTabWidget(dialog)
    wizard_tabs.setDocumentMode(True)
    wizard_tabs.setMovable(False)
    wizard_tabs.setTabsClosable(False)
    wizard_tabs.setMinimumHeight(520)
    root_layout.addWidget(wizard_tabs, 1)

    step1_page = QtWidgets.QWidget(wizard_tabs)
    step1_layout = QtWidgets.QVBoxLayout(step1_page)
    step1_layout.setContentsMargins(0, 0, 0, 0)
    step1_layout.setSpacing(Sizes.SPACING_MEDIUM)

    step1_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, step1_page)
    step1_splitter.setHandleWidth(6)
    step1_splitter.setStyleSheet(ThemeManager.splitter_style())
    step1_splitter.addWidget(cast(QtWidgets.QWidget, left.pane))
    step1_splitter.addWidget(cast(QtWidgets.QWidget, right.config_pane))
    # 默认宽度：右侧需保证“写回配置”行的浏览按钮可见（右侧列 minWidth 会兜底）。
    # 初始分配会给右侧更多空间，避免用户第一次打开就需要拖拽分割条。
    step1_splitter.setStretchFactor(0, 3)
    step1_splitter.setStretchFactor(1, 2)
    content_w = max(0, int(dialog.width() - int(Sizes.PADDING_LARGE) * 2))
    right_w = int(content_w * 0.45)
    right_w = max(560, min(820, right_w))
    left_w = max(0, content_w - right_w)
    step1_splitter.setSizes([left_w, right_w])
    step1_splitter.setCollapsible(0, False)
    step1_splitter.setCollapsible(1, False)
    step1_layout.addWidget(step1_splitter, 1)

    wizard_tabs.addTab(step1_page, "步骤1：选择与配置")
    wizard_tabs.addTab(cast(QtWidgets.QWidget, right.analysis.page), "步骤2：回填分析")
    wizard_tabs.addTab(cast(QtWidgets.QWidget, right.execute.page), "步骤3：执行")

    btn_row, footer = build_export_center_footer(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        dialog=dialog,
        open_task_history_dialog=open_task_history_dialog,
        main_window=main_window,
    )
    root_layout.addLayout(cast(QtWidgets.QLayout, btn_row))

    wire_export_center_dialog(
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

    # 兼容入口：旧导出对话框会期望直接进入对应格式配置页（.gil/.gia/...）。
    # 这里允许调用方覆盖“上次使用的格式”，并触发 controller 内部的联动刷新。
    fmt = str(preferred_format or "").strip()
    if fmt != "":
        idx = int(right.format_combo.findData(str(fmt)))
        if idx >= 0:
            right.format_combo.setCurrentIndex(idx)

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

