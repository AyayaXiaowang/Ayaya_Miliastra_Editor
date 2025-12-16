# -*- coding: utf-8 -*-
"""
editor_recognition.position_sync

识别后坐标同步：根据当前识别结果估算可见节点的程序坐标偏移，并缓存到 executor 上。
"""

from __future__ import annotations

from typing import Dict, Tuple

from app.automation.input.common import compute_position_thresholds
from engine.graph.models.graph_model import GraphModel

from .visible_nodes import recognize_visible_nodes


def synchronize_visible_nodes_positions(
    executor,
    graph_model: GraphModel,
    threshold_px: float = 40.0,
    log_callback=None,
) -> int:
    """
    根据当前识别结果估算可见节点的程序坐标偏移，避免视口偏移后仍使用过期位置。

    Args:
        executor: 执行器实例
        graph_model: 图模型
        threshold_px: 仅当左上角偏移超过该阈值（像素）才更新

    Returns:
        int: 实际被更新的节点数量
    """
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        return 0

    scale = float(executor.scale_ratio)
    if abs(scale) <= 1e-6:
        return 0

    origin_x = float(executor.origin_node_pos[0])
    origin_y = float(executor.origin_node_pos[1])
    visible_map = recognize_visible_nodes(executor, graph_model)
    if not visible_map:
        if hasattr(executor, "__dict__"):
            setattr(executor, "_recent_node_position_deltas", {})
            setattr(executor, "_position_delta_token", getattr(executor, "_view_state_token", 0))
        return 0

    # 此处不再根据步骤索引对同名节点的 bbox 进行二次重分配：
    # - `recognize_visible_nodes` 已经在几何与标题层面完成了一次全局一对一匹配；
    # - 创建节点阶段的“前置参考节点”过滤由 `editor_nodes._is_reference_node_allowed` 负责，
    #   通过 `_node_first_create_step_index` 与 `_current_step_index` 排除“未来步骤节点”；
    # 在坐标同步阶段直接信任识别得到的 node_id → bbox 绑定，避免之后的邻居偏移/最近偏移
    # 使用与“定位镜头”等工具观察到的不一致的节点 ID。

    position_deltas: Dict[str, Tuple[float, float]] = {}
    if hasattr(executor, "__dict__"):
        setattr(executor, "_recent_node_position_deltas", position_deltas)
    else:
        position_deltas = {}

    auto_threshold_x, _ = compute_position_thresholds(scale)
    adjust_threshold = float(max(threshold_px, auto_threshold_x * 0.5))

    updated = 0
    for node_id, info in visible_map.items():
        if not info.get("visible"):
            continue
        node = graph_model.nodes.get(node_id)
        if node is None:
            continue
        bbox = info.get("bbox")
        if not bbox:
            continue
        left_v, top_v, _, _ = bbox
        expected_x, expected_y = executor.convert_program_to_editor_coords(
            float(node.pos[0]),
            float(node.pos[1]),
        )
        dx = abs(float(left_v) - float(expected_x))
        dy = abs(float(top_v) - float(expected_y))
        if dx <= adjust_threshold and dy <= adjust_threshold:
            continue
        old_prog_x, old_prog_y = float(node.pos[0]), float(node.pos[1])
        new_prog_x = (float(left_v) - origin_x) / scale
        new_prog_y = (float(top_v) - origin_y) / scale
        delta_x = new_prog_x - old_prog_x
        delta_y = new_prog_y - old_prog_y
        updated += 1
        executor.log(
            f"[识别同步] '{node.title}' 偏移≈({dx:.1f},{dy:.1f}) → 记录程序坐标偏移 Δ≈({delta_x:.1f},{delta_y:.1f})",
            log_callback,
        )
        if position_deltas is not None:
            position_deltas[node_id] = (delta_x, delta_y)

    if hasattr(executor, "__dict__"):
        setattr(executor, "_position_delta_token", getattr(executor, "_view_state_token", 0))

    return updated


