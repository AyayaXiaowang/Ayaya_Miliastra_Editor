from __future__ import annotations

from pathlib import Path
from typing import Callable

from .env import ExportCenterDialogWiringEnv

_REPAIR_SUFFIX = "_修复信号.gil"
_MERGE_SUFFIX = "_合并信号.gil"


def sync_repair_output_default(env: ExportCenterDialogWiringEnv) -> None:
    """根据输入 .gil 与当前模式同步修复输出路径的默认值。"""

    input_text = str(env.repair.repair_input_gil_edit.text() or "").strip()
    if input_text == "":
        return
    in_path = Path(input_text)
    if not in_path.is_absolute():
        return
    fmt = str(env.format_combo.currentData() or "repair_signals")
    suffix = _REPAIR_SUFFIX if fmt == "repair_signals" else (_MERGE_SUFFIX if fmt == "merge_signal_entries" else _REPAIR_SUFFIX)
    auto_output = str(in_path.with_name(f"{in_path.stem}{suffix}"))
    current_out = str(env.repair.repair_output_gil_edit.text() or "").strip()
    if current_out == "" or current_out == str(env.rt.repair_last_auto_output):
        env.repair.repair_output_gil_edit.setText(auto_output)
    env.rt.repair_last_auto_output = str(auto_output)


def wire_repair_output_sync(env: ExportCenterDialogWiringEnv, *, update_preview: Callable[[], None]) -> None:
    """连接修复输入框变化到默认输出同步与预览刷新。"""

    def _on_input_changed(*_args: object) -> None:
        """处理修复输入路径变化并触发预览刷新。"""

        sync_repair_output_default(env)
        update_preview()

    env.repair.repair_input_gil_edit.textChanged.connect(_on_input_changed)

