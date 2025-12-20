from __future__ import annotations

from typing import List, Optional, Tuple
from pathlib import Path

from PyQt6 import QtCore
from engine.graph.models.graph_model import GraphModel
from app.automation.editor.editor_executor import EditorExecutor
from app.ui.execution import ExecutionRunner
from app.ui.execution.guides import ExecutionGuides
from app.ui.todo.todo_config import StepTypeRules
from app.ui.execution.strategies.step_skip_checker import SINGLE_STEP_SKIP_REASON
from app.ui.todo.todo_ui_context import TodoUiContext
from app.ui.todo.todo_execution_service import (
    RootExecutionPlan,
    StepExecutionPlan,
    StepExecutionError,
    plan_template_root_execution,
    plan_event_flow_root_execution,
    plan_remaining_event_flows_execution,
    plan_execute_from_this_step,
    plan_single_step_execution,
)
from app.ui.todo.graph_data_resolver import resolve_graph_data_for_execution


class TodoExecutorBridge(QtCore.QObject):
    """执行编排与监控桥接层。

    负责：
    - 各类执行入口（图根/事件流根/复合/右键一步/从此步起）
    - 监控面板上下文注入、状态回填与信号连线
    - 运行时状态更新（failed/skipped）与 UI 勾选推进
    """

    def __init__(
        self,
        host_widget,  # TodoListWidget（用于访问 tree/nav/main_window/notify）
        *,
        ui_context: TodoUiContext,
        tree_manager=None,
        runtime_state=None,
        preview_panel=None,
        rich_segments_role: int = 0,
    ) -> None:
        super().__init__(host_widget)
        self.host = host_widget
        self.ui_context = ui_context
        self.tree_manager = tree_manager
        self.runtime_state = runtime_state
        self.preview_panel = preview_panel
        self.RICH_SEGMENTS_ROLE = rich_segments_role

        # 与执行监控面板之间的信号连线状态（用于避免重复绑定 step_anchor_clicked）
        self._monitor_panel_for_step_anchor = None
        self._execution_runner: Optional[ExecutionRunner] = None
        self._selection_to_restore: str = ""
        # 任务树展开状态快照：在执行前记录，执行结束后恢复，避免执行过程导致树结构意外折叠。
        self._tree_expanded_state_snapshot: dict[str, bool] = {}

        # 当前运行的简要状态（供执行监控结构化事件使用）
        self._run_had_failure: bool = False
        self._run_step_order: dict[str, int] = {}
        self._run_total_steps: int = 0
        # 当前运行是否为“连续执行”（整图/剩余步骤）：用于决定执行结束时是否需要恢复选中项。
        self._run_is_continuous: bool = False

    # === 公有入口 ===

    def execute_template_graph_root(self) -> None:
        """从当前上下文执行模板图根。

        上下文解析统一交给 `current_todo_resolver.resolve_current_todo_for_root`，
        不依赖外层传入的 detail_info，避免参数与真实选中项产生偏差。
        """
        self._execute_template_root()

    def execute_event_flow_root(self) -> None:
        """从当前上下文执行事件流根（仅执行其子步骤）。"""
        self._execute_flow_root()

    def execute_remaining_event_flows(self) -> None:
        """从当前事件流起，连续执行同一节点图下的剩余事件流序列。"""
        if self.tree_manager is None:
            self._notify("内部错误：任务树管理器未初始化，无法解析事件流", "error")
            return

        context = self.ui_context.build_current_todo_context()
        todo_map = self.tree_manager.todo_map
        find_flow_root = self.tree_manager.find_event_flow_root_for_todo
        remaining_plan, error = plan_remaining_event_flows_execution(
            context,
            todo_map,
            find_template_root_for_item=self._find_template_graph_root_for_item,
            find_event_flow_root_for_todo=find_flow_root,
        )
        if error is not None:
            user_message = error.user_message or ""
            toast_type = "warning" if error.reason == "no_event_flows" else "error"
            self._notify(user_message or "内部错误：剩余事件流执行规划失败", toast_type)
            return
        if remaining_plan is None:
            self._notify("内部错误：剩余事件流执行规划失败", "error")
            return

        current_flow_root = remaining_plan.current_flow_root
        item = self._get_item_by_id(current_flow_root.todo_id)
        template_root = self._find_template_graph_root_for_item(item) if item is not None else None
        graph_data = self._resolve_graph_data(current_flow_root, template_root or current_flow_root)
        if graph_data is None:
            return

        step_list = list(remaining_plan.step_list)

        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return

        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
        # 根级连续执行入口：清空坐标映射/识别缓存，避免复用上一轮执行残留导致视口对齐与创建位置异常。
        executor.reset_mapping_state(monitor.log)
        self._inject_context_to_monitor(monitor, graph_model, executor)

        if not step_list:
            monitor.start_monitoring()
            monitor.log("当前节点图的剩余事件流中无可执行步骤：已打开监控。可使用『检查』或『定位镜头』进行识别与聚焦。")
            return

        self._selection_to_restore = current_flow_root.todo_id
        self._snapshot_tree_expanded_state()
        self._start_runner(executor, graph_model, step_list, monitor, continuous=True)
        self._notify("开始执行：当前及后续事件流", "info")

    def execute_composite_step(self, detail_type: str, detail_info: dict) -> None:
        """复合节点执行入口：仅在监控面板输出操作指引，不触发自动化。

        由编排层根据 detail_type 判定“是否为复合节点”，本方法只负责
        使用监控面板展示指引，避免在桥接层再次解析 detail_type。
        """
        if not isinstance(detail_info, dict):
            self._notify("内部错误：当前详情为空，无法执行", "error")
            return
        if not StepTypeRules.is_composite_step(detail_type):
            self._notify("内部错误：当前步骤并非复合节点类型，无法执行复合节点指引", "error")
            return

        monitor_panel = self._ensure_monitor_panel()
        if monitor_panel is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return
        monitor_panel.start_monitoring()
        monitor_panel.update_status("请在真实编辑器中按指引完成复合节点设置")
        ExecutionGuides.log_composite_guide(monitor_panel, detail_type, detail_info)
        return

    def execute_from_this_step(self, start_todo) -> None:
        # 定位根
        item = self._get_item_by_id(start_todo.todo_id)
        if item is None:
            self._notify("内部错误：未找到树项（item is None）", "error")
            return
        root_todo = self._find_template_graph_root_for_item(item)
        graph_data = self._resolve_graph_data(start_todo, root_todo)
        if graph_data is None:
            return
        todo_map = self.tree_manager.todo_map
        find_flow_root = self.tree_manager.find_event_flow_root_for_todo
        find_template_root = self.tree_manager.find_template_graph_root_for_todo
        step_plan = plan_execute_from_this_step(
            start_todo,
            todo_map,
            find_event_flow_root_for_todo=find_flow_root,
            find_template_root_for_todo=find_template_root,
        )
        step_list = list(step_plan.step_list)
        if not step_list:
            self._notify("没有可执行的步骤（规划结果为空）", "warning")
            return
        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return
        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
        self._inject_context_to_monitor(monitor, graph_model, executor)
        self._selection_to_restore = step_plan.selection_to_restore
        self._snapshot_tree_expanded_state()
        self._start_runner(executor, graph_model, step_list, monitor, continuous=True)
        self._notify("开始执行：从当前步到末尾", "info")

    def execute_single_step(self, step_todo) -> None:
        item = self._get_item_by_id(step_todo.todo_id)
        if item is None:
            self._notify("内部错误：未找到树项（item is None）", "error")
            return
        root_todo = self._find_template_graph_root_for_item(item)
        graph_data = self._resolve_graph_data(step_todo, root_todo)
        if graph_data is None:
            return
        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return
        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
        todo_map = self.tree_manager.todo_map
        find_flow_root = self.tree_manager.find_event_flow_root_for_todo
        find_template_root = self.tree_manager.find_template_graph_root_for_todo
        step_plan, error = plan_single_step_execution(
            step_todo,
            todo_map,
            find_event_flow_root_for_todo=find_flow_root,
            find_template_root_for_todo=find_template_root,
        )
        if error is not None:
            user_message = error.user_message or ""
            if user_message:
                self._log_to_monitor_or_toast(user_message)
            else:
                self._notify("内部错误：单步执行规划失败", "error")
            return
        if step_plan is None or not step_plan.step_list:
            self._notify("没有可执行的步骤（规划结果为空）", "warning")
            return
        self._selection_to_restore = step_plan.selection_to_restore
        self._snapshot_tree_expanded_state()
        self._inject_context_to_monitor(monitor, graph_model, executor)
        self._start_runner(executor, graph_model, step_plan.step_list, monitor, continuous=False)
        self._notify("开始执行：仅此一步", "info")

    # === 内部：具体执行形态 ===

    def _execute_flow_root(self) -> None:
        # 定位当前事件流根任务（使用统一解析器：树选中 → current_todo_id → detail_info 匹配 → 父链回溯）
        if self.tree_manager is None:
            self._notify("内部错误：任务树管理器未初始化，无法解析事件流", "error")
            return
        context = self.ui_context.build_current_todo_context()
        todo_map = self.tree_manager.todo_map
        find_flow_root = self.tree_manager.find_event_flow_root_for_todo
        root_plan = plan_event_flow_root_execution(
            context,
            todo_map,
            find_template_root_for_item=self._find_template_graph_root_for_item,
            find_event_flow_root_for_todo=find_flow_root,
        )
        if root_plan is None:
            self._notify("内部错误：未找到当前任务项（current_todo）", "error")
            return
        current_todo = root_plan.root_todo
        # 查找模板图根以作为回退图数据来源
        item = self._get_item_by_id(current_todo.todo_id)
        template_root = self._find_template_graph_root_for_item(item) if item is not None else None
        graph_data = self._resolve_graph_data(current_todo, template_root or current_todo)
        if graph_data is None:
            return
        step_list = list(root_plan.step_list)
        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return
        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
        # 事件流根执行入口：清空坐标映射/识别缓存，确保首个创建类步骤能在“未校准”模式下从画布中心创建锚点。
        executor.reset_mapping_state(monitor.log)
        self._inject_context_to_monitor(monitor, graph_model, executor)
        if not step_list:
            monitor.start_monitoring()
            monitor.log("当前事件流无可执行步骤：已打开监控。可使用『检查』或『定位镜头』进行识别与聚焦。")
            return
        self._selection_to_restore = current_todo.todo_id
        self._snapshot_tree_expanded_state()
        self._start_runner(executor, graph_model, step_list, monitor, continuous=True)

    def _execute_template_root(self) -> None:
        """从当前上下文执行模板图根（或其子步骤所属的模板图根）。

        使用 unified current_todo_resolver：
        - 首先按“树选中项 → current_todo_id → detail_info 匹配”解析当前 Todo；
        - 若解析结果不是模板图根，则通过 TodoTreeManager 回溯到模板图根；
        - 保持与事件流根入口一致，都直接依赖 current_todo_resolver 提供的根解析逻辑。
        """
        if self.tree_manager is None:
            self._notify("内部错误：任务树管理器未初始化，无法解析模板图根", "error")
            return
        context = self.ui_context.build_current_todo_context()
        todo_map = self.tree_manager.todo_map
        root_plan = plan_template_root_execution(
            context,
            todo_map,
            find_template_root_for_item=self._find_template_graph_root_for_item,
        )
        if root_plan is None:
            self._notify("内部错误：未找到当前任务项（current_todo）", "error")
            return
        current_todo = root_plan.root_todo
        graph_data = self._resolve_graph_data(current_todo, current_todo)
        if graph_data is None:
            return
        step_list = list(root_plan.step_list)
        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return
        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
        # 清空坐标映射/识别缓存
        executor.reset_mapping_state(monitor.log)
        self._inject_context_to_monitor(monitor, graph_model, executor)
        if not step_list:
            monitor.start_monitoring()
            monitor.log("当前节点图无可执行步骤：已打开监控。可使用『检查』或『定位镜头』进行识别与聚焦。")
            return
        # 预置第一步 tokens
        first_step = step_list[0] if step_list else None
        if first_step is not None:
            first_todo = self.tree_manager.todo_map.get(first_step.todo_id)
            if first_todo is not None:
                tokens = self._ensure_tokens_for_todo(first_todo.todo_id)
                if isinstance(tokens, list):
                    monitor.set_current_step_context(first_todo.title, "")
                    monitor.set_current_step_tokens(first_todo.todo_id, tokens)
        self._selection_to_restore = current_todo.todo_id
        self._snapshot_tree_expanded_state()
        self._start_runner(executor, graph_model, step_list, monitor, continuous=True)

    # === 内部：Runner ===

    def _start_runner(self, executor: EditorExecutor, graph_model: GraphModel, step_list: list, monitor_panel, continuous: bool) -> None:
        self._execution_runner = ExecutionRunner(self.host)
        # 重置本轮运行状态
        self._run_had_failure = False
        self._run_step_order = {}
        self._run_total_steps = len(step_list) if isinstance(step_list, (list, tuple)) else 0
        self._run_is_continuous = bool(continuous)
        # 根据 todo_id 预先建立步骤顺序映射（用于在监控面板中展示 [index/total]）
        if isinstance(step_list, (list, tuple)):
            for idx, step in enumerate(step_list):
                todo_id = step.todo_id
                if todo_id and todo_id not in self._run_step_order:
                    self._run_step_order[todo_id] = idx

        self._execution_runner.finished.connect(lambda: setattr(self, "_execution_runner", None))
        self._execution_runner.step_will_start.connect(self._on_step_will_start)
        self._execution_runner.step_will_start.connect(self._pause_if_step_mode)
        self._execution_runner.step_will_start.connect(self._set_monitor_step_context)
        # 监控面板是长生命周期组件，避免在多次执行时重复绑定 step_anchor_clicked → _on_step_anchor_clicked
        # 仅当监控面板实例发生变化时才重新连接
        if self._monitor_panel_for_step_anchor is not monitor_panel:
            monitor_panel.step_anchor_clicked.connect(self._on_step_anchor_clicked)
            self._monitor_panel_for_step_anchor = monitor_panel
        self._execution_runner.step_completed.connect(self._on_step_completed)
        self._execution_runner.step_skipped.connect(self._mark_task_skipped)
        self._execution_runner.finished.connect(self._restore_selection_after_run)
        self._execution_runner.finished.connect(self._restore_tree_expanded_state)
        # 结构化运行事件：准备本轮 run_id，并在结束时写入结果
        monitor_panel.begin_run(self._run_total_steps)

        def _on_run_finished_for_monitor() -> None:
            success = not bool(self._run_had_failure)
            monitor_panel.end_run(success)

        self._execution_runner.finished.connect(_on_run_finished_for_monitor)

        self._execution_runner.start(
            executor,
            graph_model,
            step_list,
            monitor_panel,
            fast_chain_mode=continuous,
        )

    def _snapshot_tree_expanded_state(self) -> None:
        """记录当前任务树中父节点的展开状态，用于执行结束后恢复。"""
        self._tree_expanded_state_snapshot = {}
        if self.tree_manager is None:
            return
        item_map = self.tree_manager.get_item_map()
        snapshot: dict[str, bool] = {}
        for todo_id, item in item_map.items():
            if not todo_id or item is None:
                continue
            # 仅记录包含子节点的父项展开状态，叶子项的展开状态没有意义
            if item.childCount() <= 0:
                continue
            snapshot[str(todo_id)] = bool(item.isExpanded())
        self._tree_expanded_state_snapshot = snapshot

    def _restore_tree_expanded_state(self) -> None:
        """在执行结束后恢复任务树的展开状态，保证仍停留在原有展开结构。"""
        if not self._tree_expanded_state_snapshot:
            return
        if self.tree_manager is None:
            return
        item_map = self.tree_manager.get_item_map()
        for todo_id, was_expanded in self._tree_expanded_state_snapshot.items():
            item = item_map.get(todo_id)
            if item is None:
                continue
            if item.childCount() <= 0:
                continue
            item.setExpanded(bool(was_expanded))
        self._tree_expanded_state_snapshot = {}

    # === Tree/Token 访问（统一依赖 TodoTreeManager，不再通过反射兜底） ===

    def _get_item_by_id(self, todo_id: str):
        if self.tree_manager is None:
            return None
        return self.tree_manager.get_item_by_id(todo_id)

    def _ensure_tokens_for_todo(self, todo_id: str):
        if self.tree_manager is None:
            return None
        return self.tree_manager.ensure_tokens_for_todo(todo_id)

    def _update_item_incrementally(self, item, todo) -> None:
        if self.tree_manager is None:
            return
        self.tree_manager.update_item_incrementally(item, todo)

    # === Runner 槽 ===

    def _on_step_anchor_clicked(self, todo_id: str) -> None:
        self._select_task_by_id(todo_id)

    def _on_step_will_start(self, todo_id: str) -> None:
        self._select_task_by_id(todo_id)

    def _on_step_completed(self, todo_id: str, success: bool) -> None:
        """执行完成回调：回填运行态，并在连续执行时自动推进到下一条任务。"""
        if self.tree_manager is None or self.runtime_state is None:
            return
        item = self._get_item_by_id(todo_id)
        if item is None:
            return
        todo = self.tree_manager.todo_map.get(todo_id)

        if not success:
            self._run_had_failure = True

        if success:
            self.runtime_state.mark_success(todo_id)
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        else:
            self.runtime_state.mark_failed(todo_id, "该步骤执行失败")
            if todo is not None:
                self._update_item_incrementally(item, todo)

        monitor = self.host._monitor_window
        if monitor is not None:
            title = todo.title if todo is not None else ""
            index = self._run_step_order.get(todo_id)
            total = self._run_total_steps or None
            reason = None if success else "该步骤执行失败"
            monitor.notify_step_completed(todo_id, title, index, total, success, reason)

        if not self._run_is_continuous:
            return
        # 连续执行中，左侧树的“当前步骤选中”应以执行线程发出的 step_will_start 为准，
        # 不在 step_completed 时按 UI 展示顺序做 next 导航，避免与重试/跳过等运行时决策产生错位。

    def _mark_task_skipped(self, todo_id: str, reason: str) -> None:
        if self.tree_manager is None or self.runtime_state is None:
            return
        item = self._get_item_by_id(todo_id)
        todo = self.tree_manager.todo_map.get(todo_id)
        if not item or not todo:
            return
        normalized_reason = str(reason or "该步骤因端点距离过远被跳过")
        # 单步执行模式下，非目标步骤仅作为上下文参与规划，不在任务树中高亮为“跳过”，以免误导用户。
        if normalized_reason == SINGLE_STEP_SKIP_REASON:
            return
        self.runtime_state.mark_skipped(todo_id, normalized_reason)
        self._update_item_incrementally(item, todo)
        # 推送“跳过步骤”到执行监控结构化事件
        monitor = self.host._monitor_window
        if monitor is not None:
            title = todo.title
            index = self._run_step_order.get(todo_id)
            total = self._run_total_steps or None
            monitor.notify_step_skipped(todo_id, title, index, total, normalized_reason)

    def _pause_if_step_mode(self, _todo_id: str) -> None:
        monitor = self.host._monitor_window
        if monitor is None:
            return
        if monitor.is_step_mode_enabled():
            monitor.request_pause()

    def _set_monitor_step_context(self, todo_id: str) -> None:
        monitor = self.host._monitor_window
        if monitor is None:
            return
        if self.tree_manager is None:
            return
        todo = self.tree_manager.todo_map.get(todo_id)
        if not todo:
            return
        parent_title = ""
        item = self._get_item_by_id(todo_id)
        if item is not None:
            parent_item = item.parent()
            if parent_item is not None:
                parent_id = parent_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                parent_todo = self.tree_manager.todo_map.get(parent_id)
                if parent_todo:
                    parent_title = parent_todo.title
        monitor.set_current_step_context(todo.title, parent_title)
        tokens = self._ensure_tokens_for_todo(todo_id)
        if isinstance(tokens, list):
            monitor.set_current_step_tokens(todo_id, tokens)

        # 同步结构化执行事件：记录“步骤开始”
        index = self._run_step_order.get(todo_id)
        total = self._run_total_steps or None
        monitor.notify_step_started(todo_id, todo.title, index, total)

    def _restore_selection_after_run(self) -> None:
        # 仅在连续执行（整图 / 从此步到末尾）场景下恢复选中项：
        # - 单步执行时，执行前后选中项本身就是当前步骤，无需额外恢复，避免打乱用户的浏览位置。
        if not self._run_is_continuous:
            return

        restore_id = self._selection_to_restore
        if not restore_id:
            return
        item = self._get_item_by_id(restore_id)
        if item is not None:
            self.host.tree.setCurrentItem(item)
            self.host.tree.scrollToItem(item)

    # === 工具 ===

    def _resolve_graph_data(self, focus_todo, root_todo):
        """统一解析执行所需的 graph_data，并在缺失时优先写入监控面板。

        加载顺序由 `resolve_graph_data_for_execution` 统一维护：
        - 优先复用预览面板当前的 graph_data；
        - 其次通过 TodoPreviewController.get_graph_data_id_and_container 解析；
        - 再通过 TodoTreeManager 按根 Todo 加载；
        - 最后仅在无树管理/预览面板时，从 detail_info 的缓存 key 中解析。

        资源加载与缓存写回统一交由 PreviewController/TodoTreeGraphSupport 处理，
        本类不再直接操作 graph_data_key 或 ResourceManager。
        """
        graph_data = resolve_graph_data_for_execution(
            focus_todo,
            root_todo or focus_todo,
            preview_panel=self.preview_panel,
            tree_manager=self.tree_manager,
            graph_data_service=self.ui_context.get_graph_data_service(),
            current_package=self.ui_context.try_get_current_package(),
        )
        if isinstance(graph_data, dict) and ("nodes" in graph_data or "edges" in graph_data):
            return graph_data

        self._log_to_monitor_or_toast("✗ 缺少图数据（graph_data），无法执行")
        return None

    def _ensure_monitor_panel(self, switch_tab: bool = False):
        return self.ui_context.ensure_execution_monitor_panel(switch_to=switch_tab)

    def _inject_context_to_monitor(self, monitor_panel, graph_model: GraphModel, executor: Optional[EditorExecutor] = None) -> None:
        if monitor_panel is None:
            return
        view_ref = None
        app_state = self.ui_context.get_app_state()
        if app_state is not None:
            view_ref = app_state.graph_view
        workspace_path = self.ui_context.try_get_workspace_path()
        if workspace_path is None:
            self._notify("工作区未就绪，无法注入监控上下文", "error")
            return
        monitor_panel.set_context(workspace_path, graph_model, view_ref)
        if executor is not None:
            monitor_panel.set_shared_executor(executor)
        # 将“定位镜头识别成功”统一透传到 TodoPreviewPanel 的信号上，由编排层集中处理回填，
        # 避免同时存在“监控面板→编排层”和“监控面板→预览面板→编排层”两条链路导致重复回调。
        if self.preview_panel is not None:
            self.preview_panel.wire_recognition_from_monitor_panel(monitor_panel)

    def _build_executor_and_model(self, graph_data: dict, monitor_panel) -> Tuple[EditorExecutor, GraphModel]:
        workspace_path = self.ui_context.try_get_workspace_path()
        if workspace_path is None:
            raise RuntimeError("工作区未就绪：无法创建 EditorExecutor")
        executor: Optional[EditorExecutor] = None
        # 优先复用监控面板中已存在的执行器实例，保持与“检查/定位镜头/拖拽测试”一致的视口状态与缓存
        if monitor_panel is not None:
            shared = monitor_panel.get_shared_executor()
            if shared is not None and shared.workspace_path == workspace_path:
                executor = shared
        if executor is None:
            executor = EditorExecutor(workspace_path)
        if monitor_panel is not None:
            monitor_panel.set_shared_executor(executor)
        graph_model = GraphModel.deserialize(graph_data)
        return executor, graph_model

    def _select_task_by_id(self, todo_id: str) -> None:
        item = self._get_item_by_id(todo_id)
        if item is not None:
            self.host.tree.setCurrentItem(item)
            self.host.tree.scrollToItem(item)

    def _find_template_graph_root_for_item(self, start_item) -> Optional[object]:
        """通过 TodoTreeManager 统一定位模板图根。

        优先依赖 `find_template_graph_root_for_todo`，避免在此处重复实现
        “沿树父链 / parent_id 链路向上查找”的第三套逻辑。
        """
        if self.tree_manager is None:
            return None

        base_todo_id = ""
        if start_item is not None:
            base_todo_id = start_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not base_todo_id:
            base_todo_id = self.host.current_todo_id or ""
        if not base_todo_id:
            return None
        return self.tree_manager.find_template_graph_root_for_todo(str(base_todo_id))

    def _notify(self, message: str, toast_type: str = "info") -> None:
        self.host._notify(message, toast_type)

    def _log_to_monitor_or_toast(self, text: str) -> None:
        monitor_panel = self._ensure_monitor_panel(switch_tab=True)
        if monitor_panel is not None:
            monitor_panel.start_monitoring()
            monitor_panel.log(text)
        else:
            self._notify(text, "error")


