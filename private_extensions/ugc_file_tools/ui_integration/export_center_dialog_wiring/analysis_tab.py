from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..export_center.backfill_panel_models import (
    build_backfill_deps_rows,
    compute_backfill_signature_gia,
    compute_backfill_signature_gil,
)
from ..export_center.write_ui_policy import compute_write_ui_effective_policy

from .env import ExportCenterDialogWiringEnv

_BACKFILL_TAB_MISSING_IDX = 0
_BACKFILL_TAB_READY_IDX = 1

_COL_CATEGORY = 0
_COL_KEY = 1
_COL_VALUE = 2
_COL_STATUS = 3
_COL_NOTE = 4

_READY_STATUSES = frozenset({"OK", "一同导出"})


def _is_identify_running(env: ExportCenterDialogWiringEnv) -> bool:
    """判断回填识别 worker 是否处于运行中。"""

    existing_worker = getattr(env.main_window, "_export_center_gil_identify_worker", None)
    is_running = getattr(existing_worker, "isRunning", None)
    return bool(callable(is_running) and bool(is_running()))


def clear_backfill_identify_table(env: ExportCenterDialogWiringEnv, panel: object) -> None:
    """清空回填识别表格与进度行的 UI 状态。"""

    missing_table = getattr(panel, "missing_table", None)
    ready_table = getattr(panel, "ready_table", None)
    progress_bar = getattr(panel, "progress_bar", None)
    progress_row = getattr(panel, "progress_row", None)
    progress_label = getattr(panel, "progress_label", None)

    identify_running = _is_identify_running(env)
    if missing_table is not None:
        missing_table.setRowCount(0)
    if ready_table is not None:
        ready_table.setRowCount(0)
    if progress_bar is not None and not bool(identify_running):
        progress_bar.setRange(0, 1)
        progress_bar.setValue(0)
    if progress_label is not None and not bool(identify_running):
        progress_label.setText("")
    if progress_row is not None and not bool(identify_running):
        progress_row.setVisible(False)


def _mk_table_item(env: ExportCenterDialogWiringEnv, text: object):
    """创建不可编辑且可选择的 table item 并附带 tooltip。"""

    it = env.QtWidgets.QTableWidgetItem(str(text if text is not None else ""))
    it.setFlags(env.QtCore.Qt.ItemFlag.ItemIsEnabled | env.QtCore.Qt.ItemFlag.ItemIsSelectable)
    it.setToolTip(str(text if text is not None else ""))
    return it


def _fill_backfill_table(env: ExportCenterDialogWiringEnv, table: object, rows: list[dict[str, object]]) -> None:
    """用给定 rows 填充 backfill table 的行内容。"""

    table.setRowCount(int(len(rows)))
    missing_tip = "提示：双击该行可从地图/参考 .gil 的候选列表手动选择一个 ID（仅影响本次导出，不修改任何文件）。"
    for r, row in enumerate(list(rows)):
        category = row.get("category")
        key = row.get("key")
        value = row.get("value")
        status = row.get("status")
        note = row.get("note")

        it0 = _mk_table_item(env, category)
        it1 = _mk_table_item(env, key)
        it2 = _mk_table_item(env, value)
        it3 = _mk_table_item(env, status)
        it4 = _mk_table_item(env, note)

        if str(category) in {"实体ID(entity)", "元件ID(component)"} and str(status) == "缺失":
            for it in [it0, it1, it2, it3, it4]:
                base_tip = str(it.toolTip() or "").strip()
                it.setToolTip(f"{base_tip}\n\n{missing_tip}".strip() if base_tip else str(missing_tip))

        table.setItem(int(r), _COL_CATEGORY, it0)
        table.setItem(int(r), _COL_KEY, it1)
        table.setItem(int(r), _COL_VALUE, it2)
        table.setItem(int(r), _COL_STATUS, it3)
        table.setItem(int(r), _COL_NOTE, it4)
    table.resizeColumnsToContents()


