from typing import Dict, List, Optional, Set

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt

from app.models import TodoItem
from engine.configs.settings import settings
from app.ui.todo.todo_config import StepTypeRules
from app.ui.todo.todo_preview_panel import TodoPreviewPanel
from app.ui.todo.todo_detail_panel import TodoDetailPanel
from app.ui.todo.todo_tree import TodoTreeManager
from app.ui.todo.todo_executor_bridge import TodoExecutorBridge
from app.ui.todo.todo_context_menu import TodoContextMenu
from app.ui.todo.todo_runtime_state import TodoRuntimeState
from app.ui.todo.recognition_backfill_planner import (
    plan_recognition_backfill,
    get_created_node_id_from_detail,
)
from app.ui.todo.todo_ui_context import TodoUiContext


def _is_step_auto_checkable(detail_info: Optional[Dict]) -> bool:
    """判断给定步骤是否适合在识别回填时被自动勾选为“已完成”。

    具体类型集合集中由 `StepTypeRules.AUTO_CHECK_GRAPH_STEP_TYPES` 维护。
    """
    if not isinstance(detail_info, dict):
        return False
    detail_type = detail_info.get("type", "")
    return StepTypeRules.is_auto_checkable_step(detail_type)


class _RecognitionBackfillCoordinator:
    """封装“识别结果 → 任务清单回填”的解析与自动勾选逻辑。

    负责：
    - 根据当前预览图与可见节点列表，定位所属事件流根与最新可见创建步骤；
    - 选中对应 Todo，并在事件流内对之前的可见步骤执行“自动勾选”；
    - 保持父/分组节点三态由 `TodoTreeManager` 统一反推。
    """

    def __init__(self, orchestrator: "TodoListOrchestrator") -> None:
        self._orchestrator = orchestrator

    @property
    def host(self) -> "TodoListWidget":
        return self._orchestrator.host

    def handle_focus_succeeded(self, visible_node_ids: list[str]) -> None:
        """执行监控完成“定位镜头”后的回填：跳转到最新可见创建步骤并回填完成度。"""
        host = self.host
        if not isinstance(visible_node_ids, list) or not visible_node_ids:
            return

        recognized_node_ids: Set[str] = {
            str(node_identifier) for node_identifier in visible_node_ids
        }
        graph_id, _graph_data, _container = host.preview_panel.get_current_graph_info()
        current_graph_id = graph_id

        candidate_flows = self._collect_candidate_event_flows(current_graph_id)
        if not candidate_flows:
            return

        selected_flow = self._resolve_selected_event_flow_root()
        todo_map: Dict[str, TodoItem] = host.tree_manager.todo_map
        progress = plan_recognition_backfill(
            recognized_node_ids,
            candidate_flows,
            selected_flow,
            todo_map,
        )
        if progress is None:
            return

        # 选中最新可见的创建步骤
        self._orchestrator.select_task_by_id(progress.step_todo.todo_id)
        # 自动勾选事件流中位于该步骤之前的“已完成”步骤
        self._auto_check_steps_before_index(
            progress.flow_todo, progress.step_index_in_flow
        )

    def _collect_candidate_event_flows(
        self,
        current_graph_id: Optional[str],
    ) -> List[TodoItem]:
        """根据当前预览图筛选候选事件流根。"""
        host = self.host
        candidate_flows: List[TodoItem] = []
        for todo in host.todos:
            info = todo.detail_info or {}
            detail_type = info.get("type", "")
            if not StepTypeRules.is_event_flow_root(detail_type):
                continue
            if (current_graph_id is None) or (info.get("graph_id") == current_graph_id):
                candidate_flows.append(todo)
        return candidate_flows

    def _resolve_selected_event_flow_root(self) -> Optional[TodoItem]:
        """从当前树选中项推导其所属的事件流根（若存在）。"""
        host = self.host
        selected_items = host.tree.selectedItems()
        if not selected_items:
            return None
        selected_todo_id = selected_items[0].data(0, Qt.ItemDataRole.UserRole)
        if not selected_todo_id:
            return None
        return host.tree_manager.find_event_flow_root_for_todo(selected_todo_id)

    def _auto_check_steps_before_index(
        self,
        flow_todo: TodoItem,
        last_completed_step_index: int,
    ) -> None:
        """根据事件流内的位置，自动勾选之前的已完成步骤。

        - 仅作用于 leaf 图步骤等“可自动勾选”的节点
        - 父节点/分组节点的三态由 TodoTreeManager 通过叶子状态反推
        """
        if last_completed_step_index <= 0:
            return
        host = self.host

        # 识别回填场景下的自动勾选只应更新当前会话的任务状态，
        # 不应触发外层“每次勾选都立即落盘”的持久化路径。
        # 因此这里使用 TodoTreeManager 的静默勾选 API，而不是直接 setCheckState。
        for child_index in range(last_completed_step_index):
            child_id = flow_todo.children[child_index]
            child_todo = host.tree_manager.todo_map.get(child_id)
            if not child_todo:
                continue
            self._auto_check_single_todo(child_todo)

    def _auto_check_single_todo(self, todo: TodoItem) -> None:
        """递归对子树中“可自动勾选”的叶子步骤打勾。"""
        host = self.host

        if todo.children:
            for child_id in todo.children:
                child_todo = host.tree_manager.todo_map.get(child_id)
                if child_todo is not None:
                    self._auto_check_single_todo(child_todo)
            return

        if not _is_step_auto_checkable(todo.detail_info):
            return

        host.tree_manager.set_leaf_checked_silent(todo.todo_id, True)


