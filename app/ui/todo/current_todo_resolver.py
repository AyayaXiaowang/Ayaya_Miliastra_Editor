"""当前 Todo 统一解析器

🎯 设计目标
==========
将"当前 Todo"的解析规则收敛到单一模块，避免在编排层和桥接层各自实现一套优先级策略。

统一优先级规则：
1. 树选中项（与用户视觉上的"当前任务"一致）
2. current_todo_id（由详情面板/外部跳转维护）
3. detail_info 全量匹配（用于外部联动/旧上下文恢复）
4. graph_id 兜底（用于任务清单刷新后 ID 发生变化的情况）

对于根执行（模板图根/事件流根）：
- 如果当前选中的是叶子步骤，会沿父链回溯到对应的根节点

使用方式：
- 编排层和桥接层都通过本模块的函数解析当前 Todo
- 不再各自实现解析逻辑
"""

from dataclasses import dataclass
from typing import Optional, Dict, List, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import TodoItem
    from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem


@dataclass
class CurrentTodoContext:
    """当前 Todo 解析所需的上下文信息。

    所有状态来源都通过这个结构传入，解析器本身不依赖任何 UI 对象。
    """

    # 树当前选中项的 todo_id（由调用方从树控件取出）
    selected_todo_id: str

    # 宿主维护的当前 todo_id（通常由详情面板/外部跳转设置）
    current_todo_id: str

    # 当前详情信息（用于 detail_info 全量匹配和 graph_id 兜底）
    current_detail_info: Optional[Dict]

    # todo_id -> TodoItem 的映射表
    todo_map: Dict[str, "TodoItem"]

    # 所有 TodoItem 列表（用于 detail_info 全量匹配）
    todos: List["TodoItem"]

    # 按 graph_id 查找第一个可执行叶子步骤的回调（可选）
    find_first_todo_for_graph: Optional[Callable[[str], Optional["TodoItem"]]] = None

    # 按 todo_id 查找树项的回调（用于父链回溯，可选）
    get_item_by_id: Optional[Callable[[str], Optional["QTreeWidgetItem"]]] = None


# ============================================================================
# 统一优先级规则
# ============================================================================
#
# 叶子步骤执行（resolve_current_todo_for_leaf）：
#   1. 树选中项（与用户视觉上的"当前任务"一致）
#   2. current_todo_id（由详情面板/外部跳转维护）
#   3. detail_info 全量匹配（用于外部联动/旧上下文恢复）
#   4. graph_id 兜底（用于任务清单刷新后 ID 发生变化的情况）
#
# 根执行（resolve_current_todo_for_root）：
#   1. 树选中项
#   2. current_todo_id
#   3. detail_info 全量匹配
#   然后：如果当前选中的是叶子步骤，会沿父链回溯到对应的根节点
#
# ============================================================================


def resolve_current_todo_for_leaf(context: CurrentTodoContext) -> Optional["TodoItem"]:
    """解析当前要执行的叶子 Todo。

    优先级：
    1. 树选中项的 todo_id
    2. current_todo_id
    3. detail_info 全量匹配
    4. graph_id 兜底

    返回:
        解析到的 TodoItem，或 None（如果无法解析）
    """
    todo_map = context.todo_map

    # 1) 优先使用树选中项（与用户视觉上的"当前任务"一致）
    if context.selected_todo_id:
        candidate = todo_map.get(context.selected_todo_id)
        if candidate is not None:
            return candidate

    # 2) 回退：使用 current_todo_id
    if context.current_todo_id:
        candidate = todo_map.get(context.current_todo_id)
        if candidate is not None:
            return candidate

    # 3) 回退：基于 detail_info 进行全量匹配
    if context.current_detail_info and context.todos:
        for candidate in context.todos:
            if candidate.detail_info == context.current_detail_info:
                return candidate

    # 4) 兜底：基于 graph_id 查找一个可执行叶子步骤
    if context.current_detail_info and context.find_first_todo_for_graph:
        graph_identifier = str(context.current_detail_info.get("graph_id") or "")
        if graph_identifier:
            fallback_todo = context.find_first_todo_for_graph(graph_identifier)
            if fallback_todo is not None:
                return fallback_todo

    return None