def set_backfill_table_rows(env: ExportCenterDialogWiringEnv, panel: object, *, rows: list[dict[str, object]]) -> None:
    """将 rows 分组填充到“缺失/已就绪”两个 backfill 表格并更新 tabs 标题。"""

    missing_table = getattr(panel, "missing_table", None)
    ready_table = getattr(panel, "ready_table", None)
    tabs = getattr(panel, "tabs", None)
    if missing_table is None or ready_table is None or tabs is None:
        return

    missing_table.setSortingEnabled(False)
    ready_table.setSortingEnabled(False)

    missing_rows: list[dict[str, object]] = []
    ready_rows: list[dict[str, object]] = []
    for row in list(rows):
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip()
        if status in _READY_STATUSES:
            ready_rows.append(dict(row))
        else:
            missing_rows.append(dict(row))

    _fill_backfill_table(env, missing_table, missing_rows)
    _fill_backfill_table(env, ready_table, ready_rows)

    tabs.setTabText(_BACKFILL_TAB_MISSING_IDX, f"缺失/待修复 ({int(len(missing_rows))})")
    tabs.setTabText(_BACKFILL_TAB_READY_IDX, f"已就绪 ({int(len(ready_rows))})")
    if int(len(missing_rows)) > 0:
        tabs.setCurrentIndex(_BACKFILL_TAB_MISSING_IDX)
    elif int(len(ready_rows)) > 0:
        tabs.setCurrentIndex(_BACKFILL_TAB_READY_IDX)

    env.rt.backfill_current_rows = [dict(r) for r in list(rows) if isinstance(r, dict)]


def _set_analysis_strategy_text(env: ExportCenterDialogWiringEnv, lines: list[str]) -> None:
    """设置回填分析页的策略说明文本。"""

    env.analysis.strategy_text.setPlainText("\n".join([str(x) for x in list(lines) if str(x).strip()]).strip())


def _update_analysis_tab_for_unsupported_modes(env: ExportCenterDialogWiringEnv) -> bool:
    """在不支持回填识别的模式下刷新分析页并返回 True。"""

    fmt = str(env.format_combo.currentData() or "gia")
    if fmt not in {"repair_signals", "merge_signal_entries"}:
        return False

    _set_analysis_strategy_text(
        env,
        [
            "本模式不会执行 entity_key/component_key/ui_key 等回填识别。",
            (
                "执行时会：先根据所选节点图导出临时 .gia（用于提取信号名称），再对目标 .gil 执行信号修复。"
                if fmt == "repair_signals"
                else "执行时会：对目标 .gil 执行 signal entry 合并（keep/remove），并重绑引用。"
            ),
            "输出会生成新的 .gil（不覆盖原文件）。",
        ],
    )
    panel = env.analysis.backfill_panel
    panel.target_label.setText("识别目标：<当前模式不支持>")
    clear_backfill_identify_table(env, panel)
    panel.identify_btn.setEnabled(False)
    panel.identify_btn.setToolTip("当前模式不支持识别。")
    env.rt.backfill_pending_rows = []
    env.rt.backfill_last_identify_report = None
    env.rt.backfill_current_rows = []
    return True


