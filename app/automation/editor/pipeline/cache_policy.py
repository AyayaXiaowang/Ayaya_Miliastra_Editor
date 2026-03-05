# -*- coding: utf-8 -*-
"""
缓存失效策略（步骤前后）。

职责：
- 步骤前：根据步骤类型失效连续连线上下文等“可复用状态”；
- 步骤成功后：按计划失效视觉缓存/场景快照，确保后续识别不会误用旧画面。
"""

from app.automation.vision import invalidate_cache

from ..automation_step_types import GRAPH_STEP_CONNECT, GRAPH_STEP_CONNECT_MERGED
from .step_plans import StepExecutionPlan


EXECUTE_STEP_LOG_KEY = "app.automation.editor.EditorExecutor.execute_step"


def invalidate_before_step(executor, step_type: str) -> None:
    # 连线类步骤允许跨边复用链上下文（node_snapshots/screenshot 等），
    # 因此在 graph_connect / graph_connect_merged 进入前不主动失效。
    step_text = str(step_type or "")
    if step_text in (GRAPH_STEP_CONNECT, GRAPH_STEP_CONNECT_MERGED):
        return
    executor.invalidate_connect_chain_context("step type changed")


def invalidate_after_success(executor, step_type: str, step_plan: StepExecutionPlan) -> None:
    if bool(step_plan.invalidate_cache_on_success):
        invalidate_cache()

    if bool(getattr(step_plan, "mutates_layout", False)):
        # fast_chain_mode 下的连接步骤会复用同一帧 screenshot/节点检测结果；
        # 若此处强制失效场景快照，会导致执行线程的“零节点守卫/可见性检查”在每步重新做整屏识别，
        # 产生 1~2s 的额外停顿。连接步骤本身不依赖“连线后新快照”才能定位端口，因此可跳过失效。
        if bool(getattr(executor, "fast_chain_mode", False)) and str(step_type or "") in (
            GRAPH_STEP_CONNECT,
            GRAPH_STEP_CONNECT_MERGED,
        ):
            return
        invalidate_scene = getattr(executor, "invalidate_scene_snapshot", None)
        if callable(invalidate_scene):
            invalidate_scene(f"step:{step_type}")


