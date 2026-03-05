from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class IdRefGilCandidates:
    template_name_id_pairs: list[tuple[str, int]]
    instance_name_id_pairs: list[tuple[str, int]]


def scan_id_ref_gil_candidates_via_subprocess(
    *,
    workspace_root: Path,
    gil_file_path: Path,
    scan_templates: bool,
    scan_instances: bool,
) -> tuple[IdRefGilCandidates | None, str]:
    """
    在子进程中扫描一个 `.gil` 的“模板名/实例名→ID”候选列表，供导出中心 UI 手动覆盖使用。

    说明：
    - 使用 `tool export_center_scan_gil_id_ref_candidates`（解码放在子进程，避免 UI 进程闪退风险）。
    - 返回的是“候选全集”（按名称排序），不包含任何“缺失判断/回填策略”逻辑。
    """
    import json
    from uuid import uuid4

    from .._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

    ws_root = Path(workspace_root).resolve()
    gil_path = Path(gil_file_path).resolve()
    if not gil_path.is_file():
        return None, f"文件不存在：{str(gil_path)}"
    if gil_path.suffix.lower() != ".gil":
        return None, f"不是 .gil 文件：{str(gil_path)}"

    out_dir = (ws_root / "private_extensions" / "ugc_file_tools" / "out").resolve()
    tmp_dir = (out_dir / "_tmp_cli").resolve()
    tmp_dir.mkdir(parents=True, exist_ok=True)
    report_file = (tmp_dir / f"id_ref_candidates_{uuid4().hex[:10]}.json").resolve()

    argv: list[str] = [
        "tool",
        "export_center_scan_gil_id_ref_candidates",
        str(gil_path),
        "--report",
        str(report_file),
        "--decode-max-depth",
        "16",
    ]
    if bool(scan_templates):
        argv.append("--scan-templates")
    if bool(scan_instances):
        argv.append("--scan-instances")
    if not bool(scan_templates or scan_instances):
        raise ValueError("scan_templates/scan_instances 至少应开启一个")

    command = build_run_ugc_file_tools_command(workspace_root=ws_root, argv=argv)
    result = run_cli_with_progress(command=command, cwd=ws_root, on_progress=None, stderr_tail_max_lines=240)
    if int(result.exit_code) != 0:
        tail = [str(x) for x in list(result.stderr_tail)[-120:] if str(x).strip() != ""]
        tail_text = "\n".join(tail) if tail else "(stderr 为空)"
        return None, f"扫描 GIL 候选失败：exit_code={int(result.exit_code)}\n\n{tail_text}"

    if not report_file.is_file():
        raise FileNotFoundError(str(report_file))
    obj = json.loads(report_file.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise TypeError("candidates report must be dict")

    template_pairs: list[tuple[str, int]] = []
    raw_tpl = obj.get("component_name_to_id")
    if isinstance(raw_tpl, dict) and bool(scan_templates):
        for k, v in raw_tpl.items():
            name = str(k or "").strip()
            if name == "":
                continue
            if not isinstance(v, int) or int(v) <= 0:
                continue
            template_pairs.append((name, int(v)))
    template_pairs.sort(key=lambda t: (t[0].casefold(), int(t[1])))

    instance_pairs: list[tuple[str, int]] = []
    raw_inst = obj.get("entity_name_to_guid")
    if isinstance(raw_inst, dict) and bool(scan_instances):
        for k, v in raw_inst.items():
            name = str(k or "").strip()
            if name == "":
                continue
            if not isinstance(v, int) or int(v) <= 0:
                continue
            instance_pairs.append((name, int(v)))
    instance_pairs.sort(key=lambda t: (t[0].casefold(), int(t[1])))

    return (
        IdRefGilCandidates(
            template_name_id_pairs=list(template_pairs),
            instance_name_id_pairs=list(instance_pairs),
        ),
        "",
    )


def open_id_ref_override_picker_dialog(
    *,
    parent_dialog,
    title: str,
    placeholder_kind: str,  # "entity" | "component"
    placeholder_name: str,
    source_gil_path: Path,
    candidates: list[tuple[str, int]],
    preselected_id: int | None = None,
) -> tuple[str, int] | None:
    """
    打开“从地图/参考 GIL 选择一个 ID”的对话框。

    返回：
    - (candidate_name, candidate_id) 或 None（取消）
    """
    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation.theme_manager import Colors, Sizes

    kind = str(placeholder_kind or "").strip().lower()
    if kind not in {"entity", "component"}:
        raise ValueError(f"unsupported placeholder_kind: {placeholder_kind!r}")

    dlg = QtWidgets.QDialog(parent_dialog)
    dlg.setWindowTitle(str(title or "").strip() or "选择 ID")
    dlg.setModal(True)
    dlg.resize(860, 560)

    root = QtWidgets.QVBoxLayout(dlg)
    root.setContentsMargins(
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
        Sizes.PADDING_LARGE,
    )
    root.setSpacing(Sizes.SPACING_MEDIUM)

    header_lines: list[str] = []
    header_lines.append(str(title or "").strip() or "选择 ID")
    header_lines.append(f"占位符：{str(placeholder_name or '').strip()}")
    header_lines.append(f"候选来源：{str(Path(source_gil_path).resolve())}")
    header = QtWidgets.QLabel("\n".join(header_lines), dlg)
    header.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    root.addWidget(header)

    search_row = QtWidgets.QWidget(dlg)
    search_layout = QtWidgets.QHBoxLayout(search_row)
    search_layout.setContentsMargins(0, 0, 0, 0)
    search_layout.setSpacing(Sizes.SPACING_SMALL)

    search_edit = QtWidgets.QLineEdit(search_row)
    search_edit.setPlaceholderText("搜索（按名称/ID 片段过滤）…")
    stats_label = QtWidgets.QLabel("", search_row)
    stats_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
    search_layout.addWidget(search_edit, 1)
    search_layout.addWidget(stats_label)
    root.addWidget(search_row)

    table = QtWidgets.QTableWidget(dlg)
    table.setColumnCount(2)
    table.setHorizontalHeaderLabels(["名称", "ID"])
    table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    header2 = table.horizontalHeader()
    header2.setStretchLastSection(False)
    header2.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
    header2.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
    root.addWidget(table, 1)

    btn_box = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel,
        dlg,
    )
    ok_btn = btn_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
    ok_btn.setEnabled(False)
    btn_box.rejected.connect(dlg.reject)
    btn_box.accepted.connect(dlg.accept)
    root.addWidget(btn_box)

    all_items = list(candidates or [])

    # 本对话框不尝试做“虚拟列表/分页”；只做展示上限，避免在极端样本下把 UI 卡死。
    display_limit = 2400

    def _refresh_table() -> None:
        needle = str(search_edit.text() or "").strip().casefold()
        if needle == "":
            matched = all_items
        else:
            matched = []
            for n, cid in all_items:
                if needle in str(n).casefold() or needle in str(int(cid)):
                    matched.append((n, int(cid)))

        shown = matched[: int(display_limit)]
        stats_label.setText(f"候选={len(all_items)}  匹配={len(matched)}  展示={len(shown)}（上限 {display_limit}）")

        table.setUpdatesEnabled(False)
        table.blockSignals(True)
        table.setRowCount(int(len(shown)))
        for r, (name, cid) in enumerate(shown):
            it_name = QtWidgets.QTableWidgetItem(str(name))
            it_id = QtWidgets.QTableWidgetItem(str(int(cid)))
            # 额外存一份原始数据（避免从 text 反解析）
            it_name.setData(QtCore.Qt.ItemDataRole.UserRole, (str(name), int(cid)))
            it_name.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            it_id.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            table.setItem(int(r), 0, it_name)
            table.setItem(int(r), 1, it_id)
        table.blockSignals(False)
        table.setUpdatesEnabled(True)

        ok_btn.setEnabled(False)

        # 尝试恢复预选项（按 id 命中；同 id 多个 name 时取首个展示项）
        if isinstance(preselected_id, int) and int(preselected_id) > 0:
            for r in range(table.rowCount()):
                it0 = table.item(int(r), 0)
                payload = it0.data(QtCore.Qt.ItemDataRole.UserRole) if it0 is not None else None
                if isinstance(payload, tuple) and len(payload) == 2:
                    _n, _id = payload
                    if isinstance(_id, int) and int(_id) == int(preselected_id):
                        table.selectRow(int(r))
                        ok_btn.setEnabled(True)
                        break

    def _get_selected() -> tuple[str, int] | None:
        items = table.selectedItems()
        if not items:
            return None
        # 选中行为为整行，取第 0 列即可
        it0 = table.item(int(items[0].row()), 0)
        payload = it0.data(QtCore.Qt.ItemDataRole.UserRole) if it0 is not None else None
        if not isinstance(payload, tuple) or len(payload) != 2:
            return None
        name, cid = payload
        if not isinstance(name, str) or not isinstance(cid, int):
            return None
        name2 = str(name).strip()
        if name2 == "" or int(cid) <= 0:
            return None
        return name2, int(cid)

    table.itemSelectionChanged.connect(lambda: ok_btn.setEnabled(_get_selected() is not None))

    def _on_double_click(_item: QtWidgets.QTableWidgetItem) -> None:
        if _get_selected() is None:
            return
        dlg.accept()

    table.itemDoubleClicked.connect(_on_double_click)
    search_edit.textChanged.connect(lambda _t: _refresh_table())

    _refresh_table()

    if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    return _get_selected()


__all__ = [
    "IdRefGilCandidates",
    "scan_id_ref_gil_candidates_via_subprocess",
    "open_id_ref_override_picker_dialog",
]

