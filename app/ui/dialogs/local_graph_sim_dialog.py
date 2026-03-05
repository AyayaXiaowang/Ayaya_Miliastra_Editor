"""节点图 + UI 本地测试对话框（浏览器预览）。"""

from __future__ import annotations

import json
import sys
import time
from importlib.util import find_spec
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets

from app.automation.input.subprocess_runner import spawn_process
from app.runtime.services.local_graph_sim_dialog_logic import (
    LocalGraphSimOwnerInferenceService,
    OwnerCandidate,
    parse_graph_id_from_source_file,
    parse_kv_lines,
    pick_preferred_candidate_index,
)
from app.runtime.services.local_graph_sim_server import (
    get_preferred_local_sim_http_port,
)
from app.runtime.services.local_graph_simulator import GraphMountSpec
from app.ui.foundation import dialog_utils
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager
from engine.utils.cache.cache_paths import get_runtime_cache_root

if TYPE_CHECKING:
    from engine.resources.package_index_manager import PackageIndexManager
    from engine.resources.resource_manager import ResourceManager


class LocalGraphSimDialog(BaseDialog):
    """在主程序内启动本地测试（HTTP server + 浏览器预览）。"""

    def __init__(
        self,
        *,
        workspace_root: Path,
        active_package_id: str | None = None,
        resource_manager: "ResourceManager | None" = None,
        package_index_manager: "PackageIndexManager | None" = None,
        parent=None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        pkg = str(active_package_id or "").strip()
        if pkg == "global_view":
            pkg = ""
        self.active_package_id: str | None = pkg or None

        # 运行隔离：本地测试 server 在独立子进程中启动，避免在主进程内执行节点图源码。
        self._server_process: object | None = None
        self._server_ready_file: Path | None = None
        self._server_log_file: Path | None = None
        self._server_ready_timer: QtCore.QTimer | None = None
        self._server_ready_deadline_monotonic: float = 0.0

        # ---- selection state (fallback mode)
        self._fallback_graph_files: list[Path] = []
        self._fallback_ui_html_file: Path | None = None
        self._fallback_entry_graph_file: Path | None = None

        # ---- owner inference
        self._owner_service = LocalGraphSimOwnerInferenceService(
            resource_manager=resource_manager,
            package_index_manager=package_index_manager,
        )
        self._entry_graph_path: Path | None = None
        self._entry_graph_id: str = ""
        self._owner_manually_modified: bool = False
        self._owner_last_autofill_value: str = ""

        # ---- export-style picker integration (optional)
        self._export_style_picker: QtWidgets.QWidget | None = None
        self._export_style_entry_combo: QtWidgets.QComboBox | None = None
        self._export_style_ui_combo: QtWidgets.QComboBox | None = None
        self._export_style_status_label: QtWidgets.QLabel | None = None

        super().__init__(
            title="本地测试（节点图 + UI）",
            width=1040,
            height=680,
            buttons=QtWidgets.QDialogButtonBox.StandardButton.Close,
            parent=parent,
        )

        # 工具对话框：允许用户一边操作主窗口一边测试
        self.setModal(False)

        close_button = self.button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Close)
        if close_button is not None:
            close_button.setText("关闭")

        self._build_content()
        self._update_run_summary()

    # ------------------------------------------------------------------ styles

    def _apply_styles(self) -> None:
        self.setStyleSheet(ThemeManager.dialog_surface_style())

    # ------------------------------------------------------------------ ui

    def _build_content(self) -> None:
        layout = self.content_layout

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ----------------------------- left: selections
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.tabs = QtWidgets.QTabWidget()
        left_layout.addWidget(self.tabs, 1)

        self._build_select_tab()

        # 仅保留一个 tab 时隐藏 tabBar，避免出现旧标签页入口
        tab_bar = self.tabs.tabBar()
        if tab_bar is not None:
            tab_bar.hide()

        splitter.addWidget(left)

        # ----------------------------- right: settings + controls
        right = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        settings_group = QtWidgets.QGroupBox("运行设置")
        settings_layout = QtWidgets.QFormLayout(settings_group)
        settings_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        right_layout.addWidget(settings_group)

        self.owner_entity_edit = QtWidgets.QLineEdit("自身实体")
        self.owner_entity_edit.setToolTip("勾选的节点图会统一挂载到该实体名。")
        self.owner_entity_edit.textChanged.connect(self._update_run_summary)
        self.owner_entity_edit.textEdited.connect(self._on_owner_text_edited)
        settings_layout.addRow("owner：", self.owner_entity_edit)

        self.owner_source_combo = QtWidgets.QComboBox()
        self.owner_source_combo.setToolTip("从主图（入口挂载图）的引用资源推断 owner（仅当前项目）。")
        self.owner_source_combo.currentIndexChanged.connect(self._on_owner_source_combo_changed)

        refresh_owner_sources_btn = QtWidgets.QPushButton("刷新引用")
        refresh_owner_sources_btn.clicked.connect(self._on_refresh_owner_sources_clicked)

        owner_source_row = QtWidgets.QHBoxLayout()
        owner_source_row.setContentsMargins(0, 0, 0, 0)
        owner_source_row.setSpacing(6)
        owner_source_row.addWidget(self.owner_source_combo, 1)
        owner_source_row.addWidget(refresh_owner_sources_btn)

        owner_source_widget = QtWidgets.QWidget()
        owner_source_widget.setLayout(owner_source_row)
        settings_layout.addRow("owner推断：", owner_source_widget)

        self.owner_source_status_label = QtWidgets.QLabel("")
        self.owner_source_status_label.setWordWrap(True)
        self.owner_source_status_label.setStyleSheet(ThemeManager.subtle_info_style())
        settings_layout.addRow("", self.owner_source_status_label)

        self.player_entity_edit = QtWidgets.QLineEdit("玩家1")
        settings_layout.addRow("player：", self.player_entity_edit)

        self.present_players_spin = QtWidgets.QSpinBox()
        self.present_players_spin.setRange(1, 8)
        self.present_players_spin.setValue(1)
        self.present_players_spin.setToolTip("用于“获取在场玩家实体列表/等待其他玩家/投票门槛”等多人逻辑模拟。")
        settings_layout.addRow("在场玩家：", self.present_players_spin)

        self.port_spin = QtWidgets.QSpinBox()
        self.port_spin.setRange(0, 65535)
        self.port_spin.setValue(int(get_preferred_local_sim_http_port()))
        self.port_spin.setToolTip(
            "本地测试 HTTP 监听端口（基准端口）。\n"
            "- 会优先使用该端口；若端口已被占用则向上顺延扫描；扫描不到才回退为系统临时端口。\n"
            "- 默认基准端口为 17890（可用环境变量 AYAYA_LOCAL_HTTP_PORT 覆盖；兼容 AYAYA_LOCAL_SIM_PORT 别名）。\n"
            "- 设为 0：直接让系统分配临时端口（URL 每次可能不同）。"
        )
        settings_layout.addRow("端口：", self.port_spin)

        self.run_summary_label = QtWidgets.QLabel("")
        self.run_summary_label.setWordWrap(True)
        self.run_summary_label.setStyleSheet(ThemeManager.subtle_info_style())
        right_layout.addWidget(self.run_summary_label)

        auto_group = QtWidgets.QGroupBox("启动初始化（可选）")
        auto_layout = QtWidgets.QVBoxLayout(auto_group)
        auto_layout.setContentsMargins(10, 10, 10, 10)
        auto_layout.setSpacing(8)
        right_layout.addWidget(auto_group)

        self.auto_signal_checkbox = QtWidgets.QCheckBox("启动后自动发送一次信号（用于首帧初始化）")
        self.auto_signal_checkbox.setChecked(True)
        auto_layout.addWidget(self.auto_signal_checkbox)

        self.auto_signal_id_edit = QtWidgets.QLineEdit("signal_level_lobby_start_level")
        self.auto_signal_id_edit.setPlaceholderText("signal_id（例如 signal_level_lobby_start_level）")
        auto_layout.addWidget(self.auto_signal_id_edit)

        self.auto_params_edit = QtWidgets.QPlainTextEdit()
        self.auto_params_edit.setPlaceholderText("参数：每行 key=value（例如：第X关=7）")
        self.auto_params_edit.setPlainText("第X关=7")
        self.auto_params_edit.setMaximumHeight(120)
        auto_layout.addWidget(self.auto_params_edit)

        preview_group = QtWidgets.QGroupBox("预览与控制")
        preview_layout = QtWidgets.QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(10, 10, 10, 10)
        preview_layout.setSpacing(8)
        right_layout.addWidget(preview_group)

        url_row = QtWidgets.QHBoxLayout()
        preview_layout.addLayout(url_row)

        self.url_edit = QtWidgets.QLineEdit()
        self.url_edit.setReadOnly(True)
        self.url_edit.setPlaceholderText("启动后会显示预览 URL")
        url_row.addWidget(self.url_edit, 1)

        copy_btn = QtWidgets.QPushButton("复制 URL")
        copy_btn.clicked.connect(self._copy_url)
        url_row.addWidget(copy_btn)

        buttons_row = QtWidgets.QHBoxLayout()
        preview_layout.addLayout(buttons_row)

        self.start_btn = QtWidgets.QPushButton("启动")
        self.start_btn.clicked.connect(self._on_start_clicked)
        buttons_row.addWidget(self.start_btn)

        self.stop_btn = QtWidgets.QPushButton("停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        buttons_row.addWidget(self.stop_btn)

        self.open_browser_btn = QtWidgets.QPushButton("打开浏览器")
        self.open_browser_btn.setEnabled(False)
        self.open_browser_btn.clicked.connect(self._open_browser)
        buttons_row.addWidget(self.open_browser_btn)

        buttons_row.addStretch(1)

        right_layout.addStretch(1)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        # 初始刷新 owner 推断（若主图已由选择面板决定）
        self._refresh_owner_sources_for_entry_graph(force_rebuild=False)

    def _build_select_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        pkg = str(self.active_package_id or "").strip()
        if not pkg:
            tip = QtWidgets.QLabel("未选择项目存档：请先切换到某个【项目存档】再使用本地测试。")
            tip.setWordWrap(True)
            tip.setStyleSheet(ThemeManager.subtle_info_style())
            layout.addWidget(tip)
            self.tabs.addTab(tab, "选择测试内容")
            return

        if self._can_use_export_style_picker():
            self._build_export_style_picker_ui(parent=tab, layout=layout, package_id=pkg)
        else:
            self._build_fallback_file_picker_ui(parent=tab, layout=layout)

        self.tabs.addTab(tab, "选择测试内容")

    # ------------------------------------------------------------------ selection (export-style picker)

    def _can_use_export_style_picker(self) -> bool:
        # ugc_file_tools 是可选私有扩展：只有在 importable 时才启用“导出中心风格”选择器
        return find_spec("ugc_file_tools.ui_integration.resource_picker") is not None

    def _build_export_style_picker_ui(self, *, parent: QtWidgets.QWidget, layout: QtWidgets.QVBoxLayout, package_id: str) -> None:
        tip = QtWidgets.QLabel(
            "说明：此处复用「导出中心」的资源选择器。\n"
            "- 支持按文件夹三态勾选：勾选文件夹=全选该文件夹下所有节点图；\n"
            "- 本地测试仅使用：节点图源码（graphs）与 UI源码（ui_src）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(tip)

        from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir

        resource_library_root = (self.workspace_root / "assets" / "资源库").resolve()
        packages_root = get_packages_root_dir(resource_library_root).resolve()
        shared_root = get_shared_root_dir(resource_library_root).resolve()
        project_root = (packages_root / str(package_id)).resolve()

        from app.ui.foundation.theme_manager import Colors, Sizes
        from ugc_file_tools.ui_integration.resource_picker import (
            build_resource_selection_items,
            make_resource_picker_widget_cls,
        )

        catalog = build_resource_selection_items(project_root=project_root, shared_root=shared_root, include_shared=True)
        PickerWidgetCls = make_resource_picker_widget_cls(
            QtCore=QtCore,
            QtWidgets=QtWidgets,
            Colors=Colors,
            Sizes=Sizes,
        )
        picker = PickerWidgetCls(
            parent,
            catalog=dict(catalog),
            allowed_categories={"graphs", "ui_src"},
            preselected_keys=None,
            show_remove_button=False,
            show_selected_panel=False,
            count_format="plain",
        )
        self._export_style_picker = picker
        layout.addWidget(picker, 1)

        bottom = QtWidgets.QGroupBox("主图与入口页面（用于启动本地测试）")
        bottom.setStyleSheet(ThemeManager.group_box_style())
        form = QtWidgets.QFormLayout(bottom)
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(10, 16, 10, 10)

        entry_combo = QtWidgets.QComboBox(bottom)
        entry_combo.setToolTip("主图：作为本地模拟会话的主挂载图；未选择则使用已选节点图的第一个。")
        self._export_style_entry_combo = entry_combo
        form.addRow("主图：", entry_combo)

        ui_combo = QtWidgets.QComboBox(bottom)
        ui_combo.setToolTip(
            "入口页面：作为监控面板中 iframe 预览的起始 UI HTML。\n"
            "- 资源树中可勾选多个 UI HTML（便于快速切换）；\n"
            "- 启动时必须在此下拉框明确选择 1 个入口页面；\n"
            "- 本地测试的 layout 扫描以入口页面所在目录为准（同目录 *.html 会自动成为可切换布局）。"
        )
        self._export_style_ui_combo = ui_combo
        form.addRow("入口页面：", ui_combo)

        status = QtWidgets.QLabel("")
        status.setWordWrap(True)
        status.setStyleSheet(ThemeManager.subtle_info_style())
        self._export_style_status_label = status
        form.addRow("", status)

        layout.addWidget(bottom)

        def _sync_from_picker() -> None:
            items = list(picker.get_selected_items())
            graph_items = [it for it in items if getattr(it, "category", "") == "graphs"]
            ui_items = [it for it in items if getattr(it, "category", "") == "ui_src"]
            graph_items.sort(key=lambda it: (str(getattr(it, "source_root", "")), str(getattr(it, "relative_path", "")).casefold()))
            ui_items.sort(key=lambda it: (str(getattr(it, "source_root", "")), str(getattr(it, "relative_path", "")).casefold()))

            prev_entry = str(entry_combo.currentData() or "")
            with QtCore.QSignalBlocker(entry_combo):
                entry_combo.clear()
                entry_combo.addItem("自动：使用第一个已选节点图", "")
                for it in graph_items:
                    abs_path = str(getattr(it, "absolute_path", "") or "")
                    label = f"[{'项目' if getattr(it,'source_root','')=='project' else '共享'}] {getattr(it,'relative_path','')}"
                    entry_combo.addItem(label, abs_path)
                if prev_entry:
                    idx = entry_combo.findData(prev_entry)
                    if idx >= 0:
                        entry_combo.setCurrentIndex(idx)

            prev_ui = str(ui_combo.currentData() or "")
            with QtCore.QSignalBlocker(ui_combo):
                ui_combo.clear()
                ui_combo.addItem("请选择入口页面（从已勾选 UI 源码中选择）", "")
                for it in ui_items:
                    abs_path = str(getattr(it, "absolute_path", "") or "")
                    label = f"[{'项目' if getattr(it,'source_root','')=='project' else '共享'}] {getattr(it,'relative_path','')}"
                    ui_combo.addItem(label, abs_path)
                if prev_ui:
                    idx2 = ui_combo.findData(prev_ui)
                    if idx2 >= 0:
                        ui_combo.setCurrentIndex(idx2)
                elif len(ui_items) == 1:
                    ui_combo.setCurrentIndex(1)

            status_lines = [f"已选节点图：{len(graph_items)} 个", f"已选 UI源码：{len(ui_items)} 个"]
            if len(ui_items) >= 1 and (not str(ui_combo.currentData() or "").strip()):
                status_lines.append("提示：请在下拉框选择 1 个入口页面（资源树可多选）。")
            status.setText("\n".join(status_lines))

            # 同步主图用于 owner 推断/运行摘要
            self._sync_entry_graph_from_current_selection()
            self._update_run_summary()

        picker.selection_changed.connect(_sync_from_picker)
        entry_combo.currentIndexChanged.connect(lambda _i: _sync_from_picker())
        ui_combo.currentIndexChanged.connect(lambda _i: self._update_run_summary())
        _sync_from_picker()

    # ------------------------------------------------------------------ selection (fallback file picker)

    def _build_fallback_file_picker_ui(self, *, parent: QtWidgets.QWidget, layout: QtWidgets.QVBoxLayout) -> None:
        tip = QtWidgets.QLabel(
            "当前工作区未启用「ugc_file_tools」私有扩展：已切换为内置文件选择模式。\n"
            "- 请选择至少 1 个节点图源码（.py）与 1 个 UI HTML 文件；\n"
            "- 若你希望使用“导出中心风格资源选择器”，请确保 `private_extensions/ugc_file_tools` 可被导入（通常由私有扩展 plugin 注入 sys.path）。"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(tip)

        tools_row = QtWidgets.QHBoxLayout()
        layout.addLayout(tools_row)

        pick_graphs_btn = QtWidgets.QPushButton("选择节点图…（可多选）")
        pick_graphs_btn.clicked.connect(self._fallback_pick_graph_files)
        tools_row.addWidget(pick_graphs_btn)

        pick_ui_btn = QtWidgets.QPushButton("选择入口页面（UI HTML）…")
        pick_ui_btn.clicked.connect(self._fallback_pick_ui_html_file)
        tools_row.addWidget(pick_ui_btn)

        clear_btn = QtWidgets.QPushButton("清空选择")
        clear_btn.clicked.connect(self._fallback_clear_selection)
        tools_row.addWidget(clear_btn)

        tools_row.addStretch(1)

        entry_combo = QtWidgets.QComboBox(parent)
        entry_combo.setToolTip("主图：作为本地模拟会话的主挂载图；未选择则使用已选节点图的第一个。")
        self._export_style_entry_combo = entry_combo  # 复用字段名：便于统一 selection 读取
        entry_combo.currentIndexChanged.connect(lambda _i: self._on_fallback_entry_changed())

        ui_line = QtWidgets.QLineEdit("")
        ui_line.setReadOnly(True)
        ui_line.setPlaceholderText("未选择入口页面")
        self._fallback_ui_line = ui_line  # type: ignore[attr-defined]

        form = QtWidgets.QFormLayout()
        form.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        form.addRow("主图：", entry_combo)
        form.addRow("入口页面：", ui_line)
        layout.addLayout(form)

        graphs_list = QtWidgets.QListWidget(parent)
        graphs_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self._fallback_graphs_list = graphs_list  # type: ignore[attr-defined]
        layout.addWidget(graphs_list, 1)

        status = QtWidgets.QLabel("")
        status.setWordWrap(True)
        status.setStyleSheet(ThemeManager.subtle_info_style())
        self._export_style_status_label = status
        layout.addWidget(status)

        self._fallback_refresh_widgets()

    def _fallback_pick_graph_files(self) -> None:
        files, _filter = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "选择节点图源码（可多选）",
            "",
            "Python Files (*.py);;All Files (*)",
        )
        paths = [Path(p).resolve() for p in list(files or []) if str(p).strip()]
        paths = [p for p in paths if p.is_file()]
        paths.sort(key=lambda p: p.as_posix().casefold())
        self._fallback_graph_files = paths
        if self._fallback_entry_graph_file not in self._fallback_graph_files:
            self._fallback_entry_graph_file = self._fallback_graph_files[0] if self._fallback_graph_files else None
        self._fallback_refresh_widgets()
        self._sync_entry_graph_from_current_selection()
        self._update_run_summary()

    def _fallback_pick_ui_html_file(self) -> None:
        file, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择 UI HTML",
            "",
            "HTML Files (*.html *.htm);;All Files (*)",
        )
        p = Path(file).resolve() if str(file).strip() else None
        self._fallback_ui_html_file = p if (p is not None and p.is_file()) else None
        self._fallback_refresh_widgets()
        self._update_run_summary()

    def _fallback_clear_selection(self) -> None:
        self._fallback_graph_files = []
        self._fallback_ui_html_file = None
        self._fallback_entry_graph_file = None
        self._fallback_refresh_widgets()
        self._sync_entry_graph_from_current_selection()
        self._update_run_summary()

    def _fallback_refresh_widgets(self) -> None:
        graphs_list: QtWidgets.QListWidget | None = getattr(self, "_fallback_graphs_list", None)
        ui_line: QtWidgets.QLineEdit | None = getattr(self, "_fallback_ui_line", None)
        entry_combo = self._export_style_entry_combo
        status = self._export_style_status_label

        if graphs_list is not None:
            graphs_list.clear()
            for p in list(self._fallback_graph_files or []):
                graphs_list.addItem(p.name)

        if ui_line is not None:
            ui_line.setText(str(self._fallback_ui_html_file) if self._fallback_ui_html_file else "")

        if entry_combo is not None:
            prev = str(entry_combo.currentData() or "")
            with QtCore.QSignalBlocker(entry_combo):
                entry_combo.clear()
                entry_combo.addItem("自动：使用第一个已选节点图", "")
                for p in list(self._fallback_graph_files or []):
                    entry_combo.addItem(p.name, p.as_posix())
                # restore
                if prev:
                    idx = entry_combo.findData(prev)
                    if idx >= 0:
                        entry_combo.setCurrentIndex(idx)
                elif self._fallback_entry_graph_file is not None:
                    idx2 = entry_combo.findData(self._fallback_entry_graph_file.as_posix())
                    if idx2 >= 0:
                        entry_combo.setCurrentIndex(idx2)

        if status is not None:
            lines = [f"已选节点图：{len(self._fallback_graph_files)} 个", f"UI：{'已选择' if self._fallback_ui_html_file else '未选择'}"]
            status.setText("\n".join(lines))

    def _on_fallback_entry_changed(self) -> None:
        entry_combo = self._export_style_entry_combo
        if entry_combo is None:
            return
        chosen = str(entry_combo.currentData() or "").strip()
        self._fallback_entry_graph_file = Path(chosen).resolve() if chosen else None
        if self._fallback_entry_graph_file is not None and self._fallback_entry_graph_file not in self._fallback_graph_files:
            self._fallback_entry_graph_file = None
        self._sync_entry_graph_from_current_selection()
        self._update_run_summary()

    # ------------------------------------------------------------------ lifecycle

    def reject(self) -> None:
        self._stop_server()
        super().reject()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._stop_server()
        super().closeEvent(event)

    # ------------------------------------------------------------------ selection helpers

    def _get_current_graph_files(self) -> list[Path]:
        picker = self._export_style_picker
        if picker is not None and hasattr(picker, "get_selected_items"):
            items = list(picker.get_selected_items())
            graph_items = [it for it in items if getattr(it, "category", "") == "graphs"]
            graph_files = [Path(getattr(it, "absolute_path")).resolve() for it in graph_items]
            graph_files = [p for p in graph_files if p.is_file()]
            graph_files.sort(key=lambda p: p.as_posix().casefold())
            return graph_files
        return list(self._fallback_graph_files or [])

    def _get_current_ui_html_file(self) -> Path | None:
        picker = self._export_style_picker
        if picker is not None and hasattr(picker, "get_selected_items"):
            items = list(picker.get_selected_items())
            ui_items = [it for it in items if getattr(it, "category", "") == "ui_src"]
            if not ui_items:
                return None

            combo = self._export_style_ui_combo
            chosen = str(combo.currentData() or "").strip() if combo is not None else ""
            selected_paths = {Path(getattr(it, "absolute_path")).resolve() for it in ui_items}

            if chosen:
                p = Path(chosen).resolve()
                if p in selected_paths and p.is_file():
                    return p
                return None

            # 兼容：若只勾选了 1 个 UI HTML，则允许自动使用它
            if len(ui_items) == 1:
                p2 = next(iter(selected_paths))
                return p2 if p2.is_file() else None

            return None
        return self._fallback_ui_html_file

    def _get_current_entry_graph_file(self, graph_files: list[Path]) -> Path | None:
        chosen = ""
        combo = self._export_style_entry_combo
        if combo is not None:
            chosen = str(combo.currentData() or "").strip()
        if chosen:
            p = Path(chosen).resolve()
            if p in graph_files:
                return p
        return graph_files[0] if graph_files else None

    def _sync_entry_graph_from_current_selection(self) -> None:
        graph_files = self._get_current_graph_files()
        entry = self._get_current_entry_graph_file(graph_files)
        self._entry_graph_path = entry
        self._refresh_owner_sources_for_entry_graph(force_rebuild=False)

    # ------------------------------------------------------------------ start/stop

    def _on_start_clicked(self) -> None:
        pkg = str(self.active_package_id or "").strip()
        if not pkg:
            dialog_utils.show_warning_dialog(self, "无法启动本地测试", "请先切换到某个【项目存档】。")
            return

        graph_files = self._get_current_graph_files()
        if not graph_files:
            dialog_utils.show_warning_dialog(self, "节点图选择错误", "请至少选择 1 个节点图。")
            return

        html_path = self._get_current_ui_html_file()
        if html_path is None:
            dialog_utils.show_warning_dialog(
                self,
                "UI 选择错误",
                "请勾选至少 1 个 UI HTML（UI源码），并在下拉框选择 1 个入口页面。",
            )
            return

        entry = self._get_current_entry_graph_file(graph_files)
        if entry is None or not entry.is_file():
            dialog_utils.show_warning_dialog(self, "主图无效", "主图不存在或不可读。")
            return

        owner_name = self.owner_entity_edit.text().strip() or "自身实体"
        player_name = self.player_entity_edit.text().strip() or "玩家1"
        present_players = int(self.present_players_spin.value() or 1)
        port = int(self.port_spin.value() or 0)

        extra_mounts = [
            GraphMountSpec(graph_code_file=p, owner_entity_name=owner_name)
            for p in list(graph_files or [])
            if p != entry
        ]

        auto_signal_id = ""
        auto_params: dict[str, Any] = {}
        if bool(self.auto_signal_checkbox.isChecked()):
            auto_signal_id = self.auto_signal_id_edit.text().strip()
            params, error = parse_kv_lines(self.auto_params_edit.toPlainText())
            if error:
                dialog_utils.show_warning_dialog(self, "参数格式错误", error)
                return
            auto_params = params

        # 重启 server（避免端口冲突与状态污染）
        self._stop_server()

        ready_dir = (get_runtime_cache_root(self.workspace_root) / "local_graph_sim" / "ui_subprocess").resolve()
        ready_dir.mkdir(parents=True, exist_ok=True)
        nonce = int(time.monotonic_ns())
        ready_file = (ready_dir / f"local_sim_ready.{nonce}.json").resolve()
        log_file = (ready_dir / f"local_sim_subprocess.{nonce}.log.txt").resolve()
        if ready_file.exists():
            ready_file.unlink()

        cmd = self._build_local_sim_subprocess_cmd(
            workspace_root=self.workspace_root,
            entry_graph_file=Path(entry).resolve(),
            extra_mounts=list(extra_mounts or []),
            ui_html_file=Path(html_path).resolve(),
            owner_name=owner_name,
            player_name=player_name,
            present_players=present_players,
            port=port,
            auto_signal_id=auto_signal_id,
            auto_params=dict(auto_params or {}),
            ready_file=ready_file,
        )

        # 输出重定向到日志文件，避免 pipe 缓冲区写满导致子进程阻塞
        log_handle = log_file.open("w", encoding="utf-8", errors="replace")
        proc = spawn_process(
            cmd,
            working_directory=self.workspace_root,
            stdout=log_handle,
            stderr=log_handle,
        )
        log_handle.close()

        self._server_process = proc
        self._server_ready_file = ready_file
        self._server_log_file = log_file
        self._server_ready_deadline_monotonic = float(time.monotonic()) + 8.0

        self.url_edit.setText("")
        self.stop_btn.setEnabled(True)
        self.open_browser_btn.setEnabled(False)

        timer = QtCore.QTimer(self)
        timer.setInterval(100)
        timer.timeout.connect(self._poll_local_sim_subprocess_ready)
        self._server_ready_timer = timer
        timer.start()

    def _on_stop_clicked(self) -> None:
        self._stop_server()

    def _stop_server(self) -> None:
        timer = self._server_ready_timer
        if timer is not None:
            timer.stop()
        self._server_ready_timer = None

        proc = self._server_process
        if proc is not None:
            poll = getattr(proc, "poll", None)
            terminate = getattr(proc, "terminate", None)
            kill = getattr(proc, "kill", None)
            if callable(poll) and poll() is None and callable(terminate):
                terminate()
            if callable(poll) and poll() is None and callable(kill):
                kill()
        self._server_process = None
        self._server_ready_file = None
        self._server_log_file = None
        self._server_ready_deadline_monotonic = 0.0
        self.stop_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)
        self.url_edit.setText("")

    def _build_local_sim_subprocess_cmd(
        self,
        *,
        workspace_root: Path,
        entry_graph_file: Path,
        extra_mounts: list[GraphMountSpec],
        ui_html_file: Path,
        owner_name: str,
        player_name: str,
        present_players: int,
        port: int,
        auto_signal_id: str,
        auto_params: dict[str, Any],
        ready_file: Path,
    ) -> list[str]:
        cmd: list[str] = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "app.cli.local_graph_sim",
            "--root",
            str(Path(workspace_root).resolve()),
            "serve",
            "--graph",
            str(Path(entry_graph_file).resolve()),
            "--ui-html",
            str(Path(ui_html_file).resolve()),
            "--host",
            "127.0.0.1",
            "--port",
            str(int(port)),
            "--no-open",
            "--owner",
            str(owner_name or "自身实体"),
            "--player",
            str(player_name or "玩家1"),
            "--present-players",
            str(int(max(1, int(present_players)))),
            "--ready-file",
            str(Path(ready_file).resolve()),
        ]

        # 额外挂载图
        for m in list(extra_mounts or []):
            p = Path(getattr(m, "graph_code_file", None)).resolve()
            cmd += ["--extra-graph", str(p)]
            owner = str(getattr(m, "owner_entity_name", "") or "").strip()
            if owner:
                cmd += ["--extra-owner", owner]

        # 启动初始化信号
        auto_sid = str(auto_signal_id or "").strip()
        if auto_sid:
            cmd += ["--auto-signal-id", auto_sid]
            for k, v in dict(auto_params or {}).items():
                key = str(k or "").strip()
                if not key:
                    continue
                if isinstance(v, bool):
                    value_text = "true" if v else "false"
                else:
                    value_text = str(v)
                cmd += ["--auto-param", f"{key}={value_text}"]

        return cmd

    def _poll_local_sim_subprocess_ready(self) -> None:
        ready_file = self._server_ready_file
        proc = self._server_process
        log_file = self._server_log_file

        if ready_file is None or proc is None:
            self._stop_server()
            return

        if ready_file.is_file():
            payload = json.loads(ready_file.read_text(encoding="utf-8"))
            url = str(payload.get("url") or "").strip() if isinstance(payload, dict) else ""
            ok = bool(payload.get("ok", False)) if isinstance(payload, dict) else False
            if not ok or not url:
                dialog_utils.show_warning_dialog(
                    self,
                    "本地测试启动失败",
                    "子进程未返回有效 URL。\n"
                    f"- ready_file: {ready_file}\n"
                    f"- log_file: {log_file}",
                )
                self._stop_server()
                return

            timer = self._server_ready_timer
            if timer is not None:
                timer.stop()
            self._server_ready_timer = None

            self.url_edit.setText(url)
            self.open_browser_btn.setEnabled(True)
            self._open_browser()
            return

        poll = getattr(proc, "poll", None)
        exit_code = poll() if callable(poll) else None
        if exit_code is not None:
            dialog_utils.show_warning_dialog(
                self,
                "本地测试启动失败",
                "子进程已退出，未生成 ready_file。\n"
                f"- exit_code: {exit_code}\n"
                f"- ready_file: {ready_file}\n"
                f"- log_file: {log_file}",
            )
            self._stop_server()
            return

        if self._server_ready_deadline_monotonic > 0.0 and float(time.monotonic()) > float(self._server_ready_deadline_monotonic):
            dialog_utils.show_warning_dialog(
                self,
                "本地测试启动超时",
                "等待子进程启动超时（未生成 ready_file）。\n"
                f"- ready_file: {ready_file}\n"
                f"- log_file: {log_file}",
            )
            self._stop_server()
            return

    # ------------------------------------------------------------------ browser

    def _open_browser(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        decorated = url
        if "?" not in decorated:
            decorated = decorated.rstrip("/") + "/?flatten=1"
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(decorated))

    def _copy_url(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(url)

    # ------------------------------------------------------------------ owner inference (entry graph -> owner)

    def _on_owner_text_edited(self, _text: str) -> None:
        self._owner_manually_modified = True
        self._owner_last_autofill_value = ""

    def _on_owner_source_combo_changed(self, index: int) -> None:
        data = self.owner_source_combo.itemData(int(index))
        if not isinstance(data, dict):
            return
        if data.get("kind") != "ref":
            return
        owner_name = str(data.get("owner_name") or "").strip()
        if not owner_name:
            return
        self.owner_entity_edit.setText(owner_name)
        self._owner_manually_modified = False
        self._owner_last_autofill_value = owner_name

    def _on_refresh_owner_sources_clicked(self) -> None:
        self._refresh_owner_sources_for_entry_graph(force_rebuild=True)

    def _refresh_owner_sources_for_entry_graph(self, *, force_rebuild: bool) -> None:
        # 对话框构建过程中，左侧选择面板可能先于右侧 owner 控件创建；
        # 此时只缓存主图信息，不触发 UI 更新，待 _build_content 末尾再刷新一次即可。
        if (not hasattr(self, "owner_source_combo")) or (not hasattr(self, "owner_source_status_label")):
            return

        pkg = str(self.active_package_id or "").strip()
        entry_path = self._entry_graph_path

        if entry_path is None or (not Path(entry_path).is_file()):
            self._entry_graph_id = ""
            self._populate_owner_source_combo(graph_id="", candidates=[])
            self.owner_source_status_label.setText("未选择主图，无法推断 owner。")
            self.owner_source_combo.setEnabled(False)
            return

        gid = parse_graph_id_from_source_file(Path(entry_path))
        self._entry_graph_id = gid
        if not gid:
            self._populate_owner_source_combo(graph_id="", candidates=[])
            self.owner_source_status_label.setText("主图未声明 graph_id，无法推断 owner（保持手动）。")
            self.owner_source_combo.setEnabled(True)
            return

        if not self._owner_service.is_available():
            self._populate_owner_source_combo(graph_id=gid, candidates=[])
            self.owner_source_status_label.setText(f"主图 graph_id={gid}：未注入资源管理器，无法推断 owner（保持手动）。")
            self.owner_source_combo.setEnabled(True)
            return

        self._owner_service.ensure_index(package_id=pkg, force_rebuild=bool(force_rebuild))
        candidates = self._owner_service.list_candidates(package_id=pkg, graph_id=gid)
        self._populate_owner_source_combo(graph_id=gid, candidates=candidates)

    def _populate_owner_source_combo(self, *, graph_id: str, candidates: list[OwnerCandidate]) -> None:
        gid = str(graph_id or "").strip()
        pkg = str(self.active_package_id or "").strip()

        with QtCore.QSignalBlocker(self.owner_source_combo):
            self.owner_source_combo.clear()
            self.owner_source_combo.addItem("手动（使用 owner 输入框）", {"kind": "manual"})

            if not pkg:
                self.owner_source_status_label.setText("未打开项目存档，无法推断 owner。")
                self.owner_source_combo.setEnabled(False)
                self.owner_source_combo.setCurrentIndex(0)
                return

            if not gid:
                self.owner_source_combo.setEnabled(True)
                self.owner_source_combo.setCurrentIndex(0)
                return

            for c in list(candidates or []):
                label = f"{c.display_type}：{c.entity_name}"
                self.owner_source_combo.addItem(label, {"kind": "ref", **c.to_combo_payload()})

            ref_count = max(0, self.owner_source_combo.count() - 1)
            if ref_count <= 0:
                self.owner_source_status_label.setText(f"主图 graph_id={gid}：未在当前项目找到挂载引用（保持手动）。")
                self.owner_source_combo.setEnabled(True)
                self.owner_source_combo.setCurrentIndex(0)
                return

            self.owner_source_status_label.setText(f"主图 graph_id={gid}：找到 {ref_count} 条挂载引用，可用于推断 owner。")
            self.owner_source_combo.setEnabled(True)

            preferred_i = pick_preferred_candidate_index(candidates)
            preferred_combo_index = 1 + int(preferred_i)

            current_owner = str(self.owner_entity_edit.text() or "").strip()
            allow_autofill = (
                (not self._owner_manually_modified)
                and (not current_owner or current_owner == "自身实体" or current_owner == self._owner_last_autofill_value)
            )
            if allow_autofill:
                self.owner_source_combo.setCurrentIndex(int(preferred_combo_index))
                chosen_data = self.owner_source_combo.itemData(int(preferred_combo_index))
                owner_name = str(chosen_data.get("owner_name") if isinstance(chosen_data, dict) else "").strip()
                if owner_name:
                    self.owner_entity_edit.setText(owner_name)
                    self._owner_last_autofill_value = owner_name
                    self._owner_manually_modified = False
            else:
                self.owner_source_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------ summary

    def _update_run_summary(self) -> None:
        if not hasattr(self, "run_summary_label"):
            return

        graph_files = self._get_current_graph_files()
        ui_file = self._get_current_ui_html_file()

        owner = str(self.owner_entity_edit.text() if hasattr(self, "owner_entity_edit") else "").strip() or "自身实体"
        graph_text = f"节点图：已选 {len(graph_files)} 个（统一挂载到 owner={owner}）" if graph_files else "节点图：未选择"
        ui_text = f"入口页面：{ui_file.name}" if ui_file is not None else "入口页面：未选择"

        entry = self._get_current_entry_graph_file(graph_files)
        entry_hint = f"\n主图：{entry.name}" if entry is not None else ""

        self.run_summary_label.setText(f"{graph_text}\n{ui_text}{entry_hint}")

    # ------------------------------------------------------------------ external API

    def set_active_package_id(self, package_id: str | None) -> None:
        """切换对话框的“当前项目”作用域，并重建左侧选择面板。"""
        pkg = str(package_id or "").strip()
        if pkg == "global_view":
            pkg = ""
        new_pkg = pkg or None
        if new_pkg == self.active_package_id:
            return

        self._stop_server()
        self.url_edit.setText("")

        self.active_package_id = new_pkg
        self._entry_graph_path = None
        self._entry_graph_id = ""
        self._owner_manually_modified = False
        self._owner_last_autofill_value = ""

        self._fallback_graph_files = []
        self._fallback_ui_html_file = None
        self._fallback_entry_graph_file = None

        self._export_style_picker = None
        self._export_style_entry_combo = None
        self._export_style_ui_combo = None
        self._export_style_status_label = None

        # rebuild tabs
        for i in range(int(self.tabs.count())):
            w = self.tabs.widget(i)
            if w is not None:
                w.deleteLater()
        self.tabs.clear()
        self._build_select_tab()
        tab_bar = self.tabs.tabBar()
        if tab_bar is not None:
            tab_bar.hide()

        self._populate_owner_source_combo(graph_id="", candidates=[])
        self._update_run_summary()

