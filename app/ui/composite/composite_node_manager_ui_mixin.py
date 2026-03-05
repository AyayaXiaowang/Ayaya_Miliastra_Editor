"""CompositeNodeManagerWidget 的 UI 装配 mixin。

拆分目标：避免 `composite_node_manager_widget.py` 继续膨胀为巨石文件。
"""

from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.resources.resource_manager import ResourceManager
from app.ui.controllers.graph_editor_controller import GraphEditorController
from app.ui.foundation.shared_resource_badge_delegate import install_shared_resource_badge_delegate
from app.ui.foundation.theme_manager import Sizes
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.panels.panel_scaffold import SectionCard


class CompositeNodeManagerUiMixin:
    def _build_toolbar_and_search(self) -> None:
        """顶部工具栏 + 搜索框（按钮在左，搜索在右）。"""
        toolbar_container = QtWidgets.QWidget(self)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        self.init_toolbar(toolbar_layout)

        self._add_node_button = QtWidgets.QPushButton("+ 新建节点", toolbar_container)
        self._add_folder_button = QtWidgets.QPushButton("+ 新建文件夹", toolbar_container)
        self._delete_button = QtWidgets.QPushButton("删除", toolbar_container)
        for button in (self._add_node_button, self._add_folder_button, self._delete_button):
            button.setMinimumHeight(Sizes.BUTTON_HEIGHT)

        self._add_node_button.clicked.connect(self._create_composite_node)
        self._add_folder_button.clicked.connect(self._create_folder)
        self._delete_button.clicked.connect(self._delete_item)

        self._search_line_edit = QtWidgets.QLineEdit(toolbar_container)
        self._search_line_edit.setPlaceholderText("搜索复合节点...")
        self._search_line_edit.setMinimumHeight(Sizes.INPUT_HEIGHT)
        self.connect_search(self._search_line_edit, self._on_search_text_changed, placeholder="搜索复合节点...")

        buttons: list[QtWidgets.QAbstractButton] = [
            self._add_node_button,
            self._add_folder_button,
            self._delete_button,
        ]
        self.setup_toolbar_with_search(toolbar_layout, buttons, self._search_line_edit)
        self.set_status_widget(toolbar_container)

        self._apply_persist_controls_state()

    def _build_pages(self) -> None:
        """构建：浏览页（左文件夹 + 中间列表）与预览页（子图预览）。"""
        page_stack = QtWidgets.QStackedWidget(self)
        self._page_stack = page_stack
        self.body_layout.addWidget(page_stack, 1)

        # ------------------------------ 浏览页：左侧文件夹树 + 中间复合节点列表
        browse_page = QtWidgets.QWidget(self)
        browse_layout = QtWidgets.QVBoxLayout(browse_page)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(0)

        browse_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, browse_page)

        folder_tree = QtWidgets.QTreeWidget(browse_page)
        folder_tree.setHeaderLabel("文件夹")
        folder_tree.setObjectName("leftPanel")
        # 不要锁死宽度：该页面使用 QSplitter，左侧文件夹树需要允许用户拖拽分隔线改变宽度。
        # 默认宽度仍以主题 token 为基准，初始分配由 splitter.setSizes(...) 负责。
        folder_tree.setMinimumWidth(Sizes.LEFT_PANEL_WIDTH)
        # 与节点图库一致：选中态覆盖展开箭头/缩进区域，避免只高亮文本区造成“断裂”观感。
        # 注意：不在页面级 setStyleSheet 中覆盖 left_panel_style，保持与节点图库相同的 tree_style 选中态。
        folder_tree.setStyleSheet("QTreeWidget#leftPanel { show-decoration-selected: 1; }")
        folder_tree.itemClicked.connect(self._on_folder_item_clicked)
        folder_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        folder_tree.customContextMenuRequested.connect(self._show_folder_context_menu)
        self.folder_tree = folder_tree

        composite_list = QtWidgets.QListWidget(browse_page)
        composite_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        composite_list.itemClicked.connect(self._on_composite_item_clicked)
        composite_list.itemDoubleClicked.connect(self._on_composite_item_double_clicked)
        composite_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        composite_list.customContextMenuRequested.connect(self._show_composite_list_context_menu)
        self.composite_list = composite_list
        install_shared_resource_badge_delegate(composite_list)

        folder_section = SectionCard("文件夹结构", "按文件夹浏览复合节点")
        folder_section.add_content_widget(folder_tree, stretch=1)
        browse_splitter.addWidget(folder_section)

        list_section = SectionCard("复合节点列表", "单击选中并查看右侧面板；双击打开子图预览")
        list_section.add_content_widget(composite_list, stretch=1)
        browse_splitter.addWidget(list_section)

        browse_splitter.setStretchFactor(0, 0)
        browse_splitter.setStretchFactor(1, 1)
        # 左侧默认收窄，但允许用户拖到更宽
        browse_splitter.setSizes([Sizes.LEFT_PANEL_WIDTH, 1000])
        browse_layout.addWidget(browse_splitter, 1)

        # ------------------------------ 预览页：画布预览（返回列表通过再次点击左侧导航“复合节点”）
        preview_page = QtWidgets.QWidget(self)
        preview_layout = QtWidgets.QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.graph_view = GraphView(None)
        self.graph_view.node_library = self.node_library
        preview_layout.addWidget(self.graph_view, 1)

        self._browse_page = browse_page
        self._preview_page = preview_page
        page_stack.addWidget(browse_page)
        page_stack.addWidget(preview_page)
        page_stack.setCurrentWidget(browse_page)

    def _init_graph_editor(self, resource_manager: Optional[ResourceManager]) -> None:
        """初始化图编辑控制器（如注入了 ResourceManager 则复用统一编辑核心）。"""
        if resource_manager is None or self.graph_view is None:
            return

        initial_model = GraphModel.deserialize({"nodes": [], "edges": [], "graph_variables": []})
        initial_scene = GraphScene(
            initial_model,
            read_only=bool(self._edit_session_capabilities.is_read_only),
            node_library=self.node_library,
            edit_session_capabilities=self._edit_session_capabilities,
            # 复合节点库预览页：只读但允许拖拽节点，便于查看大图局部结构（修改不落盘）。
            allow_node_drag_in_read_only=True,
        )
        self.graph_editor_controller = GraphEditorController(
            resource_manager=resource_manager,
            model=initial_model,
            scene=initial_scene,
            view=self.graph_view,
            node_library=self.node_library,
            edit_session_capabilities=self._edit_session_capabilities,
        )
        # 统一确保后续 load_pipeline 创建的新 GraphScene 也继承“只读但可拖拽”的行为。
        self.graph_editor_controller.set_scene_extra_options({"allow_node_drag_in_read_only": True})
        self.graph_model = initial_model
        self.graph_scene = initial_scene

    def _apply_persist_controls_state(self) -> None:
        """根据 can_persist 统一更新写入相关控件的启用/提示。"""
        is_enabled = bool(self.can_persist_composite)
        if self._add_node_button is not None:
            self._add_node_button.setEnabled(is_enabled)
            self._add_node_button.setToolTip("" if is_enabled else "只读模式：复合节点库仅用于浏览，不能在 UI 中新建复合节点。")
        if self._add_folder_button is not None:
            self._add_folder_button.setEnabled(is_enabled)
            self._add_folder_button.setToolTip("" if is_enabled else "只读模式：复合节点库仅用于浏览，不能在 UI 中新建文件夹。")
        if self._delete_button is not None:
            self._delete_button.setEnabled(is_enabled)
            self._delete_button.setToolTip("" if is_enabled else "只读模式：复合节点库仅用于浏览，不能在 UI 中删除复合节点或文件夹。")


