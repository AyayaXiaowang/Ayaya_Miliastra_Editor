"""TodoItem 构建辅助函数 - 用于节点图任务生成"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

from app.models import TodoItem
from app.models.todo_node_type_helper import DynamicPortPlan, NodeTypeHelper
from app.models.todo_structure_helpers import ensure_child_reference


@dataclass
class DynamicPortTodoPlan:
    todo: TodoItem
    plan: DynamicPortPlan


def build_create_node_todo(
    *,
    todo_id: str,
    parent_id: str,
    graph_id: str,
    node_id: str,
    node_title: str,
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    task_type: str,
    title_override: str = "",
    description_override: str = "",
) -> TodoItem:
    """构建“创建节点”步骤，供事件起点及批量创建复用。"""
    title = title_override or f"创建节点：{node_title}"
    description = description_override or "在图中创建该节点"
    return TodoItem(
        todo_id=todo_id,
        title=title,
        description=description,
        level=5,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_create_node",
            "graph_id": graph_id,
            "node_id": node_id,
            "node_title": node_title,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )


def build_params_todo(
    todo_id: str,
    parent_id: str,
    graph_id: str,
    node_id: str,
    node_title: str,
    params: List[Dict[str, Any]],
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    task_type: str,
) -> TodoItem:
    """构建"配置参数"步骤的 TodoItem。
    
    Args:
        todo_id: 任务唯一标识
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        node_id: 目标节点ID
        node_title: 节点标题
        params: 参数列表 [{"param_name": ..., "param_value": ...}]
        template_ctx_id: 模板上下文ID（用于跳转）
        instance_ctx_id: 实例上下文ID（用于跳转）
        suppress_auto_jump: 是否抑制自动跳转
        
    Returns:
        配置参数步骤的 TodoItem
    """
    return TodoItem(
        todo_id=todo_id,
        title=f"配置参数：【{node_title}】",
        description="设置节点的输入参数",
        level=6,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_config_node_merged",
            "graph_id": graph_id,
            "node_id": node_id,
            "node_title": node_title,
            "params": params,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )


def build_set_port_types_todo(
    todo_id: str,
    parent_id: str,
    graph_id: str,
    node_id: str,
    node_title: str,
    params: List[Dict[str, Any]],
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    task_type: str,
) -> TodoItem:
    """构建"设置端口类型（合并）"步骤的 TodoItem。

    说明：
    - 当 params 为空时，该步骤用于设置该节点输出侧的端口类型（基于连线推断）；
    - 当 params 非空时，该步骤用于为输入端口选择合适的数据类型（基于声明/值类型推断），不输入具体值。
    
    Args:
        todo_id: 任务唯一标识
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        node_id: 目标节点ID
        node_title: 节点标题
        params: 端口参数列表（可为空）
        template_ctx_id: 模板上下文ID
        instance_ctx_id: 实例上下文ID
        suppress_auto_jump: 是否抑制自动跳转
        
    Returns:
        设置端口类型步骤的 TodoItem
    """
    return TodoItem(
        todo_id=todo_id,
        title=f"设置类型：【{node_title}】",
        description="为节点的输入/输出端口选择数据类型",
        level=6,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_set_port_types_merged",
            "graph_id": graph_id,
            "node_id": node_id,
            "node_title": node_title,
            "params": params,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )


def build_connect_todo_merged(
    todo_id: str,
    parent_id: str,
    graph_id: str,
    src_id: str,
    dst_id: str,
    src_title: str,
    dst_title: str,
    edges_info: List[Dict[str, Any]],
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    task_type: str,
) -> TodoItem:
    """构建"连接（合并多条边）"步骤的 TodoItem。
    
    Args:
        todo_id: 任务唯一标识
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        src_id: 源节点ID
        dst_id: 目标节点ID
        src_title: 源节点标题
        dst_title: 目标节点标题
        edges_info: 连线信息列表 [{"edge_id": ..., "src_port": ..., "dst_port": ...}]
        template_ctx_id: 模板上下文ID
        instance_ctx_id: 实例上下文ID
        suppress_auto_jump: 是否抑制自动跳转
        
    Returns:
        合并连接步骤的 TodoItem
    """
    return TodoItem(
        todo_id=todo_id,
        title=f"连接：{src_title} → {dst_title}（{len(edges_info)}条）",
        description="建立节点间的连线",
        level=5,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_connect_merged",
            "graph_id": graph_id,
            "node1_id": src_id,
            "node2_id": dst_id,
            "node1_title": src_title,
            "node2_title": dst_title,
            "edges": edges_info,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )


def build_connect_todo_single(
    todo_id: str,
    parent_id: str,
    graph_id: str,
    edge,
    src_node_title: str,
    dst_node_title: str,
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    task_type: str,
) -> TodoItem:
    """构建"连接（单条边）"步骤的 TodoItem。
    
    Args:
        todo_id: 任务唯一标识
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        edge: 边对象（需包含 src_node, dst_node, id, src_port, dst_port）
        src_node_title: 源节点标题
        dst_node_title: 目标节点标题
        template_ctx_id: 模板上下文ID
        instance_ctx_id: 实例上下文ID
        suppress_auto_jump: 是否抑制自动跳转
        
    Returns:
        单条连接步骤的 TodoItem
    """
    return TodoItem(
        todo_id=todo_id,
        title=f"连接：{src_node_title} → {dst_node_title}",
        description="建立节点间的连线",
        level=5,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_connect",
            "graph_id": graph_id,
            "src_node": edge.src_node,
            "dst_node": edge.dst_node,
            "edge_id": edge.id,
            "src_port": edge.src_port,
            "dst_port": edge.dst_port,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )


def maybe_build_dynamic_ports_todo(
    parent_id: str,
    graph_id: str,
    node_obj,
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    todo_map: Dict[str, TodoItem],
    type_helper: NodeTypeHelper,
    task_type: str,
) -> Optional[DynamicPortTodoPlan]:
    """针对带动态端口的节点生成“新增端口”步骤。

    Args:
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        node_obj: 节点对象
        template_ctx_id: 模板上下文ID
        instance_ctx_id: 实例上下文ID
        suppress_auto_jump: 是否禁止自动跳转
        todo_map: 已生成任务的映射字典，用于去重
        type_helper: 节点类型辅助器（提供动态端口判定）
    """
    plan = type_helper.plan_dynamic_ports(node_obj)
    if plan is None or plan.add_count <= 0:
        return None

    todo_id = f"{parent_id}:dynports:{node_obj.id}"
    if todo_id in todo_map:
        return None

    behavior_to_detail_type: Dict[str, str] = {
        "variadic_inputs": "graph_add_variadic_inputs",
        "key_value_pairs": "graph_add_dict_pairs",
        "flow_branch_outputs": "graph_add_branch_outputs",
    }
    step_type = behavior_to_detail_type.get(plan.mode, "")
    if not step_type:
        return None

    todo = TodoItem(
        todo_id=todo_id,
        title=f"新增动态端口：{node_obj.title} × {plan.add_count}",
        description="为可变参数/分支节点添加所需端口",
        level=5,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": step_type,
            "graph_id": graph_id,
            "node_id": node_obj.id,
            "node_title": node_obj.title,
            "add_count": plan.add_count,
            "port_tokens": list(plan.port_tokens),
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )
    return DynamicPortTodoPlan(todo=todo, plan=plan)


def build_config_branch_outputs_todo(
    parent_id: str,
    graph_id: str,
    node_obj,
    template_ctx_id: str,
    instance_ctx_id: str,
    suppress_auto_jump: bool,
    todo_map: Dict[str, TodoItem],
    task_type: str,
) -> Optional[TodoItem]:
    """为多分支节点生成"配置分支输出值"的执行步骤。

    规则：
    - 遍历该节点的所有输出端口，排除"默认"；
    - 完全尊重端口名称作为分支匹配值，逐一输入。
    
    Args:
        parent_id: 父任务ID
        graph_id: 所属节点图ID
        node_obj: 节点对象
        template_ctx_id: 模板上下文ID
        instance_ctx_id: 实例上下文ID
        suppress_auto_jump: 是否抑制自动跳转
        todo_map: 已生成任务的映射表（用于去重）
        
    Returns:
        配置分支输出步骤的 TodoItem，如不需要则返回 None
    """
    title = node_obj.title or ""
    if title != "多分支":
        return None
    branch_names = [p.name for p in getattr(node_obj, 'outputs', []) if isinstance(p.name, str) and p.name != "默认"]
    if not branch_names:
        return None
    branches = [ {"port_name": n, "value": n} for n in branch_names ]

    todo_id = f"{parent_id}:cfg_branches:{node_obj.id}"
    if todo_id in todo_map:
        return None

    return TodoItem(
        todo_id=todo_id,
        title=f"配置分支输出：{node_obj.title}（{len(branches)}项）",
        description="为每个有告警的分支流程口输入匹配值",
        level=5,
        parent_id=parent_id,
        children=[],
        task_type=task_type,
        target_id=graph_id,
        detail_info={
            "type": "graph_config_branch_outputs",
            "graph_id": graph_id,
            "node_id": node_obj.id,
            "node_title": node_obj.title,
            "branches": branches,
            "template_id": template_ctx_id if template_ctx_id else None,
            "instance_id": instance_ctx_id if instance_ctx_id else None,
            "no_auto_jump": suppress_auto_jump,
        },
    )