def _update_analysis_tab_for_gia(env: ExportCenterDialogWiringEnv) -> None:
    """刷新 GIA 模式下的回填分析页。"""

    from ..graph_selection import build_graph_selection_from_resource_items

    identify_running = _is_identify_running(env)
    selected_items = list(env.picker.get_selected_items())
    graph_sel0 = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
    )
    graphs_total = int(len(graph_sel0.graph_code_files))
    panel = env.analysis.backfill_panel

    base_text_user = str(env.gia.base_gil_edit.text() or "").strip()
    id_ref_text = str(env.gia.gia_id_ref_edit.text() or "").strip()
    rid0 = str(env.gia.ui_export_record_combo.currentData() or "").strip() if not env.gia.ui_export_record_row.isHidden() else ""
    ui_export_record_id = rid0 if rid0 != "" else None

    identify_base_text = str(base_text_user)
    identify_base_note = "基底 .gil" if identify_base_text else ""
    if identify_base_text == "" and ui_export_record_id is not None:
        from ugc_file_tools.ui.export_records import try_get_ui_export_record_by_id

        rec0 = try_get_ui_export_record_by_id(
            workspace_root=Path(env.workspace_root),
            package_id=str(env.package_id),
            record_id=str(ui_export_record_id),
        )
        if rec0 is not None:
            out_gil = str(rec0.payload.get("output_gil_file") or "").strip()
            if out_gil != "":
                identify_base_text = str(out_gil)
                identify_base_note = "来自 UI 回填记录"
    if identify_base_text == "" and id_ref_text != "":
        identify_base_text = str(id_ref_text)
        identify_base_note = "回退：占位符参考"

    pending_rows = build_backfill_deps_rows(
        fmt="gia",
        graphs_total=int(graphs_total),
        id_ref_usage=env.rt.id_ref_usage_for_selected_graphs,
        ui_keys=env.rt.ui_keys_for_selected_graphs,
        selected_level_custom_variable_ids=[],
        level_custom_variable_meta_by_id=None,
    )
    env.rt.backfill_pending_rows = list(pending_rows)

    allow_ui_key_zero = bool(env.gia.allow_unresolved_ui_keys_cb.isChecked())
    _set_analysis_strategy_text(
        env,
        [
            "实体/元件占位符（entity_key/component_key）：默认来自“基底 .gil”；可选用“占位符参考 .gil”覆盖；缺失同名=回填为 0。",
            "UIKey（ui_key/ui）：优先使用 UI 回填记录快照；缺失时默认阻断导出。",
            f"当前 UIKey 缺失策略：{'允许回填为 0 并继续导出' if allow_ui_key_zero else '缺失将阻断导出（推荐）'}。",
            "识别仅用于对比：不会修改任何文件。",
        ],
    )

    base_line = f"base .gil：{identify_base_text}（{identify_base_note}）" if identify_base_text else "base .gil：<未选择>"
    id_ref_line = (
        f"占位符参考 .gil：{id_ref_text}"
        if id_ref_text
        else ("占位符参考 .gil：<留空=使用 base .gil>" if identify_base_text else "占位符参考 .gil：<未选择；entity/component 将回填为 0>")
    )
    panel.target_label.setText("\n".join([base_line, id_ref_line]).strip())

    target_ok = False
    disable_reason = ""
    if not graph_sel0.graph_code_files:
        disable_reason = "请先在步骤1选择至少一张节点图后再识别。"
    elif not identify_base_text:
        disable_reason = "请先选择基底 .gil（或选择 UI 回填记录）后再识别。"
    else:
        p2 = Path(identify_base_text).resolve()
        target_ok = bool(p2.is_file() and p2.suffix.lower() == ".gil")
        if not target_ok:
            disable_reason = "base .gil 无效：请选择一个存在的 .gil 文件后再识别。"
    panel.identify_btn.setEnabled(bool(target_ok) if not bool(identify_running) else False)
    panel.identify_btn.setToolTip("识别中…" if identify_running else ("" if target_ok else str(disable_reason)))
    if bool(identify_running):
        panel.progress_row.setVisible(True)

    sig_gia = compute_backfill_signature_gia(
        id_ref_usage=env.rt.id_ref_usage_for_selected_graphs,
        ui_keys=env.rt.ui_keys_for_selected_graphs,
        target_gil_text=str(identify_base_text),
        id_ref_gil_text=str(id_ref_text),
        ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
        graphs_total=int(graphs_total),
    )
    if tuple(sig_gia) != tuple(env.rt.backfill_last_signature_gia):
        clear_backfill_identify_table(env, panel)
        env.rt.backfill_last_signature_gia = tuple(sig_gia)
        env.rt.backfill_last_identify_report = None
        set_backfill_table_rows(env, panel, rows=list(pending_rows))
    elif int(panel.missing_table.rowCount() + panel.ready_table.rowCount()) == 0 and pending_rows and not bool(identify_running):
        set_backfill_table_rows(env, panel, rows=list(pending_rows))


