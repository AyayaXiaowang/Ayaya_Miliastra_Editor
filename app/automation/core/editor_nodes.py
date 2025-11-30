# -*- coding: utf-8 -*-
"""
editor_nodes: 将 EditorExecutor 中“创建节点 / 候选选择 / 类型选择”相关逻辑拆分到独立模块。

通过顶层函数接收 executor 实例，保持原有行为与日志时序不变。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Callable

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.core.candidate_popup import (
    NODE_LIST_CONTEXT_LINGER_SECONDS,
    click_type_search_and_choose,
    select_from_search_popup,
)
from app.automation.input.common import sleep_seconds, compute_position_thresholds
from engine.graph.models.graph_model import GraphModel, NodeModel
POST_INPUT_STABILIZE_SECONDS = 0.8


def _collect_neighbor_node_ids(graph_model: GraphModel, node_id: str) -> set[str]:
    neighbors: set[str] = set()
    if not graph_model or not graph_model.edges:
        return neighbors
    for edge in graph_model.edges.values():
        if edge.src_node == node_id:
            neighbors.add(edge.dst_node)
        elif edge.dst_node == node_id:
            neighbors.add(edge.src_node)
    return neighbors


def _is_reference_node_allowed(executor: EditorExecutorWithViewport, node_id: str) -> bool:
    """判断某个节点是否可以作为“前置参考节点”参与偏移推断。

    规则：
    - 若执行器未注入 `_node_first_create_step_index` 或 `_current_step_index`，则不做限制（兼容旧用法与“仅此一步”场景）。
    - 若存在映射，则仅当：
        * 该节点未出现在创建步骤映射中（例如图中原生存在的锚点节点），或
        * 该节点的首次创建步骤索引 ≤ 当前正在执行的步骤索引，
      时才允许作为参考节点；否则视为“未来步骤中的节点”，在当前创建过程中予以忽略。
    """
    node_first_index_map = getattr(executor, "_node_first_create_step_index", None)
    if not isinstance(node_first_index_map, dict) or not node_first_index_map:
        return True
    current_step_index = getattr(executor, "_current_step_index", None)
    if not isinstance(current_step_index, int):
        return True
    first_index = node_first_index_map.get(node_id)
    if first_index is None:
        return True
    return first_index <= current_step_index


def _infer_program_position_with_neighbor_offsets(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    log_callback,
) -> Optional[Tuple[float, float]]:
    deltas = getattr(executor, "_recent_node_position_deltas", None)
    if not isinstance(deltas, dict) or len(deltas) == 0:
        executor._log("· 创建：无可用前置节点偏移缓存，使用程序坐标", log_callback)
        return None
    delta_token = getattr(executor, "_position_delta_token", -1)
    view_token = getattr(executor, "_view_state_token", 0)
    if delta_token != view_token:
        executor._log("· 创建：偏移缓存与当前视口不同步，使用程序坐标", log_callback)
        return None
    neighbor_ids = _collect_neighbor_node_ids(graph_model, node.id)
    if not neighbor_ids:
        executor._log("· 邻居偏移：当前节点在图中无邻居，尝试使用最近偏移节点作为前置", log_callback)
    else:
        cached_neighbor_ids: list[str] = [
            nid for nid in neighbor_ids if nid in deltas and _is_reference_node_allowed(executor, nid)
        ]
        named_neighbors: list[str] = []
        for nid in cached_neighbor_ids:
            ref_node = graph_model.nodes.get(nid)
            if ref_node is not None:
                named_neighbors.append(ref_node.title)
        executor._log(
            f"· 邻居偏移：邻居共 {len(neighbor_ids)} 个，其中有偏移缓存 {len(cached_neighbor_ids)} 个"
            + (f"，含缓存邻居标题={named_neighbors}" if named_neighbors else ""),
            log_callback,
        )
    offsets: list[Tuple[float, float]] = [deltas[nid] for nid in cached_neighbor_ids]
    if offsets:
        avg_dx = sum(dx for dx, _ in offsets) / len(offsets)
        avg_dy = sum(dy for _, dy in offsets) / len(offsets)
        if abs(avg_dx) >= 1e-2 or abs(avg_dy) >= 1e-2:
            new_pos = (float(node.pos[0]) + avg_dx, float(node.pos[1]) + avg_dy)
            node.pos = new_pos
            executor._log(
                f"· 单步：参考 {len(offsets)} 个邻居位移 Δ≈({avg_dx:.1f},{avg_dy:.1f}) → 调整程序坐标=({new_pos[0]:.1f},{new_pos[1]:.1f})",
                log_callback,
            )
            if hasattr(executor, "__dict__") and cached_neighbor_ids:
                primary_neighbor_id = cached_neighbor_ids[0]
                executor._last_create_position_debug = {
                    "source": "neighbor_offsets",
                    "anchor_node_id": str(primary_neighbor_id),
                    "neighbor_node_ids": [str(neighbor_id) for neighbor_id in cached_neighbor_ids],
                }
            return new_pos
        executor._log(
            f"· 邻居偏移：邻居平均偏移 Δ≈({avg_dx:.1f},{avg_dy:.1f}) 过小，改用最近偏移节点作为前置",
            log_callback,
        )
    fallback_pos = _infer_program_position_with_nearest_delta(
        executor,
        graph_model,
        node,
        deltas,
        log_callback,
    )
    if fallback_pos is None:
        executor._log("· 创建：未找到可用邻居或参考节点偏移，使用程序坐标", log_callback)
    return fallback_pos


def _infer_program_position_with_nearest_delta(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    deltas: Dict[str, Tuple[float, float]],
    log_callback,
) -> Optional[Tuple[float, float]]:
    target_x = float(node.pos[0])
    target_y = float(node.pos[1])
    best_ref: Optional[Tuple[float, float, NodeModel]] = None
    best_dist2: float = float("inf")
    
    # 调试：打印步骤索引上下文
    node_first_index_map = getattr(executor, "_node_first_create_step_index", None)
    current_step_index = getattr(executor, "_current_step_index", None)
    executor._log(
        f"· 前置候选上下文：current_step_index={current_step_index}, "
        f"node_first_create_step_index 条目数={len(node_first_index_map) if isinstance(node_first_index_map, dict) else 'None'}",
        log_callback,
    )
    if isinstance(node_first_index_map, dict) and node_first_index_map:
        # 打印全部映射，便于精确还原每个 node_id 的首次创建步骤索引
        for nid, idx in node_first_index_map.items():
            ref_node = graph_model.nodes.get(nid)
            title = ref_node.title if ref_node else "<未知>"
            executor._log(f"    - 步骤映射: '{title}' (id={nid}) -> step_index={idx}", log_callback)
        executor._log(f"    - 共 {len(node_first_index_map)} 条映射", log_callback)
    
    executor._log(
        f"· 前置候选：_recent_node_position_deltas 中共有 {len(deltas)} 个节点参与距离计算（目标程序坐标=({target_x:.1f},{target_y:.1f})）",
        log_callback,
    )
    debug_candidates: list[str] = []
    debug_filtered: list[str] = []  # 记录被过滤掉的节点
    for ref_id, (delta_x, delta_y) in deltas.items():
        if ref_id == node.id:
            continue
        ref_node = graph_model.nodes.get(ref_id)
        ref_title = ref_node.title if ref_node else "<未知>"
        # 检查是否被步骤顺序过滤
        if not _is_reference_node_allowed(executor, ref_id):
            # 打印被过滤的原因
            first_idx = node_first_index_map.get(ref_id) if isinstance(node_first_index_map, dict) else None
            debug_filtered.append(
                f"    - [过滤] '{ref_title}' (id={ref_id}) first_create_index={first_idx}, "
                f"current_step_index={current_step_index} -> 被视为未来步骤节点"
            )
            continue
        if ref_node is None:
            continue
        ref_x = float(ref_node.pos[0])
        ref_y = float(ref_node.pos[1])
        dist2 = (ref_x - target_x) * (ref_x - target_x) + (ref_y - target_y) * (ref_y - target_y)
        debug_candidates.append(
            f"    - 候选 '{ref_node.title}' (id={ref_id}) 程序坐标=({ref_x:.1f},{ref_y:.1f}) "
            f"缓存Δ≈({delta_x:.1f},{delta_y:.1f}) dist²≈{dist2:.1f}"
        )
        if dist2 < best_dist2:
            best_dist2 = dist2
            best_ref = (delta_x, delta_y, ref_node)
    
    # 打印被过滤的节点
    if debug_filtered:
        executor._log("· 前置候选过滤详情：", log_callback)
        for line in debug_filtered:
            executor._log(line, log_callback)
    if best_ref is None:
        if debug_candidates:
            executor._log("· 前置候选详情：", log_callback)
            for line in debug_candidates:
                executor._log(line, log_callback)
        return None
    # 当最近候选在程序坐标上的距离远超当前视口尺寸时，视为位置完全不相干，放弃使用前置偏移
    max_allowed_dist2: Optional[float] = None
    get_view_rect = getattr(executor, "get_program_viewport_rect", None)
    if callable(get_view_rect):
        rect = get_view_rect()
        if isinstance(rect, tuple) and len(rect) >= 4:
            left, top, right, bottom = rect[0], rect[1], rect[2], rect[3]
            view_width = float(right) - float(left)
            view_height = float(bottom) - float(top)
            max_span = view_width if view_width >= view_height else view_height
            if max_span > 0.0:
                # 允许的最大参考距离：约为视口对角线的 ~1.5 倍（防止跨场景节点被误选为前置）
                threshold = max_span * 1.5
                max_allowed_dist2 = threshold * threshold
    if max_allowed_dist2 is not None and best_dist2 > max_allowed_dist2:
        if debug_candidates:
            executor._log("· 前置候选详情：", log_callback)
            for line in debug_candidates:
                executor._log(line, log_callback)
        executor._log(
            f"· 前置候选：最近候选与目标距离过大 dist²≈{best_dist2:.1f}，超过阈值≈{max_allowed_dist2:.1f}，放弃使用前置偏移",
            log_callback,
        )
        return None
    delta_x, delta_y, ref_node = best_ref
    if abs(delta_x) < 1e-2 and abs(delta_y) < 1e-2:
        if debug_candidates:
            executor._log("· 前置候选详情：", log_callback)
            for line in debug_candidates:
                executor._log(line, log_callback)
        executor._log(
            f"· 前置候选：选中的前置节点 '{ref_node.title}' 偏移过小 Δ≈({delta_x:.3f},{delta_y:.3f})，放弃使用",
            log_callback,
        )
        return None
    new_pos = (target_x + delta_x, target_y + delta_y)
    node.pos = new_pos
    if debug_candidates:
        executor._log("· 前置候选详情：", log_callback)
        for line in debug_candidates:
            executor._log(line, log_callback)
    executor._log(
        f"· 单步：参考前置节点 '{ref_node.title}' 偏移 Δ≈({delta_x:.1f},{delta_y:.1f}) → 调整程序坐标=({new_pos[0]:.1f},{new_pos[1]:.1f})",
        log_callback,
    )
    if hasattr(executor, "__dict__"):
        executor._last_create_position_debug = {
            "source": "nearest_delta",
            "anchor_node_id": str(ref_node.id),
        }
    return new_pos


def _ensure_creation_trackers(executor) -> Tuple[list[str], set[str]]:
    history = getattr(executor, "_created_node_history", None)
    lookup = getattr(executor, "_created_node_lookup", None)
    if not isinstance(history, list):
        history = []
        setattr(executor, "_created_node_history", history)
    if not isinstance(lookup, set):
        lookup = set()
        setattr(executor, "_created_node_lookup", lookup)
    return history, lookup


def _record_node_creation(executor, node_id: str) -> None:
    if not node_id:
        return
    history, lookup = _ensure_creation_trackers(executor)
    if node_id in lookup:
        return
    history.append(node_id)
    lookup.add(node_id)


def _select_creation_anchor_node(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    log_callback,
) -> Optional[Tuple[NodeModel, float, int]]:
    history, _ = _ensure_creation_trackers(executor)
    if len(history) == 0:
        executor._log("· 创建锚点：暂无已创建节点，使用程序坐标", log_callback)
        return None

    target_x = float(node.pos[0])
    target_y = float(node.pos[1])

    block_index_by_node: Dict[str, int] = {}
    for block_index, basic_block in enumerate(graph_model.basic_blocks or []):
        for node_id in basic_block.nodes:
            if node_id not in block_index_by_node:
                block_index_by_node[str(node_id)] = int(block_index)
    target_block_index: Optional[int] = None
    if node.id in block_index_by_node:
        target_block_index = block_index_by_node[node.id]

    same_block_ids: list[str] = []
    other_ids: list[str] = []
    for created_id in history:
        if created_id == node.id:
            continue
        created_id_str = str(created_id)
        if (target_block_index is not None) and (created_id_str in block_index_by_node):
            if block_index_by_node[created_id_str] == target_block_index:
                same_block_ids.append(created_id_str)
                continue
        other_ids.append(created_id_str)

    search_ids: list[str] = same_block_ids if len(same_block_ids) > 0 else [cid for cid in other_ids]

    if target_block_index is not None and len(same_block_ids) > 0:
        executor._log(
            f"· 创建锚点：当前节点所在基本块包含 {len(same_block_ids)} 个已创建节点，将优先在该基本块内选择锚点",
            log_callback,
        )

    best_node: Optional[NodeModel] = None
    best_dist2: float = float("inf")
    considered = 0
    for created_id in reversed(search_ids):
        candidate = graph_model.nodes.get(created_id)
        if candidate is None:
            continue
        candidate_x = float(candidate.pos[0])
        candidate_y = float(candidate.pos[1])
        dx = candidate_x - target_x
        dy = candidate_y - target_y
        dist2 = dx * dx + dy * dy
        considered += 1
        if dist2 < best_dist2:
            best_dist2 = dist2
            best_node = candidate

    if best_node is None:
        executor._log("· 创建锚点：未找到可作为参考的节点，使用程序坐标", log_callback)
        return None

    return (best_node, best_dist2, considered)


def _adjust_program_position_with_creation_anchor(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    visible_map: Dict[str, Dict[str, Any]],
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> Tuple[Optional[Tuple[float, float]], Dict[str, Dict[str, Any]]]:
    if executor.scale_ratio is None or executor.origin_node_pos is None:
        return (None, visible_map)
    anchor_payload = _select_creation_anchor_node(executor, graph_model, node, log_callback)
    if anchor_payload is None:
        return (None, visible_map)
    anchor_node, best_dist2, considered = anchor_payload
    executor._log(
        f"· 创建锚点：从 {considered} 个候选中选择 '{anchor_node.title}' (id={anchor_node.id})，dist²≈{best_dist2:.1f}",
        log_callback,
    )
    anchor_info = visible_map.get(anchor_node.id) if visible_map else None
    if not anchor_info or not anchor_info.get('visible'):
        executor._log(f"· 创建锚点：'{anchor_node.title}' 当前不可见，开始对齐视口", log_callback)
        executor.ensure_program_point_visible(
            float(anchor_node.pos[0]),
            float(anchor_node.pos[1]),
            margin_ratio=0.10,
            max_steps=8,
            pan_step_pixels=420,
            log_callback=log_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            visual_callback=visual_callback,
            graph_model=graph_model,
        )
        visible_map = executor.recognize_visible_nodes(graph_model)
        anchor_info = visible_map.get(anchor_node.id)
        if not anchor_info or not anchor_info.get('visible'):
            executor._log(f"· 创建锚点：未能识别到 '{anchor_node.title}'，回退程序坐标", log_callback)
            return (None, visible_map)
    bbox = anchor_info.get('bbox')
    if not bbox:
        executor._log(f"· 创建锚点：'{anchor_node.title}' 缺少识别bbox，回退程序坐标", log_callback)
        return (None, visible_map)
    expected_editor_x, expected_editor_y = executor.convert_program_to_editor_coords(
        float(anchor_node.pos[0]),
        float(anchor_node.pos[1]),
    )
    actual_editor_x = float(bbox[0])
    actual_editor_y = float(bbox[1])
    scale = float(executor.scale_ratio)
    threshold_editor_x, threshold_editor_y = compute_position_thresholds(scale)
    tolerance_editor_x = float(max(30.0, threshold_editor_x * 0.6))
    tolerance_editor_y = float(max(30.0, threshold_editor_y * 0.6))
    offset_editor_x = abs(actual_editor_x - float(expected_editor_x))
    offset_editor_y = abs(actual_editor_y - float(expected_editor_y))
    if offset_editor_x > tolerance_editor_x or offset_editor_y > tolerance_editor_y:
        executor._log(
            f"· 创建锚点：'{anchor_node.title}' 识别坐标 Δeditor≈({offset_editor_x:.1f},{offset_editor_y:.1f}) 超出阈值({tolerance_editor_x:.1f},{tolerance_editor_y:.1f})，回退程序坐标",
            log_callback,
        )
        return (None, visible_map)
    delta_prog_x = (actual_editor_x - float(expected_editor_x)) / scale
    delta_prog_y = (actual_editor_y - float(expected_editor_y)) / scale
    new_prog_x = float(node.pos[0]) + delta_prog_x
    new_prog_y = float(node.pos[1]) + delta_prog_y
    node.pos = (new_prog_x, new_prog_y)
    executor._log(
        f"· 创建锚点：参考 '{anchor_node.title}' 偏移 Δ≈({delta_prog_x:.1f},{delta_prog_y:.1f}) → 目标程序坐标=({new_prog_x:.1f},{new_prog_y:.1f})",
        log_callback,
    )
    if hasattr(executor, "__dict__"):
        executor._last_create_position_debug = {
            "source": "anchor",
            "anchor_node_id": str(anchor_node.id),
        }
    return ((new_prog_x, new_prog_y), visible_map)


def _decide_program_position_for_creation(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    visible_map: Dict[str, Dict[str, Any]],
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> Tuple[float, float]:
    """综合锚点、邻居偏移与原始坐标，决策本次创建使用的程序坐标。"""
    executor._log(f"执行创建节点: {node.title}", log_callback)
    anchor_adjusted_position, _visible_after_anchor = _adjust_program_position_with_creation_anchor(
        executor,
        graph_model,
        node,
        visible_map,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )
    if anchor_adjusted_position is not None:
        program_x, program_y = anchor_adjusted_position
    else:
        adjusted_program_pos = _infer_program_position_with_neighbor_offsets(
            executor,
            graph_model,
            node,
            log_callback,
        )
        if adjusted_program_pos is not None:
            program_x, program_y = adjusted_program_pos
        else:
            program_x, program_y = node.pos
            if hasattr(executor, "__dict__"):
                executor._last_create_position_debug = {
                    "source": "original",
                }
    return float(program_x), float(program_y)


def _perform_node_creation_interaction(
    executor: EditorExecutorWithViewport,
    graph_model: GraphModel,
    node: NodeModel,
    node_id: str,
    program_x: float,
    program_y: float,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> bool:
    """基于已决策的程序坐标，在编辑器中完成右键、输入与候选选择的整个创建流程。"""
    executor.ensure_program_point_visible(
        program_x,
        program_y,
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
    if hasattr(executor, "debug_capture_create_node_position"):
        executor.debug_capture_create_node_position(
            graph_model,
            node,
            float(program_x),
            float(program_y),
            log_callback=log_callback,
            visual_callback=visual_callback,
        )
    editor_x, editor_y = executor.convert_program_to_editor_coords(program_x, program_y)
    screen_x, screen_y = executor.convert_editor_to_screen_coords(editor_x, editor_y)
    executor._log(f"  程序坐标: ({program_x:.1f}, {program_y:.1f})", log_callback)
    executor._log(f"  编辑器坐标: ({editor_x}, {editor_y})", log_callback)
    executor._log(f"  屏幕坐标: ({screen_x}, {screen_y})", log_callback)
    executor._last_context_click_editor_pos = (editor_x, editor_y)
    if not executor._right_click_with_hooks(
        screen_x,
        screen_y,
        pause_hook,
        allow_continue,
        log_callback,
        visual_callback,
        linger_seconds=NODE_LIST_CONTEXT_LINGER_SECONDS,
    ):
        return False
    executor._log("等待 0.30 秒", log_callback)
    sleep_seconds(0.3)
    if not executor._input_text_with_hooks(node.title, pause_hook, allow_continue, log_callback):
        return False
    # 输入后稳定等待更久再进行候选列表识别（提升弹窗稳定性）
    if not executor._wait_with_hooks(POST_INPUT_STABILIZE_SECONDS, pause_hook, allow_continue, 0.1, log_callback):
        return False
    # —— 快速创建：不再使用“回车确认”，统一走候选列表 OCR 点击 ——
    # —— 回退：OCR 候选列表选择 ——
    executor._log(f"等待候选列表并点击 '{node.title}'...", log_callback)
    if not select_from_search_popup(
        executor,
        node.title,
        wait_seconds=3.0,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    ):
        executor._log(f"✗ 未能选择 '{node.title}'，步骤中止", log_callback)
        return False
    executor._log("等待 0.30 秒", log_callback)
    sleep_seconds(0.3)
    executor._log(f"✓ 节点创建完成：{node.title} (id={node_id})", log_callback)
    _record_node_creation(executor, node_id)
    return True


def execute_create_node(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: Any,
    log_callback: Optional[Callable[[str], None]] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    if hasattr(executor, "__dict__"):
        executor._last_create_position_debug = {}
    node_id = todo_item.get("node_id")
    if not node_id:
        executor._log("✗ 缺少节点ID", log_callback)
        return False
    node = graph_model.nodes.get(node_id)
    if not node:
        executor._log(f"✗ 未找到节点: {node_id}", log_callback)
        return False

    # 可见性判定仅作为“可跳过创建”的保守条件：
    # - 识别到的节点左上角需与期望 editor 坐标足够接近（≤30px）才视为“已存在”
    # - 否则继续创建，避免因为场上存在同名/相似节点而错误跳过
    visible_map = executor.recognize_visible_nodes(graph_model)
    vis_info = visible_map.get(node_id, {})
    already_visible = bool(vis_info.get('visible'))
    if already_visible:
        bbox = vis_info.get('bbox')
        expected_editor_x, expected_editor_y = executor.convert_program_to_editor_coords(node.pos[0], node.pos[1])
        close_enough = False
        if bbox is not None:
            left_v, top_v, _, _ = bbox
            dx = float(left_v - expected_editor_x)
            dy = float(top_v - expected_editor_y)
            # 30px 距离阈值（左上角为锚点，与系统其他几何逻辑一致）
            close_enough = (dx * dx + dy * dy) <= (30.0 * 30.0)
        if close_enough:
            executor._log(f"· 节点已存在（坐标匹配≤30px），此创建步视为已完成：{node.title}", log_callback)
            _record_node_creation(executor, node_id)
            return True

    program_x, program_y = _decide_program_position_for_creation(
        executor,
        graph_model,
        node,
        visible_map,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )
    return _perform_node_creation_interaction(
        executor,
        graph_model,
        node,
        str(node_id),
        float(program_x),
        float(program_y),
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def execute_create_node_unmapped(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: Any,
    log_callback: Optional[Callable[[str], None]] = None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """
    在尚未建立坐标映射（scale_ratio / origin_node_pos 为空）时的首个创建步骤。

    行为：
    - 不依赖程序坐标与视口对齐逻辑，直接在当前“节点图布置区域”的几何中心右键并创建节点；
    - 创建成功后，调用方应基于该节点执行一次坐标校准，以便后续步骤使用统一的映射。
    """
    if hasattr(executor, "__dict__"):
        executor._last_create_position_debug = {}
    node_id_value = todo_item.get("node_id")
    if not node_id_value:
        executor._log("✗ 缺少节点ID", log_callback)
        return False
    node_id = str(node_id_value)
    node_model = graph_model.nodes.get(node_id)
    if not node_model:
        executor._log(f"✗ 未找到节点: {node_id}", log_callback)
        return False

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        executor._log("✗ 截图失败（未校准创建节点）", log_callback)
        return False

    region_x, region_y, region_width, region_height = editor_capture.get_region_rect(
        screenshot,
        "节点图布置区域",
    )
    center_editor_x = int(region_x + region_width // 2)
    center_editor_y = int(region_y + region_height // 2)

    screen_x, screen_y = executor.convert_editor_to_screen_coords(
        center_editor_x,
        center_editor_y,
    )
    executor._log(
        f"执行创建节点(未校准): {node_model.title}",
        log_callback,
    )
    executor._log(
        f"  初始点击编辑器坐标: ({center_editor_x}, {center_editor_y})",
        log_callback,
    )
    executor._log(
        f"  初始点击屏幕坐标: ({screen_x}, {screen_y})",
        log_callback,
    )
    executor._last_context_click_editor_pos = (center_editor_x, center_editor_y)

    if not executor._right_click_with_hooks(
        screen_x,
        screen_y,
        pause_hook,
        allow_continue,
        log_callback,
        visual_callback,
        linger_seconds=NODE_LIST_CONTEXT_LINGER_SECONDS,
    ):
        return False

    executor._log("等待 0.30 秒", log_callback)
    sleep_seconds(0.3)
    if not executor._input_text_with_hooks(
        node_model.title,
        pause_hook,
        allow_continue,
        log_callback,
    ):
        return False

    if not executor._wait_with_hooks(
        POST_INPUT_STABILIZE_SECONDS,
        pause_hook,
        allow_continue,
        0.1,
        log_callback,
    ):
        return False

    executor._log(
        f"等待候选列表并点击 '{node_model.title}'...",
        log_callback,
    )
    if not select_from_search_popup(
        executor,
        node_model.title,
        wait_seconds=3.0,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    ):
        executor._log(
            f"✗ 未能选择 '{node_model.title}'，步骤中止",
            log_callback,
        )
        return False

    executor._log("等待 0.30 秒", log_callback)
    sleep_seconds(0.3)
    executor._log(
        f"✓ 节点创建完成：{node_model.title} (id={node_id})",
        log_callback,
    )
    _record_node_creation(executor, str(node_id))
    return True


