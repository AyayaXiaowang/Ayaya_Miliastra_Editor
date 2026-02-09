# -*- coding: utf-8 -*-
"""
执行步骤编排（单步）。

定位：
- 本模块仅负责“planner → recognizer → handler”的编排入口；
- 步骤计划表 / 识别预热 / 视口同步 / 缓存失效 / 回放记录 等横切关注点已拆分到 `editor/pipeline/`。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Callable

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor import editor_nodes
from app.automation.editor import executor_utils as _exec_utils
from app.automation.vision.ui_profile_params import get_node_view_size_px
from app.automation.editor.pipeline.cache_policy import (
    EXECUTE_STEP_LOG_KEY,
    invalidate_before_step,
    invalidate_after_success,
)
from app.automation.editor.pipeline.recognition_prewarm import prepare_for_connect_if_needed
from app.automation.editor.pipeline.replay_recorder import (
    get_or_create_replay_recorder,
    should_record_step_io,
)
from app.automation.editor.pipeline.step_plans import StepExecutionPlan, resolve_step_plan
from app.automation.editor.pipeline.viewport_sync import sync_view_if_needed
from app.automation.input.common import log_start, log_ok, log_fail
from engine.configs.settings import settings
from engine.graph.models.graph_model import GraphModel

from .automation_step_types import (
    GRAPH_STEP_CREATE_NODE,
    GRAPH_STEP_CREATE_AND_CONNECT,
)


def _get_node_view_size_for_runtime() -> tuple[float, float]:
    """返回节点几何基准尺寸（用于调试与一些保守估计）。"""
    node_view_w_px, node_view_h_px = get_node_view_size_px()
    base_w = float(node_view_w_px) if float(node_view_w_px) > 0.0 else 200.0
    base_h = float(node_view_h_px) if float(node_view_h_px) > 0.0 else 100.0
    return base_w, base_h


def _ensure_zoom_ready(
    executor,
    step_type: str,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> bool:
    """在进入任意 graph_* 步骤前，统一确保画布缩放为 50%。"""
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


def _execute_step_within_graph_roi(
    executor,
    step_type: str,
    step_plan: StepExecutionPlan,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
) -> bool:
    """在“节点图布置区域”上下文中执行具体步骤，并负责统一日志/预热/缓存策略/回放记录。"""
    recorder = get_or_create_replay_recorder(executor)
    record_io = should_record_step_io(step_type, step_plan)

    with editor_capture.enforce_graph_roi_context():
        start_ms = log_start(EXECUTE_STEP_LOG_KEY, step=str(step_type or ""))

        if record_io and recorder is not None:
            screenshot_path = recorder.record_screenshot(executor=executor, stage="before", step_type=step_type)
            recorder.record_event(
                executor=executor,
                stage="before",
                step_type=step_type,
                todo_item=todo_item,
                step_plan=step_plan,
                success=None,
                extra={"screenshot_path": screenshot_path} if screenshot_path else None,
            )

        invalidate_before_step(executor, step_type)

        if bool(step_plan.requires_connect_prepare):
            prepare_for_connect_if_needed(executor, log_callback)

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
            invalidate_after_success(executor, step_type, step_plan)

        if record_io and recorder is not None:
            screenshot_path = recorder.record_screenshot(executor=executor, stage="after", step_type=step_type)
            recorder.record_event(
                executor=executor,
                stage="after",
                step_type=step_type,
                todo_item=todo_item,
                step_plan=step_plan,
                success=bool(result),
                extra={"screenshot_path": screenshot_path} if screenshot_path else None,
            )

        if result:
            log_ok(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))
        else:
            log_fail(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))

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

    # 创建节点步骤：节点已在“右键点”落下（或本步被判定为已存在而跳过创建）。
    # 此处不再做画布吸附/避让与空白点击，避免额外触发整屏识别与「颜色约束」日志；
    # 改为将鼠标移回“右键弹出节点菜单的点击点”。
    if str(step_type or "") in (GRAPH_STEP_CREATE_NODE, GRAPH_STEP_CREATE_AND_CONNECT):
        last_editor_pos = None
        get_last_context = getattr(executor, "get_last_context_click_editor_pos", None)
        last_editor_pos = get_last_context() if callable(get_last_context) else None

        # 回退：若本次创建被“已存在”短路，可能没有设置 last_context_click，
        # 仍可根据图模型节点程序坐标推导预期的 editor 坐标作为“右键点”。
        if not (isinstance(last_editor_pos, tuple) and len(last_editor_pos) >= 2):
            node_id_value = todo_item.get("node_id")
            node_id = str(node_id_value or "")
            nodes_mapping = getattr(graph_model, "nodes", None)
            if node_id and isinstance(nodes_mapping, dict) and node_id in nodes_mapping:
                node_model = nodes_mapping[node_id]
                node_pos = getattr(node_model, "pos", None)
                if isinstance(node_pos, (list, tuple)) and len(node_pos) >= 2:
                    editor_x, editor_y = executor.convert_program_to_editor_coords(float(node_pos[0]), float(node_pos[1]))
                    executor.set_last_context_click_editor_pos(int(editor_x), int(editor_y))
                    last_editor_pos = (int(editor_x), int(editor_y))

        if isinstance(last_editor_pos, tuple) and len(last_editor_pos) >= 2:
            last_editor_x = int(last_editor_pos[0])
            last_editor_y = int(last_editor_pos[1])
            screen_x, screen_y = executor.convert_editor_to_screen_coords(int(last_editor_x), int(last_editor_y))
            from app.automation.input import win_input

            win_input.move_mouse_absolute(int(screen_x), int(screen_y))
        return

    # 连接步骤的收尾点击主要用于“为后续视觉识别准备（移出遮挡/关闭悬浮态）”。
    # 快速链模式下连线链路会尽量复用同一帧 screenshot/识别结果，因此对连接步骤直接跳过，
    # 以减少每条边固定成本并提升连线吞吐。
    if _exec_utils.is_fast_chain_runtime_enabled(executor) and str(step_type or "") in (
        "graph_connect",
        "graph_connect_merged",
    ):
        scale_ratio_value = getattr(executor, "scale_ratio", None)
        if scale_ratio_value is None:
            return
        nodes_mapping = getattr(graph_model, "nodes", None)
        if not isinstance(nodes_mapping, dict) or len(nodes_mapping) == 0:
            return

        # 优先使用当前步骤关联的节点位置作为“创建锚点”（program 坐标锚点=节点 bbox 左上角）
        primary_node_id_value = (
            todo_item.get("node_id")
            or todo_item.get("dst_node")
            or todo_item.get("src_node")
            or todo_item.get("node2_id")
            or todo_item.get("node1_id")
        )
        primary_node_id = str(primary_node_id_value or "")
        if primary_node_id and primary_node_id in nodes_mapping:
            node_model = nodes_mapping[primary_node_id]
            node_pos = getattr(node_model, "pos", None)
            if isinstance(node_pos, (list, tuple)) and len(node_pos) >= 2:
                editor_x, editor_y = executor.convert_program_to_editor_coords(float(node_pos[0]), float(node_pos[1]))
                executor.set_last_context_click_editor_pos(int(editor_x), int(editor_y))
                screen_x, screen_y = executor.convert_editor_to_screen_coords(int(editor_x), int(editor_y))
                from app.automation.input import win_input

                win_input.move_mouse_absolute(int(screen_x), int(screen_y))
                return

        # 回退：移动到“最近一次上下文右键位置”（通常也是安全空白点/创建点击点）
        get_last_context = getattr(executor, "get_last_context_click_editor_pos", None)
        last_editor_pos = get_last_context() if callable(get_last_context) else None
        if isinstance(last_editor_pos, tuple) and len(last_editor_pos) >= 2:
            last_editor_x = int(last_editor_pos[0])
            last_editor_y = int(last_editor_pos[1])
            screen_x, screen_y = executor.convert_editor_to_screen_coords(int(last_editor_x), int(last_editor_y))
            from app.automation.input import win_input

            win_input.move_mouse_absolute(int(screen_x), int(screen_y))
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
            base_w, base_h = _get_node_view_size_for_runtime()
            node_width_editor = int(base_w * scale_value)
            node_height_editor = int(base_h * scale_value)

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

    # 1. 统一保证缩放为 50%
    if not _ensure_zoom_ready(
        executor,
        str(todo_item.get("type") or ""),
        log_callback,
        pause_hook,
        allow_continue,
        visual_callback,
    ):
        return False

    # 2. 解析步骤类型
    raw_step_type = todo_item.get("type")
    step_type, plan = step_planner.resolve_step_plan(raw_step_type, executor, log_callback)

    recorder = get_or_create_replay_recorder(executor)
    record_io = should_record_step_io(step_type, plan)

    # 3. 未校准首创建：允许首个创建步骤先在画布中心落点，随后基于该节点执行坐标校准
    if executor.scale_ratio is None:
        if step_type == GRAPH_STEP_CREATE_NODE or step_type == GRAPH_STEP_CREATE_AND_CONNECT:
            with editor_capture.enforce_graph_roi_context():
                start_ms = log_start(EXECUTE_STEP_LOG_KEY, step=str(step_type or ""))

                if record_io and recorder is not None:
                    screenshot_path = recorder.record_screenshot(executor=executor, stage="before_unmapped", step_type=step_type)
                    recorder.record_event(
                        executor=executor,
                        stage="before_unmapped",
                        step_type=step_type,
                        todo_item=todo_item,
                        step_plan=plan,
                        success=None,
                        extra={"screenshot_path": screenshot_path} if screenshot_path else None,
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
                    if record_io and recorder is not None:
                        screenshot_path = recorder.record_screenshot(executor=executor, stage="after_unmapped", step_type=step_type)
                        recorder.record_event(
                            executor=executor,
                            stage="after_unmapped",
                            step_type=step_type,
                            todo_item=todo_item,
                            step_plan=plan,
                            success=False,
                            extra={"screenshot_path": screenshot_path} if screenshot_path else None,
                        )
                    log_fail(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))
                    return False

                node_id_value = todo_item.get("node_id")
                anchor_title: str | None = None
                anchor_program_pos: tuple[float, float] | None = None
                if node_id_value and node_id_value in graph_model.nodes:
                    anchor_node = graph_model.nodes[node_id_value]
                    anchor_title = anchor_node.title
                    anchor_program_pos = (float(anchor_node.pos[0]), float(anchor_node.pos[1]))
                if not anchor_title or not anchor_program_pos:
                    executor.log("✗ 未能获取锚点节点信息，无法完成坐标校准", log_callback)
                    log_fail(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))
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
                    log_fail(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))
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

                log_ok(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""))
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
        start_ms = log_start(EXECUTE_STEP_LOG_KEY, step=str(step_type or ""))
        log_fail(EXECUTE_STEP_LOG_KEY, start_ms, step=str(step_type or ""), reason="not_calibrated")
        if record_io and recorder is not None:
            recorder.record_event(
                executor=executor,
                stage="skip",
                step_type=step_type,
                todo_item=todo_item,
                step_plan=plan,
                success=False,
                reason="not_calibrated",
            )
        return False

    if plan is None:
        return False

    # 4. 在非快速链模式下，根据当前视口 token 决定是否需要同步可见节点坐标
    recognizer.sync_view_if_needed(executor, graph_model, plan, log_callback)

    # 5. 在节点图 ROI 上下文中执行真正的步骤逻辑（包含预热/缓存策略/回放记录）
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

    def resolve_step_plan(self, step_type_raw: object, executor, log_callback) -> tuple[str, Optional[StepExecutionPlan]]:
        return resolve_step_plan(step_type_raw, executor, log_callback)


class AutomationRecognizer:
    """recognizer：统一封装“视口同步 / 连线前预热”等识别侧前置步骤。"""

    def sync_view_if_needed(
        self,
        executor,
        graph_model: GraphModel,
        step_plan: StepExecutionPlan,
        log_callback,
    ) -> None:
        sync_view_if_needed(executor, graph_model, step_plan, log_callback)


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
    """兼容入口：保持对外 API 不变。"""
    return AutomationStepRunner().run_step(
        executor,
        todo_item,
        graph_model,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
    )