def _update_analysis_tab_for_gil(env: ExportCenterDialogWiringEnv) -> None:
    """刷新 GIL 模式下的回填分析页。"""

    from ..graph_selection import build_graph_selection_from_resource_items

    identify_running = _is_identify_running(env)
    selected_items = list(env.picker.get_selected_items())
    graph_sel0 = build_graph_selection_from_resource_items(
        selected_items=selected_items,
        workspace_root=Path(env.workspace_root),
        package_id=str(env.package_id),
    )
    graphs_total = int(len(graph_sel0.graph_code_files))
    panel = env.analysis.backfill_panel

    use_builtin_empty_base = bool(getattr(env.gil, "use_builtin_empty_base_cb").isChecked())
    if use_builtin_empty_base:
        from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

        base_gil_path = get_builtin_empty_base_gil_path()
        base_text = "（内置空存档）"
    else:
        base_text = str(env.gil.input_gil_edit.text() or "").strip()
        base_gil_path = Path(base_text).resolve() if base_text else None

    id_ref_text = str(env.gil.gil_id_ref_edit.text() or "").strip()
    rid1 = str(env.gil.gil_ui_export_record_combo.currentData() or "").strip() if not env.gil.gil_ui_export_record_row.isHidden() else ""
    ui_export_record_id = rid1 if rid1 != "" else None
    ui_src_selected = any(
        it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items
    )
    policy = compute_write_ui_effective_policy(
        fmt="gil",
        ui_src_selected=bool(ui_src_selected),
        user_choice=bool(env.rt.write_ui_user_choice),
    )

    pending_rows = build_backfill_deps_rows(
        fmt="gil",
        graphs_total=int(graphs_total),
        id_ref_usage=env.rt.id_ref_usage_for_selected_graphs,
        ui_keys=env.rt.ui_keys_for_selected_graphs,
        selected_level_custom_variable_ids=list(env.gil.selected_level_custom_variable_ids or []),
        level_custom_variable_meta_by_id=dict(env.gil.level_custom_variable_meta_by_id or {}),
    )
    env.rt.backfill_pending_rows = list(pending_rows)

    ui_mode_text = "强制开启（因 UI源码）" if bool(policy.forced) else ("开启" if bool(policy.effective_write_ui) else "关闭")
    auto_sync_text = "开启" if bool(policy.effective_write_ui and env.gil.ui_auto_sync_vars_cb.isChecked()) else "关闭"
    ui_record_text = str(ui_export_record_id) if ui_export_record_id is not None else "<不指定>"
    _set_analysis_strategy_text(
        env,
        [
            "实体/元件占位符（entity_key/component_key）：来自“占位符参考 .gil”（留空=使用基础 .gil；缺失同名=回填为 0）。",
            f"UI 回填记录：{ui_record_text}（若指定，将优先使用快照映射判定 UIKey；否则使用 base UI records 反查）。",
            "UIKey（ui_key/ui）：用于节点图占位符回填；缺失时会回填为 0，并在报告列出。",
            f"UI 写回：{ui_mode_text}；UI 自定义变量自动同步：{auto_sync_text}。",
            "关卡实体自定义变量：左侧勾选“关卡实体自定义变量（全部）”后会自动全量补齐写入（仅补齐缺失；同名不同类型默认不覆盖）。",
            "识别仅用于对比：不会修改任何文件。",
        ],
    )

    base_line = f"base .gil：{base_text}" if base_text else "base .gil：<未选择>"
    ref_line = f"占位符参考 .gil：{id_ref_text}" if id_ref_text else "占位符参考 .gil：<留空=使用 base .gil>"
    panel.target_label.setText("\n".join([base_line, ref_line]).strip())

    target_ok = False
    disable_reason = ""
    if not graph_sel0.graph_code_files:
        disable_reason = "请先在步骤1选择至少一张节点图后再识别。"
    elif base_gil_path is None:
        disable_reason = "请选择基础 .gil（或勾选“使用内置空存档”）后再识别。"
    else:
        target_ok = bool(base_gil_path.is_file() and base_gil_path.suffix.lower() == ".gil")
        if not target_ok:
            disable_reason = "基础 .gil 无效：请选择一个存在的 .gil 文件后再识别。"
    panel.identify_btn.setEnabled(bool(target_ok) if not bool(identify_running) else False)
    panel.identify_btn.setToolTip("识别中…" if identify_running else ("" if target_ok else str(disable_reason)))
    if bool(identify_running):
        panel.progress_row.setVisible(True)

    sig_gil = compute_backfill_signature_gil(
        id_ref_usage=env.rt.id_ref_usage_for_selected_graphs,
        ui_keys=env.rt.ui_keys_for_selected_graphs,
        target_gil_text=str(base_text),
        id_ref_gil_text=str(id_ref_text),
        use_base_as_id_ref_fallback=True,
        selected_level_custom_variable_ids=list(env.gil.selected_level_custom_variable_ids or []),
        write_ui_effective=bool(policy.effective_write_ui),
        ui_auto_sync_enabled=bool(env.gil.ui_auto_sync_vars_cb.isChecked()),
        ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
        graphs_total=int(graphs_total),
    )
    if tuple(sig_gil) != tuple(env.rt.backfill_last_signature_gil):
        clear_backfill_identify_table(env, panel)
        env.rt.backfill_last_signature_gil = tuple(sig_gil)
        env.rt.backfill_last_identify_report = None
        set_backfill_table_rows(env, panel, rows=list(pending_rows))
    elif int(panel.missing_table.rowCount() + panel.ready_table.rowCount()) == 0 and pending_rows and not bool(identify_running):
        set_backfill_table_rows(env, panel, rows=list(pending_rows))


def update_analysis_tab(env: ExportCenterDialogWiringEnv) -> None:
    """刷新回填分析页的依赖清单/识别目标/表格与按钮状态。"""

    if bool(_update_analysis_tab_for_unsupported_modes(env)):
        return
    fmt = str(env.format_combo.currentData() or "gia")
    if fmt == "gia":
        _update_analysis_tab_for_gia(env)
    else:
        _update_analysis_tab_for_gil(env)


