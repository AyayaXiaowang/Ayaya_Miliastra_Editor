"""节点图库界面 - 统一管理所有节点图"""

from PyQt6 import QtCore, QtWidgets, QtGui
from typing import Optional, Dict, List, Union, Callable
from datetime import datetime
from pathlib import Path

from app.ui.foundation.theme_manager import Sizes
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.keymap_store import KeymapStore
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
from app.ui.graph.library_pages.library_view_scope import describe_resource_view_scope
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
        self._standard_shortcuts: list[QtGui.QShortcut] = []
        self.reference_tracker = GraphReferenceTracker(resource_manager, package_index_manager)
        self.error_tracker = get_error_tracker()  # 错误跟踪器（单例）
        # 节点图库默认允许“轻量资源管理操作”（新建/复制/重命名/删除/移动到文件夹）。
        # 若需要强制只读（例如演示/只读环境），可将该开关设为 True。
        self.graph_library_read_only: bool = False
        
        self.current_folder = ""
        self.current_graph_type = "server"  # server | client | all
        self.current_sort_by = "modified"  # modified | name | nodes | references
        self.graph_cards: Dict[str, GraphCardWidget] = {}  # 存储卡片部件
        self.selected_graph_id: Optional[str] = None
        # 插件扩展区：允许私有扩展在不触碰内部 layout 的情况下追加按钮/状态控件
        self._extension_toolbar_buttons: Dict[str, QtWidgets.QAbstractButton] = {}
        self._extension_toolbar_widgets: Dict[str, QtWidgets.QWidget] = {}
        self._extension_toolbar_layout: QtWidgets.QHBoxLayout | None = None
        self._extension_toolbar_widget_host: QtWidgets.QWidget | None = None
        self.current_package: Optional[
            Union[PackageView, GlobalResourceView]
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
        package: Union[PackageView, GlobalResourceView],
    ) -> None:
        """设置当前视图对应的存档/特殊视图，用于过滤显示。

        - 全局视图：显示全部节点图（按类型/文件夹）；
        - 具体存档：按存档索引过滤可见节点图集合（避免看到其它项目的节点图）。
        """
        self.current_package = package
        # 切换存档/视图时：避免沿用上一视图残留的目录过滤（会导致列表看起来“只剩某个文件夹”，
        # 或文件夹树显示已回退到根目录但列表仍按旧 current_folder 过滤）。
        self.current_folder = ""
        setattr(self, "current_folder_scope", "all")
        self._refresh_folder_tree(force=True)
        self._refresh_graph_list()
        if self.isVisible():
            self.ensure_default_selection()

    def reload(self) -> None:
        """在当前上下文下全量刷新节点图列表并尽量恢复选中。"""
        self._force_invalidate_graph_library_view_cache()
        self._refresh_folder_tree()
        self._refresh_graph_list()
        if self.isVisible():
            self.ensure_default_selection()

    def refresh_for_mode_enter(self) -> None:
        """进入 GRAPH_LIBRARY 模式时的轻量刷新。

        设计目标：
        - 切页时避免每次都强制失效快照缓存并全量重建，降低“从大图返回列表/切到节点图库”的卡顿；
        - 仍会调用内部的增量刷新逻辑：folder tree 基于快照、graph list 基于 refresh_signature。
        """
        self._refresh_folder_tree()
        self._refresh_graph_list()

    def get_selection(self) -> Optional[LibrarySelection]:
        """返回当前选中的节点图（若存在）。"""
        graph_id = self.get_selected_graph_id()
        if not graph_id:
            return None
        return LibrarySelection(
            kind="graph",
            id=graph_id,
            context={"scope": describe_resource_view_scope(self.current_package)},
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
        # 启动/会话恢复时只需要恢复“当前选中图”，不应隐式把目录筛选切到该图所在文件夹，
        # 否则中间列表会被收窄，看起来像“只剩两三个节点图”。
        self.select_graph_by_id(selection.id, open_editor=False, sync_folder_filter=False)
    
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
        self.duplicate_graph_btn = QtWidgets.QPushButton("复制", self)
        self.rename_graph_btn = QtWidgets.QPushButton("重命名", self)
        self.delete_btn = QtWidgets.QPushButton("删除", self)
        self.move_btn = QtWidgets.QPushButton("移动到文件夹", self)
        self.search_edit = QtWidgets.QLineEdit(self)
        self.search_edit.setPlaceholderText("搜索节点图...")
        toolbar_buttons = [
            self.add_graph_btn,
            self.add_folder_btn,
            self.duplicate_graph_btn,
            self.rename_graph_btn,
            self.delete_btn,
            self.move_btn,
        ]

        # 标准按钮
        for button in toolbar_buttons:
            toolbar_layout.addWidget(button)

        # 插件扩展区：位于主按钮与搜索框之间（用于私有扩展注入按钮/状态控件）
        extension_toolbar_widget = QtWidgets.QWidget(toolbar_widget)
        extension_toolbar_layout = QtWidgets.QHBoxLayout(extension_toolbar_widget)
        extension_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        extension_toolbar_layout.setSpacing(Sizes.SPACING_MEDIUM)
        self._extension_toolbar_layout = extension_toolbar_layout
        self._extension_toolbar_widget_host = extension_toolbar_widget
        toolbar_layout.addWidget(extension_toolbar_widget)

        toolbar_layout.addStretch(1)
        toolbar_layout.addWidget(self.search_edit)
        self.set_status_widget(toolbar_widget)

        # 只读模式下禁用所有会修改节点图结构或文件夹的按钮
        if getattr(self, "graph_library_read_only", False):
            for button in (
                self.add_graph_btn,
                self.add_folder_btn,
                self.duplicate_graph_btn,
                self.rename_graph_btn,
                self.delete_btn,
                self.move_btn,
            ):
                button.setEnabled(False)
                button.setToolTip("只读模式：节点图库仅用于浏览与跳转，节点图结构与变量请在代码中维护。")
        
        # 主分割窗口
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        
        # 左侧：文件夹树
        left_section = SectionCard("文件夹结构", "管理节点图目录与拖放")
        self.folder_tree = QtWidgets.QTreeWidget()
        self.folder_tree.setHeaderLabel("文件夹")
        self.folder_tree.setObjectName("leftPanel")
        # 不要锁死宽度：该页面使用 QSplitter，左侧树需要允许用户拖拽分隔线改变宽度。
        # 默认宽度仍以主题 token 为基准，但通过 splitter.setSizes(...) 设定初始值。
        self.folder_tree.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)
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
        # 左侧默认收窄，但允许用户拖到更宽
        splitter.setSizes([Sizes.LEFT_PANEL_WIDTH, 1000])
        
        self.body_layout.addWidget(splitter, 1)
        
        # 连接信号
        self.add_graph_btn.clicked.connect(self._add_graph)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.duplicate_graph_btn.clicked.connect(self._duplicate_selected_graph)
        self.rename_graph_btn.clicked.connect(self._rename_selected_graph)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.move_btn.clicked.connect(self._move_graph)
        self.connect_search(self.search_edit, self._filter_graphs, placeholder="搜索节点图...")
        self.folder_tree.itemClicked.connect(self._on_folder_clicked)

        if self.selection_mode:
            self._apply_selection_mode()

        self._install_standard_shortcuts()

    # === 插件扩展：工具栏按钮/控件（幂等）===
    def ensure_extension_toolbar_button(
        self,
        key: str,
        text: str,
        *,
        tooltip: str = "",
        on_clicked: Callable[[], None] | None = None,
        enabled: bool = True,
    ) -> QtWidgets.QPushButton:
        """确保“扩展工具栏”存在一个按钮（幂等）。"""
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar button key 不能为空")

        existing = self._extension_toolbar_buttons.get(normalized_key)
        if existing is not None:
            if not isinstance(existing, QtWidgets.QPushButton):
                raise TypeError(
                    f"extension toolbar key 已存在但不是 QPushButton: key={normalized_key!r}, type={type(existing).__name__}"
                )
            existing.setText(str(text))
            if tooltip:
                existing.setToolTip(str(tooltip))
            existing.setEnabled(bool(enabled))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")

        button = QtWidgets.QPushButton(str(text))
        if tooltip:
            button.setToolTip(str(tooltip))
        button.setEnabled(bool(enabled))
        if on_clicked is not None:
            button.clicked.connect(on_clicked)
        self._extension_toolbar_layout.addWidget(button)
        self._extension_toolbar_buttons[normalized_key] = button
        return button

    def ensure_extension_toolbar_widget(
        self,
        key: str,
        create_widget: Callable[[QtWidgets.QWidget], QtWidgets.QWidget],
        *,
        visible: bool = True,
    ) -> QtWidgets.QWidget:
        """确保“扩展工具栏”存在一个自定义 widget（幂等）。"""
        normalized_key = str(key or "").strip()
        if not normalized_key:
            raise ValueError("extension toolbar widget key 不能为空")
        if normalized_key in self._extension_toolbar_buttons:
            raise RuntimeError(f"extension toolbar key 已被按钮占用：{normalized_key!r}")

        existing = self._extension_toolbar_widgets.get(normalized_key)
        if existing is not None:
            existing.setVisible(bool(visible))
            return existing

        if self._extension_toolbar_layout is None:
            raise RuntimeError("extension toolbar layout 未初始化（_setup_ui 尚未完成）")
        if self._extension_toolbar_widget_host is None:
            raise RuntimeError("extension toolbar host 未初始化（_setup_ui 尚未完成）")

        widget = create_widget(self._extension_toolbar_widget_host)
        if not isinstance(widget, QtWidgets.QWidget):
            raise TypeError(
                f"create_widget 必须返回 QWidget（key={normalized_key!r}, got={type(widget).__name__}）"
            )
        widget.setVisible(bool(visible))
        self._extension_toolbar_layout.addWidget(widget)
        self._extension_toolbar_widgets[normalized_key] = widget
        return widget

    def apply_keymap_shortcuts(self, keymap_store: object) -> None:
        """由主窗口调用：在快捷键配置变更后刷新本页快捷键绑定。"""
        self._install_standard_shortcuts(keymap_store=keymap_store)

    def _resolve_keymap_store(self) -> object | None:
        window_obj = self.window()
        app_state = getattr(window_obj, "app_state", None)
        return getattr(app_state, "keymap_store", None) if app_state is not None else None

    def _clear_standard_shortcuts(self) -> None:
        for shortcut in list(self._standard_shortcuts):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._standard_shortcuts.clear()

    def _primary_shortcut(self, action_id: str) -> str:
        keymap_store = self._resolve_keymap_store()
        get_primary = getattr(keymap_store, "get_primary_shortcut", None) if keymap_store is not None else None
        if callable(get_primary):
            return str(get_primary(action_id) or "")
        defaults = KeymapStore.get_default_shortcuts(action_id)
        return defaults[0] if defaults else ""

    def _install_standard_shortcuts(self, *, keymap_store: object | None = None) -> None:
        """统一快捷键（尽量与其他库页一致）。"""
        resolved = keymap_store if keymap_store is not None else self._resolve_keymap_store()
        get_primary = getattr(resolved, "get_primary_shortcut", None) if resolved is not None else None

        def _primary(action_id: str) -> str:
            if callable(get_primary):
                return str(get_primary(action_id) or "")
            defaults = KeymapStore.get_default_shortcuts(action_id)
            return defaults[0] if defaults else ""

        self._clear_standard_shortcuts()

        shortcut_new = _primary("library.new")
        if shortcut_new:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_new), self)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._add_graph)
            self._standard_shortcuts.append(sc)

        # 删除/重命名/复制/移动：仅在卡片滚动区域聚焦时触发，避免干扰搜索框输入。
        shortcut_dup = _primary("library.duplicate")
        if shortcut_dup:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_dup), self.graph_scroll_area)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._duplicate_selected_graph)
            self._standard_shortcuts.append(sc)

        shortcut_rename = _primary("library.rename")
        if shortcut_rename:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_rename), self.graph_scroll_area)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._rename_selected_graph)
            self._standard_shortcuts.append(sc)

        shortcut_delete = _primary("library.delete")
        if shortcut_delete:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_delete), self.graph_scroll_area)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._delete_selected)
            self._standard_shortcuts.append(sc)

        shortcut_move = _primary("library.move")
        if shortcut_move:
            sc = QtGui.QShortcut(QtGui.QKeySequence(shortcut_move), self.graph_scroll_area)
            sc.setContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._move_graph)
            self._standard_shortcuts.append(sc)


    

    

    
    def _on_sort_changed(self, index: int) -> None:
        """排序方式改变"""
        self.current_sort_by = self.sort_combo.itemData(index)
        self._refresh_graph_list()

    def _apply_selection_mode(self) -> None:
        self.add_folder_btn.hide()
        self.duplicate_graph_btn.hide()
        self.rename_graph_btn.hide()
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
        """刷新节点图库。

        设计目标：
        - 当节点图/复合节点/管理配置等资源被外部工具（或手动）修改后，
          允许用户在节点图库页面内直接触发一次“全局资源库刷新”，避免
          UI 仍保留已不存在的条目并提示源文件缺失。
        - 若当前运行在主窗口上下文：委托主窗口的 `refresh_resource_library()`，
          由 ResourceRefreshService 统一负责缓存失效 + 索引重建 + UI 上下文刷新。
        - 若运行在独立对话框等上下文：本地执行最小闭环（清缓存 + 重建索引 + 强制 reload）。
        """
        window = self.window()
        refresh_resource_library = getattr(window, "refresh_resource_library", None) if window else None
        if callable(refresh_resource_library):
            refresh_resource_library()
            return

        # 独立上下文：尽量与主窗口刷新链路保持一致（但不依赖主窗口服务）。
        self.resource_manager.clear_all_caches()
        self.resource_manager.rebuild_index()
        self.reload()

    def _force_invalidate_graph_library_view_cache(self) -> None:
        """强制失效节点图库 UI 侧快照缓存，确保 reload 不被签名短路。"""
        # GraphListMixin：清理元数据缓存与“刷新签名”，强制重新枚举/排序/增量刷新卡片。
        self._invalidate_graph_metadata()
        setattr(self, "__graph_list_refresh_signature", None)

        # FolderTreeMixin：强制对比快照时视为“结构可能变化”，允许重建树并恢复展开状态。
        setattr(self, "_folder_tree_snapshot", None)

        # 引用追踪缓存同样以资源库指纹为失效条件；reload 语义上需要“看见最新磁盘”。
        if hasattr(self, "reference_tracker") and self.reference_tracker is not None:
            invalidate_cache = getattr(self.reference_tracker, "invalidate_reference_cache", None)
            if callable(invalidate_cache):
                invalidate_cache()

    

    

    

    

    

    

    

    


