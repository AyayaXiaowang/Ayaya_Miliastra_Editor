from __future__ import annotations

import atexit
import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from app.runtime.services.graph_data_service import (
    GraphDataService,
    GraphLoadPayload,
    get_shared_graph_data_service,
)
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.panels.graph.graph_async_loader import GraphAsyncLoader, get_shared_graph_loader
from app.ui.panels.panel_scaffold import PanelScaffold
from app.ui.panels.panel_search_support import SidebarSearchController
from engine.graph.common import (
    SIGNAL_LISTEN_NODE_TITLE,
    SIGNAL_NAME_PORT_NAME,
    SIGNAL_SEND_NODE_TITLE,
    STRUCT_NAME_PORT_NAME,
    STRUCT_NODE_TITLES,
    VARIABLE_NAME_PORT_NAME,
)
from engine.resources.definition_schema_view import get_default_definition_schema_view
from engine.resources.level_variable_schema_view import get_default_level_variable_schema_view
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from engine.signal import get_default_signal_repository
from engine.struct import get_default_struct_repository


_USED_DEFINITIONS_EXECUTOR = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="graph-used-definitions",
)
atexit.register(_USED_DEFINITIONS_EXECUTOR.shutdown, False)


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


@dataclass(frozen=True, slots=True)
class GraphNodeUsage:
    node_id: str
    node_title: str


@dataclass(frozen=True, slots=True)
class SignalUsageItem:
    key: str
    signal_id: str
    signal_name: str
    source_path: str
    parameters: List[Dict[str, Any]]
    send_nodes: List[GraphNodeUsage]
    listen_nodes: List[GraphNodeUsage]
    raw_payload: Optional[Dict[str, Any]]
    search_blob: str


@dataclass(frozen=True, slots=True)
class StructUsageItem:
    key: str
    struct_id: str
    struct_name: str
    struct_type: str
    source_path: str
    fields: List[Dict[str, Any]]
    usage_nodes: List[GraphNodeUsage]
    used_field_names: List[str]
    raw_payload: Optional[Dict[str, Any]]
    search_blob: str


@dataclass(frozen=True, slots=True)
class LevelVariableUsageItem:
    key: str
    variable_id: str
    variable_name: str
    variable_type: str
    default_value: object
    description: str
    source_path: str
    variable_file_id: str
    get_nodes: List[GraphNodeUsage]
    set_nodes: List[GraphNodeUsage]
    changed_nodes: List[GraphNodeUsage]
    other_nodes: List[GraphNodeUsage]
    raw_payload: Optional[Dict[str, Any]]
    search_blob: str


@dataclass(frozen=True, slots=True)
class GraphUsedDefinitionsSnapshot:
    signature: float
    graph_name: str
    signal_items: List[SignalUsageItem]
    struct_items: List[StructUsageItem]
    variable_items: List[LevelVariableUsageItem]