def _get_missing_table_cell_text(env: ExportCenterDialogWiringEnv, table: object, r: int, c: int) -> str:
    """读取缺失表格单元格文本并去除两端空白。"""

    it = table.item(int(r), int(c))
    return str(it.text() or "").strip() if it is not None else ""


def _pick_component_id_override(env: ExportCenterDialogWiringEnv, *, key: str, ref_gil: Path) -> tuple[str, str, int] | None:
    """打开元件 ID 候选选择对话框并返回选择结果。"""

    from app.ui.foundation import dialog_utils
    from ..export_center.id_ref_override_picker import (
        open_id_ref_override_picker_dialog,
        scan_id_ref_gil_candidates_via_subprocess,
    )

    gil_cf = str(ref_gil.as_posix()).casefold()
    cached = env.rt.id_ref_template_candidates_by_gil_cf.get(gil_cf)
    if cached is None:
        scanned, err = scan_id_ref_gil_candidates_via_subprocess(
            workspace_root=Path(env.workspace_root),
            gil_file_path=Path(ref_gil),
            scan_templates=True,
            scan_instances=False,
        )
        if scanned is None:
            dialog_utils.show_warning_dialog(env.dialog, "扫描失败", str(err or "扫描候选失败。"))
            return None
        cached = list(scanned.template_name_id_pairs)
        env.rt.id_ref_template_candidates_by_gil_cf[gil_cf] = list(cached)

    preselected = env.rt.id_ref_override_component_name_to_id.get(key)
    picked = open_id_ref_override_picker_dialog(
        parent_dialog=env.dialog,
        title="选择元件ID（来自地图/参考 GIL）",
        placeholder_kind="component",
        placeholder_name=str(key),
        source_gil_path=Path(ref_gil),
        candidates=list(cached),
        preselected_id=(int(preselected) if isinstance(preselected, int) and int(preselected) > 0 else None),
    )
    if picked is None:
        return None
    cand_name, cand_id = picked
    return (str(key), str(cand_name), int(cand_id))


def _pick_entity_id_override(env: ExportCenterDialogWiringEnv, *, key: str, ref_gil: Path) -> tuple[str, str, int] | None:
    """打开实体 ID 候选选择对话框并返回选择结果。"""

    from app.ui.foundation import dialog_utils
    from ..export_center.id_ref_override_picker import (
        open_id_ref_override_picker_dialog,
        scan_id_ref_gil_candidates_via_subprocess,
    )

    gil_cf = str(ref_gil.as_posix()).casefold()
    cached = env.rt.id_ref_instance_candidates_by_gil_cf.get(gil_cf)
    if cached is None:
        scanned, err = scan_id_ref_gil_candidates_via_subprocess(
            workspace_root=Path(env.workspace_root),
            gil_file_path=Path(ref_gil),
            scan_templates=False,
            scan_instances=True,
        )
        if scanned is None:
            dialog_utils.show_warning_dialog(env.dialog, "扫描失败", str(err or "扫描候选失败。"))
            return None
        cached = list(scanned.instance_name_id_pairs)
        env.rt.id_ref_instance_candidates_by_gil_cf[gil_cf] = list(cached)

    preselected = env.rt.id_ref_override_entity_name_to_guid.get(key)
    picked = open_id_ref_override_picker_dialog(
        parent_dialog=env.dialog,
        title="选择实体ID（来自地图/参考 GIL）",
        placeholder_kind="entity",
        placeholder_name=str(key),
        source_gil_path=Path(ref_gil),
        candidates=list(cached),
        preselected_id=(int(preselected) if isinstance(preselected, int) and int(preselected) > 0 else None),
    )
    if picked is None:
        return None
    cand_name, cand_id = picked
    return (str(key), str(cand_name), int(cand_id))


def _apply_id_override_to_rows(env: ExportCenterDialogWiringEnv, *, category: str, key: str, value_text: str, note_text: str) -> None:
    """将手动覆盖结果写回当前 rows 并触发表格刷新。"""

    panel = env.analysis.backfill_panel
    current_rows = list(getattr(env.rt, "backfill_current_rows", []) or [])
    for r0 in current_rows:
        if not isinstance(r0, dict):
            continue
        if str(r0.get("category") or "") == str(category) and str(r0.get("key") or "") == str(key):
            r0["value"] = str(value_text)
            r0["status"] = "OK"
            r0["note"] = str(note_text)
            break
    env.rt.backfill_current_rows = [dict(x) for x in current_rows if isinstance(x, dict)]
    set_backfill_table_rows(env, panel, rows=list(env.rt.backfill_current_rows))


