from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from .dialog_types import AnalysisCenterDialogWidgets
from .index_v1 import dump_index_json
from .workers import UsageIndexBuildWorker


SEARCH_TYPE_AUTO: str = "auto"
SEARCH_TYPE_NODE: str = "node"
SEARCH_TYPE_COMPOSITE: str = "composite"
SEARCH_TYPE_SIGNAL: str = "signal"
SEARCH_TYPE_PLACEHOLDER: str = "placeholder"
SEARCH_TYPES: tuple[str, str, str, str, str] = (
    SEARCH_TYPE_AUTO,
    SEARCH_TYPE_NODE,
    SEARCH_TYPE_COMPOSITE,
    SEARCH_TYPE_SIGNAL,
    SEARCH_TYPE_PLACEHOLDER,
)

SCOPE_PROJECT_ONLY: str = "project_only"
SCOPE_SHARED_ONLY: str = "shared_only"
SCOPE_PROJECT_AND_SHARED: str = "project_and_shared"
SCOPES: tuple[str, str, str] = (SCOPE_PROJECT_AND_SHARED, SCOPE_PROJECT_ONLY, SCOPE_SHARED_ONLY)

RESULT_COL_TYPE: int = 0
RESULT_COL_KEY: int = 1
RESULT_COL_GRAPH_ID: int = 2
RESULT_COL_GRAPH_FILE: int = 3
RESULT_COL_COUNT: int = 4
RESULT_COLS: int = 5

PROGRESS_INDETERMINATE_MIN: int = 0
PROGRESS_INDETERMINATE_MAX: int = 0


def _safe_json(value: object) -> str:
    """将对象序列化为可读 JSON 字符串。"""
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


