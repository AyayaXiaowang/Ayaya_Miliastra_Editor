from __future__ import annotations

from pathlib import Path
from typing import Any

from .export_center_dialog_types import ExportCenterFooter, ExportCenterLeftPane, ExportCenterRightPane
from .export_center_dialog_wiring.wire import wire_export_center_dialog as _wire_export_center_dialog


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
    left: ExportCenterLeftPane,
    right: ExportCenterRightPane,
    wizard_tabs: Any,
    footer: ExportCenterFooter,
    open_task_history_dialog: Any,
    append_task_history_entry: Any,
    now_ts: Any,
) -> None:
    """对外薄入口：转发到拆分后的 wiring 实现。"""

    _wire_export_center_dialog(
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
