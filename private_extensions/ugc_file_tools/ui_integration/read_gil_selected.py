from __future__ import annotations

from pathlib import Path

from engine.utils.name_utils import generate_unique_name

from ._common import (
    ToolbarProgressWidgetSpec,
    make_toolbar_progress_widget_cls,
    resolve_packages_root_dir,
)


def on_read_clicked(main_window: object) -> None:
    """选择性读取 `.gil` → 导入为项目存档（支持勾选多个节点图）。"""
    from dataclasses import dataclass

    from PyQt6 import QtCore, QtGui, QtWidgets

    from app.ui.foundation import dialog_utils
    from app.ui.foundation.base_widgets import FormDialog
    from app.ui.foundation.theme_manager import Colors, Sizes
    from .export_history import append_task_history_entry, now_ts

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    existing_worker = getattr(main_window, "_read_gil_selected_worker", None)
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

    ensure_structure = getattr(package_index_manager, "ensure_package_directory_structure", None)
    if not callable(ensure_structure):
        raise RuntimeError("PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构")

    existing_names = [p.name for p in packages_root.iterdir() if p.is_dir()]
    template_package_dirname = str(
        getattr(package_index_manager, "TEMPLATE_PACKAGE_DIRNAME", "示例项目模板") or ""
    ).strip()
    importable_package_ids = sorted(
        [name for name in existing_names if name and name != template_package_dirname],
        key=lambda text: str(text).casefold(),
    )

    @dataclass(frozen=True)
    class _ReadGilSelectedPlan:
        input_gil_path: Path
        package_id: str
        output_package_root: Path
        overwrite_existing: bool

        # ===== 导入范围（资源段开关） =====
        export_raw_pyugc_dump: bool
        export_node_graphs: bool
        export_templates: bool
        export_instances: bool
        export_combat_presets: bool
        export_section15: bool
        export_struct_definitions: bool
        export_signals: bool
        export_data_blobs: bool
        export_decoded_dtype_type3: bool
        export_decoded_generic: bool

        # ===== 选择性节点图 =====
        selected_node_graph_id_ints: list[int]

        # ===== 选项：生成 + 校验 =====
        enable_dll_dump: bool
        generate_graph_code: bool
        validate_after_generate: bool

    class _ReadGilSelectedDialog(FormDialog):
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            super().__init__(title="选择性读取 .gil", width=920, height=720, parent=parent)
            self.setWindowTitle("选择性读取 .gil（导入为项目存档）")

            self._last_auto_name: str = ""
            self._plan: _ReadGilSelectedPlan | None = None

            self._scan_worker: QtCore.QThread | None = None
            self._scanned_graphs: list[dict] = []

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

            # ===== 导入范围（资源段） =====
            parts_box = QtWidgets.QGroupBox("导入范围（可选）", self)
            parts_layout = QtWidgets.QGridLayout(parts_box)
            parts_layout.setContentsMargins(
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
            )
            parts_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
            parts_layout.setVerticalSpacing(Sizes.SPACING_SMALL)

            self.export_node_graphs_cb = QtWidgets.QCheckBox("节点图（可多选）", parts_box)
            self.export_node_graphs_cb.setChecked(True)
            self.export_templates_cb = QtWidgets.QCheckBox("元件", parts_box)
            self.export_templates_cb.setChecked(False)
            self.export_instances_cb = QtWidgets.QCheckBox("实体摆放", parts_box)
            self.export_instances_cb.setChecked(False)
            self.export_struct_defs_cb = QtWidgets.QCheckBox("结构体定义", parts_box)
            self.export_struct_defs_cb.setChecked(False)
            self.export_signals_cb = QtWidgets.QCheckBox("信号定义", parts_box)
            self.export_signals_cb.setChecked(False)
            self.export_combat_presets_cb = QtWidgets.QCheckBox("战斗预设（玩家模板/职业）", parts_box)
            self.export_combat_presets_cb.setChecked(False)
            self.export_section15_cb = QtWidgets.QCheckBox("战斗/管理条目（技能/道具/关卡设置等）", parts_box)
            self.export_section15_cb.setChecked(False)

            self.export_raw_pyugc_cb = QtWidgets.QCheckBox("原始解析（pyugc dump/string_index）", parts_box)
            self.export_raw_pyugc_cb.setChecked(False)
            self.export_data_blobs_cb = QtWidgets.QCheckBox("数据块解析（原始解析/数据块 + decoded_*）", parts_box)
            self.export_data_blobs_cb.setChecked(False)

            parts_layout.addWidget(self.export_node_graphs_cb, 0, 0)
            parts_layout.addWidget(self.export_templates_cb, 0, 1)
            parts_layout.addWidget(self.export_instances_cb, 0, 2)
            parts_layout.addWidget(self.export_struct_defs_cb, 1, 0)
            parts_layout.addWidget(self.export_signals_cb, 1, 1)
            parts_layout.addWidget(self.export_combat_presets_cb, 1, 2)
            parts_layout.addWidget(self.export_section15_cb, 2, 0, 1, 3)
            parts_layout.addWidget(self.export_raw_pyugc_cb, 3, 0, 1, 3)
            parts_layout.addWidget(self.export_data_blobs_cb, 4, 0, 1, 3)

            hint = QtWidgets.QLabel(
                "提示：默认仅导入节点图，避免整包导入带来大量无关资源。\n"
                "若你想“整包还原为项目存档”，请使用“读取 .gil（整包导入）”。",
                parts_box,
            )
            hint.setWordWrap(True)
            hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
            parts_layout.addWidget(hint, 5, 0, 1, 3)

            self.add_widget(parts_box)

            # ===== 节点图选择 =====
            graphs_box = QtWidgets.QGroupBox("节点图选择（多选）", self)
            graphs_box_layout = QtWidgets.QVBoxLayout(graphs_box)
            graphs_box_layout.setContentsMargins(
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
            )
            graphs_box_layout.setSpacing(Sizes.SPACING_SMALL)

            action_row = QtWidgets.QWidget(graphs_box)
            action_row_layout = QtWidgets.QHBoxLayout(action_row)
            action_row_layout.setContentsMargins(0, 0, 0, 0)
            action_row_layout.setSpacing(Sizes.SPACING_SMALL)

            self.scan_btn = QtWidgets.QPushButton("分析节点图清单…", action_row)
            self.scan_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            self.scan_btn.clicked.connect(self._scan_graphs)

            self.select_all_btn = QtWidgets.QPushButton("全选", action_row)
            self.select_all_btn.clicked.connect(lambda: self._set_all_graph_checks(True))
            self.unselect_all_btn = QtWidgets.QPushButton("全不选", action_row)
            self.unselect_all_btn.clicked.connect(lambda: self._set_all_graph_checks(False))

            action_row_layout.addWidget(self.scan_btn)
            action_row_layout.addStretch(1)
            action_row_layout.addWidget(self.select_all_btn)
            action_row_layout.addWidget(self.unselect_all_btn)
            graphs_box_layout.addWidget(action_row)

            self.scan_status_label = QtWidgets.QLabel("尚未分析节点图清单。", graphs_box)
            self.scan_status_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
            graphs_box_layout.addWidget(self.scan_status_label)

            self.graphs_list = QtWidgets.QListWidget(graphs_box)
            self.graphs_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
            self.graphs_list.setMinimumHeight(220)
            graphs_box_layout.addWidget(self.graphs_list, 1)

            self.add_widget(graphs_box)

            # ===== 选项：生成 + 校验 =====
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
            self.validate_graph_code_checkbox = QtWidgets.QCheckBox("生成后自动校验（推荐）", options_box)
            self.validate_graph_code_checkbox.setChecked(True)

            self.enable_dll_dump_checkbox = QtWidgets.QCheckBox(
                "解析并导出界面控件组（UI控件模板；会变慢）",
                options_box,
            )
            self.enable_dll_dump_checkbox.setChecked(False)

            options_layout.addWidget(self.generate_graph_code_checkbox)
            options_layout.addWidget(self.validate_graph_code_checkbox)
            options_layout.addWidget(self.enable_dll_dump_checkbox)
            self.add_widget(options_box)

            # 目标目录预览
            self.preview_label = QtWidgets.QLabel("", self)
            self.preview_label.setWordWrap(True)
            self.preview_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
            self.add_widget(self.preview_label)

            # 行为联动
            self.input_path_edit.textChanged.connect(self._on_input_path_text_changed)
            self.target_mode_combo.currentIndexChanged.connect(self._on_target_mode_changed)
            self.package_name_edit.textChanged.connect(self._update_preview)
            self.existing_package_combo.currentIndexChanged.connect(self._update_preview)

            self.export_node_graphs_cb.toggled.connect(self._sync_graphs_enabled_state)
            self.generate_graph_code_checkbox.toggled.connect(self._on_generate_toggled)
            self.export_data_blobs_cb.toggled.connect(self._sync_data_blob_state)

            self._on_target_mode_changed()
            self._sync_graphs_enabled_state(bool(self.export_node_graphs_cb.isChecked()))
            self._on_generate_toggled(bool(self.generate_graph_code_checkbox.isChecked()))
            self._sync_data_blob_state(bool(self.export_data_blobs_cb.isChecked()))
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
                        "建议优先导入到“新建项目存档”作为片段包，再手工合并。"
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

            # 新建模式：自动填充 package_name
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

        def _sync_graphs_enabled_state(self, enabled: bool) -> None:
            self.scan_btn.setEnabled(bool(enabled))
            self.select_all_btn.setEnabled(bool(enabled))
            self.unselect_all_btn.setEnabled(bool(enabled))
            self.graphs_list.setEnabled(bool(enabled))
            self.generate_graph_code_checkbox.setEnabled(bool(enabled))
            if not enabled:
                self.generate_graph_code_checkbox.setChecked(False)
            self._update_preview()

        def _sync_data_blob_state(self, enabled: bool) -> None:
            # decoded_* 依赖 data_blobs；这里直接跟随
            if not enabled:
                # 不做额外 UI：直接在 plan 构建时同步关闭 decoded 开关
                pass
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
                if final_id != sanitized:
                    details.append(f"提示：目录名将自动使用：{final_id}")

            # 简洁列出导入范围
            parts: list[str] = []
            if self.export_node_graphs_cb.isChecked():
                parts.append("节点图")
            if self.export_templates_cb.isChecked():
                parts.append("元件库")
            if self.export_instances_cb.isChecked():
                parts.append("实体摆放")
            if self.export_struct_defs_cb.isChecked():
                parts.append("结构体")
            if self.export_signals_cb.isChecked():
                parts.append("信号")
            if self.export_combat_presets_cb.isChecked():
                parts.append("战斗预设")
            if self.export_section15_cb.isChecked():
                parts.append("战斗/管理条目")
            if self.export_raw_pyugc_cb.isChecked():
                parts.append("原始解析")
            if self.export_data_blobs_cb.isChecked():
                parts.append("数据块解析")
            details.append("导入范围：" + (" + ".join(parts) if parts else "<未选择>"))

            if self.export_node_graphs_cb.isChecked():
                details.append("节点图：请先点击“分析节点图清单”并勾选要导入的图。")

            self.preview_label.setText("\n".join(details))

        def _set_all_graph_checks(self, checked: bool) -> None:
            for i in range(int(self.graphs_list.count())):
                it = self.graphs_list.item(i)
                if it is None:
                    continue
                it.setCheckState(
                    QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
                )

        def _scan_graphs(self) -> None:
            input_text = str(self.input_path_edit.text() or "").strip()
            if input_text == "":
                self.show_error("请先选择一个 .gil 文件。")
                return
            input_path = Path(input_text).resolve()
            if not input_path.is_file() or input_path.suffix.lower() != ".gil":
                self.show_error("输入文件不是有效的 .gil。")
                return

            if self._scan_worker is not None and isinstance(self._scan_worker, QtCore.QThread):
                if self._scan_worker.isRunning():
                    return

            # UI 状态
            self.scan_btn.setEnabled(False)
            self.scan_status_label.setText("正在分析节点图清单…（请稍候）")
            self.graphs_list.clear()
            self._scanned_graphs = []

            class _ScanWorker(QtCore.QThread):
                succeeded = QtCore.pyqtSignal(object)  # list[dict]

                def __init__(self, *, input_gil: Path, parent: QtCore.QObject | None = None) -> None:
                    super().__init__(parent)
                    self._input_gil = Path(input_gil).resolve()
                    self.setObjectName("ScanGilNodeGraphs")

                def run(self) -> None:
                    from ugc_file_tools.gil_package_exporter.node_graph_listing import list_gil_node_graphs
                    from ugc_file_tools.gil_package_exporter.paths import resolve_default_dtype_path

                    dtype = Path(resolve_default_dtype_path()).resolve()
                    graphs = list_gil_node_graphs(input_gil_file_path=Path(self._input_gil), dtype_path=dtype)
                    self.succeeded.emit(graphs)

            worker = _ScanWorker(input_gil=input_path, parent=self)
            self._scan_worker = worker

            def _on_succeeded(graphs_obj: object) -> None:
                graphs = list(graphs_obj) if isinstance(graphs_obj, list) else []
                self._scanned_graphs = [dict(x) for x in graphs if isinstance(x, dict)]
                self.graphs_list.clear()

                for g in self._scanned_graphs:
                    gid = g.get("graph_id_int")
                    name = str(g.get("graph_name") or "").strip()
                    gid_int = int(gid) if isinstance(gid, int) else None
                    if gid_int is None:
                        continue
                    label = f"{name or '<未命名>'}  (graph_id_int={gid_int})"
                    item = QtWidgets.QListWidgetItem(label)
                    item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(QtCore.Qt.CheckState.Checked)
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, int(gid_int))
                    self.graphs_list.addItem(item)

                self.scan_status_label.setText(f"已分析：{len(self._scanned_graphs)} 张节点图。")
                self.scan_btn.setEnabled(True)

            def _on_finished() -> None:
                # 若失败：保持按钮可用（失败原因由控制台抛出）
                if self.scan_btn.isEnabled():
                    return
                self.scan_btn.setEnabled(True)
                if not self._scanned_graphs:
                    self.scan_status_label.setText("分析失败（请查看控制台错误）。")

            worker.succeeded.connect(_on_succeeded)
            worker.finished.connect(worker.deleteLater)
            worker.finished.connect(_on_finished)
            worker.start()

        def _collect_selected_graph_ids(self) -> list[int]:
            ids: list[int] = []
            for i in range(int(self.graphs_list.count())):
                it = self.graphs_list.item(i)
                if it is None:
                    continue
                if it.checkState() != QtCore.Qt.CheckState.Checked:
                    continue
                gid = it.data(QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(gid, int):
                    ids.append(int(gid))
            return sorted(set(ids))

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

            export_node_graphs = bool(self.export_node_graphs_cb.isChecked())
            selected_graph_ids: list[int] = []
            if export_node_graphs:
                selected_graph_ids = self._collect_selected_graph_ids()
                if not selected_graph_ids:
                    self.show_error("请先分析并勾选至少 1 张节点图。")
                    return False

            generate_graph_code = bool(self.generate_graph_code_checkbox.isChecked())
            validate_after_generate = bool(self.validate_graph_code_checkbox.isChecked()) if generate_graph_code else False
            if generate_graph_code and not export_node_graphs:
                self.show_error("启用“生成节点图代码”需要同时勾选导入范围：节点图。")
                return False

            export_data_blobs = bool(self.export_data_blobs_cb.isChecked())
            export_decoded_dtype_type3 = bool(export_data_blobs)
            export_decoded_generic = bool(export_data_blobs)

            self._plan = _ReadGilSelectedPlan(
                input_gil_path=input_path,
                package_id=str(final_package_id),
                output_package_root=output_package_root,
                overwrite_existing=bool(overwrite_existing),
                export_raw_pyugc_dump=bool(self.export_raw_pyugc_cb.isChecked()),
                export_node_graphs=bool(export_node_graphs),
                export_templates=bool(self.export_templates_cb.isChecked()),
                export_instances=bool(self.export_instances_cb.isChecked()),
                export_combat_presets=bool(self.export_combat_presets_cb.isChecked()),
                export_section15=bool(self.export_section15_cb.isChecked()),
                export_struct_definitions=bool(self.export_struct_defs_cb.isChecked()),
                export_signals=bool(self.export_signals_cb.isChecked()),
                export_data_blobs=bool(export_data_blobs),
                export_decoded_dtype_type3=bool(export_decoded_dtype_type3),
                export_decoded_generic=bool(export_decoded_generic),
                selected_node_graph_id_ints=list(selected_graph_ids),
                enable_dll_dump=bool(self.enable_dll_dump_checkbox.isChecked()),
                generate_graph_code=bool(generate_graph_code),
                validate_after_generate=bool(validate_after_generate),
            )
            return True

        def get_plan(self) -> _ReadGilSelectedPlan | None:
            return self._plan

    dialog = _ReadGilSelectedDialog(main_window)
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
        ToolbarProgressWidgetSpec(kind="read_gil_selected", initial_label="准备读取…", progress_width=200),
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )

    def _get_progress_widget(*, visible: bool) -> QtWidgets.QWidget:
        widget_obj = ensure_widget(
            "ugc_file_tools.read_gil_selected_progress",
            create_widget=lambda parent: ProgressWidgetCls(parent),
            visible=visible,
        )
        if not isinstance(widget_obj, ProgressWidgetCls):
            raise TypeError(f"read progress widget 类型不匹配（got: {type(widget_obj).__name__}）")
        return widget_obj

    class _ReadGilSelectedWorker(QtCore.QThread):
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label
        succeeded = QtCore.pyqtSignal(str, object)  # package_id, report(dict)

        def __init__(self, *, plan: _ReadGilSelectedPlan, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._plan = plan
            self.setObjectName(f"ReadGilSelectedWorker:{self._plan.package_id}")

        def run(self) -> None:
            from ugc_file_tools.pipelines.gil_to_project_archive import (
                GilToProjectArchivePlan,
                run_gil_to_project_archive,
            )

            report = run_gil_to_project_archive(
                plan=GilToProjectArchivePlan(
                    input_gil_file_path=Path(self._plan.input_gil_path),
                    output_package_root=Path(self._plan.output_package_root),
                    package_id=str(self._plan.package_id),
                    enable_dll_dump=bool(self._plan.enable_dll_dump),
                    data_blob_min_bytes_for_decode=512,
                    generic_scan_min_bytes=256,
                    focus_graph_id=None,
                    selected_node_graph_id_ints=list(self._plan.selected_node_graph_id_ints),
                    export_raw_pyugc_dump=bool(self._plan.export_raw_pyugc_dump),
                    export_node_graphs=bool(self._plan.export_node_graphs),
                    export_templates=bool(self._plan.export_templates),
                    export_instances=bool(self._plan.export_instances),
                    export_combat_presets=bool(self._plan.export_combat_presets),
                    export_section15=bool(self._plan.export_section15),
                    export_struct_definitions=bool(self._plan.export_struct_definitions),
                    export_signals=bool(self._plan.export_signals),
                    export_data_blobs=bool(self._plan.export_data_blobs),
                    export_decoded_dtype_type3=bool(self._plan.export_decoded_dtype_type3),
                    export_decoded_generic=bool(self._plan.export_decoded_generic),
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
            self.succeeded.emit(str(self._plan.package_id), report)

    worker = _ReadGilSelectedWorker(plan=plan, parent=main_window)
    setattr(main_window, "_read_gil_selected_worker", worker)

    state = {"succeeded": False}

    def _on_progress(current: int, total: int, label: str) -> None:
        progress_widget = _get_progress_widget(visible=True)
        progress_widget.set_status(label=str(label), current=int(current), total=int(total))

    def _on_succeeded(package_id: str, report_obj: object) -> None:
        state["succeeded"] = True
        _get_progress_widget(visible=False).set_status(label="完成", current=0, total=0)

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

        report = dict(report_obj) if isinstance(report_obj, dict) else {}
        selected_graphs = list(plan.selected_node_graph_id_ints or [])
        dialog_utils.show_info_dialog(
            main_window,
            "导入完成",
            "选择性读取完成：\n"
            f"- 项目存档：{str(package_id)}\n"
            f"- 节点图：{len(selected_graphs)} 张\n"
            f"- 输入：{str(plan.input_gil_path)}",
        )

        append_task_history_entry(
            workspace_root=Path(workspace_root),
            entry={
                "ts": now_ts(),
                "kind": "read_gil_selected",
                "title": f"读取GIL（选择）→ 导入（{package_id}）",
                "package_id": str(package_id),
                "input_gil": str(plan.input_gil_path),
                "selected_node_graph_id_ints": list(selected_graphs),
                "export_flags": {
                    "raw_pyugc": bool(plan.export_raw_pyugc_dump),
                    "node_graphs": bool(plan.export_node_graphs),
                    "templates": bool(plan.export_templates),
                    "instances": bool(plan.export_instances),
                    "combat_presets": bool(plan.export_combat_presets),
                    "section15": bool(plan.export_section15),
                    "struct_definitions": bool(plan.export_struct_definitions),
                    "signals": bool(plan.export_signals),
                    "data_blobs": bool(plan.export_data_blobs),
                    "decoded_dtype_type3": bool(plan.export_decoded_dtype_type3),
                    "decoded_generic": bool(plan.export_decoded_generic),
                },
                "generate_graph_code": bool(plan.generate_graph_code),
                "validate_after_generate": bool(plan.validate_after_generate),
                "report": report,
            },
        )

    def _on_worker_finished() -> None:
        setattr(main_window, "_read_gil_selected_worker", None)
        if state["succeeded"]:
            return
        _get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
        dialog_utils.show_warning_dialog(main_window, "读取失败", "读取失败（请查看控制台错误）。")

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_succeeded)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_worker_finished)
    _get_progress_widget(visible=True).set_status(label="准备开始…", current=0, total=0)
    worker.start()

