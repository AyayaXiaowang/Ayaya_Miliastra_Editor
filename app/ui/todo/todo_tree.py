from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from app.runtime.services.graph_data_service import GraphDataService
from app.ui.foundation.refresh_gate import RefreshGate
from app.ui.todo.todo_runtime_state import TodoRuntimeState
from app.ui.todo.todo_tree_build_mixin import TodoTreeBuildMixin
from app.ui.todo.todo_tree_data_mixin import TodoTreeDataMixin
from app.ui.todo.todo_tree_events_mixin import TodoTreeEventsMixin
from app.ui.todo.todo_tree_graph_support import TodoTreeGraphSupport
from app.ui.todo.todo_tree_highlight_mixin import TodoTreeHighlightMixin
from app.ui.todo.todo_tree_lazy_mixin import TodoTreeLazyMixin
from app.ui.todo.todo_tree_node_highlight import TodoTreeNodeHighlighter
from app.ui.todo.todo_tree_refresh_mixin import TodoTreeRefreshMixin
from app.ui.todo.todo_tree_source_tooltip import TodoTreeSourceTooltipProvider


class TodoTreeManager(
    TodoTreeDataMixin,
    TodoTreeHighlightMixin,
    TodoTreeRefreshMixin,
    TodoTreeEventsMixin,
    TodoTreeBuildMixin,
    TodoTreeLazyMixin,
    QtCore.QObject,
):
    """负责：树构建、懒加载、增量刷新、三态/样式。

    与 UI 解耦：
    - 外部传入 QTreeWidget 与 runtime_state；
    - 对外暴露 `todo_checked` 信号；
    - 仅将“选中变化”回调回宿主，由宿主决定右侧面板切换。
    """

    todo_checked = QtCore.pyqtSignal(str, bool)  # todo_id, checked

    def __init__(
        self,
        tree: QtWidgets.QTreeWidget,
        runtime_state: TodoRuntimeState,
        rich_segments_role: int,
        parent=None,
        graph_expand_dependency_getter: Optional[Callable[[], Optional[Tuple[Any, ...]]]] = None,
        graph_data_service_getter: Optional[Callable[[], GraphDataService]] = None,
    ) -> None:
        super().__init__(parent)
        self.tree = tree
        self.runtime_state = runtime_state
        self.RICH_SEGMENTS_ROLE = rich_segments_role
        self._viewport: Optional[QtWidgets.QWidget] = None

        # 运行态数据：由上层一次性注入，后续仅在本类内部增量维护。
        # 注意：todos/todo_states 引用外部传入的容器，todo_map 作为集中索引在此处维护。
        self.todos: List[TodoItem] = []
        self.todo_map: Dict[str, TodoItem] = {}
        self.todo_states: Dict[str, bool] = {}

        self._item_map: Dict[str, QtWidgets.QTreeWidgetItem] = {}
        self._refresh_gate = RefreshGate(self.tree)
        self._structure_signature: Optional[tuple] = None
        self._graph_support = TodoTreeGraphSupport(
            self.tree,
            self.RICH_SEGMENTS_ROLE,
            graph_data_service_getter=graph_data_service_getter,
        )
        # 懒加载图步骤所需的依赖解析器：由宿主注入 (package, resource_manager)，避免直接依赖 MainWindow。
        self._graph_expand_dependency_getter = graph_expand_dependency_getter
        # UI 辅助状态：当前高亮的“块分组”头节点
        self._current_block_header_item: Optional[QtWidgets.QTreeWidgetItem] = None
        # UI 辅助状态：当前因“节点选中”而高亮的 Todo ID 集合
        self._current_node_highlight_ids: set[str] = set()
        # UI 辅助状态：当前“节点选中高亮”模式下的锚点步骤（通常为创建步骤）
        self._current_node_anchor_todo_id: Optional[str] = None
        # UI 辅助状态：当前是否处于“按节点过滤步骤”的置灰模式
        self._node_filter_active: bool = False
        # 富文本委托使用的“置灰标记”角色：约定为富文本角色之后的一个自定义角色。
        self.DIMMED_ROLE: int = self.RICH_SEGMENTS_ROLE + 1
        # 树项“标记”角色：用于区分逻辑块头等非 Todo 树项。
        # 注意：必须与 DIMMED_ROLE 分离，避免 role 冲突导致 block_header 被误当成 dimmed。
        self.MARKER_ROLE: int = int(Qt.ItemDataRole.UserRole) + 20
        self._node_highlighter = TodoTreeNodeHighlighter(
            self.tree,
            rich_segments_role=self.RICH_SEGMENTS_ROLE,
            dimmed_role=self.DIMMED_ROLE,
        )
        self._source_tooltip_provider = TodoTreeSourceTooltipProvider(graph_expand_dependency_getter)

        # 事件流根（event_flow_root）的子步骤 UI 懒加载：
        # - Todo 数据在后台生成后已具备 children 列表，但树上不立即创建数千个子项；
        # - 当用户展开事件流根时，再以分批方式挂载其子步骤，保证 UI 始终可交互。
        self._event_flow_children_pending: set[str] = set()
        self._event_flow_children_built: set[str] = set()
        self._event_flow_build_inflight: dict[str, bool] = {}
        self._event_flow_build_callbacks: dict[str, list[Callable[[bool], None]]] = {}
        self._event_flow_loading_items: dict[str, QtWidgets.QTreeWidgetItem] = {}
        # “按需定位”请求：执行过程中可能需要在事件流根尚未构建子树项时选中某一步，
        # 这里记录等待者并在分批挂载过程中尽快触发回调。
        # 结构：flow_root_id -> [(target_todo_id, callback)]
        self._event_flow_item_waiters: dict[str, list[tuple[str, Callable[[QtWidgets.QTreeWidgetItem], None]]]] = {}

        # 槽连接
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.itemExpanded.connect(self._on_tree_item_expanded)
        self.runtime_state.status_changed.connect(self._on_runtime_status_changed)

        # Tooltip 仅在真正需要显示时才计算（避免为大树的每个步骤提前做 IO/反序列化）
        self._viewport = self.tree.viewport()
        if self._viewport is not None:
            self._viewport.installEventFilter(self)



