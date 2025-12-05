from __future__ import annotations

# -*- coding: utf-8 -*-
"""
端口新增与相关 UI 步骤的通用小工具。

当前用途：
- 为字典端口与变参端口的“新增端口”步骤提供统一的节点解析与基础校验；
- 为端口相关自动化步骤提供统一的节点可见性保证工具，避免在各模块中重复硬编码
  `ensure_program_point_visible` 的视口参数。
"""

from typing import Dict, Any, Optional, Tuple, Callable

from PIL import Image

from app.automation.core.executor_protocol import EditorExecutorWithViewport
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
        executor.log(f"✗ {feature_label}缺少节点或节点不存在", log_callback)
        return None, int(add_count)

    node_model = graph_model.nodes[node_id]
    return node_model, int(add_count)


def ensure_node_visible_for_automation(
    executor: EditorExecutorWithViewport,
    node_model: NodeModel,
    graph_model: GraphModel,
    *,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> None:
    """使用统一参数确保节点在画布可见区域内，供端口相关自动化步骤复用。"""
    executor.ensure_program_point_visible(
        node_model.pos[0],
        node_model.pos[1],
        margin_ratio=0.10,
        max_steps=8,
        pan_step_pixels=420,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        graph_model=graph_model,
        force_pan_if_inside_margin=False,
    )


def execute_add_ports_generic(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    *,
    feature_label: str,
    prefer_multi: bool,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    list_ports_for_bbox_func: Optional[
        Callable[[Image.Image, Tuple[int, int, int, int]], list[Any]]
    ] = None,
    compute_final_add_count: Optional[
        Callable[
            [
                EditorExecutorWithViewport,
                Dict[str, Any],
                GraphModel,
                NodeModel,
                int,
                Optional[
                    Callable[[Image.Image, Tuple[int, int, int, int]], list[Any]]
                ],
                Optional[Callable[[str], None]],
            ],
            Tuple[bool, int],
        ]
    ] = None,
) -> bool:
    """统一的“新增端口”执行骨架。

    责任边界：
    - 解析节点与基础 add_count；
    - 可选地委托策略函数计算最终 add_count；
    - 调用图标点击流程完成新增。

    具体“如何根据当前端口数量与目标数量计算最终 add_count”由 compute_final_add_count 决定，
    便于为变参端口/字典端口等场景复用同一套骨架。
    """
    node_model, add_count_initial = resolve_node_and_initial_add_count(
        executor,
        todo_item,
        graph_model,
        feature_label=feature_label,
        log_callback=log_callback,
    )
    if node_model is None:
        return False

    add_count = int(add_count_initial)

    if compute_final_add_count is not None:
        ok, final_add_count = compute_final_add_count(
            executor,
            todo_item,
            graph_model,
            node_model,
            add_count,
            list_ports_for_bbox_func,
            log_callback,
        )
        if not ok:
            return False
        add_count = int(final_add_count)

    if add_count <= 0:
        return True

    # 延迟导入以避免在模块加载阶段引入不必要的依赖与潜在循环引用。
    from app.automation.config.branch_config import execute_add_with_icon_clicks as _execute_add_with_icon_clicks

    return _execute_add_with_icon_clicks(
        executor,
        node_model,
        add_count,
        prefer_multi=prefer_multi,
        graph_model=graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )


__all__ = [
    "resolve_node_and_initial_add_count",
    "ensure_node_visible_for_automation",
    "execute_add_ports_generic",
]


