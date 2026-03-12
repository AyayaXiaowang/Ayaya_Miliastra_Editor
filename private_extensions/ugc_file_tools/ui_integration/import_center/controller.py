from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .dialog_types import ImportCenterDialogWidgets
from .plans import IMPORT_TASK_GIA, IMPORT_TASK_GIL_FULL, IMPORT_TASK_GIL_SELECTED, ImportGiaPlan, ImportGilPlan, ImportGilSelectedPlan
from .workers import GiaImportWorker, GilImportWorker, GilScanGraphsWorker, GilSelectedImportWorker


PROGRESS_COMPLETE_EXTRA_STEP = 1
EXECUTE_PROGRESS_INDETERMINATE_MIN = 0
EXECUTE_PROGRESS_INDETERMINATE_MAX = 0


def refresh_package_library_and_select_package(main_window: object, *, package_id: str) -> None:
    """刷新项目存档列表并将选择切换到指定 package。"""
    from PyQt6 import QtWidgets

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    package_library_widget = getattr(main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法刷新项目存档列表")

    packages_changed = getattr(package_library_widget, "packages_changed", None)
    if packages_changed is not None and hasattr(packages_changed, "emit"):
        packages_changed.emit()

    refresh = getattr(package_library_widget, "refresh", None)
    if callable(refresh):
        refresh()

    set_selection = getattr(package_library_widget, "set_selection", None)
    if callable(set_selection):
        from app.ui.graph.library_pages.library_scaffold import LibrarySelection

        set_selection(LibrarySelection(kind="package", id=str(package_id), context=None))

    load_signal = getattr(package_library_widget, "package_load_requested", None)
    if load_signal is not None and hasattr(load_signal, "emit"):
        load_signal.emit(str(package_id))


class _ImportCenterController:
    """管理导入中心对话框的状态同步与后台执行。"""

    def __init__(
        self,
        *,
        QtCore: Any,
        QtWidgets: Any,
        main_window: object,
        widgets: ImportCenterDialogWidgets,
        workspace_root: Path,
        packages_root: Path,
        package_index_manager: object,
        sanitize_package_id: Callable[[str], str],
        template_package_dirname: str,
        importable_package_ids: list[str],
        existing_package_dirnames: list[str],
        generate_unique_name: Callable[[str, list[str]], str],
        append_task_history_entry: Callable[..., None],
        now_ts: Callable[[], str],
    ) -> None:
        """保存对话框依赖与运行期状态。"""
        self._QtCore = QtCore
        self._QtWidgets = QtWidgets
        self._main_window = main_window
        self._widgets = widgets
        self._workspace_root = Path(workspace_root).resolve()
        self._packages_root = Path(packages_root).resolve()
        self._package_index_manager = package_index_manager
        self._sanitize_package_id = sanitize_package_id
        self._template_package_dirname = str(template_package_dirname)
        self._importable_package_ids = list(importable_package_ids)
        self._existing_package_dirnames = list(existing_package_dirnames)
        self._generate_unique_name = generate_unique_name
        self._append_task_history_entry = append_task_history_entry
        self._now_ts = now_ts
        self._runtime: dict[str, object] = {"scan_worker": None, "execute_worker": None}

    def wire(self) -> None:
        """连接 UI 信号并初始化默认状态。"""
        self._wire_buttons()
        self._wire_step1()
        self._wire_step2()
        self._sync_target_mode_ui()
        self._sync_task_specific_ui()
        self._sync_preview_texts()
        self._sync_step_nav()

    def _dialog_utils(self) -> Any:
        """延迟导入 dialog_utils 以降低插件加载开销。"""
        from app.ui.foundation import dialog_utils

        return dialog_utils

    def _task(self) -> str:
        """读取当前任务类型。"""
        return str(self._widgets.step1.task_combo.currentData() or IMPORT_TASK_GIL_FULL)

    def _target_mode(self) -> str:
        """读取当前导入目标模式。"""
        return str(self._widgets.step1.target_mode_combo.currentData() or "existing")

    def _append_log(self, line: str) -> None:
        """向执行页日志尾部追加一行。"""
        text = str(line or "").strip()
        if text == "":
            return
        self._widgets.step3.log_text.appendPlainText(text)

    def _set_execute_progress(self, current: int, total: int, label: str) -> None:
        """更新执行页进度条并追加进度日志。"""
        c = int(current)
        t = int(total)
        line = f"[{c}/{t}] {label}" if t > 0 else str(label)
        if t <= 0:
            self._widgets.step3.progress_bar.setRange(EXECUTE_PROGRESS_INDETERMINATE_MIN, EXECUTE_PROGRESS_INDETERMINATE_MAX)
        else:
            self._widgets.step3.progress_bar.setRange(0, t + int(PROGRESS_COMPLETE_EXTRA_STEP))
            self._widgets.step3.progress_bar.setValue(min(max(c, 0), t))
        self._widgets.step3.progress_label.setText(str(line))
        self._append_log(str(line))

    def _set_execute_failed(self, err_text: str) -> None:
        """将执行页标记为失败并展示错误文本。"""
        self._widgets.step3.progress_bar.setRange(0, 1)
        self._widgets.step3.progress_bar.setValue(0)
        self._widgets.step3.progress_label.setText("失败")
        self._widgets.step3.result_text.setPlainText(str(err_text or "导入失败（请查看控制台错误）。"))

    def _set_execute_succeeded(self, report_payload: dict[str, object]) -> None:
        """将执行页标记为成功并展示结果摘要。"""
        self._widgets.step3.progress_bar.setRange(0, 1)
        self._widgets.step3.progress_bar.setValue(1)
        self._widgets.step3.progress_label.setText("完成")
        self._widgets.step3.result_text.setPlainText(json.dumps(report_payload, ensure_ascii=False, indent=2))

    def _sanitize_new_package_dirname(self, raw_name: str) -> str:
        """将用户输入的项目存档名转换为可用目录名。"""
        raw = str(raw_name or "").strip()
        if raw == "":
            raw = "未命名项目存档"
        sanitized = str(self._sanitize_package_id(raw) or "").strip()
        return sanitized if sanitized != "" else "未命名项目存档"

    def _compute_new_package_id(self, raw_name: str) -> str:
        """基于用户输入生成唯一的 package_id。"""
        sanitized = self._sanitize_new_package_dirname(str(raw_name))
        return str(self._generate_unique_name(str(sanitized), list(self._existing_package_dirnames)))

    def _sync_target_mode_ui(self) -> None:
        """同步“导入目标”区域的启用状态与提示文案。"""
        step1 = self._widgets.step1
        is_existing = self._target_mode() == "existing"
        step1.package_name_edit.setEnabled(not is_existing)
        step1.existing_package_combo.setEnabled(is_existing)
        if is_existing:
            if not self._importable_package_ids:
                step1.overwrite_warning_label.setText(
                    "提示：当前没有可选的“已有项目存档”。\n（示例项目模板不允许作为导入目标；请先新建一个项目存档。）"
                )
            else:
                step1.overwrite_warning_label.setText("注意：导入到已有项目存档时，会新增/覆盖资源文件（不可撤销）。")
        else:
            step1.overwrite_warning_label.setText("")

    def _sync_task_specific_ui(self) -> None:
        """同步任务类型相关的控件显隐与可用性。"""
        step1 = self._widgets.step1
        step2 = self._widgets.step2
        task = self._task()
        is_gia = task == IMPORT_TASK_GIA
        is_gil_selected = task == IMPORT_TASK_GIL_SELECTED

        step1.gil_selected_parts_box.setVisible(bool(is_gil_selected))
        step1.gia_config_box.setVisible(bool(is_gia))

        step1.generate_graph_code_checkbox.setEnabled(not bool(is_gia))
        step1.enable_dll_dump_checkbox.setEnabled(not bool(is_gia))
        self._sync_generate_validate_enabled_state()

        step2.stacked.setCurrentWidget(step2.gil_selected_page if is_gil_selected else step2.default_preview_text)
        self._sync_gia_sub_options()

    def _sync_generate_validate_enabled_state(self) -> None:
        """同步“生成代码/生成后校验”的启用状态。"""
        step1 = self._widgets.step1
        if self._task() == IMPORT_TASK_GIA:
            step1.validate_after_generate_checkbox.setEnabled(False)
            return
        if self._task() == IMPORT_TASK_GIL_SELECTED and not bool(step1.export_node_graphs_cb.isChecked()):
            step1.generate_graph_code_checkbox.setChecked(False)
        step1.validate_after_generate_checkbox.setEnabled(bool(step1.generate_graph_code_checkbox.isChecked()))
        if not bool(step1.generate_graph_code_checkbox.isChecked()):
            step1.validate_after_generate_checkbox.setChecked(False)

    def _sync_gia_sub_options(self) -> None:
        """同步 GIA 子选项（bundle/player_template/node_graphs）的显隐。"""
        step1 = self._widgets.step1
        if self._task() != IMPORT_TASK_GIA:
            return
        kind = str(step1.gia_import_kind_combo.currentData() or "templates_instances").strip()
        is_bundle = kind == "templates_instances"
        is_node_graphs = kind == "node_graphs"
        step1.gia_templates_cb.setVisible(bool(is_bundle))
        step1.gia_instances_cb.setVisible(bool(is_bundle))
        step1.gia_instances_mode_row.setVisible(bool(is_bundle and step1.gia_instances_cb.isChecked()))
        step1.gia_validate_after_import_cb.setVisible(bool(is_node_graphs))

    def _sync_preview_texts(self) -> None:
        """刷新步骤1与步骤2的预览文本。"""
        step1 = self._widgets.step1
        step2 = self._widgets.step2
        task = self._task()
        input_text = str(step1.input_path_edit.text() or "").strip()
        mode = self._target_mode()
        overwrite = bool(step1.overwrite_checkbox.isChecked())

        if mode == "existing":
            target_id = str(step1.existing_package_combo.currentText() or "").strip()
            out_root = (self._packages_root / target_id).resolve() if target_id else None
            pkg_id = target_id
        else:
            pkg_id = self._compute_new_package_id(str(step1.package_name_edit.text() or "").strip())
            out_root = (self._packages_root / pkg_id).resolve()

        lines: list[str] = []
        if task == IMPORT_TASK_GIA:
            kind = str(step1.gia_import_kind_combo.currentData() or "templates_instances").strip()
            lines.extend(["任务：导入 .gia", f"类型：{kind}"])
        elif task == IMPORT_TASK_GIL_SELECTED:
            parts = self._format_gil_selected_parts()
            lines.extend(["任务：读取 .gil（选择性导入）", f"导入范围：{parts}"])
        else:
            lines.append("任务：读取 .gil（整包导入）")

        if input_text:
            lines.append(f"输入：{input_text}")
        lines.append(f"输出：{str(out_root) if out_root is not None else '<未选择目标项目存档>'}")
        if overwrite:
            lines.append("覆盖写入：开启（谨慎）")

        text = "\n".join([x for x in lines if str(x).strip()])
        step1.preview_label.setText(text)
        (step2.gil_selected_preview_text if task == IMPORT_TASK_GIL_SELECTED else step2.default_preview_text).setPlainText(text)

    def _format_gil_selected_parts(self) -> str:
        """将选择性导入的资源段开关格式化为文本。"""
        s = self._widgets.step1
        parts: list[str] = []
        if s.export_node_graphs_cb.isChecked():
            parts.append("节点图")
        if s.export_templates_cb.isChecked():
            parts.append("元件库")
        if s.export_instances_cb.isChecked():
            parts.append("实体摆放")
        if s.export_struct_defs_cb.isChecked():
            parts.append("结构体")
        if s.export_signals_cb.isChecked():
            parts.append("信号")
        if s.export_combat_presets_cb.isChecked():
            parts.append("战斗预设")
        if s.export_section15_cb.isChecked():
            parts.append("战斗/管理条目")
        if s.export_raw_pyugc_cb.isChecked():
            parts.append("原始解析")
        if s.export_data_blobs_cb.isChecked():
            parts.append("数据块解析")
        return " + ".join(parts) if parts else "<未选择>"

    def _validate_step1_inputs(self) -> tuple[str, Path, str, Path, bool]:
        """校验步骤1输入并返回执行所需的关键路径信息。"""
        step1 = self._widgets.step1
        task = self._task()
        input_text = str(step1.input_path_edit.text() or "").strip()
        if input_text == "":
            raise ValueError("请先选择输入文件。")
        input_path = Path(input_text).resolve()
        if not input_path.is_file():
            raise FileNotFoundError(f"文件不存在：{str(input_path)}")
        if task == IMPORT_TASK_GIA and input_path.suffix.lower() != ".gia":
            raise ValueError("输入文件不是 .gia。")
        if task != IMPORT_TASK_GIA and input_path.suffix.lower() != ".gil":
            raise ValueError("输入文件不是 .gil。")

        mode = self._target_mode()
        overwrite_existing = bool(step1.overwrite_checkbox.isChecked())
        if mode == "existing":
            if not self._importable_package_ids:
                raise ValueError("当前没有可选的“已有项目存档”。请先新建一个项目存档。")
            selected_id = str(step1.existing_package_combo.currentText() or "").strip()
            if selected_id == "":
                raise ValueError("请先选择一个目标项目存档。")
            if selected_id == str(self._template_package_dirname):
                raise ValueError("不允许将导入结果写入“示例项目模板”。")
            output_root = (self._packages_root / selected_id).resolve()
            if (not output_root.exists()) or (not output_root.is_dir()):
                raise FileNotFoundError(f"目标项目存档目录不存在：{str(output_root)}")
            package_id = selected_id
        else:
            package_id = self._compute_new_package_id(str(step1.package_name_edit.text() or "").strip())
            output_root = (self._packages_root / package_id).resolve()
            if output_root.exists():
                raise ValueError(f"目标目录已存在，请修改项目存档名：{str(output_root)}")

        return task, input_path, str(package_id), output_root, bool(overwrite_existing)

    def _collect_selected_graph_ids(self) -> list[int]:
        """收集步骤2中勾选的节点图 graph_id_int 列表。"""
        ids: list[int] = []
        for i in range(int(self._widgets.step2.gil_selected_graphs_list.count())):
            it = self._widgets.step2.gil_selected_graphs_list.item(i)
            if it is None:
                continue
            if it.checkState() != self._QtCore.Qt.CheckState.Checked:
                continue
            gid = it.data(self._QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(gid, int):
                ids.append(int(gid))
        return sorted(set(ids))

    def _validate_step2_for_execute(self, task: str) -> None:
        """校验步骤2的选择性导入前置条件。"""
        if task != IMPORT_TASK_GIL_SELECTED:
            return
        if not bool(self._widgets.step1.export_node_graphs_cb.isChecked()):
            return
        if not self._collect_selected_graph_ids():
            raise ValueError("请先在步骤2勾选至少 1 张节点图。")

    def _build_plan(self, task: str, input_path: Path, package_id: str, output_root: Path, overwrite_existing: bool) -> object:
        """根据当前 UI 状态构建最终执行 plan。"""
        s = self._widgets.step1
        if task == IMPORT_TASK_GIL_FULL:
            gen = bool(s.generate_graph_code_checkbox.isChecked())
            val = bool(s.validate_after_generate_checkbox.isChecked()) if gen else False
            return ImportGilPlan(
                input_gil_path=Path(input_path),
                package_id=str(package_id),
                output_package_root=Path(output_root),
                overwrite_existing=bool(overwrite_existing),
                enable_dll_dump=bool(s.enable_dll_dump_checkbox.isChecked()),
                generate_graph_code=bool(gen),
                validate_after_generate=bool(val),
            )
        if task == IMPORT_TASK_GIL_SELECTED:
            export_node_graphs = bool(s.export_node_graphs_cb.isChecked())
            gen = bool(s.generate_graph_code_checkbox.isChecked())
            val = bool(s.validate_after_generate_checkbox.isChecked()) if gen else False
            export_data_blobs = bool(s.export_data_blobs_cb.isChecked())
            selected_graphs = self._collect_selected_graph_ids() if export_node_graphs else []
            return ImportGilSelectedPlan(
                input_gil_path=Path(input_path),
                package_id=str(package_id),
                output_package_root=Path(output_root),
                overwrite_existing=bool(overwrite_existing),
                export_raw_pyugc_dump=bool(s.export_raw_pyugc_cb.isChecked()),
                export_node_graphs=bool(export_node_graphs),
                export_templates=bool(s.export_templates_cb.isChecked()),
                export_instances=bool(s.export_instances_cb.isChecked()),
                export_combat_presets=bool(s.export_combat_presets_cb.isChecked()),
                export_section15=bool(s.export_section15_cb.isChecked()),
                export_struct_definitions=bool(s.export_struct_defs_cb.isChecked()),
                export_signals=bool(s.export_signals_cb.isChecked()),
                export_data_blobs=bool(export_data_blobs),
                export_decoded_dtype_type3=bool(export_data_blobs),
                export_decoded_generic=bool(export_data_blobs),
                selected_node_graph_id_ints=list(selected_graphs),
                enable_dll_dump=bool(s.enable_dll_dump_checkbox.isChecked()),
                generate_graph_code=bool(gen),
                validate_after_generate=bool(val),
            )

        kind = str(s.gia_import_kind_combo.currentData() or "templates_instances").strip()
        self._validate_gia_kind(kind)
        return ImportGiaPlan(
            input_gia_path=Path(input_path),
            import_kind=str(kind),
            package_id=str(package_id),
            output_package_root=Path(output_root),
            overwrite_existing=bool(overwrite_existing),
            import_templates=bool(s.gia_templates_cb.isChecked()),
            import_instances=bool(s.gia_instances_cb.isChecked()),
            instances_mode=str(s.gia_instances_mode_combo.currentData() or "decorations_to_template"),
            decode_max_depth=int(s.gia_decode_depth_spin.value()),
            validate_after_import=bool(s.gia_validate_after_import_cb.isChecked()),
        )

    def _validate_gia_kind(self, kind: str) -> None:
        """校验 GIA bundle 导入的范围与装饰物模式约束。"""
        s = self._widgets.step1
        if kind != "templates_instances":
            return
        if not s.gia_templates_cb.isChecked() and not s.gia_instances_cb.isChecked():
            raise ValueError("请至少勾选一个导入范围（元件库/实体摆放）。")
        if s.gia_instances_cb.isChecked():
            mode2 = str(s.gia_instances_mode_combo.currentData() or "decorations_to_template").strip()
            if mode2 == "decorations_to_template" and not s.gia_templates_cb.isChecked():
                raise ValueError("“写入对应元件”模式需要同时导入元件。")

    def _sync_step_nav(self) -> None:
        """同步顶部步骤与 footer 按钮状态。"""
        tabs = self._widgets.wizard_tabs
        idx = int(tabs.currentIndex())
        self._widgets.footer.back_btn.setEnabled(idx > 0)
        self._widgets.footer.next_btn.setText("下一步：预览/分析" if idx == 0 else ("下一步：执行" if idx == 1 else "开始导入"))
        self._widgets.footer.next_btn.setEnabled(True)

    def _go_prev_step(self) -> None:
        """切换到上一步。"""
        tabs = self._widgets.wizard_tabs
        idx = int(tabs.currentIndex())
        if idx > 0:
            tabs.setCurrentIndex(idx - 1)

    def _go_next_step(self) -> None:
        """切换到下一步或触发执行。"""
        du = self._dialog_utils()
        tabs = self._widgets.wizard_tabs
        idx = int(tabs.currentIndex())
        if idx == 0:
            try:
                self._validate_step1_inputs()
            except BaseException as exc:
                du.show_warning_dialog(self._widgets.dialog, "无法进入下一步", str(exc))
                return
            tabs.setCurrentIndex(1)
            return
        if idx == 1:
            try:
                task, input_path, package_id, output_root, overwrite_existing = self._validate_step1_inputs()
                self._validate_step2_for_execute(task)
                self._build_plan(task, input_path, package_id, output_root, overwrite_existing)
            except BaseException as exc:
                du.show_warning_dialog(self._widgets.dialog, "无法进入执行步骤", str(exc))
                return
            tabs.setCurrentIndex(2)
            return
        self._start_execute()

    def _on_tabs_current_changed(self, _new_idx: int) -> None:
        """在步骤切换时刷新导航与预览。"""
        self._sync_step_nav()
        self._sync_preview_texts()

    def _clear_execute(self) -> None:
        """清空执行页的进度/日志/结果。"""
        s3 = self._widgets.step3
        s3.progress_label.setText("未开始。")
        s3.progress_bar.setRange(0, 1)
        s3.progress_bar.setValue(0)
        s3.log_text.setPlainText("")
        s3.result_text.setPlainText("")

    def _start_execute(self) -> None:
        """构建 plan 并启动后台 worker。"""
        du = self._dialog_utils()
        tabs = self._widgets.wizard_tabs
        try:
            task, input_path, package_id, output_root, overwrite_existing = self._validate_step1_inputs()
            self._validate_step2_for_execute(task)
            plan = self._build_plan(task, input_path, package_id, output_root, overwrite_existing)
        except BaseException as exc:
            du.show_warning_dialog(self._widgets.dialog, "无法开始导入", str(exc))
            return

        tabs.setCurrentIndex(2)
        self._sync_step_nav()
        self._clear_execute()
        self._widgets.step3.progress_label.setText("准备导入…")
        self._widgets.step3.progress_bar.setRange(EXECUTE_PROGRESS_INDETERMINATE_MIN, EXECUTE_PROGRESS_INDETERMINATE_MAX)

        worker = self._create_execute_worker(task=task, plan=plan)
        self._runtime["execute_worker"] = worker
        self._wire_execute_worker(worker=worker, task=task, package_id=str(package_id), input_path=Path(input_path), overwrite_existing=bool(overwrite_existing))
        worker.start()

    def _create_execute_worker(self, *, task: str, plan: object) -> Any:
        """根据任务类型创建对应的 execute worker。"""
        if task == IMPORT_TASK_GIL_FULL:
            return GilImportWorker(QtCore=self._QtCore, plan=plan, workspace_root=Path(self._workspace_root), package_index_manager=self._package_index_manager).thread
        if task == IMPORT_TASK_GIL_SELECTED:
            return GilSelectedImportWorker(
                QtCore=self._QtCore,
                plan=plan,
                workspace_root=Path(self._workspace_root),
                package_index_manager=self._package_index_manager,
            ).thread
        return GiaImportWorker(QtCore=self._QtCore, plan=plan, package_index_manager=self._package_index_manager).thread

    def _wire_execute_worker(self, *, worker: Any, task: str, package_id: str, input_path: Path, overwrite_existing: bool) -> None:
        """连接 execute worker 的 progress/succeeded/failed 信号。"""
        def _on_progress(cur: int, tot: int, label: str) -> None:
            self._set_execute_progress(int(cur), int(tot), str(label))

        def _on_succeeded(payload_obj: object) -> None:
            payload = dict(payload_obj) if isinstance(payload_obj, dict) else {"payload": payload_obj}
            self._set_execute_succeeded(payload)
            refresh_package_library_and_select_package(self._main_window, package_id=str(package_id))
            self._append_task_history_entry(
                workspace_root=Path(self._workspace_root),
                entry={
                    "ts": self._now_ts(),
                    "kind": f"import_center:{task}",
                    "title": f"导入中心：{task}（{package_id}）",
                    "package_id": str(package_id),
                    "input": str(input_path),
                    "overwrite_existing": bool(overwrite_existing),
                    "payload": payload,
                },
            )

        def _on_failed(err_text: str) -> None:
            self._set_execute_failed(str(err_text))

        def _on_finished() -> None:
            self._runtime["execute_worker"] = None

        if hasattr(worker, "progress_changed"):
            worker.progress_changed.connect(_on_progress)
        if hasattr(worker, "succeeded"):
            worker.succeeded.connect(_on_succeeded)
        if hasattr(worker, "failed"):
            worker.failed.connect(_on_failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(_on_finished)

    def _set_all_graph_checks(self, checked: bool) -> None:
        """将节点图清单中的勾选状态批量置为全选或全不选。"""
        for i in range(int(self._widgets.step2.gil_selected_graphs_list.count())):
            it = self._widgets.step2.gil_selected_graphs_list.item(i)
            if it is None:
                continue
            it.setCheckState(self._QtCore.Qt.CheckState.Checked if checked else self._QtCore.Qt.CheckState.Unchecked)

    def _scan_gil_graphs(self) -> None:
        """启动后台扫描 `.gil` 节点图清单并回填到步骤2列表。"""
        du = self._dialog_utils()
        s1 = self._widgets.step1
        s2 = self._widgets.step2
        input_text = str(s1.input_path_edit.text() or "").strip()
        if input_text == "":
            du.show_warning_dialog(self._widgets.dialog, "提示", "请先在步骤1选择一个 .gil 文件。")
            return
        input_path = Path(input_text).resolve()
        if (not input_path.is_file()) or input_path.suffix.lower() != ".gil":
            du.show_warning_dialog(self._widgets.dialog, "提示", "输入文件不是有效的 .gil。")
            return

        s2.gil_selected_scan_btn.setEnabled(False)
        s2.gil_selected_scan_status_label.setText("正在分析节点图清单…（请稍候）")
        s2.gil_selected_graphs_list.clear()

        worker = GilScanGraphsWorker(QtCore=self._QtCore, input_gil=Path(input_path)).thread
        self._runtime["scan_worker"] = worker

        def _on_scan_succeeded(graphs_obj: object) -> None:
            graphs = list(graphs_obj) if isinstance(graphs_obj, list) else []
            scanned = [dict(x) for x in graphs if isinstance(x, dict)]
            s2.gil_selected_graphs_list.clear()
            for g in scanned:
                gid = g.get("graph_id_int")
                name = str(g.get("graph_name") or "").strip()
                gid_int = int(gid) if isinstance(gid, int) else None
                if gid_int is None:
                    continue
                label = f"{name or '<未命名>'}  (graph_id_int={gid_int})"
                item = self._QtWidgets.QListWidgetItem(label)
                item.setFlags(item.flags() | self._QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(self._QtCore.Qt.CheckState.Checked)
                item.setData(self._QtCore.Qt.ItemDataRole.UserRole, int(gid_int))
                s2.gil_selected_graphs_list.addItem(item)
            s2.gil_selected_scan_status_label.setText(f"已分析：{len(scanned)} 张节点图。")
            s2.gil_selected_scan_btn.setEnabled(True)
            self._sync_preview_texts()

        def _on_scan_failed(err_text: str) -> None:
            s2.gil_selected_scan_status_label.setText("分析失败（错误已写入执行页）。")
            self._widgets.step3.result_text.setPlainText(str(err_text))
            s2.gil_selected_scan_btn.setEnabled(True)

        def _on_scan_finished() -> None:
            self._runtime["scan_worker"] = None

        worker.succeeded.connect(_on_scan_succeeded)
        worker.failed.connect(_on_scan_failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(_on_scan_finished)
        worker.start()

    def _wire_buttons(self) -> None:
        """连接 footer 与执行页清空按钮。"""
        self._widgets.footer.back_btn.clicked.connect(self._go_prev_step)
        self._widgets.footer.next_btn.clicked.connect(self._go_next_step)
        self._widgets.wizard_tabs.currentChanged.connect(self._on_tabs_current_changed)
        self._widgets.step3.clear_log_btn.clicked.connect(lambda: self._widgets.step3.log_text.setPlainText(""))
        self._widgets.step3.clear_result_btn.clicked.connect(lambda: self._widgets.step3.result_text.setPlainText(""))

    def _wire_step1(self) -> None:
        """连接步骤1控件的联动刷新。"""
        s = self._widgets.step1
        s.task_combo.currentIndexChanged.connect(lambda *_: (self._sync_task_specific_ui(), self._sync_preview_texts()))
        s.target_mode_combo.currentIndexChanged.connect(lambda *_: (self._sync_target_mode_ui(), self._sync_preview_texts()))
        s.package_name_edit.textChanged.connect(lambda *_: self._sync_preview_texts())
        s.existing_package_combo.currentIndexChanged.connect(lambda *_: self._sync_preview_texts())
        s.overwrite_checkbox.toggled.connect(lambda *_: self._sync_preview_texts())
        s.input_path_edit.textChanged.connect(lambda *_: self._sync_preview_texts())

        s.export_node_graphs_cb.toggled.connect(lambda *_: (self._sync_generate_validate_enabled_state(), self._sync_preview_texts()))
        s.gia_import_kind_combo.currentIndexChanged.connect(lambda *_: (self._sync_gia_sub_options(), self._sync_preview_texts()))
        s.gia_instances_cb.toggled.connect(lambda *_: (self._sync_gia_sub_options(), self._sync_preview_texts()))
        s.generate_graph_code_checkbox.toggled.connect(lambda *_: (self._sync_generate_validate_enabled_state(), self._sync_preview_texts()))
        s.validate_after_generate_checkbox.toggled.connect(lambda *_: self._sync_preview_texts())
        s.enable_dll_dump_checkbox.toggled.connect(lambda *_: self._sync_preview_texts())

    def _wire_step2(self) -> None:
        """连接步骤2（节点图清单）的按钮事件。"""
        s2 = self._widgets.step2
        s2.gil_selected_scan_btn.clicked.connect(self._scan_gil_graphs)
        s2.gil_selected_select_all_btn.clicked.connect(lambda: self._set_all_graph_checks(True))
        s2.gil_selected_unselect_all_btn.clicked.connect(lambda: self._set_all_graph_checks(False))
        s2.gil_selected_graphs_list.itemChanged.connect(lambda *_: self._sync_preview_texts())


def wire_import_center_dialog(
    *,
    QtCore: Any,
    QtWidgets: Any,
    Colors: Any,
    Sizes: Any,
    ThemeManager: Any,
    main_window: object,
    widgets: ImportCenterDialogWidgets,
    workspace_root: Path,
    packages_root: Path,
    package_index_manager: object,
    sanitize_package_id: Callable[[str], str],
    template_package_dirname: str,
    importable_package_ids: list[str],
    existing_package_dirnames: list[str],
    generate_unique_name: Callable[[str, list[str]], str],
    refresh_and_select_package: Callable[[object, str], None],
    append_task_history_entry: Callable[..., None],
    now_ts: Callable[[], str],
) -> None:
    """构建并挂载导入中心 controller。"""
    _ = Colors, Sizes, ThemeManager, refresh_and_select_package
    _ImportCenterController(
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        main_window=main_window,
        widgets=widgets,
        workspace_root=Path(workspace_root),
        packages_root=Path(packages_root),
        package_index_manager=package_index_manager,
        sanitize_package_id=sanitize_package_id,
        template_package_dirname=str(template_package_dirname),
        importable_package_ids=list(importable_package_ids),
        existing_package_dirnames=list(existing_package_dirnames),
        generate_unique_name=generate_unique_name,
        append_task_history_entry=append_task_history_entry,
        now_ts=now_ts,
    ).wire()

