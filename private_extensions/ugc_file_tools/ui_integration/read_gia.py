from __future__ import annotations

from pathlib import Path

from engine.utils.name_utils import generate_unique_name

from ._common import (
    ToolbarProgressWidgetSpec,
    get_selected_package_id,
    make_toolbar_progress_widget_cls,
    resolve_packages_root_dir,
)


def on_read_clicked(main_window: object) -> None:
    """读取/导入 `.gia` 到项目存档。

    当前支持：
    - 元件 + 实体摆放 bundle.gia → 写入 `元件库/` 与 `实体摆放/`
    - 玩家模板 player_template.gia → 写入 `战斗预设/玩家模板/` 与 `管理配置/关卡变量/自定义变量/`
    """
    from dataclasses import dataclass

    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation import dialog_utils
    from app.ui.foundation.base_widgets import FormDialog
    from app.ui.foundation.theme_manager import Colors, Sizes
    from .export_history import append_task_history_entry, now_ts

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    existing_worker = getattr(main_window, "_read_gia_worker", None)
    if isinstance(existing_worker, QtCore.QThread) and existing_worker.isRunning():
        dialog_utils.show_warning_dialog(
            main_window,
            "导入进行中",
            "已有一个 `.gia` 导入任务正在运行，请等待完成后再开始新的导入。",
        )
        return

    app_state = getattr(main_window, "app_state", None)
    if app_state is None:
        raise RuntimeError("主窗口缺少 app_state，无法执行导入")

    workspace_root = Path(getattr(app_state, "workspace_path")).resolve()
    packages_root = resolve_packages_root_dir(workspace_root=workspace_root)
    packages_root.mkdir(parents=True, exist_ok=True)

    package_index_manager = getattr(app_state, "package_index_manager", None)
    if package_index_manager is None:
        raise RuntimeError("主窗口缺少 package_index_manager，无法执行导入")

    sanitize_fn = getattr(package_index_manager, "sanitize_package_id", None)
    if not callable(sanitize_fn):
        raise RuntimeError("PackageIndexManager 缺少 sanitize_package_id，无法生成目录名")

    ensure_structure = getattr(package_index_manager, "ensure_package_directory_structure", None)
    if not callable(ensure_structure):
        raise RuntimeError(
            "PackageIndexManager 缺少 ensure_package_directory_structure，无法补齐目录结构"
        )

    existing_names = [p.name for p in packages_root.iterdir() if p.is_dir()]
    template_package_dirname = str(
        getattr(package_index_manager, "TEMPLATE_PACKAGE_DIRNAME", "示例项目模板") or ""
    ).strip()
    importable_package_ids = sorted(
        [name for name in existing_names if name and name != template_package_dirname],
        key=lambda text: str(text).casefold(),
    )
    default_existing_package_id = str(get_selected_package_id(main_window) or "").strip()
    if default_existing_package_id in {"global_view", "unclassified_view"}:
        default_existing_package_id = ""
    if default_existing_package_id not in set(importable_package_ids):
        default_existing_package_id = ""

    @dataclass(frozen=True)
    class _ReadGiaPlan:
        input_gia_path: Path
        import_kind: str  # templates_instances | player_template | node_graphs
        package_id: str
        output_package_root: Path
        overwrite_existing: bool
        import_templates: bool
        import_instances: bool
        instances_mode: str = "decorations_to_template"  # decorations_to_template | decorations_carrier | instances（仅 templates_instances 使用）
        decode_max_depth: int
        validate_after_import: bool

    class _ReadGiaDialog(FormDialog):
        def __init__(self, parent: QtWidgets.QWidget) -> None:
            super().__init__(title="导入 .gia", width=720, height=520, parent=parent)
            self.setWindowTitle("导入 .gia（写入项目存档）")

            self._last_auto_name: str = ""
            self._plan: _ReadGiaPlan | None = None

            # 输入文件
            file_row = QtWidgets.QWidget(self)
            file_row_layout = QtWidgets.QHBoxLayout(file_row)
            file_row_layout.setContentsMargins(0, 0, 0, 0)
            file_row_layout.setSpacing(Sizes.SPACING_SMALL)
            self.input_path_edit = QtWidgets.QLineEdit(file_row)
            self.input_path_edit.setPlaceholderText("请选择一个 .gia 文件…")
            browse_btn = QtWidgets.QPushButton("浏览…", file_row)
            browse_btn.clicked.connect(self._choose_input_file)
            file_row_layout.addWidget(self.input_path_edit, 1)
            file_row_layout.addWidget(browse_btn)
            self.add_form_field("输入文件：", file_row, field_name="input_file")

            # 导入类型
            self.import_kind_combo = QtWidgets.QComboBox(self)
            self.import_kind_combo.addItem("元件 + 实体摆放（bundle.gia）", "templates_instances")
            self.import_kind_combo.addItem("玩家模板（player_template.gia）", "player_template")
            self.import_kind_combo.addItem("节点图（node_graph.gia）", "node_graphs")
            self.import_kind_combo.setToolTip(
                "说明：\n"
                "- 元件+实体摆放：写入 `元件库/` 与 `实体摆放/`（并生成 index.json）。\n"
                "- 玩家模板：提取自定义变量并生成变量文件 + 玩家模板 JSON 骨架。\n"
                "- 节点图：解析 `.gia` 内的 NodeGraph，生成 `节点图/server|client/*.py`（Graph Code）。"
            )
            self.add_form_field("导入类型：", self.import_kind_combo, field_name="import_kind")

            # 导入目标模式
            self.target_mode_combo = QtWidgets.QComboBox(self)
            self.target_mode_combo.addItem("导入到已有项目存档（推荐）", "existing")
            self.target_mode_combo.addItem("新建项目存档", "new")
            if not importable_package_ids:
                # 没有任何可选的“已有项目存档”时，默认切换到“新建”，避免用户误以为可直接导入。
                idx = self.target_mode_combo.findData("new")
                if idx >= 0:
                    self.target_mode_combo.setCurrentIndex(int(idx))
            self.add_form_field("导入目标：", self.target_mode_combo, field_name="target_mode")

            # 项目存档名（new）
            self.package_name_edit = QtWidgets.QLineEdit(self)
            self.package_name_edit.setPlaceholderText("仅新建模式使用；默认使用文件名，可自行修改")
            self.add_form_field("项目存档名：", self.package_name_edit, field_name="package_name")

            # 选择已有项目存档（existing）
            self.existing_package_combo = QtWidgets.QComboBox(self)
            self.existing_package_combo.setEditable(False)
            for package_id in importable_package_ids:
                self.existing_package_combo.addItem(str(package_id))
            if default_existing_package_id:
                idx2 = self.existing_package_combo.findText(str(default_existing_package_id))
                if idx2 >= 0:
                    self.existing_package_combo.setCurrentIndex(int(idx2))
            self.add_form_field("目标存档：", self.existing_package_combo, field_name="existing_package")

            self.overwrite_warning_label = QtWidgets.QLabel("", self)
            self.overwrite_warning_label.setWordWrap(True)
            self.overwrite_warning_label.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
            )
            self.add_widget(self.overwrite_warning_label)

            # 选项
            options_box = QtWidgets.QGroupBox("选项", self)
            options_layout = QtWidgets.QVBoxLayout(options_box)
            options_layout.setContentsMargins(
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
                Sizes.PADDING_MEDIUM,
            )
            options_layout.setSpacing(Sizes.SPACING_SMALL)

            self.overwrite_checkbox = QtWidgets.QCheckBox(
                "允许覆盖已存在的输出（谨慎）",
                options_box,
            )
            self.overwrite_checkbox.setChecked(False)
            self.overwrite_checkbox.setToolTip(
                "开启后：\n"
                "- 元件+实体摆放：允许覆盖同 template_id/instance_id 的 JSON 文件。\n"
                "- 玩家模板：允许覆盖输出的变量文件与玩家模板 JSON。\n"
                "- 节点图：允许覆盖输出的 Graph Code 文件。"
            )
            options_layout.addWidget(self.overwrite_checkbox)

            self.templates_cb = QtWidgets.QCheckBox("导入元件（元件库）", options_box)
            self.templates_cb.setChecked(True)
            self.templates_cb.setToolTip("关闭则仅导入实体摆放（要求目标项目存档已存在被引用元件）。")
            options_layout.addWidget(self.templates_cb)

            self.instances_cb = QtWidgets.QCheckBox("导入实体摆放（instances）", options_box)
            self.instances_cb.setChecked(True)
            self.instances_cb.setToolTip("关闭则仅导入元件（不导入装饰物/摆放）。")
            options_layout.addWidget(self.instances_cb)

            instances_mode_row = QtWidgets.QWidget(options_box)
            instances_mode_layout = QtWidgets.QHBoxLayout(instances_mode_row)
            instances_mode_layout.setContentsMargins(0, 0, 0, 0)
            instances_mode_layout.setSpacing(Sizes.SPACING_SMALL)
            instances_mode_label = QtWidgets.QLabel("装饰物导入模式：", instances_mode_row)
            self.instances_mode_combo = QtWidgets.QComboBox(instances_mode_row)
            self.instances_mode_combo.addItem("写入对应元件（以元件为主，按引用归类）", "decorations_to_template")
            self.instances_mode_combo.addItem("合并为装饰物（1 个载体实体）", "decorations_carrier")
            self.instances_mode_combo.addItem("生成独立实体摆放（旧行为，可能产生大量文件）", "instances")
            self.instances_mode_combo.setToolTip(
                "说明：\n"
                "- 写入对应元件：将 `.gia` 的 Root.field_2 按被引用 template_id 分组，并写入到对应元件模板的 "
                "`metadata.common_inspector.model.decorations`（以元件为主；不生成实体摆放文件；需要同时导入元件）。\n"
                "- 合并模式会将 `.gia` 的 Root.field_2 写入到一个载体实体的 "
                "`metadata.common_inspector.model.decorations`，避免创建成千上万个实体摆放文件。\n"
                "- 独立模式会为每个 unit 生成一个实体摆放 JSON（更接近旧行为）。"
            )
            instances_mode_layout.addWidget(instances_mode_label)
            instances_mode_layout.addWidget(self.instances_mode_combo, 1)
            options_layout.addWidget(instances_mode_row)

            depth_row = QtWidgets.QWidget(options_box)
            depth_layout = QtWidgets.QHBoxLayout(depth_row)
            depth_layout.setContentsMargins(0, 0, 0, 0)
            depth_layout.setSpacing(Sizes.SPACING_SMALL)
            depth_label = QtWidgets.QLabel("解码深度上限：", depth_row)
            self.decode_depth_spin = QtWidgets.QSpinBox(depth_row)
            self.decode_depth_spin.setRange(8, 200)
            self.decode_depth_spin.setValue(28)
            self.decode_depth_spin.setToolTip("protobuf-like 递归解码深度上限（默认 28）。")
            depth_layout.addWidget(depth_label)
            depth_layout.addWidget(self.decode_depth_spin)
            depth_layout.addStretch(1)
            options_layout.addWidget(depth_row)

            self.validate_after_import_cb = QtWidgets.QCheckBox("导入后校验项目存档（推荐）", options_box)
            self.validate_after_import_cb.setChecked(True)
            self.validate_after_import_cb.setToolTip(
                "开启后会执行一次综合校验（ComprehensiveValidator），用于确认导入的节点图可被索引与解析。\n"
                "如果你只是想快速落盘查看，可以先关闭。"
            )
            options_layout.addWidget(self.validate_after_import_cb)

            self.player_template_hint = QtWidgets.QLabel(
                "提示：玩家模板导入会生成：\n"
                "- `管理配置/关卡变量/自定义变量/导入_玩家模板变量__*.py`\n"
                "- `战斗预设/玩家模板/*.json`",
                options_box,
            )
            self.player_template_hint.setWordWrap(True)
            self.player_template_hint.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
            )
            options_layout.addWidget(self.player_template_hint)

            self.node_graphs_hint = QtWidgets.QLabel(
                "提示：节点图导入会生成：\n"
                "- `节点图/server/*.py` 或 `节点图/client/*.py`（按 graph_id 高位自动推断 scope）",
                options_box,
            )
            self.node_graphs_hint.setWordWrap(True)
            self.node_graphs_hint.setStyleSheet(
                f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;"
            )
            options_layout.addWidget(self.node_graphs_hint)

            self.add_widget(options_box)

            # 目标目录预览
            self.preview_label = QtWidgets.QLabel("", self)
            self.preview_label.setWordWrap(True)
            self.preview_label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: 10px;")
            self.add_widget(self.preview_label)

            # 行为联动
            self.input_path_edit.textChanged.connect(self._on_input_path_text_changed)
            self.package_name_edit.textChanged.connect(self._update_preview)
            self.existing_package_combo.currentIndexChanged.connect(self._update_preview)
            self.import_kind_combo.currentIndexChanged.connect(self._on_import_kind_changed)
            self.target_mode_combo.currentIndexChanged.connect(self._on_target_mode_changed)
            self.templates_cb.toggled.connect(self._update_preview)
            self.instances_cb.toggled.connect(self._update_preview)
            self.instances_cb.toggled.connect(self._update_instances_mode_visibility)
            self.instances_mode_combo.currentIndexChanged.connect(self._update_preview)
            self.decode_depth_spin.valueChanged.connect(self._update_preview)
            self.validate_after_import_cb.toggled.connect(self._update_preview)

            self._on_target_mode_changed()
            self._on_import_kind_changed()
            self._update_instances_mode_visibility()
            self._update_preview()

        def _get_target_mode(self) -> str:
            return str(self.target_mode_combo.currentData() or "existing")

        def _get_import_kind(self) -> str:
            return str(self.import_kind_combo.currentData() or "templates_instances")

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
                        "注意：导入到已有项目存档时，会新增/覆盖资源文件（不可撤销）。\n"
                        "建议先备份目标项目存档目录。"
                    )
            else:
                self.overwrite_warning_label.setText("")
            self._update_preview()

        def _on_import_kind_changed(self) -> None:
            kind = self._get_import_kind()
            is_bundle = kind == "templates_instances"
            is_node_graphs = kind == "node_graphs"
            self.templates_cb.setVisible(bool(is_bundle))
            self.instances_cb.setVisible(bool(is_bundle))
            self._update_instances_mode_visibility()
            self.decode_depth_spin.parentWidget().setVisible(bool(is_bundle or is_node_graphs))
            self.validate_after_import_cb.setVisible(bool(is_node_graphs))
            self.player_template_hint.setVisible(kind == "player_template")
            self.node_graphs_hint.setVisible(bool(is_node_graphs))
            self._update_preview()

        def _update_instances_mode_visibility(self) -> None:
            kind = self._get_import_kind()
            visible = bool(kind == "templates_instances" and self.instances_cb.isChecked())
            self.instances_mode_combo.parentWidget().setVisible(bool(visible))
            self.instances_mode_combo.setEnabled(bool(visible))

        def _choose_input_file(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "选择 .gia 文件",
                "",
                "GIA (*.gia);;所有文件 (*)",
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
            kind = self._get_import_kind()
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
            details.append(
                "类型：元件+实体摆放（写入 元件库/ + 实体摆放/）"
                if kind == "templates_instances"
                else (
                    "类型：玩家模板（写入 战斗预设/玩家模板/ + 自定义变量/）"
                    if kind == "player_template"
                    else "类型：节点图（写入 节点图/server|client/）"
                )
            )
            if mode == "existing":
                if target_path is None:
                    details.append("输出：<未选择目标项目存档>")
                else:
                    details.append(f"输出：{str(target_path)}")
            else:
                details.append(f"输出：{str(target_path)}")
                if final_id != sanitized:
                    details.append(f"提示：目录名将自动使用：{final_id}")

            if kind == "templates_instances":
                selected_parts: list[str] = []
                if self.templates_cb.isChecked():
                    selected_parts.append("元件库")
                if self.instances_cb.isChecked():
                    selected_parts.append("装饰物/摆放")
                if selected_parts:
                    details.append(f"导入范围：{' + '.join(selected_parts)}")
                else:
                    details.append("导入范围：<未选择任何范围>")
                if self.instances_cb.isChecked():
                    mode2 = str(self.instances_mode_combo.currentData() or "decorations_to_template")
                    if mode2 == "decorations_to_template":
                        details.append("装饰物模式：写入对应元件（decorations_to_template）")
                    elif mode2 == "decorations_carrier":
                        details.append("装饰物模式：合并为 1 个载体实体（decorations_carrier）")
                    else:
                        details.append("装饰物模式：生成独立实体摆放（instances，可能产生大量文件）")
            elif kind == "node_graphs":
                details.append(
                    "导入范围：节点图（将按 graph_id 自动分配到 server/client；默认会生成 Graph Code）"
                )
                if self.validate_after_import_cb.isChecked():
                    details.append("导入后校验：开启")
                else:
                    details.append("导入后校验：关闭")

            if self.overwrite_checkbox.isChecked():
                details.append("注意：已开启覆盖写入（谨慎）。")

            self.preview_label.setText("\n".join(details))

        def validate(self) -> bool:
            input_text = str(self.input_path_edit.text() or "").strip()
            if input_text == "":
                self.show_error("请先选择一个 .gia 文件。")
                return False

            input_path = Path(input_text).resolve()
            if not input_path.is_file():
                self.show_error(f"文件不存在：{str(input_path)}")
                return False

            if input_path.suffix.lower() != ".gia":
                self.show_error("输入文件不是 .gia。")
                return False

            kind = self._get_import_kind()
            if kind not in {"templates_instances", "player_template", "node_graphs"}:
                self.show_error("导入类型无效。")
                return False

            mode = self._get_target_mode()
            if mode not in {"existing", "new"}:
                self.show_error("导入目标模式无效。")
                return False

            if kind == "templates_instances":
                if not self.templates_cb.isChecked() and not self.instances_cb.isChecked():
                    self.show_error("请至少勾选一个导入范围（元件库/实体摆放）。")
                    return False
                if self.instances_cb.isChecked():
                    mode2 = str(self.instances_mode_combo.currentData() or "decorations_to_template").strip()
                    if mode2 == "decorations_to_template" and not self.templates_cb.isChecked():
                        self.show_error("“写入对应元件”模式需要同时导入元件（请勾选“导入元件（元件库）”）。")
                        return False

            overwrite_existing = bool(self.overwrite_checkbox.isChecked())

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
            else:
                final_package_id = self._compute_final_package_id()
                output_package_root = (packages_root / final_package_id).resolve()
                if output_package_root.exists():
                    self.show_error(f"目标目录已存在，请修改项目存档名：{str(output_package_root)}")
                    return False

            decode_max_depth = int(self.decode_depth_spin.value())
            instances_mode = str(self.instances_mode_combo.currentData() or "decorations_to_template")

            self._plan = _ReadGiaPlan(
                input_gia_path=input_path,
                import_kind=str(kind),
                package_id=str(final_package_id),
                output_package_root=output_package_root,
                overwrite_existing=bool(overwrite_existing),
                import_templates=bool(self.templates_cb.isChecked()),
                import_instances=bool(self.instances_cb.isChecked()),
                instances_mode=str(instances_mode),
                decode_max_depth=int(decode_max_depth),
                validate_after_import=bool(self.validate_after_import_cb.isChecked()),
            )
            return True

        def get_plan(self) -> _ReadGiaPlan | None:
            return self._plan

    dialog = _ReadGiaDialog(main_window)
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return

    plan = dialog.get_plan()
    if plan is None:
        return

    package_library_widget = getattr(main_window, "package_library_widget", None)
    if package_library_widget is None:
        raise RuntimeError("主窗口缺少 package_library_widget，无法显示导入进度")

    ensure_widget = getattr(package_library_widget, "ensure_extension_toolbar_widget", None)
    if not callable(ensure_widget):
        raise RuntimeError("PackageLibraryWidget 缺少 ensure_extension_toolbar_widget，无法显示导入进度")

    ProgressWidgetCls = make_toolbar_progress_widget_cls(
        ToolbarProgressWidgetSpec(kind="read_gia", initial_label="准备导入…", progress_width=180),
        QtCore=QtCore,
        QtWidgets=QtWidgets,
        Colors=Colors,
        Sizes=Sizes,
    )

    def _get_progress_widget(*, visible: bool) -> QtWidgets.QWidget:
        widget_obj = ensure_widget(
            "ugc_file_tools.read_gia_progress",
            create_widget=lambda parent: ProgressWidgetCls(parent),
            visible=visible,
        )
        if not isinstance(widget_obj, ProgressWidgetCls):
            raise TypeError(f"gia progress widget 类型不匹配（got: {type(widget_obj).__name__}）")
        return widget_obj

    class _ReadGiaWorker(QtCore.QThread):
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label
        succeeded = QtCore.pyqtSignal(str, object)  # package_id, report(dict)

        def __init__(self, *, plan: _ReadGiaPlan, parent: QtCore.QObject | None = None) -> None:
            super().__init__(parent)
            self._plan = plan
            self.setObjectName(f"ReadGiaWorker:{self._plan.package_id}")

        def run(self) -> None:
            total_steps = 3
            self.progress_changed.emit(0, total_steps, "准备导入 .gia…")

            output_root = Path(self._plan.output_package_root).resolve()
            if not output_root.exists():
                output_root.mkdir(parents=True, exist_ok=True)

            kind = str(self._plan.import_kind or "").strip()
            self.progress_changed.emit(1, total_steps, "正在导入 .gia → 项目存档…")

            if kind == "templates_instances":
                from ugc_file_tools.pipelines.gia_templates_and_instances_to_project_archive import (
                    ImportGiaTemplatesAndInstancesPlan,
                    run_import_gia_templates_and_instances_to_project_archive,
                )

                report = run_import_gia_templates_and_instances_to_project_archive(
                    plan=ImportGiaTemplatesAndInstancesPlan(
                        input_gia_file=Path(self._plan.input_gia_path),
                        project_archive_path=Path(output_root),
                        overwrite=bool(self._plan.overwrite_existing),
                        decode_max_depth=int(self._plan.decode_max_depth),
                        skip_templates=not bool(self._plan.import_templates),
                        skip_instances=not bool(self._plan.import_instances),
                        instances_mode=str(self._plan.instances_mode or "decorations_carrier"),
                    )
                )
            elif kind == "player_template":
                from ugc_file_tools.pipelines.player_template_gia_to_project_archive import (
                    ImportPlayerTemplateGiaPlan,
                    run_import_player_template_gia_to_project_archive,
                )

                report = run_import_player_template_gia_to_project_archive(
                    plan=ImportPlayerTemplateGiaPlan(
                        input_gia_file=Path(self._plan.input_gia_path),
                        project_archive_path=Path(output_root),
                        overwrite=bool(self._plan.overwrite_existing),
                        output_variable_file_id="",
                        output_variable_file_name="",
                        output_template_id="",
                    )
                )
            elif kind == "node_graphs":
                from ugc_file_tools.pipelines.gia_node_graphs_to_project_archive import (
                    ImportGiaNodeGraphsPlan,
                    run_import_gia_node_graphs_to_project_archive,
                )

                report = run_import_gia_node_graphs_to_project_archive(
                    plan=ImportGiaNodeGraphsPlan(
                        input_gia_file=Path(self._plan.input_gia_path),
                        project_archive_path=Path(output_root),
                        package_id=str(self._plan.package_id),
                        overwrite_graph_code=bool(self._plan.overwrite_existing),
                        check_header=False,
                        decode_max_depth=int(self._plan.decode_max_depth),
                        validate_after_import=bool(self._plan.validate_after_import),
                        set_last_opened=False,
                    )
                )
            else:
                raise ValueError(f"未知的 import_kind：{kind!r}")

            self.progress_changed.emit(2, total_steps, "正在补齐项目存档目录骨架…")
            ensure_structure(str(self._plan.package_id))

            self.progress_changed.emit(3, total_steps, "完成")
            self.succeeded.emit(str(self._plan.package_id), report)

    worker = _ReadGiaWorker(plan=plan, parent=main_window)
    setattr(main_window, "_read_gia_worker", worker)

    state = {"succeeded": False}

    def _on_progress(current: int, total: int, label: str) -> None:
        progress_widget = _get_progress_widget(visible=True)
        progress_widget.set_status(label=str(label), current=int(current), total=int(total))

    def _format_result_message(*, package_id: str, report: dict) -> str:
        kind = str(plan.import_kind or "").strip()
        lines: list[str] = [f"项目存档：{str(package_id)}", f"输入：{str(plan.input_gia_path)}"]
        if kind == "templates_instances":
            lines.append(f"导入元件：{int(report.get('imported_templates_count', 0) or 0)} 个")
            mode2 = str(report.get("instances_mode") or "").strip()
            if mode2 == "decorations_carrier":
                deco_count = int(report.get("imported_decorations_count", 0) or 0)
                carrier_count = int(report.get("imported_instances_count", 0) or 0)
                carrier_id = str(report.get("decorations_carrier_instance_id") or "").strip()
                lines.append(f"导入装饰物：{deco_count} 个（合并为 {carrier_count} 个载体实体）")
                if carrier_id:
                    lines.append(f"载体实体ID：{carrier_id}")
            elif mode2 == "decorations_to_template":
                deco_count = int(report.get("imported_decorations_count", 0) or 0)
                tpl_count = int(report.get("decorations_to_template_target_templates_count", 0) or 0)
                lines.append("导入实体摆放：0 个（装饰物已写入元件模板）")
                lines.append(f"导入装饰物：{deco_count} 个（写入 {tpl_count} 个元件）")
            else:
                lines.append(f"导入实体摆放：{int(report.get('imported_instances_count', 0) or 0)} 个")
            skipped1 = report.get("skipped_instance_unit_ids_missing_template_ref")
            skipped2 = report.get("skipped_instance_unit_ids_missing_transform")
            if isinstance(skipped1, list) and skipped1:
                lines.append(f"跳过（缺元件引用）：{len(skipped1)} 个 unit")
            if isinstance(skipped2, list) and skipped2:
                lines.append(f"跳过（缺 transform）：{len(skipped2)} 个 unit")
        elif kind == "player_template":
            lines.append(f"模板名：{str(report.get('template_name') or '')}")
            lines.append(f"导入变量：{int(report.get('custom_variables_count', 0) or 0)} 个")
            lines.append(f"输出玩家模板：{str(report.get('output_player_template_json') or '')}")
            lines.append(f"输出变量文件：{str(report.get('output_variable_file') or '')}")
        elif kind == "node_graphs":
            lines.append(f"图数量：{int(report.get('graphs_count', 0) or 0)}")
            written = report.get("written_graph_code_files")
            skipped = report.get("skipped_graph_code_files")
            if isinstance(written, list):
                lines.append(f"写入 Graph Code：{len(written)} 个")
            if isinstance(skipped, list) and skipped:
                lines.append(f"跳过（已存在且未覆盖）：{len(skipped)} 个")
            validation_summary = report.get("validation_summary")
            if isinstance(validation_summary, dict):
                lines.append(
                    f"校验：errors={int(validation_summary.get('errors', 0) or 0)}, "
                    f"warnings={int(validation_summary.get('warnings', 0) or 0)}"
                )
        return "\n".join([line for line in lines if str(line).strip()])

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
        dialog_utils.show_info_dialog(
            main_window,
            "导入完成",
            _format_result_message(package_id=str(package_id), report=report),
        )

        append_task_history_entry(
            workspace_root=Path(workspace_root),
            entry={
                "ts": now_ts(),
                "kind": "read_gia",
                "title": f"导入GIA → 项目存档（{package_id}）",
                "package_id": str(package_id),
                "import_kind": str(plan.import_kind),
                "input_gia": str(plan.input_gia_path),
                "overwrite_existing": bool(plan.overwrite_existing),
                "import_templates": bool(plan.import_templates),
                "import_instances": bool(plan.import_instances),
                "instances_mode": str(plan.instances_mode),
                "decode_max_depth": int(plan.decode_max_depth),
                "validate_after_import": bool(plan.validate_after_import),
                "report": report,
            },
        )

    def _on_worker_finished() -> None:
        setattr(main_window, "_read_gia_worker", None)
        if state["succeeded"]:
            return
        _get_progress_widget(visible=False).set_status(label="失败", current=0, total=0)
        dialog_utils.show_warning_dialog(main_window, "导入失败", "导入失败（请查看控制台错误）。")

    worker.progress_changed.connect(_on_progress)
    worker.succeeded.connect(_on_succeeded)
    worker.finished.connect(worker.deleteLater)
    worker.finished.connect(_on_worker_finished)
    _get_progress_widget(visible=True).set_status(label="准备开始…", current=0, total=0)
    worker.start()