class _AnalysisCenterController:
    """管理分析中心对话框的状态同步与后台构建索引。"""

    def __init__(
        self,
        *,
        QtCore: Any,
        QtWidgets: Any,
        main_window: object,
        widgets: AnalysisCenterDialogWidgets,
        workspace_root: Path,
        package_id: str,
        append_task_history_entry: Callable[..., None],
        now_ts: Callable[[], str],
    ) -> None:
        """保存对话框依赖与运行期状态。"""
        self._QtCore = QtCore
        self._QtWidgets = QtWidgets
        self._main_window = main_window
        self._widgets = widgets
        self._workspace_root = Path(workspace_root).resolve()
        self._resource_library_root = (self._workspace_root / "assets" / "资源库").resolve()
        self._package_id = str(package_id or "").strip()
        self._append_task_history_entry = append_task_history_entry
        self._now_ts = now_ts

        self._runtime: dict[str, object] = {"worker": None, "index_payload": None, "failures": []}

    def wire(self) -> None:
        """连接 UI 信号并初始化默认状态。"""
        self._wire_step1()
        self._wire_step2()
        self._wire_step3()
        self._sync_step1_picker()
        self._sync_search_enabled()

    def _dialog_utils(self) -> Any:
        """延迟导入 dialog_utils 以降低插件加载开销。"""
        from app.ui.foundation import dialog_utils

        return dialog_utils

    def _show_warning(self, title: str, message: str) -> None:
        """在 UI 上展示警告对话框。"""
        self._dialog_utils().show_warning_dialog(self._widgets.tabs, str(title), str(message))

    def _wire_step1(self) -> None:
        """连接步骤1控件事件。"""
        step1 = self._widgets.step1
        step1.scope_combo.currentIndexChanged.connect(self._on_scope_changed)

    def _wire_step2(self) -> None:
        """连接步骤2控件事件。"""
        step2 = self._widgets.step2
        step2.query_edit.textChanged.connect(self._on_search_inputs_changed)
        step2.type_combo.currentIndexChanged.connect(self._on_search_inputs_changed)
        step2.copy_btn.clicked.connect(self._copy_results_to_clipboard)

    def _wire_step3(self) -> None:
        """连接步骤3控件事件。"""
        step3 = self._widgets.step3
        step3.build_btn.clicked.connect(self._start_build)
        step3.cancel_btn.clicked.connect(self._cancel_build)

    def _scope(self) -> str:
        """读取当前 scope。"""
        return str(self._widgets.step1.scope_combo.currentData() or SCOPE_PROJECT_AND_SHARED)

    def _sync_step1_picker(self) -> None:
        """根据 scope 重建步骤1的节点图资源树选择器。"""
        from app.ui.foundation.theme_manager import Colors, Sizes
        from ugc_file_tools.ui_integration.resource_picker import build_resource_selection_items, make_resource_picker_widget_cls
        from ugc_file_tools.ui_integration.export_center.state import (
            load_last_resource_picker_expanded_node_ids,
            save_last_resource_picker_expanded_node_ids,
        )

        scope = self._scope()
        include_shared = bool(scope in {SCOPE_PROJECT_AND_SHARED, SCOPE_SHARED_ONLY})

        shared_root = (self._resource_library_root / "共享").resolve()
        if self._package_id != "":
            project_root = (self._resource_library_root / "项目存档" / self._package_id).resolve()
        else:
            project_root = (self._resource_library_root / "项目存档" / "__no_package_selected__").resolve()

        catalog = build_resource_selection_items(
            project_root=Path(project_root),
            shared_root=Path(shared_root),
            include_shared=bool(include_shared),
        )

        # 仅保留 graphs 分类，减少 UI 噪音（对齐“分析中心：节点图范围选择”）。
        catalog = {"graphs": list(catalog.get("graphs") or [])}
        all_graph_code_files = [
            Path(getattr(it, "absolute_path")).resolve()
            for it in list(catalog.get("graphs") or [])
            if getattr(it, "absolute_path", None) is not None
        ]
        all_graph_code_files = [p for p in all_graph_code_files if p.is_file()]
        all_graph_code_files.sort(key=lambda p: str(p).casefold())

        PickerWidgetCls = make_resource_picker_widget_cls(
            QtCore=self._QtCore,
            QtWidgets=self._QtWidgets,
            Colors=Colors,
            Sizes=Sizes,
        )

        host = self._widgets.step1.picker_host
        host_layout = host.layout()
        if host_layout is None:
            host_layout = self._QtWidgets.QVBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
        while host_layout.count() > 0:
            item = host_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        picker = PickerWidgetCls(
            host,
            catalog=dict(catalog),
            allowed_categories={"graphs"},
            preselected_keys=None,
            show_selected_panel=True,
            show_remove_button=True,
            show_relative_path_column=True,
        )

        # 复用导出中心的“展开状态持久化”口径。
        expanded_ids = set(load_last_resource_picker_expanded_node_ids(workspace_root=Path(self._workspace_root)))

        def _persist_picker_expanded_state() -> None:
            save_last_resource_picker_expanded_node_ids(
                workspace_root=Path(self._workspace_root),
                node_ids=sorted(picker.get_expanded_node_ids(), key=lambda t: t.casefold()),
            )

        picker.tree.itemExpanded.connect(lambda _it: _persist_picker_expanded_state())
        picker.tree.itemCollapsed.connect(lambda _it: _persist_picker_expanded_state())
        self._widgets.tabs.destroyed.connect(lambda *_: _persist_picker_expanded_state())
        self._QtCore.QTimer.singleShot(0, lambda: picker.set_expanded_node_ids(expanded_ids))

        host_layout.addWidget(picker, 1)

        self._runtime["picker"] = picker
        self._runtime["graph_code_files_all"] = list(all_graph_code_files)
        graphs_total = int(len(list(catalog.get("graphs") or [])))
        scope_text = {
            SCOPE_PROJECT_AND_SHARED: "当前项目 + 共享",
            SCOPE_PROJECT_ONLY: "仅当前项目",
            SCOPE_SHARED_ONLY: "仅共享",
        }.get(scope, str(scope))
        self._widgets.step1.scope_hint_label.setText(
            f"提示：可在下方资源树中勾选要扫描的节点图；留空=扫描该范围内全部节点图（范围={scope_text}，候选={graphs_total}）。"
        )

    def _sync_search_enabled(self) -> None:
        """同步搜索区启用状态与提示。"""
        has_index = isinstance(self._runtime.get("index_payload"), dict)
        step2 = self._widgets.step2
        step2.query_edit.setEnabled(bool(has_index))
        step2.type_combo.setEnabled(bool(has_index))
        step2.copy_btn.setEnabled(bool(has_index))
        if has_index:
            step2.hint_label.setText("提示：支持按“包含”匹配；类型=自动会合并所有类别结果。")
        else:
            step2.hint_label.setText("尚未构建索引：请先前往“步骤3：构建索引”。")

    def _on_scope_changed(self) -> None:
        """响应 scope 变化并刷新预览。"""
        self._sync_step1_picker()

    def _start_build(self) -> None:
        """启动后台索引构建。"""
        from .cache_v1 import (
            CacheHit,
            CacheMiss,
            compute_graph_files_fingerprint,
            compute_index_cache_key,
            get_analysis_center_cache_dir,
            get_cache_file_path,
            try_load_cached_index_payload,
        )
        from .index_v1 import INDEX_VERSION_V1, compute_current_node_defs_fp

        if isinstance(self._runtime.get("worker"), UsageIndexBuildWorker):
            self._show_warning("已在运行", "已有正在运行的索引构建任务。")
            return

        picker = self._runtime.get("picker")
        if picker is None:
            self._show_warning("无法构建索引", "节点图选择器未初始化，无法构建索引。")
            return

        selected = [it for it in list(picker.get_selected_items()) if str(getattr(it, "category", "")) == "graphs"]
        selected_files = [Path(getattr(it, "absolute_path")).resolve() for it in selected]
        selected_files = [p for p in selected_files if p.is_file()]
        selected_files.sort(key=lambda p: str(p).casefold())

        # 约定：未勾选任何节点图时扫描全部候选（由 picker 的 catalog 提供）。
        if selected_files:
            graph_code_files = list(selected_files)
        else:
            all_files2 = self._runtime.get("graph_code_files_all")
            graph_code_files = list(all_files2) if isinstance(all_files2, list) else []

        if not graph_code_files:
            self._show_warning("无法构建索引", "当前范围内未找到任何节点图源码文件。")
            return

        node_defs_fp = compute_current_node_defs_fp(workspace_root=Path(self._workspace_root))
        graph_files_fp = compute_graph_files_fingerprint(
            workspace_root=Path(self._workspace_root),
            graph_code_files=list(graph_code_files),
        )
        cache_key = compute_index_cache_key(
            index_version=str(INDEX_VERSION_V1),
            scope=str(self._scope()),
            package_id=str(self._package_id),
            node_defs_fp=str(node_defs_fp),
            graph_files_fingerprint=str(graph_files_fp),
        )
        cache_dir = get_analysis_center_cache_dir(workspace_root=Path(self._workspace_root))
        cache_path = get_cache_file_path(cache_dir=cache_dir, index_version=str(INDEX_VERSION_V1), cache_key=str(cache_key))

        cache_result = try_load_cached_index_payload(
            cache_path=Path(cache_path),
            expected_index_version=str(INDEX_VERSION_V1),
            expected_cache_key=str(cache_key),
        )

        step3 = self._widgets.step3
        step3.log_text.setPlainText("")
        if isinstance(cache_result, CacheHit):
            self._runtime["worker"] = None
            self._runtime["index_payload"] = dict(cache_result.payload)
            self._runtime["failures"] = []

            step3.build_btn.setEnabled(True)
            step3.cancel_btn.setEnabled(False)
            step3.progress_bar.setRange(0, 1)
            step3.progress_bar.setValue(1)
            step3.progress_label.setText("完成（缓存命中）")
            step3.log_text.appendPlainText(f"缓存命中：{str(cache_result.cache_path)}")
            step3.failures_text.setPlainText(_safe_json([]))

            self._append_task_history_entry(
                workspace_root=self._workspace_root,
                entry={
                    "ts": self._now_ts(),
                    "kind": "analysis_index_cache_hit",
                    "title": "分析中心：构建索引（缓存命中）",
                    "cache_path": str(cache_result.cache_path),
                    "cache_key": str(cache_key),
                    "scope": self._scope(),
                    "package_id": self._package_id,
                    "graph_files_total": int(len(graph_code_files)),
                },
            )
            self._sync_search_enabled()
            self._refresh_search_results()
            return
        if isinstance(cache_result, CacheMiss):
            step3.log_text.appendPlainText(f"缓存未命中：{str(cache_result.reason)}")

        cache_meta = {
            "cache_key": str(cache_key),
            "cache_path": str(cache_path),
            "scope": str(self._scope()),
            "package_id": str(self._package_id),
            "node_defs_fp": str(node_defs_fp),
            "graph_files_fingerprint": str(graph_files_fp),
            "graph_files_total": int(len(graph_code_files)),
        }
        worker = UsageIndexBuildWorker(
            QtCore=self._QtCore,
            workspace_root=self._workspace_root,
            graph_code_files=graph_code_files,
            cache_path=Path(cache_path),
            cache_meta=dict(cache_meta),
        )
        self._runtime["worker"] = worker

        step3.build_btn.setEnabled(False)
        step3.cancel_btn.setEnabled(True)
        step3.progress_bar.setRange(PROGRESS_INDETERMINATE_MIN, PROGRESS_INDETERMINATE_MAX)
        step3.progress_bar.setValue(0)
        step3.progress_label.setText("准备…")
        step3.log_text.setPlainText("")
        step3.failures_text.setPlainText("")

        worker.thread.progress_changed.connect(self._on_build_progress)
        worker.thread.failed.connect(self._on_build_failed)
        worker.thread.succeeded.connect(self._on_build_succeeded)
        worker.thread.start()

    def _cancel_build(self) -> None:
        """取消后台索引构建。"""
        worker = self._runtime.get("worker")
        if isinstance(worker, UsageIndexBuildWorker):
            worker.thread.requestInterruption()

    def _on_build_progress(self, current: int, total: int, label: str) -> None:
        """更新执行页进度与日志。"""
        step3 = self._widgets.step3
        c = int(current)
        t = int(total)
        if t <= 0:
            step3.progress_bar.setRange(PROGRESS_INDETERMINATE_MIN, PROGRESS_INDETERMINATE_MAX)
        else:
            step3.progress_bar.setRange(0, t)
            step3.progress_bar.setValue(min(max(c, 0), t))
        line = f"[{c}/{t}] {label}" if t > 0 else str(label)
        step3.progress_label.setText(str(line))
        step3.log_text.appendPlainText(str(line))

    def _on_build_failed(self, err_text: str, failures: object) -> None:
        """处理索引构建失败并展示错误。"""
        self._runtime["worker"] = None
        self._runtime["index_payload"] = None
        self._runtime["failures"] = list(failures) if isinstance(failures, list) else []

        step3 = self._widgets.step3
        step3.build_btn.setEnabled(True)
        step3.cancel_btn.setEnabled(False)
        step3.progress_bar.setRange(0, 1)
        step3.progress_bar.setValue(0)
        step3.progress_label.setText("失败")
        step3.log_text.appendPlainText(str(err_text or "构建失败。"))
        step3.failures_text.setPlainText(_safe_json(self._runtime["failures"]))

        self._append_task_history_entry(
            workspace_root=self._workspace_root,
            entry={
                "ts": self._now_ts(),
                "kind": "analysis_index_build",
                "title": "分析中心：构建索引（失败）",
                "error": str(err_text or ""),
                "failures": list(self._runtime["failures"]),
                "scope": self._scope(),
                "package_id": self._package_id,
            },
        )
        self._sync_search_enabled()

    def _on_build_succeeded(self, payload: object, failures: object) -> None:
        """处理索引构建成功并启用搜索。"""
        self._runtime["worker"] = None
        self._runtime["index_payload"] = dict(payload) if isinstance(payload, dict) else {}
        self._runtime["failures"] = list(failures) if isinstance(failures, list) else []

        step3 = self._widgets.step3
        step3.build_btn.setEnabled(True)
        step3.cancel_btn.setEnabled(False)
        step3.progress_bar.setRange(0, 1)
        step3.progress_bar.setValue(1)
        cache_path = ""
        if isinstance(self._runtime.get("index_payload"), dict):
            meta = self._runtime["index_payload"].get("_cache")
            cache_path = str(meta.get("cache_path") or "") if isinstance(meta, dict) else ""
        step3.progress_label.setText("完成（已写入缓存）" if cache_path else "完成")
        if cache_path:
            step3.log_text.appendPlainText(f"已写入缓存：{cache_path}")
        step3.failures_text.setPlainText(_safe_json(self._runtime["failures"]))

        self._append_task_history_entry(
            workspace_root=self._workspace_root,
            entry={
                "ts": self._now_ts(),
                "kind": "analysis_index_build",
                "title": "分析中心：构建索引",
                "payload": dict(self._runtime["index_payload"]),
                "failures": list(self._runtime["failures"]),
                "scope": self._scope(),
                "package_id": self._package_id,
            },
        )
        self._sync_search_enabled()
        self._refresh_search_results()

    def _on_search_inputs_changed(self) -> None:
        """响应搜索输入变化并刷新结果。"""
        self._refresh_search_results()

    def _refresh_search_results(self) -> None:
        """基于当前输入刷新结果表格。"""
        payload = self._runtime.get("index_payload")
        if not isinstance(payload, dict):
            return

        step2 = self._widgets.step2
        query = str(step2.query_edit.text() or "").strip()
        search_type = str(step2.type_combo.currentData() or SEARCH_TYPE_AUTO)
        results = self._search(payload=payload, query=query, search_type=search_type)
        self._apply_results(results=results)

    def _search(self, *, payload: dict, query: str, search_type: str) -> list[dict]:
        """执行一次索引内搜索并返回结果行列表。"""
        q = str(query or "").strip()
        if q == "":
            return []
        q_cf = q.casefold()

        graphs = payload.get("graphs") if isinstance(payload.get("graphs"), dict) else {}
        results: list[dict] = []

        def add_hits(kind: str, bucket: dict) -> None:
            for key, graph_counts in bucket.items():
                k = str(key or "")
                if q_cf not in k.casefold():
                    continue
                if not isinstance(graph_counts, dict):
                    continue
                for gid, cnt in graph_counts.items():
                    gid_text = str(gid or "").strip()
                    count = int(cnt) if isinstance(cnt, int) else int(cnt or 0)
                    graph_info = graphs.get(gid_text, {}) if isinstance(graphs, dict) else {}
                    graph_file = str((graph_info or {}).get("graph_file") or "")
                    results.append(
                        {
                            "type": kind,
                            "key": k,
                            "graph_id": gid_text,
                            "graph_file": graph_file,
                            "count": count,
                        }
                    )

        if search_type in {SEARCH_TYPE_AUTO, SEARCH_TYPE_NODE}:
            node_by_key = payload.get("node_by_key")
            node_by_title = payload.get("node_by_title")
            if isinstance(node_by_key, dict):
                add_hits("node_key", node_by_key)
            if isinstance(node_by_title, dict):
                add_hits("node_title", node_by_title)

        if search_type in {SEARCH_TYPE_AUTO, SEARCH_TYPE_COMPOSITE}:
            composite_by_id = payload.get("composite_by_id")
            if isinstance(composite_by_id, dict):
                add_hits("composite", composite_by_id)

        if search_type in {SEARCH_TYPE_AUTO, SEARCH_TYPE_SIGNAL}:
            signals_by_name = payload.get("signals_by_name")
            if isinstance(signals_by_name, dict):
                add_hits("signal", signals_by_name)

        if search_type in {SEARCH_TYPE_AUTO, SEARCH_TYPE_PLACEHOLDER}:
            ui_key_by_key = payload.get("ui_key_by_key")
            entity_key_by_name = payload.get("entity_key_by_name")
            component_key_by_name = payload.get("component_key_by_name")
            if isinstance(ui_key_by_key, dict):
                add_hits("ui_key", ui_key_by_key)
            if isinstance(entity_key_by_name, dict):
                add_hits("entity_key", entity_key_by_name)
            if isinstance(component_key_by_name, dict):
                add_hits("component_key", component_key_by_name)

        results.sort(key=lambda r: (str(r.get("type")), str(r.get("key")), str(r.get("graph_file")), str(r.get("graph_id"))))
        return results

    def _apply_results(self, *, results: list[dict]) -> None:
        """将结果行渲染到表格并更新摘要。"""
        step2 = self._widgets.step2
        table = step2.result_table
        table.setRowCount(0)
        table.setColumnCount(int(RESULT_COLS))
        table.setHorizontalHeaderLabels(["类型", "命中对象", "graph_id", "图文件", "次数"])

        for r in results:
            row = int(table.rowCount())
            table.insertRow(row)
            table.setItem(row, RESULT_COL_TYPE, self._QtWidgets.QTableWidgetItem(str(r.get("type") or "")))
            table.setItem(row, RESULT_COL_KEY, self._QtWidgets.QTableWidgetItem(str(r.get("key") or "")))
            table.setItem(row, RESULT_COL_GRAPH_ID, self._QtWidgets.QTableWidgetItem(str(r.get("graph_id") or "")))
            table.setItem(row, RESULT_COL_GRAPH_FILE, self._QtWidgets.QTableWidgetItem(str(r.get("graph_file") or "")))
            table.setItem(row, RESULT_COL_COUNT, self._QtWidgets.QTableWidgetItem(str(int(r.get("count") or 0))))

        step2.summary_label.setText(f"命中行数：{len(results)}")
        table.resizeColumnsToContents()

    def _copy_results_to_clipboard(self) -> None:
        """将当前结果表复制到剪贴板。"""
        payload = self._runtime.get("index_payload")
        if not isinstance(payload, dict):
            return
        step2 = self._widgets.step2
        query = str(step2.query_edit.text() or "").strip()
        search_type = str(step2.type_combo.currentData() or SEARCH_TYPE_AUTO)
        results = self._search(payload=payload, query=query, search_type=search_type)
        text = _safe_json(results)
        self._QtWidgets.QApplication.clipboard().setText(text)

    def debug_dump_index_to_step3_log(self) -> None:
        """将当前索引 payload 以 JSON 形式写入执行页日志。"""
        payload = self._runtime.get("index_payload")
        if not isinstance(payload, dict):
            return
        self._widgets.step3.log_text.appendPlainText(dump_index_json(payload=payload))


def wire_analysis_center_dialog(
    *,
    QtCore: Any,
    QtWidgets: Any,
    main_window: object,
    widgets: AnalysisCenterDialogWidgets,
    workspace_root: Path,
    package_id: str,
    append_task_history_entry: Callable[..., None],
    now_ts: Callable[[], str],
) -> None:
    """装配分析中心对话框 controller 并完成信号连接。"""
    controller = _AnalysisCenterController(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        main_window=main_window,
        widgets=widgets,
        workspace_root=workspace_root,
        package_id=package_id,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
    )
    controller.wire()

