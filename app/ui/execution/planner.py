# -*- coding: utf-8 -*-
"""
执行步骤规划：从当前选中的任务节点推导出可执行的节点图步骤序列。
"""

from typing import List, Dict

from app.models import TodoItem


SUPPORTED_STEP_TYPES = {
    "graph_create_node",
    "graph_connect",
    "graph_connect_merged",
    "graph_create_and_connect",
    "graph_set_port_types_merged",
    "graph_config_node_merged",
    # 动态端口相关
    "graph_add_variadic_inputs",
    "graph_add_dict_pairs",
    "graph_add_branch_outputs",
    "graph_config_branch_outputs",
    "graph_bind_signal",
}


class ExecutionPlanner:
    """执行计划器：将任务清单转换为可执行步骤序列。"""

    @staticmethod
    def _filter_supported_steps(steps: List[TodoItem]) -> List[TodoItem]:
        """仅保留自动化执行器真正支持的节点图步骤类型。

        说明：
        - 执行器只认识上述 SUPPORTED_STEP_TYPES 对应的 `graph_*` 叶子步骤；
        - 模板图根、事件流根、变量总表、信号概览等结构性 Todo 只参与导航和展示，
          不应被送入执行器，否则会在第一步就报“类型不支持”的错误。
        """
        filtered: List[TodoItem] = []
        for step in steps:
            info = step.detail_info or {}
            step_type = str(info.get("type", ""))
            if step_type in SUPPORTED_STEP_TYPES:
                filtered.append(step)
        return filtered

    @staticmethod
    def plan_steps(current_todo: TodoItem, todo_map: Dict[str, TodoItem]) -> List[TodoItem]:
        """严格按左侧列表顺序返回**可执行**步骤。

        规则：
        - 若存在 `event_flow_root`，按其 children 顺序返回，并过滤出受支持的 `graph_*` 叶子步骤；
        - 否则，按当前节点的 children 顺序返回，同样仅保留受支持的步骤类型。
        """
        # 优先：事件流根 → 按子项原始顺序原样收集，再做类型过滤
        flow_root = None
        for child_id in current_todo.children:
            child = todo_map.get(child_id)
            if child and (child.detail_info or {}).get("type") == "event_flow_root":
                flow_root = child
                break

        if flow_root is not None:
            raw_steps: List[TodoItem] = []
            for step_id in flow_root.children:
                step = todo_map.get(step_id)
                if step is not None:
                    raw_steps.append(step)
            return ExecutionPlanner._filter_supported_steps(raw_steps)

        # 回退：无事件流根时，直接返回当前层级的子项顺序（同样做类型过滤）
        raw_steps: List[TodoItem] = []
        for child_id in current_todo.children:
            child = todo_map.get(child_id)
            if child is not None:
                raw_steps.append(child)
        return ExecutionPlanner._filter_supported_steps(raw_steps)
