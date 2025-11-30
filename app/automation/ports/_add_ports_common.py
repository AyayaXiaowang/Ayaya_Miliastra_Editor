from __future__ import annotations

# -*- coding: utf-8 -*-
"""
端口新增类步骤的通用小工具。

当前用途：
- 为字典端口与变参端口的“新增端口”步骤提供统一的节点解析与基础校验；
- 保持日志前缀可自定义，避免在各自模块中重复编写 node_id 校验与错误信息。
"""

from typing import Dict, Any, Optional, Tuple

from engine.graph.models.graph_model import GraphModel, NodeModel


def resolve_node_and_initial_add_count(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    *,
    feature_label: str,
    log_callback=None,
) -> Tuple[Optional[NodeModel], int]:
    """解析待操作节点并返回基础新增数量。

    Args:
        executor: 执行器实例，用于日志输出。
        todo_item: 当前待办项，要求至少包含 node_id 与可选的 add_count。
        graph_model: 图模型，用于校验节点是否存在。
        feature_label: 日志前缀，如“字典端口添加”/“变参端口添加”。
        log_callback: 日志回调。

    Returns:
        (node_model, add_count)：
        - node_model 为 None 表示节点不存在或参数缺失，调用方应视为失败；
        - add_count 为初始计划新增数量，未做任何业务层面的修正。
    """
    node_id = todo_item.get("node_id")
    add_count_raw = todo_item.get("add_count")
    add_count = int(add_count_raw or 0)

    if not node_id or node_id not in graph_model.nodes:
        executor._log(f"✗ {feature_label}缺少节点或节点不存在", log_callback)
        return None, int(add_count)

    node_model = graph_model.nodes[node_id]
    return node_model, int(add_count)


__all__ = ["resolve_node_and_initial_add_count"]


