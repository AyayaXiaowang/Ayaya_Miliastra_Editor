# -*- coding: utf-8 -*-
"""
port_type_setter: 端口类型设置功能（重构版本）
将庞大的execute_set_port_types_merged拆分为清晰的步骤函数。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, Tuple
from PIL import Image

from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from engine.graph.models.graph_model import GraphModel
from app.automation.input.common import compute_position_thresholds

from app.automation.ports.port_type_inference import build_edge_lookup
from app.automation.ports.port_type_steps import (
    process_input_ports_type_setting,
    process_output_ports_type_setting,
)
from app.automation.core.visualization_helpers import emit_node_and_port_overlays


def _emit_expected_position_overlay(
    executor: EditorExecutorWithViewport,
    node,
    visual_callback,
    log_callback,
    label: str,
) -> None:
    if visual_callback is None:
        return
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        return

    scale = float(executor.scale_ratio or 1.0)
    threshold_x, threshold_y = compute_position_thresholds(scale)
    roi_half_w = int(threshold_x * 2.0)
    roi_half_h = int(threshold_y * 2.0)

    program_x, program_y = float(node.pos[0]), float(node.pos[1])
    editor_x, editor_y = executor.convert_program_to_editor_coords(program_x, program_y)
    roi_left = int(editor_x - roi_half_w)
    roi_top = int(editor_y - roi_half_h)
    roi_width = int(roi_half_w * 2)
    roi_height = int(roi_half_h * 2)

    def _builder(_: Image.Image) -> dict:
        return {
            "rects": [
                {
                    "bbox": (roi_left, roi_top, roi_width, roi_height),
                    "color": (255, 120, 120),
                    "label": f"{label} · 期望区域",
                }
            ],
            "circles": [
                {
                    "center": (int(editor_x), int(editor_y)),
                    "radius": 6,
                    "color": (255, 200, 0),
                    "label": "期望中心",
                }
            ],
        }

    executor.capture_and_emit(
        label=label,
        overlays_builder=_builder,
        visual_callback=visual_callback,
    )
    executor._log(
        f"  · 已在监控画面标注期望位置：center=({int(editor_x)},{int(editor_y)}) ROI=({roi_left},{roi_top},{roi_width},{roi_height})",
        log_callback,
    )


def _compute_edges_signature(edges: Dict[str, Any]) -> Tuple[int, int]:
    checksum = 0
    count = 0
    for edge_id, edge in edges.items():
        count += 1
        src_node = getattr(edge, "src_node", "")
        src_port = getattr(edge, "src_port", "")
        dst_node = getattr(edge, "dst_node", "")
        dst_port = getattr(edge, "dst_port", "")
        checksum ^= hash((str(edge_id), str(src_node), str(src_port), str(dst_node), str(dst_port)))
    return count, checksum


def _get_cached_edge_lookup(graph_model: GraphModel):
    edges = getattr(graph_model, "edges", {})
    signature = _compute_edges_signature(edges)
    cached_lookup = getattr(graph_model, "_automation_edge_lookup_cache", None)
    cached_signature = getattr(graph_model, "_automation_edge_lookup_signature", None)
    if cached_lookup is not None and cached_signature == signature:
        return cached_lookup
    lookup = build_edge_lookup(graph_model)
    setattr(graph_model, "_automation_edge_lookup_cache", lookup)
    setattr(graph_model, "_automation_edge_lookup_signature", signature)
    return lookup


def execute_set_port_types_merged(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """为节点的输入/输出端口设置数据类型（重构版）。
    
    功能：
    - 输入侧：根据params推断类型并设置（仅当params非空时）
    - 输出侧：根据连线/本节点输入常量推断类型并设置
    
    Args:
        executor: 执行器实例
        todo_item: 待办项，包含 node_id 和 params 列表
        graph_model: 图模型
        log_callback: 日志回调
        pause_hook: 暂停钩子
        allow_continue: 继续判断钩子
        visual_callback: 可视化回调
    
    Returns:
        成功返回True，失败返回False
    """
    # ========== 1. 初始化与准备 ==========
    node_id = todo_item.get("node_id")
    params_list = todo_item.get("params") or []
    
    if not node_id or node_id not in graph_model.nodes:
        executor._log("✗ 端口类型设置缺少节点或节点不存在", log_callback)
        return False
    
    node = graph_model.nodes[node_id]
    edge_lookup = _get_cached_edge_lookup(graph_model)
    
    # 确保节点在可见区域
    executor.ensure_program_point_visible(
        node.pos[0],
        node.pos[1],
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
    
    snapshot = NodePortsSnapshotCache(executor, node, log_callback)
    if not snapshot.ensure(reason="端口类型设置", require_bbox=True):
        _emit_expected_position_overlay(
            executor,
            node,
            visual_callback,
            log_callback,
            label=f"定位失败：{node.title}",
        )
        return False
    node_bbox = snapshot.node_bbox
    screenshot = snapshot.screenshot
    ports_for_overlay = snapshot.ports
    
    # ========== 2. 可视化：节点图区域、所有节点、当前节点端口 ==========
    emit_node_and_port_overlays(
        executor,
        screenshot,
        node_bbox,
        visual_callback,
        ports=ports_for_overlay,
        port_label_mode="raw",
    )
    
    # ========== 3. 获取节点定义 ==========
    node_def = executor._get_node_def_for_model(node)
    
    # 判定是否为运算节点（同侧仅需设置一次）
    is_operation_node = False
    if isinstance(getattr(node, 'category', None), str):
        is_operation_node = ('运算' in str(node.category))
    
    typed_side_once: Dict[str, bool] = {'left': False, 'right': False}
    
    # ========== 4. 处理输入侧端口类型设置 ==========
    success_input = process_input_ports_type_setting(
        executor,
        node,
        node_def,
        node_bbox,
        snapshot,
        params_list,
        graph_model,
        edge_lookup,
        is_operation_node,
        typed_side_once,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    if not success_input:
        return False
    
    # ========== 5. 处理输出侧端口类型设置 ==========
    success_output = process_output_ports_type_setting(
        executor,
        node,
        node_def,
        node_bbox,
        snapshot,
        graph_model,
        edge_lookup,
        is_operation_node,
        typed_side_once,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    if not success_output:
        return False
    
    return True

