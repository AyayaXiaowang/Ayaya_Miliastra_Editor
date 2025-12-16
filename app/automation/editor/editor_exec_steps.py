# -*- coding: utf-8 -*-
"""
执行步骤编排：
- 单步执行分派
- 创建/连接/配置类步骤的编排（底层委托 editor_nodes.py/editor_connect.py）
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable
from PIL import Image

from app.automation.input.common import log_start, log_ok, log_fail
from app.automation.vision import invalidate_cache
from app.automation.editor import editor_connect, editor_nodes
from app.automation import capture as editor_capture
from app.automation.input import win_input
from app.automation.config.signal_config import execute_bind_signal
from app.automation.editor.ui_constants import NODE_VIEW_WIDTH_PX, NODE_VIEW_HEIGHT_PX
from app.automation.editor import executor_utils as _exec_utils
from engine.configs.settings import settings
from engine.graph.models.graph_model import GraphModel
from . import editor_recognition as _rec

from .automation_step_types import (
    GRAPH_STEP_CREATE_NODE,
    GRAPH_STEP_CONNECT,
    GRAPH_STEP_CREATE_AND_CONNECT,
    GRAPH_STEP_CONNECT_MERGED,
    GRAPH_STEP_CONFIG_NODE_MERGED,
    GRAPH_STEP_SET_PORT_TYPES_MERGED,
    GRAPH_STEP_ADD_VARIADIC_INPUTS,
    GRAPH_STEP_ADD_DICT_PAIRS,
    GRAPH_STEP_ADD_BRANCH_OUTPUTS,
    GRAPH_STEP_CONFIG_BRANCH_OUTPUTS,
    GRAPH_STEP_BIND_SIGNAL,
    FAST_CHAIN_ELIGIBLE_STEP_TYPES,
)


# 为了后续在步骤层统一控制“截图/识别/视口同步”等前置流程，这里对步骤处理函数做一个统一别名，
# 便于在类型注释与计划表中复用。
StepHandler = Callable[
    [
        Any,
        Dict[str, Any],
        GraphModel,
        Optional[Callable[[str], None]],
        Optional[Callable[[], None]],
        Optional[Callable[[], bool]],
        Optional[Callable[[Image.Image, Optional[dict]], None]],
    ],
    bool,
]


@dataclass(frozen=True)
class _StepExecutionPlan:
    """单个 graph_* 步骤类型的执行计划。

    当前字段均保持与原有行为一致，仅对结构做轻量抽象，后续可以在此处集中控制：
    - 是否需要视口同步
    - 是否需要连线前识别预热
    - 成功后是否主动失效视觉缓存
    """

    handler: StepHandler
    requires_connect_prepare: bool = False
    invalidate_cache_on_success: bool = False
    # 视口同步标记：目前所有步骤都需要，在后续做“高容错步骤跳过识别”时再做区分。
    requires_view_sync: bool = True
    # 标记该步骤是否会导致节点布局发生变化（创建节点、连线拖拽等），用于在成功后失效场景级截图缓存。
    mutates_layout: bool = False


def _prepare_for_connect_if_needed(executor, log_callback) -> None:
    if executor.should_prepare_for_connect():
        _rec.prepare_for_connect(executor, log_callback)
        executor.mark_connect_prepared()
    else:
        executor.log("· 连线预热：视口未变化，跳过识别缓存刷新", log_callback)


def _handle_graph_create_node(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_nodes.execute_create_node(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_connect(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_connect(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_create_and_connect(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    created = editor_nodes.execute_create_node(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )
    if not created:
        return False
    invalidate_cache()
    _prepare_for_connect_if_needed(executor, log_callback)
    return editor_connect.execute_connect(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_connect_merged(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    node1_id = todo_item.get("node1_id")
    node2_id = todo_item.get("node2_id")
    edges_list = todo_item.get("edges") or []
    if not node1_id or not node2_id or not isinstance(edges_list, list) or len(edges_list) == 0:
        executor.log("✗ 合并连线步骤缺少必要信息", log_callback)
        return False
    orig_x, orig_y = editor_capture.get_cursor_pos()
    # 复用链上下文仅用于保留节点级快照等结构化信息，
    # 截图与检测结果会在每条连线前强制清理，以便重新截图并识别端口位置。
    reuse_context = executor.begin_connect_chain_step()
    if not reuse_context:
        reuse_context = {
            "node_snapshots": {},
            "screenshot": None,
        }
    else:
        reuse_context.setdefault("node_snapshots", {})
        reuse_context.setdefault("screenshot", None)
    ok_all = True
    for edge_info in edges_list:
         # 每条连线开始前显式丢弃上一条连线产生的截图与检测缓存，
         # 确保当前连线在最新画面上重新截图并识别端口位置。
        if reuse_context is not None:
            for key in ("screenshot", "screenshot_token", "detected_nodes", "detected_nodes_token"):
                if key in reuse_context:
                    reuse_context.pop(key, None)
        edge_payload = {
            "type": "graph_connect",
            "src_node": node1_id,
            "dst_node": node2_id,
            "src_port": edge_info.get("src_port"),
            "dst_port": edge_info.get("dst_port"),
            "edge_id": edge_info.get("edge_id"),
        }
        ok = editor_connect.execute_connect(
            executor,
            edge_payload,
            graph_model,
            log_callback,
            pause_hook,
            allow_continue,
            visual_callback,
            reuse_context=reuse_context,
        )
        if not ok:
            ok_all = False
            break
    win_input.move_mouse_absolute(int(orig_x), int(orig_y))
    executor.complete_connect_chain_step(reuse_context, ok_all)
    return ok_all


def _handle_graph_config_node_merged(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_config_node_merged(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_set_port_types(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_set_port_types_merged(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_variadic_inputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_variadic_inputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_dict_pairs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_dict_pairs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_add_branch_outputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_add_branch_outputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_config_branch_outputs(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return editor_connect.execute_config_branch_outputs(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


def _handle_graph_bind_signal(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook,
    allow_continue,
    visual_callback,
) -> bool:
    return execute_bind_signal(
        executor,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )


_STEP_PLANS: Dict[str, _StepExecutionPlan] = {
    GRAPH_STEP_CREATE_NODE: _StepExecutionPlan(
        handler=_handle_graph_create_node,
        # 创建节点会显式改变场景布局，需要在成功后失效场景级快照，
        # 保证下一步在相同视口下也会重新截图并纳入新节点。
        mutates_layout=True,
    ),
    GRAPH_STEP_CONNECT: _StepExecutionPlan(
        handler=_handle_graph_connect,
        requires_connect_prepare=True,
        mutates_layout=True,
    ),
    GRAPH_STEP_CREATE_AND_CONNECT: _StepExecutionPlan(
        handler=_handle_graph_create_and_connect,
        mutates_layout=True,
    ),
    GRAPH_STEP_CONNECT_MERGED: _StepExecutionPlan(
        handler=_handle_graph_connect_merged,
        requires_connect_prepare=True,
        mutates_layout=True,
    ),
    GRAPH_STEP_CONFIG_NODE_MERGED: _StepExecutionPlan(
        handler=_handle_graph_config_node_merged,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_SET_PORT_TYPES_MERGED: _StepExecutionPlan(
        handler=_handle_graph_set_port_types,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_ADD_VARIADIC_INPUTS: _StepExecutionPlan(
        handler=_handle_graph_add_variadic_inputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_ADD_DICT_PAIRS: _StepExecutionPlan(
        handler=_handle_graph_add_dict_pairs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_ADD_BRANCH_OUTPUTS: _StepExecutionPlan(
        handler=_handle_graph_add_branch_outputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_CONFIG_BRANCH_OUTPUTS: _StepExecutionPlan(
        handler=_handle_graph_config_branch_outputs,
        requires_connect_prepare=True,
    ),
    GRAPH_STEP_BIND_SIGNAL: _StepExecutionPlan(
        handler=_handle_graph_bind_signal,
        requires_connect_prepare=True,
    ),
}


def _ensure_zoom_ready(
    executor,
    step_type: str,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> bool:
    """在进入任意 graph_* 步骤前，统一确保画布缩放为 50%。

    行为保持与原逻辑一致：
    - 若 zoom_50_confirmed 已为 True，则不再重复检查；
    - 否则调用 ensure_zoom_ratio_50，失败时记录日志并终止当前步骤。
    """
    if bool(getattr(executor, "zoom_50_confirmed", False)):
        return True
    ok_zoom_pre = executor.ensure_zoom_ratio_50(
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )
    if not ok_zoom_pre:
        executor.log("✗ 无法将缩放调整为 50%，终止此步", log_callback)
        return False
    return True


def _resolve_step_plan(step_type_raw: object, executor, log_callback) -> tuple[str, Optional[_StepExecutionPlan]]:
    """根据 todo_item.type 解析步骤类型并从计划表中取出对应计划。

    仅做类型解析与 plan 查找，不触发任何副作用，便于在日志中使用统一的 step_type 字符串。
    """
    step_type = str(step_type_raw or "")
    step_plan = _STEP_PLANS.get(step_type or "")
    if step_plan is None:
        executor.log(f"✗ 不支持的步骤类型: {step_type}", log_callback)
    return step_type, step_plan


def _sync_view_if_needed(
    executor,
    graph_model: GraphModel,
    step_plan: _StepExecutionPlan,
    log_callback,
) -> None:
    """在非快速链模式下，根据步骤计划决定是否执行视口同步。

    当前实现中所有步骤的 requires_view_sync 均为 True，因此行为与原逻辑完全一致：
    - fast_chain_mode=True 时完全跳过此阶段；
    - fast_chain_mode=False 时，当视口 token 发生变化才调用同步函数。
    """
    if not bool(getattr(executor, "fast_chain_mode", False)) and bool(step_plan.requires_view_sync):
        if executor.should_sync_visible_nodes_positions():
            synced_count = executor.sync_visible_nodes_positions(
                graph_model,
                threshold_px=60.0,
                log_callback=log_callback,
            )
            executor.mark_visible_nodes_positions_synced()
            if synced_count > 0:
                executor.log(
                    f"· 单步：同步可见节点坐标 {synced_count} 个，避免使用过期位置",
                    log_callback,
                )
            else:
                executor.log("· 单步：重新确认视口，无可更新坐标", log_callback)
        else:
            executor.log("· 单步：视口未变化，跳过可见节点同步", log_callback)


def _execute_step_within_graph_roi(
    executor,
    step_type: str,
    step_plan: _StepExecutionPlan,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> bool:
    """在“节点图布置区域”上下文中执行具体步骤，并负责统一的日志与缓存处理。"""
    with editor_capture.enforce_graph_roi_context():
        start_ms = log_start(
            "core.automation.EditorExecutor.execute_step",
            step=step_type,
        )

        if step_type != GRAPH_STEP_CONNECT_MERGED:
            executor.invalidate_connect_chain_context("step type changed")

        if step_plan.requires_connect_prepare:
            _prepare_for_connect_if_needed(executor, log_callback)

        result = step_plan.handler(
            executor,
            todo_item,
            graph_model,
            log_callback,
            pause_hook,
            allow_continue,
            visual_callback,
        )

        if result:
            if step_plan.invalidate_cache_on_success:
                invalidate_cache()
            # 若步骤被标记为会改变节点布局，则在成功后显式失效场景级快照，
            # 确保后续步骤在相同视口下也会重新截图与识别。
            if getattr(step_plan, "mutates_layout", False):
                invalidate_scene = getattr(executor, "invalidate_scene_snapshot", None)
                if callable(invalidate_scene):
                    invalidate_scene(f"step:{step_type}")

        if result:
            log_ok(
                "core.automation.EditorExecutor.execute_step",
                start_ms,
                step=str(step_type or ""),
            )
        else:
            log_fail(
                "core.automation.EditorExecutor.execute_step",
                start_ms,
                step=str(step_type or ""),
            )

        return bool(result)


def _click_canvas_blank_after_step(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    *,
    step_type: str,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> None:
    """
    统一的步骤收尾小流程：在目标节点上方附近点击一次画布空白位置。

    设计要点：
    - 仅在 REAL_EXEC_CLICK_BLANK_AFTER_STEP 开关启用且已建立坐标映射时生效；
    - 优先使用当前步骤关联的节点（node_id / dst_node / src_node / node2_id / node1_id）推导起点；
    - 起点选在“节点顶部上方、与节点水平居中对齐”的编辑器坐标，再委托画布吸附逻辑寻找安全空白点；
    - 若无法解析到节点，则回退到最近一次上下文右键位置；若仍不可用则直接跳过。
    """
    if not getattr(settings, "REAL_EXEC_CLICK_BLANK_AFTER_STEP", True):
        return

    scale_ratio_value = getattr(executor, "scale_ratio", None)
    if scale_ratio_value is None:
        return

    nodes_mapping = getattr(graph_model, "nodes", None)
    if not isinstance(nodes_mapping, dict) or len(nodes_mapping) == 0:
        return

    primary_node_id_value = (
        todo_item.get("node_id")
        or todo_item.get("dst_node")
        or todo_item.get("src_node")
        or todo_item.get("node2_id")
        or todo_item.get("node1_id")
    )
    primary_node_id = str(primary_node_id_value or "")

    start_screen_x: Optional[int] = None
    start_screen_y: Optional[int] = None

    if primary_node_id and primary_node_id in nodes_mapping:
        node_model = nodes_mapping[primary_node_id]
        node_pos = getattr(node_model, "pos", None)
        if isinstance(node_pos, (list, tuple)) and len(node_pos) >= 2:
            program_x = float(node_pos[0])
            program_y = float(node_pos[1])
            editor_x, editor_y = executor.convert_program_to_editor_coords(program_x, program_y)

            scale_value = float(scale_ratio_value) if abs(float(scale_ratio_value)) > 1e-6 else 1.0
            node_width_editor = int(NODE_VIEW_WIDTH_PX * scale_value)
            node_height_editor = int(NODE_VIEW_HEIGHT_PX * scale_value)

            center_editor_x = int(editor_x) + int(node_width_editor // 2)
            preferred_offset_pixels = int(min(node_height_editor * 0.8, 80.0))
            if preferred_offset_pixels < 20:
                preferred_offset_pixels = 20
            above_editor_y = int(editor_y) - preferred_offset_pixels

            screen_x, screen_y = executor.convert_editor_to_screen_coords(
                int(center_editor_x),
                int(above_editor_y),
            )
            start_screen_x = int(screen_x)
            start_screen_y = int(screen_y)

    if start_screen_x is None or start_screen_y is None:
        get_last_context = getattr(executor, "get_last_context_click_editor_pos", None)
        last_editor_pos = get_last_context() if callable(get_last_context) else None
        if isinstance(last_editor_pos, tuple) and len(last_editor_pos) >= 2:
            last_editor_x = int(last_editor_pos[0])
            last_editor_y = int(last_editor_pos[1])
            screen_x, screen_y = executor.convert_editor_to_screen_coords(
                int(last_editor_x),
                int(last_editor_y),
            )
            start_screen_x = int(screen_x)
            start_screen_y = int(screen_y)
        else:
            return

    _exec_utils.click_canvas_blank_near_screen_point(
        executor,
        int(start_screen_x),
        int(start_screen_y),
        log_prefix=f"[步骤收尾] {step_type} ",
        wait_seconds=0.1,
        wait_message="等待 0.10 秒（步骤收尾后画布状态稳定）",
        log_callback=log_callback,
        visual_callback=visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )


def _execute_step_impl(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    *,
    step_planner: "AutomationStepPlanner | None" = None,
    recognizer: "AutomationRecognizer | None" = None,
) -> bool:
    step_planner = step_planner if step_planner is not None else AutomationStepPlanner()
    recognizer = recognizer if recognizer is not None else AutomationRecognizer()

    # 1. 统一保证缩放为 50%（连续执行时通常已在外层完成，仅在标记未确认时触发一次性检查）
    if not _ensure_zoom_ready(
        executor,
        str(todo_item.get("type") or ""),
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    ):
        return False

    # 2. 解析步骤类型并处理“未校准首创建”场景
    raw_step_type = todo_item.get("type")
    step_type, plan = step_planner.resolve_step_plan(raw_step_type, executor, log_callback)
    if executor.scale_ratio is None:
        if step_type == GRAPH_STEP_CREATE_NODE or step_type == GRAPH_STEP_CREATE_AND_CONNECT:
            # 在尚未建立坐标映射时，允许首个创建步骤在画布中心放置节点，
            # 随后基于该节点执行一次锚点坐标校准，再继续后续步骤。
            with editor_capture.enforce_graph_roi_context():
                start_ms = log_start(
                    "core.automation.EditorExecutor.execute_step",
                    step=str(step_type or ""),
                )
                created_ok = editor_nodes.execute_create_node_unmapped(
                    executor,
                    todo_item,
                    graph_model,
                    log_callback,
                    pause_hook,
                    allow_continue,
                    visual_callback,
                )
                if not created_ok:
                    log_fail(
                        "core.automation.EditorExecutor.execute_step",
                        start_ms,
                        step=str(step_type or ""),
                    )
                    return False

                node_id_value = todo_item.get("node_id")
                anchor_title: str | None = None
                anchor_program_pos: tuple[float, float] | None = None
                if node_id_value and node_id_value in graph_model.nodes:
                    anchor_node = graph_model.nodes[node_id_value]
                    anchor_title = anchor_node.title
                    anchor_program_pos = tuple(anchor_node.pos)
                if not anchor_title or not anchor_program_pos:
                    executor.log("✗ 未能获取锚点节点信息，无法完成坐标校准", log_callback)
                    log_fail(
                        "core.automation.EditorExecutor.execute_step",
                        start_ms,
                        step=str(step_type or ""),
                    )
                    return False

                calibrated_ok = executor.calibrate_coordinates(
                    anchor_title,
                    anchor_program_pos,
                    log_callback=log_callback,
                    create_anchor_node=False,
                    pause_hook=pause_hook,
                    allow_continue=allow_continue,
                    visual_callback=visual_callback,
                    graph_model=graph_model,
                )
                if not calibrated_ok:
                    log_fail(
                        "core.automation.EditorExecutor.execute_step",
                        start_ms,
                        step=str(step_type or ""),
                    )
                    return False

                # 若当前步骤为“创建并连线”，在校准完成后继续执行连接部分。
                if step_type == GRAPH_STEP_CREATE_AND_CONNECT:
                    if plan is None:
                        return False
                    recognizer.sync_view_if_needed(
                        executor,
                        graph_model,
                        plan,
                        log_callback,
                    )
                    result_connect = _execute_step_within_graph_roi(
                        executor,
                        step_type,
                        plan,
                        todo_item,
                        graph_model,
                        log_callback,
                        pause_hook,
                        allow_continue,
                        visual_callback,
                    )
                    if result_connect:
                        _click_canvas_blank_after_step(
                            executor,
                            todo_item,
                            graph_model,
                            step_type=step_type,
                            log_callback=log_callback,
                            pause_hook=pause_hook,
                            allow_continue=allow_continue,
                            visual_callback=visual_callback,
                        )
                    return bool(result_connect)

                log_ok(
                    "core.automation.EditorExecutor.execute_step",
                    start_ms,
                    step=str(step_type or ""),
                )
                _click_canvas_blank_after_step(
                    executor,
                    todo_item,
                    graph_model,
                    step_type=step_type,
                    log_callback=log_callback,
                    pause_hook=pause_hook,
                    allow_continue=allow_continue,
                    visual_callback=visual_callback,
                )
                return True

        executor.log("✗ 坐标未校准，请先调用calibrate_coordinates()", log_callback)
        log_fail(
            "core.automation.EditorExecutor.execute_step",
            log_start("core.automation.EditorExecutor.execute_step", step=str(step_type or "")),
            reason="not_calibrated",
        )
        return False

    if plan is None:
        # 不支持的步骤类型，日志已在 _resolve_step_plan 中输出
        return False

    # 3. 在非快速链模式下，根据当前视口 token 决定是否需要同步可见节点坐标
    recognizer.sync_view_if_needed(
        executor,
        graph_model,
        plan,
        log_callback,
    )

    # 4. 在节点图 ROI 上下文中执行真正的步骤逻辑（包含连线预热与缓存处理）
    result_step = _execute_step_within_graph_roi(
        executor,
        step_type,
        plan,
        todo_item,
        graph_model,
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    )
    if result_step:
        _click_canvas_blank_after_step(
            executor,
            todo_item,
            graph_model,
            step_type=step_type,
            log_callback=log_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            visual_callback=visual_callback,
        )
    return bool(result_step)


class AutomationStepPlanner:
    """planner：把 todo_item 解析为 (step_type, step_plan) 的纯规划阶段。"""

    def resolve_step_plan(self, step_type_raw: object, executor, log_callback) -> tuple[str, Optional[_StepExecutionPlan]]:
        return _resolve_step_plan(step_type_raw, executor, log_callback)


class AutomationRecognizer:
    """recognizer：统一封装“视口同步 / 连线前预热”等识别侧前置步骤。"""

    def sync_view_if_needed(
        self,
        executor,
        graph_model: GraphModel,
        step_plan: _StepExecutionPlan,
        log_callback,
    ) -> None:
        _sync_view_if_needed(executor, graph_model, step_plan, log_callback)


class AutomationStepRunner:
    """step runner：执行单个 todo 步骤的编排入口（planner → recognizer → handler）。"""

    def __init__(
        self,
        *,
        step_planner: AutomationStepPlanner | None = None,
        recognizer: AutomationRecognizer | None = None,
    ) -> None:
        self._step_planner = step_planner if step_planner is not None else AutomationStepPlanner()
        self._recognizer = recognizer if recognizer is not None else AutomationRecognizer()

    def run_step(
        self,
        executor,
        todo_item: Dict[str, Any],
        graph_model: GraphModel,
        log_callback=None,
        pause_hook: Optional[Callable[[], None]] = None,
        allow_continue: Optional[Callable[[], bool]] = None,
        visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    ) -> bool:
        return _execute_step_impl(
            executor,
            todo_item,
            graph_model,
            log_callback=log_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
            visual_callback=visual_callback,
            step_planner=self._step_planner,
            recognizer=self._recognizer,
        )


def execute_step(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """兼容入口：保持对外 API 不变，但内部收敛为 planner → step runner → recognizer。"""
    return AutomationStepRunner().run_step(
        executor,
        todo_item,
        graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )
