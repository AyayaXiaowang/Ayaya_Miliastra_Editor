from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..export_center_dialog_plan_validators import (
    validate_gia_plan,
    validate_gil_plan,
    validate_merge_signal_entries_plan,
    validate_repair_signals_plan,
)

from .env import ExportCenterDialogWiringEnv

_STEP_SELECT_IDX = 0
_STEP_ANALYSIS_IDX = 1
_STEP_EXECUTE_IDX = 2

_MIN_REQUIRED_SELECTIONS = 1


def has_any_selection(env: ExportCenterDialogWiringEnv) -> bool:
    """判断当前模式是否满足“允许进入下一步”的选择条件。"""

    fmt = str(env.format_combo.currentData() or "gia")
    if fmt == "merge_signal_entries":
        return True
    return bool(list(env.picker.get_selected_items()))


def can_enter_analysis_step(env: ExportCenterDialogWiringEnv) -> bool:
    """校验是否允许从步骤1进入步骤2。"""

    if has_any_selection(env):
        return True
    from app.ui.foundation import dialog_utils

    dialog_utils.show_warning_dialog(env.main_window, "提示", f"请先在左侧勾选至少 {_MIN_REQUIRED_SELECTIONS} 个资源，再进入下一步。")
    return False


def can_enter_execute_step(env: ExportCenterDialogWiringEnv) -> bool:
    """校验是否允许从步骤2进入步骤3。"""

    fmt = str(env.format_combo.currentData() or "gia")
    if fmt == "gia":
        return (
            validate_gia_plan(
                main_window=env.main_window,
                workspace_root=Path(env.workspace_root),
                package_id=str(env.package_id),
                project_root=Path(env.project_root),
                picker=env.picker,
                gia=env.gia,
            )
            is not None
        )
    if fmt == "gil":
        return (
            validate_gil_plan(
                main_window=env.main_window,
                workspace_root=Path(env.workspace_root),
                package_id=str(env.package_id),
                project_root=Path(env.project_root),
                picker=env.picker,
                gil=env.gil,
            )
            is not None
        )
    if fmt == "merge_signal_entries":
        return (
            validate_merge_signal_entries_plan(
                main_window=env.main_window,
                workspace_root=Path(env.workspace_root),
                package_id=str(env.package_id),
                project_root=Path(env.project_root),
                picker=env.picker,
                repair=env.repair,
            )
            is not None
        )
    return (
        validate_repair_signals_plan(
            main_window=env.main_window,
            workspace_root=Path(env.workspace_root),
            package_id=str(env.package_id),
            project_root=Path(env.project_root),
            picker=env.picker,
            repair=env.repair,
        )
        is not None
    )


def sync_step_nav(env: ExportCenterDialogWiringEnv) -> None:
    """根据当前步骤索引与选择状态同步 footer/steps 的可用性与文案。"""

    idx = int(env.tabs.currentIndex())
    env.back_btn.setEnabled(idx > _STEP_SELECT_IDX)
    has_sel = bool(has_any_selection(env))
    env.tabs.setTabEnabled(_STEP_ANALYSIS_IDX, bool(has_sel))
    env.tabs.setTabEnabled(_STEP_EXECUTE_IDX, bool(has_sel))
    if idx == _STEP_SELECT_IDX:
        env.next_btn.setEnabled(bool(has_sel))
        env.next_btn.setText("下一步：回填分析")
        env.next_btn.setDefault(True)
        env.next_btn.setStyleSheet(env.footer_next_default_stylesheet)
        env.next_btn.setToolTip("" if has_sel else f"请先勾选至少 {_MIN_REQUIRED_SELECTIONS} 个资源")
        env.run_btn.setDefault(False)
    elif idx == _STEP_ANALYSIS_IDX:
        env.next_btn.setEnabled(True)
        env.next_btn.setText("下一步：执行")
        env.next_btn.setDefault(True)
        env.next_btn.setStyleSheet(env.footer_next_default_stylesheet)
        env.next_btn.setToolTip("")
        env.run_btn.setDefault(False)
    else:
        env.next_btn.setEnabled(True)
        env.next_btn.setText(str(env.run_btn.text() or "开始导出"))
        env.next_btn.setDefault(True)
        env.next_btn.setStyleSheet(env.footer_next_primary_stylesheet)
        env.next_btn.setToolTip("")
        env.run_btn.setDefault(False)
    env.run_btn.setEnabled(False)


def go_prev_step(env: ExportCenterDialogWiringEnv) -> None:
    """处理 footer 的“上一步”按钮点击。"""

    idx = int(env.tabs.currentIndex())
    if idx <= _STEP_SELECT_IDX:
        return
    env.tabs.setCurrentIndex(idx - 1)


def go_next_step(env: ExportCenterDialogWiringEnv, *, on_run_clicked: Callable[[object], None]) -> None:
    """处理 footer 的“下一步/开始”按钮点击并在步骤3触发执行。"""

    idx = int(env.tabs.currentIndex())
    if idx == _STEP_SELECT_IDX:
        if not bool(can_enter_analysis_step(env)):
            return
        env.tabs.setCurrentIndex(_STEP_ANALYSIS_IDX)
        return
    if idx == _STEP_ANALYSIS_IDX:
        if not bool(can_enter_execute_step(env)):
            return
        env.tabs.setCurrentIndex(_STEP_EXECUTE_IDX)
        return
    if idx == _STEP_EXECUTE_IDX:
        on_run_clicked(env.next_btn)


def wire_step_navigation(
    env: ExportCenterDialogWiringEnv,
    *,
    on_run_clicked: Callable[[object], None],
    update_preview: Callable[[], None],
) -> None:
    """连接步骤 tabs 与 footer 按钮的导航逻辑。"""

    env.back_btn.clicked.connect(lambda: go_prev_step(env))
    env.next_btn.clicked.connect(lambda: go_next_step(env, on_run_clicked=on_run_clicked))
    step_state = {"last_idx": int(env.tabs.currentIndex())}

    def _on_tabs_current_changed(new_idx: int) -> None:
        """拦截不满足条件的 step 切换并触发联动刷新。"""
        prev = int(step_state.get("last_idx") or 0)
        cur = int(new_idx)
        if cur == _STEP_ANALYSIS_IDX and prev != _STEP_ANALYSIS_IDX:
            if not bool(can_enter_analysis_step(env)):
                env.tabs.blockSignals(True)
                env.tabs.setCurrentIndex(int(prev))
                env.tabs.blockSignals(False)
                sync_step_nav(env)
                return
        if cur == _STEP_EXECUTE_IDX and prev != _STEP_EXECUTE_IDX:
            if not bool(can_enter_execute_step(env)):
                env.tabs.blockSignals(True)
                env.tabs.setCurrentIndex(int(prev))
                env.tabs.blockSignals(False)
                sync_step_nav(env)
                return
        step_state["last_idx"] = int(cur)
        sync_step_nav(env)
        update_preview()

    env.tabs.currentChanged.connect(_on_tabs_current_changed)