class GraphUsedDefinitionsPanel(PanelScaffold):
    """节点图库：查看当前节点图引用到的信号/结构体/自定义变量（只读）。"""

    _analysis_ready = QtCore.pyqtSignal(int, str, object)

    def __init__(
        self,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(
            parent,
            title="信号/结构体/变量",
            description="查看当前节点图引用到的信号、结构体定义与关卡变量（自定义变量）。仅供查看。",
        )
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager

        self.data_provider: GraphDataService = get_shared_graph_data_service(
            resource_manager, package_index_manager
        )
        self.graph_loader: GraphAsyncLoader = get_shared_graph_loader(self.data_provider)

        self.current_graph_id: Optional[str] = None
        self._current_search_text: str = ""

        self._signal_items: List[SignalUsageItem] = []
        self._signal_item_by_key: Dict[str, SignalUsageItem] = {}

        self._struct_items: List[StructUsageItem] = []
        self._struct_item_by_key: Dict[str, StructUsageItem] = {}

        self._variable_items: List[LevelVariableUsageItem] = []
        self._variable_item_by_key: Dict[str, LevelVariableUsageItem] = {}

        self._analysis_generation: int = 0
        self._active_analysis_future: Future | None = None
        self._usage_cache: Dict[str, GraphUsedDefinitionsSnapshot] = {}
        self._current_graph_name: str = ""
        self._analysis_ready.connect(self._apply_analysis_result)

        self._status_badge = self.create_status_badge(
            "GraphUsedDefinitionsStatusBadge",
            "未选中节点图",
        )
        self._build_ui()
        self.set_empty_state()

    # ------------------------------------------------------------------ UI

    def showEvent(self, event: QtGui.QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._ensure_loaded_for_current_graph()

    def _build_ui(self) -> None:
        self.search_controller = SidebarSearchController(
            placeholder="搜索：ID / 名称 / 参数 / 字段 / 说明",
            on_text_changed=self._on_search_text_changed,
            parent=self,
        )
        self.body_layout.addWidget(self.search_controller.widget)

        self.tab_widget = QtWidgets.QTabWidget(self)
        self.body_layout.addWidget(self.tab_widget, 1)

        self._build_signal_tab()
        self._build_struct_tab()
        self._build_variable_tab()

    def _build_signal_tab(self) -> None:
        tab = QtWidgets.QWidget(self.tab_widget)
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, tab)
        layout.addWidget(splitter, 1)

        self.signal_table = QtWidgets.QTableWidget(splitter)
        self.signal_table.setColumnCount(4)
        self.signal_table.setHorizontalHeaderLabels(["信号名", "signal_id", "发送", "监听"])
        self._setup_readonly_table(self.signal_table)
        self.signal_table.itemSelectionChanged.connect(self._on_signal_selection_changed)
        splitter.addWidget(self.signal_table)

        detail_root = QtWidgets.QWidget(splitter)
        detail_layout = QtWidgets.QVBoxLayout(detail_root)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(Sizes.SPACING_MEDIUM)

        form_widget = QtWidgets.QWidget(detail_root)
        form_layout = QtWidgets.QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)
        detail_layout.addWidget(form_widget)

        self.signal_name_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.signal_name_value)
        self.signal_id_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.signal_id_value)
        self.signal_source_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.signal_source_value)
        self.signal_usage_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.signal_usage_value)

        form_layout.addRow("信号名:", self.signal_name_value)
        form_layout.addRow("signal_id:", self.signal_id_value)
        form_layout.addRow("来源文件:", self.signal_source_value)
        form_layout.addRow("使用情况:", self.signal_usage_value)

        self.signal_detail_tabs = QtWidgets.QTabWidget(detail_root)
        detail_layout.addWidget(self.signal_detail_tabs, 1)

        params_tab = QtWidgets.QWidget(self.signal_detail_tabs)
        params_layout = QtWidgets.QVBoxLayout(params_tab)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(Sizes.SPACING_SMALL)
        self.signal_parameters_table = QtWidgets.QTableWidget(params_tab)
        self.signal_parameters_table.setColumnCount(3)
        self.signal_parameters_table.setHorizontalHeaderLabels(["参数名", "类型", "说明"])
        self._setup_readonly_table(self.signal_parameters_table)
        params_layout.addWidget(self.signal_parameters_table, 1)
        self.signal_detail_tabs.addTab(params_tab, "参数")

        usage_tab = QtWidgets.QWidget(self.signal_detail_tabs)
        usage_layout = QtWidgets.QVBoxLayout(usage_tab)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.setSpacing(Sizes.SPACING_SMALL)
        self.signal_usage_text = self._build_readonly_text_area(usage_tab)
        usage_layout.addWidget(self.signal_usage_text, 1)
        self.signal_detail_tabs.addTab(usage_tab, "使用位置")

        raw_tab = QtWidgets.QWidget(self.signal_detail_tabs)
        raw_layout = QtWidgets.QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(Sizes.SPACING_SMALL)
        self.signal_raw_text = self._build_readonly_text_area(raw_tab)
        raw_layout.addWidget(self.signal_raw_text, 1)
        self.signal_detail_tabs.addTab(raw_tab, "原始数据")

        splitter.addWidget(detail_root)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.tab_widget.addTab(tab, "信号")

    def _build_struct_tab(self) -> None:
        tab = QtWidgets.QWidget(self.tab_widget)
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, tab)
        layout.addWidget(splitter, 1)

        self.struct_table = QtWidgets.QTableWidget(splitter)
        self.struct_table.setColumnCount(4)
        self.struct_table.setHorizontalHeaderLabels(["结构体名", "struct_id", "字段(用到)", "节点"])
        self._setup_readonly_table(self.struct_table)
        self.struct_table.itemSelectionChanged.connect(self._on_struct_selection_changed)
        splitter.addWidget(self.struct_table)

        detail_root = QtWidgets.QWidget(splitter)
        detail_layout = QtWidgets.QVBoxLayout(detail_root)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(Sizes.SPACING_MEDIUM)

        form_widget = QtWidgets.QWidget(detail_root)
        form_layout = QtWidgets.QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)
        detail_layout.addWidget(form_widget)

        self.struct_name_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.struct_name_value)
        self.struct_id_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.struct_id_value)
        self.struct_type_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.struct_type_value)
        self.struct_source_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.struct_source_value)

        form_layout.addRow("结构体名:", self.struct_name_value)
        form_layout.addRow("struct_id:", self.struct_id_value)
        form_layout.addRow("类型:", self.struct_type_value)
        form_layout.addRow("来源文件:", self.struct_source_value)

        self.struct_detail_tabs = QtWidgets.QTabWidget(detail_root)
        detail_layout.addWidget(self.struct_detail_tabs, 1)

        fields_tab = QtWidgets.QWidget(self.struct_detail_tabs)
        fields_layout = QtWidgets.QVBoxLayout(fields_tab)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(Sizes.SPACING_SMALL)
        self.struct_fields_table = QtWidgets.QTableWidget(fields_tab)
        self.struct_fields_table.setColumnCount(4)
        self.struct_fields_table.setHorizontalHeaderLabels(["字段名", "类型", "默认值", "长度"])
        self._setup_readonly_table(self.struct_fields_table)
        fields_layout.addWidget(self.struct_fields_table, 1)
        self.struct_detail_tabs.addTab(fields_tab, "字段")

        usage_tab = QtWidgets.QWidget(self.struct_detail_tabs)
        usage_layout = QtWidgets.QVBoxLayout(usage_tab)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.setSpacing(Sizes.SPACING_SMALL)
        self.struct_usage_text = self._build_readonly_text_area(usage_tab)
        usage_layout.addWidget(self.struct_usage_text, 1)
        self.struct_detail_tabs.addTab(usage_tab, "使用位置")

        raw_tab = QtWidgets.QWidget(self.struct_detail_tabs)
        raw_layout = QtWidgets.QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(Sizes.SPACING_SMALL)
        self.struct_raw_text = self._build_readonly_text_area(raw_tab)
        raw_layout.addWidget(self.struct_raw_text, 1)
        self.struct_detail_tabs.addTab(raw_tab, "原始数据")

        splitter.addWidget(detail_root)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.tab_widget.addTab(tab, "结构体")

    def _build_variable_tab(self) -> None:
        tab = QtWidgets.QWidget(self.tab_widget)
        layout = QtWidgets.QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Sizes.SPACING_MEDIUM)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, tab)
        layout.addWidget(splitter, 1)

        self.variable_table = QtWidgets.QTableWidget(splitter)
        self.variable_table.setColumnCount(6)
        self.variable_table.setHorizontalHeaderLabels(
            ["变量名", "variable_id", "类型", "读", "写", "变化"]
        )
        self._setup_readonly_table(self.variable_table)
        self.variable_table.itemSelectionChanged.connect(self._on_variable_selection_changed)
        splitter.addWidget(self.variable_table)

        detail_root = QtWidgets.QWidget(splitter)
        detail_layout = QtWidgets.QVBoxLayout(detail_root)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(Sizes.SPACING_MEDIUM)

        form_widget = QtWidgets.QWidget(detail_root)
        form_layout = QtWidgets.QFormLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(Sizes.SPACING_MEDIUM)
        form_layout.setVerticalSpacing(Sizes.SPACING_SMALL)
        detail_layout.addWidget(form_widget)

        self.variable_name_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.variable_name_value)
        self.variable_id_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.variable_id_value)
        self.variable_type_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.variable_type_value)
        self.variable_source_value = QtWidgets.QLabel("-")
        self._configure_readonly_label(self.variable_source_value)

        form_layout.addRow("变量名:", self.variable_name_value)
        form_layout.addRow("variable_id:", self.variable_id_value)
        form_layout.addRow("类型:", self.variable_type_value)
        form_layout.addRow("来源文件:", self.variable_source_value)

        self.variable_detail_tabs = QtWidgets.QTabWidget(detail_root)
        detail_layout.addWidget(self.variable_detail_tabs, 1)

        definition_tab = QtWidgets.QWidget(self.variable_detail_tabs)
        definition_layout = QtWidgets.QVBoxLayout(definition_tab)
        definition_layout.setContentsMargins(0, 0, 0, 0)
        definition_layout.setSpacing(Sizes.SPACING_SMALL)
        self.variable_definition_text = self._build_readonly_text_area(definition_tab)
        definition_layout.addWidget(self.variable_definition_text, 1)
        self.variable_detail_tabs.addTab(definition_tab, "定义")

        usage_tab = QtWidgets.QWidget(self.variable_detail_tabs)
        usage_layout = QtWidgets.QVBoxLayout(usage_tab)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.setSpacing(Sizes.SPACING_SMALL)
        self.variable_usage_text = self._build_readonly_text_area(usage_tab)
        usage_layout.addWidget(self.variable_usage_text, 1)
        self.variable_detail_tabs.addTab(usage_tab, "使用位置")

        raw_tab = QtWidgets.QWidget(self.variable_detail_tabs)
        raw_layout = QtWidgets.QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(0, 0, 0, 0)
        raw_layout.setSpacing(Sizes.SPACING_SMALL)
        self.variable_raw_text = self._build_readonly_text_area(raw_tab)
        raw_layout.addWidget(self.variable_raw_text, 1)
        self.variable_detail_tabs.addTab(raw_tab, "原始数据")

        splitter.addWidget(detail_root)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        self.tab_widget.addTab(tab, "自定义变量")

    def _setup_readonly_table(self, table: QtWidgets.QTableWidget) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setShowGrid(False)
        table.setStyleSheet(ThemeManager.table_style())
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)

    def _build_readonly_text_area(self, parent: QtWidgets.QWidget) -> QtWidgets.QPlainTextEdit:
        text_area = QtWidgets.QPlainTextEdit(parent)
        text_area.setReadOnly(True)
        text_area.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        text_area.setFont(ui_fonts.monospace_font(9))
        text_area.setStyleSheet(
            f"background-color: {Colors.BG_DARK};"
            f"color: {Colors.TEXT_PRIMARY};"
            f"border: 1px solid {Colors.BORDER_LIGHT};"
            f"border-radius: {Sizes.RADIUS_SMALL}px;"
            "padding: 6px;"
        )
        return text_area

    def _configure_readonly_label(self, label_widget: QtWidgets.QLabel) -> None:
        label_widget.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        label_widget.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.IBeamCursor))

    # ------------------------------------------------------------------ Public API

    def set_graph(self, graph_id: str) -> None:
        """设置当前图上下文（惰性加载）。

        设计目标（用户视角）：
        - 节点图库列表的单击必须瞬时：不允许在单击阶段做“按节点规模线性增长”的分析扫描；
        - 只有当用户真正切到本面板（widget 可见）时，才开始后台加载与分析；
        - 同一张图在未发生文件变更时复用缓存结果，避免重复扫描大图。
        """
        self.current_graph_id = graph_id or None
        self._current_graph_name = ""
        if not self.current_graph_id:
            # 面板不可见时避免清空大表格造成卡顿；等真正显示时再刷新 UI。
            if self.isVisible():
                self.set_empty_state()
            else:
                self._status_badge.setText("未选中节点图")
                self.update_status_badge_style(
                    self._status_badge, Colors.INFO_BG, Colors.TEXT_PRIMARY
                )
                self.tab_widget.setEnabled(False)
            return

        # 面板不可见：仅记录 graph_id，不触发任何加载/分析与大表格重建。
        if not self.isVisible():
            self._status_badge.setText("待加载（切换到此页签后自动分析）")
            self.update_status_badge_style(
                self._status_badge, Colors.INFO_BG, Colors.TEXT_SECONDARY
            )
            return

        self._ensure_loaded_for_current_graph()

    def set_empty_state(self) -> None:
        self.current_graph_id = None
        self._signal_items = []
        self._signal_item_by_key = {}
        self._struct_items = []
        self._struct_item_by_key = {}
        self._variable_items = []
        self._variable_item_by_key = {}

        self._status_badge.setText("未选中节点图")
        self.update_status_badge_style(self._status_badge, Colors.INFO_BG, Colors.TEXT_PRIMARY)
        self.tab_widget.setEnabled(False)

        self.signal_table.setRowCount(0)
        self.struct_table.setRowCount(0)
        self.variable_table.setRowCount(0)

        self._clear_signal_detail()
        self._clear_struct_detail()
        self._clear_variable_detail()

    # ------------------------------------------------------------------ Loading & snapshot

    def _get_graph_signature(self, graph_id: str) -> float:
        """用于缓存命中判定的轻量签名：优先使用图文件 mtime。

        说明：
        - 签名检查必须足够便宜，才能让“单击选中”保持瞬时；
        - mtime 变化即认为图内容已变，缓存需失效并重新分析。
        """
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return 0.0
        file_path = self.resource_manager.get_graph_file_path(graph_id_text)
        if not isinstance(file_path, Path) or not file_path.exists():
            return 0.0
        return float(file_path.stat().st_mtime)

    def _ensure_loaded_for_current_graph(self) -> None:
        if not self.current_graph_id:
            if self.isVisible():
                self.set_empty_state()
            return

        graph_id = str(self.current_graph_id or "").strip()
        if not graph_id:
            return

        signature = self._get_graph_signature(graph_id)
        cached = self._usage_cache.get(graph_id)
        if cached is not None and float(cached.signature) == float(signature):
            # 缓存命中：直接应用，不再重复扫描
            if self.isVisible():
                self._apply_snapshot(cached, keep_selection=True)
            return

        self._enter_loading_state()
        self.graph_loader.request_payload(graph_id, self._handle_async_payload)

    def _enter_loading_state(self) -> None:
        self.tab_widget.setEnabled(False)
        self._status_badge.setText("加载中…")
        self.update_status_badge_style(self._status_badge, Colors.INFO_BG, Colors.TEXT_SECONDARY)

    def _handle_async_payload(self, graph_id: str, payload: GraphLoadPayload) -> None:
        if graph_id != self.current_graph_id:
            return
        # 若 payload 返回时面板已不可见，则不继续做分析；等用户真正切回本面板再触发。
        if not self.isVisible():
            self._status_badge.setText("待加载（切换到此页签后自动分析）")
            self.update_status_badge_style(
                self._status_badge, Colors.INFO_BG, Colors.TEXT_SECONDARY
            )
            return
        if payload.error:
            show_warning_dialog(self, "加载失败", payload.error)
            self.set_empty_state()
            return
        if payload.graph_model is None or payload.graph_config is None:
            self.set_empty_state()
            return
        self._current_graph_name = str(payload.graph_config.name or "").strip()

        signature = self._get_graph_signature(graph_id)
        self._submit_analysis_build(
            graph_id=graph_id,
            signature=signature,
            graph_name=str(self._current_graph_name or ""),
            graph_model=payload.graph_model,
        )

    def _submit_analysis_build(
        self,
        *,
        graph_id: str,
        signature: float,
        graph_name: str,
        graph_model: object,
    ) -> None:
        # generation：用于丢弃旧任务回调（用户快速切换选中图）
        self._analysis_generation += 1
        generation = int(self._analysis_generation)
        graph_name_text = str(graph_name or "")

        prev = self._active_analysis_future
        if prev is not None and not prev.done():
            prev.cancel()
        self._active_analysis_future = None

        future = _USED_DEFINITIONS_EXECUTOR.submit(self._build_usage_items, graph_model)
        self._active_analysis_future = future

        def _deliver() -> None:
            # 退出阶段或任务被取消时直接丢弃，避免跨线程回调触发不稳定行为
            if QtCore.QCoreApplication.instance() is None or QtCore.QCoreApplication.closingDown():
                return
            if future.cancelled():
                return
            error = future.exception()
            if error is not None:
                result = GraphUsedDefinitionsSnapshot(
                    signature=float(signature),
                    graph_name=graph_name_text,
                    signal_items=[],
                    struct_items=[],
                    variable_items=[],
                )
                self._analysis_ready.emit(generation, graph_id, (result, str(error)))
                return
            signal_items, struct_items, variable_items = future.result()
            result = GraphUsedDefinitionsSnapshot(
                signature=float(signature),
                graph_name=graph_name_text,
                signal_items=signal_items,
                struct_items=struct_items,
                variable_items=variable_items,
            )
            self._analysis_ready.emit(generation, graph_id, (result, None))

        future.add_done_callback(lambda _: _deliver())

    @QtCore.pyqtSlot(int, str, object)
    def _apply_analysis_result(self, generation: int, graph_id: str, payload: object) -> None:
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        result, error_text = payload
        if not isinstance(result, GraphUsedDefinitionsSnapshot):
            return
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return

        # 缓存写入：即使用户已切换到别的图，也保留结果，后续再选中可直接复用
        if not error_text:
            self._usage_cache[graph_id_text] = result

        # 仅当结果仍对应“当前正在看的图”时才更新 UI / 弹错误
        if int(generation) != int(self._analysis_generation):
            return
        if graph_id_text != str(self.current_graph_id or ""):
            return
        if error_text:
            show_warning_dialog(self, "分析失败", str(error_text))
            self.set_empty_state()
            return
        if not self.isVisible():
            return
        self._apply_snapshot(result, keep_selection=True)

    def _apply_snapshot(self, snapshot: GraphUsedDefinitionsSnapshot, *, keep_selection: bool) -> None:
        self._signal_items = list(snapshot.signal_items or [])
        self._signal_item_by_key = {item.key: item for item in self._signal_items}
        self._struct_items = list(snapshot.struct_items or [])
        self._struct_item_by_key = {item.key: item for item in self._struct_items}
        self._variable_items = list(snapshot.variable_items or [])
        self._variable_item_by_key = {item.key: item for item in self._variable_items}

        graph_name = str(snapshot.graph_name or "").strip() or str(self.current_graph_id or "")
        summary = (
            f"{graph_name} | "
            f"信号 {len(self._signal_items)} | 结构体 {len(self._struct_items)} | 自定义变量 {len(self._variable_items)}"
        )
        self._status_badge.setText(summary)
        self.update_status_badge_style(self._status_badge, Colors.INFO_BG, Colors.PRIMARY)

        self._rebuild_all_tables(keep_selection=bool(keep_selection))
        self.tab_widget.setEnabled(True)

    def _build_usage_items(
        self,
        graph_model: object,
    ) -> tuple[List[SignalUsageItem], List[StructUsageItem], List[LevelVariableUsageItem]]:
        from engine.graph.models.graph_model import GraphModel, NodeModel

        if not isinstance(graph_model, GraphModel):
            return [], [], []

        signal_repository = get_default_signal_repository()
        struct_repository = get_default_struct_repository()
        definition_schema_view = get_default_definition_schema_view()
        level_variable_view = get_default_level_variable_schema_view()

        all_signal_payloads = signal_repository.get_all_payloads()
        all_struct_payloads = struct_repository.get_all_payloads()
        signal_sources = definition_schema_view.get_all_signal_definition_sources()
        struct_sources = definition_schema_view.get_all_struct_definition_sources()
        all_level_variables = level_variable_view.get_all_variables()

        unique_variable_id_by_name = self._build_unique_variable_id_by_name(all_level_variables)

        # ------------------------------ Signals
        signal_nodes_by_id: Dict[str, Dict[str, List[GraphNodeUsage]]] = {}

        for node_id, node in (graph_model.nodes or {}).items():
            if not isinstance(node, NodeModel):
                continue
            node_title = _safe_text(getattr(node, "title", ""))
            if node_title not in (SIGNAL_SEND_NODE_TITLE, SIGNAL_LISTEN_NODE_TITLE):
                continue

            constants = getattr(node, "input_constants", None)
            constants_dict = constants if isinstance(constants, dict) else {}

            resolved_signal_id = _safe_text(constants_dict.get("__signal_id"))
            if not resolved_signal_id:
                literal = _safe_text(constants_dict.get(SIGNAL_NAME_PORT_NAME))
                resolved_by_name = signal_repository.resolve_id_by_name(literal)
                resolved_signal_id = resolved_by_name or literal

            if not resolved_signal_id:
                continue

            entry = signal_nodes_by_id.setdefault(
                resolved_signal_id, {"send": [], "listen": []}
            )
            usage = GraphNodeUsage(node_id=str(node_id), node_title=node_title)
            if node_title == SIGNAL_SEND_NODE_TITLE:
                entry["send"].append(usage)
            else:
                entry["listen"].append(usage)

        signal_items: List[SignalUsageItem] = []
        for signal_id, usage_groups in sorted(signal_nodes_by_id.items(), key=lambda pair: pair[0]):
            payload = all_signal_payloads.get(str(signal_id))
            payload_dict = dict(payload) if isinstance(payload, Mapping) else None
            signal_name = _safe_text((payload_dict or {}).get("signal_name")) or str(signal_id)
            parameters_raw = (payload_dict or {}).get("parameters") or []
            parameters: List[Dict[str, Any]] = (
                list(parameters_raw) if isinstance(parameters_raw, list) else []
            )
            source_path = self._format_source_path(signal_sources.get(str(signal_id)))
            search_blob = " ".join(
                [
                    signal_name,
                    str(signal_id),
                    source_path,
                    _pretty_json(parameters) if parameters else "",
                ]
            ).casefold()
            signal_items.append(
                SignalUsageItem(
                    key=str(signal_id),
                    signal_id=str(signal_id),
                    signal_name=signal_name,
                    source_path=source_path,
                    parameters=parameters,
                    send_nodes=list(usage_groups.get("send") or []),
                    listen_nodes=list(usage_groups.get("listen") or []),
                    raw_payload=payload_dict,
                    search_blob=search_blob,
                )
            )

        # ------------------------------ Structs
        struct_nodes_by_id: Dict[str, List[GraphNodeUsage]] = {}
        struct_node_ids_seen: Dict[str, set[str]] = {}
        used_fields_by_struct: Dict[str, List[str]] = {}

        struct_bindings = graph_model.get_struct_bindings()
        for node_id, binding in (struct_bindings or {}).items():
            if not isinstance(binding, dict):
                continue
            struct_id = _safe_text(binding.get("struct_id"))
            if not struct_id:
                continue
            node = (graph_model.nodes or {}).get(str(node_id))
            node_title = _safe_text(getattr(node, "title", "")) if node is not None else ""
            node_id_text = str(node_id)
            seen_node_ids = struct_node_ids_seen.setdefault(struct_id, set())
            if node_id_text not in seen_node_ids:
                seen_node_ids.add(node_id_text)
                struct_nodes_by_id.setdefault(struct_id, []).append(
                    GraphNodeUsage(node_id=node_id_text, node_title=node_title)
                )
            raw_field_names = binding.get("field_names") or []
            field_names = [
                _safe_text(field)
                for field in raw_field_names
                if isinstance(field, str) and _safe_text(field)
            ]
            used_fields_by_struct.setdefault(struct_id, []).extend(field_names)

        # 兼容：若某些结构体节点没有进入 metadata bindings，则尝试从节点常量补齐
        for node_id, node in (graph_model.nodes or {}).items():
            if not isinstance(node, NodeModel):
                continue
            node_title = _safe_text(getattr(node, "title", ""))
            if node_title not in STRUCT_NODE_TITLES:
                continue
            constants = getattr(node, "input_constants", None)
            constants_dict = constants if isinstance(constants, dict) else {}
            struct_id = _safe_text(constants_dict.get("__struct_id"))
            if not struct_id:
                literal = _safe_text(constants_dict.get(STRUCT_NAME_PORT_NAME))
                resolved_by_name = struct_repository.resolve_id_by_name(literal)
                struct_id = resolved_by_name or literal
            if not struct_id:
                continue
            node_id_text = str(node_id)
            seen_node_ids = struct_node_ids_seen.setdefault(struct_id, set())
            if node_id_text not in seen_node_ids:
                seen_node_ids.add(node_id_text)
                struct_nodes_by_id.setdefault(struct_id, []).append(
                    GraphNodeUsage(node_id=node_id_text, node_title=node_title)
                )

        struct_items: List[StructUsageItem] = []
        for struct_id, usage_nodes in sorted(struct_nodes_by_id.items(), key=lambda pair: pair[0]):
            payload = all_struct_payloads.get(str(struct_id))
            payload_dict = dict(payload) if isinstance(payload, Mapping) else None
            struct_name = _safe_text((payload_dict or {}).get("struct_name")) or str(struct_id)
            struct_type = _safe_text((payload_dict or {}).get("struct_type"))
            fields_raw = (payload_dict or {}).get("fields") or []
            fields: List[Dict[str, Any]] = list(fields_raw) if isinstance(fields_raw, list) else []

            raw_used_fields = used_fields_by_struct.get(str(struct_id)) or []
            deduped_used_fields: List[str] = []
            for field_name in raw_used_fields:
                text = _safe_text(field_name)
                if not text:
                    continue
                if text not in deduped_used_fields:
                    deduped_used_fields.append(text)

            source_path = self._format_source_path(struct_sources.get(str(struct_id)))
            search_blob = " ".join(
                [
                    struct_name,
                    str(struct_id),
                    struct_type,
                    source_path,
                    _pretty_json(fields) if fields else "",
                ]
            ).casefold()
            struct_items.append(
                StructUsageItem(
                    key=str(struct_id),
                    struct_id=str(struct_id),
                    struct_name=struct_name,
                    struct_type=struct_type,
                    source_path=source_path,
                    fields=fields,
                    usage_nodes=list(usage_nodes),
                    used_field_names=deduped_used_fields,
                    raw_payload=payload_dict,
                    search_blob=search_blob,
                )
            )

        # ------------------------------ Level variables (custom variables)
        variable_usages: Dict[str, Dict[str, List[GraphNodeUsage]]] = {}
        variable_key_to_raw_ref: Dict[str, str] = {}

        for node_id, node in (graph_model.nodes or {}).items():
            if not isinstance(node, NodeModel):
                continue
            node_title = _safe_text(getattr(node, "title", ""))
            if "自定义变量" not in node_title:
                continue
            constants = getattr(node, "input_constants", None)
            constants_dict = constants if isinstance(constants, dict) else {}
            raw_ref = _safe_text(constants_dict.get(VARIABLE_NAME_PORT_NAME))
            if not raw_ref:
                continue

            resolved_variable_id = self._normalize_level_variable_reference_text(
                raw_ref,
                variable_payloads=all_level_variables,
                unique_id_by_name=unique_variable_id_by_name,
            )
            key = resolved_variable_id or raw_ref
            variable_key_to_raw_ref.setdefault(key, raw_ref)

            entry = variable_usages.setdefault(
                key,
                {
                    "get": [],
                    "set": [],
                    "changed": [],
                    "other": [],
                },
            )
            usage = GraphNodeUsage(node_id=str(node_id), node_title=node_title)
            if node_title == "获取自定义变量":
                entry["get"].append(usage)
            elif node_title == "设置自定义变量":
                entry["set"].append(usage)
            elif node_title == "自定义变量变化时":
                entry["changed"].append(usage)
            else:
                entry["other"].append(usage)

        variable_items: List[LevelVariableUsageItem] = []
        for variable_key, usage_groups in sorted(variable_usages.items(), key=lambda pair: pair[0]):
            payload = all_level_variables.get(str(variable_key))
            payload_dict = dict(payload) if isinstance(payload, Mapping) else None

            variable_id = _safe_text((payload_dict or {}).get("variable_id")) or str(variable_key)
            variable_name = (
                _safe_text((payload_dict or {}).get("variable_name"))
                or _safe_text((payload_dict or {}).get("name"))
                or variable_id
            )
            variable_type = (
                _safe_text((payload_dict or {}).get("variable_type"))
                or _safe_text((payload_dict or {}).get("type_name"))
            )
            default_value = (payload_dict or {}).get("default_value")
            description = _safe_text((payload_dict or {}).get("description"))
            source_path = _safe_text((payload_dict or {}).get("source_path"))
            variable_file_id = _safe_text((payload_dict or {}).get("variable_file_id"))

            raw_ref = variable_key_to_raw_ref.get(variable_key) or ""
            search_blob = " ".join(
                [
                    variable_name,
                    variable_id,
                    variable_type,
                    description,
                    source_path,
                    variable_file_id,
                    raw_ref,
                    _pretty_json(default_value) if default_value is not None else "",
                ]
            ).casefold()

            variable_items.append(
                LevelVariableUsageItem(
                    key=str(variable_key),
                    variable_id=variable_id,
                    variable_name=variable_name,
                    variable_type=variable_type,
                    default_value=default_value,
                    description=description,
                    source_path=source_path,
                    variable_file_id=variable_file_id,
                    get_nodes=list(usage_groups.get("get") or []),
                    set_nodes=list(usage_groups.get("set") or []),
                    changed_nodes=list(usage_groups.get("changed") or []),
                    other_nodes=list(usage_groups.get("other") or []),
                    raw_payload=payload_dict,
                    search_blob=search_blob,
                )
            )

        return signal_items, struct_items, variable_items

    def _format_source_path(self, source_path: object) -> str:
        if not isinstance(source_path, Path):
            return "-"
        source_text = source_path.as_posix()
        workspace_root = getattr(self.resource_manager, "workspace_path", None)
        if isinstance(workspace_root, Path):
            workspace_text = workspace_root.as_posix()
            prefix = (workspace_text.rstrip("/") + "/").casefold()
            candidate = source_text.casefold()
            if candidate.startswith(prefix):
                return source_text[len(prefix) :]
        return source_text

    def _build_unique_variable_id_by_name(
        self,
        payloads: Mapping[str, Mapping[str, Any]],
    ) -> Dict[str, str]:
        id_by_name: Dict[str, str] = {}
        duplicates: set[str] = set()
        for variable_id, payload in payloads.items():
            if not isinstance(payload, Mapping):
                continue
            name_text = _safe_text(payload.get("variable_name")) or _safe_text(payload.get("name"))
            if not name_text:
                continue
            if name_text in id_by_name:
                duplicates.add(name_text)
                continue
            id_by_name[name_text] = str(variable_id)
        for duplicated in duplicates:
            id_by_name.pop(duplicated, None)
        return id_by_name

    def _normalize_level_variable_reference_text(
        self,
        raw_value: object,
        *,
        variable_payloads: Mapping[str, Mapping[str, Any]],
        unique_id_by_name: Mapping[str, str],
    ) -> str:
        raw_text = _safe_text(raw_value)
        if not raw_text:
            return ""

        candidate = raw_text

        # 1) 兼容展示格式：name (variable_id)
        if candidate.endswith(")") and "(" in candidate:
            inside = candidate.rsplit("(", 1)[-1].rstrip(")").strip()
            if inside:
                candidate = inside

        # 2) 兼容列表项格式：name | variable_id | ...
        if "|" in candidate:
            parts = [part.strip() for part in candidate.split("|")]
            if len(parts) >= 2 and parts[1]:
                candidate = parts[1]

        # 3) 已是 variable_id
        if candidate in variable_payloads:
            return candidate

        # 4) 若是全局唯一的 variable_name，则归一为 variable_id
        resolved = unique_id_by_name.get(candidate)
        if resolved:
            return str(resolved)

        return raw_text

    # ------------------------------------------------------------------ Filter & rebuild

    def _on_search_text_changed(self, normalized_text: str) -> None:
        self._current_search_text = normalized_text
        self._rebuild_all_tables(keep_selection=True)

    def _matches_search(self, item_search_blob: str) -> bool:
        query = self._current_search_text
        if not query:
            return True
        return query in item_search_blob

    def _rebuild_all_tables(self, *, keep_selection: bool) -> None:
        selected_signal_key = self._get_selected_table_item_key(self.signal_table)
        selected_struct_key = self._get_selected_table_item_key(self.struct_table)
        selected_variable_key = self._get_selected_table_item_key(self.variable_table)

        self._rebuild_signal_table(prefer_key=selected_signal_key if keep_selection else "")
        self._rebuild_struct_table(prefer_key=selected_struct_key if keep_selection else "")
        self._rebuild_variable_table(prefer_key=selected_variable_key if keep_selection else "")

    def _get_selected_table_item_key(self, table: QtWidgets.QTableWidget) -> str:
        current_row = table.currentRow()
        if current_row < 0:
            return ""
        first_cell = table.item(current_row, 0)
        if first_cell is None:
            return ""
        key_value = first_cell.data(QtCore.Qt.ItemDataRole.UserRole)
        return str(key_value) if isinstance(key_value, str) else ""

    def _set_row_key(self, table: QtWidgets.QTableWidget, row: int, key: str) -> None:
        first_cell = table.item(row, 0)
        if first_cell is None:
            return
        first_cell.setData(QtCore.Qt.ItemDataRole.UserRole, key)

    def _select_row_by_key(self, table: QtWidgets.QTableWidget, key: str) -> None:
        if not key:
            return
        for row in range(table.rowCount()):
            first_cell = table.item(row, 0)
            if first_cell is None:
                continue
            cell_key = first_cell.data(QtCore.Qt.ItemDataRole.UserRole)
            if isinstance(cell_key, str) and cell_key == key:
                table.setCurrentCell(row, 0)
                return

    def _rebuild_signal_table(self, *, prefer_key: str) -> None:
        matched_items = [item for item in self._signal_items if self._matches_search(item.search_blob)]
        self.signal_table.setRowCount(len(matched_items))

        for row_index, item in enumerate(matched_items):
            self.signal_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(item.signal_name))
            self.signal_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(item.signal_id))
            self.signal_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(str(len(item.send_nodes))))
            self.signal_table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(str(len(item.listen_nodes))))
            self._set_row_key(self.signal_table, row_index, item.key)

        self.signal_table.resizeColumnsToContents()
        self._select_row_by_key(self.signal_table, prefer_key)
        if self.signal_table.currentRow() < 0 and self.signal_table.rowCount() > 0:
            self.signal_table.setCurrentCell(0, 0)

    def _rebuild_struct_table(self, *, prefer_key: str) -> None:
        matched_items = [item for item in self._struct_items if self._matches_search(item.search_blob)]
        self.struct_table.setRowCount(len(matched_items))

        for row_index, item in enumerate(matched_items):
            self.struct_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(item.struct_name))
            self.struct_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(item.struct_id))
            self.struct_table.setItem(
                row_index,
                2,
                QtWidgets.QTableWidgetItem(str(len(item.used_field_names))),
            )
            self.struct_table.setItem(
                row_index,
                3,
                QtWidgets.QTableWidgetItem(str(len(item.usage_nodes))),
            )
            self._set_row_key(self.struct_table, row_index, item.key)

        self.struct_table.resizeColumnsToContents()
        self._select_row_by_key(self.struct_table, prefer_key)
        if self.struct_table.currentRow() < 0 and self.struct_table.rowCount() > 0:
            self.struct_table.setCurrentCell(0, 0)

    def _rebuild_variable_table(self, *, prefer_key: str) -> None:
        matched_items = [item for item in self._variable_items if self._matches_search(item.search_blob)]
        self.variable_table.setRowCount(len(matched_items))

        for row_index, item in enumerate(matched_items):
            self.variable_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(item.variable_name))
            self.variable_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(item.variable_id))
            self.variable_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(item.variable_type or "-"))
            self.variable_table.setItem(row_index, 3, QtWidgets.QTableWidgetItem(str(len(item.get_nodes))))
            self.variable_table.setItem(row_index, 4, QtWidgets.QTableWidgetItem(str(len(item.set_nodes))))
            self.variable_table.setItem(
                row_index, 5, QtWidgets.QTableWidgetItem(str(len(item.changed_nodes)))
            )
            self._set_row_key(self.variable_table, row_index, item.key)

        self.variable_table.resizeColumnsToContents()
        self._select_row_by_key(self.variable_table, prefer_key)
        if self.variable_table.currentRow() < 0 and self.variable_table.rowCount() > 0:
            self.variable_table.setCurrentCell(0, 0)

    # ------------------------------------------------------------------ Selection handlers

    def _on_signal_selection_changed(self) -> None:
        key = self._get_selected_table_item_key(self.signal_table)
        selected = self._signal_item_by_key.get(key)
        if selected is None:
            self._clear_signal_detail()
            return
        self._apply_signal_detail(selected)

    def _on_struct_selection_changed(self) -> None:
        key = self._get_selected_table_item_key(self.struct_table)
        selected = self._struct_item_by_key.get(key)
        if selected is None:
            self._clear_struct_detail()
            return
        self._apply_struct_detail(selected)

    def _on_variable_selection_changed(self) -> None:
        key = self._get_selected_table_item_key(self.variable_table)
        selected = self._variable_item_by_key.get(key)
        if selected is None:
            self._clear_variable_detail()
            return
        self._apply_variable_detail(selected)

    # ------------------------------------------------------------------ Detail render

    def _clear_signal_detail(self) -> None:
        self.signal_name_value.setText("-")
        self.signal_id_value.setText("-")
        self.signal_source_value.setText("-")
        self.signal_usage_value.setText("-")
        self.signal_parameters_table.setRowCount(0)
        self.signal_usage_text.setPlainText("")
        self.signal_raw_text.setPlainText("")
        self.signal_detail_tabs.setCurrentIndex(0)

    def _apply_signal_detail(self, item: SignalUsageItem) -> None:
        self.signal_name_value.setText(item.signal_name or "-")
        self.signal_id_value.setText(item.signal_id or "-")
        self.signal_source_value.setText(item.source_path or "-")
        self.signal_usage_value.setText(
            f"发送 {len(item.send_nodes)} | 监听 {len(item.listen_nodes)}"
        )

        parameters = item.parameters if isinstance(item.parameters, list) else []
        self.signal_parameters_table.setRowCount(len(parameters))
        for row_index, entry in enumerate(parameters):
            entry_dict = entry if isinstance(entry, dict) else {}
            name_text = _safe_text(entry_dict.get("name"))
            type_text = _safe_text(entry_dict.get("parameter_type"))
            desc_text = _safe_text(entry_dict.get("description"))
            self.signal_parameters_table.setItem(row_index, 0, QtWidgets.QTableWidgetItem(name_text))
            self.signal_parameters_table.setItem(row_index, 1, QtWidgets.QTableWidgetItem(type_text))
            self.signal_parameters_table.setItem(row_index, 2, QtWidgets.QTableWidgetItem(desc_text))
        self.signal_parameters_table.resizeColumnsToContents()

        usage_lines: List[str] = []
        if item.send_nodes:
            usage_lines.append(f"【发送信号】({len(item.send_nodes)})")
            for usage in item.send_nodes:
                usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
            usage_lines.append("")
        if item.listen_nodes:
            usage_lines.append(f"【监听信号】({len(item.listen_nodes)})")
            for usage in item.listen_nodes:
                usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
        self.signal_usage_text.setPlainText("\n".join(usage_lines).strip())

        self.signal_raw_text.setPlainText(_pretty_json(item.raw_payload or {}))

    def _clear_struct_detail(self) -> None:
        self.struct_name_value.setText("-")
        self.struct_id_value.setText("-")
        self.struct_type_value.setText("-")
        self.struct_source_value.setText("-")
        self.struct_fields_table.setRowCount(0)
        self.struct_usage_text.setPlainText("")
        self.struct_raw_text.setPlainText("")
        self.struct_detail_tabs.setCurrentIndex(0)

    def _apply_struct_detail(self, item: StructUsageItem) -> None:
        self.struct_name_value.setText(item.struct_name or "-")
        self.struct_id_value.setText(item.struct_id or "-")
        self.struct_type_value.setText(item.struct_type or "-")
        self.struct_source_value.setText(item.source_path or "-")

        fields = item.fields if isinstance(item.fields, list) else []
        self.struct_fields_table.setRowCount(len(fields))
        for row_index, entry in enumerate(fields):
            entry_dict = entry if isinstance(entry, dict) else {}
            field_name = _safe_text(entry_dict.get("field_name"))
            param_type = _safe_text(entry_dict.get("param_type"))
            default_value = entry_dict.get("default_value")
            length_value = entry_dict.get("length")
            length_text = str(length_value) if isinstance(length_value, int) else ""

            default_text = ""
            if default_value is not None:
                default_text = _pretty_json(default_value)

            name_item = QtWidgets.QTableWidgetItem(field_name)
            type_item = QtWidgets.QTableWidgetItem(param_type)
            default_item = QtWidgets.QTableWidgetItem(default_text)
            length_item = QtWidgets.QTableWidgetItem(length_text)

            if field_name and field_name in (item.used_field_names or []):
                name_item.setForeground(QtGui.QBrush(QtGui.QColor(Colors.PRIMARY)))
                type_item.setForeground(QtGui.QBrush(QtGui.QColor(Colors.PRIMARY)))

            self.struct_fields_table.setItem(row_index, 0, name_item)
            self.struct_fields_table.setItem(row_index, 1, type_item)
            self.struct_fields_table.setItem(row_index, 2, default_item)
            self.struct_fields_table.setItem(row_index, 3, length_item)

        self.struct_fields_table.resizeColumnsToContents()

        usage_lines: List[str] = []
        if item.used_field_names:
            usage_lines.append("用到的字段：")
            for field_name in item.used_field_names:
                usage_lines.append(f"- {field_name}")
            usage_lines.append("")
        if item.usage_nodes:
            usage_lines.append(f"结构体节点({len(item.usage_nodes)})")
            for usage in item.usage_nodes:
                title = usage.node_title or "（未知节点）"
                usage_lines.append(f"- {usage.node_id}  {title}")
        self.struct_usage_text.setPlainText("\n".join(usage_lines).strip())

        self.struct_raw_text.setPlainText(_pretty_json(item.raw_payload or {}))

    def _clear_variable_detail(self) -> None:
        self.variable_name_value.setText("-")
        self.variable_id_value.setText("-")
        self.variable_type_value.setText("-")
        self.variable_source_value.setText("-")
        self.variable_definition_text.setPlainText("")
        self.variable_usage_text.setPlainText("")
        self.variable_raw_text.setPlainText("")
        self.variable_detail_tabs.setCurrentIndex(0)

    def _apply_variable_detail(self, item: LevelVariableUsageItem) -> None:
        self.variable_name_value.setText(item.variable_name or "-")
        self.variable_id_value.setText(item.variable_id or "-")
        self.variable_type_value.setText(item.variable_type or "-")
        source_text = item.source_path or "-"
        if item.variable_file_id:
            source_text = f"{source_text}  (变量文件: {item.variable_file_id})"
        self.variable_source_value.setText(source_text)

        definition_lines: List[str] = []
        definition_lines.append(f"variable_id: {item.variable_id}")
        definition_lines.append(f"变量名: {item.variable_name}")
        definition_lines.append(f"类型: {item.variable_type or '-'}")
        if item.description:
            definition_lines.append(f"说明: {item.description}")
        definition_lines.append("")
        definition_lines.append("默认值:")
        definition_lines.append(_pretty_json(item.default_value))
        self.variable_definition_text.setPlainText("\n".join(definition_lines).strip())

        usage_lines: List[str] = []
        usage_lines.append(f"读取(获取自定义变量): {len(item.get_nodes)}")
        for usage in item.get_nodes:
            usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
        usage_lines.append("")
        usage_lines.append(f"写入(设置自定义变量): {len(item.set_nodes)}")
        for usage in item.set_nodes:
            usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
        usage_lines.append("")
        usage_lines.append(f"变化事件(自定义变量变化时): {len(item.changed_nodes)}")
        for usage in item.changed_nodes:
            usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
        if item.other_nodes:
            usage_lines.append("")
            usage_lines.append(f"其他相关节点: {len(item.other_nodes)}")
            for usage in item.other_nodes:
                usage_lines.append(f"- {usage.node_id}  {usage.node_title}")
        self.variable_usage_text.setPlainText("\n".join(usage_lines).strip())

        self.variable_raw_text.setPlainText(_pretty_json(item.raw_payload or {}))


__all__ = ["GraphUsedDefinitionsPanel"]