def on_backfill_table_item_double_clicked(env: ExportCenterDialogWiringEnv, item: object) -> None:
    """处理回填缺失表格双击并允许用户手动选择覆盖 ID。"""

    from app.ui.foundation import dialog_utils

    panel = env.analysis.backfill_panel
    table = getattr(panel, "missing_table", None)
    if table is None or item is None:
        return
    row = int(getattr(item, "row", lambda: -1)())
    if row < 0 or row >= int(table.rowCount()):
        return

    category = _get_missing_table_cell_text(env, table, row, _COL_CATEGORY)
    key = _get_missing_table_cell_text(env, table, row, _COL_KEY)
    status = _get_missing_table_cell_text(env, table, row, _COL_STATUS)
    if category not in {"实体ID(entity)", "元件ID(component)"} or status != "缺失" or key == "":
        return

    report = env.rt.backfill_last_identify_report
    if not isinstance(report, dict):
        dialog_utils.show_warning_dialog(env.dialog, "提示", "请先点击“识别”生成对比表后，再对缺失项进行手动选择。")
        return

    id_ref_path_text = str(report.get("id_ref_gil_path") or "").strip()
    base_path_text = str(report.get("base_gil_path") or "").strip()
    ref_text = id_ref_path_text or base_path_text
    if ref_text == "":
        dialog_utils.show_warning_dialog(env.dialog, "提示", "未找到本次识别使用的参考 GIL 路径，请重新识别后再尝试。")
        return
    ref_gil = Path(ref_text).resolve()
    if (not ref_gil.is_file()) or ref_gil.suffix.lower() != ".gil":
        dialog_utils.show_warning_dialog(env.dialog, "提示", f"参考 GIL 无效或不存在：{str(ref_gil)}")
        return

    if category == "元件ID(component)":
        picked = _pick_component_id_override(env, key=str(key), ref_gil=Path(ref_gil))
        if picked is None:
            return
        placeholder_name, cand_name, cand_id = picked
        env.rt.id_ref_override_component_name_to_id[str(placeholder_name)] = int(cand_id)
        value_text = str(int(cand_id))
        note_text = f"手动覆盖：{placeholder_name} → {cand_name} ({int(cand_id)})"
    else:
        picked2 = _pick_entity_id_override(env, key=str(key), ref_gil=Path(ref_gil))
        if picked2 is None:
            return
        placeholder_name2, cand_name2, cand_id2 = picked2
        env.rt.id_ref_override_entity_name_to_guid[str(placeholder_name2)] = int(cand_id2)
        value_text = str(int(cand_id2))
        note_text = f"手动覆盖：{placeholder_name2} → {cand_name2} ({int(cand_id2)})"

    _apply_id_override_to_rows(
        env,
        category=str(category),
        key=str(key),
        value_text=str(value_text),
        note_text=str(note_text),
    )


def wire_analysis_tab(
    env: ExportCenterDialogWiringEnv,
    *,
    update_analysis_tab: Callable[[], None],
) -> None:
    """连接回填分析页的识别按钮、双击覆盖与关卡变量联动。"""

    from ..export_center.dialog_actions import start_export_center_backfill_identify_action

    env.analysis.backfill_panel.identify_btn.clicked.connect(
        lambda: start_export_center_backfill_identify_action(
            QtCore=env.QtCore,
            main_window=env.main_window,
            dialog=env.dialog,
            workspace_root=Path(env.workspace_root),
            package_id=str(env.package_id),
            project_root=Path(env.project_root),
            picker=env.picker,
            format_combo=env.format_combo,
            gia=env.gia,
            gil=env.gil,
            panel=env.analysis.backfill_panel,
            rt=env.rt,
            set_backfill_table_rows=lambda panel, rows: set_backfill_table_rows(env, panel, rows=list(rows)),
            update_backfill_panels=lambda: update_analysis_tab(),
        )
    )
    env.analysis.backfill_panel.missing_table.itemDoubleClicked.connect(lambda it: on_backfill_table_item_double_clicked(env, it))
    env.gil.level_vars_select_btn.clicked.connect(lambda: update_analysis_tab())
    env.gil.level_vars_clear_btn.clicked.connect(lambda: update_analysis_tab())

