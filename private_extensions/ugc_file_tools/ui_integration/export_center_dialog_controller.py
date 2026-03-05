from __future__ import annotations

from pathlib import Path
from typing import Any

from ._common import IdRefPlaceholderUsage, ToolbarProgressWidgetSpec, make_toolbar_progress_widget_cls
from .export_center.backfill_panel_models import (
    build_backfill_deps_rows,
    compute_backfill_signature_gia,
    compute_backfill_signature_gil,
)
from .export_center.dialog_actions import (
    start_export_center_action,
    start_export_center_backfill_identify_action,
)
from .export_center.dialog_runtime_state import ExportCenterDialogRuntimeState
from .export_center.mgmt_cfg_ids import _collect_writeback_ids_from_mgmt_cfg_items
from .export_center.preview_models import (
    build_gia_preview_texts,
    build_gil_preview_texts,
    build_merge_signal_entries_preview_texts,
    build_repair_signals_preview_texts,
)
from .export_center.write_ui_policy import compute_write_ui_effective_policy
from .export_center_dialog_plan_validators import (
    _scan_id_ref_usage_for_graphs,
    validate_gia_plan,
    validate_gil_plan,
    validate_merge_signal_entries_plan,
    validate_repair_signals_plan,
)
from .export_center_dialog_types import ExportCenterFooter, ExportCenterLeftPane, ExportCenterRightPane


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
    from .graph_selection import build_graph_selection_from_resource_items

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

    def _sync_bundle_enabled_state(*_args: object) -> None:
        enabled = bool(gia.bundle_enabled_cb.isChecked())
        gia.bundle_include_signals_cb.setEnabled(enabled)
        gia.bundle_include_ui_guid_cb.setEnabled(enabled)

    def _sync_pack_enabled_state(*_args: object) -> None:
        selected_items = list(picker.get_selected_items())
        graph_sel = build_graph_selection_from_resource_items(
            selected_items=selected_items,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
        )
        enabled = bool(gia.pack_graphs_cb.isChecked()) and int(len(graph_sel.graph_code_files)) >= 2
        gia.pack_name_edit.setEnabled(enabled)
        if int(len(graph_sel.graph_code_files)) < 2:
            gia.pack_graphs_cb.setEnabled(False)
            gia.pack_graphs_cb.setToolTip("至少需要选择 2 个节点图才能打包")
        else:
            gia.pack_graphs_cb.setEnabled(True)
            gia.pack_graphs_cb.setToolTip("")

    def _sync_ui_auto_sync_enabled_state(*_args: object) -> None:
        gil.ui_auto_sync_vars_cb.setEnabled(bool(gil.write_ui_cb.isChecked()))

    def _sync_write_ui_effective_state(*_args: object) -> None:
        fmt = str(format_combo.currentData() or "gia")
        selected_items = list(picker.get_selected_items())
        # 仅 project scope 的 UI源码 选择才会触发 “UI 写回强制开启”。
        ui_src_selected = any(
            it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items
        )
        policy = compute_write_ui_effective_policy(
            fmt=str(fmt),
            ui_src_selected=bool(ui_src_selected),
            user_choice=bool(rt.write_ui_user_choice),
        )

        if bool(policy.forced):
            gil.write_ui_hint.setText(
                "已选择 UI源码：UI 写回将强制开启（此勾选框仅作展示）。\n若要关闭，请在左侧取消选择 UI源码。"
            )
            gil.write_ui_hint.setVisible(True)
            if not bool(gil.write_ui_cb.isChecked()):
                gil.write_ui_cb.blockSignals(True)
                gil.write_ui_cb.setChecked(True)
                gil.write_ui_cb.blockSignals(False)
            gil.write_ui_cb.setEnabled(False)
        else:
            gil.write_ui_hint.setText("")
            gil.write_ui_hint.setVisible(False)
            gil.write_ui_cb.setEnabled(True)
            if bool(gil.write_ui_cb.isChecked()) != bool(policy.effective_write_ui):
                gil.write_ui_cb.blockSignals(True)
                gil.write_ui_cb.setChecked(bool(policy.effective_write_ui))
                gil.write_ui_cb.blockSignals(False)

        _sync_ui_auto_sync_enabled_state()

    def _update_ui_export_record_detail_text(*_args: object) -> None:
        rid2 = str(gia.ui_export_record_combo.currentData() or "").strip()
        if rid2 == "":
            gia.ui_export_record_detail.setText("自动使用当前 UI GUID registry")
            return
        rec2 = rt.ui_export_records_by_id.get(rid2)
        if rec2 is None:
            gia.ui_export_record_detail.setText("未找到记录详情")
            return
        from .ui_export_record_picker import format_ui_export_record_detail_text

        gia.ui_export_record_detail.setText(format_ui_export_record_detail_text(rec2))

    def _clear_backfill_identify_table(panel: object) -> None:
        # 兼容：旧逻辑会在签名变化时清空表格。新交互改为“保留依赖行，只重置识别结果”。
        # 该函数仅负责清空 UI 状态（表格内容由调用方决定）。
        missing_table = getattr(panel, "missing_table", None)
        ready_table = getattr(panel, "ready_table", None)
        progress_bar = getattr(panel, "progress_bar", None)
        progress_row = getattr(panel, "progress_row", None)
        progress_label = getattr(panel, "progress_label", None)

        identify_running = False
        existing_worker = getattr(main_window, "_export_center_gil_identify_worker", None)
        is_running = getattr(existing_worker, "isRunning", None)
        if callable(is_running) and bool(is_running()):
            identify_running = True
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

    def _set_backfill_table_rows(panel: object, *, rows: list[dict[str, object]]) -> None:
        missing_table = getattr(panel, "missing_table", None)
        ready_table = getattr(panel, "ready_table", None)
        tabs = getattr(panel, "tabs", None)
        if missing_table is None or ready_table is None or tabs is None:
            return
        missing_table.setSortingEnabled(False)
        ready_table.setSortingEnabled(False)

        READY = {"OK", "一同导出"}
        missing_rows: list[dict[str, object]] = []
        ready_rows: list[dict[str, object]] = []
        for row in list(rows):
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").strip()
            if status in READY:
                ready_rows.append(dict(row))
            else:
                missing_rows.append(dict(row))

        def _mk_item(text: object):
            it = QtWidgets.QTableWidgetItem(str(text if text is not None else ""))
            it.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            return it

        def _fill(table: object, rows2: list[dict[str, object]]) -> None:
            table.setRowCount(int(len(rows2)))
            for r, row in enumerate(list(rows2)):
                category = row.get("category")
                key = row.get("key")
                value = row.get("value")
                status = row.get("status")
                note = row.get("note")

                it0 = _mk_item(category)
                it1 = _mk_item(key)
                it2 = _mk_item(value)
                it3 = _mk_item(status)
                it4 = _mk_item(note)

                if str(category) in {"实体ID(entity)", "元件ID(component)"} and str(status) == "缺失":
                    tip = "提示：双击该行可从地图/参考 .gil 的候选列表手动选择一个 ID（仅影响本次导出，不修改任何文件）。"
                    for it in [it0, it1, it2, it3, it4]:
                        it.setToolTip(str(tip))

                table.setItem(int(r), 0, it0)
                table.setItem(int(r), 1, it1)
                table.setItem(int(r), 2, it2)
                table.setItem(int(r), 3, it3)
                table.setItem(int(r), 4, it4)
            table.resizeColumnsToContents()

        _fill(missing_table, missing_rows)
        _fill(ready_table, ready_rows)

        tabs.setTabText(0, f"缺失/待修复 ({int(len(missing_rows))})")
        tabs.setTabText(1, f"已就绪 ({int(len(ready_rows))})")
        if int(len(missing_rows)) > 0:
            tabs.setCurrentIndex(0)
        elif int(len(ready_rows)) > 0:
            tabs.setCurrentIndex(1)

        rt.backfill_current_rows = [dict(r) for r in list(rows) if isinstance(r, dict)]
        # 交互收敛：不提供“清空结果”按钮；如需重跑识别，直接再次点击“识别”。

    def _update_analysis_tab(*_args: object) -> None:
        identify_running = False
        existing_worker = getattr(main_window, "_export_center_gil_identify_worker", None)
        is_running = getattr(existing_worker, "isRunning", None)
        if callable(is_running) and bool(is_running()):
            identify_running = True

        selected_items = list(picker.get_selected_items())
        graph_sel0 = build_graph_selection_from_resource_items(
            selected_items=selected_items,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
        )
        fmt = str(format_combo.currentData() or "gia")
        panel = analysis.backfill_panel
        graphs_total = int(len(graph_sel0.graph_code_files))

        if fmt in {"repair_signals", "merge_signal_entries"}:
            analysis.strategy_text.setPlainText(
                "\n".join(
                    [
                        "本模式不会执行 entity_key/component_key/ui_key 等回填识别。",
                        (
                            "执行时会：先根据所选节点图导出临时 .gia（用于提取信号名称），再对目标 .gil 执行信号修复。"
                            if fmt == "repair_signals"
                            else "执行时会：对目标 .gil 执行 signal entry 合并（keep/remove），并重绑引用。"
                        ),
                        "输出会生成新的 .gil（不覆盖原文件）。",
                    ]
                ).strip()
            )
            panel.target_label.setText("识别目标：<当前模式不支持>")
            _clear_backfill_identify_table(panel)
            panel.identify_btn.setEnabled(False)
            panel.identify_btn.setToolTip("当前模式不支持识别。")
            rt.backfill_pending_rows = []
            rt.backfill_last_identify_report = None
            rt.backfill_current_rows = []
            return

        if fmt == "gia":
            base_text_user = str(gia.base_gil_edit.text() or "").strip()
            id_ref_text = str(gia.gia_id_ref_edit.text() or "").strip()
            rid0 = str(gia.ui_export_record_combo.currentData() or "").strip() if not gia.ui_export_record_row.isHidden() else ""
            ui_export_record_id = rid0 if rid0 != "" else None

            identify_base_text = str(base_text_user)
            identify_base_note = "基底 .gil" if identify_base_text else ""
            if identify_base_text == "" and ui_export_record_id is not None:
                from ugc_file_tools.ui.export_records import try_get_ui_export_record_by_id

                rec0 = try_get_ui_export_record_by_id(
                    workspace_root=Path(workspace_root),
                    package_id=str(package_id),
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
                id_ref_usage=rt.id_ref_usage_for_selected_graphs,
                ui_keys=rt.ui_keys_for_selected_graphs,
                selected_level_custom_variable_ids=[],
                level_custom_variable_meta_by_id=None,
            )
            rt.backfill_pending_rows = list(pending_rows)

            allow_ui_key_zero = bool(gia.allow_unresolved_ui_keys_cb.isChecked())
            analysis.strategy_text.setPlainText(
                "\n".join(
                    [
                        "实体/元件占位符（entity_key/component_key）：默认来自“基底 .gil”；可选用“占位符参考 .gil”覆盖；缺失同名=回填为 0。",
                        "UIKey（ui_key/ui）：优先使用 UI 回填记录快照；缺失时默认阻断导出。",
                        f"当前 UIKey 缺失策略：{'允许回填为 0 并继续导出' if allow_ui_key_zero else '缺失将阻断导出（推荐）'}。",
                        "识别仅用于对比：不会修改任何文件。",
                    ]
                ).strip()
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
                id_ref_usage=rt.id_ref_usage_for_selected_graphs,
                ui_keys=rt.ui_keys_for_selected_graphs,
                target_gil_text=str(identify_base_text),
                id_ref_gil_text=str(id_ref_text),
                ui_export_record_id=(str(ui_export_record_id) if ui_export_record_id is not None else None),
                graphs_total=int(graphs_total),
            )
            if tuple(sig_gia) != tuple(rt.backfill_last_signature_gia):
                _clear_backfill_identify_table(panel)
                rt.backfill_last_signature_gia = tuple(sig_gia)
                rt.backfill_last_identify_report = None
                _set_backfill_table_rows(panel, rows=list(pending_rows))
            elif int(panel.missing_table.rowCount() + panel.ready_table.rowCount()) == 0 and pending_rows and not bool(identify_running):
                _set_backfill_table_rows(panel, rows=list(pending_rows))
            return

        # fmt == "gil"
        use_builtin_empty_base = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
        if use_builtin_empty_base:
            from ugc_file_tools.gil.builtin_empty_base import get_builtin_empty_base_gil_path

            base_gil_path = get_builtin_empty_base_gil_path()
            base_text = "（内置空存档）"
        else:
            base_text = str(gil.input_gil_edit.text() or "").strip()
            base_gil_path = Path(base_text).resolve() if base_text else None
        id_ref_text2 = str(gil.gil_id_ref_edit.text() or "").strip()
        rid1 = str(gil.gil_ui_export_record_combo.currentData() or "").strip() if not gil.gil_ui_export_record_row.isHidden() else ""
        ui_export_record_id2 = rid1 if rid1 != "" else None
        ui_src_selected = any(
            it.category == "ui_src" and str(getattr(it, "source_root", "")) == "project" for it in selected_items
        )
        policy2 = compute_write_ui_effective_policy(
            fmt="gil",
            ui_src_selected=bool(ui_src_selected),
            user_choice=bool(rt.write_ui_user_choice),
        )
        pending_rows2 = build_backfill_deps_rows(
            fmt="gil",
            graphs_total=int(graphs_total),
            id_ref_usage=rt.id_ref_usage_for_selected_graphs,
            ui_keys=rt.ui_keys_for_selected_graphs,
            selected_level_custom_variable_ids=list(gil.selected_level_custom_variable_ids or []),
            level_custom_variable_meta_by_id=dict(gil.level_custom_variable_meta_by_id or {}),
        )
        rt.backfill_pending_rows = list(pending_rows2)

        ui_mode_text = "强制开启（因 UI源码）" if bool(policy2.forced) else ("开启" if bool(policy2.effective_write_ui) else "关闭")
        auto_sync_text = "开启" if bool(policy2.effective_write_ui and gil.ui_auto_sync_vars_cb.isChecked()) else "关闭"
        ui_record_text = str(ui_export_record_id2) if ui_export_record_id2 is not None else "<不指定>"
        analysis.strategy_text.setPlainText(
            "\n".join(
                [
                    "实体/元件占位符（entity_key/component_key）：来自“占位符参考 .gil”（留空=使用基础 .gil；缺失同名=回填为 0）。",
                    f"UI 回填记录：{ui_record_text}（若指定，将优先使用快照映射判定 UIKey；否则使用 base UI records 反查）。",
                    "UIKey（ui_key/ui）：用于节点图占位符回填；缺失时会回填为 0，并在报告列出。",
                    f"UI 写回：{ui_mode_text}；UI 自定义变量自动同步：{auto_sync_text}。",
                    "关卡实体自定义变量：左侧勾选“关卡实体自定义变量（全部）”后会自动全量补齐写入（仅补齐缺失；同名不同类型默认不覆盖）。",
                    "识别仅用于对比：不会修改任何文件。",
                ]
            ).strip()
        )

        base_line = f"base .gil：{base_text}" if base_text else "base .gil：<未选择>"
        ref_line = f"占位符参考 .gil：{id_ref_text2}" if id_ref_text2 else "占位符参考 .gil：<留空=使用 base .gil>"
        panel.target_label.setText("\n".join([base_line, ref_line]).strip())
        target_ok2 = False
        disable_reason2 = ""
        if not graph_sel0.graph_code_files:
            disable_reason2 = "请先在步骤1选择至少一张节点图后再识别。"
        elif base_gil_path is None:
            disable_reason2 = "请选择基础 .gil（或勾选“使用内置空存档”）后再识别。"
        else:
            target_ok2 = bool(base_gil_path.is_file() and base_gil_path.suffix.lower() == ".gil")
            if not target_ok2:
                disable_reason2 = "基础 .gil 无效：请选择一个存在的 .gil 文件后再识别。"
        panel.identify_btn.setEnabled(bool(target_ok2) if not bool(identify_running) else False)
        panel.identify_btn.setToolTip("识别中…" if identify_running else ("" if target_ok2 else str(disable_reason2)))
        if bool(identify_running):
            panel.progress_row.setVisible(True)

        sig_gil = compute_backfill_signature_gil(
            id_ref_usage=rt.id_ref_usage_for_selected_graphs,
            ui_keys=rt.ui_keys_for_selected_graphs,
            target_gil_text=str(base_text),
            id_ref_gil_text=str(id_ref_text2),
            use_base_as_id_ref_fallback=True,
            selected_level_custom_variable_ids=list(gil.selected_level_custom_variable_ids or []),
            write_ui_effective=bool(policy2.effective_write_ui),
            ui_auto_sync_enabled=bool(gil.ui_auto_sync_vars_cb.isChecked()),
            ui_export_record_id=(str(ui_export_record_id2) if ui_export_record_id2 is not None else None),
            graphs_total=int(graphs_total),
        )
        if tuple(sig_gil) != tuple(rt.backfill_last_signature_gil):
            _clear_backfill_identify_table(panel)
            rt.backfill_last_signature_gil = tuple(sig_gil)
            rt.backfill_last_identify_report = None
            _set_backfill_table_rows(panel, rows=list(pending_rows2))
        elif int(panel.missing_table.rowCount() + panel.ready_table.rowCount()) == 0 and pending_rows2 and not bool(identify_running):
            _set_backfill_table_rows(panel, rows=list(pending_rows2))

    def _update_ui_export_record_ui(*_args: object) -> None:
        selected_items = list(picker.get_selected_items())
        fmt = str(format_combo.currentData() or "gia")
        graph_sel = build_graph_selection_from_resource_items(
            selected_items=selected_items,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
        )
        if fmt in {"repair_signals", "merge_signal_entries"}:
            rt.id_ref_usage_for_selected_graphs = IdRefPlaceholderUsage(entity_names=frozenset(), component_names=frozenset())
            rt.ui_keys_for_selected_graphs = frozenset()
            rt.ui_key_layout_hints_by_key = {}
            gia.ui_export_record_row.setVisible(False)
            gil.gil_ui_export_record_row.setVisible(False)
            gia.base_gil_row.setVisible(False)
            gia.gia_id_ref_row.setVisible(False)
            gil.gil_id_ref_row.setVisible(False)
            _update_analysis_tab()
            return
        if not graph_sel.graph_code_files:
            rt.id_ref_usage_for_selected_graphs = IdRefPlaceholderUsage(entity_names=frozenset(), component_names=frozenset())
            rt.ui_keys_for_selected_graphs = frozenset()
            rt.ui_key_layout_hints_by_key = {}
            gia.ui_export_record_row.setVisible(False)
            gil.gil_ui_export_record_row.setVisible(False)
            gia.base_gil_row.setVisible(False)
            gia.gia_id_ref_row.setVisible(False)
            gil.gil_id_ref_row.setVisible(False)
            _update_analysis_tab()
            return

        gia.base_gil_row.setVisible(True)
        gia.gia_id_ref_row.setVisible(True)
        gil.gil_id_ref_row.setVisible(True)

        id_ref_usage = _scan_id_ref_usage_for_graphs(graph_code_files=list(graph_sel.graph_code_files))
        rt.id_ref_usage_for_selected_graphs = id_ref_usage
        gia.base_gil_edit.setPlaceholderText(
            (
                "建议：选择基底 .gil（用于 entity_key/component_key 回填）"
                if bool(id_ref_usage.is_used)
                else "可选：选择基底 .gil（用于 entity_key/component_key 回填）"
            )
        )
        gia.gia_id_ref_edit.setPlaceholderText(
            (
                "可选：占位符参考 .gil（覆盖基底；留空=使用基底 .gil；缺失同名=回填为 0）"
                if bool(id_ref_usage.is_used)
                else "可选：占位符参考 .gil（覆盖基底；留空=使用基底 .gil）"
            )
        )

        from .export_center.backfill_inspector import scan_ui_key_placeholders_in_graph_code_files

        ui_usage = scan_ui_key_placeholders_in_graph_code_files(graph_code_files=list(graph_sel.graph_code_files))
        rt.ui_keys_for_selected_graphs = frozenset(ui_usage.ui_keys)
        rt.ui_key_layout_hints_by_key = dict(ui_usage.layout_hints_by_ui_key)

        from .ui_export_record_picker import (
            graph_code_files_need_ui_export_record,
            load_ui_export_record_options,
        )

        need = graph_code_files_need_ui_export_record(graph_code_files=list(graph_sel.graph_code_files))
        if not bool(need):
            gia.ui_export_record_row.setVisible(False)
            gil.gil_ui_export_record_row.setVisible(False)
            _update_analysis_tab()
            return

        options = load_ui_export_record_options(workspace_root=Path(workspace_root), package_id=str(package_id))

        rt.ui_export_records_by_id.clear()
        gia.ui_export_record_combo.blockSignals(True)
        gia.ui_export_record_combo.clear()
        gia.ui_export_record_combo.addItem("自动（使用最新 UI 导出记录）", "")
        for opt in list(options):
            rid = str(opt.get("record_id") or "").strip()
            label = str(opt.get("label") or "").strip()
            rec = opt.get("record")
            if rid == "" or label == "" or rec is None:
                continue
            gia.ui_export_record_combo.addItem(label, rid)
            rt.ui_export_records_by_id[rid] = rec
        if gia.ui_export_record_combo.count() > 1:
            gia.ui_export_record_combo.setCurrentIndex(1)
        gia.ui_export_record_combo.blockSignals(False)

        _update_ui_export_record_detail_text()
        gia.ui_export_record_row.setVisible(True)

        prev_gil_rid = str(gil.gil_ui_export_record_combo.currentData() or "").strip()
        gil.gil_ui_export_record_combo.blockSignals(True)
        gil.gil_ui_export_record_combo.clear()
        gil.gil_ui_export_record_combo.addItem("（不指定）", "")
        for opt in list(options):
            rid = str(opt.get("record_id") or "").strip()
            label = str(opt.get("label") or "").strip()
            if rid == "" or label == "":
                continue
            gil.gil_ui_export_record_combo.addItem(label, rid)
        if prev_gil_rid != "":
            prev_idx = int(gil.gil_ui_export_record_combo.findData(prev_gil_rid))
            gil.gil_ui_export_record_combo.setCurrentIndex(prev_idx if prev_idx >= 0 else 0)
        else:
            gil.gil_ui_export_record_combo.setCurrentIndex(0)
        gil.gil_ui_export_record_combo.blockSignals(False)
        gil.gil_ui_export_record_row.setVisible(True)

        _update_analysis_tab()

    def _update_preview(*_args: object) -> None:
        selected_items = list(picker.get_selected_items())
        graphs_count = sum(1 for it in selected_items if it.category == "graphs")
        templates_count = sum(1 for it in selected_items if it.category == "templates")
        instances_count = sum(1 for it in selected_items if it.category == "instances")
        player_templates_count = sum(1 for it in selected_items if it.category == "player_templates")
        mgmt_count = sum(1 for it in selected_items if it.category == "mgmt_cfg")
        ui_src_count = sum(1 for it in selected_items if it.category == "ui_src")
        custom_vars_count = sum(1 for it in selected_items if it.category == "custom_vars")

        signal_ids, basic_struct_ids, ingame_struct_ids = _collect_writeback_ids_from_mgmt_cfg_items(selected_items)

        fmt = str(format_combo.currentData() or "gia")
        gia.player_template_base_gia_row.setVisible(bool(fmt == "gia") and int(player_templates_count) > 0)
        # === UI 勾选联动：UI 引用到的自定义变量必须在“已选资源”里一同勾选 ===
        if fmt == "gil":
            DEFER_SELECTION_UPDATE_DELAY_MS = 0
            selected_ui_html_files = [
                Path(it.absolute_path).resolve()
                for it in selected_items
                if str(getattr(it, "category", "") or "") == "ui_src"
                and str(getattr(it, "source_root", "") or "") == "project"
                and str(Path(it.absolute_path).suffix).lower() in {".html", ".htm"}
            ]
            selected_ui_html_files.sort(key=lambda x: x.as_posix().casefold())

            from ugc_file_tools.auto_custom_variable_registry_bridge import OWNER_LEVEL, OWNER_PLAYER
            from ugc_file_tools.auto_custom_variable_registry_bridge import (
                try_load_auto_custom_variable_registry_index_from_project_root,
            )
            from ugc_file_tools.node_graph_writeback.ui_custom_variable_sync import (
                scan_ui_html_files_for_placeholder_variable_refs_and_defaults,
            )
            from ugc_file_tools.ui_integration.resource_picker import build_custom_var_owner_select_all_item_key_for_project

            package_root = (Path(workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(package_id)).resolve()

            # UI 未勾选：撤销自动勾选的变量条目（只移除“自动添加”的集合）
            if not selected_ui_html_files:
                if getattr(rt, "ui_auto_selected_custom_var_keys", None):
                    # 重要：不要在资源树 itemChanged/selection_changed 的回调栈内直接修改 selection，
                    # 避免 Qt 侧 re-entrancy 导致的崩溃（用户反馈“勾选 UI 立即闪退”）。
                    keys_to_remove = list(rt.ui_auto_selected_custom_var_keys)
                    rt.ui_auto_selected_custom_var_keys = set()
                    if keys_to_remove:
                        QtCore.QTimer.singleShot(
                            DEFER_SELECTION_UPDATE_DELAY_MS,
                            lambda keys=keys_to_remove: picker.remove_keys(list(keys)),
                        )
                        return
            else:
                idx = try_load_auto_custom_variable_registry_index_from_project_root(project_root=package_root)
                if idx is not None:
                    scan = scan_ui_html_files_for_placeholder_variable_refs_and_defaults(selected_ui_html_files)
                    required: set[tuple[str, str]] = set()
                    for g, n, _path in set(scan.variable_refs or set()):
                        gg = str(g or "").strip()
                        nn = str(n or "").strip()
                        if gg and nn:
                            required.add((gg, nn))
                    for full_name in dict(scan.normalized_variable_defaults or {}).keys():
                        full = str(full_name or "").strip()
                        if "." not in full:
                            continue
                        g, _, n = full.partition(".")
                        if str(g).strip() and str(n).strip():
                            required.add((str(g).strip(), str(n).strip()))

                    group_to_owner = {"关卡": OWNER_LEVEL, "玩家自身": OWNER_PLAYER}
                    auto_keys: set[str] = set()
                    for group_name, var_name in sorted(required, key=lambda t: (t[0].casefold(), t[1].casefold())):
                        owner = group_to_owner.get(str(group_name))
                        if owner is None:
                            continue
                        # 按 owner 粒度整组选：只要 UI 引用到任一变量，就勾选该 owner 的（全部）。
                        auto_keys.add(build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner)))

                    # 同步缓存 + 程序化勾选（缺少条目会被 add_keys 忽略；写回阶段仍会 fail-fast）
                    rt.ui_auto_selected_custom_var_keys = set(auto_keys)
                    to_add = sorted(set(auto_keys) - set(picker.get_selected_keys()), key=lambda s: str(s).casefold())
                    if to_add:
                        # 同上：避免在回调栈内做“选中集变更 → rebuild_tree”导致 re-entrancy 崩溃
                        QtCore.QTimer.singleShot(
                            DEFER_SELECTION_UPDATE_DELAY_MS,
                            lambda keys=to_add: picker.add_keys(list(keys)),
                        )
                        return

            # === 元件/实体勾选联动：选中资源后，资源绑定的自定义变量 owner 也必须一同勾选（整组） ===
            def _load_json_index_map(*, index_path: Path, id_key: str) -> dict[str, tuple[str, str]]:
                """
                返回：abs_path_cf -> (owner_ref(id), display_name)
                """
                if not index_path.is_file():
                    return {}
                obj = json.loads(index_path.read_text(encoding="utf-8"))
                if not isinstance(obj, list):
                    return {}
                out: dict[str, tuple[str, str]] = {}
                for item in obj:
                    if not isinstance(item, dict):
                        continue
                    rid = str(item.get(id_key) or "").strip()
                    nm = str(item.get("name") or "").strip()
                    rel_out = str(item.get("output") or "").replace("\\", "/").strip()
                    if not rid or not rel_out:
                        continue
                    abs_path = (package_root / rel_out).resolve()
                    out[str(abs_path).casefold()] = (rid, nm)
                return out

            import json  # local import: avoid adding weight to module import time

            templates_map = _load_json_index_map(
                index_path=(package_root / "元件库" / "templates_index.json").resolve(),
                id_key="template_id",
            )
            instances_map = _load_json_index_map(
                index_path=(package_root / "实体摆放" / "instances_index.json").resolve(),
                id_key="instance_id",
            )

            desired_asset_keys: set[str] = set()
            for it in selected_items:
                cat = str(getattr(it, "category", "") or "")
                if cat not in {"templates", "instances"}:
                    continue
                if str(getattr(it, "source_root", "") or "") != "project":
                    continue
                abs_cf = str(Path(it.absolute_path).resolve()).casefold()
                if cat == "templates":
                    ref = templates_map.get(abs_cf)
                    if ref is None:
                        continue
                    owner_ref, display = ref
                    desired_asset_keys.add(
                        build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner_ref), owner_display=str(display))
                    )
                else:
                    ref = instances_map.get(abs_cf)
                    if ref is None:
                        continue
                    owner_ref, display = ref
                    desired_asset_keys.add(
                        build_custom_var_owner_select_all_item_key_for_project(owner_ref=str(owner_ref), owner_display=str(display))
                    )

            current_asset_auto = set(getattr(rt, "asset_auto_selected_custom_var_keys", set()) or set())
            # remove stale
            to_remove_asset = sorted(current_asset_auto - set(desired_asset_keys), key=lambda s: str(s).casefold())
            if to_remove_asset:
                rt.asset_auto_selected_custom_var_keys = set(desired_asset_keys)
                QtCore.QTimer.singleShot(
                    DEFER_SELECTION_UPDATE_DELAY_MS,
                    lambda keys=to_remove_asset: picker.remove_keys(list(keys)),
                )
                return

            # add missing
            rt.asset_auto_selected_custom_var_keys = set(desired_asset_keys)
            to_add_asset = sorted(set(desired_asset_keys) - set(picker.get_selected_keys()), key=lambda s: str(s).casefold())
            if to_add_asset:
                QtCore.QTimer.singleShot(
                    DEFER_SELECTION_UPDATE_DELAY_MS,
                    lambda keys=to_add_asset: picker.add_keys(list(keys)),
                )
                return

        # === 右侧 GIL 页“关卡实体变量”预览：复用旧字段（仅用于展示与回填识别） ===
        if fmt == "gil":
            level_ids: list[str] = []
            level_meta: dict[str, dict[str, str]] = {}
            for it in selected_items:
                if str(getattr(it, "category", "")) != "custom_vars":
                    continue
                meta = getattr(it, "meta", None)
                m = meta if isinstance(meta, dict) else {}
                owner_ref = str(m.get("owner_ref") or "").strip().lower()
                if owner_ref != "level":
                    continue
                if str(m.get("select_all") or "").strip() == "1":
                    # 扩展：全选关卡 owner（按注册表真源）
                    from ugc_file_tools.auto_custom_variable_registry_bridge import (
                        try_load_auto_custom_variable_registry_index_from_project_root,
                    )

                    package_root = (Path(workspace_root).resolve() / "assets" / "资源库" / "项目存档" / str(package_id)).resolve()
                    idx2 = try_load_auto_custom_variable_registry_index_from_project_root(project_root=package_root)
                    if idx2 is not None:
                        for payload in idx2.payloads_by_owner_and_name.get("level", {}).values():
                            vid = str(payload.get("variable_id") or "").strip()
                            vname = str(payload.get("variable_name") or "").strip()
                            vtype = str(payload.get("variable_type") or "").strip()
                            if vid:
                                level_ids.append(vid)
                                level_meta[vid] = {"variable_id": vid, "variable_name": vname, "variable_type": vtype, "source": str(idx2.registry_path)}
                    continue
                vid = str(m.get("variable_id") or "").strip()
                if vid:
                    level_ids.append(vid)
                    level_meta[vid] = {
                        "variable_id": vid,
                        "variable_name": str(m.get("variable_name") or ""),
                        "variable_type": str(m.get("variable_type") or ""),
                        "source": str(getattr(it, "absolute_path", "")),
                    }
            # 去重保持顺序
            seen: set[str] = set()
            level_ids_dedup: list[str] = []
            for vid in level_ids:
                k = str(vid).casefold()
                if k in seen:
                    continue
                seen.add(k)
                level_ids_dedup.append(str(vid))
            gil.selected_level_custom_variable_ids[:] = list(level_ids_dedup)
            gil.level_custom_variable_meta_by_id.clear()
            gil.level_custom_variable_meta_by_id.update(dict(level_meta))

            level_vars_count = len(list(gil.selected_level_custom_variable_ids or []))
            if int(level_vars_count) <= 0:
                gil.level_vars_preview.setText("未选择任何关卡实体自定义变量。导出时不会修改关卡实体 override_variables。")
            else:
                names: list[str] = []
                for vid in list(gil.selected_level_custom_variable_ids or []):
                    meta = gil.level_custom_variable_meta_by_id.get(str(vid))
                    n = str(meta.get("variable_name") or "").strip() if isinstance(meta, dict) else ""
                    names.append(n if n != "" else str(vid))
                shown = ", ".join(names[:8])
                suffix = "" if len(names) <= 8 else f" …（共 {len(names)} 个）"
                gil.level_vars_preview.setText(f"已选择：{len(names)} 个（{shown}{suffix}）")
        else:
            gil.selected_level_custom_variable_ids[:] = []
            gil.level_custom_variable_meta_by_id.clear()
            gil.level_vars_preview.setText("")

        # 左侧“已选资源”摘要：只展示“已选条目统计”，避免把写回细节/强制策略塞进中间栏造成视觉噪音。
        # 详细计划仍收口到“步骤3：执行”的预览文本；这里仅保留 tooltip 便于快速核对。
        summary_parts: list[str] = []
        if int(graphs_count) > 0:
            summary_parts.append(f"节点图={int(graphs_count)}")
        if int(templates_count) > 0:
            summary_parts.append(f"元件={int(templates_count)}")
        if int(player_templates_count) > 0:
            summary_parts.append(f"玩家模板={int(player_templates_count)}")
        if int(instances_count) > 0:
            summary_parts.append(f"实体摆放={int(instances_count)}")
        if int(ui_src_count) > 0:
            summary_parts.append(f"UI源码={int(ui_src_count)}")
        if int(mgmt_count) > 0:
            summary_parts.append(f"信号/结构体={int(mgmt_count)}")
        if int(custom_vars_count) > 0:
            summary_parts.append(f"自定义变量={int(custom_vars_count)}")
        summary_text = ("已选：" + "  ".join(list(summary_parts))) if summary_parts else "未选择任何资源。"
        summary_tooltip = ""

        if fmt == "gia":
            model = build_gia_preview_texts(
                package_id=str(package_id),
                graphs_count=int(graphs_count),
                templates_count=int(templates_count),
                mgmt_cfg_count=int(mgmt_count),
                signal_ids_total=int(len(signal_ids)),
                basic_struct_ids_total=int(len(basic_struct_ids)),
                ingame_struct_ids_total=int(len(ingame_struct_ids)),
                out_dir_name=str(gia.out_dir_edit.text() or ""),
                copy_dir=str(gia.copy_dir_edit.text() or ""),
                base_gil_row_visible=bool(gia.base_gil_row.isVisible()),
                base_gil_text=str(gia.base_gil_edit.text() or ""),
                id_ref_row_visible=bool(gia.gia_id_ref_row.isVisible()),
                id_ref_text=str(gia.gia_id_ref_edit.text() or ""),
                id_ref_is_used=bool(rt.id_ref_usage_for_selected_graphs.is_used),
                player_templates_count=int(player_templates_count),
                player_template_base_gia_row_visible=bool(gia.player_template_base_gia_row.isVisible()),
                player_template_base_gia_text=str(gia.player_template_base_gia_edit.text() or ""),
            )
            execute.plan_preview_text.setPlainText(str(model.preview_text))
            summary_tooltip = str(model.summary_tooltip)
        elif fmt == "gil":
            use_builtin_empty_base2 = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
            input_text = "（内置空存档）" if use_builtin_empty_base2 else str(gil.input_gil_edit.text() or "").strip()
            output_text = str(gil.output_gil_edit.text() or "").strip() or f"{package_id}.gil"
            ui_src_selected = int(ui_src_count) > 0
            policy = compute_write_ui_effective_policy(
                fmt="gil",
                ui_src_selected=bool(ui_src_selected),
                user_choice=bool(rt.write_ui_user_choice),
            )
            forced_ui = bool(policy.forced)
            want_ui = bool(policy.effective_write_ui)
            graph_sel = build_graph_selection_from_resource_items(
                selected_items=selected_items,
                workspace_root=Path(workspace_root),
                package_id=str(package_id),
            )
            rid3 = str(gil.gil_ui_export_record_combo.currentData() or "").strip()
            model2 = build_gil_preview_texts(
                package_id=str(package_id),
                templates_count=int(templates_count),
                instances_count=int(instances_count),
                graphs_total=int(len(graph_sel.graph_code_files)),
                level_custom_variables_total=int(level_vars_count),
                signal_ids_total=int(len(signal_ids)),
                basic_struct_ids_total=int(len(basic_struct_ids)),
                ingame_struct_ids_total=int(len(ingame_struct_ids)),
                input_gil_text=str(input_text),
                output_gil_text=str(output_text),
                forced_ui=bool(forced_ui),
                write_ui_effective=bool(want_ui),
                ui_auto_sync_enabled=bool(gil.ui_auto_sync_vars_cb.isChecked()),
                prefer_signal_specific_type_id=bool(gil.prefer_signal_specific_type_id_cb.isChecked()),
                id_ref_row_visible=bool(gil.gil_id_ref_row.isVisible()),
                id_ref_text=str(gil.gil_id_ref_edit.text() or ""),
                ui_export_record_row_visible=bool(gil.gil_ui_export_record_row.isVisible()),
                ui_export_record_id=str(rid3),
            )
            execute.plan_preview_text.setPlainText(str(model2.preview_text))
            summary_tooltip = str(model2.summary_tooltip)
        elif fmt == "repair_signals":
            input_text3 = str(repair.repair_input_gil_edit.text() or "").strip()
            output_text3 = str(repair.repair_output_gil_edit.text() or "").strip()
            graph_sel3 = build_graph_selection_from_resource_items(
                selected_items=selected_items,
                workspace_root=Path(workspace_root),
                package_id=str(package_id),
            )
            model3 = build_repair_signals_preview_texts(
                package_id=str(package_id),
                graphs_total=int(len(graph_sel3.graph_code_files)),
                input_gil_text=str(input_text3),
                output_gil_text=str(output_text3),
                prune_placeholder_orphans=bool(repair.repair_prune_orphans_cb.isChecked()),
            )
            execute.plan_preview_text.setPlainText(str(model3.preview_text))
            summary_tooltip = str(model3.summary_tooltip)
        elif fmt == "merge_signal_entries":
            input_text4 = str(repair.repair_input_gil_edit.text() or "").strip()
            output_text4 = str(repair.repair_output_gil_edit.text() or "").strip()
            model4 = build_merge_signal_entries_preview_texts(
                package_id=str(package_id),
                input_gil_text=str(input_text4),
                output_gil_text=str(output_text4),
                keep_signal_name=str(repair.merge_keep_signal_edit.text() or ""),
                remove_signal_name=str(repair.merge_remove_signal_edit.text() or ""),
                rename_keep_to=str(repair.merge_rename_keep_to_edit.text() or ""),
                patch_composite_pin_index=bool(repair.merge_patch_cpi_cb.isChecked()),
            )
            execute.plan_preview_text.setPlainText(str(model4.preview_text))
            summary_tooltip = str(model4.summary_tooltip)
        else:
            execute.plan_preview_text.setPlainText("（未知模式）")
            summary_tooltip = ""

        prune_note = str(getattr(rt, "selection_pruned_note", "") or "").strip()
        if prune_note:
            summary_text = f"{summary_text}\n{prune_note}"
            rt.selection_pruned_note = ""

        if not selected_items:
            if fmt == "merge_signal_entries":
                summary_text = "合并信号条目模式：无需勾选资源。"
            elif fmt == "gil":
                # GIL 模式存在“非资源勾选”的选择来源（例如关卡实体自定义变量、UI 写回），
                # 不能仅以 selected_items 为空就提示“未选择任何资源”。
                ui_src_selected2 = int(ui_src_count) > 0
                policy2 = compute_write_ui_effective_policy(
                    fmt="gil",
                    ui_src_selected=bool(ui_src_selected2),
                    user_choice=bool(rt.write_ui_user_choice),
                )
                if bool(level_vars_count) or bool(policy2.effective_write_ui):
                    pass
                else:
                    summary_text = "未选择任何资源。"
                    summary_tooltip = ""
                    execute.plan_preview_text.setPlainText("未选择任何资源。")
            else:
                summary_text = "未选择任何资源。"
                summary_tooltip = ""
                execute.plan_preview_text.setPlainText("未选择任何资源。")
        left.selected_summary_label.setText(str(summary_text))
        left.selected_summary_label.setToolTip(str(summary_tooltip))

        _update_analysis_tab()

    def _sync_repair_output_default(*_args: object) -> None:
        input_text = str(repair.repair_input_gil_edit.text() or "").strip()
        if input_text == "":
            return
        in_path = Path(input_text)
        if not in_path.is_absolute():
            return
        fmt = str(format_combo.currentData() or "repair_signals")
        suffix = "_修复信号.gil" if fmt == "repair_signals" else ("_合并信号.gil" if fmt == "merge_signal_entries" else "_修复信号.gil")
        auto_output = str(in_path.with_name(f"{in_path.stem}{suffix}"))
        current_out = str(repair.repair_output_gil_edit.text() or "").strip()
        if current_out == "" or current_out == str(rt.repair_last_auto_output):
            repair.repair_output_gil_edit.setText(auto_output)
        rt.repair_last_auto_output = str(auto_output)

    def _sync_left_selected_list() -> None:
        left.selected_list.clear()
        for it in sorted(list(picker.get_selected_items()), key=lambda x: x.key.casefold()):
            prefix = "项目" if it.source_root == "project" else "共享"
            display = str(getattr(picker, "get_item_display_text")(it))
            text = f"[{prefix}] {display} — {it.relative_path}"
            item = QtWidgets.QListWidgetItem(text)
            item.setToolTip(str(it.absolute_path))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, str(it.key))
            left.selected_list.addItem(item)

    def _remove_selected_from_left_list() -> None:
        keys = [
            str(x.data(QtCore.Qt.ItemDataRole.UserRole) or "").strip()
            for x in left.selected_list.selectedItems()
        ]
        keys = [k for k in keys if k]
        if keys:
            picker.remove_keys(keys)

    def _clear_left_selection() -> None:
        picker.clear_selection()

    left.selected_remove_btn.clicked.connect(_remove_selected_from_left_list)
    left.selected_clear_btn.clicked.connect(_clear_left_selection)
    picker.selection_changed.connect(_sync_left_selected_list)

    def _update_format_ui(*_args: object) -> None:
        fmt = str(format_combo.currentData() or "gia")
        if fmt == "gia":
            stacked.setCurrentWidget(gia.page)
            removed = picker.set_allowed_categories({"graphs", "templates", "player_templates", "mgmt_cfg"}, prune_selection=True)
            if int(removed) > 0:
                rt.selection_pruned_note = f"提示：切换到 GIA 模式后，已自动移除 {int(removed)} 项不支持的勾选。"
            run_btn.setText("开始导出")
            repair.repair_auto_box.setVisible(True)
            repair.merge_entries_box.setVisible(True)
        elif fmt == "gil":
            stacked.setCurrentWidget(gil.page)
            removed = picker.set_allowed_categories(
                {"graphs", "templates", "instances", "ui_src", "custom_vars", "mgmt_cfg"},
                prune_selection=True,
            )
            if int(removed) > 0:
                rt.selection_pruned_note = f"提示：切换到 GIL 模式后，已自动移除 {int(removed)} 项不支持的勾选。"
            run_btn.setText("开始导出")
            repair.repair_auto_box.setVisible(True)
            repair.merge_entries_box.setVisible(True)
        elif fmt == "repair_signals":
            stacked.setCurrentWidget(repair.page)
            removed = picker.set_allowed_categories({"graphs"}, prune_selection=True)
            if int(removed) > 0:
                rt.selection_pruned_note = f"提示：切换到『修复信号』模式后，已自动移除 {int(removed)} 项不支持的勾选。"
            run_btn.setText("开始修复")
            repair.repair_auto_box.setVisible(True)
            repair.merge_entries_box.setVisible(False)
            _sync_repair_output_default()
        elif fmt == "merge_signal_entries":
            stacked.setCurrentWidget(repair.page)
            removed = picker.set_allowed_categories({"graphs"}, prune_selection=True)
            if int(removed) > 0:
                rt.selection_pruned_note = f"提示：切换到『合并信号条目』模式后，已自动移除 {int(removed)} 项不支持的勾选。"
            run_btn.setText("开始合并")
            repair.repair_auto_box.setVisible(False)
            repair.merge_entries_box.setVisible(True)
            _sync_repair_output_default()
        else:
            stacked.setCurrentWidget(repair.page)
            removed = picker.set_allowed_categories({"graphs"}, prune_selection=True)
            if int(removed) > 0:
                rt.selection_pruned_note = f"提示：切换模式后，已自动移除 {int(removed)} 项不支持的勾选。"
            run_btn.setText("开始修复")
            repair.repair_auto_box.setVisible(True)
            repair.merge_entries_box.setVisible(True)
        _sync_bundle_enabled_state()
        _sync_pack_enabled_state()
        _sync_write_ui_effective_state()
        _update_ui_export_record_ui()
        _update_preview()

    def _on_write_ui_toggled(_v: bool) -> None:
        if bool(gil.write_ui_cb.isEnabled()):
            rt.write_ui_user_choice = bool(gil.write_ui_cb.isChecked())
        _sync_ui_auto_sync_enabled_state()
        _update_preview()

    gia.gia_advanced_toggle.toggled.connect(lambda checked: gia.gia_advanced_box.setVisible(bool(checked)))
    gia.bundle_enabled_cb.stateChanged.connect(_sync_bundle_enabled_state)
    gia.pack_graphs_cb.stateChanged.connect(_sync_pack_enabled_state)

    gil.gil_advanced_toggle.toggled.connect(lambda checked: gil.gil_advanced_box.setVisible(bool(checked)))
    gil.write_ui_cb.toggled.connect(_on_write_ui_toggled)
    gil.gil_ui_export_record_refresh_btn.clicked.connect(_update_ui_export_record_ui)

    def _sync_builtin_empty_base_ui_state(*_args: object) -> None:
        use_builtin = bool(getattr(gil, "use_builtin_empty_base_cb").isChecked())
        gil.input_gil_edit.setEnabled(not bool(use_builtin))
        gil.input_gil_browse_btn.setEnabled(not bool(use_builtin))
        gil.recent_combo.setEnabled(not bool(use_builtin))
        gil.recent_use_btn.setEnabled(not bool(use_builtin))
        gil.recent_refresh_btn.setEnabled(not bool(use_builtin))

    def _on_use_builtin_empty_base_toggled(_v: bool) -> None:
        from .export_center.state import _save_last_use_builtin_empty_base_gil

        _save_last_use_builtin_empty_base_gil(workspace_root=Path(workspace_root), enabled=bool(gil.use_builtin_empty_base_cb.isChecked()))
        _sync_builtin_empty_base_ui_state()
        _update_preview()

    gia.ui_export_record_combo.currentIndexChanged.connect(_update_ui_export_record_detail_text)

    def _on_picker_selection_changed() -> None:
        _sync_pack_enabled_state()
        _sync_write_ui_effective_state()
        _update_ui_export_record_ui()
        _update_preview()
        _sync_step_nav()

    picker.selection_changed.connect(_on_picker_selection_changed)
    format_combo.currentIndexChanged.connect(_update_format_ui)

    gia.out_dir_edit.textChanged.connect(_update_preview)
    gia.copy_dir_edit.textChanged.connect(_update_preview)
    gia.gia_id_ref_edit.textChanged.connect(_update_preview)
    gia.player_template_base_gia_edit.textChanged.connect(_update_preview)

    gil.input_gil_edit.textChanged.connect(_update_preview)
    gil.use_builtin_empty_base_cb.toggled.connect(_on_use_builtin_empty_base_toggled)
    gil.output_gil_edit.textChanged.connect(_update_preview)
    gil.struct_mode_combo.currentIndexChanged.connect(_update_preview)
    gil.instances_mode_combo.currentIndexChanged.connect(_update_preview)
    gil.signals_mode_combo.currentIndexChanged.connect(_update_preview)
    gil.prefer_signal_specific_type_id_cb.toggled.connect(_update_preview)
    gil.ui_mode_combo.currentIndexChanged.connect(_update_preview)
    gil.ui_auto_sync_vars_cb.toggled.connect(_update_preview)
    gil.gil_ui_export_record_combo.currentIndexChanged.connect(_update_preview)
    gil.gil_id_ref_edit.textChanged.connect(_update_preview)

    def _on_repair_input_gil_text_changed(*_args: object) -> None:
        _sync_repair_output_default()
        _update_preview()

    repair.repair_input_gil_edit.textChanged.connect(_on_repair_input_gil_text_changed)
    repair.repair_output_gil_edit.textChanged.connect(_update_preview)
    repair.repair_prune_orphans_cb.toggled.connect(_update_preview)
    repair.merge_keep_signal_edit.textChanged.connect(_update_preview)
    repair.merge_remove_signal_edit.textChanged.connect(_update_preview)
    repair.merge_rename_keep_to_edit.textChanged.connect(_update_preview)
    repair.merge_patch_cpi_cb.toggled.connect(_update_preview)

    _sync_repair_output_default()
    _update_format_ui()
    _sync_left_selected_list()
    _sync_builtin_empty_base_ui_state()

    ProgressWidgetCls = make_toolbar_progress_widget_cls(
        ToolbarProgressWidgetSpec(kind="export_center", initial_label="准备导出…", progress_width=220),
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )

    package_library_widget = getattr(main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法显示导出进度")
    ensure_widget = getattr(package_library_widget, "ensure_extension_toolbar_widget", None)
    if not callable(ensure_widget):
        raise RuntimeError("PackageLibraryWidget 缺少 ensure_extension_toolbar_widget，无法显示导出进度")

    def _get_progress_widget(*, visible: bool) -> Any:
        widget_obj = ensure_widget(
            "ugc_file_tools.export_center_progress",
            create_widget=lambda parent: ProgressWidgetCls(parent),
            visible=visible,
        )
        if not isinstance(widget_obj, ProgressWidgetCls):
            raise TypeError(f"export center progress widget 类型不匹配（got: {type(widget_obj).__name__}）")
        return widget_obj

    # ===== Step navigation (tabs + footer) =====
    def _has_any_selection() -> bool:
        # 合并信号条目：不依赖资源选择（仅依赖右侧输入/输出与 keep/remove 参数）。
        fmt = str(format_combo.currentData() or "gia")
        if fmt == "merge_signal_entries":
            return True
        return bool(list(picker.get_selected_items()))

    def _can_enter_analysis_step() -> bool:
        if _has_any_selection():
            return True
        from app.ui.foundation import dialog_utils

        dialog_utils.show_warning_dialog(main_window, "提示", "请先在左侧勾选至少 1 个资源，再进入下一步。")
        return False

    def _sync_step_nav() -> None:
        idx = int(tabs.currentIndex())
        back_btn.setEnabled(idx > 0)
        has_sel = bool(_has_any_selection())
        # 顶部步骤 tabs：当不满足进入条件时直接禁用（避免“点了才弹窗”）
        tabs.setTabEnabled(1, bool(has_sel))
        tabs.setTabEnabled(2, bool(has_sel))
        if idx == 0:
            next_btn.setEnabled(bool(has_sel))
            next_btn.setText("下一步：回填分析")
            next_btn.setDefault(True)
            next_btn.setStyleSheet(footer_next_default_stylesheet)
            next_btn.setToolTip("" if has_sel else "请先勾选至少 1 个资源")
            run_btn.setDefault(False)
        elif idx == 1:
            next_btn.setEnabled(True)
            next_btn.setText("下一步：执行")
            next_btn.setDefault(True)
            next_btn.setStyleSheet(footer_next_default_stylesheet)
            next_btn.setToolTip("")
            run_btn.setDefault(False)
        else:
            # Step3：footer 的“下一步”按钮变成“开始导出/开始修复”并触发执行
            next_btn.setEnabled(True)
            next_btn.setText(str(run_btn.text() or "开始导出"))
            next_btn.setDefault(True)
            next_btn.setStyleSheet(footer_next_primary_stylesheet)
            next_btn.setToolTip("")
            run_btn.setDefault(False)
        # 执行页内部按钮仅作为隐藏 ref（真实入口在 footer.next_btn）
        run_btn.setEnabled(False)

    def _go_prev_step() -> None:
        idx = int(tabs.currentIndex())
        if idx <= 0:
            return
        tabs.setCurrentIndex(idx - 1)

    def _can_enter_execute_step() -> bool:
        fmt = str(format_combo.currentData() or "gia")
        selected_items = list(picker.get_selected_items())
        if fmt == "gia":
            return (
                validate_gia_plan(
                    main_window=main_window,
                    workspace_root=Path(workspace_root),
                    package_id=str(package_id),
                    project_root=Path(project_root),
                    picker=picker,
                    gia=gia,
                )
                is not None
            )
        if fmt == "gil":
            return (
                validate_gil_plan(
                    main_window=main_window,
                    workspace_root=Path(workspace_root),
                    package_id=str(package_id),
                    project_root=Path(project_root),
                    picker=picker,
                    gil=gil,
                )
                is not None
            )
        if fmt == "merge_signal_entries":
            return (
                validate_merge_signal_entries_plan(
                    main_window=main_window,
                    workspace_root=Path(workspace_root),
                    package_id=str(package_id),
                    project_root=Path(project_root),
                    picker=picker,
                    repair=repair,
                )
                is not None
            )
        return (
            validate_repair_signals_plan(
                main_window=main_window,
                workspace_root=Path(workspace_root),
                package_id=str(package_id),
                project_root=Path(project_root),
                picker=picker,
                repair=repair,
            )
            is not None
        )

    def _go_next_step() -> None:
        idx = int(tabs.currentIndex())
        if idx == 0:
            if not bool(_can_enter_analysis_step()):
                return
            tabs.setCurrentIndex(1)
            return
        if idx == 1:
            if not bool(_can_enter_execute_step()):
                return
            tabs.setCurrentIndex(2)
            return
        if idx == 2:
            _on_run_clicked(trigger_btn=next_btn)
            return

    back_btn.clicked.connect(_go_prev_step)
    next_btn.clicked.connect(_go_next_step)
    step_state = {"last_idx": int(tabs.currentIndex())}

    def _on_tabs_current_changed(new_idx: int) -> None:
        prev = int(step_state.get("last_idx") or 0)
        cur = int(new_idx)
        if cur == 1 and prev != 1:
            if not bool(_can_enter_analysis_step()):
                tabs.blockSignals(True)
                tabs.setCurrentIndex(int(prev))
                tabs.blockSignals(False)
                _sync_step_nav()
                return
        if cur == 2 and prev != 2:
            if not bool(_can_enter_execute_step()):
                tabs.blockSignals(True)
                tabs.setCurrentIndex(int(prev))
                tabs.blockSignals(False)
                _sync_step_nav()
                return
        step_state["last_idx"] = int(cur)
        _sync_step_nav()
        _update_preview()

    tabs.currentChanged.connect(_on_tabs_current_changed)

    # ===== Execute tab: clear buttons =====
    execute.clear_log_btn.clicked.connect(lambda: execute.log_text.setPlainText(""))
    execute.clear_result_btn.clicked.connect(lambda: execute.result_text.setPlainText(""))

    # ===== Execute tab: progress/result hooks =====
    def _append_execute_log_line(text: str) -> None:
        t = str(text or "").strip()
        if t == "":
            return
        execute.log_text.appendPlainText(t)

    def _set_execute_progress(current: int, total: int, label: str) -> None:
        c = int(current)
        t = int(total)
        line = f"[{c}/{t}] {label}" if t > 0 else str(label)
        if t <= 0:
            execute.progress_bar.setRange(0, 0)
        else:
            # UI 约束：不到最终成功，不显示 100%。
            # 因此将“完成(100%)”作为额外的最后一步：max=total+1，value<=total。
            execute.progress_bar.setRange(0, t + 1)
            execute.progress_bar.setValue(min(max(c, 0), t))
        execute.progress_label.setText(str(line))
        _append_execute_log_line(str(line))

    def _format_export_result_text(report: dict) -> str:
        fmt = str(report.get("format") or "")

        skipped_inputs: list[dict[str, object]] = []
        raw_skipped = report.get("precheck_skipped_inputs") if isinstance(report, dict) else None
        if isinstance(raw_skipped, list) and raw_skipped:
            skipped_inputs = [x for x in raw_skipped if isinstance(x, dict)]

        def _append_precheck_skipped_inputs(lines: list[str]) -> None:
            if not skipped_inputs:
                return
            lines.append("")
            lines.append(f"注意：预检阶段自动跳过 {len(skipped_inputs)} 个输入文件：")
            for item in skipped_inputs[:10]:
                fp = str(item.get("file") or "").strip()
                reason = str(item.get("reason") or "").strip()
                name = Path(fp).name if fp else "(unknown)"
                lines.append(f"- {name}：{reason}" if reason else f"- {name}")
            if len(skipped_inputs) > 10:
                lines.append(f"... 还有 {len(skipped_inputs) - 10} 个未展示")

        if fmt == "gil":
            rep = report.get("report") if isinstance(report, dict) else None
            output_tool = str(rep.get("output_gil_resolved") or rep.get("output_gil") or "") if isinstance(rep, dict) else ""
            output_user = str(rep.get("output_gil_user_resolved") or rep.get("output_gil_user") or "") if isinstance(rep, dict) else ""
            lines_gil = [
                "导出完成（.gil）：",
                f"- out 产物：{output_tool}",
                f"- 导出路径：{output_user}",
            ]
            _append_precheck_skipped_inputs(lines_gil)
            return "\n".join(lines_gil).strip()
        if fmt == "repair_signals":
            rep2 = report.get("report") if isinstance(report, dict) else None
            output_user2 = str(rep2.get("output_gil") or "") if isinstance(rep2, dict) else ""
            removed_entries = int(rep2.get("removed_signal_entries") or 0) if isinstance(rep2, dict) else 0
            id_remap_size = int(rep2.get("id_remap_size") or 0) if isinstance(rep2, dict) else 0
            node_changes = int(rep2.get("node_instance_id_changes") or 0) if isinstance(rep2, dict) else 0
            lines_fix = [
                "修复完成（修复信号）：",
                f"- 输出路径：{output_user2}",
                f"- 合并/移除信号条目：{removed_entries}",
                f"- 引用重绑映射条数：{id_remap_size}",
                f"- 节点引用更新次数：{node_changes}",
            ]
            _append_precheck_skipped_inputs(lines_fix)
            return "\n".join(lines_fix).strip()
        if fmt == "merge_signal_entries":
            repm = report.get("report") if isinstance(report, dict) else None
            output_user_m = str(repm.get("output_gil") or "") if isinstance(repm, dict) else ""
            removed_entries_m = int(repm.get("removed_signal_entries") or 0) if isinstance(repm, dict) else 0
            node_changes_m = int(repm.get("node_instance_id_changes") or 0) if isinstance(repm, dict) else 0
            pin_patches_m = int(repm.get("node_pin_patches") or 0) if isinstance(repm, dict) else 0
            lines_merge = [
                "修复完成（合并信号条目）：",
                f"- 输出路径：{output_user_m}",
                f"- 移除信号条目：{removed_entries_m}",
                f"- 节点引用更新次数：{node_changes_m}",
                f"- pin 端口索引修补次数：{pin_patches_m}",
            ]
            _append_precheck_skipped_inputs(lines_merge)
            return "\n".join(lines_merge).strip()

        graphs_rep = report.get("graphs") if isinstance(report, dict) else None
        tpl_rep = report.get("templates") if isinstance(report, dict) else None
        tpl_bundle_rep = report.get("templates_instances_bundle") if isinstance(report, dict) else None
        tpl_missing_source = report.get("templates_missing_source_info") if isinstance(report, dict) else None
        player_tpl_rep = report.get("player_templates") if isinstance(report, dict) else None
        structs_rep = report.get("basic_structs") if isinstance(report, dict) else None
        signals_rep = report.get("signals") if isinstance(report, dict) else None
        lines: list[str] = ["导出完成（.gia）："]
        if isinstance(graphs_rep, dict):
            exported = graphs_rep.get("exported_graphs")
            lines.append(f"- 节点图：{len(exported) if isinstance(exported, list) else 0} 个（out={graphs_rep.get('output_dir','')}）")

        # 元件导出：可能同时包含
        # - 保真切片：export_project_templates_instances_bundle_gia（report key: exported, templates_instances_dir）
        # - 空模型导出：export_project_templates_to_gia（report key: exported_templates, templates_dir）
        bundle_rep: dict | None = None
        if isinstance(tpl_bundle_rep, dict) and isinstance(tpl_bundle_rep.get("exported"), list):
            bundle_rep = dict(tpl_bundle_rep)
        elif isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported"), list) and not isinstance(tpl_rep.get("exported_templates"), list):
            # 兼容旧 report：曾把 bundle.gia 切片报告写在 templates 下
            bundle_rep = dict(tpl_rep)

        bundle_count = 0
        bundle_out = ""
        if isinstance(bundle_rep, dict):
            exported = bundle_rep.get("exported")
            bundle_count = len(exported) if isinstance(exported, list) else 0
            bundle_out = str(bundle_rep.get("templates_instances_dir") or bundle_rep.get("output_dir") or "").strip()

        empty_count = 0
        empty_out = ""
        if isinstance(tpl_rep, dict) and isinstance(tpl_rep.get("exported_templates"), list):
            exported = tpl_rep.get("exported_templates")
            empty_count = len(exported) if isinstance(exported, list) else 0
            empty_out = str(tpl_rep.get("templates_dir") or tpl_rep.get("output_dir") or "").strip()

        if int(bundle_count) > 0 and int(empty_count) > 0:
            lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}） + {int(empty_count)} 个（模板导出，out={empty_out}）")
        elif int(bundle_count) > 0:
            lines.append(f"- 元件：{int(bundle_count)} 个（保真切片，out={bundle_out}）")
        elif int(empty_count) > 0:
            lines.append(f"- 元件：{int(empty_count)} 个（模板导出，out={empty_out}）")

        if isinstance(tpl_missing_source, list) and tpl_missing_source:
            missing_with_decorations = 0
            for item in list(tpl_missing_source):
                if not isinstance(item, dict):
                    continue
                if bool(item.get("has_decorations")):
                    missing_with_decorations += 1
            if int(missing_with_decorations) > 0:
                lines.append(
                    f"注意：{int(missing_with_decorations)} 个元件模板包含装饰物，但本次仅导出模板（自定义变量），装饰物实例未随 .gia 导出。"
                )
        if isinstance(structs_rep, dict):
            lines.append(f"- 基础结构体：{int(structs_rep.get('structs_total') or 0)} 个（out={structs_rep.get('output_gia_file','')}）")
        if isinstance(signals_rep, dict):
            lines.append(f"- 信号：{int(signals_rep.get('signals_total') or 0)} 个（out={signals_rep.get('output_gia_file','')}）")
        if isinstance(player_tpl_rep, dict):
            exported = player_tpl_rep.get("exported_player_templates")
            pt_count = len(exported) if isinstance(exported, list) else int(player_tpl_rep.get("player_templates_total") or 0)
            pt_out = str(player_tpl_rep.get("player_templates_dir") or player_tpl_rep.get("output_dir") or "").strip()
            lines.append(f"- 玩家模板：{int(pt_count)} 个（out={pt_out}）")
        _append_precheck_skipped_inputs(lines)
        return "\n".join(lines).strip()

    def _on_export_succeeded_report(report: dict) -> None:
        execute.progress_bar.setRange(0, 1)
        execute.progress_bar.setValue(1)
        execute.progress_label.setText("完成")
        execute.result_text.setPlainText(_format_export_result_text(dict(report)))
        _sync_step_nav()

    def _on_export_failed_message(message: str) -> None:
        execute.progress_bar.setRange(0, 1)
        execute.progress_bar.setValue(0)
        execute.progress_label.setText("失败")
        execute.result_text.setPlainText(str(message or "导出失败（请查看控制台错误）。"))
        _sync_step_nav()

    def _on_run_clicked(*, trigger_btn: object) -> None:
        tabs.setCurrentIndex(2)
        _sync_step_nav()
        execute.progress_label.setText("准备导出…")
        execute.progress_bar.setRange(0, 0)
        execute.log_text.setPlainText("")
        execute.result_text.setPlainText("")
        start_export_center_action(
            QtCore=QtCore,
            main_window=main_window,
            dialog=dialog,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            gia=gia,
            gil=gil,
            repair=repair,
            format_combo=format_combo,
            rt=rt,
            stacked=stacked,
            run_btn=trigger_btn,
            close_btn=close_btn,
            history_btn=history_btn,
            get_progress_widget=_get_progress_widget,
            append_task_history_entry=append_task_history_entry,
            now_ts=now_ts,
            on_progress_changed=_set_execute_progress,
            on_succeeded_report=_on_export_succeeded_report,
            on_failed_message=_on_export_failed_message,
        )

    run_btn.clicked.connect(lambda: _on_run_clicked(trigger_btn=run_btn))

    # ===== Analysis tab: identify =====
    analysis.backfill_panel.identify_btn.clicked.connect(
        lambda: start_export_center_backfill_identify_action(
            QtCore=QtCore,
            main_window=main_window,
            dialog=dialog,
            workspace_root=Path(workspace_root),
            package_id=str(package_id),
            project_root=Path(project_root),
            picker=picker,
            format_combo=format_combo,
            gia=gia,
            gil=gil,
            panel=analysis.backfill_panel,
            rt=rt,
            set_backfill_table_rows=_set_backfill_table_rows,
            update_backfill_panels=_update_analysis_tab,
        )
    )
    def _on_backfill_table_item_double_clicked(item: object) -> None:
        from app.ui.foundation import dialog_utils

        panel = analysis.backfill_panel
        table = getattr(panel, "missing_table", None)
        if table is None:
            return
        if item is None:
            return
        row = int(getattr(item, "row", lambda: -1)())
        if row < 0 or row >= int(table.rowCount()):
            return

        def _cell_text(r: int, c: int) -> str:
            it = table.item(int(r), int(c))
            return str(it.text() or "").strip() if it is not None else ""

        category = _cell_text(row, 0)
        key = _cell_text(row, 1)
        status = _cell_text(row, 3)

        if category not in {"实体ID(entity)", "元件ID(component)"}:
            return
        if status != "缺失":
            return
        if key == "":
            return

        report = rt.backfill_last_identify_report
        if not isinstance(report, dict):
            dialog_utils.show_warning_dialog(dialog, "提示", "请先点击“识别”生成对比表后，再对缺失项进行手动选择。")
            return

        id_ref_path_text = str(report.get("id_ref_gil_path") or "").strip()
        base_path_text = str(report.get("base_gil_path") or "").strip()
        ref_text = id_ref_path_text or base_path_text
        if ref_text == "":
            dialog_utils.show_warning_dialog(dialog, "提示", "未找到本次识别使用的参考 GIL 路径，请重新识别后再尝试。")
            return
        ref_gil = Path(ref_text).resolve()
        if (not ref_gil.is_file()) or ref_gil.suffix.lower() != ".gil":
            dialog_utils.show_warning_dialog(dialog, "提示", f"参考 GIL 无效或不存在：{str(ref_gil)}")
            return

        gil_cf = str(ref_gil.as_posix()).casefold()

        from .export_center.id_ref_override_picker import (
            open_id_ref_override_picker_dialog,
            scan_id_ref_gil_candidates_via_subprocess,
        )

        if category == "元件ID(component)":
            cached = rt.id_ref_template_candidates_by_gil_cf.get(gil_cf)
            if cached is None:
                scanned, err = scan_id_ref_gil_candidates_via_subprocess(
                    workspace_root=Path(workspace_root),
                    gil_file_path=Path(ref_gil),
                    scan_templates=True,
                    scan_instances=False,
                )
                if scanned is None:
                    dialog_utils.show_warning_dialog(dialog, "扫描失败", str(err or "扫描候选失败。"))
                    return
                cached = list(scanned.template_name_id_pairs)
                rt.id_ref_template_candidates_by_gil_cf[gil_cf] = list(cached)

            preselected = rt.id_ref_override_component_name_to_id.get(key)
            picked = open_id_ref_override_picker_dialog(
                parent_dialog=dialog,
                title="选择元件ID（来自地图/参考 GIL）",
                placeholder_kind="component",
                placeholder_name=str(key),
                source_gil_path=Path(ref_gil),
                candidates=list(cached),
                preselected_id=(int(preselected) if isinstance(preselected, int) and int(preselected) > 0 else None),
            )
            if picked is None:
                return
            cand_name, cand_id = picked
            rt.id_ref_override_component_name_to_id[str(key)] = int(cand_id)

            value_text = str(int(cand_id))
            note_text = f"手动覆盖：{key} → {cand_name} ({int(cand_id)})"
        else:
            cached2 = rt.id_ref_instance_candidates_by_gil_cf.get(gil_cf)
            if cached2 is None:
                scanned2, err2 = scan_id_ref_gil_candidates_via_subprocess(
                    workspace_root=Path(workspace_root),
                    gil_file_path=Path(ref_gil),
                    scan_templates=False,
                    scan_instances=True,
                )
                if scanned2 is None:
                    dialog_utils.show_warning_dialog(dialog, "扫描失败", str(err2 or "扫描候选失败。"))
                    return
                cached2 = list(scanned2.instance_name_id_pairs)
                rt.id_ref_instance_candidates_by_gil_cf[gil_cf] = list(cached2)

            preselected2 = rt.id_ref_override_entity_name_to_guid.get(key)
            picked2 = open_id_ref_override_picker_dialog(
                parent_dialog=dialog,
                title="选择实体ID（来自地图/参考 GIL）",
                placeholder_kind="entity",
                placeholder_name=str(key),
                source_gil_path=Path(ref_gil),
                candidates=list(cached2),
                preselected_id=(int(preselected2) if isinstance(preselected2, int) and int(preselected2) > 0 else None),
            )
            if picked2 is None:
                return
            cand_name2, cand_id2 = picked2
            rt.id_ref_override_entity_name_to_guid[str(key)] = int(cand_id2)

            value_text = str(int(cand_id2))
            note_text = f"手动覆盖：{key} → {cand_name2} ({int(cand_id2)})"

        # 更新当前 rows 并重新分组到“缺失/已就绪”两个标签页
        current_rows = list(getattr(rt, "backfill_current_rows", []) or [])
        for r0 in current_rows:
            if not isinstance(r0, dict):
                continue
            if str(r0.get("category") or "") == str(category) and str(r0.get("key") or "") == str(key):
                r0["value"] = str(value_text)
                r0["status"] = "OK"
                r0["note"] = str(note_text)
                break
        rt.backfill_current_rows = [dict(x) for x in current_rows if isinstance(x, dict)]
        _set_backfill_table_rows(panel, rows=list(rt.backfill_current_rows))

    analysis.backfill_panel.missing_table.itemDoubleClicked.connect(_on_backfill_table_item_double_clicked)

    # 关卡变量选择会影响依赖清单/识别
    gil.level_vars_select_btn.clicked.connect(lambda: _update_analysis_tab())
    gil.level_vars_clear_btn.clicked.connect(lambda: _update_analysis_tab())

    _sync_step_nav()
