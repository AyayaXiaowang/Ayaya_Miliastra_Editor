from typing import Dict, List, Optional, Set
from pathlib import Path

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
from app.ui.todo.current_todo_resolver import build_context_from_host, resolve_current_todo_for_leaf
from app.ui.todo.preview_graph_context_resolver import resolve_graph_preview_context
from app.ui.todo.recognition_backfill_planner import (
    plan_recognition_backfill,
    _get_created_node_id_from_detail,
)


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
        todo_map: Dict[str, TodoItem] = getattr(host, "todo_map", {})
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
        if not hasattr(host, "tree_manager") or host.tree_manager is None:
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
        # 不应立刻触发频繁的存档保存（尤其在全局视图下）。
        # 因此在批量 setCheckState 期间暂时告诉主窗口跳过 todo 勾选的立即落盘，
        # 由后续显式保存操作统一持久化 todo_states。
        main_window = getattr(host, "main_window", None)
        suppress_attr = "_suppress_todo_persist"
        previous_flag = False
        if main_window is not None:
            previous_flag = getattr(main_window, suppress_attr, False)
            setattr(main_window, suppress_attr, True)
        try:
            for child_index in range(last_completed_step_index):
                child_id = flow_todo.children[child_index]
                child_todo = host.todo_map.get(child_id)
                if not child_todo:
                    continue
                self._auto_check_single_todo(child_todo)
        finally:
            if main_window is not None:
                setattr(main_window, suppress_attr, previous_flag)

    def _auto_check_single_todo(self, todo: TodoItem) -> None:
        """递归对子树中“可自动勾选”的叶子步骤打勾。"""
        host = self.host

        if todo.children:
            for child_id in todo.children:
                child_todo = host.todo_map.get(child_id)
                if child_todo is not None:
                    self._auto_check_single_todo(child_todo)
            return

        if not _is_step_auto_checkable(todo.detail_info):
            return

        item = host.tree_manager.get_item_by_id(todo.todo_id)
        if item is not None:
            item.setCheckState(0, Qt.CheckState.Checked)


