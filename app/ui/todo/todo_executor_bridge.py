from __future__ import annotations

from typing import List, Optional, Tuple
from pathlib import Path

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtWidgets import QAbstractItemView
from engine.graph.models.graph_model import GraphModel
from app.ui.execution import ExecutionRunner, ExecutionGuides, ExecutionSession, EditorExecutorProvider
from app.ui.todo.todo_config import StepTypeRules
from app.ui.execution.strategies.step_skip_checker import SINGLE_STEP_SKIP_REASON
from app.ui.todo.todo_ui_context import TodoUiContext
from app.ui.foundation.dialog_utils import ask_warning_action_dialog, show_warning_dialog
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
from app.ui.todo.execution_preflight_warning import inspect_graph_execution_preflight


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

        # 执行前提醒：每个 graph_id 仅弹一次，避免单步执行时反复弹窗。
        self._preflight_warning_shown_graph_ids: set[str] = set()

    # === 公有入口 ===

    def is_execution_running(self) -> bool:
        """当前是否存在正在运行的执行线程。"""
        return self._execution_runner is not None

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
        if not self._maybe_show_graph_preflight_warning(
            str((current_flow_root.detail_info or {}).get("graph_id") or "")
        ):
            return
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
        if not self._maybe_show_graph_preflight_warning(
            str((start_todo.detail_info or {}).get("graph_id") or "")
        ):
            return
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
        if not self._maybe_show_graph_preflight_warning(
            str((step_todo.detail_info or {}).get("graph_id") or "")
        ):
            return
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
        if not self._maybe_show_graph_preflight_warning(
            str((current_todo.detail_info or {}).get("graph_id") or "")
        ):
            return
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

        # 若当前模板图根尚未完成“图步骤懒加载展开”，则先异步展开，完成后自动续航执行。
        # 目的：避免大图在 UI 线程同步生成步骤导致界面卡死，同时保证用户点击执行后不会得到“空计划”。
        detail_type = str((current_todo.detail_info or {}).get("type", ""))
        if StepTypeRules.is_template_graph_root(detail_type) and not current_todo.children:
            def _resume_after_expand(expand_success: bool) -> None:
                if not expand_success:
                    self._notify("节点图步骤生成失败，无法执行。请检查节点图资源是否可加载。", "error")
                    return
                QtCore.QTimer.singleShot(0, self._execute_template_root)

            self.tree_manager.expand_graph_on_demand(
                current_todo,
                on_finished=_resume_after_expand,
            )
            self._notify("正在生成节点图步骤，完成后将自动开始执行…", "info")
            return

        if not self._maybe_show_graph_preflight_warning(
            str((current_todo.detail_info or {}).get("graph_id") or "")
        ):
            return
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

    def _start_runner(
        self,
        executor: object,
        graph_model: GraphModel,
        step_list: list,
        monitor_panel,
        continuous: bool,
    ) -> None:
        if self._execution_runner is not None:
            self._notify("当前已有执行在运行中，请先终止或等待执行结束", "warning")
            return

        self._execution_runner = ExecutionRunner(self.host)
        # 执行开始：确保运行时全局热键处于正确注册状态（例如 Ctrl+P 暂停）。
        self.host.sync_global_hotkeys()
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
        # 执行结束：根据“页面可见性/是否仍在执行”规则同步热键注册状态。
        # 注意：该连接需在上面的 setattr 之后建立，确保 sync 时 _execution_runner 已置空。
        self._execution_runner.finished.connect(self.host.sync_global_hotkeys)
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

        # 执行期间：暂停文件监控与资源库自动刷新，避免本地文件更新打断真实执行进程。
        main_window = self.ui_context.get_main_window()
        file_watcher_manager = getattr(main_window, "file_watcher_manager", None) if main_window is not None else None
        begin_suppression = getattr(file_watcher_manager, "begin_execution_suppression", None)
        end_suppression = getattr(file_watcher_manager, "end_execution_suppression", None)
        if callable(begin_suppression) and callable(end_suppression):
            begin_suppression()
            self._execution_runner.finished.connect(lambda end=end_suppression: end())

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
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return

        # 事件流子步骤在树上采用懒加载：执行线程触发 step_will_start 时，目标树项可能尚未创建。
        # 为避免“执行已在跑但左侧/中间联动看起来没反应”，当树项尚不存在时先主动驱动预览聚焦；
        # 后续树项就绪后仍会通过 ensure_item_built 的回调完成真正的步骤选中。
        existing_item = None
        if self.tree_manager is not None:
            existing_item = self.tree_manager.get_item_by_id(normalized_todo_id)
        if existing_item is None:
            _ = self._focus_preview_for_todo_id(normalized_todo_id)

        self._select_task_by_id(normalized_todo_id)

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
            # 成功态以“完成度勾选”表达：统一通过 TreeManager 收口完成状态变更，
            # 避免外部直接 setCheckState 导致 todo_states / 运行态清理 / 父级三态反推 / 持久化信号时序不一致。
            applied = self.tree_manager.set_leaf_checked(todo_id, True)
            if not applied:
                # 非叶子（理论上不应出现）：仅清理失败/跳过残留并刷新样式
                self.runtime_state.mark_success(todo_id)
                if todo is not None:
                    self._update_item_incrementally(item, todo)
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
        return self.ui_context.ensure_execution_monitor(switch_to=switch_tab)

    def _inject_context_to_monitor(
        self,
        monitor_panel,
        graph_model: GraphModel,
        executor: object | None = None,
    ) -> None:
        if monitor_panel is None:
            return
        workspace_path = self.ui_context.try_get_workspace_path()
        if workspace_path is None:
            self._notify("工作区未就绪，无法注入监控上下文", "error")
            return
        view_ref = None
        app_state = self.ui_context.get_app_state()
        if app_state is not None:
            view_ref = app_state.graph_view
        monitor_panel.attach_session(
            ExecutionSession(
                workspace_path=workspace_path,
                graph_model=graph_model,
                executor=executor,
                graph_view=view_ref,
            )
        )
        # 将“定位镜头识别成功”统一透传到 TodoPreviewPanel 的信号上，由编排层集中处理回填，
        # 避免同时存在“监控面板→编排层”和“监控面板→预览面板→编排层”两条链路导致重复回调。
        if self.preview_panel is not None:
            self.preview_panel.wire_recognition_from_monitor_panel(monitor_panel)

    def _build_executor_and_model(
        self,
        graph_data: dict,
        monitor_panel,
    ) -> Tuple[object, GraphModel]:
        workspace_path = self.ui_context.try_get_workspace_path()
        if workspace_path is None:
            raise RuntimeError("工作区未就绪：无法创建 EditorExecutor")
        executor_provider = EditorExecutorProvider()
        executor = executor_provider.get_or_create_executor(
            workspace_path=workspace_path,
            monitor_port=monitor_panel,
        )
        graph_model = GraphModel.deserialize(graph_data)
        return executor, graph_model

    def _focus_preview_for_todo_id(self, todo_id: str) -> bool:
        """在不依赖树项已创建的前提下，尽量同步右侧预览到指定 Todo。

        用途：
        - 事件流子步骤树项采用懒加载时，step_will_start 可能先到而树项尚未构建；
          此时先驱动预览聚焦，用户能立刻看到“当前步骤”的画板联动。
        """
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return False
        if self.preview_panel is None or self.tree_manager is None:
            return False

        todo = self.tree_manager.todo_map.get(normalized_todo_id)
        if todo is None:
            return False

        switched_to_preview = False
        if self.preview_panel.handle_composite_preview(todo, self.ui_context):
            switched_to_preview = True
        elif self.preview_panel.handle_graph_preview(
            todo,
            self.tree_manager.todo_map,
            tree_manager=self.tree_manager,
            ui_context=self.ui_context,
        ):
            switched_to_preview = True

        if switched_to_preview and hasattr(self.host, "right_stack"):
            self.host.right_stack.setCurrentIndex(1)
        return switched_to_preview

    def _select_task_by_id(self, todo_id: str) -> None:
        normalized_todo_id = str(todo_id or "")
        if not normalized_todo_id:
            return
        if self.tree_manager is None:
            return

        def _select_tree_item(target_item) -> None:
            if target_item is None:
                return
            # 统一通过 TreeManager 收口“current 状态”写入（展开父链/选中/滚动）
            _ = self.tree_manager.select_task_by_id(normalized_todo_id)

        existing_item = self.tree_manager.get_item_by_id(normalized_todo_id)
        if existing_item is not None:
            _select_tree_item(existing_item)
            return

        # 懒加载场景：目标步骤树项尚未创建。先尽量选中其所属事件流根，
        # 让用户至少看到“正在执行哪个事件流”，并触发一次父链展开。
        flow_root = self.tree_manager.find_event_flow_root_for_todo(normalized_todo_id)
        if flow_root is not None:
            flow_root_item = self.tree_manager.get_item_by_id(str(getattr(flow_root, "todo_id", "") or ""))
            if flow_root_item is not None:
                _select_tree_item(flow_root_item)

        # 事件流根子步骤可能尚未被 UI 懒加载创建：触发分批构建并在就绪后再选中
        self.tree_manager.ensure_item_built(normalized_todo_id, on_ready=_select_tree_item)

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

    def _maybe_show_graph_preflight_warning(self, graph_id: str) -> bool:
        """执行前弹窗提醒（每个节点图仅弹一次）。

        触发条件：当前 graph_id 的 Todo 集合中包含信号/结构体/复合节点相关步骤。
        """
        normalized_graph_id = str(graph_id or "")
        if not normalized_graph_id:
            return True
        if normalized_graph_id in self._preflight_warning_shown_graph_ids:
            return True
        if self.tree_manager is None:
            return True

        todo_map = getattr(self.tree_manager, "todo_map", {}) or {}
        summary = inspect_graph_execution_preflight(todo_map, normalized_graph_id)
        if not summary.should_warn:
            return True

        message = summary.build_dialog_message()
        if not message:
            return True

        signal_id_to_focus = summary.suggested_signal_id_for_navigation
        if summary.includes_signal and signal_id_to_focus:
            action_clicked = ask_warning_action_dialog(
                self.host,
                "执行前提醒",
                message,
                action_label="前往信号管理",
                continue_label="继续执行",
            )
            if action_clicked:
                self._navigate_to_signal_management(signal_id_to_focus)
                return False
        else:
            show_warning_dialog(self.host, "执行前提醒", message)

        self._preflight_warning_shown_graph_ids.add(normalized_graph_id)
        return True

    def _navigate_to_signal_management(self, signal_id: str) -> None:
        """跳转到【管理配置 → 信号管理】并尽量选中指定信号。"""
        signal_id_text = str(signal_id or "").strip()
        if not signal_id_text:
            return

        main_window = self.ui_context.get_main_window()
        if main_window is None:
            return
        nav = getattr(main_window, "nav_coordinator", None)
        if nav is None:
            return

        # 先切到管理模式，再定位到信号条目（避免在当前模式下直接 focus 无效）
        nav.navigate_to_mode.emit("management")
        QtCore.QTimer.singleShot(
            150,
            lambda sid=signal_id_text: nav.focus_management_section_and_item.emit("signals", sid),
        )
        # 尽量把右侧面板切到“信号”页签（若实现提供该入口）
        right_panel = getattr(main_window, "right_panel", None)
        ensure_visible = getattr(right_panel, "ensure_visible", None) if right_panel is not None else None
        if callable(ensure_visible):
            ensure_visible("signal_editor", visible=True, switch_to=True)


