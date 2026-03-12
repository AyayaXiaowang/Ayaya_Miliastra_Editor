from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..export_center.write_ui_policy import compute_write_ui_effective_policy

from .env import ExportCenterDialogWiringEnv

_MIN_GRAPHS_FOR_PACK = 2


def sync_bundle_enabled_state(env: ExportCenterDialogWiringEnv) -> None:
    """同步 GIA 打包勾选的子选项可用性。"""

    enabled = bool(env.gia.bundle_enabled_cb.isChecked())
    env.gia.bundle_include_signals_cb.setEnabled(enabled)
    env.gia.bundle_include_ui_guid_cb.setEnabled(enabled)


def sync_pack_enabled_state(env: ExportCenterDialogWiringEnv) -> None:
    """同步“打包合并(.gia)”的可用性与提示文本。"""

    from ..graph_selection import build_graph_selection_from_resource_items

    selected_items = list(env.picker.get_selected_items())
    graph_sel = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
    )
    enabled = bool(env.gia.pack_graphs_cb.isChecked()) and int(len(graph_sel.graph_code_files)) >= _MIN_GRAPHS_FOR_PACK
    env.gia.pack_name_edit.setEnabled(enabled)
    if int(len(graph_sel.graph_code_files)) < _MIN_GRAPHS_FOR_PACK:
        env.gia.pack_graphs_cb.setEnabled(False)
        env.gia.pack_graphs_cb.setToolTip(f"至少需要选择 {_MIN_GRAPHS_FOR_PACK} 个节点图才能打包")
    else:
        env.gia.pack_graphs_cb.setEnabled(True)
        env.gia.pack_graphs_cb.setToolTip("")


def sync_ui_auto_sync_enabled_state(env: ExportCenterDialogWiringEnv) -> None:
    """同步“UI 自定义变量自动同步”复选框的可用性。"""

    env.gil.ui_auto_sync_vars_cb.setEnabled(bool(env.gil.write_ui_cb.isChecked()))


def sync_write_ui_effective_state(env: ExportCenterDialogWiringEnv) -> None:
    """同步“UI 写回”的强制策略与勾选框状态。"""

    fmt = str(env.format_combo.currentData() or "gia")
    selected_items = list(env.picker.get_selected_items())
    ui_src_selected = any(
        it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items
    )
    policy = compute_write_ui_effective_policy(
        fmt=str(fmt),
        ui_src_selected=bool(ui_src_selected),
        user_choice=bool(env.rt.write_ui_user_choice),
    )

    if bool(policy.forced):
        env.gil.write_ui_hint.setText(
            "已选择 UI源码：UI 写回将强制开启（此勾选框仅作展示）。\n若要关闭，请在左侧取消选择 UI源码。"
        )
        env.gil.write_ui_hint.setVisible(True)
        if not bool(env.gil.write_ui_cb.isChecked()):
            env.gil.write_ui_cb.blockSignals(True)
            env.gil.write_ui_cb.setChecked(True)
            env.gil.write_ui_cb.blockSignals(False)
        env.gil.write_ui_cb.setEnabled(False)
    else:
        env.gil.write_ui_hint.setText("")
        env.gil.write_ui_hint.setVisible(False)
        env.gil.write_ui_cb.setEnabled(True)
        if bool(env.gil.write_ui_cb.isChecked()) != bool(policy.effective_write_ui):
            env.gil.write_ui_cb.blockSignals(True)
            env.gil.write_ui_cb.setChecked(bool(policy.effective_write_ui))
            env.gil.write_ui_cb.blockSignals(False)

    sync_ui_auto_sync_enabled_state(env)


def handle_write_ui_toggled(env: ExportCenterDialogWiringEnv, *, update_preview: Callable[[], None]) -> None:
    """处理“UI 写回”勾选变化并触发预览刷新。"""

    if bool(env.gil.write_ui_cb.isEnabled()):
        env.rt.write_ui_user_choice = bool(env.gil.write_ui_cb.isChecked())
    sync_ui_auto_sync_enabled_state(env)
    update_preview()


def sync_builtin_empty_base_ui_state(env: ExportCenterDialogWiringEnv) -> None:
    """同步“使用内置空存档”开关对输入控件的禁用状态。"""

    use_builtin = bool(getattr(env.gil, "use_builtin_empty_base_cb").isChecked())
    env.gil.input_gil_edit.setEnabled(not bool(use_builtin))
    env.gil.input_gil_browse_btn.setEnabled(not bool(use_builtin))
    env.gil.recent_combo.setEnabled(not bool(use_builtin))
    env.gil.recent_use_btn.setEnabled(not bool(use_builtin))
    env.gil.recent_refresh_btn.setEnabled(not bool(use_builtin))


def handle_use_builtin_empty_base_toggled(
    env: ExportCenterDialogWiringEnv,
    *,
    update_preview: Callable[[], None],
) -> None:
    """处理“使用内置空存档”切换并触发预览刷新。"""

    from ..export_center.state import _save_last_use_builtin_empty_base_gil

    _save_last_use_builtin_empty_base_gil(
        workspace_root=Path(env.workspace_root),
        enabled=bool(env.gil.use_builtin_empty_base_cb.isChecked()),
    )
    sync_builtin_empty_base_ui_state(env)
    update_preview()


def wire_basic_sync_connections(
    env: ExportCenterDialogWiringEnv,
    *,
    update_preview: Callable[[], None],
) -> None:
    """连接基础开关与高级选项的 UI 信号。"""

    env.gia.gia_advanced_toggle.toggled.connect(lambda checked: env.gia.gia_advanced_box.setVisible(bool(checked)))
    env.gia.bundle_enabled_cb.stateChanged.connect(lambda *_: sync_bundle_enabled_state(env))
    env.gia.pack_graphs_cb.stateChanged.connect(lambda *_: sync_pack_enabled_state(env))

    env.gil.gil_advanced_toggle.toggled.connect(lambda checked: env.gil.gil_advanced_box.setVisible(bool(checked)))
    env.gil.write_ui_cb.toggled.connect(lambda *_: handle_write_ui_toggled(env, update_preview=update_preview))
    env.gil.use_builtin_empty_base_cb.toggled.connect(
        lambda *_: handle_use_builtin_empty_base_toggled(env, update_preview=update_preview)
    )

