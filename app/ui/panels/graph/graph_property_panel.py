"""节点图属性面板 - 显示选中节点图的详细信息"""

from concurrent.futures import Future
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Tuple, Dict, Set

from PyQt6 import QtCore, QtWidgets, QtGui

from app.ui.foundation.dialog_utils import show_warning_dialog
from app.ui.foundation import fonts as ui_fonts
from app.ui.foundation.theme_manager import ThemeManager, Colors, Sizes
from app.ui.panels.panel_scaffold import PanelScaffold
from app.ui.panels.package_membership_selector import build_package_membership_row
from app.ui.widgets.graph_references_table_widget import GraphReferencesTableWidget
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index_manager import PackageIndexManager
from engine.configs.resource_types import ResourceType
from engine.configs.specialized.struct_definitions_data import list_struct_ids
from engine.graph.utils.metadata_extractor import load_graph_metadata_from_file
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from engine.utils.resource_library_layout import get_packages_root_dir, get_shared_root_dir
from app.ui.widgets.graph_variable_table_widget import GraphVariableTableWidget
from app.ui.foundation.info_snippets import GRAPH_VARIABLE_INFO
from app.runtime.services.graph_data_service import GraphDataService, GraphLoadPayload, get_shared_graph_data_service
from app.ui.panels.graph.graph_async_loader import get_shared_graph_loader, GraphAsyncLoader


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
        self.data_provider: GraphDataService = get_shared_graph_data_service(resource_manager, package_index_manager)
        self.graph_loader: GraphAsyncLoader = get_shared_graph_loader(self.data_provider)
        
        self.current_graph_id: Optional[str] = None
        self.current_graph_model: Optional[GraphModel] = None
        # “节点图变量”页签可能包含大量控件（两行结构表格 + 子表格）。
        # 为避免在切换选中节点图时总是同步构建整张变量表，变量表改为“页签可见时才加载”。
        self._variables_table_graph_id: str = ""
        # 节点图库场景的“轻量预览”模式：单击列表只展示轻量元数据，避免触发解析+自动布局。
        self._library_preview_active: bool = False
        self._pending_full_load_tab_index: int | None = None
        self._graph_editor_controller: Optional[Any] = None
        self._warned_missing_controller = False
        self._active_membership_future: Optional[Future] = None
        self._active_references_future: Optional[Future] = None
        # 预览模式：用于“项目存档页预览另一个存档的节点图”场景，只展示轻量元数据，不触发图资源加载。
        self._preview_mode_active: bool = False
        self._preview_package_id: str = ""
        self._preview_current_package_id: str = ""
        
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
        
        # 交互：在节点图库的轻量预览模式下，用户若主动切到“节点图变量”，再触发完整加载。
        self.tabs.currentChanged.connect(self._on_tabs_current_changed)

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
        info_label.setFont(ui_fonts.ui_font(9))
        info_label.setStyleSheet(ThemeManager.info_label_dark_style())
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        self.variable_table_widget = GraphVariableTableWidget(self)
        self._apply_variable_struct_options()
        self.variable_table_widget.variables_changed.connect(self._on_variable_widget_changed)
        layout.addWidget(self.variable_table_widget)
        
        return widget

    def _apply_variable_struct_options(self) -> None:
        """为节点图变量表格配置结构体下拉选项。"""
        struct_ids = list_struct_ids(self.resource_manager)
        self.variable_table_widget.set_struct_id_options(struct_ids)

    def _on_variable_widget_changed(self) -> None:
        """变量发生变更时通过控制器保存"""
        # 变量当前在 UI 中只读，不再通过属性面板触发任何保存逻辑
        if not self.current_graph_model:
            return
        return
    
    def set_graph(self, graph_id: str) -> None:
        """设置当前显示的节点图"""
        self._library_preview_active = False
        self._pending_full_load_tab_index = None
        self._preview_mode_active = False
        self._preview_package_id = ""
        self._preview_current_package_id = ""
        self.current_graph_id = graph_id or None

        # 切到完整加载：取消可能挂起的“引用列表惰性加载”任务，避免旧回调覆盖 UI。
        if self._active_references_future:
            self._active_references_future.cancel()
            self._active_references_future = None
        if not self.current_graph_id:
            self.set_empty_state()
            return
        self._submit_graph_load(self.current_graph_id)

    def set_graph_library_preview(
        self,
        graph_id: str,
        *,
        references: list[tuple[str, str, str, str]] | None = None,
        reference_count: int | None = None,
    ) -> None:
        """节点图库：轻量预览选中的节点图（不触发解析+自动布局）。

        用户视角目标：
        - 单击节点图卡片必须瞬时，不应触发 `ResourceManager.load_resource(ResourceType.GRAPH, ...)`；
        - 先展示“足够确认”的轻量信息（名称/类型/目录/描述/节点数/连线数/修改时间/引用数）；
        - 引用列表详情只在用户切到“引用列表”页签时再按需加载（避免单击阶段重建大表格）；
        - 当用户主动切到“节点图变量”页签时，才按需触发完整加载。
        """
        self._library_preview_active = True
        self._pending_full_load_tab_index = None
        self._preview_mode_active = False
        self._preview_package_id = ""
        self._preview_current_package_id = ""

        self.current_graph_id = graph_id or None
        self.current_graph_model = None
        # 引用表格内容可能滞后：单击预览默认不重建引用表格（避免卡顿），因此标记为“待刷新”。
        setattr(self, "_references_table_graph_id", "")
        if not self.current_graph_id:
            self.set_empty_state()
            return

        # 取消上一次的 membership 异步任务，避免旧回调覆盖当前预览态 UI。
        if self._active_membership_future:
            self._active_membership_future.cancel()
            self._active_membership_future = None
        if self._active_references_future:
            self._active_references_future.cancel()
            self._active_references_future = None

        # 清理依赖 GraphModel 的视图
        self.variable_table_widget.set_graph_model(None)
        self._save_debounce_timer.stop()

        # 轻量元数据：不触发节点图解析/布局
        metadata = self.resource_manager.load_graph_metadata(self.current_graph_id)
        if not isinstance(metadata, dict):
            self.set_empty_state()
            return

        graph_name = str(metadata.get("name") or "").strip() or str(self.current_graph_id)
        graph_type = str(metadata.get("graph_type") or "").strip() or "server"
        folder_path = str(metadata.get("folder_path") or "").strip()
        description = str(metadata.get("description") or "").strip()

        # 统计口径（列表页约束）：
        # - node_count/edge_count 只允许来自持久化 graph_cache；
        # - 若当前未命中缓存，则保持为空（展示为 "-"），禁止在列表页做任何估算/计算。
        node_count_raw = metadata.get("node_count")
        edge_count_raw = metadata.get("edge_count")
        node_count: int | None = int(node_count_raw) if isinstance(node_count_raw, (int, float)) else None
        edge_count: int | None = int(edge_count_raw) if isinstance(edge_count_raw, (int, float)) else None
        node_count_text = str(node_count) if isinstance(node_count, int) else "-"
        edge_count_text = str(edge_count) if isinstance(edge_count, int) else "-"

        modified_time = metadata.get("modified_time")
        if isinstance(modified_time, (int, float)) and float(modified_time) > 0:
            dt = datetime.fromtimestamp(float(modified_time))
            updated_text = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            updated_text = "-"

        self.name_label.setText(graph_name)
        self.type_label.setText("🔷 服务器" if graph_type == "server" else "🔶 客户端")
        self.folder_label.setText(folder_path if folder_path else "<根目录>")
        self.description_label.setText(description if description else "<无描述>")
        self.node_count_label.setText(node_count_text)
        self.edge_count_label.setText(edge_count_text)

        # 引用信息：
        # - 单击预览只更新“引用次数”（足够确认是否为常用图/是否被大量挂载）；
        # - 引用列表详情仅在“引用列表”页签可见时再按需加载，避免重建大表格造成卡顿。
        ref_count_value = 0
        if isinstance(reference_count, int):
            ref_count_value = int(reference_count)
        elif isinstance(reference_count, float):
            ref_count_value = int(reference_count)
        elif isinstance(references, list):
            ref_count_value = len(references)
        self.reference_count_label.setText(str(max(0, ref_count_value)))

        current_tab_index = int(self.tabs.currentIndex()) if hasattr(self, "tabs") else 0
        if current_tab_index == 1:
            # 用户当前就在引用页签：清理旧数据并按需加载（可能较大，必须后台化）
            self.references_widget.clear()
            if isinstance(references, list):
                reference_list = list(references)
                self.references_widget.set_references(reference_list, package_name_map=None)
                setattr(self, "_references_table_graph_id", str(self.current_graph_id or ""))
            else:
                self._submit_references_load(str(self.current_graph_id))

        self.created_at_label.setText("-")
        self.updated_at_label.setText(updated_text)

        type_color = Colors.PRIMARY if graph_type == "server" else Colors.SUCCESS
        type_label = "服务器" if graph_type == "server" else "客户端"
        self._status_label.setText(
            f"{type_label} | 节点 {node_count_text} | 引用 {max(0, ref_count_value)}"
        )
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, type_color)

        # Tab 状态：变量页签允许点击（触发完整加载），其余直接可用
        self.tabs.setEnabled(True)
        self.tabs.setTabEnabled(0, True)
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, True)

        self._submit_package_membership_load(self.current_graph_id)

    def set_graph_preview(
        self,
        graph_id: str,
        *,
        preview_package_id: str,
        current_package_id: str = "",
    ) -> None:
        """以“预览模式”展示节点图（不触发 ResourceManager.load_resource）。

        典型场景：用户当前打开存档 A，但在“项目存档”页面预览存档 B 的节点图条目。
        此时直接加载会因为 ResourceManager 作用域不包含存档 B 而误报“不存在”，
        因此这里只展示 docstring/路径推断得到的轻量元数据，并提示用户切换存档后再加载完整内容。
        """
        self._preview_mode_active = True
        self._preview_package_id = str(preview_package_id or "").strip()
        self._preview_current_package_id = str(current_package_id or "").strip()

        self.current_graph_id = graph_id or None
        self.current_graph_model = None
        if not self.current_graph_id:
            self.set_empty_state()
            return

        # 取消上一次的 membership 异步任务，避免旧回调覆盖当前预览态 UI。
        if self._active_membership_future:
            self._active_membership_future.cancel()
            self._active_membership_future = None

        # 清理依赖 GraphModel 的视图
        self.variable_table_widget.set_graph_model(None)
        self.references_widget.clear()
        self._save_debounce_timer.stop()

        # 仅启用“基本信息”页签；引用/变量需要完整加载才有意义
        self.tabs.setEnabled(True)
        self.tabs.setTabEnabled(0, True)
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)

        preview_info = self._load_preview_graph_basic_info(
            graph_id=self.current_graph_id,
            preview_package_id=self._preview_package_id,
        )
        self._apply_preview_basic_info(preview_info)
        self._apply_preview_membership(
            preview_package_id=self._preview_package_id,
        )

    def _submit_graph_load(self, graph_id: str) -> None:
        self._enter_loading_state()
        self.graph_loader.request_payload(graph_id, self._handle_async_payload)
    
    def set_empty_state(self) -> None:
        """设置为空状态（未选中任何节点图）"""
        self._preview_mode_active = False
        self._preview_package_id = ""
        self._preview_current_package_id = ""
        self.current_graph_id = None
        self.current_graph_model = None
        if self._active_membership_future:
            self._active_membership_future.cancel()
            self._active_membership_future = None
        if self._active_references_future:
            self._active_references_future.cancel()
            self._active_references_future = None
        
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
        self._variables_table_graph_id = ""
        self.references_widget.clear()
        self._status_label.setText("加载中…")
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_SECONDARY)
        self._save_debounce_timer.stop()

    def _ensure_variables_loaded(self) -> None:
        """确保“节点图变量”页签已加载当前节点图的变量表。"""
        graph_id = str(self.current_graph_id or "").strip()
        if not graph_id:
            return
        if self.current_graph_model is None:
            return
        if str(getattr(self, "_variables_table_graph_id", "") or "") == graph_id:
            return
        self.variable_table_widget.set_graph_model(self.current_graph_model)
        self._variables_table_graph_id = graph_id

    def _on_tabs_current_changed(self, index: int) -> None:
        """页签切换：引用/变量页签按需加载，避免大图卡顿。"""
        if self._preview_mode_active:
            return
        if not self.current_graph_id:
            return

        tab_index = int(index)

        # 引用列表页签索引固定为 1：只加载引用详情，不触发图解析
        if tab_index == 1 and self._library_preview_active:
            references_table_graph_id = str(getattr(self, "_references_table_graph_id", "") or "")
            if references_table_graph_id != str(self.current_graph_id or ""):
                self.references_widget.clear()
                self._submit_references_load(str(self.current_graph_id))
            return

        # 变量页签索引固定为 2：按需加载变量表（必要时触发完整加载）
        if tab_index != 2:
            return

        # 节点图库轻量预览：用户显式切到“节点图变量”时触发完整加载（异步）
        if self._library_preview_active and self.current_graph_model is None:
            # 防止重复触发：记录一次“希望停留的 tab”
            if self._pending_full_load_tab_index is None:
                self._pending_full_load_tab_index = 2
            self.set_graph(self.current_graph_id)
            return

        # 普通模式/已加载完整模型：按需加载变量表格
        self._ensure_variables_loaded()

    def _handle_async_payload(self, graph_id: str, payload: GraphLoadPayload) -> None:
        self.graph_data_loaded.emit(graph_id, payload)

    @QtCore.pyqtSlot(str, object)
    def _apply_graph_payload(self, graph_id: str, payload: GraphLoadPayload) -> None:
        if graph_id != self.current_graph_id:
            return
        if self._preview_mode_active:
            return
        if payload.error:
            show_warning_dialog(self, "加载失败", payload.error)
            self.set_empty_state()
            return
        if not payload.graph_config or not payload.graph_model:
            self.set_empty_state()
            return
        self.current_graph_model = payload.graph_model
        # 变量页签可能很重：仅在页签可见时才加载变量表，避免大图加载时额外卡顿。
        self._variables_table_graph_id = ""
        self._load_basic_info(payload.graph_config, payload.references)

        package_map = self.data_provider.get_package_map()
        package_name_map: Dict[str, str] = {
            package_id: info.get("name", package_id) if info else package_id
            for package_id, info in package_map.items()
        }
        self.references_widget.set_references(payload.references, package_name_map)
        self.tabs.setEnabled(True)
        pending_tab = self._pending_full_load_tab_index
        self._pending_full_load_tab_index = None
        if isinstance(pending_tab, int) and pending_tab >= 0:
            self.tabs.setCurrentIndex(int(pending_tab))
        # 若当前就在“节点图变量”页签，则立即按需加载变量表
        if hasattr(self, "tabs") and int(self.tabs.currentIndex()) == 2:
            self._ensure_variables_loaded()
        self._submit_package_membership_load(graph_id)

    # ------------------------------------------------------------------ Library preview: references (lazy)

    def _submit_references_load(self, graph_id: str) -> None:
        """节点图库轻量预览：按需后台加载引用列表详情。"""
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return
        if self._active_references_future:
            self._active_references_future.cancel()
        # 引用详情只在“引用列表”页签需要：后台加载，避免 UI 线程构建大表格卡顿
        self._active_references_future = self.graph_loader.request_references(
            graph_id_text,
            self._handle_references_payload,
        )

    def _handle_references_payload(self, graph_id: str, references: object, error_text: object) -> None:
        if graph_id != self.current_graph_id:
            return
        if self._preview_mode_active:
            return
        if not self._library_preview_active:
            return
        # 只有当“引用列表”页签可见时才更新表格，避免后台回调打断单击预览的顺滑感
        if hasattr(self, "tabs") and int(self.tabs.currentIndex()) != 1:
            return

        message = str(error_text or "").strip()
        if message:
            show_warning_dialog(self, "引用列表加载失败", message)
            return

        reference_list = list(references) if isinstance(references, list) else []
        self.references_widget.set_references(reference_list, package_name_map=None)
        setattr(self, "_references_table_graph_id", str(self.current_graph_id or ""))
        self.reference_count_label.setText(str(len(reference_list)))

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
        if graph_id == self.current_graph_id and self._preview_mode_active:
            return
        if error:
            if graph_id == self.current_graph_id:
                show_warning_dialog(self, "存档列表加载失败", error)
            return
        self.package_membership_loaded.emit(graph_id, packages, membership)

    @QtCore.pyqtSlot(str, list, set)
    def _apply_package_membership(self, graph_id: str, packages: List[dict], membership: Set[str]) -> None:
        if graph_id != self.current_graph_id:
            return
        if self._preview_mode_active:
            return
        self.package_selector.set_packages(packages)
        self.package_selector.set_membership(membership)

    # ------------------------------------------------------------------ Preview helpers
    @property
    def _preview_graph_id_to_path_cache_by_package(self) -> Dict[str, Dict[str, Path]]:
        cache = getattr(self, "__preview_graph_id_to_path_cache_by_package", None)
        if cache is None:
            cache = {}
            setattr(self, "__preview_graph_id_to_path_cache_by_package", cache)
        return cache

    def _normalize_preview_package_id_for_cache(self, preview_package_id: str) -> str:
        pkg_id = str(preview_package_id or "").strip()
        if not pkg_id or pkg_id == "global_view":
            return "shared"
        return pkg_id

    def _build_preview_graph_id_to_path_map(self, *, preview_package_id: str) -> Dict[str, Path]:
        pkg_id = self._normalize_preview_package_id_for_cache(preview_package_id)
        root_dir = self._resolve_preview_root_dir(preview_package_id=pkg_id)
        if root_dir is None:
            return {}
        graph_root_dir = (root_dir / ResourceType.GRAPH.value).resolve()
        if not graph_root_dir.exists() or not graph_root_dir.is_dir():
            return {}

        py_files = sorted(
            list(graph_root_dir.rglob("*.py")),
            key=lambda path: path.as_posix().casefold(),
        )
        id_to_path: Dict[str, Path] = {}
        for py_file in py_files:
            if not py_file.is_file():
                continue
            if py_file.name.startswith("_"):
                continue
            if "校验" in py_file.stem:
                continue
            if py_file.parent.name == "__pycache__":
                continue

            meta = load_graph_metadata_from_file(py_file)
            candidate_id = str(meta.graph_id or "").strip() or py_file.stem
            # 遇到重复 graph_id 时保留排序后的第一个，保持与“逐个扫描命中即返回”的行为一致。
            if candidate_id and candidate_id not in id_to_path:
                id_to_path[candidate_id] = py_file

        return id_to_path

    def _get_preview_graph_id_to_path_map(self, *, preview_package_id: str) -> Dict[str, Path]:
        pkg_id = self._normalize_preview_package_id_for_cache(preview_package_id)
        cache = self._preview_graph_id_to_path_cache_by_package
        if pkg_id in cache:
            return cache[pkg_id]
        mapping = self._build_preview_graph_id_to_path_map(preview_package_id=pkg_id)
        cache[pkg_id] = mapping
        return mapping

    def _rebuild_preview_graph_id_to_path_map(self, *, preview_package_id: str) -> Dict[str, Path]:
        pkg_id = self._normalize_preview_package_id_for_cache(preview_package_id)
        mapping = self._build_preview_graph_id_to_path_map(preview_package_id=pkg_id)
        self._preview_graph_id_to_path_cache_by_package[pkg_id] = mapping
        return mapping

    def _resolve_preview_root_dir(self, *, preview_package_id: str) -> Path | None:
        resource_library_dir = getattr(self.resource_manager, "resource_library_dir", None)
        if not isinstance(resource_library_dir, Path):
            return None

        pkg_id = str(preview_package_id or "").strip()
        if not pkg_id or pkg_id == "global_view" or pkg_id == "shared":
            return get_shared_root_dir(resource_library_dir)
        return (get_packages_root_dir(resource_library_dir) / pkg_id).resolve()

    def _resolve_preview_graph_file_path(self, *, graph_id: str, preview_package_id: str) -> Path | None:
        graph_id_text = str(graph_id or "").strip()
        if not graph_id_text:
            return None
        pkg_id = self._normalize_preview_package_id_for_cache(preview_package_id)

        mapping = self._get_preview_graph_id_to_path_map(preview_package_id=pkg_id)
        candidate = mapping.get(graph_id_text)
        if isinstance(candidate, Path) and candidate.exists() and candidate.is_file():
            return candidate
        if isinstance(candidate, Path):
            # 命中但文件不再存在（外部移动/删除）时回退重建一次。
            mapping = self._rebuild_preview_graph_id_to_path_map(preview_package_id=pkg_id)
            candidate = mapping.get(graph_id_text)
            if isinstance(candidate, Path) and candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _load_preview_graph_basic_info(self, *, graph_id: str, preview_package_id: str) -> dict:
        graph_id_text = str(graph_id or "").strip()
        file_path = self._resolve_preview_graph_file_path(
            graph_id=graph_id_text,
            preview_package_id=preview_package_id,
        )
        info: dict = {
            "graph_id": graph_id_text,
            "name": graph_id_text,
            "graph_type": "",
            "folder_path": "",
            "description": "",
            "file_path": None,
            "modified_time": None,
        }
        if file_path is None or not file_path.exists():
            return info

        meta = load_graph_metadata_from_file(file_path)
        candidate_id = str(meta.graph_id or "").strip() or file_path.stem
        if candidate_id != graph_id_text:
            # 命中时校验 metadata，避免外部改 ID/移动文件导致短暂错配；不匹配则重建索引后再尝试一次。
            self._rebuild_preview_graph_id_to_path_map(preview_package_id=preview_package_id)
            file_path = self._resolve_preview_graph_file_path(
                graph_id=graph_id_text,
                preview_package_id=preview_package_id,
            )
            if file_path is None or not file_path.exists():
                return info
            meta = load_graph_metadata_from_file(file_path)
            candidate_id = str(meta.graph_id or "").strip() or file_path.stem
            if candidate_id != graph_id_text:
                return info

        info["file_path"] = file_path
        info["modified_time"] = float(file_path.stat().st_mtime)
        info["name"] = str(meta.graph_name or "").strip() or graph_id_text
        info["graph_type"] = str(meta.graph_type or "").strip() or "server"
        info["folder_path"] = str(meta.folder_path or "").strip()
        info["description"] = str(meta.description or "").strip()
        return info

    def _apply_preview_basic_info(self, info: dict) -> None:
        graph_id = str(info.get("graph_id") or "").strip() or "-"
        name = str(info.get("name") or "").strip() or graph_id
        graph_type = str(info.get("graph_type") or "").strip()
        folder_path = str(info.get("folder_path") or "").strip()
        description = str(info.get("description") or "").strip()
        file_path = info.get("file_path")
        modified_time = info.get("modified_time")

        self.name_label.setText(name)
        if isinstance(file_path, Path):
            self.name_label.setToolTip(str(file_path))

        if graph_type == "server":
            self.type_label.setText("🔷 服务器")
        elif graph_type == "client":
            self.type_label.setText("🔶 客户端")
        else:
            self.type_label.setText(graph_type or "-")

        self.folder_label.setText(folder_path if folder_path else "<根目录>")
        self.description_label.setText(description if description else "<无描述>")

        # 预览模式不解析图结构：统计信息与引用列表留空
        self.node_count_label.setText("-")
        self.edge_count_label.setText("-")
        self.reference_count_label.setText("-")
        self.created_at_label.setText("-")

        if isinstance(modified_time, (int, float)) and modified_time > 0:
            dt = datetime.fromtimestamp(float(modified_time))
            self.updated_at_label.setText(dt.strftime("%Y-%m-%d %H:%M:%S"))
        else:
            self.updated_at_label.setText("-")

        preview_pkg = self._preview_package_id or "-"
        current_pkg = self._preview_current_package_id or ""
        if current_pkg and preview_pkg and preview_pkg != current_pkg:
            badge_text = f"预览模式：{preview_pkg}（当前：{current_pkg}）"
        else:
            badge_text = f"预览模式：{preview_pkg}"
        self._status_label.setText(badge_text)
        self.update_status_badge_style(self._status_label, Colors.INFO_BG, Colors.TEXT_SECONDARY)

        if isinstance(file_path, Path):
            tooltip_pkg = self._preview_package_id or "<未知>"
            self._status_label.setToolTip(
                f"预览模式：未加载图结构/变量/引用。\n"
                f"预览存档：{tooltip_pkg}\n"
                f"文件：{file_path}"
            )
        else:
            self._status_label.setToolTip("预览模式：未找到节点图源文件，无法加载完整信息。")

    def _apply_preview_membership(self, *, preview_package_id: str) -> None:
        owner_id = str(preview_package_id or "").strip()
        if not owner_id or owner_id == "global_view":
            owner_id = "shared"
        packages: list[dict] = []
        if self.package_index_manager is not None:
            packages = list(self.package_index_manager.list_packages())
        self.package_selector.set_packages(packages)
        self.package_selector.set_membership({owner_id})
        # 预览模式下不允许切换归属：跨作用域移动需要先切换为当前存档再操作
        self.package_selector.setEnabled(False)

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

