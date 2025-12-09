# -*- coding: utf-8 -*-
"""
editor_connect: 将 EditorExecutor 中的连线与端口/变参相关的大块逻辑拆分为独立模块，
通过函数形式接收 executor 实例，避免循环依赖并提升可维护性。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Callable
import re
import time
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.core import executor_utils as _exec_utils
from app.automation.core import editor_nodes
from app.automation.core.ui_constants import (
    NODE_VIEW_WIDTH_PX,
    NODE_VIEW_HEIGHT_PX,
    VIEW_SAFE_MARGIN_RATIO_DEFAULT,
)
from app.automation.core.port_matching import ConnectionFrameState, PortMatchingService
from app.automation.ports._ports import (
    normalize_kind_text,
    is_data_input_port,
    is_flow_output_port,
)
from app.automation.ports.port_type_inference import safe_get_port_type_from_node_def
from app.automation.ports.port_picker import pick_settings_center_by_recognition
from app.automation.config.config_params import execute_config_node_merged
from app.automation.config.branch_config import (
    click_add_icon_within_node,
    execute_add_branch_outputs,
    execute_config_branch_outputs,
)
from app.automation.ports.port_type_setter import execute_set_port_types_merged
from app.automation.ports.dict_ports import execute_add_dict_pairs
from app.automation.ports import variadic_ports
from engine.utils.graph.graph_utils import is_flow_port_name
from app.automation.vision import list_nodes, list_ports as list_ports_for_bbox, invalidate_cache
from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import GraphModel, NodeModel
from engine.nodes.port_index_mapper import get_and_clear_last_mappings as _get_port_mapping_logs
from app.automation.vision import get_and_clear_title_mapping_logs as _get_title_mapping_logs
from app.automation.core.connection_drag import perform_connection_drag
from app.automation.core.editor_mapping import MIN_SCALE_RATIO, FIXED_SCALE_RATIO

MAX_PAIR_ALIGN_ATTEMPTS = 2


def execute_add_variadic_inputs(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """为节点添加变参输入端口。

    这里作为应用层入口：
    - 由 core 层负责注入端口识别函数 list_ports_for_bbox；
    - 具体的几何与变参逻辑由 app.automation.ports.variadic_ports 实现。
    """
    return variadic_ports.execute_add_variadic_inputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
        list_ports_for_bbox_func=list_ports_for_bbox,
    )


def _infer_expected_kinds_from_names(
    src_port_name: str | None,
    dst_port_name: str | None,
) -> Tuple[Optional[str], Optional[str]]:
    """仅基于端口名推断期望端口类型（flow/data），并在一端未知时向另一端传播。

    说明：
    - 这里只依赖端口名的“是否为流程端口”判断，用于：
      * 在端口筛选阶段给出“偏好类型”；
      * 在类型声明参与前，做一次保守的类型匹配检查。
    """
    src_expected_kind: Optional[str] = None
    dst_expected_kind: Optional[str] = None
    if isinstance(src_port_name, str) and src_port_name:
        src_expected_kind = "flow" if is_flow_port_name(src_port_name) else None
    if isinstance(dst_port_name, str) and dst_port_name:
        dst_expected_kind = "flow" if is_flow_port_name(dst_port_name) else None
    if src_expected_kind is None and dst_expected_kind in ("flow", "data"):
        src_expected_kind = dst_expected_kind
    if dst_expected_kind is None and src_expected_kind in ("flow", "data"):
        dst_expected_kind = src_expected_kind
    return src_expected_kind, dst_expected_kind


def _infer_expected_kinds_with_type_decls(
    src_port_name: str | None,
    dst_port_name: str | None,
    src_type_decl: str,
    dst_type_decl: str,
) -> Tuple[Optional[str], Optional[str]]:
    """结合端口名与定义中的类型声明推断期望端口类型。

    规则：
    - 先按端口名推断（与 `_infer_expected_kinds_from_names` 一致），得到首选类型；
    - 若仍未知，则尝试从定义声明中解析为 flow/data；
    - 最后若仅一端已知，则按已知一端向另一端传播类型。
    """
    src_expected_kind, dst_expected_kind = _infer_expected_kinds_from_names(
        src_port_name,
        dst_port_name,
    )
    if src_expected_kind is None:
        kind_src_decl = normalize_kind_text(src_type_decl or "")
        if kind_src_decl in ("flow", "data"):
            src_expected_kind = kind_src_decl
    if dst_expected_kind is None:
        kind_dst_decl = normalize_kind_text(dst_type_decl or "")
        if kind_dst_decl in ("flow", "data"):
            dst_expected_kind = kind_dst_decl
    if src_expected_kind is None and dst_expected_kind in ("flow", "data"):
        src_expected_kind = dst_expected_kind
    if dst_expected_kind is None and src_expected_kind in ("flow", "data"):
        dst_expected_kind = src_expected_kind
    return src_expected_kind, dst_expected_kind


def _reset_connection_frame_context(reuse_context: Optional[Dict[str, Any]]) -> None:
    if reuse_context is None:
        return
    for key in ("screenshot", "screenshot_token", "detected_nodes", "detected_nodes_token"):
        if key in reuse_context:
            reuse_context.pop(key, None)


def _ensure_connect_pair_visible(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    src_node: NodeModel,
    dst_node: NodeModel,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    ) -> bool:
    too_far, reason = executor.will_connect_too_far(
        graph_model,
        src_node.id,
        dst_node.id,
        margin_ratio=VIEW_SAFE_MARGIN_RATIO_DEFAULT,
    )
    if reason:
        executor.log(f"· 同屏评估：{reason}", log_callback)
    if too_far:
        executor.log("✗ 连线端点无法同屏，放弃当前连线", log_callback)
        return False

    mid_x = (float(src_node.pos[0]) + float(dst_node.pos[0])) * 0.5
    mid_y = (float(src_node.pos[1]) + float(dst_node.pos[1])) * 0.5
    executor.log(
        f"· 连线视口调度：对齐两端中点=({mid_x:.1f},{mid_y:.1f})，尝试一次性展示源/目标节点",
        log_callback,
    )
    executor.ensure_program_point_visible(
        mid_x,
        mid_y,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        graph_model=graph_model,
        force_pan_if_inside_margin=False,
    )
    invalidate_cache()
    return True


def execute_connect(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    reuse_context: Optional[Dict[str, Any]] = None,
) -> bool:
    src_node_id = todo_item.get("src_node") or todo_item.get("prev_node_id")
    dst_node_id = todo_item.get("dst_node") or todo_item.get("node_id")
    src_port_name = todo_item.get("src_port")
    dst_port_name = todo_item.get("dst_port")
    if not src_node_id or not dst_node_id:
        executor.log("✗ 连接步骤缺少节点ID", log_callback)
        return False
    return _connect_nodes(
        executor=executor,
        graph_model=graph_model,
        src_node_id=str(src_node_id),
        dst_node_id=str(dst_node_id),
        src_port_name=str(src_port_name or ""),
        dst_port_name=str(dst_port_name or ""),
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        reuse_context=reuse_context,
    )

def _connect_nodes(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    src_node_id: str,
    dst_node_id: str,
    src_port_name: str | None,
    dst_port_name: str | None,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    reuse_context: Optional[Dict[str, Any]] = None,
) -> bool:
    if src_node_id not in graph_model.nodes or dst_node_id not in graph_model.nodes:
        executor.log("✗ 图模型中未找到源/目标节点", log_callback)
        return False
    src_node = graph_model.nodes[src_node_id]
    dst_node = graph_model.nodes[dst_node_id]
    if pause_hook is not None:
        pause_hook()
    if allow_continue is not None and not allow_continue():
        executor.log("用户终止/暂停，放弃连线", log_callback)
        return False
    graph_label = (
        str(getattr(graph_model, "graph_id", "") or getattr(graph_model, "id", "") or getattr(graph_model, "name", ""))
    ).strip()
    trace_context = {
        "trace_id": f"{int(time.time() * 1000)}-{src_node_id}->{dst_node_id}",
        "src_node_id": src_node_id,
        "dst_node_id": dst_node_id,
    }
    if src_port_name:
        trace_context["src_port_name"] = src_port_name
    if dst_port_name:
        trace_context["dst_port_name"] = dst_port_name
    if graph_label:
        trace_context["graph"] = graph_label

    matching_service = PortMatchingService(
        executor,
        log_callback,
        visual_callback,
        trace_context=trace_context,
    )
    matching_service._log_trace(
        "追踪",
        "开始连接追踪",
        graph=graph_label or "unknown",
        src_node=src_node.title,
        dst_node=dst_node.title,
    )
    align_attempts = 0
    frame_state: Optional[ConnectionFrameState] = None
    src_snapshot = None
    dst_snapshot = None
    src_debug: Dict[str, Any] = {}
    dst_debug: Dict[str, Any] = {}
    bbox_result = None

    def _try_pair_alignment(reason: str) -> bool:
        nonlocal align_attempts
        if align_attempts >= MAX_PAIR_ALIGN_ATTEMPTS:
            executor.log(f"{reason}｜已达到视口调度上限", log_callback)
            executor.log("✗ 多次视口调度仍未能同时定位两端，放弃本次连线", log_callback)
            return False
        attempt_no = align_attempts + 1
        executor.log(f"{reason}｜尝试第{attempt_no}次视口调度以求同屏", log_callback)
        align_attempts += 1
        ok = _ensure_connect_pair_visible(
            executor,
            graph_model,
            src_node,
            dst_node,
            log_callback,
            pause_hook,
            allow_continue,
            visual_callback,
        )
        if ok:
            _reset_connection_frame_context(reuse_context)
        return ok

    while True:
        frame_state = ConnectionFrameState.create(executor, reuse_context, visual_callback)
        if frame_state is None:
            executor.log("✗ 截图失败", log_callback)
            return False
        src_debug = {}
        dst_debug = {}
        src_snapshot = frame_state.get_snapshot(src_node_id, src_node, "源", src_debug, log_callback)
        dst_snapshot = frame_state.get_snapshot(dst_node_id, dst_node, "目标", dst_debug, log_callback)
        if src_snapshot is None or dst_snapshot is None:
            missing_labels = []
            if src_snapshot is None:
                missing_labels.append("源")
            if dst_snapshot is None:
                missing_labels.append("目标")
            missing_text = f"⚠ 未能定位节点：{'、'.join(missing_labels)}（疑似屏幕外）"
            if not _try_pair_alignment(missing_text):
                return False
            continue
        bbox_result = matching_service.ensure_valid_bboxes(
            frame_state,
            src_node,
            dst_node,
            src_snapshot,
            dst_snapshot,
        )
        if bbox_result is None:
            if not _try_pair_alignment("⚠ 节点位置与预期偏差过大，重新对齐视口"):
                executor.log("✗ 未能定位源或目标节点（同名但与预期位置偏差过大，或不在搜索范围内）", log_callback)
                return False
            continue
        break

    if src_snapshot is None or dst_snapshot is None:
        executor.log("✗ 连线快照缺失，终止本次连线", log_callback)
        return False
    src_bbox, dst_bbox, src_debug, dst_debug = bbox_result

    src_expected_kind, dst_expected_kind = _infer_expected_kinds_from_names(
        src_port_name,
        dst_port_name,
    )

    selection = matching_service.build_port_selection(
        frame_state.screenshot,
        src_node,
        dst_node,
        src_snapshot,
        dst_snapshot,
        src_port_name,
        dst_port_name,
        src_expected_kind,
        dst_expected_kind,
    )
    if selection is None:
        return False
    src_center = selection.src_center
    dst_center = selection.dst_center
    screenshot = frame_state.screenshot
    src_expected_kind, dst_expected_kind = _infer_expected_kinds_from_names(
        src_port_name,
        dst_port_name,
    )

    if src_expected_kind in ("flow", "data") and dst_expected_kind in ("flow", "data") and src_expected_kind != dst_expected_kind:
        executor.log("✗ 端口类型不匹配（流程端口只能连流程端口，数据端口只能连数据端口）", log_callback)
        return False

    src_def = executor.get_node_def_for_model(src_node)
    dst_def = executor.get_node_def_for_model(dst_node)
    src_type_decl = ""
    if src_def and src_port_name:
        src_type_decl = safe_get_port_type_from_node_def(
            src_def,
            src_port_name,
            is_input=False,
        )
    dst_type_decl = ""
    if dst_def and dst_port_name:
        dst_type_decl = safe_get_port_type_from_node_def(
            dst_def,
            dst_port_name,
            is_input=True,
        )
    executor.log(
        f"[连接] 计划连接: 源[{src_node.title}]({src_node.id}).{str(src_port_name or '?')} -> 目标[{dst_node.title}]({dst_node.id}).{str(dst_port_name or '?')}",
        log_callback,
    )
    src_expected_kind, dst_expected_kind = _infer_expected_kinds_with_type_decls(
        src_port_name,
        dst_port_name,
        src_type_decl,
        dst_type_decl,
    )
    executor.log(
        f"[连接] 端口类型预期: 源={str(src_expected_kind or '?')}, 目标={str(dst_expected_kind or '?')}；定义类型: 源={str(src_type_decl or '?')}, 目标={str(dst_type_decl or '?')}",
        log_callback,
    )

    executor.log(f"✓ 节点匹配成功：源 '{src_node.title}' 位置框{src_bbox}；目标 '{dst_node.title}' 位置框{dst_bbox}", log_callback)
    program_node_width = NODE_VIEW_WIDTH_PX
    program_node_height = NODE_VIEW_HEIGHT_PX
    src_scale_now = ((float(src_bbox[2]) / program_node_width) + (float(src_bbox[3]) / program_node_height)) / 2.0
    dst_scale_now = ((float(dst_bbox[2]) / program_node_width) + (float(dst_bbox[3]) / program_node_height)) / 2.0
    avg_scale_now = (src_scale_now + dst_scale_now) / 2.0
    rel_diff = abs(avg_scale_now - float(executor.scale_ratio or 1.0)) / float(executor.scale_ratio or 1.0)
    executor.log(
        f"  缩放检查：当前估计≈{avg_scale_now:.4f}（源≈{src_scale_now:.4f}，目标≈{dst_scale_now:.4f}），校准比例={float(executor.scale_ratio or 1.0):.4f}，相对偏差≈{rel_diff*100:.1f}%",
        log_callback,
    )
    executor.log(
        f"  端口: 源(输出) '{src_port_name or '?'}' → ({int(src_center[0])},{int(src_center[1])})；目标(输入) '{dst_port_name or '?'}' → ({int(dst_center[0])},{int(dst_center[1])})",
        log_callback,
    )
    if visual_callback is not None:
        rects = []
        all_nodes = list_nodes(screenshot)
        for detected in all_nodes:
            bx, by, bw, bh = detected.bbox
            rects.append({'bbox': (int(bx), int(by), int(bw), int(bh)), 'color': (120,120,120), 'label': f"检测: {str(detected.name_cn or '')}"})
        rects.append({ 'bbox': (int(src_bbox[0]), int(src_bbox[1]), int(src_bbox[2]), int(src_bbox[3])), 'color': (255, 80, 80), 'label': f"源节点: {src_node.title}" })
        rects.append({ 'bbox': (int(dst_bbox[0]), int(dst_bbox[1]), int(dst_bbox[2]), int(dst_bbox[3])), 'color': (80, 200, 120), 'label': f"目标节点: {dst_node.title}" })
        circles = [
            { 'center': (int(src_center[0]), int(src_center[1])), 'radius': 6, 'color': (255, 200, 0), 'label': '输出端口' },
            { 'center': (int(dst_center[0]), int(dst_center[1])), 'radius': 6, 'color': (0, 200, 255), 'label': '输入端口' },
        ]
        visual_callback(screenshot, { 'rects': rects, 'circles': circles })
    src_screen = executor.convert_editor_to_screen_coords(src_center[0], src_center[1])
    dst_screen = executor.convert_editor_to_screen_coords(dst_center[0], dst_center[1])

    def _log(message: str) -> None:
        executor.log(message, log_callback)

    def _drag_callable(x1: int, y1: int, x2: int, y2: int) -> None:
        post_release_sleep = 0.0 if _exec_utils.is_fast_chain_runtime_enabled(executor) else None
        editor_capture.drag_left_button(
            x1,
            y1,
            x2,
            y2,
            post_release_sleep=post_release_sleep,
        )

    description = f"{src_node.title}.{src_port_name or '?'} → {dst_node.title}.{dst_port_name or '?'}"
    return perform_connection_drag(
        drag_callable=_drag_callable,
        src_screen=src_screen,
        dst_screen=dst_screen,
        log_fn=_log,
        description=description,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )


