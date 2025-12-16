# -*- coding: utf-8 -*-
"""
port_type_setter: 端口类型设置功能（重构版本）
将庞大的execute_set_port_types_merged拆分为清晰的步骤函数。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, Tuple
from dataclasses import dataclass
from PIL import Image

from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.editor.node_snapshot import NodePortsSnapshotCache
from engine.graph.models.graph_model import GraphModel, NodeModel
from app.automation.input.common import compute_position_thresholds

from app.automation.ports.port_type_inference import build_edge_lookup
from app.automation.ports._add_ports_common import ensure_node_visible_for_automation
from app.automation.ports.port_type_steps import (
    process_input_ports_type_setting,
    process_output_ports_type_setting,
)
from app.automation.editor.visualization_helpers import emit_node_and_port_overlays


@dataclass
class PortTypeExecutionContext:
    """端口类型设置所需的节点上下文。

    将节点模型、节点定义、截图快照与图上下文打包，便于在输入/输出侧步骤之间复用，
    同时为单元测试提供清晰的上下文边界。
    """

    node: NodeModel
    node_def: Any
    node_bbox: Tuple[int, int, int, int]
    snapshot: NodePortsSnapshotCache
    graph_model: GraphModel
    edge_lookup: Any
    is_operation_node: bool


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
        use_strict_window_capture=True,
    )
    executor.log(
        f"  · 已在监控画面标注期望位置：center=({int(editor_x)},{int(editor_y)}) ROI=({roi_left},{roi_top},{roi_width},{roi_height})",
        log_callback,
    )


def _is_operation_node(node: NodeModel) -> bool:
    """根据节点类别判定是否为“运算节点”。

    运算节点的类型设置策略与普通节点略有不同：同侧端口只需设置一次，
    因此需要在编排阶段提前打上标记。
    """
    category_text = getattr(node, "category", None)
    if not isinstance(category_text, str):
        return False
    return "运算" in category_text


def prepare_node_context(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node_id: Any,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> Optional[PortTypeExecutionContext]:
    """准备端口类型设置所需的节点上下文。

    负责：
    - 校验 node_id 并获取节点模型；
    - 构建入/出边索引；
    - 确保节点在视口内可见；
    - 通过 `NodePortsSnapshotCache` 构建节点截图与端口快照；
    - 获取节点定义与“运算节点”标记。

    失败时写入日志并返回 None，由调用方决定是否终止本次步骤。
    """
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 端口类型设置缺少节点或节点不存在", log_callback)
        return None
    
    node = graph_model.nodes[node_id]
    edge_lookup = build_edge_lookup(graph_model)
    
    # 确保节点在可见区域
    ensure_node_visible_for_automation(
        executor,
        node,
        graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
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
        return None

    node_bbox = snapshot.node_bbox

    # 获取节点定义与运算节点标记
    node_def = executor.get_node_def_for_model(node)
    is_operation_node = _is_operation_node(node)

    return PortTypeExecutionContext(
        node=node,
        node_def=node_def,
        node_bbox=node_bbox,
        snapshot=snapshot,
        graph_model=graph_model,
        edge_lookup=edge_lookup,
        is_operation_node=is_operation_node,
    )


def emit_overlays(
    executor: EditorExecutorWithViewport,
    context: PortTypeExecutionContext,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> None:
    """在监控画面上标注当前节点与端口识别结果。

    该步骤只负责可视化，不影响后续类型推断与 UI 操作。
    """
    if visual_callback is None:
        return

    screenshot = context.snapshot.screenshot
    if screenshot is None:
        return

    emit_node_and_port_overlays(
        executor,
        screenshot,
        context.node_bbox,
        visual_callback,
        ports=context.snapshot.ports,
        port_label_mode="raw",
    )


def set_input_types(
    executor: EditorExecutorWithViewport,
    context: PortTypeExecutionContext,
    params_list: list,
    typed_side_once: Dict[str, bool],
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """处理输入侧端口类型设置（左侧数据端口）。"""
    success_input = process_input_ports_type_setting(
        executor,
        context.node,
        context.node_def,
        context.node_bbox,
        context.snapshot,
        params_list,
        context.graph_model,
        context.edge_lookup,
        context.is_operation_node,
        typed_side_once,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    return bool(success_input)


def set_output_types(
    executor: EditorExecutorWithViewport,
    context: PortTypeExecutionContext,
    typed_side_once: Dict[str, bool],
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """处理输出侧端口类型设置（右侧数据端口）。"""
    success_output = process_output_ports_type_setting(
        executor,
        context.node,
        context.node_def,
        context.node_bbox,
        context.snapshot,
        context.graph_model,
        context.edge_lookup,
        context.is_operation_node,
        typed_side_once,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    
    return bool(success_output)


def execute_set_port_types_merged(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """为节点的输入/输出端口设置数据类型（编排入口）。

    执行流程拆分为几个清晰步骤：
    1）`prepare_node_context`：节点可见性、快照构建与节点定义获取；
    2）`emit_overlays`：在监控画面上标注当前节点与端口；
    3）`set_input_types`：根据参数与连线推断输入端口类型并在 UI 中设置；
    4）`set_output_types`：根据本节点输入与出边推断输出端口类型并在 UI 中设置。
    """
    node_id = todo_item.get("node_id")
    params_list = todo_item.get("params") or []

    context = prepare_node_context(
        executor=executor,
        graph_model=graph_model,
        node_id=node_id,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )
    if context is None:
        return False

    emit_overlays(executor, context, visual_callback=visual_callback)

    typed_side_once: Dict[str, bool] = {"left": False, "right": False}

    if not set_input_types(
        executor=executor,
        context=context,
        params_list=params_list,
        typed_side_once=typed_side_once,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    ):
        return False

    if not set_output_types(
        executor=executor,
        context=context,
        typed_side_once=typed_side_once,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    ):
        return False

    return True

