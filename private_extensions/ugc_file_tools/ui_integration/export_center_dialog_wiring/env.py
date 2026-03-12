from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..export_center.dialog_runtime_state import ExportCenterDialogRuntimeState
from ..export_center_dialog_types import ExportCenterFooter, ExportCenterLeftPane, ExportCenterRightPane


@dataclass
class ExportCenterDialogWiringEnv:
    """承载导出中心对话框 wiring 所需的控件引用与运行态状态对象。"""

    QtCore: Any
    QtWidgets: Any
    Colors: Any
    Sizes: Any
    ThemeManager: Any
    dialog: Any
    main_window: Any
    workspace_root: Path
    package_id: str
    project_root: Path
    left: ExportCenterLeftPane
    right: ExportCenterRightPane
    wizard_tabs: Any
    footer: ExportCenterFooter
    open_task_history_dialog: Any
    append_task_history_entry: Any
    now_ts: Any

    picker: Any
    gia: Any
    gil: Any
    repair: Any
    analysis: Any
    execute: Any

    tabs: Any
    run_btn: Any
    back_btn: Any
    next_btn: Any
    close_btn: Any
    history_btn: Any
    format_combo: Any
    stacked: Any

    rt: ExportCenterDialogRuntimeState
    footer_next_default_stylesheet: str
    footer_next_primary_stylesheet: str


def build_export_center_dialog_wiring_env(
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
    left: ExportCenterLeftPane,
    right: ExportCenterRightPane,
    wizard_tabs: Any,
    footer: ExportCenterFooter,
    open_task_history_dialog: Any,
    append_task_history_entry: Any,
    now_ts: Any,
) -> ExportCenterDialogWiringEnv:
    """构建导出中心对话框 wiring 的环境对象。"""

    picker = left.picker
    gia = right.gia
    gil = right.gil
    repair = right.repair
    analysis = right.analysis
    execute = right.execute

    tabs = wizard_tabs
    run_btn = execute.run_btn
    back_btn = footer.back_btn
    next_btn = footer.next_btn
    close_btn = footer.close_btn
    history_btn = footer.history_btn
    format_combo = right.format_combo
    stacked = right.stacked

    rt = ExportCenterDialogRuntimeState()
    footer_next_default_stylesheet = str(next_btn.styleSheet() or "")
    footer_next_primary_stylesheet = f"""
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
    """

    return ExportCenterDialogWiringEnv(
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
        picker=picker,
        gia=gia,
        gil=gil,
        repair=repair,
        analysis=analysis,
        execute=execute,
        tabs=tabs,
        run_btn=run_btn,
        back_btn=back_btn,
        next_btn=next_btn,
        close_btn=close_btn,
        history_btn=history_btn,
        format_combo=format_combo,
        stacked=stacked,
        rt=rt,
        footer_next_default_stylesheet=footer_next_default_stylesheet,
        footer_next_primary_stylesheet=footer_next_primary_stylesheet,
    )