class TodoListOrchestrator:
    """任务清单编排层：负责子组件创建与信号连线，不直接持有 UI 状态。

    设计目标：
    - 将 `TodoListWidget` 压缩为“布局 + 样式 + 对外接口”，便于阅读与调试
    - 将运行态对象（树管理/预览/详情/执行桥/右键菜单）的创建与 wiring 集中到一个地方
    - 所有领域相关入口（加载任务、选中变化、执行入口、识别联动）统一从这里经过
    """

    def __init__(self, ui_context: TodoUiContext) -> None:
        self.ui_context = ui_context
        self.host = ui_context.host
        self._recognition_coordinator = _RecognitionBackfillCoordinator(self)
        self._monitor_panel_for_execute_controls = None
        self._setup_subcomponents()
        self._wire_signals()

    # === 子组件创建 ===

    def _setup_subcomponents(self) -> None:
        host = self.host
        # 运行态/树/预览/详情
        host.runtime_state = TodoRuntimeState(host)
        host.tree_manager = TodoTreeManager(
            host.tree,
            host.runtime_state,
            host.RICH_SEGMENTS_ROLE,
            host,
            graph_expand_dependency_getter=self.ui_context.build_graph_expand_dependencies,
        )
        host.preview_panel = TodoPreviewPanel(host.right_stack, self.ui_context)
        host.detail_panel = TodoDetailPanel(host.right_stack)
        host.detail_panel.host_list_widget = host

        # 装入右侧堆叠页（索引顺序：0=详情，1=预览）
        host.right_stack.insertWidget(0, host.detail_panel)
        host.right_stack.insertWidget(1, host.preview_panel)

        # 右键菜单与执行桥（todo_map 统一由 TodoTreeManager 维护）
        host._context_menu = TodoContextMenu(host, host.tree, host.tree_manager)
        host.executor_bridge = TodoExecutorBridge(
            host,
            ui_context=self.ui_context,
            tree_manager=host.tree_manager,
            runtime_state=host.runtime_state,
            preview_panel=host.preview_panel,
            rich_segments_role=host.RICH_SEGMENTS_ROLE,
        )

    def _wire_signals(self) -> None:
        host = self.host
        # 树选择变化 → 详情/预览
        host.tree.currentItemChanged.connect(self.on_selection_changed)
        # 右键菜单：统一由 TodoContextMenu 构建并调用执行桥
        host.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        host.tree.customContextMenuRequested.connect(self._on_tree_context_menu_requested)

        # 转发树的勾选信号，保持对外信号不变
        host.tree_manager.todo_checked.connect(host.todo_checked.emit)

        # 预览与详情的执行入口统一路由到执行桥
        host.detail_panel.execute_clicked.connect(self.on_execute_clicked)
        host.preview_panel.execute_clicked.connect(self.on_execute_clicked)

        # 预览与详情的“执行剩余步骤”统一路由到执行桥
        host.detail_panel.execute_remaining_clicked.connect(self.on_execute_remaining_clicked)
        host.preview_panel.execute_remaining_clicked.connect(self.on_execute_remaining_clicked)

        # 预览“返回详情”
        host.preview_panel.back_to_detail_requested.connect(
            lambda: host.right_stack.setCurrentIndex(0)
        )
        # 预览“编辑”请求 → 跳转到编辑器
        host.preview_panel.edit_requested.connect(host._open_graph_in_editor)
        # 识别聚焦成功信号透传给宿主逻辑
        host.preview_panel.recognition_focus_succeeded.connect(
            self.on_recognition_focus_succeeded
        )

        # 预览中单击节点/空白 → 联动任务树高亮与跳转
        host.preview_panel.node_clicked.connect(self.on_preview_node_clicked)
        host.preview_panel.background_clicked.connect(self.on_preview_background_clicked)

    # === 入口 API（供宿主委托）===

    def load_todos(self, todos: List[TodoItem], todo_states: Dict[str, bool]) -> None:
        """加载任务列表并同步到树管理器（TodoTreeManager 作为集中数据源）。"""
        host = self.host
        # 控制台提示：保留该行仅用于快速定位“任务清单是否完成装配并收到数据”
        print(f"[TASK-LIST] load_todos: todos={len(todos)}, todo_states={len(todo_states)}")
        host.tree_manager.set_data(todos, todo_states)
        host._update_stats()

    def on_selection_changed(
        self,
        current_item: QtWidgets.QTreeWidgetItem,
        previous_item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """树项选中变化：高亮 BasicBlock，刷新详情与预览。

        约定：
        - 当存在“按节点过滤步骤”的置灰模式时，若用户点到的树项不是当前节点相关步骤，
          则自动清除由节点选中产生的高亮与置灰效果，恢复整棵树的正常配色；
        - 若仍然点在相关步骤上（含锚点与其它关联步骤），则保留当前节点高亮状态。
        """
        if not current_item:
            return

        host = self.host
        tree_manager = host.tree_manager

        # 若当前处于“按节点过滤步骤”的置灰模式，且本次选中项不在高亮集合中，则清除节点高亮。
        if tree_manager.is_node_filter_active():
            todo_id_for_filter = current_item.data(0, Qt.ItemDataRole.UserRole)
            related_ids = tree_manager.get_current_node_highlight_ids()
            is_block_header = tree_manager.is_block_header_item(current_item)
            if (
                is_block_header
                or not todo_id_for_filter
                or todo_id_for_filter not in related_ids
            ):
                tree_manager.clear_node_highlight()

        tree_manager.highlight_block_for_item(current_item)

        if tree_manager.is_block_header_item(current_item):
            self._focus_logic_block_for_header(current_item)
            return

        todo_id = current_item.data(0, Qt.ItemDataRole.UserRole)
        todo = host._get_todo_by_id(todo_id)
        if not todo:
            return
        if settings.PREVIEW_VERBOSE:
            detail_type = todo.detail_info.get("type", "") if todo.detail_info else ""
            print(
                f"[PREVIEW] 选中任务: id={todo_id}, type={detail_type}, title={todo.title}"
            )
        self.show_detail(todo)

    def _focus_logic_block_for_header(
        self,
        header_item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """选中“逻辑块”分组头时，仅调整右侧预览镜头以适应该块所在区域。"""
        host = self.host
        tree_manager = host.tree_manager
        block_node_ids = tree_manager.collect_block_node_ids_for_header_item(header_item)
        if not block_node_ids:
            return

        parent_item = header_item.parent()
        if parent_item is None:
            return
        flow_root_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
        if not flow_root_id:
            return

        flow_root_todo = host._get_todo_by_id(flow_root_id)
        if not flow_root_todo:
            return

        preview_panel = host.preview_panel
        switched_to_preview = preview_panel.handle_graph_preview(
            flow_root_todo,
            tree_manager.todo_map,
            tree_manager=tree_manager,
            ui_context=self.ui_context,
        )
        if not switched_to_preview:
            return

        preview_panel.focus_on_node_group(block_node_ids)

        monitor_panel = self.ui_context.try_get_execution_monitor_panel()
        workspace_path = self.ui_context.try_get_workspace_path()
        if monitor_panel is not None and workspace_path is not None:
            preview_panel.bind_monitor_panel(monitor_panel, workspace_path)
        host.right_stack.setCurrentIndex(1)

    def on_execute_clicked(self) -> None:
        """执行按钮点击（委托给执行桥接层）。"""
        host = self.host
        if not host.current_detail_info:
            host._notify("内部错误：当前详情为空，无法执行", "error")
            return
        detail_type = host.current_detail_info.get("type", "")
        execution_profile = StepTypeRules.build_execution_profile(detail_type)

        # 1) 若当前详情语义为“叶子图步骤”，则严格按照单步执行处理：
        #    - 尝试解析出叶子 Todo；
        #    - 若解析失败，则给出明确提示而不是回退到整图执行，避免误触发父级。
        if execution_profile.is_leaf_graph_step:
            leaf_todo = self._resolve_leaf_todo_for_execution()
            if leaf_todo is None:
                host._notify(
                    "当前选中的任务已不在最新的任务清单中，请重新选择要执行的步骤", "warning"
                )
                return
            host.executor_bridge.execute_single_step(leaf_todo)
            return

        # 2) 若当前语义已是模板图根/事件流根/复合节点，则按对应入口执行。

        if execution_profile.is_template_graph_root:
            host.executor_bridge.execute_template_graph_root()
            return

        if execution_profile.is_event_flow_root:
            host.executor_bridge.execute_event_flow_root()
            return

        if execution_profile.is_composite_step:
            host.executor_bridge.execute_composite_step(detail_type, host.current_detail_info)

    def on_execute_remaining_clicked(self) -> None:
        """执行剩余序列：叶子步骤 → 同级末尾；事件流根 → 当前及后续事件流。"""
        host = self.host
        if not host.current_detail_info:
            host._notify("内部错误：当前详情为空，无法执行", "error")
            return
        detail_type = host.current_detail_info.get("type", "")
        execution_profile = StepTypeRules.build_execution_profile(detail_type)

        if execution_profile.is_leaf_graph_step:
            leaf_todo = self._resolve_leaf_todo_for_execution()
            if leaf_todo is None:
                host._notify(
                    "当前选中的任务已不在最新的任务清单中，请重新选择要执行的步骤", "warning"
                )
                return
            host.executor_bridge.execute_from_this_step(leaf_todo)
            return

        if execution_profile.is_event_flow_root:
            host.executor_bridge.execute_remaining_event_flows()
            return

        host._notify("仅支持在叶子图步骤或事件流根上执行剩余序列", "warning")

    def _resolve_leaf_todo_for_execution(self) -> Optional[TodoItem]:
        """根据当前上下文解析出可执行的叶子 Todo。

        使用统一的 CurrentTodoResolver 进行解析，优先顺序：
        1) 树中当前选中项的 todo_id
        2) current_todo_id（通常由详情/外部跳转维护）
        3) 在当前 todos 中按 detail_info 全量匹配
        4) 根据 graph_id 在最新任务清单中查找一个可用的叶子 Todo
        """
        host = self.host
        resolved_todo = self.ui_context.resolve_current_leaf_todo()

        if resolved_todo is not None:
            # 同步宿主状态，保持与原有行为一致
            host.current_todo_id = resolved_todo.todo_id
            host.current_detail_info = resolved_todo.detail_info
            # 如果是通过 graph_id 兜底找到的，尝试同步树选中状态
            resolved_item = host.tree_manager.get_item_by_id(resolved_todo.todo_id)
            if resolved_item is not None:
                current_item = host.tree.currentItem()
                # 只在当前选中项不是解析结果时才同步
                if (
                    current_item is None
                    or current_item.data(0, Qt.ItemDataRole.UserRole)
                    != resolved_todo.todo_id
                ):
                    host.tree.setCurrentItem(resolved_item)
                    host.tree.scrollToItem(
                        resolved_item,
                        QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
                    )

        return resolved_todo

    def _compute_execute_button_text(self, execution_profile) -> str:
        """根据执行能力画像，为主执行按钮计算更贴合语义的文案。

        约定：
        - 叶子图步骤：保持为“执行当前步骤”，强调只执行这一条 Todo
        - 模板图根：使用“执行整张节点图”，表示会按清单顺序连续执行整图
        - 事件流根：使用“执行整个事件流”，表示仅执行该事件流下的所有步骤
        - 复合节点步骤：使用“查看复合节点指引”，表示只输出操作指引而不触发自动化
        - 其它可执行类型：回退为通用“执行”
        """
        if execution_profile.is_leaf_graph_step:
            return "执行当前步骤"
        if execution_profile.is_template_graph_root:
            return "执行整张节点图"
        if execution_profile.is_event_flow_root:
            return "执行整个事件流"
        if execution_profile.is_composite_step:
            return "查看复合节点指引"
        return "执行"

    def _compute_execute_remaining_button_text(self, execution_profile) -> str:
        """根据执行能力画像，为“执行剩余”按钮计算语义化文案。"""
        if execution_profile.is_event_flow_root:
            return "执行剩余事件流"
        return "执行剩余步骤"

    def show_detail(self, todo: TodoItem) -> None:
        """显示任务详情 + 懒加载图步骤 + 右侧预览/执行按钮状态。"""
        host = self.host
        host.current_detail_info = todo.detail_info
        host.current_todo_id = todo.todo_id

        host.detail_panel.set_detail(todo)
        # 将当前选中步骤同步给主窗口，便于右侧属性面板根据 Todo 展示只读属性视图
        main_window = self.ui_context.get_main_window()
        if main_window is not None:
            main_window.on_todo_selection_changed(todo)  # type: ignore[attr-defined]

        detail_type_for_expand = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_template_graph_root(detail_type_for_expand) and not todo.children:
            host.tree_manager.expand_graph_on_demand(todo)

        # 执行精简模式下：不加载/不切换节点图预览（避免占用空间与重载共享画布）
        if getattr(host, "execution_compact_mode_enabled", False):
            host.right_stack.setCurrentIndex(0)
        else:
            switched_to_preview = False
            if host.preview_panel.handle_composite_preview(todo, self.ui_context):
                switched_to_preview = True
            elif host.preview_panel.handle_graph_preview(
                todo,
                host.tree_manager.todo_map,
                tree_manager=host.tree_manager,
                ui_context=self.ui_context,
            ):
                switched_to_preview = True

            if switched_to_preview:
                monitor_panel = self.ui_context.try_get_execution_monitor_panel()
                workspace_path = self.ui_context.try_get_workspace_path()
                if monitor_panel is not None and workspace_path is not None:
                    host.preview_panel.bind_monitor_panel(monitor_panel, workspace_path)
                host.right_stack.setCurrentIndex(1)
            else:
                host.right_stack.setCurrentIndex(0)

        detail_type = todo.detail_info.get("type", "") if todo.detail_info else ""
        execution_profile = StepTypeRules.build_execution_profile(detail_type)

        host.detail_panel.set_execute_visible(execution_profile.is_executable)
        host.preview_panel.set_execute_visible(execution_profile.is_executable)

        execute_button_text = self._compute_execute_button_text(execution_profile)
        host.detail_panel.set_execute_text(execute_button_text)
        host.preview_panel.set_execute_text(execute_button_text)

        show_exec_remaining = execution_profile.supports_execute_remaining
        execute_remaining_text = self._compute_execute_remaining_button_text(
            execution_profile
        )
        host.detail_panel.set_execute_remaining_visible(show_exec_remaining)
        host.detail_panel.set_execute_remaining_text(execute_remaining_text)
        host.preview_panel.set_execute_remaining_visible(show_exec_remaining)
        host.preview_panel.set_execute_remaining_text(execute_remaining_text)

        if settings.PREVIEW_VERBOSE:
            print(
                f"[EXECUTE] 任务类型: {detail_type}, "
                f"可执行: {bool(execution_profile.is_executable)} "
                f"(graph_root={execution_profile.is_template_graph_root}, "
                f"flow_root={execution_profile.is_event_flow_root})"
            )

        monitor_panel = self.ui_context.try_get_execution_monitor_panel()
        if monitor_panel is not None:
            # 精简模式下，执行入口集中在执行监控面板；详情/预览中的执行按钮隐藏以节省空间
            if getattr(host, "execution_compact_mode_enabled", False):
                host.detail_panel.set_execute_visible(False)
                host.preview_panel.set_execute_visible(False)
                host.detail_panel.set_execute_remaining_visible(False)
                host.preview_panel.set_execute_remaining_visible(False)
                if hasattr(monitor_panel, "set_execute_visible"):
                    monitor_panel.set_execute_visible(bool(execution_profile.is_executable))
                if hasattr(monitor_panel, "set_execute_text"):
                    monitor_panel.set_execute_text(execute_button_text)
                if hasattr(monitor_panel, "set_execute_remaining_visible"):
                    monitor_panel.set_execute_remaining_visible(bool(show_exec_remaining))
                if hasattr(monitor_panel, "set_execute_remaining_text"):
                    monitor_panel.set_execute_remaining_text(execute_remaining_text)

                # 幂等绑定：监控面板“执行/执行剩余”按钮 → 本编排层的执行入口
                if self._monitor_panel_for_execute_controls is not monitor_panel:
                    if hasattr(monitor_panel, "execute_clicked"):
                        monitor_panel.execute_clicked.connect(self.on_execute_clicked)
                    if hasattr(monitor_panel, "execute_remaining_clicked"):
                        monitor_panel.execute_remaining_clicked.connect(
                            self.on_execute_remaining_clicked
                        )
                    self._monitor_panel_for_execute_controls = monitor_panel

            parent_title = ""
            item = host.tree_manager.get_item_by_id(todo.todo_id)
            if item is not None:
                parent_item = item.parent()
                if parent_item is not None:
                    parent_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
                    parent_todo = host._get_todo_by_id(parent_id)
                    if parent_todo:
                        parent_title = parent_todo.title
            monitor_panel.set_current_step_context(todo.title, parent_title)
            tokens = host.tree_manager.ensure_tokens_for_todo(todo.todo_id)
            if isinstance(tokens, list):
                monitor_panel.set_current_step_tokens(todo.todo_id, tokens)

    def select_task_by_id(
        self, todo_id: str
    ) -> Optional[QtWidgets.QTreeWidgetItem]:
        """选中指定任务（用于联动），返回对应树项。"""
        host = self.host
        item = host.tree_manager.get_item_by_id(todo_id)
        if item is None:
            return None
        parent_item = item.parent()
        while parent_item is not None:
            parent_item.setExpanded(True)
            parent_item = parent_item.parent()
        already_selected = host.tree.currentItem() is item
        if not already_selected:
            host.tree.setCurrentItem(item)
        host.tree.scrollToItem(
            item, QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter
        )
        return item

    def focus_task_from_external(
        self, todo_id: str, detail_info: Optional[dict] = None
    ) -> None:
        """外部入口：例如节点图编辑器可调用此方法跳回指定步骤。"""
        if not todo_id:
            return
        item = self.select_task_by_id(todo_id)
        if item is None:
            return
        host = self.host
        if host.tree.currentItem() is item:
            todo = host._get_todo_by_id(todo_id)
            if todo:
                self.show_detail(todo)

    def on_recognition_focus_succeeded(self, visible_node_ids: list[str]) -> None:
        """执行监控完成“定位镜头”后的回填：委托给识别回填协调器。"""
        self._recognition_coordinator.handle_focus_succeeded(visible_node_ids)

    def find_first_todo_for_graph(self, graph_id: str) -> Optional[TodoItem]:
        """根据 graph_id 查找一个可用的 todo（优先叶子步骤，其次父级根）。"""
        if not graph_id:
            return None
        host = self.host
        normalized = str(graph_id)
        best_leaf: Optional[TodoItem] = None
        best_parent: Optional[TodoItem] = None

        for todo in host.todos:
            info = todo.detail_info or {}
            if str(info.get("graph_id", "")) != normalized:
                continue
            detail_type = info.get("type", "")
            if StepTypeRules.is_leaf_graph_step(detail_type):
                if best_leaf is None:
                    best_leaf = todo
                continue
            if StepTypeRules.is_composite_step(detail_type):
                if best_parent is None or (
                    best_parent
                    and StepTypeRules.is_graph_step(
                        (best_parent.detail_info or {}).get("type", "")
                    )
                ):
                    best_parent = todo
                continue
            if best_parent is None:
                best_parent = todo

        return best_leaf or best_parent

    # === 预览点击联动 ===

    def on_preview_node_clicked(self, node_id: str) -> None:
        """在预览中单击节点时：高亮关联步骤，并跳转到创建该节点的步骤。"""
        host = self.host
        if not node_id:
            return
        tree_manager = host.tree_manager

        related_todos = tree_manager.get_related_todos_for_node(node_id)
        if not related_todos:
            tree_manager.clear_node_highlight()
            return

        normalized = str(node_id)
        anchor_todo: Optional[TodoItem] = None
        for candidate in related_todos:
            detail_info = candidate.detail_info or {}
            created_node_id = get_created_node_id_from_detail(detail_info)
            if created_node_id and created_node_id == normalized:
                anchor_todo = candidate
                break
        if anchor_todo is None:
            anchor_todo = related_todos[0]

        anchor_todo_id = anchor_todo.todo_id if anchor_todo else ""
        tree_manager.highlight_steps_for_node(
            node_id, anchor_todo_id=anchor_todo_id or None
        )

        if anchor_todo_id:
            self.select_task_by_id(anchor_todo_id)

    def on_preview_background_clicked(self) -> None:
        """在预览中点击空白处时，清除由节点选中产生的步骤高亮。"""
        host = self.host
        host.tree_manager.clear_node_highlight()

    # === 内部工具 ===

    def _on_tree_context_menu_requested(self, position: QtCore.QPoint) -> None:
        """右键菜单请求：统一交给 TodoContextMenu 与执行桥处理。"""
        host = self.host
        host._context_menu.show_menu(position, host.executor_bridge)


