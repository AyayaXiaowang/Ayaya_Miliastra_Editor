"""节点图 + UI 本地测试对话框（浏览器预览）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from PyQt6 import QtCore, QtGui, QtWidgets

from app.runtime.services.local_graph_sim_mount_catalog import (
    LocalGraphSimResourceMountSpec,
    list_mount_resources_for_package,
)
from app.runtime.services.local_graph_sim_server import (
    LocalGraphSimServer,
    LocalGraphSimServerConfig,
    get_preferred_local_sim_http_port,
)
from app.runtime.services.local_graph_simulator import GraphMountSpec
from app.ui.foundation import dialog_utils
from app.ui.foundation.base_widgets import BaseDialog
from app.ui.foundation.theme_manager import ThemeManager
from engine.configs.resource_types import ResourceType
from engine.resources.graph_reference_service import iter_references_from_package_index

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
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager

        self._server: LocalGraphSimServer | None = None
        self._package_root: Path | None = None
        self._graph_root: Path | None = None
        self._ui_root: Path | None = None

        self._entry_graph_path: Path | None = None
        self._entry_graph_id: str = ""

        # 节点图选择（左侧目录树 + 右侧总览）
        self._checked_graph_keys: set[str] = set()
        self._graph_files_by_dir_rel: dict[str, list[Path]] = {}
        self._graph_dir_item_by_rel: dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._selected_graph_dir_rel: str = ""
        self._graph_dir_syncing: bool = False

        # owner 推断（入口图引用 -> owner 实体名）
        self._owner_source_syncing: bool = False
        self._owner_manually_modified: bool = False
        self._owner_last_autofill_value: str = ""

        # 入口图引用缓存（按 package + 资源库指纹失效）
        self._ref_index_ready: bool = False
        self._ref_index_package_id: str = ""
        self._ref_index_fingerprint: str = ""
        self._ref_index_graph_to_refs: dict[str, list[tuple[str, str, str, str]]] = {}
        self._ref_index_level_entity_id: str = ""
        self._ref_index_level_entity_name: str = "关卡实体"

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
        self._refresh_project_roots()
        self._refresh_graph_list()
        self._refresh_ui_list()
        self._update_run_summary()

    # ------------------------------------------------------------------ styles

    def _apply_styles(self) -> None:
        self.setStyleSheet(ThemeManager.dialog_surface_style())

    # ------------------------------------------------------------------ ui

    def _build_content(self) -> None:
        layout = self.content_layout

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ----------------------------- left: selections (tabs)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        self.tabs = QtWidgets.QTabWidget()
        left_layout.addWidget(self.tabs, 1)

        self._build_quick_select_tab()
        self._build_mount_tab()

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

        # owner 推断：入口图引用 -> owner（仅当前项目存档范围）
        self.owner_source_combo = QtWidgets.QComboBox()
        self.owner_source_combo.setToolTip("从入口图的引用资源推断 owner（仅当前项目）。")
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

    def _build_quick_select_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        graph_group = QtWidgets.QGroupBox("节点图（当前项目，可多选）")
        graph_layout = QtWidgets.QVBoxLayout(graph_group)
        graph_layout.setContentsMargins(10, 10, 10, 10)
        graph_layout.setSpacing(8)

        graph_tools = QtWidgets.QHBoxLayout()
        graph_layout.addLayout(graph_tools)

        self.graph_filter_edit = QtWidgets.QLineEdit()
        self.graph_filter_edit.setPlaceholderText("过滤节点图：输入关键词（支持路径/文件名）")
        self.graph_filter_edit.textChanged.connect(self._apply_graph_filter)
        graph_tools.addWidget(self.graph_filter_edit, 1)

        self.graph_type_combo = QtWidgets.QComboBox()
        self.graph_type_combo.addItem("全部", "all")
        self.graph_type_combo.addItem("仅 server", "server")
        self.graph_type_combo.addItem("仅 client", "client")
        self.graph_type_combo.currentIndexChanged.connect(self._apply_graph_filter)
        graph_tools.addWidget(self.graph_type_combo)

        self.refresh_graphs_btn = QtWidgets.QPushButton("刷新")
        self.refresh_graphs_btn.clicked.connect(self._refresh_graph_list)
        graph_tools.addWidget(self.refresh_graphs_btn)

        open_graph_dir_btn = QtWidgets.QPushButton("打开目录")
        open_graph_dir_btn.clicked.connect(self._open_graph_root_dir)
        graph_tools.addWidget(open_graph_dir_btn)

        check_all_btn = QtWidgets.QPushButton("全选")
        check_all_btn.clicked.connect(self._check_all_graphs)
        graph_tools.addWidget(check_all_btn)

        uncheck_all_btn = QtWidgets.QPushButton("全不选")
        uncheck_all_btn.clicked.connect(self._uncheck_all_graphs)
        graph_tools.addWidget(uncheck_all_btn)

        set_entry_btn = QtWidgets.QPushButton("设为入口")
        set_entry_btn.clicked.connect(self._set_entry_from_current_row)
        graph_tools.addWidget(set_entry_btn)

        owner_hint = QtWidgets.QLabel(
            "提示：这里勾选的节点图会统一挂载到右侧 owner 实体；"
            "如果需要把某些图挂到其它实体，请在“元件/实体挂载（可选）”里选择对应资源。"
        )
        owner_hint.setWordWrap(True)
        owner_hint.setStyleSheet(ThemeManager.subtle_info_style())
        graph_layout.addWidget(owner_hint)

        browser_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        browser_split.setChildrenCollapsible(False)
        graph_layout.addWidget(browser_split, 1)

        self.graph_dir_tree = QtWidgets.QTreeWidget()
        self.graph_dir_tree.setHeaderHidden(True)
        self.graph_dir_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.graph_dir_tree.setMinimumWidth(240)
        self.graph_dir_tree.itemSelectionChanged.connect(self._on_graph_dir_selection_changed)
        browser_split.addWidget(self.graph_dir_tree)

        self.graph_table = QtWidgets.QTableWidget()
        self.graph_table.setColumnCount(3)
        self.graph_table.setHorizontalHeaderLabels(["运行", "入口", "节点图"])
        self.graph_table.setRowCount(0)
        self.graph_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.graph_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.graph_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.graph_table.verticalHeader().setVisible(False)
        header = self.graph_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.graph_table.setMinimumHeight(260)
        self.graph_table.itemChanged.connect(self._on_graph_table_item_changed)
        self.graph_table.cellDoubleClicked.connect(self._on_graph_table_double_clicked)
        browser_split.addWidget(self.graph_table)
        browser_split.setStretchFactor(0, 1)
        browser_split.setStretchFactor(1, 3)

        self.entry_graph_label = QtWidgets.QLabel("入口图：未设置（启动时会取第一个勾选的节点图）")
        self.entry_graph_label.setStyleSheet(ThemeManager.subtle_info_style())
        graph_layout.addWidget(self.entry_graph_label)

        ui_group = QtWidgets.QGroupBox("UI HTML（当前项目，单选）")
        ui_layout = QtWidgets.QVBoxLayout(ui_group)
        ui_layout.setContentsMargins(10, 10, 10, 10)
        ui_layout.setSpacing(8)

        ui_tools = QtWidgets.QHBoxLayout()
        ui_layout.addLayout(ui_tools)

        self.ui_filter_edit = QtWidgets.QLineEdit()
        self.ui_filter_edit.setPlaceholderText("过滤 UI HTML：输入关键词（支持路径/文件名）")
        self.ui_filter_edit.textChanged.connect(self._apply_ui_filter)
        ui_tools.addWidget(self.ui_filter_edit, 1)

        self.refresh_ui_btn = QtWidgets.QPushButton("刷新")
        self.refresh_ui_btn.clicked.connect(self._refresh_ui_list)
        ui_tools.addWidget(self.refresh_ui_btn)

        open_ui_dir_btn = QtWidgets.QPushButton("打开目录")
        open_ui_dir_btn.clicked.connect(self._open_ui_root_dir)
        ui_tools.addWidget(open_ui_dir_btn)

        self.ui_table = QtWidgets.QTableWidget()
        self.ui_table.setColumnCount(1)
        self.ui_table.setHorizontalHeaderLabels(["UI HTML"])
        self.ui_table.setRowCount(0)
        self.ui_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ui_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.ui_table.verticalHeader().setVisible(False)
        ui_header = self.ui_table.horizontalHeader()
        if ui_header is not None:
            ui_header.setStretchLastSection(True)
            ui_header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.ui_table.setMinimumHeight(160)
        self.ui_table.itemSelectionChanged.connect(self._on_ui_selection_changed)
        ui_layout.addWidget(self.ui_table, 1)

        self.selected_ui_label = QtWidgets.QLabel("已选 UI：未选择")
        self.selected_ui_label.setStyleSheet(ThemeManager.subtle_info_style())
        ui_layout.addWidget(self.selected_ui_label)

        quick_split = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        quick_split.addWidget(graph_group)
        quick_split.addWidget(ui_group)
        quick_split.setStretchFactor(0, 3)
        quick_split.setStretchFactor(1, 2)
        layout.addWidget(quick_split, 1)

        self.tabs.addTab(tab, "选择节点图与 UI")

    def _build_mount_tab(self) -> None:
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        mount_tip = QtWidgets.QLabel(
            "说明：扫描当前项目存档的『元件模板/实体摆放/关卡实体』，把其挂载的节点图一并加入模拟，"
            "并将『自定义变量』组件的默认值（以及实例 override_variables）预先写入到对应实体上。"
        )
        mount_tip.setWordWrap(True)
        mount_tip.setStyleSheet(ThemeManager.subtle_info_style())
        layout.addWidget(mount_tip)

        mount_tools = QtWidgets.QHBoxLayout()
        layout.addLayout(mount_tools)

        self.mount_include_template_graphs_checkbox = QtWidgets.QCheckBox("实例同时挂载模板默认节点图（default_graphs）")
        self.mount_include_template_graphs_checkbox.setChecked(True)
        mount_tools.addWidget(self.mount_include_template_graphs_checkbox)

        self.scan_mounts_btn = QtWidgets.QPushButton("扫描挂载…")
        self.scan_mounts_btn.clicked.connect(self._scan_mount_resources)
        mount_tools.addWidget(self.scan_mounts_btn)

        clear_mounts_btn = QtWidgets.QPushButton("清空勾选")
        clear_mounts_btn.clicked.connect(self._clear_mount_resource_checks)
        mount_tools.addWidget(clear_mounts_btn)

        mount_tools.addStretch(1)

        self.mount_table = QtWidgets.QTableWidget()
        self.mount_table.setColumnCount(6)
        self.mount_table.setHorizontalHeaderLabels(["运行", "类型", "名称", "owner实体名", "挂载节点图", "自定义变量"])
        self.mount_table.setRowCount(0)
        self.mount_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.mount_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.mount_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked
            | QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
            | QtWidgets.QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.mount_table.verticalHeader().setVisible(False)
        header = self.mount_table.horizontalHeader()
        if header is not None:
            header.setStretchLastSection(True)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.mount_table.setMinimumHeight(260)
        layout.addWidget(self.mount_table, 1)

        self.tabs.addTab(tab, "元件/实体挂载（可选）")

    # ------------------------------------------------------------------ lifecycle

    def reject(self) -> None:
        self._stop_server()
        super().reject()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._stop_server()
        super().closeEvent(event)

    # ------------------------------------------------------------------ start/stop

    def _on_start_clicked(self) -> None:
        main_graph_path, extra_mounts, error = self._collect_graph_mounts_from_table()
        if error:
            dialog_utils.show_warning_dialog(self, "节点图选择错误", error)
            return

        html_path, error = self._collect_ui_html_from_table()
        if error:
            dialog_utils.show_warning_dialog(self, "UI 选择错误", error)
            return

        if not main_graph_path.is_file():
            dialog_utils.show_warning_dialog(self, "节点图文件不存在", str(main_graph_path))
            return
        if not html_path.is_file():
            dialog_utils.show_warning_dialog(self, "UI HTML 不存在", str(html_path))
            return

        owner_name = self.owner_entity_edit.text().strip() or "自身实体"
        player_name = self.player_entity_edit.text().strip() or "玩家1"
        present_players = int(self.present_players_spin.value() or 1)
        port = int(self.port_spin.value() or 0)

        resource_mounts, error = self._collect_resource_mount_specs()
        if error:
            dialog_utils.show_warning_dialog(self, "元件/实体挂载配置错误", error)
            return

        auto_signal_id = ""
        auto_params: dict[str, Any] = {}
        if bool(self.auto_signal_checkbox.isChecked()):
            auto_signal_id = self.auto_signal_id_edit.text().strip()
            params, error = self._parse_kv_lines(self.auto_params_edit.toPlainText())
            if error:
                dialog_utils.show_warning_dialog(self, "参数格式错误", error)
                return
            auto_params = params

        # 重启 server（避免端口冲突与状态污染）
        self._stop_server()

        cfg = LocalGraphSimServerConfig(
            workspace_root=self.workspace_root,
            graph_code_file=Path(main_graph_path).resolve(),
            ui_html_file=Path(html_path).resolve(),
            owner_entity_name=owner_name,
            player_entity_name=player_name,
            present_player_count=present_players,
            host="127.0.0.1",
            port=port,
            auto_emit_signal_id=auto_signal_id,
            auto_emit_signal_params=auto_params,
            extra_graph_mounts=list(extra_mounts or []),
            resource_mounts=list(resource_mounts or []),
        )
        server = LocalGraphSimServer(cfg)
        server.start()
        self._server = server

        url = server.get_url()
        self.url_edit.setText(url)
        self.stop_btn.setEnabled(True)
        self.open_browser_btn.setEnabled(True)

        # 默认自动打开浏览器（用户操作入口）
        self._open_browser()

    def _on_stop_clicked(self) -> None:
        self._stop_server()

    def _open_browser(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

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
        # 用户手动修改 owner 后，不再自动覆盖，除非用户显式从下拉中选择引用项
        self._owner_manually_modified = True
        self._owner_last_autofill_value = ""

    def _on_owner_source_combo_changed(self, index: int) -> None:
        if self._owner_source_syncing:
            return
        data = self.owner_source_combo.itemData(int(index))
        if not isinstance(data, dict):
            return
        if data.get("kind") != "ref":
            return
        owner_name = str(data.get("owner_name") or "").strip()
        if not owner_name:
            return
        self._owner_source_syncing = True
        self.owner_entity_edit.setText(owner_name)
        self._owner_source_syncing = False
        self._owner_manually_modified = False
        self._owner_last_autofill_value = owner_name

    def _on_refresh_owner_sources_clicked(self) -> None:
        self._refresh_owner_sources_for_entry_graph(force_rebuild=True)

    def _parse_graph_id_from_source_file(self, graph_code_file: Path) -> str:
        path = Path(graph_code_file).resolve()
        if not path.is_file():
            return ""

        # 仅扫描前若干行足够（避免大型图文件反复全量读取）
        lines: list[str] = []
        with path.open("r", encoding="utf-8-sig") as f:
            for _ in range(220):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
        head = "".join(lines)

        match = re.search(r"^graph_id:\s*(.+?)\s*$", head, flags=re.MULTILINE)
        return str(match.group(1)).strip() if match else ""

    def _ensure_owner_reference_index(self, *, force_rebuild: bool) -> None:
        """构建当前项目存档的 graph_id -> 引用资源反向索引（按资源库指纹失效）。"""
        pkg = str(self.active_package_id or "").strip()
        if not pkg:
            self._ref_index_ready = False
            self._ref_index_package_id = ""
            self._ref_index_fingerprint = ""
            self._ref_index_graph_to_refs = {}
            self._ref_index_level_entity_id = ""
            self._ref_index_level_entity_name = "关卡实体"
            return

        rm = getattr(self, "resource_manager", None)
        pim = getattr(self, "package_index_manager", None)
        if rm is None or pim is None:
            self._ref_index_ready = False
            self._ref_index_package_id = ""
            self._ref_index_fingerprint = ""
            self._ref_index_graph_to_refs = {}
            self._ref_index_level_entity_id = ""
            self._ref_index_level_entity_name = "关卡实体"
            return

        fingerprint = str(rm.get_resource_library_fingerprint() or "").strip()
        if (
            (not force_rebuild)
            and self._ref_index_ready
            and self._ref_index_package_id == pkg
            and self._ref_index_fingerprint == fingerprint
        ):
            return

        package_index = pim.load_package_index(pkg, refresh_resource_names=False)
        if package_index is None:
            self._ref_index_ready = True
            self._ref_index_package_id = pkg
            self._ref_index_fingerprint = fingerprint
            self._ref_index_graph_to_refs = {}
            self._ref_index_level_entity_id = ""
            self._ref_index_level_entity_name = "关卡实体"
            return

        level_entity_id = str(getattr(package_index, "level_entity_id", "") or "").strip()
        level_entity_name = "关卡实体"
        if level_entity_id:
            payload = rm.load_resource(ResourceType.INSTANCE, level_entity_id, copy_mode="none")
            if isinstance(payload, dict):
                name = str(payload.get("name") or "").strip()
                if name:
                    level_entity_name = name

        graph_to_refs: dict[str, list[tuple[str, str, str, str]]] = {}
        for ref in iter_references_from_package_index(
            package_id=pkg,
            package_index=package_index,
            resource_manager=rm,
            include_combat_presets=False,
            include_skill_ugc_indirect=False,
        ):
            graph_to_refs.setdefault(ref.graph_id, []).append(
                (ref.reference_type, ref.reference_id, ref.reference_name, ref.package_id)
            )

        self._ref_index_ready = True
        self._ref_index_package_id = pkg
        self._ref_index_fingerprint = fingerprint
        self._ref_index_graph_to_refs = graph_to_refs
        self._ref_index_level_entity_id = level_entity_id
        self._ref_index_level_entity_name = level_entity_name

    def _list_owner_candidates_for_graph_id(self, graph_id: str) -> list[dict[str, str]]:
        pkg = str(self.active_package_id or "").strip()
        gid = str(graph_id or "").strip()
        if not pkg or not gid:
            return []

        refs = list(self._ref_index_graph_to_refs.get(gid, []) or [])
        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        level_entity_id = str(self._ref_index_level_entity_id or "").strip()
        level_entity_name = str(self._ref_index_level_entity_name or "关卡实体").strip() or "关卡实体"

        for rtype, rid, rname, rpackage in refs:
            if str(rpackage or "").strip() != pkg:
                continue
            kind = str(rtype or "").strip()
            if kind == "level_entity":
                if not level_entity_id:
                    continue
                key = ("level_entity", level_entity_id)
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    {
                        "entity_type": "level_entity",
                        "entity_id": level_entity_id,
                        "entity_name": level_entity_name,
                        "owner_name": level_entity_name,
                        "display_type": "关卡实体",
                        "priority": "0",
                    }
                )
                continue
            if kind == "instance":
                entity_id = str(rid or "").strip()
                if not entity_id:
                    continue
                key = ("instance", entity_id)
                if key in seen:
                    continue
                seen.add(key)
                name = str(rname or entity_id).strip() or entity_id
                out.append(
                    {
                        "entity_type": "instance",
                        "entity_id": entity_id,
                        "entity_name": name,
                        "owner_name": name,
                        "display_type": "实体摆放",
                        "priority": "1",
                    }
                )
                continue
            if kind == "template":
                entity_id = str(rid or "").strip()
                if not entity_id:
                    continue
                key = ("template", entity_id)
                if key in seen:
                    continue
                seen.add(key)
                name = str(rname or entity_id).strip() or entity_id
                out.append(
                    {
                        "entity_type": "template",
                        "entity_id": entity_id,
                        "entity_name": name,
                        "owner_name": name,
                        "display_type": "元件模板",
                        "priority": "2",
                    }
                )
                continue

        out.sort(key=lambda x: (int(x.get("priority", "9") or "9"), str(x.get("entity_name", "")).casefold()))
        return out

    def _refresh_owner_sources_for_entry_graph(self, *, force_rebuild: bool) -> None:
        entry_path = self._entry_graph_path
        if entry_path is None or (not Path(entry_path).is_file()):
            self._entry_graph_id = ""
            self._populate_owner_source_combo(graph_id="", candidates=[])
            self.owner_source_status_label.setText("未选择入口图，无法推断 owner。")
            self.owner_source_combo.setEnabled(False)
            return

        gid = self._parse_graph_id_from_source_file(Path(entry_path))
        self._entry_graph_id = gid
        if not gid:
            self._populate_owner_source_combo(graph_id="", candidates=[])
            return

        rm = getattr(self, "resource_manager", None)
        pim = getattr(self, "package_index_manager", None)
        if rm is None or pim is None:
            self._populate_owner_source_combo(graph_id=gid, candidates=[])
            self.owner_source_status_label.setText(
                f"入口图 graph_id={gid}：未注入资源管理器，无法推断 owner（保持手动）。"
            )
            return

        self._ensure_owner_reference_index(force_rebuild=bool(force_rebuild))
        candidates = self._list_owner_candidates_for_graph_id(gid)
        self._populate_owner_source_combo(graph_id=gid, candidates=candidates)

    def _populate_owner_source_combo(self, *, graph_id: str, candidates: list[dict[str, str]]) -> None:
        gid = str(graph_id or "").strip()
        pkg = str(self.active_package_id or "").strip()

        self._owner_source_syncing = True
        self.owner_source_combo.clear()
        self.owner_source_combo.addItem("手动（使用 owner 输入框）", {"kind": "manual"})

        if not pkg:
            self.owner_source_status_label.setText("未打开项目存档，无法推断 owner。")
            self.owner_source_combo.setEnabled(False)
            self._owner_source_syncing = False
            return

        if not gid:
            self.owner_source_status_label.setText("入口图未声明 graph_id，无法推断 owner（保持手动）。")
            self.owner_source_combo.setEnabled(True)
            self.owner_source_combo.setCurrentIndex(0)
            self._owner_source_syncing = False
            return

        for c in list(candidates or []):
            owner_name = str(c.get("owner_name") or "").strip()
            display_type = str(c.get("display_type") or "").strip()
            entity_name = str(c.get("entity_name") or "").strip()
            if not owner_name:
                continue
            label = f"{display_type}：{entity_name}"
            self.owner_source_combo.addItem(label, {"kind": "ref", "owner_name": owner_name, **c})

        ref_count = max(0, self.owner_source_combo.count() - 1)
        if ref_count <= 0:
            self.owner_source_status_label.setText(f"入口图 graph_id={gid}：未在当前项目找到挂载引用（保持手动）。")
            self.owner_source_combo.setEnabled(True)
            self.owner_source_combo.setCurrentIndex(0)
            self._owner_source_syncing = False
            return

        self.owner_source_status_label.setText(f"入口图 graph_id={gid}：找到 {ref_count} 条挂载引用，可用于推断 owner。")
        self.owner_source_combo.setEnabled(True)

        # 自动选择策略：优先关卡实体，其次实体摆放，再次元件模板
        preferred_index = 1
        preferred_priority = 99
        for i in range(1, int(self.owner_source_combo.count())):
            data = self.owner_source_combo.itemData(i)
            if not isinstance(data, dict):
                continue
            priority_text = str(data.get("priority") or "").strip()
            if not priority_text.isdigit():
                continue
            pr = int(priority_text)
            if pr < preferred_priority:
                preferred_priority = pr
                preferred_index = i

        current_owner = str(self.owner_entity_edit.text() or "").strip()
        allow_autofill = (
            (not self._owner_manually_modified)
            and (not current_owner or current_owner == "自身实体" or current_owner == self._owner_last_autofill_value)
        )
        if allow_autofill:
            self.owner_source_combo.setCurrentIndex(int(preferred_index))
            chosen_data = self.owner_source_combo.itemData(int(preferred_index))
            owner_name = str(chosen_data.get("owner_name") if isinstance(chosen_data, dict) else "").strip()
            if owner_name:
                self.owner_entity_edit.setText(owner_name)
                self._owner_last_autofill_value = owner_name
                self._owner_manually_modified = False
        else:
            self.owner_source_combo.setCurrentIndex(0)

        self._owner_source_syncing = False

    # ------------------------------------------------------------------ selection: graphs

    def set_active_package_id(self, package_id: str | None) -> None:
        """切换对话框的“当前项目”作用域，并刷新可选列表。"""
        pkg = str(package_id or "").strip()
        if pkg == "global_view":
            pkg = ""
        new_pkg = pkg or None
        if new_pkg == self.active_package_id:
            return

        # 切换作用域时：停止旧会话，避免用户误以为仍在跑“当前项目”的配置。
        self._stop_server()
        self.url_edit.setText("")

        self.active_package_id = new_pkg
        self._entry_graph_path = None
        self._entry_graph_id = ""
        self._checked_graph_keys = set()
        self._graph_files_by_dir_rel = {}
        self._graph_dir_item_by_rel = {}
        self._selected_graph_dir_rel = ""
        self._owner_manually_modified = False
        self._owner_last_autofill_value = ""
        self._ref_index_ready = False
        self._ref_index_package_id = ""
        self._ref_index_fingerprint = ""
        self._ref_index_graph_to_refs = {}
        self._ref_index_level_entity_id = ""
        self._ref_index_level_entity_name = "关卡实体"
        self._refresh_project_roots()
        self._refresh_graph_list()
        self._refresh_ui_list()

        # 挂载扫描结果属于项目存档上下文，切换后清空更安全
        self.mount_table.setRowCount(0)
        self._populate_owner_source_combo(graph_id="", candidates=[])
        self._update_run_summary()

    def _refresh_project_roots(self) -> None:
        pkg = str(self.active_package_id or "").strip()
        if not pkg:
            self._package_root = None
            self._graph_root = None
            self._ui_root = None
            return

        package_root = (self.workspace_root / "assets" / "资源库" / "项目存档" / pkg).resolve()
        self._package_root = package_root
        self._graph_root = (package_root / "节点图").resolve()
        self._ui_root = (package_root / "管理配置" / "UI源码").resolve()

    def _scan_graph_files(self) -> list[Path]:
        root = self._graph_root
        if root is None or not root.is_dir():
            return []
        out: list[Path] = []
        for p in root.rglob("*.py"):
            if not p.is_file():
                continue
            if p.name == "__init__.py":
                continue
            if p.name == "校验节点图.py":
                continue
            out.append(p.resolve())
        out.sort(key=lambda x: x.as_posix().casefold())
        return out

    def _refresh_graph_list(self) -> None:
        files = self._scan_graph_files()
        root = self._graph_root

        existing_keys = {p.as_posix() for p in files}
        self._checked_graph_keys.intersection_update(existing_keys)
        if self._entry_graph_path is not None and self._entry_graph_path.as_posix() not in existing_keys:
            self._entry_graph_path = None

        self._build_graph_dir_tree(files=files, root=root)
        self._ensure_entry_graph_valid()
        self._refresh_graph_file_table()
        self._apply_graph_filter()

    def _get_selected_graph_dir_rel(self) -> str:
        if not hasattr(self, "graph_dir_tree"):
            return ""
        items = list(self.graph_dir_tree.selectedItems() or [])
        if not items:
            return ""
        item = items[0]
        key = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        return str(key) if isinstance(key, str) else ""

    def _on_graph_dir_selection_changed(self) -> None:
        if self._graph_dir_syncing:
            return
        self._selected_graph_dir_rel = self._get_selected_graph_dir_rel()
        self._refresh_graph_file_table()
        self._apply_graph_filter()

    def _build_graph_dir_tree(self, *, files: list[Path], root: Path | None) -> None:
        if not hasattr(self, "graph_dir_tree"):
            return

        want_dir = str(self._selected_graph_dir_rel or "").strip()

        self._graph_files_by_dir_rel = {}
        self._graph_dir_item_by_rel = {}

        self._graph_dir_syncing = True
        self.graph_dir_tree.clear()

        root_item = QtWidgets.QTreeWidgetItem(["全部"])
        root_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, "")
        self.graph_dir_tree.addTopLevelItem(root_item)
        self._graph_dir_item_by_rel[""] = root_item

        for p in list(files or []):
            rel_path = p.relative_to(root).as_posix() if (root is not None and p.is_relative_to(root)) else p.name
            parts = [x for x in str(rel_path).split("/") if x]
            dir_parts = parts[:-1]

            dir_rel = "/".join(dir_parts)
            self._graph_files_by_dir_rel.setdefault(dir_rel, []).append(p)

            parent = root_item
            cur_rel = ""
            for part in dir_parts:
                cur_rel = f"{cur_rel}/{part}" if cur_rel else part
                node = self._graph_dir_item_by_rel.get(cur_rel)
                if node is None:
                    node = QtWidgets.QTreeWidgetItem([part])
                    node.setData(0, QtCore.Qt.ItemDataRole.UserRole, cur_rel)
                    parent.addChild(node)
                    self._graph_dir_item_by_rel[cur_rel] = node
                parent = node

        def sort_children(item: QtWidgets.QTreeWidgetItem) -> None:
            item.sortChildren(0, QtCore.Qt.SortOrder.AscendingOrder)
            for i in range(int(item.childCount())):
                child = item.child(i)
                if child is not None:
                    sort_children(child)

        sort_children(root_item)
        self.graph_dir_tree.expandItem(root_item)

        if want_dir and want_dir not in self._graph_dir_item_by_rel:
            want_dir = ""
        item = self._graph_dir_item_by_rel.get(want_dir) or root_item
        self.graph_dir_tree.setCurrentItem(item)
        self._selected_graph_dir_rel = str(want_dir or "")
        self._graph_dir_syncing = False

    def _refresh_graph_file_table(self) -> None:
        if not hasattr(self, "graph_table"):
            return

        root = self._graph_root
        dir_rel = str(self._selected_graph_dir_rel or "").strip()
        files = list(self._graph_files_by_dir_rel.get(dir_rel, []) or [])

        def file_sort_key(p: Path) -> str:
            name = p.name
            if root is None:
                return name.casefold()
            rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()
            return str(rel).casefold()

        files.sort(key=file_sort_key)

        entry_key = self._entry_graph_path.as_posix() if self._entry_graph_path is not None else ""

        self.graph_table.blockSignals(True)
        self.graph_table.setRowCount(0)
        for p in files:
            row = int(self.graph_table.rowCount())
            self.graph_table.insertRow(row)

            path_key = p.as_posix()
            rel_path = p.relative_to(root).as_posix() if (root is not None and p.is_relative_to(root)) else p.name

            checked = path_key in self._checked_graph_keys

            run_item = QtWidgets.QTableWidgetItem("")
            run_item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsSelectable
            )
            run_item.setCheckState(QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked)
            run_item.setData(QtCore.Qt.ItemDataRole.UserRole, path_key)
            self.graph_table.setItem(row, 0, run_item)

            entry_item = QtWidgets.QTableWidgetItem("主" if (entry_key and path_key == entry_key) else "")
            entry_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            entry_item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self.graph_table.setItem(row, 1, entry_item)

            display = p.name
            if dir_rel and root is not None:
                base_dir = root / dir_rel
                display = p.relative_to(base_dir).as_posix() if p.is_relative_to(base_dir) else p.name
            path_item = QtWidgets.QTableWidgetItem(display)
            path_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            path_item.setToolTip(rel_path + "\n" + str(p))
            path_item.setData(QtCore.Qt.ItemDataRole.UserRole, rel_path)
            self.graph_table.setItem(row, 2, path_item)

        self.graph_table.blockSignals(False)

    def _apply_graph_filter(self) -> None:
        text = str(self.graph_filter_edit.text() if hasattr(self, "graph_filter_edit") else "").strip().casefold()
        kind = str(self.graph_type_combo.currentData() if hasattr(self, "graph_type_combo") else "all")

        for row in range(int(self.graph_table.rowCount())):
            item = self.graph_table.item(row, 2)
            rel = item.data(QtCore.Qt.ItemDataRole.UserRole) if item is not None else ""
            path_text = str(rel if isinstance(rel, str) else (item.text() if item is not None else "")).casefold()
            ok_kind = True
            if kind in {"server", "client"}:
                ok_kind = path_text.startswith(f"{kind}/") or path_text.startswith(f"{kind}\\")
            ok_text = True
            if text:
                ok_text = text in path_text
            self.graph_table.setRowHidden(row, not (ok_kind and ok_text))

    def _check_all_graphs(self) -> None:
        self.graph_table.blockSignals(True)
        for row in range(int(self.graph_table.rowCount())):
            if self.graph_table.isRowHidden(row):
                continue
            item = self.graph_table.item(row, 0)
            if item is None:
                continue
            item.setCheckState(QtCore.Qt.CheckState.Checked)
            path_key = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(path_key, str) and path_key:
                self._checked_graph_keys.add(path_key)
        self.graph_table.blockSignals(False)
        self._ensure_entry_graph_valid()

    def _uncheck_all_graphs(self) -> None:
        self._checked_graph_keys = set()
        self.graph_table.blockSignals(True)
        for row in range(int(self.graph_table.rowCount())):
            item = self.graph_table.item(row, 0)
            if item is None:
                continue
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)
        self.graph_table.blockSignals(False)
        self._set_entry_graph(None)

    def _on_graph_table_double_clicked(self, row: int, _col: int) -> None:
        self._set_entry_from_row(row)

    def _set_entry_from_current_row(self) -> None:
        row = int(self.graph_table.currentRow())
        if row < 0:
            dialog_utils.show_warning_dialog(self, "提示", "请先在列表中选中一个节点图。")
            return
        self._set_entry_from_row(row)

    def _set_entry_from_row(self, row: int) -> None:
        run_item = self.graph_table.item(int(row), 0)
        if run_item is None:
            return
        path_key = run_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(path_key, str) or not path_key:
            return
        self._set_entry_graph(Path(path_key))

    def _set_entry_graph(self, path: Path | None) -> None:
        prev_entry = self._entry_graph_path
        if path is None:
            self._entry_graph_path = None
        else:
            self._entry_graph_path = Path(path).resolve()

        # 入口图必须是“勾选运行”
        if self._entry_graph_path is not None:
            self._checked_graph_keys.add(self._entry_graph_path.as_posix())

        # 更新右侧总览：入口标记/勾选状态（可见范围），先屏蔽 table 信号，避免 itemChanged 递归触发
        entry_key = self._entry_graph_path.as_posix() if self._entry_graph_path is not None else ""
        self.graph_table.blockSignals(True)
        for row in range(int(self.graph_table.rowCount())):
            run_item = self.graph_table.item(row, 0)
            entry_item = self.graph_table.item(row, 1)
            if run_item is None or entry_item is None:
                continue
            path_key = run_item.data(QtCore.Qt.ItemDataRole.UserRole)
            is_entry = bool(entry_key and isinstance(path_key, str) and path_key == entry_key)
            entry_item.setText("主" if is_entry else "")
            if is_entry:
                run_item.setCheckState(QtCore.Qt.CheckState.Checked)
        self.graph_table.blockSignals(False)

        if self._entry_graph_path is None:
            self.entry_graph_label.setText("入口图：未设置（启动时会取第一个勾选的节点图）")
        else:
            display = str(self._entry_graph_path)
            root = self._graph_root
            if root is not None and self._entry_graph_path.is_relative_to(root):
                display = self._entry_graph_path.relative_to(root).as_posix()
            else:
                display = self._entry_graph_path.name
            self.entry_graph_label.setText(f"入口图：{display}（双击列表行可切换）")

        # 仅在入口图变化时刷新 owner 推断（避免勾选变化时频繁全量扫描引用）
        if (self._entry_graph_path != prev_entry) or (self._entry_graph_path is None):
            self._refresh_owner_sources_for_entry_graph(force_rebuild=False)

        self._update_run_summary()

    def _ensure_entry_graph_valid(self) -> None:
        checked = self._collect_checked_graph_paths()
        if not checked:
            self._set_entry_graph(None)
            return
        entry = self._entry_graph_path if self._entry_graph_path in checked else checked[0]
        # 即使 entry 未变化也需要刷新“入口”列标记与提示文本
        self._set_entry_graph(entry)

    def _collect_checked_graph_paths(self) -> list[Path]:
        keys = [str(x) for x in (self._checked_graph_keys or set()) if isinstance(x, str) and str(x).strip()]
        paths = [Path(k).resolve() for k in keys]
        root = self._graph_root

        def sort_key(p: Path) -> str:
            if root is not None:
                rel = p.relative_to(root).as_posix() if p.is_relative_to(root) else p.as_posix()
                return str(rel).casefold()
            return p.as_posix().casefold()

        paths.sort(key=sort_key)
        return paths

    def _on_graph_table_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if item is None:
            return

        col = int(item.column())

        # 勾选变化：确保入口图有效
        if col != 0:
            return
        path_key = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(path_key, str) and path_key:
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                self._checked_graph_keys.add(path_key)
            else:
                self._checked_graph_keys.discard(path_key)
        self._ensure_entry_graph_valid()

    def _collect_graph_mounts_from_table(self) -> tuple[Path, list[GraphMountSpec], str]:
        checked_paths = self._collect_checked_graph_paths()
        if not checked_paths:
            return Path("."), [], "请先在列表中勾选至少 1 个节点图。"

        entry = self._entry_graph_path if self._entry_graph_path in checked_paths else checked_paths[0]
        owner = self.owner_entity_edit.text().strip() or "自身实体"

        extra: list[GraphMountSpec] = []
        for p in checked_paths:
            if p == entry:
                continue
            extra.append(GraphMountSpec(graph_code_file=p, owner_entity_name=owner))
        return entry, extra, ""

    # ------------------------------------------------------------------ selection: UI

    def _scan_ui_html_files(self) -> list[Path]:
        root = self._ui_root
        if root is None or not root.is_dir():
            return []
        out: list[Path] = []
        for p in root.rglob("*.html"):
            if p.is_file():
                out.append(p.resolve())
        for p in root.rglob("*.htm"):
            if p.is_file():
                out.append(p.resolve())
        out.sort(key=lambda x: x.as_posix().casefold())
        return out

    def _refresh_ui_list(self) -> None:
        prev_selected = self._get_selected_ui_path_key()
        files = self._scan_ui_html_files()
        root = self._ui_root

        self.ui_table.setRowCount(0)
        for p in files:
            row = int(self.ui_table.rowCount())
            self.ui_table.insertRow(row)

            display = p.name
            if root is not None and p.is_relative_to(root):
                display = p.relative_to(root).as_posix()
            item = QtWidgets.QTableWidgetItem(display)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            item.setToolTip(str(p))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, p.as_posix())
            self.ui_table.setItem(row, 0, item)

        self._apply_ui_filter()

        # 恢复选中
        if prev_selected:
            for row in range(int(self.ui_table.rowCount())):
                item = self.ui_table.item(row, 0)
                if item is None:
                    continue
                key = item.data(QtCore.Qt.ItemDataRole.UserRole)
                if key == prev_selected:
                    self.ui_table.selectRow(row)
                    break

        self._on_ui_selection_changed()

    def _get_selected_ui_path_key(self) -> str:
        items = list(self.ui_table.selectedItems() or [])
        if not items:
            return ""
        key = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
        return str(key) if isinstance(key, str) else ""

    def _apply_ui_filter(self) -> None:
        text = str(self.ui_filter_edit.text() if hasattr(self, "ui_filter_edit") else "").strip().casefold()
        for row in range(int(self.ui_table.rowCount())):
            item = self.ui_table.item(row, 0)
            path_text = str(item.text() if item is not None else "").casefold()
            ok = True
            if text:
                ok = text in path_text
            self.ui_table.setRowHidden(row, not ok)

    def _on_ui_selection_changed(self) -> None:
        key = self._get_selected_ui_path_key()
        if not key:
            self.selected_ui_label.setText("已选 UI：未选择")
            self._update_run_summary()
            return

        display = key
        root = self._ui_root
        if root is not None:
            ui_path = Path(key).resolve()
            display = ui_path.relative_to(root).as_posix() if ui_path.is_relative_to(root) else ui_path.name
        self.selected_ui_label.setText(f"已选 UI：{display}")
        self._update_run_summary()

    def _collect_ui_html_from_table(self) -> tuple[Path, str]:
        key = self._get_selected_ui_path_key()
        if not key:
            return Path("."), "请先在列表中选择 1 个 UI HTML 文件。"
        return Path(key).resolve(), ""

    # ------------------------------------------------------------------ mount tab (resource mounts)

    def _scan_mount_resources(self) -> None:
        pkg = str(self.active_package_id or "").strip()
        if not pkg:
            dialog_utils.show_warning_dialog(self, "无法扫描挂载", "当前未打开项目存档，无法扫描元件/实体挂载。")
            return
        infos = list_mount_resources_for_package(workspace_root=self.workspace_root, package_id=pkg)
        self._populate_mount_table(infos)

    def _populate_mount_table(self, infos: list[Any]) -> None:
        self.mount_table.setRowCount(0)
        for info in list(infos or []):
            spec = getattr(info, "spec", None)
            if spec is None:
                continue
            resource_type = str(getattr(spec, "resource_type", "") or "").strip()
            resource_id = str(getattr(spec, "resource_id", "") or "").strip()
            if not resource_type or not resource_id:
                continue

            display_type = str(getattr(info, "display_type", "") or "").strip()
            resource_name = str(getattr(info, "resource_name", "") or resource_id).strip() or resource_id
            owner_name = str(getattr(spec, "owner_entity_name", "") or resource_name).strip() or resource_name

            graphs = list(getattr(info, "graphs", []) or [])
            graph_lines: list[str] = []
            graph_tooltip_lines: list[str] = []
            for g in graphs:
                gname = str(getattr(g, "graph_name", "") or getattr(g, "graph_id", "") or "").strip()
                gid = str(getattr(g, "graph_id", "") or "").strip()
                gtype = str(getattr(g, "graph_type", "") or "").strip()
                gfile = str(getattr(g, "graph_code_file", "") or "").strip()
                if gname and gid and gname != gid:
                    graph_lines.append(gname)
                else:
                    graph_lines.append(gid or gname)
                graph_tooltip_lines.append(f"- {gname or gid} ({gtype})")
                if gfile:
                    graph_tooltip_lines.append(f"  file: {gfile}")

            custom_var_names = list(getattr(info, "custom_variable_names", []) or [])
            custom_preview = ", ".join([str(x) for x in custom_var_names[:6]])
            if len(custom_var_names) > 6:
                custom_preview = custom_preview + "…"
            custom_text = f"{len(custom_var_names)} 个"
            if custom_preview:
                custom_text = f"{custom_text}（{custom_preview}）"

            row = int(self.mount_table.rowCount())
            self.mount_table.insertRow(row)

            run_item = QtWidgets.QTableWidgetItem("")
            run_item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsUserCheckable
                | QtCore.Qt.ItemFlag.ItemIsSelectable
            )
            run_item.setCheckState(QtCore.Qt.CheckState.Unchecked)
            run_item.setData(
                QtCore.Qt.ItemDataRole.UserRole,
                {"resource_type": resource_type, "resource_id": resource_id},
            )
            self.mount_table.setItem(row, 0, run_item)

            t_item = QtWidgets.QTableWidgetItem(display_type)
            t_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.mount_table.setItem(row, 1, t_item)

            name_item = QtWidgets.QTableWidgetItem(resource_name)
            name_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            self.mount_table.setItem(row, 2, name_item)

            owner_item = QtWidgets.QTableWidgetItem(owner_name)
            owner_item.setFlags(
                QtCore.Qt.ItemFlag.ItemIsEnabled
                | QtCore.Qt.ItemFlag.ItemIsSelectable
                | QtCore.Qt.ItemFlag.ItemIsEditable
            )
            self.mount_table.setItem(row, 3, owner_item)

            graphs_item = QtWidgets.QTableWidgetItem("\n".join(graph_lines))
            graphs_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            tooltip = "\n".join(graph_tooltip_lines).strip()
            if tooltip:
                graphs_item.setToolTip(tooltip)
            self.mount_table.setItem(row, 4, graphs_item)

            custom_item = QtWidgets.QTableWidgetItem(custom_text)
            custom_item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
            if custom_var_names:
                custom_item.setToolTip("\n".join([f"- {x}" for x in custom_var_names]))
            self.mount_table.setItem(row, 5, custom_item)

        self.mount_table.resizeRowsToContents()

    def _clear_mount_resource_checks(self) -> None:
        for row in range(int(self.mount_table.rowCount())):
            item = self.mount_table.item(row, 0)
            if item is None:
                continue
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def _collect_resource_mount_specs(self) -> tuple[list[LocalGraphSimResourceMountSpec], str]:
        include_template = bool(self.mount_include_template_graphs_checkbox.isChecked())
        specs: list[LocalGraphSimResourceMountSpec] = []
        for row in range(int(self.mount_table.rowCount())):
            run_item = self.mount_table.item(row, 0)
            if run_item is None:
                continue
            if run_item.checkState() != QtCore.Qt.CheckState.Checked:
                continue
            data = run_item.data(QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(data, dict):
                continue
            resource_type = str(data.get("resource_type") or "").strip()
            resource_id = str(data.get("resource_id") or "").strip()
            if not resource_type or not resource_id:
                continue
            owner_item = self.mount_table.item(row, 3)
            owner_name = str(owner_item.text() if owner_item is not None else "").strip()
            if not owner_name:
                return [], f"第 {row + 1} 行 owner实体名 为空"
            specs.append(
                LocalGraphSimResourceMountSpec(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    owner_entity_name=owner_name,
                    include_template_graphs=bool(include_template),
                )
            )
        return specs, ""

    # ------------------------------------------------------------------ misc helpers

    def _stop_server(self) -> None:
        server = self._server
        if server is None:
            return
        server.stop()
        self._server = None
        self.stop_btn.setEnabled(False)
        self.open_browser_btn.setEnabled(False)

    def _open_graph_root_dir(self) -> None:
        root = self._graph_root
        if root is None or not root.is_dir():
            dialog_utils.show_warning_dialog(self, "无法打开目录", "当前项目缺少『节点图』目录。")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(root)))

    def _open_ui_root_dir(self) -> None:
        root = self._ui_root
        if root is None or not root.is_dir():
            dialog_utils.show_warning_dialog(self, "无法打开目录", "当前项目缺少『管理配置/UI源码』目录。")
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(root)))

    def _update_run_summary(self) -> None:
        checked = self._collect_checked_graph_paths()
        ui_key = self._get_selected_ui_path_key()

        owner = str(self.owner_entity_edit.text() if hasattr(self, "owner_entity_edit") else "").strip() or "自身实体"
        graph_text = "节点图：未选择"
        if checked:
            entry = self._entry_graph_path if self._entry_graph_path in checked else checked[0]
            extra_count = max(0, len(checked) - 1)
            display = entry.name
            root = self._graph_root
            if root is not None:
                display = entry.relative_to(root).as_posix() if entry.is_relative_to(root) else entry.name
            graph_text = f"节点图：入口={display}，附加={extra_count} 个（统一挂载到 owner={owner}）"

        ui_text = "UI：未选择"
        if ui_key:
            ui_path = Path(ui_key).resolve()
            display2 = ui_path.name
            root2 = self._ui_root
            if root2 is not None:
                display2 = ui_path.relative_to(root2).as_posix() if ui_path.is_relative_to(root2) else ui_path.name
            ui_text = f"UI：{display2}"

        self.run_summary_label.setText(f"{graph_text}\n{ui_text}")

    def _parse_kv_lines(self, raw_text: str) -> tuple[dict[str, Any], str]:
        params: dict[str, Any] = {}
        for line_no, raw_line in enumerate(str(raw_text or "").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if "=" not in line:
                return {}, f"第 {line_no} 行不是 key=value：{raw_line!r}"
            key, value = line.split("=", 1)
            k = key.strip()
            v = value.strip()
            if not k:
                return {}, f"第 {line_no} 行 key 为空：{raw_line!r}"
            if v.lower() in {"true", "false"}:
                params[k] = v.lower() == "true"
                continue
            if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                params[k] = int(v)
                continue
            params[k] = v
        return params, ""

