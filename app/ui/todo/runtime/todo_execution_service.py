from __future__ import annotations

"""Todo 执行规划领域服务（纯逻辑模块，不依赖 Qt）。

职责：
- 基于 CurrentTodoContext 与 todo_map 解析当前要执行的根 Todo；
- 为模板图根 / 事件流根构建执行步骤列表；
- 为“从此步起执行剩余步骤”与“仅执行此一步”提供统一的规划逻辑。

该模块不负责：
- 图数据解析与缓存（交由 TodoExecutorBridge 与预览/树支持处理）；
- 执行线程与监控面板 wiring（交由 TodoExecutorBridge 处理）；
- UI 提示与日志输出（仅通过返回值向调用方暴露错误原因）。
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models import TodoItem
from app.ui.execution.planner import ExecutionPlanner, SUPPORTED_STEP_TYPES
from app.ui.todo.runtime.current_todo_resolver import CurrentTodoContext, resolve_current_todo_for_root
from app.models.todo_detail_info_accessors import get_detail_type
from app.ui.todo.misc.todo_config import StepTypeRules


FindTemplateRootForItem = Callable[[Any], Optional[TodoItem]]
FindEventFlowRootForTodo = Callable[[str], Optional[TodoItem]]
FindTemplateRootForTodo = Callable[[str], Optional[TodoItem]]


@dataclass(frozen=True)
class RootExecutionPlan:
    """根执行规划结果：模板图根或事件流根 + 其执行步骤列表。"""

    root_todo: TodoItem
    step_list: List[TodoItem]


@dataclass(frozen=True)
class RemainingEventFlowsExecutionPlan:
    """“从当前事件流起执行剩余事件流”的规划结果。"""

    current_flow_root: TodoItem
    graph_root: TodoItem
    flow_roots: List[TodoItem]
    step_list: List[TodoItem]


@dataclass(frozen=True)
class RemainingEventFlowsExecutionError:
    """“剩余事件流执行”规划失败原因（供 UI 层提示）。"""

    reason: str
    user_message: str = ""


@dataclass(frozen=True)
class StepExecutionPlan:
    """单步/从此步起执行规划结果。"""

    anchor_todo: TodoItem
    step_list: List[TodoItem]
    selection_to_restore: str
    # 可选：在需要区分“真正执行步骤”与“仅用于上下文的步骤”时，用于标记目标 todo_id。
    single_step_target_id: Optional[str] = None


@dataclass(frozen=True)
class StepExecutionError:
    """单步执行规划失败原因（供 UI 层决定提示文案）。

    reason: 机器可读错误码，例如 "unsupported_type"；
    detail_type: 对应步骤的 detail_type；
    user_message: 推荐给 UI 展示的人类可读提示文案。
    """

    reason: str
    detail_type: str
    user_message: str = ""


# === 根执行规划 ===


def plan_template_root_execution(
    context: CurrentTodoContext,
    todo_map: Dict[str, TodoItem],
    find_template_root_for_item: Optional[FindTemplateRootForItem] = None,
) -> Optional[RootExecutionPlan]:
    """根据当前上下文规划“模板图根执行”。

    解析规则委托给 `resolve_current_todo_for_root`：
    - 优先使用树选中项；
    - 回退到 current_todo_id；
    - 再回退到 detail_info 全量匹配。
    若解析结果不是模板图根，则尝试通过 `find_template_root_for_item` 沿树项回溯到模板图根。
    """
    root_todo = resolve_current_todo_for_root(
        context,
        find_template_root_for_item=find_template_root_for_item,
        root_type="template",
    )
    if root_todo is None:
        return None

    step_list = ExecutionPlanner.plan_steps(root_todo, todo_map)
    return RootExecutionPlan(root_todo=root_todo, step_list=step_list)


def plan_event_flow_root_execution(
    context: CurrentTodoContext,
    todo_map: Dict[str, TodoItem],
    find_template_root_for_item: Optional[FindTemplateRootForItem] = None,
    find_event_flow_root_for_todo: Optional[FindEventFlowRootForTodo] = None,
) -> Optional[RootExecutionPlan]:
    """根据当前上下文规划“事件流根执行”。

    与模板图根类似，但在解析到的 Todo 不是事件流根时，会尝试通过
    `find_event_flow_root_for_todo` 回溯到对应的事件流根。
    """
    flow_root_todo = resolve_current_todo_for_root(
        context,
        find_template_root_for_item=find_template_root_for_item,
        find_event_flow_root_for_todo=find_event_flow_root_for_todo,
        root_type="flow",
    )
    if flow_root_todo is None:
        return None

    step_list = ExecutionPlanner.plan_steps(flow_root_todo, todo_map)
    return RootExecutionPlan(root_todo=flow_root_todo, step_list=step_list)


def plan_remaining_event_flows_execution(
    context: CurrentTodoContext,
    todo_map: Dict[str, TodoItem],
    *,
    find_template_root_for_item: Optional[FindTemplateRootForItem] = None,
    find_event_flow_root_for_todo: Optional[FindEventFlowRootForTodo] = None,
) -> Tuple[Optional[RemainingEventFlowsExecutionPlan], Optional[RemainingEventFlowsExecutionError]]:
    """规划“从当前事件流起，连续执行同一节点图下的剩余事件流序列”。"""
    current_flow_root = resolve_current_todo_for_root(
        context,
        find_template_root_for_item=find_template_root_for_item,
        find_event_flow_root_for_todo=find_event_flow_root_for_todo,
        root_type="flow",
    )
    if current_flow_root is None:
        return None, RemainingEventFlowsExecutionError(
            reason="no_current_todo",
            user_message="无法执行：未找到当前选择的任务步骤。",
        )

    graph_root_id = _resolve_graph_root_todo_id_for_flow(current_flow_root)
    if not graph_root_id:
        return None, RemainingEventFlowsExecutionError(
            reason="missing_graph_root_id",
            user_message="无法执行：无法定位当前步骤所属的节点图。",
        )

    graph_root = todo_map.get(graph_root_id)
    if graph_root is None:
        return None, RemainingEventFlowsExecutionError(
            reason="graph_root_not_found",
            user_message="无法执行：无法定位所属的节点图。",
        )

    flow_roots_in_graph: List[TodoItem] = []
    for child_id in graph_root.children:
        child = todo_map.get(child_id)
        if child is None:
            continue
        detail_info = child.detail_info or {}
        if StepTypeRules.is_event_flow_root(get_detail_type(detail_info)):
            flow_roots_in_graph.append(child)

    if not flow_roots_in_graph:
        return None, RemainingEventFlowsExecutionError(
            reason="no_event_flows",
            user_message="当前节点图未发现任何事件流",
        )

    start_index = -1
    for index, flow_root in enumerate(flow_roots_in_graph):
        if flow_root.todo_id == current_flow_root.todo_id:
            start_index = index
            break
    if start_index == -1:
        return None, RemainingEventFlowsExecutionError(
            reason="current_flow_not_in_graph",
            user_message="无法执行：当前步骤不在有效的执行序列中。",
        )

    remaining_flow_roots = flow_roots_in_graph[start_index:]
    step_list: List[TodoItem] = []
    for flow_root in remaining_flow_roots:
        planned_steps = ExecutionPlanner.plan_steps(flow_root, todo_map)
        if planned_steps:
            step_list.extend(planned_steps)

    plan = RemainingEventFlowsExecutionPlan(
        current_flow_root=current_flow_root,
        graph_root=graph_root,
        flow_roots=remaining_flow_roots,
        step_list=step_list,
    )
    return plan, None


# === 步骤级执行规划 ===


def plan_execute_from_this_step(
    start_todo: TodoItem,
    todo_map: Dict[str, TodoItem],
    find_event_flow_root_for_todo: Optional[FindEventFlowRootForTodo] = None,
    find_template_root_for_todo: Optional[FindTemplateRootForTodo] = None,
) -> StepExecutionPlan:
    """规划“从当前叶子步骤到同级末尾”的连续执行序列。

    规划策略：
    - 优先在所属事件流根上进行规划（若能解析到事件流根）；
    - 否则退回到模板图根；
    - 再否则退回到直接父节点；
    - 最后退回到自身 Todo。
    """
    template_root: Optional[TodoItem] = None
    if find_template_root_for_todo is not None:
        template_root = find_template_root_for_todo(start_todo.todo_id)

    anchor_todo = _pick_planning_anchor(
        start_todo=start_todo,
        template_root_for_todo=template_root,
        find_event_flow_root_for_todo=find_event_flow_root_for_todo,
        todo_map=todo_map,
    )
    step_list = _build_step_sequence(anchor_todo, start_todo, todo_map)
    return StepExecutionPlan(
        anchor_todo=anchor_todo,
        step_list=step_list,
        selection_to_restore=start_todo.todo_id,
        single_step_target_id=None,
    )


def plan_single_step_execution(
    step_todo: TodoItem,
    todo_map: Dict[str, TodoItem],
    find_event_flow_root_for_todo: Optional[FindEventFlowRootForTodo] = None,
    find_template_root_for_todo: Optional[FindTemplateRootForTodo] = None,
) -> Tuple[Optional[StepExecutionPlan], Optional[StepExecutionError]]:
    """规划“仅执行此一步”（严格单步）。

    约定：
    - 始终只返回包含当前步骤本身的执行计划（`step_list == [step_todo]`）；
    - 若步骤类型不在 SUPPORTED_STEP_TYPES 内，则返回错误并由调用方决定提示文案。
    """
    template_root: Optional[TodoItem] = None
    if find_template_root_for_todo is not None:
        template_root = find_template_root_for_todo(step_todo.todo_id)

    anchor_todo = _pick_planning_anchor(
        start_todo=step_todo,
        template_root_for_todo=template_root,
        find_event_flow_root_for_todo=find_event_flow_root_for_todo,
        todo_map=todo_map,
    )

    detail_info = step_todo.detail_info or {}
    detail_type = get_detail_type(detail_info)
    if detail_type not in SUPPORTED_STEP_TYPES:
        message = (
            f"✗ 当前步骤类型不支持自动执行：{detail_type}。"
            "请前往【设置】页面，将【步骤生成顺序】切换为【AI-先配置后连线】或【AI-逐个节点模式】（不是【人类模式】）后再试。"
            "设置完成后，请在左侧选择具体的节点图操作步骤（创建节点/连线/配置等）再执行。"
        )
        return None, StepExecutionError(
            reason="unsupported_type",
            detail_type=detail_type,
            user_message=message,
        )

    step_list = [step_todo]

    plan = StepExecutionPlan(
        anchor_todo=anchor_todo,
        step_list=step_list,
        selection_to_restore=step_todo.todo_id,
        single_step_target_id=None,
    )
    return plan, None


# === 内部工具 ===


def _pick_planning_anchor(
    start_todo: TodoItem,
    template_root_for_todo: Optional[TodoItem],
    find_event_flow_root_for_todo: Optional[FindEventFlowRootForTodo],
    todo_map: Dict[str, TodoItem],
) -> TodoItem:
    """选择执行规划的锚点 Todo（事件流根 / 模板图根 / 父节点 / 自身）。"""
    if find_event_flow_root_for_todo is not None:
        flow_root = find_event_flow_root_for_todo(start_todo.todo_id)
        if flow_root is not None:
            return flow_root

    if template_root_for_todo is not None:
        return template_root_for_todo

    parent_id = getattr(start_todo, "parent_id", "") or ""
    if parent_id:
        parent_todo = todo_map.get(parent_id)
        if parent_todo is not None:
            return parent_todo

    return start_todo


def _build_step_sequence(
    anchor_todo: TodoItem,
    start_todo: TodoItem,
    todo_map: Dict[str, TodoItem],
) -> List[TodoItem]:
    """基于锚点 Todo 构建从指定步骤开始的连续执行序列。"""
    planned_steps = ExecutionPlanner.plan_steps(anchor_todo, todo_map)
    if not planned_steps:
        return []

    start_index = -1
    for index, planned_step in enumerate(planned_steps):
        if planned_step.todo_id == start_todo.todo_id:
            start_index = index
            break

    if start_index == -1:
        return [start_todo]
    return planned_steps[start_index:]


def _resolve_graph_root_todo_id_for_flow(flow_root: TodoItem) -> str:
    """从事件流根 Todo 推导其所属的节点图根 Todo ID。"""
    detail_info = flow_root.detail_info or {}
    raw_root_id = detail_info.get("graph_root_todo_id")
    if isinstance(raw_root_id, str) and raw_root_id:
        return raw_root_id
    parent_id = getattr(flow_root, "parent_id", "") or ""
    return str(parent_id) if parent_id else ""


