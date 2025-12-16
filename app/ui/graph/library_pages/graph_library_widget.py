"""节点图库界面 - 统一管理所有节点图"""

from PyQt6 import QtCore, QtWidgets
from typing import Optional, Dict, List, Union
from datetime import datetime
from pathlib import Path

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.graph.library_mixins import (
    SearchFilterMixin,
    SelectionAndScrollMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
)
from app.ui.graph.library_pages.library_scaffold import (
    LibraryChangeEvent,
    LibraryPageMixin,
    LibrarySelection,
)
from engine.resources.resource_manager import ResourceManager, ResourceType
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.graph_reference_tracker import GraphReferenceTracker
from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from app.ui.dialogs.graph_detail_dialog import GraphDetailDialog
from app.ui.graph.library_pages.graph_card_widget import GraphCardWidget
from app.ui.controllers.graph_error_tracker import get_instance as get_error_tracker
from engine.resources.package_view import PackageView
from engine.resources.global_resource_view import GlobalResourceView
from engine.resources.unclassified_resource_view import UnclassifiedResourceView
from app.ui.panels.panel_scaffold import PanelScaffold, SectionCard

from app.ui.graph.graph_library import FolderTreeMixin, GraphListMixin


class GraphLibraryWidget(
    PanelScaffold,
    FolderTreeMixin,
    GraphListMixin,
    LibraryPageMixin,
    SearchFilterMixin,
    SelectionAndScrollMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """节点图库界面"""
    
    graph_selected = QtCore.pyqtSignal(str)  # graph_id
    graph_double_clicked = QtCore.pyqtSignal(str, dict)  # (graph_id, graph_data)
    jump_to_entity_requested = QtCore.pyqtSignal(str, str, str)  # (entity_type, entity_id, package_id)
    
    def __init__(
        self,
        resource_manager: ResourceManager,
        package_index_manager: PackageIndexManager,
        parent=None,
        *,
        selection_mode: bool = False,
    ):
        super().__init__(
            parent,
            title="节点图库",
            description="统一浏览、筛选与维护所有节点图，支持类型切换与排序查看。",
        )
        self.resource_manager = resource_manager
        self.package_index_manager = package_index_manager
        self.selection_mode = selection_mode
        self.reference_tracker = GraphReferenceTracker(resource_manager, package_index_manager)
        self.error_tracker = get_error_tracker()  # 错误跟踪器（单例）
        # 节点图库在当前工程中以只读模式运行：
        # - 仅用于浏览、筛选与跳转节点图
        # - 不在 UI 中新建/删除/移动节点图，也不编辑节点图变量
        # - 唯一允许写入的仍是右侧属性面板中的“所属存档”行（写入 PackageIndex）
        self.graph_library_read_only: bool = True
        
        self.current_folder = ""
        self.current_graph_type = "server"  # server | client | all
        self.current_sort_by = "modified"  # modified | name | nodes | references
        self.graph_cards: Dict[str, GraphCardWidget] = {}  # 存储卡片部件
        self.selected_graph_id: Optional[str] = None
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView, UnclassifiedResourceView]
        ] = None

        self._setup_ui()
        self._refresh_folder_tree()
        self._refresh_graph_list()

    # === LibraryPage 协议实现 ===

    # GraphLibraryWidget 以只读模式运行，因此当前实现不会主动发出结构化的
    # LibraryChangeEvent；依旧为主窗口暴露 data_changed 信号以满足协议要求，
    # 后续若允许在图库中执行增删改操作，可在 GraphListMixin 的相关入口中补充事件发射。
    data_changed = QtCore.pyqtSignal(LibraryChangeEvent)

    def set_context(
        self,
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """设置当前视图对应的存档/特殊视图，用于过滤显示。

        - 未分类视图：仅显示未分类的节点图；
        - 全局/具体存档：显示全部节点图（按类型/文件夹）。
        """
        self.current_package = package
        self._refresh_graph_list()
        if self.isVisible():
            self.ensure_default_selection()

    def set_package(
        self,
        package: Union[PackageView, GlobalResourceView, UnclassifiedResourceView],
    ) -> None:
        """兼容旧接口，内部委托给 set_context。"""
        self.set_context(package)

    def reload(self) -> None:
        """在当前上下文下全量刷新节点图列表并尽量恢复选中。"""
        self._refresh_folder_tree()
        self._refresh_graph_list()
        if self.isVisible():
            self.ensure_default_selection()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的节点图（若存在）。"""
        graph_id = self.get_selected_graph_id()
        if not graph_id:
            return None
        return LibrarySelection(
            kind="graph",
            id=graph_id,
            context={"scope": self._describe_current_scope()},
        )

    def set_selection(self, selection: Optional[LibrarySelection]) -> None:
        """根据 LibrarySelection 恢复节点图选中状态。"""
        if selection is None:
            self.selected_graph_id = None
            return
        if selection.kind != "graph":
            return
        if not selection.id:
            return
        self.select_graph_by_id(selection.id, open_editor=False)
    
    def _setup_ui(self) -> None:
        """设置UI"""
        # 顶部过滤
        filter_widget = QtWidgets.QWidget()
        filter_layout = QtWidgets.QHBoxLayout(filter_widget)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(Sizes.SPACING_SMALL)
        type_label = QtWidgets.QLabel("类型:")
        self.type_combo = QtWidgets.QComboBox()
        self.type_combo.addItem("全部", "all")
        self.type_combo.addItem("🔷 服务器节点图", "server")
        self.type_combo.addItem("🔶 客户端节点图", "client")
        self.type_combo.setCurrentIndex(1)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        sort_label = QtWidgets.QLabel("排序:")
        self.sort_combo = QtWidgets.QComboBox()
        self.sort_combo.addItem("修改时间", "modified")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.addItem("节点数", "nodes")
        self.sort_combo.addItem("引用次数", "references")
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        filter_layout.addWidget(type_label)
        filter_layout.addWidget(self.type_combo)
        filter_layout.addSpacing(Sizes.SPACING_MEDIUM)
        filter_layout.addWidget(sort_label)
        filter_layout.addWidget(self.sort_combo)
        self.add_action_widget(filter_widget)

        # 工具栏
        toolbar_widget = QtWidgets.QWidget()
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        self.init_toolbar(toolbar_layout)
        self.add_graph_btn = QtWidgets.QPushButton("+ 新建节点图", self)
        self.add_folder_btn = QtWidgets.QPushButton("+ 新建文件夹", self)
        self.delete_btn = QtWidgets.QPushButton("删除", self)
        self.move_btn = QtWidgets.QPushButton("移动到文件夹", self)
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索节点图...")
        toolbar_buttons = [
            self.add_graph_btn,
            self.add_folder_btn,
            self.delete_btn,
            self.move_btn,
        ]
        self.setup_toolbar_with_search(toolbar_layout, toolbar_buttons, self.search_edit)
        self.set_status_widget(toolbar_widget)

        # 只读模式下禁用所有会修改节点图结构或文件夹的按钮
        if getattr(self, "graph_library_read_only", False):
            for button in toolbar_buttons:
                button.setEnabled(False)
                button.setToolTip("只读模式：节点图库仅用于浏览与跳转，节点图结构与变量请在代码中维护。")
        
        # 主分割窗口
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # 左侧：文件夹树
        left_section = SectionCard("文件夹结构", "管理节点图目录与拖放")
        self.folder_tree = QtWidgets.QTreeWidget()
        self.folder_tree.setHeaderLabel("文件夹")
        self.folder_tree.setObjectName("leftPanel")
        self.folder_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)
        if not self.selection_mode:
            self.folder_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            self.folder_tree.customContextMenuRequested.connect(self._show_folder_context_menu)
        else:
            self.folder_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        
        # 启用拖放
        self.folder_tree.setAcceptDrops(True)
        self.folder_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DropOnly)
        self.folder_tree.setDropIndicatorShown(True)
        
        # 安装事件过滤器以处理拖放
        self.folder_tree.viewport().installEventFilter(self)
        
        # 自动展开计时器
        self._drag_hover_timer = QtCore.QTimer(self)
        self._drag_hover_timer.setSingleShot(True)
        self._drag_hover_timer.timeout.connect(self._expand_hovered_item)
        self._drag_hover_item = None
        
        left_section.add_content_widget(self.folder_tree, stretch=1)
        splitter.addWidget(left_section)
        
        # 中间：节点图卡片列表（使用滚动区域）
        center_section = SectionCard("节点图列表", "滚动浏览卡片，双击可打开编辑")
        self.graph_scroll_area = QtWidgets.QScrollArea()
        self.graph_scroll_area.setWidgetResizable(True)
        self.graph_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 卡片容器
        self.graph_container_widget = QtWidgets.QWidget()
        self.graph_container_layout = QtWidgets.QVBoxLayout(self.graph_container_widget)
        self.graph_container_layout.setContentsMargins(5, 5, 5, 5)
        self.graph_container_layout.setSpacing(8)
        self.graph_container_layout.addStretch()
        
        self.graph_scroll_area.setWidget(self.graph_container_widget)
        if not self.selection_mode:
            self.graph_scroll_area.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
            self.graph_scroll_area.customContextMenuRequested.connect(self._show_graph_context_menu)
        else:
            self.graph_scroll_area.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
        
        center_section.add_content_widget(self.graph_scroll_area, stretch=1)
        splitter.addWidget(center_section)
        
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        self.body_layout.addWidget(splitter, 1)
        
        # 连接信号
        self.add_graph_btn.clicked.connect(self._add_graph)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.move_btn.clicked.connect(self._move_graph)
        self.connect_search(self.search_edit, self._filter_graphs, placeholder="搜索节点图...")
        self.folder_tree.itemClicked.connect(self._on_folder_clicked)

        if self.selection_mode:
            self._apply_selection_mode()


    

    

    
    def _on_sort_changed(self, index: int) -> None:
        """排序方式改变"""
        self.current_sort_by = self.sort_combo.itemData(index)
        self._refresh_graph_list()

    def _apply_selection_mode(self) -> None:
        self.add_folder_btn.hide()
        self.delete_btn.hide()
        self.move_btn.hide()
        self.folder_tree.setDragEnabled(False)
        self.folder_tree.setAcceptDrops(False)
        self.folder_tree.setDropIndicatorShown(False)
        self.folder_tree.viewport().removeEventFilter(self)
    

    

    

    

    

    
    def _on_type_changed(self, index: int) -> None:
        """类型切换"""
        self.current_graph_type = self.type_combo.itemData(index)
        self.current_folder = ""
        # 类型切换时强制刷新文件夹树，避免仅依赖快照缓存导致左侧仍显示上一次类型的根节点。
        self._refresh_folder_tree(force=True)
        self._refresh_graph_list()
    

    

    

    

    

    

    

    

    

    


    # === 对外API ===

    

    
    def refresh(self) -> None:
        """刷新界面（兼容旧入口，内部委托给 reload）。"""
        self.reload()

    def _describe_current_scope(self) -> str:
        """根据当前资源视图返回简单 scope 标识，用于变更事件上下文。"""
        if isinstance(self.current_package, PackageView):
            return "package"
        if isinstance(self.current_package, GlobalResourceView):
            return "global"
        if isinstance(self.current_package, UnclassifiedResourceView):
            return "unclassified"
        return "unknown"
    

    

    

    

    

    


