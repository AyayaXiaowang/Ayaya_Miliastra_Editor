"""节点图属性面板 - 显示选中节点图的详细信息"""

from concurrent.futures import Future
from datetime import datetime
from typing import Any, Optional, List, Tuple, Dict, Set

from PyQt6 import QtCore, QtWidgets, QtGui

from ui.foundation.dialog_utils import show_warning_dialog
from ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from ui.panels.panel_scaffold import PanelScaffold
from ui.panels.package_membership_selector import build_package_membership_row
from ui.widgets.graph_references_table_widget import GraphReferencesTableWidget
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from engine.configs.resource_types import ResourceType
from engine.configs.specialized.struct_definitions_data import list_struct_ids
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from ui.widgets.graph_variable_table_widget import GraphVariableTableWidget
from ui.foundation.info_snippets import GRAPH_VARIABLE_INFO
from ui.panels.graph_data_provider import (
    GraphDataProvider,
    GraphLoadPayload,
    get_shared_graph_data_provider,
)
from ui.panels.graph_async_loader import get_shared_graph_loader, GraphAsyncLoader


class GraphPropertyPanel(PanelScaffold):
    """节点图属性面板 - 嵌入式面板，包含基本信息、引用列表和节点图变量"""
    
    # 信号
    jump_to_reference = QtCore.pyqtSignal(str, str, str)  # (entity_type, entity_id, package_id)
    graph_updated = QtCore.pyqtSignal(str)  # graph_id - 节点图数据更新时触发
    package_membership_changed = QtCore.pyqtSignal(str, str, bool)  # graph_id, package_id, is_checked
    graph_data_loaded = QtCore.pyqtSignal(str, object)
    package_membership_loaded = QtCore.pyqtSignal(str, list, set)
    
    def __init__(self, resource_manager: ResourceManager,
                 package_index_manager: PackageIndexManager,
                 parent=None):
        super().__init__(
            parent,
            title="节点图属性",
            description="查看当前节点图的基础信息、引用关系与变量列表",
        )
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self.data_provider = get_shared_graph_data_provider(resource_manager, package_index_manager)
        self.graph_loader: GraphAsyncLoader = get_shared_graph_loader(self.data_provider)
        
        self.current_graph_id: Optional[str] = None
        self.current_graph_model: Optional[GraphModel] = None
        self._graph_editor_controller: Optional[Any] = None
        self._warned_missing_controller = False
        self._active_membership_future: Optional[Future] = None
        
        self._save_debounce_timer = QtCore.QTimer(self)
        self._save_debounce_timer.setSingleShot(True)
        self._save_debounce_timer.setInterval(400)
        self._save_debounce_timer.timeout.connect(self._perform_deferred_save)
        
        self._status_label = self.create_status_badge(
            "GraphPropertyStatusBadge",
            "未选中节点图",
        )
        self._setup_ui()
        self.graph_data_loaded.connect(self._apply_graph_payload)
        self.package_membership_loaded.connect(self._apply_package_membership)
        self.graph_editor_controller = None
    
    def _setup_ui(self) -> None:
        """设置UI"""
        # 状态徽章下方的面板级“所属存档”选择行（标签页外部）
        self._build_package_membership_row()

        self.tabs = QtWidgets.QTabWidget()
        
        self.basic_tab = self._create_basic_tab()
        self.tabs.addTab(self.basic_tab, "基本信息")
        
        self.references_tab = self._create_references_tab()
        self.tabs.addTab(self.references_tab, "引用列表")
        
        self.variables_tab = self._create_variables_tab()
        self.tabs.addTab(self.variables_tab, "节点图变量")
        
        self.body_layout.addWidget(self.tabs, 1)
        
        self.set_empty_state()

    def _build_package_membership_row(self) -> None:
        """在面板级正文顶部构建“所属存档”选择行。"""
        (
            self._package_membership_widget,
            self._package_label,
            self.package_selector,
        ) = build_package_membership_row(
            self.body_layout,
            self,
            self._on_package_membership_selector_changed,
        )

    @property
    def graph_editor_controller(self):
        return self._graph_editor_controller

    @graph_editor_controller.setter
    def graph_editor_controller(self, controller):
        self._graph_editor_controller = controller
        # 变量在当前工程中改为“仅代码可写”，属性面板始终以只读方式展示
        self._update_variable_editor_state()
        if controller:
            self._warned_missing_controller = False

    def _update_variable_editor_state(self) -> None:
        # 节点图变量在 UI 中只读：所有编辑需在 Python 节点图文件中完成。
        # 仅禁用增删与单元格编辑，保留表格滚动与列表/字典展开能力，方便在节点图库等只读视图中浏览变量详情。
        if hasattr(self, "variable_table_widget"):
            self.variable_table_widget.set_read_only_mode(True)
            self.variable_table_widget.setToolTip(
                "节点图变量在 UI 中只读；请在节点图 Python 文件里维护变量定义。"
            )

    def _schedule_graph_save(self) -> None:
        if not self.graph_editor_controller:
            self._warn_missing_controller()
            if self.current_graph_model:
                self.variable_table_widget.set_graph_model(self.current_graph_model)
            return
        self._save_debounce_timer.start()

    def _perform_deferred_save(self) -> None:
        self._save_graph_data()
    
    def _create_basic_tab(self) -> QtWidgets.QWidget:
        """创建基本信息标签页"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.name_label = QtWidgets.QLabel()
        self.type_label = QtWidgets.QLabel()
        self.folder_label = QtWidgets.QLabel()
        self.description_label = QtWidgets.QLabel()
        self.description_label.setWordWrap(True)

        self.node_count_label = QtWidgets.QLabel()
        self.edge_count_label = QtWidgets.QLabel()
        self.reference_count_label = QtWidgets.QLabel()

        self.created_at_label = QtWidgets.QLabel()
        self.updated_at_label = QtWidgets.QLabel()

        for text_label_widget in (
            self.name_label,
            self.type_label,
            self.folder_label,
            self.description_label,
            self.node_count_label,
            self.edge_count_label,
            self.reference_count_label,
            self.created_at_label,
            self.updated_at_label,
        ):
            self._configure_readonly_label(text_label_widget)
        
        layout.addRow("节点图名称:", self.name_label)
        layout.addRow("类型:", self.type_label)
        layout.addRow("文件夹:", self.folder_label)
        layout.addRow("描述:", self.description_label)
        
        layout.addRow("", QtWidgets.QLabel())  # 空行分隔
        
        layout.addRow("节点数量:", self.node_count_label)
        layout.addRow("连接数量:", self.edge_count_label)
        layout.addRow("引用次数:", self.reference_count_label)
        
        layout.addRow("", QtWidgets.QLabel())  # 空行分隔

        layout.addRow("创建时间:", self.created_at_label)
        layout.addRow("更新时间:", self.updated_at_label)
        
        return widget

    def _configure_readonly_label(self, label_widget: QtWidgets.QLabel) -> None:
        """将只读信息标签配置为支持文本选中与复制。"""
        label_widget.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        label_widget.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        label_widget.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.IBeamCursor))
    
    def _create_references_tab(self) -> QtWidgets.QWidget:
        """创建引用列表标签页"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)

        self.references_widget = GraphReferencesTableWidget(widget)
        self.references_widget.reference_activated.connect(self._jump_to_entity)
        layout.addWidget(self.references_widget)
        
        return widget
    
    def _create_variables_tab(self) -> QtWidgets.QWidget:
        """创建节点图变量标签页"""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 说明文字
        info_label = QtWidgets.QLabel(GRAPH_VARIABLE_INFO)
        info_label.setFont(QtGui.QFont("Microsoft YaHei UI", 9))
        info_label.setStyleSheet(f"color: {Colors.TEXT_PLACEHOLDER}; padding: 5px; background-color: {Colors.BG_DARK}; border-radius: 4px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.variable_table_widget = GraphVariableTableWidget(self)
        self._apply_variable_struct_options()
        self.variable_table_widget.variables_changed.connect(self._on_variable_widget_changed)
        layout.addWidget(self.variable_table_widget)
        
        return widget

    def _apply_variable_struct_options(self) -> None:
        """为节点图变量表格配置结构体下拉选项。"""
        struct_ids = list_struct_ids()
        self.variable_table_widget.set_struct_id_options(struct_ids)

    def _on_variable_widget_changed(self) -> None:
        """变量发生变更时通过控制器保存"""
        # 变量当前在 UI 中只读，不再通过属性面板触发任何保存逻辑
        if not self.current_graph_model:
            return
        return
    
    def set_graph(self, graph_id: str) -> None:
        """设置当前显示的节点图"""
        self.current_graph_id = graph_id or None
        if not self.current_graph_id:
            self.set_empty_state()
            return
        self._submit_graph_load(self.current_graph_id)

    def _submit_graph_load(self, graph_id: str) -> None:
        self._enter_loading_state()
        self.graph_loader.request_payload(graph_id, self._handle_async_payload)
    
    def set_empty_state(self) -> None:
        """设置为空状态（未选中任何节点图）"""
        self.current_graph_id = None
        self.current_graph_model = None
        if self._active_membership_future:
            self._active_membership_future.cancel()
            self._active_membership_future = None
        
        # 清空所有显示
        self.name_label.setText("-")
        self.type_label.setText("-")
        self.folder_label.setText("-")
        self.description_label.setText("-")
        self.node_count_label.setText("-")
        self.edge_count_label.setText("-")
        self.reference_count_label.setText("-")
        self.created_at_label.setText("-")
        self.updated_at_label.setText("-")
        
        self.references_widget.clear()
        
        self.variable_table_widget.set_graph_model(None)

        # 禁用所有控件
        self.tabs.setEnabled(False)
        self._status_label.setText("未选中节点图")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_PRIMARY)
        self.package_selector.clear_membership()
        self._save_debounce_timer.stop()

    def switch_to_variables_tab(self) -> None:
        """切换到节点图变量标签页"""
        self.tabs.setCurrentIndex(2)  # 第三个标签页（索引2）
    
    def _load_basic_info(self, graph_config: GraphConfig, references: List[Tuple[str, str, str, str]]) -> None:
        """加载基本信息
        
        Args:
            graph_config: 节点图配置
            references: 引用列表（避免重复查询）
        """
        self.name_label.setText(graph_config.name)
        
        type_text = "🔷 服务器" if graph_config.graph_type == "server" else "🔶 客户端"
        self.type_label.setText(type_text)
        
        folder_text = graph_config.folder_path if graph_config.folder_path else "<根目录>"
        self.folder_label.setText(folder_text)
        
        desc_text = graph_config.description if graph_config.description else "<无描述>"
        self.description_label.setText(desc_text)
        
        self.node_count_label.setText(str(graph_config.get_node_count()))
        self.edge_count_label.setText(str(graph_config.get_edge_count()))
        
        # 引用信息（直接使用传入的引用列表）
        self.reference_count_label.setText(str(len(references)))
        
        # 时间戳
        created_at = graph_config.metadata.get("created_at", "未知")
        updated_at = graph_config.metadata.get("updated_at", "未知")
        self.created_at_label.setText(self._format_datetime(created_at))
        self.updated_at_label.setText(self._format_datetime(updated_at))
        
        type_color = Colors.PRIMARY if graph_config.graph_type == "server" else Colors.SUCCESS
        type_label = "服务器" if graph_config.graph_type == "server" else "客户端"
        self._status_label.setText(
            f"{type_label} | 节点 {graph_config.get_node_count()} | 引用 {len(references)}"
        )
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, type_color)
    
    def _jump_to_entity(self, entity_type: str, entity_id: str, package_id: str) -> None:
        """跳转到实体编辑界面"""
        self.jump_to_reference.emit(entity_type, entity_id, package_id)
    
    
    def _save_graph_data(self) -> None:
        """保存节点图数据（统一通过 GraphEditorController）"""
        # 节点图变量与结构的持久化完全由 Python 代码负责，
        # 属性面板不再直接触发对 ResourceManager 的写操作。
        return

    
    def _format_datetime(self, dt_str: str) -> str:
        """格式化日期时间"""
        if not dt_str or dt_str == "未知":
            return "未知"
        
        normalized = dt_str
        if dt_str.endswith("Z"):
            normalized = f"{dt_str[:-1]}+00:00"
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _on_package_membership_selector_changed(self, package_id: str, is_checked: bool) -> None:
        if not self.current_graph_id or not package_id:
            return
        self.data_provider.invalidate_package_cache()
        self.package_membership_changed.emit(self.current_graph_id, package_id, is_checked)

    def _enter_loading_state(self) -> None:
        self.tabs.setEnabled(False)
        self.variable_table_widget.set_graph_model(None)
        self.references_widget.clear()
        self._status_label.setText("加载中…")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_SECONDARY)
        self._save_debounce_timer.stop()

    def _handle_async_payload(self, graph_id: str, payload: GraphLoadPayload) -> None:
        self.graph_data_loaded.emit(graph_id, payload)

    @QtCore.pyqtSlot(str, object)
    def _apply_graph_payload(self, graph_id: str, payload: GraphLoadPayload) -> None:
        if graph_id != self.current_graph_id:
            return
        if payload.error:
            show_warning_dialog(self, "加载失败", payload.error)
            self.set_empty_state()
            return
        if not payload.graph_config or not payload.graph_model:
            self.set_empty_state()
            return
        self.current_graph_model = payload.graph_model
        self.variable_table_widget.set_graph_model(payload.graph_model)
        self._load_basic_info(payload.graph_config, payload.references)

        package_map = self.data_provider.get_package_map()
        package_name_map: Dict[str, str] = {
            package_id: info.get("name", package_id) if info else package_id
            for package_id, info in package_map.items()
        }
        self.references_widget.set_references(payload.references, package_name_map)
        self.tabs.setEnabled(True)
        self._submit_package_membership_load(graph_id)

    def _submit_package_membership_load(self, graph_id: str) -> None:
        if not graph_id:
            return
        if self._active_membership_future:
            self._active_membership_future.cancel()
        self._active_membership_future = self.graph_loader.request_membership(
            graph_id, self._handle_membership_payload
        )

    def _handle_membership_payload(
        self,
        graph_id: str,
        packages: List[dict],
        membership: set[str],
        error: Optional[str],
    ) -> None:
        if error:
            if graph_id == self.current_graph_id:
                show_warning_dialog(self, "存档列表加载失败", error)
            return
        self.package_membership_loaded.emit(graph_id, packages, membership)

    @QtCore.pyqtSlot(str, list, set)
    def _apply_package_membership(self, graph_id: str, packages: List[dict], membership: Set[str]) -> None:
        if graph_id != self.current_graph_id:
            return
        self.package_selector.set_packages(packages)
        self.package_selector.set_membership(membership)

    def closeEvent(self, a0: Optional[QtGui.QCloseEvent]) -> None:
        self._flush_pending_save()
        super().closeEvent(a0)

    def _warn_missing_controller(self) -> None:
        if self._warned_missing_controller:
            return
        self._warned_missing_controller = True
        self._status_label.setText("变量只读：未绑定图编辑控制器")
        self.update_status_badge_style(self._status_label, Colors.WARNING_BG, Colors.WARNING)

    def _flush_pending_save(self) -> None:
        if not self._save_debounce_timer.isActive():
            return
        self._save_debounce_timer.stop()
        self._perform_deferred_save()