def resolve_current_todo_for_root(
    context: CurrentTodoContext,
    find_template_root_for_item: Optional[Callable] = None,
    find_event_flow_root_for_todo: Optional[Callable[[str], Optional["TodoItem"]]] = None,
    root_type: str = "template",
) -> Optional["TodoItem"]:
    """解析当前要执行的根 Todo（模板图根或事件流根）。

    优先级：
    1. 树选中项的 todo_id
    2. current_todo_id
    3. detail_info 全量匹配

    如果解析到的 Todo 不是根类型，会尝试沿父链回溯到对应的根节点。

    参数:
        context: 解析上下文
        find_template_root_for_item: 从树项查找模板图根的回调
        find_event_flow_root_for_todo: 从 todo_id 查找事件流根的回调
        root_type: 根类型，"template" 或 "flow"

    返回:
        解析到的根 TodoItem，或 None（如果无法解析）
    """
    todo_map = context.todo_map
    current_todo = None

    # 1) 优先使用树选中项
    if context.selected_todo_id:
        current_todo = todo_map.get(context.selected_todo_id)

    # 2) 回退：使用 current_todo_id
    if current_todo is None and context.current_todo_id:
        current_todo = todo_map.get(context.current_todo_id)

    # 3) 回退：基于 detail_info 进行全量匹配
    if current_todo is None and context.current_detail_info and context.todos:
        for candidate in context.todos:
            if candidate.detail_info == context.current_detail_info:
                current_todo = candidate
                break

    if current_todo is None:
        return None

    # 检查是否需要回溯到根
    detail_info = getattr(current_todo, "detail_info", None) or {}
    detail_type = detail_info.get("type", "")

    if root_type == "template":
        # 模板图根执行：如果当前不是模板图根，沿父链回溯
        if detail_type != "template_graph_root":
            if find_template_root_for_item and context.get_item_by_id:
                item = context.get_item_by_id(current_todo.todo_id)
                if item is not None:
                    root_todo = find_template_root_for_item(item)
                    if root_todo is not None:
                        return root_todo
            # 回溯失败，返回当前 todo（让调用方决定如何处理）
            return current_todo
        return current_todo

    elif root_type == "flow":
        # 事件流根执行：如果当前不是事件流根，查找对应的事件流根
        if detail_type != "event_flow_root":
            if find_event_flow_root_for_todo:
                flow_root = find_event_flow_root_for_todo(current_todo.todo_id)
                if flow_root is not None:
                    return flow_root
            # 回溯失败，返回当前 todo
            return current_todo
        return current_todo

    return current_todo


def get_selected_todo_id_from_tree(tree: "QTreeWidget") -> str:
    """从树控件获取当前选中项的 todo_id。

    这是一个辅助函数，用于构造 CurrentTodoContext。

    参数:
        tree: 树控件

    返回:
        选中项的 todo_id，如果没有选中项则返回空字符串
    """
    from PyQt6.QtCore import Qt

    if tree is None:
        return ""

    current_item = tree.currentItem()
    if current_item is None:
        return ""

    todo_id = current_item.data(0, Qt.ItemDataRole.UserRole)
    return str(todo_id) if todo_id else ""


def build_context_from_host(host) -> CurrentTodoContext:
    """从宿主组件构造解析上下文。

    这是一个便捷函数，用于从 TodoListWidget 或类似宿主构造 CurrentTodoContext。

    参数:
        host: 宿主组件（需要有 tree, current_todo_id, current_detail_info, todo_map, todos 属性）

    返回:
        构造好的 CurrentTodoContext
    """
    tree = getattr(host, "tree", None)
    selected_todo_id = get_selected_todo_id_from_tree(tree) if tree else ""

    # 获取 find_first_todo_for_graph 回调
    find_first_todo_for_graph = None
    if hasattr(host, "find_first_todo_for_graph"):
        find_first_todo_for_graph = host.find_first_todo_for_graph

    # 获取 get_item_by_id 回调
    get_item_by_id = None
    tree_manager = getattr(host, "tree_manager", None)
    if tree_manager and hasattr(tree_manager, "get_item_by_id"):
        get_item_by_id = tree_manager.get_item_by_id

    # Todo 数据统一以 TreeManager 作为集中权威来源，其次才回退到宿主自身字段
    tree_manager = getattr(host, "tree_manager", None)
    if tree_manager is not None:
        todo_map = getattr(tree_manager, "todo_map", {}) or {}
        todos = getattr(tree_manager, "todos", []) or []
    else:
        todo_map = getattr(host, "todo_map", {}) or {}
        todos = getattr(host, "todos", []) or []

    return CurrentTodoContext(
        selected_todo_id=selected_todo_id,
        current_todo_id=getattr(host, "current_todo_id", "") or "",
        current_detail_info=getattr(host, "current_detail_info", None),
        todo_map=todo_map,
        todos=todos,
        find_first_todo_for_graph=find_first_todo_for_graph,
        get_item_by_id=get_item_by_id,
    )

