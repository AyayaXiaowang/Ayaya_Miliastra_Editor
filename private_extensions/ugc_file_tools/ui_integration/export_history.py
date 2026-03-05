from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def _resolve_history_file_path(*, workspace_root: Path) -> Path:
    # 约定：运行期缓存位于 app/runtime/cache（默认应被忽略不入库）
    cache_dir = (Path(workspace_root).resolve() / "app" / "runtime" / "cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return (cache_dir / "ugc_file_tools_task_history.json").resolve()


def append_task_history_entry(*, workspace_root: Path, entry: Dict[str, Any]) -> None:
    path = _resolve_history_file_path(workspace_root=Path(workspace_root))
    items: List[Dict[str, Any]] = []
    if path.is_file():
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            items = [x for x in obj if isinstance(x, dict)]
    items.append(dict(entry))
    # 只保留最近 200 条，避免缓存文件无限增长
    if len(items) > 200:
        items = items[-200:]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class TaskHistoryEntry:
    ts: str
    kind: str
    title: str
    payload: Dict[str, Any]


def _load_history_entries(*, workspace_root: Path) -> List[TaskHistoryEntry]:
    path = _resolve_history_file_path(workspace_root=workspace_root)
    if not path.is_file():
        return []
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, list):
        return []
    entries: List[TaskHistoryEntry] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        ts = str(item.get("ts") or "").strip()
        kind = str(item.get("kind") or "").strip()
        title = str(item.get("title") or "").strip()
        if ts == "" or kind == "" or title == "":
            continue
        entries.append(TaskHistoryEntry(ts=ts, kind=kind, title=title, payload=dict(item)))
    entries.reverse()  # 最新在前
    return entries


def open_task_history_dialog(*, main_window: object) -> None:
    """打开“最近任务”对话框（只读：查看 manifest / 输出路径 / 复制详情）。"""
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes

    app_state = getattr(main_window, "app_state", None)
    if app_state is None:
        raise RuntimeError("主窗口缺少 app_state，无法读取任务历史")
    workspace_root = Path(getattr(app_state, "workspace_path")).resolve()

    entries = _load_history_entries(workspace_root=workspace_root)

    dialog = QtWidgets.QDialog(main_window)
    dialog.setWindowTitle("最近任务（导入/导出历史）")
    dialog.setModal(True)
    dialog.resize(980, 600)

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
    )
    layout.setSpacing(Sizes.SPACING_MEDIUM)

    hint = QtWidgets.QLabel(
        "说明：这里只记录“最近一次导入/导出”摘要与 manifest（用于复盘与排查）。\n"
        "文件位置：app/runtime/cache/ugc_file_tools_task_history.json",
        dialog,
    )
    hint.setWordWrap(True)
    hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    layout.addWidget(hint)

    splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, dialog)
    layout.addWidget(splitter, 1)

    list_widget = QtWidgets.QListWidget(splitter)
    detail = QtWidgets.QPlainTextEdit(splitter)
    detail.setReadOnly(True)
    detail.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
    splitter.setSizes([420, 560])

    def _format_payload(payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    for e in entries:
        item = QtWidgets.QListWidgetItem(f"{e.ts}  {e.title}")
        item.setData(QtCore.Qt.ItemDataRole.UserRole, e.payload)
        list_widget.addItem(item)

    if entries:
        list_widget.setCurrentRow(0)
        detail.setPlainText(_format_payload(entries[0].payload))
    else:
        detail.setPlainText("暂无记录。")

    def _on_selection_changed() -> None:
        items = list_widget.selectedItems()
        if not items:
            return
        payload = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(payload, dict):
            return
        detail.setPlainText(_format_payload(payload))

    list_widget.itemSelectionChanged.connect(_on_selection_changed)

    btn_row = QtWidgets.QHBoxLayout()
    btn_row.addStretch(1)
    copy_btn = QtWidgets.QPushButton("复制详情", dialog)
    close_btn = QtWidgets.QPushButton("关闭", dialog)

    def _copy_current() -> None:
        text = str(detail.toPlainText() or "")
        QtWidgets.QApplication.clipboard().setText(text)

    copy_btn.clicked.connect(_copy_current)
    close_btn.clicked.connect(dialog.reject)
    btn_row.addWidget(copy_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dialog.exec()


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")

