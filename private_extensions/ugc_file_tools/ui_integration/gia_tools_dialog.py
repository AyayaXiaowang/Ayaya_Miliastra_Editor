from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence


def _is_running_worker(worker: object | None) -> bool:
    if worker is None:
        return False
    is_running = getattr(worker, "isRunning", None)
    return bool(callable(is_running) and bool(is_running()))


def _make_cli_tool_worker_cls(*, QtCore: Any):
    class _Worker(QtCore.QThread):  # type: ignore[misc]
        progress_changed = QtCore.pyqtSignal(int, int, str)  # current, total, label
        log_line = QtCore.pyqtSignal(str)  # stderr line
        succeeded = QtCore.pyqtSignal(dict)  # report
        failed = QtCore.pyqtSignal(str)  # message

        def __init__(
            self,
            *,
            workspace_root: Path,
            argv: Sequence[str],
            report_file: Path,
            parent: object | None = None,
        ) -> None:
            super().__init__(parent)
            self._workspace_root = Path(workspace_root).resolve()
            self._argv = [str(x) for x in list(argv)]
            self._report_file = Path(report_file).resolve()
            self.setObjectName(f"GiaToolsWorker:{self._report_file.name}")

        def run(self) -> None:
            import json

            from ._cli_subprocess import build_run_ugc_file_tools_command, run_cli_with_progress

            command = build_run_ugc_file_tools_command(workspace_root=Path(self._workspace_root), argv=self._argv)
            result = run_cli_with_progress(
                command=command,
                cwd=Path(self._workspace_root),
                on_progress=lambda current, total, label: self.progress_changed.emit(int(current), int(total), str(label)),
                on_log_line=lambda line: self.log_line.emit(str(line)),
                stderr_tail_max_lines=240,
            )
            if int(result.exit_code) != 0:
                tail = [str(x) for x in list(result.stderr_tail)[-80:] if str(x).strip() != ""]
                tail_text = "\n".join(tail) if tail else "(stderr 为空)"
                self.failed.emit(f"执行失败：退出码={int(result.exit_code)}\n\n{tail_text}")
                return

            if not self._report_file.is_file():
                raise FileNotFoundError(str(self._report_file))
            report_obj = json.loads(self._report_file.read_text(encoding="utf-8"))
            if not isinstance(report_obj, dict):
                raise TypeError("tool report must be dict")
            self.succeeded.emit(dict(report_obj))

    return _Worker


@dataclass(frozen=True, slots=True)
class _RunBox:
    run_btn: Any
    status_label: Any
    log_text: Any
    result_text: Any


def _build_run_box(*, QtWidgets: Any, ThemeManager: Any, Sizes: Any, parent: Any) -> tuple[Any, _RunBox]:
    box = QtWidgets.QGroupBox("执行", parent)
    box.setStyleSheet(ThemeManager.group_box_style())
    layout = QtWidgets.QVBoxLayout(box)
    layout.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    layout.setSpacing(Sizes.SPACING_SMALL)

    run_row = QtWidgets.QWidget(box)
    run_layout = QtWidgets.QHBoxLayout(run_row)
    run_layout.setContentsMargins(0, 0, 0, 0)
    run_layout.setSpacing(Sizes.SPACING_MEDIUM)

    run_btn = QtWidgets.QPushButton("执行", run_row)
    run_btn.setMinimumWidth(110)
    status_label = QtWidgets.QLabel("", run_row)
    status_label.setWordWrap(True)
    status_label.setStyleSheet(ThemeManager.subtle_info_style())

    run_layout.addWidget(run_btn)
    run_layout.addWidget(status_label, 1)
    layout.addWidget(run_row)

    result_text = QtWidgets.QPlainTextEdit(box)
    result_text.setReadOnly(True)
    result_text.setPlaceholderText("执行结果会显示在这里。")
    result_text.setMaximumHeight(150)
    layout.addWidget(result_text)

    log_text = QtWidgets.QPlainTextEdit(box)
    log_text.setReadOnly(True)
    log_text.setPlaceholderText("stderr tail / 日志（仅用于排错）。")
    log_text.setMaximumHeight(220)
    layout.addWidget(log_text)

    return box, _RunBox(run_btn=run_btn, status_label=status_label, log_text=log_text, result_text=result_text)


