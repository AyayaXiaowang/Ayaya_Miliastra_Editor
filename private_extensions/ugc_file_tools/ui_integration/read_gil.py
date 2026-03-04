from __future__ import annotations

from pathlib import Path

from engine.utils.name_utils import generate_unique_name

from ._common import (
    ToolbarProgressWidgetSpec,
    make_toolbar_progress_widget_cls,
    resolve_packages_root_dir,
)


def on_read_clicked(main_window: object) -> None:
    from dataclasses import dataclass

    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation import dialog_utils
    from app.ui.foundation.base_widgets import FormDialog
    from app.ui.foundation.theme_manager import Colors, Sizes
    from .export_history import append_task_history_entry, now_ts

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    existing_worker = getattr(main_window, "_read_gil_worker", None)
    if isinstance(existing_worker, QtCore.QThread) and existing_worker.isRunning():
        dialog_utils.show_warning_dialog(
            main_window,
            "读取进行中",
            "已有一个读取任务正在运行，请等待完成后再开始新的读取。",
        )
        return

    app_state = getattr(main_window, "app_state", None)
    if app_state is None:
        raise RuntimeError("主窗口缺少 app_state，无法执行读取")

    workspace_root = Path(getattr(app_state, "workspace_path")).resolve()
    packages_root = resolve_packages_root_dir(workspace_root=workspace_root)
    packages_root.mkdir(parents=True, exist_ok=True)

    package_index_manager = getattr(app_state, "package_index_manager", None)
    if package_index_manager is None:
        raise RuntimeError("主窗口缺少 package_index_manager，无法执行读取")

    sanitize_fn = getattr(package_index_manager, "sanitize_package_id", None)
    if not callable(sanitize_fn):
        raise RuntimeError("PackageIndexManager 缺少 sanitize_package_id，无法生成目录名")

    existing_names = [p.name for p in packages_root.iterdir() if p.is_dir()]
    template_package_dirname = str(
        getattr(package_index_manager, "TEMPLATE_PACKAGE_DIRNAME", "示例项目模板") or ""
    ).strip()
    importable_package_ids = sorted(
        [name for name in existing_names if name and name != template_package_dirname],
        key=lambda text: str(text).casefold(),
    )

    @dataclass(frozen=True)
    class _ReadGilPlan:
        input_gil_path: Path
        package_id: str
        output_package_root: Path
        overwrite_existing: bool
        enable_dll_dump: bool
        generate_graph_code: bool
        validate_after_generate: bool

    class _ReadGilDialog(FormDialog):
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            super().__init__(title="读取 .gil", width=680, height=420, parent=parent)
            self.setWindowTitle("读取 .gil（导入为项目存档）")

            self._last_auto_name: str = ""
            self._plan: _ReadGilPlan | None = None

            # 输入文件
            file_row = QtWidgets.QWidget(self)
            file_row_layout = QtWidgets.QHBoxLayout(file_row)
            file_row_layout.setContentsMargins(0, 0, 0, 0)
            file_row_layout.setSpacing(Sizes.SPACING_SMALL)
            self.input_path_edit = QtWidgets.QLineEdit(file_row)
            self.input_path_edit.setPlaceholderText("请选择一个 .gil 文件…")
            browse_btn = QtWidgets.QPushButton("浏览…", file_row)
            browse_btn.clicked.connect(self._choose_input_file)
            file_row_layout.addWidget(self.input_path_edit, 1)
            file_row_layout.addWidget(browse_btn)
            self.add_form_field("输入文件：", file_row, field_name="input_file")

            # 导入目标模式
            self.target_mode_combo = QtWidgets.QComboBox(self)
            self.target_mode_combo.addItem("新建项目存档（推荐）", "new")
            self.target_mode_combo.addItem("导入到已有项目存档（覆盖同名文件）", "existing")
            self.add_form_field("导入目标：", self.target_mode_combo, field_name="target_mode")

            # 项目存档名
            self.package_name_edit = QtWidgets.QLineEdit(self)
            self.package_name_edit.setPlaceholderText("默认使用文件名，可自行修改")
            self.add_form_field("项目存档名：", self.package_name_edit, field_name="package_name")

            # 选择已有项目存档（仅 existing 模式可用）
            self.existing_package_combo = QtWidgets.QComboBox(self)
            self.existing_package_combo.setEditable(False)
            for package_id in importable_package_ids:
                self.existing_package_combo.addItem(str(package_id))
            self.add_form_field("目标存档：", self.existing_package_combo, field_name="existing_package")

            self.overwrite_warning_label = QtWidgets.QLabel("", self)
            self.overwrite_warning_label.setWordWrap(True)
            self.overwrite_warning_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
            )
            self.add_widget(self.overwrite_warning_label)

            # 选项：生成 + 校验
            options_box = QtWidgets.QGroupBox("选项", self)
            options_layout = QtWidgets.QVBoxLayout(options_box)
            options_layout.setContentsMargins(
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
            )
            options_layout.setSpacing(Sizes.SPACING_SMALL)

            self.generate_graph_code_checkbox = QtWidgets.QCheckBox("生成可识别的节点图代码（推荐）", options_box)
            self.generate_graph_code_checkbox.setChecked(True)
            self.generate_graph_code_checkbox.setToolTip(
                "启用后，将从“节点图/原始解析/pyugc_graphs”生成可在程序内浏览/校验的 Graph Code。\n"
                "关闭则只导入项目存档目录结构（不生成节点图源码）。"
            )
            options_layout.addWidget(self.generate_graph_code_checkbox)

            self.validate_graph_code_checkbox = QtWidgets.QCheckBox("生成后自动校验（推荐）", options_box)
            self.validate_graph_code_checkbox.setChecked(True)
            self.validate_graph_code_checkbox.setToolTip(
                "对生成的 Graph Code 执行一次单包校验，用于确保“可打开/可验证”闭环。"
            )
            options_layout.addWidget(self.validate_graph_code_checkbox)

            self.enable_dll_dump_checkbox = QtWidgets.QCheckBox(
                "解析并导出界面控件组（UI控件模板）",
                options_box,
            )
            self.enable_dll_dump_checkbox.setChecked(True)
            self.enable_dll_dump_checkbox.setToolTip(
                "启用后会额外执行一次 dump-json（纯 Python），并从中提取 UI 相关数据，\n"
                "导出到项目存档的 `管理配置/UI控件模板/`（用于后续写回/合并）。\n"
                "关闭则只走 pyugc 解析（不导出 UI 控件组资源）。"
            )
            options_layout.addWidget(self.enable_dll_dump_checkbox)
            self.add_widget(options_box)

            # 目标目录预览
            self.preview_label = QtWidgets.QLabel("", self)
            self.preview_label.setWordWrap(True)
            self.preview_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
            self.add_widget(self.preview_label)

            # 行为联动
            self.input_path_edit.textChanged.connect(self._on_input_path_text_changed)
            self.package_name_edit.textChanged.connect(self._update_preview)
            self.target_mode_combo.currentIndexChanged.connect(self._on_target_mode_changed)
            self.existing_package_combo.currentIndexChanged.connect(self._update_preview)
            self.generate_graph_code_checkbox.toggled.connect(self._on_generate_toggled)
            self._on_target_mode_changed()
            self._on_generate_toggled(self.generate_graph_code_checkbox.isChecked())
            self._update_preview()

        def _get_target_mode(self) -> str:
            mode = self.target_mode_combo.currentData()
            return str(mode or "new")

        def _on_target_mode_changed(self) -> None:
            is_existing = self._get_target_mode() == "existing"
            self.package_name_edit.setEnabled(not is_existing)
            self.existing_package_combo.setEnabled(is_existing)
            if is_existing:
                if not importable_package_ids:
                    self.overwrite_warning_label.setText(
                        "提示：当前没有可选的“已有项目存档”。\n"
                        "（示例项目模板不允许作为导入目标；请先新建一个项目存档。）"
                    )
                else:
                    self.overwrite_warning_label.setText(
                        "注意：导入到已有项目存档时，会覆盖同名文件（不可撤销）。\n"
                        "如开启“生成节点图代码”，将按覆盖模式重新生成 `自动解析_节点图_*.py`。"
                    )
            else:
                self.overwrite_warning_label.setText("")
            self._update_preview()

        def _choose_input_file(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "选择 .gil 文件",
                "",
                "GIL (*.gil);;所有文件 (*)",
            )
            if not path:
                return
            self.input_path_edit.setText(str(Path(path).resolve()))

        def _on_input_path_text_changed(self, text: str) -> None:
            resolved = str(text or "").strip()
            if not resolved:
                self._update_preview()
                return

            if self._get_target_mode() == "existing":
                self._update_preview()
                return

            p = Path(resolved)
            stem = p.stem
            should_autofill = False
            current_name = str(self.package_name_edit.text() or "")
            if current_name.strip() == "":
                should_autofill = True
            elif self._last_auto_name and current_name.strip() == self._last_auto_name.strip():
                should_autofill = True

            if should_autofill:
                self._last_auto_name = str(stem)
                self.package_name_edit.setText(str(stem))

            self._update_preview()

        def _on_generate_toggled(self, enabled: bool) -> None:
            self.validate_graph_code_checkbox.setEnabled(bool(enabled))
            if not enabled:
                self.validate_graph_code_checkbox.setChecked(False)
            self._update_preview()

        def _compute_sanitized_name(self) -> str:
            raw = str(self.package_name_edit.text() or "").strip()
            if raw == "":
                raw = "未命名项目存档"
            sanitized = str(sanitize_fn(raw) or "").strip()
            if sanitized == "":
                sanitized = "未命名项目存档"
            return sanitized

        def _compute_final_package_id(self) -> str:
            sanitized = self._compute_sanitized_name()
            return str(generate_unique_name(sanitized, existing_names))

        def _update_preview(self) -> None:
            input_text = str(self.input_path_edit.text() or "").strip()
            mode = self._get_target_mode()
            sanitized = self._compute_sanitized_name()
            final_id = self._compute_final_package_id()
            if mode == "existing":
                selected_id = str(self.existing_package_combo.currentText() or "").strip()
                target_path = (packages_root / selected_id).resolve() if selected_id else None
            else:
                target_path = (packages_root / final_id).resolve()

            details: list[str] = []
            if input_text:
                details.append(f"输入：{input_text}")
            if mode == "existing":
                if target_path is None:
                    details.append("输出：<未选择目标项目存档>")
                else:
                    details.append(f"输出：{str(target_path)}（覆盖同名文件）")
            else:
                details.append(f"输出：{str(target_path)}")

            if mode != "existing" and final_id != sanitized:
                details.append(f"提示：目录名将自动使用：{final_id}")

            if not self.generate_graph_code_checkbox.isChecked():
                details.append("注意：未开启“生成节点图代码”，导入后不会生成节点图源码。")

            self.preview_label.setText("\n".join(details))

        def validate(self) -> bool:
            input_text = str(self.input_path_edit.text() or "").strip()
            if input_text == "":
                self.show_error("请先选择一个 .gil 文件。")
                return False

            input_path = Path(input_text).resolve()
            if not input_path.is_file():
                self.show_error(f"文件不存在：{str(input_path)}")
                return False

            if input_path.suffix.lower() != ".gil":
                self.show_error("输入文件不是 .gil。")
                return False

            mode = self._get_target_mode()
            overwrite_existing = False

            if mode == "existing":
                if not importable_package_ids:
                    self.show_error("当前没有可选的“已有项目存档”。请先新建一个项目存档。")
                    return False
                selected_id = str(self.existing_package_combo.currentText() or "").strip()
                if selected_id == "":
                    self.show_error("请先选择一个目标项目存档。")
                    return False
                if selected_id == template_package_dirname:
                    self.show_error("不允许将导入结果写入“示例项目模板”。请改选其它项目存档。")
                    return False
                output_package_root = (packages_root / selected_id).resolve()
                if not output_package_root.exists() or not output_package_root.is_dir():
                    self.show_error(f"目标项目存档目录不存在：{str(output_package_root)}")
                    return False
                final_package_id = selected_id
                overwrite_existing = True
            else:
                final_package_id = self._compute_final_package_id()
                output_package_root = (packages_root / final_package_id).resolve()
                if output_package_root.exists():
                    self.show_error(f"目标目录已存在，请修改项目存档名：{str(output_package_root)}")
                    return False

            generate_graph_code = bool(self.generate_graph_code_checkbox.isChecked())
            validate_after_generate = (
                bool(self.validate_graph_code_checkbox.isChecked()) if generate_graph_code else False
            )
            enable_dll_dump = bool(self.enable_dll_dump_checkbox.isChecked())

            self._plan = _ReadGilPlan(
                input_gil_path=input_path,
                package_id=str(final_package_id),
                output_package_root=output_package_root,
                overwrite_existing=bool(overwrite_existing),
                enable_dll_dump=enable_dll_dump,
                generate_graph_code=generate_graph_code,
                validate_after_generate=validate_after_generate,
            )
            return True

        def get_plan(self) -> _ReadGilPlan | None:
            return self._plan

    dialog = _ReadGilDialog(main_window)
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return

    plan = dialog.get_plan()
    if plan is None:
        return

    package_library_widget = getattr(main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法显示读取进度")

    ensure_widget = getattr(package_library_widget, "ensure_extension_toolbar_widget", None)
    if not callable(ensure_widget):
        raise RuntimeError("PackageLibraryWidget 缺少 ensure_extension_toolbar_widget，无法显示读取进度")

    ProgressWidgetCls = make_toolbar_progress_widget_cls(
        ToolbarProgressWidgetSpec(kind="read_gil", initial_label="准备读取…", progress_width=180),
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )

    def _get_progress_widget(*, visible: bool) -> QtWidgets.QWidget:
        widget_obj = ensure_widget(
            "ugc_file_tools.read_gil_progress",
            create_widget=lambda parent: ProgressWidgetCls(parent),
            visible=visible,
        )
        if not isinstance(widget_obj, ProgressWidgetCls):
            raise TypeError(
                f"read progress widget 类型不匹配（got: {type(widget_obj).__name__}）"
            )
        return widget_obj

    def _set_read_button_enabled(enabled: bool) -> None:
        btn = getattr(package_library_widget, "_ugc_file_tools_read_btn", None)
        if isinstance(btn, QtWidgets.QAbstractButton):
            btn.setEnabled(bool(enabled))

    class _ReadGilWorker(QtCore.QThread):
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label
        succeeded = QtCore.pyqtSignal(str, object)  # package_id, validation_summary(dict|None)

        def __init__(self, *, plan: _ReadGilPlan, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._plan = plan
            self.setObjectName(f"ReadGilWorker:{self._plan.package_id}")

        def run(self) -> None:
            from ugc_file_tools.pipelines.gil_to_project_archive import (
                GilToProjectArchivePlan,
                run_gil_to_project_archive,
            )

            ensure_structure = getattr(package_index_manager, "ensure_package_directory_structure", None)
            if not callable(ensure_structure):
                raise RuntimeError("PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构")

            report = run_gil_to_project_archive(
                plan=GilToProjectArchivePlan(
                    input_gil_file_path=Path(self._plan.input_gil_path),
                    output_package_root=Path(self._plan.output_package_root),
                    package_id=str(self._plan.package_id),
                    enable_dll_dump=bool(self._plan.enable_dll_dump),
                    data_blob_min_bytes_for_decode=512,
                    generic_scan_min_bytes=256,
                    focus_graph_id=None,
                    ensure_package_structure_fn=ensure_structure,
                    generate_graph_code=bool(self._plan.generate_graph_code),
                    overwrite_graph_code=bool(self._plan.overwrite_existing),
                    validate_graph_code_after_generate=bool(self._plan.validate_after_generate),
                    graph_generater_root_for_validation=Path(workspace_root),
                    set_last_opened=False,
                ),
                progress_cb=lambda current, total, label: self.progress_changed.emit(
                    int(current), int(total), str(label)
                ),
            )

            validation_summary = report.get("validation_summary")
            self.succeeded.emit(str(self._plan.package_id), validation_summary)

    worker = _ReadGilWorker(plan=plan, parent=main_window)
    setattr(main_window, "_read_gil_worker", worker)

    state = {"succeeded": False}

    def _on_progress(current: int, total: int, label: str) -> None:
        progress_widget = _get_progress_widget(visible=True)
        progress_widget.set_status(label=str(label), current=int(current), total=int(total))

    def _on_succeeded(package_id: str, validation_summary_obj: object) -> None:
        state["succeeded"] = True
        _get_progress_widget(visible=False).set_status(label="完成", current=0, total=0)
        _set_read_button_enabled(True)

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

        if isinstance(validation_summary_obj, dict):
            dialog_utils.show_info_dialog(
                main_window,
                "校验结果",
                f"项目存档：{str(package_id)}\n"
                f"错误：{int(validation_summary_obj.get('errors', 0) or 0)}\n"
                f"警告：{int(validation_summary_obj.get('warnings', 0) or 0)}",
            )

        append_task_history_entry(
            workspace_root=Path(workspace_root),
            entry={
                "ts": now_ts(),
                "kind": "read_gil",
                "title": f"读取GIL → 导入（{package_id}）",
                "package_id": str(package_id),
                "input_gil": str(plan.input_gil_path),
                "overwrite_existing": bool(plan.overwrite_existing),
                "generate_graph_code": bool(plan.generate_graph_code),
                "validate_after_generate": bool(plan.validate_after_generate),
                "validation_summary": (dict(validation_summary_obj) if isinstance(validation_summary_obj, dict) else None),
            },
        )

    def _on_worker_finished() -> None:
        setattr(main_window, "_read_gil_worker", None)
        if state["succeeded"]:
            return
        _get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
        _set_read_button_enabled(True)
        dialog_utils.show_warning_dialog(main_window, "读取失败", "读取失败（请查看控制台错误）。")

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_succeeded)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_worker_finished)
    _set_read_button_enabled(False)
    _get_progress_widget(visible=True).set_status(label="准备开始…", current=0, total=0)
    worker.start()