class TodoListOrchestrator:
    """任务清单编排层：负责子组件创建与信号连线，不直接持有 UI 状态。

    设计目标：
    - 将 `TodoListWidget` 压缩为“布局 + 样式 + 对外接口”，便于阅读与调试
    - 将运行态对象（树管理/预览/详情/执行桥/右键菜单）的创建与 wiring 集中到一个地方
    - 所有领域相关入口（加载任务、选中变化、执行入口、识别联动）统一从这里经过
    """

    def __init__(self, host_widget: "TodoListWidget") -> None:
        self.host = host_widget
        self._recognition_coordinator = _RecognitionBackfillCoordinator(self)
        self._setup_subcomponents()
        self._wire_signals()

    # === 内部：主窗口与监控面板解析 ===

    def _get_main_window(self):
        return getattr(self.host, "main_window", None)

    def _get_execution_monitor_panel(self):
        main_window = self._get_main_window()
        if main_window is None:
            return None
        return getattr(main_window, "execution_monitor_panel", None)

    def _get_workspace_path(self) -> Path:
        main_window = self._get_main_window()
        if main_window is not None and hasattr(main_window, "workspace_path"):
            return Path(main_window.workspace_path)
        current_file = Path(__file__).resolve()
        return current_file.parent.parent

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
            graph_expand_dependency_getter=self._build_graph_expand_dependencies,
        )
        host.preview_panel = TodoPreviewPanel(host.right_stack)
        host.detail_panel = TodoDetailPanel(host.right_stack)
        host.detail_panel.host_list_widget = host

        # 装入右侧堆叠页（索引顺序：0=详情，1=预览）
        host.right_stack.insertWidget(0, host.detail_panel)
        host.right_stack.insertWidget(1, host.preview_panel)

        # 兼容旧引用：主窗口直接访问 preview_view 信号
        host.preview_view = host.preview_panel.preview_view

        # 右键菜单与执行桥（todo_map 统一由 TodoTreeManager 维护）
        host._context_menu = TodoContextMenu(host, host.tree, host.tree_manager)
        host.executor_bridge = TodoExecutorBridge(
            host,
            tree_manager=host.tree_manager,
            runtime_state=host.runtime_state,
            preview_panel=host.preview_panel,
            rich_segments_role=host.RICH_SEGMENTS_ROLE,
        )

    def _build_graph_expand_dependencies(self) -> Optional[tuple[object, object, object]]:
        """为模板图根懒加载提供 package/resource_manager 依赖。

        由宿主 TodoListWidget 注入 MainWindow 引用后，通过该方法统一解析当前包与资源管理器，
        避免在 `TodoTreeManager` 内部直接依赖 MainWindow 结构。
        """
        host = self.host
        main_window = getattr(host, "main_window", None)
        if main_window is None:
            return None
        package_controller = getattr(main_window, "package_controller", None)
        resource_manager = getattr(main_window, "resource_manager", None)
        if package_controller is None or resource_manager is None:
            return None
        package = getattr(package_controller, "current_package", None)
        if not package:
            return None
        package_index_manager = getattr(main_window, "package_index_manager", None)
        return (package, resource_manager, package_index_manager)

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
        if hasattr(host.detail_panel, "execute_remaining_clicked"):
            host.detail_panel.execute_remaining_clicked.connect(
                self.on_execute_remaining_clicked
            )
        if hasattr(host.preview_panel, "execute_remaining_clicked"):
            host.preview_panel.execute_remaining_clicked.connect(
                self.on_execute_remaining_clicked
            )

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
        if hasattr(host.preview_panel, "node_clicked"):
            host.preview_panel.node_clicked.connect(self.on_preview_node_clicked)
        if hasattr(host.preview_panel, "background_clicked"):
            host.preview_panel.background_clicked.connect(
                self.on_preview_background_clicked
            )

    # === 入口 API（供宿主委托）===

    def load_todos(self, todos: List[TodoItem], todo_states: Dict[str, bool]) -> None:
        """加载任务列表并同步到树管理器（TodoTreeManager 作为集中数据源）。"""
        host = self.host
        print(
            f"[TODO-WIDGET] load_todos 调用: 接收到 {len(todos)} 条任务，"
            f"todo_states 条目数={len(todo_states)}"
        )
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
        tree_manager = getattr(host, "tree_manager", None)

        # 若当前处于“按节点过滤步骤”的置灰模式，且本次选中项不在高亮集合中，则清除节点高亮。
        if (
            tree_manager is not None
            and getattr(tree_manager, "_node_filter_active", False)
        ):
            todo_id_for_filter = current_item.data(0, Qt.ItemDataRole.UserRole)
            related_ids = getattr(tree_manager, "_current_node_highlight_ids", set())
            marker_for_filter = current_item.data(
                0, Qt.ItemDataRole.UserRole + 2
            )
            is_block_header = marker_for_filter == "block_header"
            if (
                is_block_header
                or not todo_id_for_filter
                or todo_id_for_filter not in related_ids
            ):
                tree_manager.clear_node_highlight()

        if tree_manager is not None and hasattr(
            tree_manager, "highlight_block_for_item"
        ):
            tree_manager.highlight_block_for_item(current_item)

        marker = current_item.data(0, Qt.ItemDataRole.UserRole + 2)
        if marker == "block_header":
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
        tree_manager = getattr(host, "tree_manager", None)
        if tree_manager is None:
            return
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
        (
            graph_data,
            graph_id,
            container,
        ) = resolve_graph_preview_context(
            flow_root_todo,
            tree_manager.todo_map,
            tree_manager=tree_manager,
            main_window=host.main_window,
        )
        if not isinstance(graph_data, dict) or not graph_id:
            return

        previous_graph_id = preview_panel.current_graph_id
        has_scene = bool(getattr(preview_panel, "preview_scene", None))
        is_same_graph = (previous_graph_id == graph_id) and has_scene

        preview_panel.current_graph_id = graph_id
        preview_panel.current_graph_data = graph_data
        preview_panel.current_template_or_instance = container

        if not is_same_graph:
            if settings.PREVIEW_VERBOSE:
                print(
                    f"[PREVIEW] (block) 预览切换 → 重建场景: prev={previous_graph_id}, curr={graph_id}"
                )
            preview_panel._load_graph_preview(graph_data)
            if (
                host.main_window
                and hasattr(host.main_window, "library")
                and getattr(host.main_window, "library")
            ):
                preview_panel.preview_view.node_library = host.main_window.library
                if hasattr(preview_panel, "preview_scene") and preview_panel.preview_scene:
                    preview_panel.preview_scene.node_library = host.main_window.library
        else:
            if settings.PREVIEW_VERBOSE:
                print(f"[PREVIEW] (block) 复用现有预览场景: graph_id={graph_id}")

        preview_panel.preview_controller.focus_on_node_group(block_node_ids)

        monitor_panel = self._get_execution_monitor_panel()
        if monitor_panel is not None:
            preview_panel.bind_monitor_panel(
                monitor_panel,
                self._get_workspace_path(),
                recognition_slot=self.on_recognition_focus_succeeded,
            )
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
            if hasattr(host.executor_bridge, "execute_template_graph_root"):
                host.executor_bridge.execute_template_graph_root()
            return

        if execution_profile.is_event_flow_root:
            if hasattr(host.executor_bridge, "execute_event_flow_root"):
                host.executor_bridge.execute_event_flow_root()
            return

        if execution_profile.is_composite_step:
            if hasattr(host.executor_bridge, "execute_composite_step"):
                host.executor_bridge.execute_composite_step(
                    detail_type, host.current_detail_info
                )

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
            executor_bridge = getattr(host, "executor_bridge", None)
            if executor_bridge is None:
                host._notify("内部错误：执行桥接层不存在，无法启动执行", "error")
                return
            if hasattr(executor_bridge, "execute_remaining_event_flows"):
                executor_bridge.execute_remaining_event_flows()
            else:
                host._notify("内部错误：当前版本暂不支持按事件流执行剩余序列", "error")
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
        context = build_context_from_host(host)
        resolved_todo = resolve_current_todo_for_leaf(context)

        if resolved_todo is not None:
            # 同步宿主状态，保持与原有行为一致
            host.current_todo_id = resolved_todo.todo_id
            host.current_detail_info = resolved_todo.detail_info
            # 如果是通过 graph_id 兜底找到的，尝试同步树选中状态
            if hasattr(host, "tree_manager") and host.tree_manager is not None:
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
        if getattr(execution_profile, "is_leaf_graph_step", False):
            return "执行当前步骤"
        if getattr(execution_profile, "is_template_graph_root", False):
            return "执行整张节点图"
        if getattr(execution_profile, "is_event_flow_root", False):
            return "执行整个事件流"
        if getattr(execution_profile, "is_composite_step", False):
            return "查看复合节点指引"
        return "执行"

    def _compute_execute_remaining_button_text(self, execution_profile) -> str:
        """根据执行能力画像，为“执行剩余”按钮计算语义化文案。"""
        if getattr(execution_profile, "is_event_flow_root", False):
            return "执行剩余事件流"
        return "执行剩余步骤"

    def show_detail(self, todo: TodoItem) -> None:
        """显示任务详情 + 懒加载图步骤 + 右侧预览/执行按钮状态。"""
        host = self.host
        host.current_detail_info = todo.detail_info
        host.current_todo_id = todo.todo_id

        host.detail_panel.set_detail(todo)
        # 将当前选中步骤同步给主窗口，便于右侧属性面板根据 Todo 展示只读属性视图
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, "on_todo_selection_changed"):
            main_window.on_todo_selection_changed(todo)

        detail_type_for_expand = (todo.detail_info or {}).get("type", "")
        if StepTypeRules.is_template_graph_root(detail_type_for_expand) and not todo.children:
            host.tree_manager.expand_graph_on_demand(todo)

        switched_to_preview = False
        if host.preview_panel.handle_composite_preview(todo, host.main_window):
            switched_to_preview = True
        elif host.preview_panel.handle_graph_preview(
            todo,
            host.tree_manager.todo_map,
            host.main_window,
            tree_manager=host.tree_manager,
        ):
            switched_to_preview = True

        if switched_to_preview:
            monitor_panel = self._get_execution_monitor_panel()
            if monitor_panel is not None:
                host.preview_panel.bind_monitor_panel(
                    monitor_panel,
                    self._get_workspace_path(),
                    recognition_slot=self.on_recognition_focus_succeeded,
                )
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
        if hasattr(host.detail_panel, "set_execute_remaining_visible"):
            host.detail_panel.set_execute_remaining_visible(show_exec_remaining)
        if hasattr(host.detail_panel, "set_execute_remaining_text"):
            host.detail_panel.set_execute_remaining_text(execute_remaining_text)
        if hasattr(host.preview_panel, "set_execute_remaining_visible"):
            host.preview_panel.set_execute_remaining_visible(show_exec_remaining)
        if hasattr(host.preview_panel, "set_execute_remaining_text"):
            host.preview_panel.set_execute_remaining_text(execute_remaining_text)

        if settings.PREVIEW_VERBOSE:
            print(
                f"[EXECUTE] 任务类型: {detail_type}, "
                f"可执行: {bool(execution_profile.is_executable)} "
                f"(graph_root={execution_profile.is_template_graph_root}, "
                f"flow_root={execution_profile.is_event_flow_root})"
            )

        monitor_panel = self._get_execution_monitor_panel()
        if monitor_panel is not None and hasattr(
            monitor_panel, "set_current_step_context"
        ):
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
            if hasattr(monitor_panel, "set_current_step_tokens"):
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
        tree_manager = getattr(host, "tree_manager", None)
        if tree_manager is None:
            return

        related_todos = tree_manager.get_related_todos_for_node(node_id)
        if not related_todos:
            tree_manager.clear_node_highlight()
            return

        normalized = str(node_id)
        anchor_todo: Optional[TodoItem] = None
        for candidate in related_todos:
            detail_info = candidate.detail_info or {}
            created_node_id = _get_created_node_id_from_detail(detail_info)
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
        tree_manager = getattr(host, "tree_manager", None)
        if tree_manager is None:
            return
        tree_manager.clear_node_highlight()

    # === 内部工具 ===

    def _on_tree_context_menu_requested(self, position: QtCore.QPoint) -> None:
        """右键菜单请求：统一交给 TodoContextMenu 与执行桥处理。"""
        host = self.host
        if not hasattr(host, "_context_menu") or not getattr(
            host, "executor_bridge", None
        ):
            return
        host._context_menu.show_menu(position, host.executor_bridge)