def open_gia_tools_dialog(*, main_window: object, workspace_root: Path) -> None:
    from uuid import uuid4

    from PyQt6 import QtCore, QtWidgets

    from app.ui.foundation import dialog_utils
    from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager

    if not isinstance(main_window, QtWidgets.QMainWindow):
        raise TypeError(f"main_window 必须是 QMainWindow（got: {type(main_window).__name__}）")

    workspace_root = Path(workspace_root).resolve()
    out_dir = (workspace_root / "private_extensions" / "ugc_file_tools" / "out").resolve()
    tmp_dir = (out_dir / "_tmp_cli").resolve()

    dialog_attr = "_ugc_file_tools_gia_tools_dialog"
    existing_dialog = getattr(main_window, dialog_attr, None)
    if isinstance(existing_dialog, QtWidgets.QDialog):
        existing_dialog.show()
        existing_dialog.raise_()
        existing_dialog.activateWindow()
        return

    dialog = QtWidgets.QDialog(main_window)
    dialog.setObjectName("ugc_file_tools_gia_tools_dialog")
    dialog.setWindowTitle("GIA 文件工具")
    dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.setWindowModality(QtCore.Qt.WindowModality.NonModal)
    dialog.setModal(False)
    dialog.setSizeGripEnabled(True)
    dialog.resize(980, 760)

    setattr(main_window, dialog_attr, dialog)
    dialog.destroyed.connect(lambda *_: setattr(main_window, dialog_attr, None))

    dialog.setStyleSheet(f"""
        QDialog {{
            background-color: {Colors.BG_MAIN};
        }}
        QLabel {{
            color: {Colors.TEXT_PRIMARY};
        }}
    """)

    root_layout = QtWidgets.QVBoxLayout(dialog)
    root_layout.setContentsMargins(Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE, Sizes.PADDING_LARGE)
    root_layout.setSpacing(Sizes.SPACING_MEDIUM)

    title = QtWidgets.QLabel("GIA 文件工具", dialog)
    title.setStyleSheet(ThemeManager.heading(level=2))
    root_layout.addWidget(title)

    intro = QtWidgets.QLabel(
        "说明：这些工具用于对已有 `.gia` 文件做 wire-level 变换。\n"
        "- 输出文件会强制落盘到 `private_extensions/ugc_file_tools/out/`（可在 out 内建子目录）。\n"
        "- 执行通过子进程运行 `ugc_file_tools tool --dangerous ...`，不会阻塞主 UI；失败会直接抛错/报错，不做吞错。",
        dialog,
    )
    intro.setWordWrap(True)
    intro.setStyleSheet(ThemeManager.subtle_info_style())
    root_layout.addWidget(intro)

    out_hint = QtWidgets.QLabel(f"out 目录：{str(out_dir)}", dialog)
    out_hint.setStyleSheet(ThemeManager.subtle_info_style())
    out_hint.setWordWrap(True)
    root_layout.addWidget(out_hint)

    tabs = QtWidgets.QTabWidget(dialog)
    tabs.setDocumentMode(True)
    tabs.setMovable(False)
    tabs.setTabsClosable(False)
    root_layout.addWidget(tabs, 1)

    WorkerCls = _make_cli_tool_worker_cls(QtCore=QtCore)

    # ======================
    # Tab 1: merge/center decorations
    # ======================
    tab1 = QtWidgets.QWidget(tabs)
    tab1_layout = QtWidgets.QVBoxLayout(tab1)
    tab1_layout.setContentsMargins(0, 0, 0, 0)
    tab1_layout.setSpacing(Sizes.SPACING_MEDIUM)

    deco_box = QtWidgets.QGroupBox("装饰物(accessories)合并/居中", tab1)
    deco_box.setStyleSheet(ThemeManager.group_box_style())
    deco_form = QtWidgets.QFormLayout(deco_box)
    deco_form.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    deco_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    deco_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    deco_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

    deco_input_row = QtWidgets.QWidget(deco_box)
    deco_input_layout = QtWidgets.QHBoxLayout(deco_input_row)
    deco_input_layout.setContentsMargins(0, 0, 0, 0)
    deco_input_layout.setSpacing(Sizes.SPACING_SMALL)
    deco_input_edit = QtWidgets.QLineEdit(deco_input_row)
    deco_input_edit.setPlaceholderText("选择输入 .gia 文件（空物体+多装饰物 accessories）…")
    deco_input_browse = QtWidgets.QPushButton("浏览…", deco_input_row)
    deco_input_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    deco_input_browse.clicked.connect(
        lambda: (
            (lambda p: deco_input_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(tab1, "选择输入 .gia", "", "GIA (*.gia)")[0]
            )
        )
    )
    deco_input_layout.addWidget(deco_input_edit, 1)
    deco_input_layout.addWidget(deco_input_browse)
    deco_form.addRow("输入 .gia:", deco_input_row)

    deco_output_edit = QtWidgets.QLineEdit(deco_box)
    deco_output_edit.setPlaceholderText("输出文件名（强制落盘到 out/；支持 out 内子目录）")
    deco_output_edit.setText("decorations_centered.gia")
    deco_form.addRow("输出到 out/:", deco_output_edit)

    deco_check_header_cb = QtWidgets.QCheckBox("严格校验 .gia 容器头/尾（失败直接报错）", deco_box)
    deco_form.addRow("", deco_check_header_cb)

    deco_do_center_cb = QtWidgets.QCheckBox("启用居中", deco_box)
    deco_do_center_cb.setChecked(True)
    deco_form.addRow("", deco_do_center_cb)

    deco_center_policy_combo = QtWidgets.QComboBox(deco_box)
    deco_center_policy_combo.addItem("keep_world（推荐：移动 parent 并补偿 local，世界坐标不变）", "keep_world")
    deco_center_policy_combo.addItem("move_decorations（直接移动装饰物，世界坐标会变）", "move_decorations")
    deco_form.addRow("居中策略:", deco_center_policy_combo)

    deco_center_mode_combo = QtWidgets.QComboBox(deco_box)
    deco_center_mode_combo.addItem("bbox（包围盒中心）", "bbox")
    deco_center_mode_combo.addItem("mean（均值中心）", "mean")
    deco_form.addRow("中心点:", deco_center_mode_combo)

    deco_center_axes_combo = QtWidgets.QComboBox(deco_box)
    for k in ["x", "y", "z", "xy", "xz", "yz", "xyz"]:
        deco_center_axes_combo.addItem(k, k)
    deco_center_axes_combo.setCurrentIndex(int(deco_center_axes_combo.findData("xyz")))
    deco_form.addRow("居中轴:", deco_center_axes_combo)

    deco_do_merge_cb = QtWidgets.QCheckBox("启用合并（多 parent → 统一挂到一个 parent）", deco_box)
    deco_do_merge_cb.setChecked(True)
    deco_form.addRow("", deco_do_merge_cb)

    deco_target_parent_id = QtWidgets.QLineEdit(deco_box)
    deco_target_parent_id.setPlaceholderText("可选：合并目标 parent 的 unit_id（整数；优先级高于 name）")
    deco_form.addRow("目标 parent_id:", deco_target_parent_id)

    deco_target_parent_name = QtWidgets.QLineEdit(deco_box)
    deco_target_parent_name.setPlaceholderText("可选：合并目标 parent 的 GraphUnit.name（需唯一匹配）")
    deco_form.addRow("目标 parent_name:", deco_target_parent_name)

    deco_drop_other_cb = QtWidgets.QCheckBox("合并后删除其它 parent（默认仅清空 relatedIds）", deco_box)
    deco_form.addRow("", deco_drop_other_cb)

    deco_keep_file_path_cb = QtWidgets.QCheckBox("保持 Root.filePath 不变", deco_box)
    deco_form.addRow("", deco_keep_file_path_cb)

    deco_file_path_override = QtWidgets.QLineEdit(deco_box)
    deco_file_path_override.setPlaceholderText(r"可选：覆盖 Root.filePath（优先级高于保持不变）")
    deco_form.addRow("filePath 覆盖:", deco_file_path_override)

    deco_copy_to = QtWidgets.QLineEdit(deco_box)
    deco_copy_to.setPlaceholderText("可选：额外复制到指定目录（默认仍会复制到 Beyond_Local_Export）")
    deco_form.addRow("额外复制到:", deco_copy_to)

    tab1_layout.addWidget(deco_box)

    run_box1_widget, run_box1 = _build_run_box(QtWidgets=QtWidgets, ThemeManager=ThemeManager, Sizes=Sizes, parent=tab1)
    tab1_layout.addWidget(run_box1_widget)
    tab1_layout.addStretch(1)
    tabs.addTab(tab1, "装饰物合并/居中")

    # ======================
    # Tab 2: convert component/entity bundle
    # ======================
    tab2 = QtWidgets.QWidget(tabs)
    tab2_layout = QtWidgets.QVBoxLayout(tab2)
    tab2_layout.setContentsMargins(0, 0, 0, 0)
    tab2_layout.setSpacing(Sizes.SPACING_MEDIUM)

    conv_box = QtWidgets.QGroupBox("元件 ↔ 实体摆放（bundle.gia）转换", tab2)
    conv_box.setStyleSheet(ThemeManager.group_box_style())
    conv_form = QtWidgets.QFormLayout(conv_box)
    conv_form.setContentsMargins(
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM + 10,
        Sizes.PADDING_MEDIUM,
        Sizes.PADDING_MEDIUM,
    )
    conv_form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
    conv_form.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
    conv_form.setVerticalSpacing(Sizes.SPACING_MEDIUM)

    conv_input_row = QtWidgets.QWidget(conv_box)
    conv_input_layout = QtWidgets.QHBoxLayout(conv_input_row)
    conv_input_layout.setContentsMargins(0, 0, 0, 0)
    conv_input_layout.setSpacing(Sizes.SPACING_SMALL)
    conv_input_edit = QtWidgets.QLineEdit(conv_input_row)
    conv_input_edit.setPlaceholderText("选择输入 bundle.gia（元件+实体摆放）…")
    conv_input_browse = QtWidgets.QPushButton("浏览…", conv_input_row)
    conv_input_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    conv_input_browse.clicked.connect(
        lambda: (
            (lambda p: conv_input_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(tab2, "选择输入 bundle.gia", "", "GIA (*.gia)")[0]
            )
        )
    )
    conv_input_layout.addWidget(conv_input_edit, 1)
    conv_input_layout.addWidget(conv_input_browse)
    conv_form.addRow("输入 bundle.gia:", conv_input_row)

    conv_output_edit = QtWidgets.QLineEdit(conv_box)
    conv_output_edit.setPlaceholderText("输出文件名（强制落盘到 out/；支持 out 内子目录）")
    conv_output_edit.setText("converted_bundle.gia")
    conv_form.addRow("输出到 out/:", conv_output_edit)

    conv_check_header_cb = QtWidgets.QCheckBox("严格校验 .gia 容器头/尾（失败直接报错）", conv_box)
    conv_form.addRow("", conv_check_header_cb)

    conv_mode_combo = QtWidgets.QComboBox(conv_box)
    conv_mode_combo.addItem("元件 → 实体（component_to_entity）", "component_to_entity")
    conv_mode_combo.addItem("实体 → 元件（entity_to_component）", "entity_to_component")
    conv_form.addRow("转换方向:", conv_mode_combo)

    conv_keep_unref_tpl_cb = QtWidgets.QCheckBox("实体→元件：保留未被实例引用的元件（默认裁剪闭包）", conv_box)
    conv_form.addRow("", conv_keep_unref_tpl_cb)

    conv_tpl_contains = QtWidgets.QLineEdit(conv_box)
    conv_tpl_contains.setPlaceholderText("元件→实体：仅为 name 包含该子串的元件生成实例（默认空=全量）")
    conv_form.addRow("元件名筛选:", conv_tpl_contains)

    conv_drop_existing_inst_cb = QtWidgets.QCheckBox("元件→实体：丢弃输入中已有的 instances（只输出新生成实例）", conv_box)
    conv_form.addRow("", conv_drop_existing_inst_cb)

    conv_inst_tpl_row = QtWidgets.QWidget(conv_box)
    conv_inst_tpl_layout = QtWidgets.QHBoxLayout(conv_inst_tpl_row)
    conv_inst_tpl_layout.setContentsMargins(0, 0, 0, 0)
    conv_inst_tpl_layout.setSpacing(Sizes.SPACING_SMALL)
    conv_inst_tpl_edit = QtWidgets.QLineEdit(conv_inst_tpl_row)
    conv_inst_tpl_edit.setPlaceholderText("元件→实体：可选 instance_template_gia（输入内无实例可克隆时使用）")
    conv_inst_tpl_browse = QtWidgets.QPushButton("浏览…", conv_inst_tpl_row)
    conv_inst_tpl_browse.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    conv_inst_tpl_browse.clicked.connect(
        lambda: (
            (lambda p: conv_inst_tpl_edit.setText(str(Path(p).resolve())) if p else None)(
                QtWidgets.QFileDialog.getOpenFileName(tab2, "选择 instance_template_gia（可选）", "", "GIA (*.gia)")[0]
            )
        )
    )
    conv_inst_tpl_layout.addWidget(conv_inst_tpl_edit, 1)
    conv_inst_tpl_layout.addWidget(conv_inst_tpl_browse)
    conv_form.addRow("实例结构参考:", conv_inst_tpl_row)

    conv_pos_mode_combo = QtWidgets.QComboBox(conv_box)
    conv_pos_mode_combo.addItem("grid（按步长平铺）", "grid")
    conv_pos_mode_combo.addItem("origin（全部同点）", "origin")
    conv_form.addRow("摆放方式:", conv_pos_mode_combo)

    conv_start_pos = QtWidgets.QLineEdit(conv_box)
    conv_start_pos.setText("0,0,0")
    conv_start_pos.setPlaceholderText("元件→实体：起始位置 x,y,z（默认 0,0,0）")
    conv_form.addRow("起始位置:", conv_start_pos)

    conv_grid_step = QtWidgets.QLineEdit(conv_box)
    conv_grid_step.setText("200,0,0")
    conv_grid_step.setPlaceholderText("元件→实体：grid 步长 x,y,z（默认 200,0,0）")
    conv_form.addRow("grid 步长:", conv_grid_step)

    conv_default_rot = QtWidgets.QLineEdit(conv_box)
    conv_default_rot.setText("0,0,0")
    conv_default_rot.setPlaceholderText("元件→实体：默认旋转角度(deg) x,y,z（默认 0,0,0）")
    conv_form.addRow("默认旋转:", conv_default_rot)

    conv_default_scale = QtWidgets.QLineEdit(conv_box)
    conv_default_scale.setText("1,1,1")
    conv_default_scale.setPlaceholderText("元件→实体：默认缩放 x,y,z（默认 1,1,1）")
    conv_form.addRow("默认缩放:", conv_default_scale)

    conv_keep_file_path_cb = QtWidgets.QCheckBox("保持 Root.filePath 不变", conv_box)
    conv_form.addRow("", conv_keep_file_path_cb)

    conv_file_path_override = QtWidgets.QLineEdit(conv_box)
    conv_file_path_override.setPlaceholderText(r"可选：覆盖 Root.filePath（优先级高于保持不变）")
    conv_form.addRow("filePath 覆盖:", conv_file_path_override)

    conv_copy_to = QtWidgets.QLineEdit(conv_box)
    conv_copy_to.setPlaceholderText("可选：额外复制到指定目录（默认仍会复制到 Beyond_Local_Export）")
    conv_form.addRow("额外复制到:", conv_copy_to)

    tab2_layout.addWidget(conv_box)

    run_box2_widget, run_box2 = _build_run_box(QtWidgets=QtWidgets, ThemeManager=ThemeManager, Sizes=Sizes, parent=tab2)
    tab2_layout.addWidget(run_box2_widget)
    tab2_layout.addStretch(1)
    tabs.addTab(tab2, "元件↔实体转换")

    # ---- mode toggles ----
    def _sync_convert_mode_enabled_state() -> None:
        mode = str(conv_mode_combo.currentData() or "")
        is_comp_to_ent = mode == "component_to_entity"
        is_ent_to_comp = mode == "entity_to_component"

        conv_keep_unref_tpl_cb.setEnabled(bool(is_ent_to_comp))

        for w in [
            conv_tpl_contains,
            conv_drop_existing_inst_cb,
            conv_inst_tpl_row,
            conv_pos_mode_combo,
            conv_start_pos,
            conv_grid_step,
            conv_default_rot,
            conv_default_scale,
        ]:
            w.setEnabled(bool(is_comp_to_ent))

    conv_mode_combo.currentIndexChanged.connect(_sync_convert_mode_enabled_state)
    _sync_convert_mode_enabled_state()

    # ---- keep_world controls ----
    def _sync_deco_center_enabled_state() -> None:
        enabled = bool(deco_do_center_cb.isChecked())
        for w in [deco_center_policy_combo, deco_center_mode_combo, deco_center_axes_combo]:
            w.setEnabled(bool(enabled))

    deco_do_center_cb.stateChanged.connect(_sync_deco_center_enabled_state)
    _sync_deco_center_enabled_state()

    # ======================
    # Run handlers
    # ======================
    def _start_worker(*, argv: list[str], report_file: Path, run_box: _RunBox, title_text: str) -> None:
        existing_worker = getattr(dialog, "_gia_tools_worker", None)
        if _is_running_worker(existing_worker):
            dialog_utils.show_warning_dialog(dialog, "提示", "已有一个 GIA 工具任务在运行，请等待完成后再开始新的任务。")
            return

        worker = WorkerCls(workspace_root=Path(workspace_root), argv=list(argv), report_file=Path(report_file), parent=dialog)
        setattr(dialog, "_gia_tools_worker", worker)

        run_box.run_btn.setEnabled(False)
        run_box.status_label.setText(f"{title_text}：执行中…")
        run_box.log_text.setPlainText("")
        run_box.result_text.setPlainText("")

        def _append_log(line: str) -> None:
            t = str(line or "").rstrip("\n")
            if t == "":
                return
            run_box.log_text.appendPlainText(t)

        def _on_progress(current: int, total: int, label: str) -> None:
            if int(total) > 0:
                run_box.status_label.setText(f"{title_text}：[{int(current)}/{int(total)}] {str(label)}")

        def _on_failed(message: str) -> None:
            run_box.run_btn.setEnabled(True)
            run_box.status_label.setText(f"{title_text}：失败")
            run_box.result_text.setPlainText(str(message))
            dialog_utils.show_warning_dialog(dialog, "执行失败", str(message))

        def _on_succeeded(report: dict) -> None:
            run_box.run_btn.setEnabled(True)
            run_box.status_label.setText(f"{title_text}：完成")
            run_box.result_text.setPlainText(_format_report_text(report))
            dialog_utils.show_info_dialog(dialog, "执行完成", "已完成。\n\n输出信息请查看“执行结果”。")

        worker.log_line.connect(_append_log)
        worker.progress_changed.connect(_on_progress)
        worker.failed.connect(_on_failed)
        worker.succeeded.connect(_on_succeeded)
        worker.start()

    def _format_report_text(report: dict) -> str:
        # report 是工具侧通过 --report 输出的 JSON（wire-level 工具会补齐 exported_to/copied_to 等字段）。
        keys_first = [
            "input_gia_file",
            "output_gia_file",
            "exported_to",
            "copied_to",
            "mode",
            "accessories_count",
            "merged",
            "target_parent_unit_id",
            "center_policy",
            "center_space",
            "center",
            "shift_applied",
            "shift_space",
            "templates_in",
            "templates_out",
            "instances_in",
            "instances_out",
            "file_path",
        ]
        lines: list[str] = []
        for k in keys_first:
            if k in report:
                lines.append(f"- {k}: {report.get(k)}")
        for k in sorted([str(x) for x in report.keys() if str(x) not in set(keys_first)], key=lambda x: x.casefold()):
            lines.append(f"- {k}: {report.get(k)}")
        return "\n".join(lines).strip() if lines else "(report 为空)"

    def _build_report_path(tool_name: str) -> Path:
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return (tmp_dir / f"{tool_name}.report_{uuid4().hex[:10]}.json").resolve()

    # ---- Tab1 run ----
    def _run_decorations() -> None:
        input_text = str(deco_input_edit.text() or "").strip()
        if input_text == "":
            dialog_utils.show_warning_dialog(dialog, "提示", "请先选择输入 .gia。")
            return
        input_gia = Path(input_text).resolve()
        if not input_gia.is_file():
            dialog_utils.show_warning_dialog(dialog, "提示", f"输入文件不存在：{str(input_gia)}")
            return
        if input_gia.suffix.lower() != ".gia":
            dialog_utils.show_warning_dialog(dialog, "提示", "输入文件必须是 .gia。")
            return

        output_text = str(deco_output_edit.text() or "").strip()
        if output_text == "":
            dialog_utils.show_warning_dialog(dialog, "提示", "输出文件名不能为空。")
            return
        if not output_text.lower().endswith(".gia"):
            output_text = output_text + ".gia"
            deco_output_edit.setText(output_text)

        report_file = _build_report_path("gia_merge_and_center_decorations")

        argv: list[str] = [
            "tool",
            "--dangerous",
            "gia_merge_and_center_decorations",
            "--input-gia",
            str(input_gia),
            "--output",
            str(output_text),
            "--report",
            str(report_file),
            "--center-policy",
            str(deco_center_policy_combo.currentData() or "keep_world"),
            "--center-mode",
            str(deco_center_mode_combo.currentData() or "bbox"),
            "--center-axes",
            str(deco_center_axes_combo.currentData() or "xyz"),
        ]
        if bool(deco_check_header_cb.isChecked()):
            argv.append("--check-header")
        if not bool(deco_do_center_cb.isChecked()):
            argv.append("--no-center")
        if not bool(deco_do_merge_cb.isChecked()):
            argv.append("--no-merge")

        tid_text = str(deco_target_parent_id.text() or "").strip()
        if tid_text != "":
            if not tid_text.isdigit():
                dialog_utils.show_warning_dialog(dialog, "提示", "目标 parent_id 必须是整数。")
                return
            argv.extend(["--target-parent-id", str(tid_text)])

        tname_text = str(deco_target_parent_name.text() or "").strip()
        if tname_text != "":
            argv.extend(["--target-parent-name", str(tname_text)])

        if bool(deco_drop_other_cb.isChecked()):
            argv.append("--drop-other-parents")

        if bool(deco_keep_file_path_cb.isChecked()):
            argv.append("--keep-file-path")

        fp_text = str(deco_file_path_override.text() or "").strip()
        if fp_text != "":
            argv.extend(["--file-path", str(fp_text)])

        copy_to_text = str(deco_copy_to.text() or "").strip()
        if copy_to_text != "":
            argv.extend(["--copy-to", str(copy_to_text)])

        _start_worker(argv=argv, report_file=report_file, run_box=run_box1, title_text="装饰物合并/居中")

    run_box1.run_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    run_box1.run_btn.clicked.connect(_run_decorations)

    # ---- Tab2 run ----
    def _run_convert() -> None:
        input_text = str(conv_input_edit.text() or "").strip()
        if input_text == "":
            dialog_utils.show_warning_dialog(dialog, "提示", "请先选择输入 bundle.gia。")
            return
        input_gia = Path(input_text).resolve()
        if not input_gia.is_file():
            dialog_utils.show_warning_dialog(dialog, "提示", f"输入文件不存在：{str(input_gia)}")
            return
        if input_gia.suffix.lower() != ".gia":
            dialog_utils.show_warning_dialog(dialog, "提示", "输入文件必须是 .gia。")
            return

        output_text = str(conv_output_edit.text() or "").strip()
        if output_text == "":
            dialog_utils.show_warning_dialog(dialog, "提示", "输出文件名不能为空。")
            return
        if not output_text.lower().endswith(".gia"):
            output_text = output_text + ".gia"
            conv_output_edit.setText(output_text)

        mode = str(conv_mode_combo.currentData() or "").strip()
        if mode not in {"component_to_entity", "entity_to_component"}:
            raise ValueError(f"unknown convert mode: {mode!r}")

        report_file = _build_report_path("gia_convert_component_entity")

        argv: list[str] = [
            "tool",
            "--dangerous",
            "gia_convert_component_entity",
            "--input-gia",
            str(input_gia),
            "--output",
            str(output_text),
            "--mode",
            str(mode),
            "--report",
            str(report_file),
        ]
        if bool(conv_check_header_cb.isChecked()):
            argv.append("--check-header")

        if mode == "entity_to_component":
            if bool(conv_keep_unref_tpl_cb.isChecked()):
                argv.append("--keep-unreferenced-templates")

        if mode == "component_to_entity":
            name_contains = str(conv_tpl_contains.text() or "").strip()
            if name_contains != "":
                argv.extend(["--template-name-contains", str(name_contains)])
            if bool(conv_drop_existing_inst_cb.isChecked()):
                argv.append("--drop-existing-instances")
            inst_tpl_text = str(conv_inst_tpl_edit.text() or "").strip()
            if inst_tpl_text != "":
                inst_tpl_path = Path(inst_tpl_text).resolve()
                if not inst_tpl_path.is_file():
                    dialog_utils.show_warning_dialog(dialog, "提示", f"instance_template_gia 不存在：{str(inst_tpl_path)}")
                    return
                argv.extend(["--instance-template-gia", str(inst_tpl_path)])

            argv.extend(["--pos-mode", str(conv_pos_mode_combo.currentData() or "grid")])
            argv.extend(["--start-pos", str(conv_start_pos.text() or "0,0,0").strip() or "0,0,0"])
            argv.extend(["--grid-step", str(conv_grid_step.text() or "200,0,0").strip() or "200,0,0"])
            argv.extend(["--default-rot-deg", str(conv_default_rot.text() or "0,0,0").strip() or "0,0,0"])
            argv.extend(["--default-scale", str(conv_default_scale.text() or "1,1,1").strip() or "1,1,1"])

        if bool(conv_keep_file_path_cb.isChecked()):
            argv.append("--keep-file-path")

        fp_text = str(conv_file_path_override.text() or "").strip()
        if fp_text != "":
            argv.extend(["--file-path", str(fp_text)])

        copy_to_text = str(conv_copy_to.text() or "").strip()
        if copy_to_text != "":
            argv.extend(["--copy-to", str(copy_to_text)])

        _start_worker(argv=argv, report_file=report_file, run_box=run_box2, title_text="元件↔实体转换")

    run_box2.run_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    run_box2.run_btn.clicked.connect(_run_convert)

    # ======================
    # Footer
    # ======================
    footer_row = QtWidgets.QHBoxLayout()
    footer_row.addStretch(1)
    close_btn = QtWidgets.QPushButton("关闭", dialog)
    close_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
    close_btn.clicked.connect(dialog.reject)
    footer_row.addWidget(close_btn)
    root_layout.addLayout(footer_row)

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

