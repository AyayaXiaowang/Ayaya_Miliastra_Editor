"""复合节点管理库页面与编辑入口。

该文件保持对外入口（`CompositeNodeManagerWidget`）不变，但将巨石实现拆分到同目录下的：
- `composite_node_manager_service.py`：无 Qt 的 service 与行数据结构
- `composite_node_manager_*_mixin.py`：按职责拆分的 UI 行为 mixin

目标：减少单文件体积，降低循环依赖与维护成本。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from engine.graph.models.graph_model import GraphModel
from engine.nodes.advanced_node_features import CompositeNodeConfig
from engine.nodes.composite_node_manager import CompositeNodeManager
from engine.resources.package_index import PackageIndex
from engine.resources.package_index_manager import PackageIndexManager
from engine.resources.resource_manager import ResourceManager
from app.models.edit_session_capabilities import EditSessionCapabilities
from app.ui.controllers.graph_editor_controller import GraphEditorController
from app.ui.graph.graph_scene import GraphScene
from app.ui.graph.graph_view import GraphView
from app.ui.graph.library_mixins import ConfirmDialogMixin, SearchFilterMixin, ToolbarMixin
from app.ui.graph.library_pages.library_scaffold import DualPaneLibraryScaffold
from app.ui.composite.composite_node_manager_browse_mixin import CompositeNodeManagerBrowseMixin
from app.ui.composite.composite_node_manager_context_menu_mixin import CompositeNodeManagerContextMenuMixin
from app.ui.composite.composite_node_manager_save_mixin import CompositeNodeManagerSaveMixin
from app.ui.composite.composite_node_manager_selection_mixin import CompositeNodeManagerSelectionMixin
from app.ui.composite.composite_node_manager_service import CompositeNodeRow, CompositeNodeService
from app.ui.composite.composite_node_manager_ui_mixin import CompositeNodeManagerUiMixin

# 兼容：历史上可能有人从本模块 import 这两个名字
__all__ = [
    "CompositeNodeManagerWidget",
    "CompositeNodeRow",
    "CompositeNodeService",
]


class CompositeNodeManagerWidget(
    CompositeNodeManagerUiMixin,
    CompositeNodeManagerBrowseMixin,
    CompositeNodeManagerSelectionMixin,
    CompositeNodeManagerContextMenuMixin,
    CompositeNodeManagerSaveMixin,
    DualPaneLibraryScaffold,
    SearchFilterMixin,
    ToolbarMixin,
    ConfirmDialogMixin,
):
    """复合节点管理库页面。

    - 浏览页：左侧文件夹列表 + 中间复合节点列表；
    - 预览页：双击列表条目后进入，展示该复合节点的子图预览/编辑区（默认只读预览；显式开启保存能力后才允许落盘）。
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
            description="浏览复合节点结构：左侧文件夹 + 中间列表；双击条目进入子图预览页。返回列表通过再次点击左侧导航“复合节点”。（库页只读浏览）",
        )

        self.workspace_path = workspace_path
        self.node_library = node_library
        self._service = CompositeNodeService(workspace_path)
        self._package_index_manager: Optional[PackageIndexManager] = package_index_manager

        # 复合节点库过滤上下文：由主窗口“当前存档”注入。
        # 约定：
        # - None：不启用过滤（<共享资源>）
        # - set[str]：仅显示指定 composite_id 集合（具体存档）
        self._active_composite_id_filter: set[str] | None = None
        # 向下兼容：外部仍可通过 .manager 访问引擎侧 CompositeNodeManager
        self.manager: CompositeNodeManager = self._service.manager
        # 复合节点编辑会话能力（单一真源）：
        # - 默认：只读预览（与“节点图库”一致：库页仅用于浏览与跳转，不在 UI 内修改/落盘）
        self._edit_session_capabilities: EditSessionCapabilities = (
            edit_session_capabilities
            if isinstance(edit_session_capabilities, EditSessionCapabilities)
            # 复合节点库预览页需要“自动排版”入口：自动排版自身会做校验并仅影响当前进程内视图坐标，
            # 不等价于允许编辑或落盘，因此这里保持只读（can_interact=False/can_persist=False），但允许校验。
            else EditSessionCapabilities.read_only_preview().with_overrides(can_validate=True)
        )

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
        self.folder_tree: Optional[QtWidgets.QTreeWidget] = None
        self.composite_list: Optional[QtWidgets.QListWidget] = None
        self._page_stack: Optional[QtWidgets.QStackedWidget] = None
        self._browse_page: Optional[QtWidgets.QWidget] = None
        self._preview_page: Optional[QtWidgets.QWidget] = None
        self._search_line_edit: Optional[QtWidgets.QLineEdit] = None
        self._add_node_button: Optional[QtWidgets.QPushButton] = None
        self._add_folder_button: Optional[QtWidgets.QPushButton] = None
        self._delete_button: Optional[QtWidgets.QPushButton] = None
        self.graph_view: Optional[GraphView] = None
        # 左侧文件夹树的“当前选择”由两部分构成：
        # - scope: all / project / shared
        # - path: 该 scope 下的相对 folder_path（空字符串表示该 scope 的根）
        # 约定：默认以“全部”视图展示（项目在前、共享在后），与节点图库一致。
        self._current_folder_scope: str = "all"
        self._current_folder_path: str = ""

        self._build_toolbar_and_search()
        self._build_pages()
        self._init_graph_editor(resource_manager)
        self._refresh_composite_list()

    # ------------------------------------------------------------------ 能力（单一真源）

    @property
    def edit_session_capabilities(self) -> EditSessionCapabilities:
        return self._edit_session_capabilities

    @property
    def can_persist_composite(self) -> bool:
        """复合节点页是否允许写回复合节点文件（落盘）。"""
        return bool(self._edit_session_capabilities.can_persist)

    # ------------------------------------------------------------------ 上下文入口（类型提示）

    def set_context(self, current_package_id: str | None, current_package_index: PackageIndex | None) -> None:  # noqa: D401
        # 实现拆分在 CompositeNodeManagerBrowseMixin；这里仅保留 signature 以便 IDE 友好。
        return super().set_context(current_package_id, current_package_index)  # type: ignore[misc]



