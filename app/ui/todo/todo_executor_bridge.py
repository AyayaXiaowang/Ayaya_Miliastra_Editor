from __future__ import annotations

from typing import List, Optional, Tuple
from pathlib import Path

from PyQt6 import QtCore
from engine.graph.models.graph_model import GraphModel
from app.automation.core.editor_executor import EditorExecutor
from app.ui.execution import ExecutionRunner
from app.ui.execution.guides import ExecutionGuides
from app.ui.execution.planner import ExecutionPlanner
from app.ui.todo.todo_config import StepTypeRules
from app.ui.execution.strategies.step_skip_checker import SINGLE_STEP_SKIP_REASON
from app.ui.todo.current_todo_resolver import build_context_from_host, resolve_current_todo_for_leaf
from app.ui.todo.todo_execution_service import (
    RootExecutionPlan,
    StepExecutionPlan,
    StepExecutionError,
    plan_template_root_execution,
    plan_event_flow_root_execution,
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
        tree_manager=None,
        runtime_state=None,
        preview_panel=None,
        rich_segments_role: int = 0,
    ) -> None:
        super().__init__(host_widget)
        self.host = host_widget
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

        context = build_context_from_host(self.host)
        todo_map = getattr(self.tree_manager, "todo_map", {})
        find_flow_root = (
            self.tree_manager.find_event_flow_root_for_todo
            if hasattr(self.tree_manager, "find_event_flow_root_for_todo")
            else None
        )
        root_plan = plan_event_flow_root_execution(
            context,
            todo_map,
            find_template_root_for_item=self._find_template_graph_root_for_item,
            find_event_flow_root_for_todo=find_flow_root,
        )
        if root_plan is None:
            self._notify("内部错误：未找到当前任务项（current_todo）", "error")
            return

        current_flow_root = root_plan.root_todo

        item = self._get_item_by_id(current_flow_root.todo_id)
        template_root = self._find_template_graph_root_for_item(item) if item is not None else None
        graph_data = self._resolve_graph_data(current_flow_root, template_root or current_flow_root)
        if graph_data is None:
            return

        detail_info = current_flow_root.detail_info or {}
        graph_root_id = ""
        raw_root_id = detail_info.get("graph_root_todo_id")
        if isinstance(raw_root_id, str) and raw_root_id:
            graph_root_id = raw_root_id
        if not graph_root_id:
            parent_identifier = str(current_flow_root.parent_id or "")
            if parent_identifier:
                graph_root_id = parent_identifier
        if not graph_root_id:
            self._notify("内部错误：无法确定当前事件流所属的节点图根 Todo", "error")
            return

        graph_root = todo_map.get(graph_root_id)
        if graph_root is None:
            self._notify("内部错误：未找到所属节点图根 Todo", "error")
            return

        flow_roots_in_graph = []
        for child_id in graph_root.children:
            child = todo_map.get(child_id)
            if child is None:
                continue
            child_info = child.detail_info or {}
            if child_info.get("type") == "event_flow_root":
                flow_roots_in_graph.append(child)

        if not flow_roots_in_graph:
            self._notify("当前节点图未发现任何事件流", "warning")
            return

        start_index = -1
        for index, flow_root in enumerate(flow_roots_in_graph):
            if flow_root.todo_id == current_flow_root.todo_id:
                start_index = index
                break
        if start_index == -1:
            self._notify("内部错误：当前事件流不在所属节点图的事件流列表中", "error")
            return

        remaining_flow_roots = flow_roots_in_graph[start_index:]
        step_list = []
        for flow_root in remaining_flow_roots:
            planned_steps = ExecutionPlanner.plan_steps(flow_root, todo_map)
            if planned_steps:
                step_list.extend(planned_steps)

        monitor = self._ensure_monitor_panel(switch_tab=True)
        if monitor is None:
            self._notify("未找到执行监控面板，无法启动执行", "error")
            return

        executor, graph_model = self._build_executor_and_model(graph_data, monitor)
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
        todo_map = getattr(self.tree_manager, "todo_map", {})
        find_flow_root = (
            self.tree_manager.find_event_flow_root_for_todo
            if self.tree_manager and hasattr(self.tree_manager, "find_event_flow_root_for_todo")
            else None
        )
        find_template_root = (
            self.tree_manager.find_template_graph_root_for_todo
            if self.tree_manager and hasattr(self.tree_manager, "find_template_graph_root_for_todo")
            else None
        )
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
        todo_map = getattr(self.tree_manager, "todo_map", {})
        find_flow_root = (
            self.tree_manager.find_event_flow_root_for_todo
            if self.tree_manager and hasattr(self.tree_manager, "find_event_flow_root_for_todo")
            else None
        )
        find_template_root = (
            self.tree_manager.find_template_graph_root_for_todo
            if self.tree_manager and hasattr(self.tree_manager, "find_template_graph_root_for_todo")
            else None
        )
        step_plan, error = plan_single_step_execution(
            step_todo,
            todo_map,
            find_event_flow_root_for_todo=find_flow_root,
            find_template_root_for_todo=find_template_root,
        )
        if error is not None:
            user_message = getattr(error, "user_message", "") or ""
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
        context = build_context_from_host(self.host)
        todo_map = getattr(self.tree_manager, "todo_map", {})
        find_flow_root = (
            self.tree_manager.find_event_flow_root_for_todo
            if self.tree_manager and hasattr(self.tree_manager, "find_event_flow_root_for_todo")
            else None
        )
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
        context = build_context_from_host(self.host)
        todo_map = getattr(self.tree_manager, "todo_map", {})
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
        if hasattr(monitor, 'log'):
            executor.reset_mapping_state(monitor.log)
        else:
            executor.reset_mapping_state(None)
        self._inject_context_to_monitor(monitor, graph_model, executor)
        if not step_list:
            monitor.start_monitoring()
            monitor.log("当前节点图无可执行步骤：已打开监控。可使用『检查』或『定位镜头』进行识别与聚焦。")
            return
        # 预置第一步 tokens
        first_step = step_list[0] if step_list else None
        if first_step is not None and hasattr(monitor, 'set_current_step_tokens'):
            todo_map = getattr(self.tree_manager, 'todo_map', {}) if self.tree_manager else {}
            first_todo = todo_map.get(first_step.todo_id)
            if first_todo is not None:
                tokens = self._ensure_tokens_for_todo(first_todo.todo_id)
                if hasattr(monitor, 'set_current_step_context'):
                    monitor.set_current_step_context(first_todo.title, "")
                if isinstance(tokens, list):
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
        try:
            for idx, step in enumerate(step_list):
                todo_id = getattr(step, "todo_id", "") or ""
                if todo_id and todo_id not in self._run_step_order:
                    self._run_step_order[todo_id] = idx
        except Exception:
            # 映射失败不影响执行，仅影响结构化显示
            self._run_step_order = {}

        self._execution_runner.finished.connect(lambda: setattr(self, "_execution_runner", None))
        self._execution_runner.step_will_start.connect(self._on_step_will_start)
        self._execution_runner.step_will_start.connect(self._pause_if_step_mode)
        self._execution_runner.step_will_start.connect(self._set_monitor_step_context)
        if hasattr(monitor_panel, 'step_anchor_clicked'):
            # 监控面板是长生命周期组件，避免在多次执行时重复绑定 step_anchor_clicked → _on_step_anchor_clicked
            # 仅当监控面板实例发生变化时才重新连接
            if self._monitor_panel_for_step_anchor is not monitor_panel:
                monitor_panel.step_anchor_clicked.connect(self._on_step_anchor_clicked)
                self._monitor_panel_for_step_anchor = monitor_panel
        if continuous:
            self._execution_runner.step_completed.connect(self._complete_task_and_advance)
        else:
            self._execution_runner.step_completed.connect(self._complete_task_only)
        if hasattr(self._execution_runner, 'step_skipped'):
            self._execution_runner.step_skipped.connect(self._mark_task_skipped)
        self._execution_runner.finished.connect(self._restore_selection_after_run)
        self._execution_runner.finished.connect(self._restore_tree_expanded_state)
        # 结构化运行事件：准备本轮 run_id，并在结束时写入结果
        if hasattr(monitor_panel, "begin_run") and callable(getattr(monitor_panel, "begin_run")):
            try:
                monitor_panel.begin_run(self._run_total_steps)
            except Exception:
                pass
        if hasattr(monitor_panel, "end_run") and callable(getattr(monitor_panel, "end_run")):
            def _on_run_finished_for_monitor() -> None:
                success = not bool(self._run_had_failure)
                try:
                    monitor_panel.end_run(success)
                except Exception:
                    pass

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
        tree_manager = self.tree_manager
        if tree_manager is None or not hasattr(tree_manager, "get_item_map"):
            return
        item_map = tree_manager.get_item_map()
        if not isinstance(item_map, dict):
            return
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
        tree_manager = self.tree_manager
        if tree_manager is None or not hasattr(tree_manager, "get_item_map"):
            return
        item_map = tree_manager.get_item_map()
        if not isinstance(item_map, dict):
            return
        for todo_id, was_expanded in self._tree_expanded_state_snapshot.items():
            item = item_map.get(todo_id)
            if item is None:
                continue
            if item.childCount() <= 0:
                continue
            item.setExpanded(bool(was_expanded))
        self._tree_expanded_state_snapshot = {}

    # === Fallback 适配（未接入 TodoTreeManager / 预览面板时仍可工作） ===

    def _get_item_by_id(self, todo_id: str):
        if self.tree_manager and hasattr(self.tree_manager, 'get_item_by_id'):
            return self.tree_manager.get_item_by_id(todo_id)
        # 回退：读取宿主映射
        return getattr(self.host, '_item_map', {}).get(todo_id)

    def _ensure_tokens_for_todo(self, todo_id: str):
        if self.tree_manager and hasattr(self.tree_manager, 'ensure_tokens_for_todo'):
            return self.tree_manager.ensure_tokens_for_todo(todo_id)
        # 回退：调用宿主生成 tokens 后读取
        item = self._get_item_by_id(todo_id)
        todo = self.host.todo_map.get(todo_id) if hasattr(self.host, 'todo_map') else None
        role = getattr(self, 'RICH_SEGMENTS_ROLE', 0)
        if item is None or todo is None or not hasattr(self.host, '_update_item_rich_tokens'):
            return None
        self.host._update_item_rich_tokens(item, todo)
        tokens = item.data(0, role)
        return tokens if isinstance(tokens, list) else None

    def _update_item_incrementally(self, item, todo) -> None:
        if self.tree_manager and hasattr(self.tree_manager, 'update_item_incrementally'):
            self.tree_manager.update_item_incrementally(item, todo)
            return
        if hasattr(self.host, '_update_item_incrementally'):
            self.host._update_item_incrementally(item, todo)

    # === Runner 槽 ===

    def _on_step_anchor_clicked(self, todo_id: str) -> None:
        self._select_task_by_id(todo_id)

    def _on_step_will_start(self, todo_id: str) -> None:
        self._select_task_by_id(todo_id)

    def _complete_task_and_advance(self, todo_id: str, success: bool) -> None:
        if self.tree_manager is None or self.runtime_state is None:
            return
        item = self._get_item_by_id(todo_id)
        if item is None:
            return
        todo = getattr(self.tree_manager, 'todo_map', {}).get(todo_id)
        # 结构化运行状态：记录失败标记
        if not success:
            self._run_had_failure = True

        if success:
            self.runtime_state.mark_success(todo_id)
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        else:
            self.runtime_state.mark_failed(todo_id, "该步骤执行失败")
            if todo:
                self._update_item_incrementally(item, todo)

        # 将“步骤完成”写入执行监控的结构化事件表
        monitor = getattr(self.host, "_monitor_window", None)
        if monitor and hasattr(monitor, "notify_step_completed"):
            try:
                title = todo.title if todo else ""
                index = self._run_step_order.get(todo_id)
                total = self._run_total_steps or None
                reason = None if success else "该步骤执行失败"
                monitor.notify_step_completed(todo_id, title, index, total, success, reason)
            except Exception:
                pass
        monitor = getattr(self.host, "_monitor_window", None)
        if monitor and hasattr(monitor, "is_step_mode_enabled") and callable(getattr(monitor, "is_step_mode_enabled")):
            if monitor.is_step_mode_enabled():
                return
        self.host.nav_controller.navigate_to_next_task()

    def _complete_task_only(self, todo_id: str, success: bool) -> None:
        if self.tree_manager is None or self.runtime_state is None:
            return
        item = self._get_item_by_id(todo_id)
        if item is None:
            return
        todo = getattr(self.tree_manager, 'todo_map', {}).get(todo_id)
        # 结构化运行状态：记录失败标记
        if not success:
            self._run_had_failure = True

        if success:
            self.runtime_state.mark_success(todo_id)
            item.setCheckState(0, QtCore.Qt.CheckState.Checked)
        else:
            self.runtime_state.mark_failed(todo_id, "该步骤执行失败")
            if todo:
                self._update_item_incrementally(item, todo)

        # 将“步骤完成”写入执行监控的结构化事件表
        monitor = getattr(self.host, "_monitor_window", None)
        if monitor and hasattr(monitor, "notify_step_completed"):
            try:
                title = todo.title if todo else ""
                index = self._run_step_order.get(todo_id)
                total = self._run_total_steps or None
                reason = None if success else "该步骤执行失败"
                monitor.notify_step_completed(todo_id, title, index, total, success, reason)
            except Exception:
                pass

    def _mark_task_skipped(self, todo_id: str, reason: str) -> None:
        if self.tree_manager is None or self.runtime_state is None:
            return
        item = self._get_item_by_id(todo_id)
        todo = getattr(self.tree_manager, 'todo_map', {}).get(todo_id)
        if not item or not todo:
            return
        normalized_reason = str(reason or "该步骤因端点距离过远被跳过")
        # 单步执行模式下，非目标步骤仅作为上下文参与规划，不在任务树中高亮为“跳过”，以免误导用户。
        if normalized_reason == SINGLE_STEP_SKIP_REASON:
            return
        self.runtime_state.mark_skipped(todo_id, normalized_reason)
        self._update_item_incrementally(item, todo)
        # 推送“跳过步骤”到执行监控结构化事件
        monitor = getattr(self.host, "_monitor_window", None)
        if monitor and hasattr(monitor, "notify_step_skipped"):
            try:
                title = todo.title
                index = self._run_step_order.get(todo_id)
                total = self._run_total_steps or None
                monitor.notify_step_skipped(todo_id, title, index, total, normalized_reason)
            except Exception:
                pass

    def _pause_if_step_mode(self, _todo_id: str) -> None:
        monitor = getattr(self.host, "_monitor_window", None)
        if monitor and hasattr(monitor, "is_step_mode_enabled") and callable(getattr(monitor, "is_step_mode_enabled")):
            if monitor.is_step_mode_enabled() and hasattr(monitor, "request_pause"):
                monitor.request_pause()

    def _set_monitor_step_context(self, todo_id: str) -> None:
        monitor = getattr(self.host, "_monitor_window", None)
        if not monitor or not hasattr(monitor, "set_current_step_context"):
            return
        todo = getattr(self.tree_manager, 'todo_map', {}).get(todo_id) if self.tree_manager else None
        if not todo:
            return
        parent_title = ""
        item = self._get_item_by_id(todo_id)
        if item is not None:
            parent_item = item.parent()
            if parent_item is not None:
                parent_id = parent_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
                parent_todo = getattr(self.tree_manager, "todo_map", {}).get(parent_id) if self.tree_manager else None
                if parent_todo:
                    parent_title = parent_todo.title
        monitor.set_current_step_context(todo.title, parent_title)
        if hasattr(monitor, 'set_current_step_tokens'):
            tokens = self._ensure_tokens_for_todo(todo_id)
            if isinstance(tokens, list):
                monitor.set_current_step_tokens(todo_id, tokens)

        # 同步结构化执行事件：记录“步骤开始”
        if hasattr(monitor, "notify_step_started"):
            try:
                index = self._run_step_order.get(todo_id)
                total = self._run_total_steps or None
                monitor.notify_step_started(todo_id, todo.title, index, total)
            except Exception:
                pass

    def _restore_selection_after_run(self) -> None:
        # 仅在连续执行（整图 / 从此步到末尾）场景下恢复选中项：
        # - 单步执行时，执行前后选中项本身就是当前步骤，无需额外恢复，避免打乱用户的浏览位置。
        if not getattr(self, "_run_is_continuous", False):
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
            main_window=getattr(self.host, "main_window", None),
        )
        if isinstance(graph_data, dict) and ("nodes" in graph_data or "edges" in graph_data):
            return graph_data

        self._log_to_monitor_or_toast("✗ 缺少图数据（graph_data），无法执行")
        return None

    def _ensure_monitor_panel(self, switch_tab: bool = False):
        main_window = getattr(self.host, "main_window", None)
        if not main_window or not hasattr(main_window, "execution_monitor_panel"):
            return None

        monitor_panel = main_window.execution_monitor_panel
        # 优先通过主窗口提供的公开 API 管理右侧标签，避免在 todo 层直接操作 side_tab 结构。
        ensure_visible = getattr(main_window, "ensure_execution_monitor_panel_visible", None)
        if callable(ensure_visible):
            ensure_visible(visible=True, switch_to=switch_tab)
        else:
            # 当主窗口未提供显式 API 时，退回到直接挂载逻辑。
            side_tab = getattr(main_window, "side_tab", None)
            if side_tab is not None:
                index_in_tab = side_tab.indexOf(monitor_panel)
                if index_in_tab == -1:
                    tab_title = "执行监控"
                    if hasattr(main_window, "_tab_title_for_id"):
                        tab_title = main_window._tab_title_for_id("execution_monitor")
                    side_tab.addTab(monitor_panel, tab_title)
                if switch_tab:
                    side_tab.setCurrentWidget(monitor_panel)
                if hasattr(main_window, "_update_right_panel_visibility"):
                    main_window._update_right_panel_visibility()

        self.host._monitor_window = monitor_panel
        return monitor_panel

    def _inject_context_to_monitor(self, monitor_panel, graph_model: GraphModel, executor: Optional[EditorExecutor] = None) -> None:
        if not monitor_panel or not hasattr(monitor_panel, 'set_context'):
            return
        view_ref = self.host.main_window.view if (self.host.main_window and hasattr(self.host.main_window, 'view')) else None
        monitor_panel.set_context(self._get_workspace_path(), graph_model, view_ref)
        if executor is not None and hasattr(monitor_panel, "set_shared_executor"):
            monitor_panel.set_shared_executor(executor)
        if hasattr(monitor_panel, 'recognition_focus_succeeded'):
            if not getattr(monitor_panel, '_todo_recognition_bound', False):
                orchestrator = getattr(self.host, "_orchestrator", None)
                if orchestrator is not None and hasattr(orchestrator, "on_recognition_focus_succeeded"):
                    monitor_panel.recognition_focus_succeeded.connect(orchestrator.on_recognition_focus_succeeded)
                    setattr(monitor_panel, '_todo_recognition_bound', True)

    def _build_executor_and_model(self, graph_data: dict, monitor_panel) -> Tuple[EditorExecutor, GraphModel]:
        workspace_path = self._get_workspace_path()
        executor: Optional[EditorExecutor] = None
        # 优先复用监控面板中已存在的执行器实例，保持与“检查/定位镜头/拖拽测试”一致的视口状态与缓存
        if monitor_panel is not None and hasattr(monitor_panel, "get_shared_executor"):
            shared = monitor_panel.get_shared_executor()
            if shared is not None and getattr(shared, "workspace_path", None) == workspace_path:
                executor = shared
        if executor is None:
            executor = EditorExecutor(workspace_path)
        if hasattr(monitor_panel, "set_shared_executor"):
            monitor_panel.set_shared_executor(executor)
        graph_model = GraphModel.deserialize(graph_data)
        return executor, graph_model

    def _get_workspace_path(self) -> Path:
        if self.host.main_window and hasattr(self.host.main_window, 'workspace_path'):
            return Path(self.host.main_window.workspace_path)
        current_file = Path(__file__).resolve()
        return current_file.parent.parent

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
        if not self.tree_manager or not hasattr(self.tree_manager, "find_template_graph_root_for_todo"):
            return None

        base_todo_id = ""
        if start_item is not None:
            base_todo_id = start_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not base_todo_id:
            base_todo_id = getattr(self.host, "current_todo_id", "") or ""
        if not base_todo_id:
            return None
        return self.tree_manager.find_template_graph_root_for_todo(str(base_todo_id))

    def _notify(self, message: str, toast_type: str = "info") -> None:
        self.host._notify(message, toast_type)

    def _log_to_monitor_or_toast(self, text: str) -> None:
        monitor_panel = self._ensure_monitor_panel()
        if monitor_panel is not None:
            if hasattr(self.host.main_window, 'side_tab'):
                self.host.main_window.side_tab.setCurrentWidget(monitor_panel)
            if hasattr(monitor_panel, 'start_monitoring'):
                monitor_panel.start_monitoring()
            if hasattr(monitor_panel, 'log'):
                monitor_panel.log(text)
        else:
            self._notify(text, "error")


