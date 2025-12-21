"""复合节点管理库页面与编辑入口。

采用标准库骨架 (DualPaneLibraryScaffold) 与 service 层，将左侧树与中央图编辑解耦，
并复用 GraphEditorController 的加载约束，保持与节点图编辑器一致的体验。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.nodes.advanced_node_features import CompositeNodeConfig, VirtualPinConfig
from engine.nodes.composite_node_manager import CompositeNodeManager, get_composite_node_manager
from engine.nodes.node_registry import get_node_registry
from engine.resources.resource_manager import ResourceManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_index_manager import PackageIndexManager
from app.codegen import CompositeCodeGenerator
from app.ui.controllers.graph_editor_controller import GraphEditorController
from app.ui.foundation import input_dialogs
from app.ui.foundation.context_menu_builder import ContextMenuBuilder
from app.ui.foundation.dialog_utils import ask_yes_no_dialog, show_warning_dialog
from app.ui.foundation.folder_tree_helper import (
    FolderTreeBuilder,
    capture_expanded_paths,
    restore_expanded_paths,
)
from app.ui.foundation.theme_manager import Colors, Sizes, ThemeManager
from app.ui.foundation.toast_notification import ToastNotification
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.graph.library_mixins import SearchFilterMixin, ToolbarMixin, ConfirmDialogMixin
from app.ui.graph.library_pages.library_scaffold import DualPaneLibraryScaffold
from app.ui.panels.panel_scaffold import SectionCard


@dataclass(frozen=True)
class CompositeNodeRow:
    """复合节点在左侧树/列表中的扁平行数据表示。"""

    composite_id: str
    node_name: str
    folder_path: str
    description: str


class CompositeNodeService:
    """复合节点库的应用服务层。

    封装 CompositeNodeManager，提供：
    - iter_rows(): 扁平行数据（名称、文件夹等），供左树/列表渲染；
    - CRUD：create/delete/move 文件夹与复合节点；
    - load/save：按需加载子图并写回 CompositeNodeConfig。
    """

    def __init__(self, workspace_path: Path) -> None:
        self.workspace_path = workspace_path
        registry = get_node_registry(workspace_path, include_composite=True)
        node_library = registry.get_library()
        code_generator = CompositeCodeGenerator(node_library)
        self._manager = get_composite_node_manager(
            workspace_path,
            base_node_library=node_library,
            composite_code_generator=code_generator,
        )

    @property
    def manager(self) -> CompositeNodeManager:
        return self._manager

    def iter_rows(self) -> list[CompositeNodeRow]:
        rows: list[CompositeNodeRow] = []
        for composite_config in self._manager.list_composite_nodes():
            rows.append(
                CompositeNodeRow(
                    composite_id=composite_config.composite_id,
                    node_name=composite_config.node_name,
                    folder_path=composite_config.folder_path or "",
                    description=composite_config.node_description or "",
                )
            )
        return rows

    def list_folders(self) -> list[str]:
        return list(self._manager.folder_manager.folders)

    def load_composite(
        self,
        composite_id: str,
        *,
        ensure_subgraph: bool = True,
    ) -> Optional[CompositeNodeConfig]:
        if ensure_subgraph:
            self._manager.load_subgraph_if_needed(composite_id)
        return self._manager.get_composite_node(composite_id)

    def create_composite(self, folder_path: str) -> str:
        """创建新的复合节点，返回 composite_id。"""
        return self._manager.create_composite_node(
            node_name=None,
            node_description="",
            sub_graph={"nodes": [], "edges": [], "graph_variables": []},
            virtual_pins=[],
            folder_path=folder_path or "",
        )

    def create_folder(self, folder_name: str, parent_folder_path: str) -> bool:
        return self._manager.create_folder(folder_name, parent_folder_path or "")

    def delete_composite(self, composite_id: str) -> Optional[CompositeNodeConfig]:
        composite_config = self._manager.get_composite_node(composite_id)
        if composite_config is None:
            return None
        self._manager.delete_composite_node(composite_id)
        return composite_config

    def delete_folder(self, folder_path: str) -> bool:
        return self._manager.delete_folder(folder_path, force=True)

    def move_composite(self, composite_id: str, target_folder_path: str) -> bool:
        return self._manager.move_to_folder(composite_id, target_folder_path or "")

    def analyze_update_impact(
        self,
        composite_id: str,
        composite_config: CompositeNodeConfig,
    ) -> dict:
        return self._manager.analyze_composite_update_impact(composite_id, composite_config)

    def persist_updated_composite(
        self,
        composite_id: str,
        composite_config: CompositeNodeConfig,
        *,
        skip_impact_check: bool,
    ) -> None:
        self._manager.update_composite_node(
            composite_id,
            composite_config,
            skip_impact_check=skip_impact_check,
        )


class CompositeNodeManagerWidget(
    DualPaneLibraryScaffold,
    SearchFilterMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """复合节点管理库页面。

    - 左侧：复合节点库树（按文件夹组织）；
    - 右侧：复合节点子图预览/编辑区（默认只读预览；显式开启保存能力后才允许落盘）。
    """

    composite_library_updated = QtCore.pyqtSignal()
    composite_selected = QtCore.pyqtSignal(str)

    def __init__(
        self,
        workspace_path: Path,
        node_library: dict,
        parent: Optional[QtWidgets.QWidget] = None,
        resource_manager: Optional[ResourceManager] = None,
        package_index_manager: Optional[PackageIndexManager] = None,
        *,
        edit_session_capabilities: Optional[EditSessionCapabilities] = None,
    ) -> None:
        super().__init__(
            parent,
            title="复合节点库",
            description="浏览复合节点结构并在中间区域加载其子图进行预览；默认可交互预览但不自动落盘（避免误覆盖手写源码结构）。",
        )

        self.workspace_path = workspace_path
        self.node_library = node_library
        self._service = CompositeNodeService(workspace_path)
        self._package_index_manager: Optional[PackageIndexManager] = package_index_manager

        # 复合节点库过滤上下文：由主窗口“当前存档”注入。
        # 约定：
        # - None：不启用过滤（<全部资源>）
        # - set[str]：仅显示指定 composite_id 集合（具体存档 / <未分类资源>）
        self._active_composite_id_filter: set[str] | None = None
        # 向下兼容：外部仍可通过 .manager 访问引擎侧 CompositeNodeManager
        self.manager: CompositeNodeManager = self._service.manager
        # 复合节点编辑会话能力（单一真源）：
        # - 默认：可交互预览（允许移动/连线等交互，但不落盘）
        # - 开启：完整编辑（允许校验 + 落盘保存）
        self._edit_session_capabilities: EditSessionCapabilities = (
            edit_session_capabilities
            if isinstance(edit_session_capabilities, EditSessionCapabilities)
            else EditSessionCapabilities.interactive_preview()
        )
        self._persist_toggle: Optional[QtWidgets.QAbstractButton] = None

        # 复合节点“元信息/虚拟引脚”脏标记（graph 的脏状态由 GraphEditorController 维护）。
        self._composite_meta_dirty: bool = False
        # 防止在程序性选中/回滚选中时递归触发 itemClicked 逻辑。
        self._suppress_tree_item_clicked: bool = False

        # 当前编辑的复合节点
        self.current_composite: Optional[CompositeNodeConfig] = None
        self.current_composite_id: str = ""

        # 节点图编辑相关
        self.graph_model: Optional[GraphModel] = None
        self.graph_scene: Optional[GraphScene] = None
        self.graph_editor_controller: Optional[GraphEditorController] = None

        # UI 组件引用
        self.composite_tree: Optional[QtWidgets.QTreeWidget] = None
        self._search_line_edit: Optional[QtWidgets.QLineEdit] = None
        self._add_node_button: Optional[QtWidgets.QPushButton] = None
        self._add_folder_button: Optional[QtWidgets.QPushButton] = None
        self._delete_button: Optional[QtWidgets.QPushButton] = None
        self.center_title_label: Optional[QtWidgets.QLabel] = None
        self.save_button: Optional[QtWidgets.QPushButton] = None
        self.graph_view: Optional[GraphView] = None
        self._left_section_card: Optional[SectionCard] = None
        self._right_section_card: Optional[SectionCard] = None

        self._build_toolbar_and_search()
        self._build_panes()
        self._init_graph_editor(resource_manager)
        self._refresh_composite_list()

    # ------------------------------------------------------------------ 存档上下文（过滤）

    def set_context(
        self,
        current_package_id: str | None,
        current_package_index: PackageIndex | None,
    ) -> None:
        """注入当前存档上下文，用于过滤左侧复合节点树。

        设计约定：
        - <全部资源>：显示所有复合节点（不启用过滤）
        - 具体存档：仅显示 current_package_index.resources.composites
        - <未分类资源>：显示“未被任何包引用”的复合节点（依赖 PackageIndexManager 汇总）
        """
        self._active_composite_id_filter = self._compute_active_composite_id_filter(
            current_package_id,
            current_package_index,
        )
        self._refresh_composite_list()

    def _compute_active_composite_id_filter(
        self,
        current_package_id: str | None,
        current_package_index: PackageIndex | None,
    ) -> set[str] | None:
        package_id = str(current_package_id or "")
        if not package_id or package_id == "global_view":
            return None
        if package_id == "unclassified_view":
            return self._compute_unclassified_composite_ids()
        if current_package_index is None:
            return set()
        return {
            composite_id
            for composite_id in current_package_index.resources.composites
            if isinstance(composite_id, str) and composite_id
        }

    def _compute_unclassified_composite_ids(self) -> set[str]:
        """计算未分类视图下的复合节点集合：未被任何包的 resources.composites 引用。"""
        # 1) 当前工作区全部复合节点
        all_composite_ids: set[str] = {
            str(cfg.composite_id)
            for cfg in self.manager.list_composite_nodes()
            if isinstance(getattr(cfg, "composite_id", None), str) and cfg.composite_id
        }

        # 2) 已归档（被任意存档索引引用）
        classified_composite_ids: set[str] = set()
        if self._package_index_manager is not None:
            packages = self._package_index_manager.list_packages()
            for pkg_info in packages:
                package_id_value = ""
                if isinstance(pkg_info, dict):
                    package_id_value = str(pkg_info.get("package_id", "") or "")
                if not package_id_value:
                    continue
                resources = self._package_index_manager.get_package_resources(package_id_value)
                if resources is None:
                    continue
                composite_ids = getattr(resources, "composites", [])
                if isinstance(composite_ids, list):
                    for composite_id in composite_ids:
                        if isinstance(composite_id, str) and composite_id:
                            classified_composite_ids.add(composite_id)

        return {composite_id for composite_id in all_composite_ids if composite_id not in classified_composite_ids}

    @staticmethod
    def _collect_visible_folder_paths(rows: list[CompositeNodeRow]) -> list[str]:
        """由可见的复合节点行推导需要构建的文件夹路径集合（含父路径）。"""
        folder_paths: set[str] = set()
        for row in rows:
            raw_folder_path = str(row.folder_path or "")
            normalized = raw_folder_path.replace("\\", "/").strip("/").strip()
            if not normalized:
                continue
            parts = [part for part in normalized.split("/") if part]
            accumulated = ""
            for part in parts:
                accumulated = part if not accumulated else f"{accumulated}/{part}"
                folder_paths.add(accumulated)
        return sorted(folder_paths)

    # ------------------------------------------------------------------ 能力（单一真源）

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._edit_session_capabilities

    @property
    def can_persist_composite(self) -> bool:
        """复合节点页是否允许写回复合节点文件（落盘）。"""
        return bool(self._edit_session_capabilities.can_persist)

    def _set_edit_session_capabilities(self, capabilities: EditSessionCapabilities) -> None:
        """更新能力，并同步到 GraphEditorController/GraphScene 与 UI 控件启用状态。"""
        self._edit_session_capabilities = capabilities
        if self.graph_editor_controller is not None:
            self.graph_editor_controller.set_edit_session_capabilities(capabilities)
        if self.graph_scene is not None:
            self.graph_scene.set_edit_session_capabilities(capabilities)
        self._apply_persist_controls_state()

    # ------------------------------------------------------------------ UI 装配

    def _build_toolbar_and_search(self) -> None:
        """顶部工具栏 + 搜索框（按钮在左，搜索在右）。"""
        toolbar_container = QtWidgets.QWidget(self)
        toolbar_layout = QtWidgets.QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(Sizes.SPACING_SMALL)
        self.init_toolbar(toolbar_layout)

        # 保存能力开关：默认可交互预览（不落盘）；显式开启后允许保存与库结构操作。
        persist_toggle = QtWidgets.QCheckBox("允许保存", toolbar_container)
        persist_toggle.setChecked(bool(self._edit_session_capabilities.can_persist))
        persist_toggle.setToolTip("开启后：允许保存复合节点到文件（必要时会提示覆盖源码并转换为 payload 格式）。")
        persist_toggle.toggled.connect(self._on_persist_toggled)
        self._persist_toggle = persist_toggle

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
            persist_toggle,
            self._add_node_button,
            self._add_folder_button,
            self._delete_button,
        ]
        self.setup_toolbar_with_search(toolbar_layout, buttons, self._search_line_edit)
        self.set_status_widget(toolbar_container)

        self._apply_persist_controls_state()

    def _build_panes(self) -> None:
        """构建左树 + 右编辑区双栏布局。"""
        composite_tree = QtWidgets.QTreeWidget()
        composite_tree.setHeaderLabel("复合节点")
        composite_tree.setObjectName("leftPanel")
        composite_tree.setFixedWidth(Sizes.LEFT_PANEL_WIDTH)
        composite_tree.itemClicked.connect(self._on_tree_item_clicked)
        composite_tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        composite_tree.customContextMenuRequested.connect(self._show_context_menu)
        if not self.can_persist_composite:
            composite_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.NoDragDrop)
            composite_tree.setAcceptDrops(False)
        else:
            composite_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
            composite_tree.setAcceptDrops(True)
        self.composite_tree = composite_tree

        right_container = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(Sizes.SPACING_SMALL)

        title_layout = QtWidgets.QHBoxLayout()
        title_layout.setContentsMargins(0, 0, 0, 0)
        self.center_title_label = QtWidgets.QLabel("选择一个复合节点进行编辑")
        self.center_title_label.setStyleSheet("font-size: 12px; font-weight: bold; padding: 5px;")
        title_layout.addWidget(self.center_title_label)

        self.save_button = QtWidgets.QPushButton("💾 保存")
        self.save_button.clicked.connect(self._save_current_composite)
        title_layout.addWidget(self.save_button)
        right_layout.addLayout(title_layout)

        self.graph_view = GraphView(None)
        self.graph_view.node_library = self.node_library
        right_layout.addWidget(self.graph_view)

        if not self.can_persist_composite:
            self.save_button.setEnabled(False)
            self.save_button.setToolTip("预览模式：复合节点不允许从 UI 保存到文件；可勾选顶部“允许保存”开启落盘。")

        left_section_title = "复合节点库"
        left_section_description = "按文件夹浏览复合节点，选中条目将在右侧加载相应子图用于预览与虚拟引脚配置。"
        right_section_title = "复合节点编辑"
        right_section_description = "中间画布使用统一的节点图编辑器内核，默认仅在内存中尝试修改，不写回源码。"

        left_section, right_section = self.build_dual_pane(
            composite_tree,
            right_container,
            left_title=left_section_title,
            left_description=left_section_description,
            right_title=right_section_title,
            right_description=right_section_description,
        )
        self._left_section_card = left_section
        self._right_section_card = right_section

        self._apply_styles()

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
        )
        self.graph_editor_controller = GraphEditorController(
            resource_manager=resource_manager,
            model=initial_model,
            scene=initial_scene,
            view=self.graph_view,
            node_library=self.node_library,
            edit_session_capabilities=self._edit_session_capabilities,
        )
        self.graph_model = initial_model
        self.graph_scene = initial_scene

    def _apply_styles(self) -> None:
        """应用页面级样式，与其它库页面保持一致。"""
        self.setStyleSheet(
            f"""
            CompositeNodeManagerWidget {{
                background-color: {Colors.BG_MAIN};
            }}
            {ThemeManager.button_style()}
            {ThemeManager.tree_style()}
            {ThemeManager.left_panel_style()}
            {ThemeManager.list_style()}
            {ThemeManager.scrollbar_style()}
        """
        )

    # ------------------------------------------------------------------ 列表刷新与搜索

    def _refresh_composite_list(self) -> None:
        """刷新左侧复合节点树结构。

        行为约定：
        - 尽量恢复当前选中的 composite_id；
        - 若无当前选中且列表非空，则默认选中第一项；
        - 若列表为空，则清空右侧编辑区标题与场景。
        """
        if self.composite_tree is None:
            return

        expanded_state = capture_expanded_paths(self.composite_tree, self._folder_item_key)
        self.composite_tree.clear()
        root_item = self.composite_tree.invisibleRootItem()

        allowed_composite_ids = self._active_composite_id_filter
        all_rows = self._service.iter_rows()
        visible_rows = (
            [row for row in all_rows if row.composite_id in allowed_composite_ids]
            if allowed_composite_ids is not None
            else all_rows
        )

        folder_builder = FolderTreeBuilder(
            data_factory=lambda folder_path: {"type": "folder", "path": folder_path},
        )
        visible_folders = self._collect_visible_folder_paths(visible_rows)
        folder_items = folder_builder.build(root_item, visible_folders)

        preferred_composite_id = self.current_composite_id
        preferred_item: Optional[QtWidgets.QTreeWidgetItem] = None
        first_node_item: Optional[QtWidgets.QTreeWidgetItem] = None

        for row in visible_rows:
            parent_item = folder_items.get(row.folder_path, root_item)
            node_item = QtWidgets.QTreeWidgetItem(parent_item)
            node_item.setText(0, f"🧩 {row.node_name}")
            node_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole,
                {"type": "node", "id": row.composite_id},
            )
            search_tokens = [row.node_name, row.description, row.folder_path]
            search_value = " ".join(token for token in search_tokens if token)
            node_item.setData(
                0,
                QtCore.Qt.ItemDataRole.UserRole + 1,
                search_value.casefold(),
            )

            if first_node_item is None:
                first_node_item = node_item
            if preferred_composite_id and row.composite_id == preferred_composite_id:
                preferred_item = node_item

        self.composite_tree.expandAll()
        restore_expanded_paths(self.composite_tree, expanded_state, self._folder_item_key)

        # 若当前选中项不在过滤结果中：优先落到“列表第一项”，避免右侧空白。
        target_item = preferred_item or first_node_item

        if target_item is not None:
            self.composite_tree.setCurrentItem(target_item)
            self._on_tree_item_clicked(target_item, 0)
        else:
            # 列表为空或无法恢复选中：清空右侧上下文
            self.current_composite = None
            self.current_composite_id = ""
            if self.center_title_label is not None:
                self.center_title_label.setText("暂无复合节点")
            if self.graph_view is not None:
                self.graph_view.setScene(None)
            self.graph_model = None
            self.graph_scene = None

    def _folder_item_key(self, item: QtWidgets.QTreeWidgetItem) -> Optional[str]:
        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if isinstance(item_data, dict) and item_data.get("type") == "folder":
            return str(item_data.get("path") or "")
        return None

    def _on_search_text_changed(self, text: str) -> None:
        """根据关键字过滤左侧树（匹配名称/描述/路径）。"""
        if self.composite_tree is None:
            return
        normalized_query = self.normalize_query(text)
        self._apply_tree_filter(self.composite_tree, normalized_query)

    def _apply_tree_filter(self, tree_widget: QtWidgets.QTreeWidget, normalized_query: str) -> None:
        def match_and_update_visibility(tree_item: QtWidgets.QTreeWidgetItem) -> bool:
            search_value = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
            if search_value is None:
                search_value = tree_item.text(0)
            value_text = str(search_value).casefold()
            if not normalized_query:
                is_match = True
            else:
                is_match = normalized_query in value_text

            has_visible_child = False
            for child_index in range(tree_item.childCount()):
                child_item = tree_item.child(child_index)
                if match_and_update_visibility(child_item):
                    has_visible_child = True

            is_visible = is_match or has_visible_child
            tree_item.setHidden(not is_visible)
            return is_visible

        root_item = tree_widget.invisibleRootItem()
        for row_index in range(root_item.childCount()):
            child_item = root_item.child(row_index)
            match_and_update_visibility(child_item)

    # ------------------------------------------------------------------ 选择与图加载

    def _on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        """树项点击事件：加载选中的复合节点。"""
        if self._suppress_tree_item_clicked:
            return
        _ = column
        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return
        if item_data.get("type") != "node":
            return

        composite_id_value = item_data.get("id")
        composite_id = str(composite_id_value or "")
        if not composite_id:
            return

        if self.current_composite_id and self.current_composite_id != composite_id:
            if not self._confirm_leave_current_composite():
                self._restore_tree_selection(self.current_composite_id)
                return

        composite_config = self._service.load_composite(composite_id, ensure_subgraph=True)
        if composite_config is None:
            show_warning_dialog(self, "错误", "无法加载复合节点")
            return

        self.current_composite = composite_config
        self.current_composite_id = composite_id
        self._composite_meta_dirty = False
        self._load_composite_to_ui(composite_config)

        print(f"[复合节点] 选中节点: {composite_config.node_name} (ID: {composite_id})")
        self.composite_selected.emit(composite_id)

    def _load_composite_to_ui(self, composite: CompositeNodeConfig) -> None:
        """将复合节点元信息与子图加载到 UI。"""
        if self.center_title_label is not None:
            self.center_title_label.setText(f"编辑: {composite.node_name}")

        if composite.composite_id:
            manager_composite = self.manager.get_composite_node(composite.composite_id)
            if manager_composite is not None:
                flow_in_count = sum(
                    1
                    for virtual_pin in manager_composite.virtual_pins
                    if virtual_pin.is_input and virtual_pin.is_flow
                )
                flow_out_count = sum(
                    1
                    for virtual_pin in manager_composite.virtual_pins
                    if (not virtual_pin.is_input) and virtual_pin.is_flow
                )
                print(f"[复合节点] 虚拟引脚统计: 流程入={flow_in_count}, 流程出={flow_out_count}")

        self._load_graph(composite.sub_graph)

    def _restore_tree_selection(self, composite_id: str) -> None:
        """将左侧树的选中项回滚到指定复合节点（不触发加载）。"""
        if not composite_id:
            return
        self._suppress_tree_item_clicked = True
        try:
            self._select_node_in_tree(composite_id)
        finally:
            self._suppress_tree_item_clicked = False

    def _has_unsaved_changes(self) -> bool:
        """判断当前复合节点是否存在未保存的修改。"""
        graph_dirty = False
        if self.graph_editor_controller is not None:
            graph_dirty = bool(self.graph_editor_controller.is_dirty)
        return graph_dirty or self._composite_meta_dirty

    def _confirm_leave_current_composite(self) -> bool:
        """切换复合节点前确认：仅在有脏改动时询问是否保存/放弃/取消切换。"""
        if not self.current_composite or not self.current_composite_id:
            return True
        if not self._has_unsaved_changes():
            return True

        # 预览模式：不允许保存，直接询问是否放弃修改（修改理论上不应产生，但仍防御 UI 误触发）。
        if not self.can_persist_composite:
            message_box = QtWidgets.QMessageBox(self)
            message_box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
            message_box.setWindowTitle("未保存修改")
            message_box.setText(f"复合节点“{self.current_composite.node_name}”存在未保存的修改。\n只读模式下无法保存，切换将丢失这些修改。")
            message_box.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Discard | QtWidgets.QMessageBox.StandardButton.Cancel
            )
            discard_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Discard)
            if discard_button is not None:
                discard_button.setText("放弃修改")
            cancel_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Cancel)
            if cancel_button is not None:
                cancel_button.setText("取消")
            message_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            reply = message_box.exec()
            return reply == QtWidgets.QMessageBox.StandardButton.Discard

        message_box = QtWidgets.QMessageBox(self)
        message_box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        message_box.setWindowTitle("未保存修改")
        message_box.setText(f"复合节点“{self.current_composite.node_name}”有未保存的修改。\n是否在切换前保存？")
        message_box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Save
            | QtWidgets.QMessageBox.StandardButton.Discard
            | QtWidgets.QMessageBox.StandardButton.Cancel
        )
        save_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Save)
        if save_button is not None:
            save_button.setText("保存")
        discard_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Discard)
        if discard_button is not None:
            discard_button.setText("不保存")
        cancel_button = message_box.button(QtWidgets.QMessageBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("取消")
        message_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Save)

        reply = message_box.exec()
        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            return False
        if reply == QtWidgets.QMessageBox.StandardButton.Save:
            self._save_current_composite()
            return True
        return True

    def _load_graph(self, graph_data: dict) -> None:
        """加载子图到编辑器（优先复用 GraphEditorController）。"""
        if not graph_data:
            return

        if self.graph_editor_controller is not None and self.graph_view is not None:
            composite_edit_context = {
                "composite_id": self.current_composite_id,
                "manager": self.manager,
                "on_virtual_pins_changed": self._on_virtual_pins_changed,
                "can_persist": self.can_persist_composite,
            }
            self.graph_editor_controller.load_graph_for_composite(
                self.current_composite_id or "composite_graph",
                graph_data,
                composite_edit_context=composite_edit_context,
            )
            self.graph_model = self.graph_editor_controller.get_current_model()
            self.graph_scene = self.graph_editor_controller.get_current_scene()
        else:
            # 回退：在未注入 ResourceManager 时仍构造独立场景。
            self.graph_model = GraphModel.deserialize(graph_data)
            if self.node_library:
                updated_count = self.graph_model.sync_composite_nodes_from_library(self.node_library)
                if updated_count > 0:
                    print(f"  [复合节点编辑器] 同步了 {updated_count} 个复合节点的端口定义")
            self.graph_scene = GraphScene(
                self.graph_model,
                node_library=self.node_library,
                composite_edit_context={
                    "composite_id": self.current_composite_id,
                    "manager": self.manager,
                    "on_virtual_pins_changed": self._on_virtual_pins_changed,
                    "can_persist": self.can_persist_composite,
                },
                edit_session_capabilities=self._edit_session_capabilities,
            )
            if self.graph_view is not None:
                self.graph_view.setScene(self.graph_scene)
            if self.graph_scene is not None:
                for node_model in self.graph_model.nodes.values():
                    self.graph_scene.add_node_item(node_model)
                for edge_model in self.graph_model.edges.values():
                    self.graph_scene.add_edge_item(edge_model)

        if self.graph_view is not None:
            QtCore.QTimer.singleShot(100, self.graph_view.fit_all)

    def _on_virtual_pins_changed(self) -> None:
        """虚拟引脚被修改后的回调（节点删除导致引脚清理时触发）。"""
        print("[复合节点管理器] 虚拟引脚已更新，触发刷新")
        if self.current_composite_id:
            self.composite_selected.emit(self.current_composite_id)

    # ------------------------------------------------------------------ 树辅助与外部选择接口

    def _select_node_in_tree(self, composite_id: str) -> None:
        """在树中选中指定的复合节点并触发加载。"""
        if self.composite_tree is None:
            return

        root_item = self.composite_tree.invisibleRootItem()

        def find_node_item(parent_item: QtWidgets.QTreeWidgetItem) -> Optional[QtWidgets.QTreeWidgetItem]:
            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                item_data = child_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(item_data, dict) and item_data.get("type") == "node" and item_data.get("id") == composite_id:
                    return child_item
                result_item = find_node_item(child_item)
                if result_item is not None:
                    return result_item
            return None

        target_item = find_node_item(root_item)
        if target_item is not None:
            self.composite_tree.setCurrentItem(target_item)
            self._on_tree_item_clicked(target_item, 0)

    def select_composite_by_name(self, composite_name: str) -> bool:
        """通过名称选中复合节点（供外部导航使用）。"""
        if self.composite_tree is None:
            return False

        root_item = self.composite_tree.invisibleRootItem()

        def find_node_by_name(parent_item: QtWidgets.QTreeWidgetItem, target_name: str) -> Optional[QtWidgets.QTreeWidgetItem]:
            for child_index in range(parent_item.childCount()):
                child_item = parent_item.child(child_index)
                item_data = child_item.data(0, QtCore.Qt.ItemDataRole.UserRole)

                if isinstance(item_data, dict) and item_data.get("type") == "node":
                    composite_id_value = item_data.get("id")
                    composite_id = str(composite_id_value or "")
                    composite_config = self.manager.get_composite_node(composite_id)
                    if composite_config is not None and composite_config.node_name == target_name:
                        return child_item

                result_item = find_node_by_name(child_item, target_name)
                if result_item is not None:
                    return result_item
            return None

        target_item = find_node_by_name(root_item, composite_name)
        if target_item is None:
            return False

        parent_item = target_item.parent()
        if parent_item is not None:
            parent_item.setExpanded(True)

        self.composite_tree.setCurrentItem(target_item)
        self._on_tree_item_clicked(target_item, 0)
        return True

    # ------------------------------------------------------------------ 右键菜单与 CRUD（库结构）

    def _show_context_menu(self, position: QtCore.QPoint) -> None:
        if self.composite_tree is None:
            return
        item = self.composite_tree.itemAt(position)
        if item is None:
            return

        item_data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return

        builder = ContextMenuBuilder(self)
        if not self.can_persist_composite:
            # 只读模式下不提供任何修改库结构的菜单，仅保留空菜单以占位。
            builder.exec_for(self.composite_tree.viewport(), position)
            return

        if item_data.get("type") == "node":
            composite_id_value = item_data.get("id")
            composite_id = str(composite_id_value or "")
            builder.add_action("移动到...", lambda: self._move_node_to_folder(composite_id))
        elif item_data.get("type") == "folder":
            builder.add_action("重命名", lambda: None, enabled=False)

        builder.exec_for(self.composite_tree.viewport(), position)

    def _create_composite_node(self) -> None:
        """创建新的复合节点（默认自动命名，无弹窗）。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中新建复合节点。")
            return
        folder_path = ""
        if self.composite_tree is not None:
            current_item = self.composite_tree.currentItem()
            if current_item is not None:
                item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(item_data, dict) and item_data.get("type") == "folder":
                    folder_path = str(item_data.get("path") or "")

        composite_id = self._service.create_composite(folder_path)
        self._refresh_composite_list()
        self._select_node_in_tree(composite_id)
        self.composite_library_updated.emit()

    def _create_folder(self) -> None:
        """创建新文件夹。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中新建文件夹。")
            return

        parent_folder_path = ""
        if self.composite_tree is not None:
            current_item = self.composite_tree.currentItem()
            if current_item is not None:
                item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                if isinstance(item_data, dict) and item_data.get("type") == "folder":
                    parent_folder_path = str(item_data.get("path") or "")

        folder_name = input_dialogs.prompt_text(self, "新建文件夹", "请输入文件夹名称:")
        if not folder_name:
            return

        if self._service.create_folder(folder_name, parent_folder_path):
            self._refresh_composite_list()
        else:
            show_warning_dialog(self, "错误", f"创建文件夹失败：{folder_name}")

    def _delete_item(self) -> None:
        """删除选中的项（节点或文件夹）。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中删除复合节点或文件夹。")
            return

        if self.composite_tree is None:
            return
        current_item = self.composite_tree.currentItem()
        if current_item is None:
            show_warning_dialog(self, "提示", "请先选择一个项")
            return

        item_data = current_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(item_data, dict):
            return

        if item_data.get("type") == "node":
            composite_id_value = item_data.get("id")
            composite_id = str(composite_id_value or "")
            self._delete_composite_node(composite_id)
        elif item_data.get("type") == "folder":
            folder_path_value = item_data.get("path")
            folder_path = str(folder_path_value or "")
            self._delete_folder(folder_path)

    def _delete_composite_node(self, composite_id: str) -> None:
        """删除指定的复合节点。"""
        if not self.can_persist_composite:
            return

        composite_config = self.manager.get_composite_node(composite_id)
        if composite_config is None:
            return

        if not ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除复合节点 '{composite_config.node_name}' 吗？\n此操作不可撤销。",
        ):
            return

        self._service.delete_composite(composite_id)
        if self.current_composite_id == composite_id:
            self.current_composite = None
            self.current_composite_id = ""
            self.graph_model = None
            self.graph_scene = None
            if self.graph_view is not None:
                self.graph_view.setScene(None)

        self._refresh_composite_list()
        self.composite_library_updated.emit()
        ToastNotification.show_message(self, f"已删除复合节点 '{composite_config.node_name}'。", "success")

    def _delete_folder(self, folder_path: str) -> None:
        """删除指定的文件夹。"""
        if not self.can_persist_composite:
            return

        if not ask_yes_no_dialog(
            self,
            "确认删除",
            f"确定要删除文件夹 '{folder_path}' 吗？\n如果文件夹不为空，将删除其中所有复合节点。\n此操作不可撤销。",
        ):
            return

        if self._service.delete_folder(folder_path):
            self._refresh_composite_list()
            self.composite_library_updated.emit()
            ToastNotification.show_message(self, f"已删除复合节点文件夹 '{folder_path}'。", "success")

    def _move_node_to_folder(self, composite_id: str) -> None:
        """移动节点到文件夹。"""
        if not self.can_persist_composite:
            show_warning_dialog(self, "只读模式", "当前复合节点库为只读模式，不能在 UI 中移动复合节点。")
            return

        folders = ["(根目录)"] + self.manager.folder_manager.folders
        target_folder_caption = input_dialogs.prompt_item(
            self,
            "移动到文件夹",
            "选择目标文件夹:",
            folders,
            current_index=0,
            editable=False,
        )
        if not target_folder_caption:
            return

        target_folder_path = "" if target_folder_caption == "(根目录)" else target_folder_caption
        if self._service.move_composite(composite_id, target_folder_path):
            self._refresh_composite_list()
            self.composite_library_updated.emit()

    # ------------------------------------------------------------------ 虚拟引脚与基本信息（供右侧面板调用）

    def add_virtual_pin(self, is_input: bool) -> None:
        """添加虚拟引脚（由属性面板调用）。"""
        if not self.current_composite:
            show_warning_dialog(self, "提示", "请先选择一个复合节点")
            return

        existing_indices = [virtual_pin.pin_index for virtual_pin in self.current_composite.virtual_pins]
        new_index = max(existing_indices) + 1 if existing_indices else 1

        direction_name = "输入" if is_input else "输出"
        new_pin = VirtualPinConfig(
            pin_index=new_index,
            pin_name=f"{direction_name}_{new_index}",
            pin_type="泛型",
            is_input=is_input,
            description="",
        )
        self.current_composite.virtual_pins.append(new_pin)
        self._composite_meta_dirty = True
        self.composite_selected.emit(self.current_composite_id)

    def remove_virtual_pin(self, pin_index: int) -> None:
        """删除指定的虚拟引脚（由属性面板调用）。"""
        if not self.current_composite:
            return

        self.current_composite.virtual_pins = [
            virtual_pin for virtual_pin in self.current_composite.virtual_pins if virtual_pin.pin_index != pin_index
        ]
        self._composite_meta_dirty = True
        self.composite_selected.emit(self.current_composite_id)

    def update_pin_from_table(self, pin_index: int, name: str, pin_type: str) -> None:
        """更新虚拟引脚的名称与类型（由属性面板调用）。"""
        if not self.current_composite:
            return

        target_pin = next(
            (virtual_pin for virtual_pin in self.current_composite.virtual_pins if virtual_pin.pin_index == pin_index),
            None,
        )
        if target_pin is None:
            return
        target_pin.pin_name = name
        target_pin.pin_type = pin_type
        self._composite_meta_dirty = True

    def update_composite_basic_info(self, name: str, description: str) -> None:
        """更新复合节点基本信息（由属性面板调用）。"""
        if not self.current_composite:
            return

        self.current_composite.node_name = name
        self.current_composite.node_description = description
        self._composite_meta_dirty = True

        if self.center_title_label is not None:
            self.center_title_label.setText(f"编辑: {name}")

    def get_current_composite(self) -> Optional[CompositeNodeConfig]:
        """获取当前编辑的复合节点。"""
        return self.current_composite

    # ------------------------------------------------------------------ 保存（仍保留，只读模式下短路）

    def _save_current_composite(self) -> None:
        """保存当前编辑的复合节点（默认在只读模式下短路，不落盘）。"""
        if not self.current_composite or not self.current_composite_id:
            return
        if not self.can_persist_composite:
            print(f"[预览] 已阻止保存复合节点 {self.current_composite.node_name}")
            return
        if not self._has_unsaved_changes():
            return

        if self.graph_model is not None:
            self.current_composite.sub_graph = self.graph_model.serialize()

        # 保护：若该复合节点文件不是 payload 格式，保存会覆盖原有源码结构（转换为 payload 以保证可解析/可校验）。
        if not self._is_payload_backed_file(self.current_composite_id):
            if not ask_yes_no_dialog(
                self,
                "确认覆盖源码",
                (
                    "该复合节点当前不是“可视化落盘（payload）格式”。\n"
                    "继续保存将覆盖原有 Python 源码结构，并转换为 payload 格式，"
                    "以保证后续可被解析器加载与校验器验证。\n\n"
                    "是否继续？"
                ),
            ):
                print(f"[取消] 用户取消保存复合节点: {self.current_composite.node_name}")
                return

        impact = self._service.analyze_update_impact(self.current_composite_id, self.current_composite)
        if impact.get("has_impact", False):
            if not self._show_impact_confirmation_dialog(impact):
                print(f"[取消] 用户取消保存复合节点: {self.current_composite.node_name}")
                return

        self._service.persist_updated_composite(
            self.current_composite_id,
            self.current_composite,
            skip_impact_check=True,
        )
        self._composite_meta_dirty = False
        if self.graph_editor_controller is not None:
            self.graph_editor_controller.mark_as_saved()

    def _is_payload_backed_file(self, composite_id: str) -> bool:
        """判断复合节点文件是否为 payload 落盘格式。"""
        file_path = getattr(self.manager, "composite_index", {}).get(composite_id)
        if file_path is None:
            return False
        if not file_path.exists():
            return False
        with open(file_path, "r", encoding="utf-8") as file:
            code = file.read()
        return "COMPOSITE_PAYLOAD_JSON" in code

    def _on_persist_toggled(self, checked: bool) -> None:
        """顶部“允许保存”开关回调。"""
        capabilities = EditSessionCapabilities.full_editing() if checked else EditSessionCapabilities.interactive_preview()
        self._set_edit_session_capabilities(capabilities)
        # 切换能力后：若当前已加载子图，重载一次以把 can_persist 写入 composite_edit_context。
        if self.current_composite is not None:
            self._load_composite_to_ui(self.current_composite)

    def _apply_persist_controls_state(self) -> None:
        """根据 can_persist 统一更新写入相关控件的启用/提示。"""
        is_enabled = bool(self.can_persist_composite)
        if self._add_node_button is not None:
            self._add_node_button.setEnabled(is_enabled)
            self._add_node_button.setToolTip("" if is_enabled else "预览模式：禁止在 UI 中新建复合节点。")
        if self._add_folder_button is not None:
            self._add_folder_button.setEnabled(is_enabled)
            self._add_folder_button.setToolTip("" if is_enabled else "预览模式：禁止在 UI 中新建文件夹。")
        if self._delete_button is not None:
            self._delete_button.setEnabled(is_enabled)
            self._delete_button.setToolTip("" if is_enabled else "预览模式：禁止在 UI 中删除复合节点或文件夹。")
        if self.save_button is not None:
            self.save_button.setEnabled(is_enabled)
            self.save_button.setToolTip("" if is_enabled else "预览模式：不允许保存复合节点到文件。")

    def _show_impact_confirmation_dialog(self, impact: dict) -> bool:
        """显示复合节点更新影响的确认对话框。"""
        removed_pins = impact.get("removed_pins", [])
        changed_pins = impact.get("changed_pins", [])
        affected_graphs = impact.get("affected_graphs", [])
        total_connections = impact.get("total_affected_connections", 0)

        if not self.current_composite:
            return False

        message_lines: list[str] = [
            f"复合节点 '{self.current_composite.node_name}' 的修改会影响其他节点图：\n"
        ]

        if removed_pins:
            message_lines.append(f"⚠️  删除了 {len(removed_pins)} 个引脚：")
            for pin_name in removed_pins[:5]:
                message_lines.append(f"   • {pin_name}")
            if len(removed_pins) > 5:
                message_lines.append(f"   ... 还有 {len(removed_pins) - 5} 个")
            message_lines.append("")

        if changed_pins:
            message_lines.append(f"⚠️  修改了 {len(changed_pins)} 个引脚的类型：")
            for pin_name in changed_pins[:5]:
                message_lines.append(f"   • {pin_name}")
            if len(changed_pins) > 5:
                message_lines.append(f"   ... 还有 {len(changed_pins) - 5} 个")
            message_lines.append("")

        message_lines.append("📊 影响范围：")
        message_lines.append(f"   • {len(affected_graphs)} 个节点图")
        message_lines.append(f"   • {total_connections} 条连线将被自动断开\n")

        message_lines.append("受影响的节点图：")
        for graph in affected_graphs[:5]:
            graph_name = graph.get("graph_name", "")
            connection_count = graph.get("connection_count", 0)
            message_lines.append(f"   • {graph_name} ({connection_count} 条连线)")
        if len(affected_graphs) > 5:
            message_lines.append(f"   ... 还有 {len(affected_graphs) - 5} 个节点图")

        message_lines.append("\n⚡ 确认保存后，受影响的连线会自动断开。")
        message_lines.append("您确定要保存这些修改吗？")

        message_text = "\n".join(message_lines)
        return ask_yes_no_dialog(
            self,
            "确认保存复合节点",
            message_text,
        )


