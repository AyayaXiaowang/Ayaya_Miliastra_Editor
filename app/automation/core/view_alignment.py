from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

from PIL import Image


@dataclass(frozen=True)
class PanEvaluation:
    """表示单次视口对齐评估的结果。"""

    satisfied: bool
    drag_args: Optional[Any] = None
    aborted: bool = False


@dataclass(frozen=True)
class PanLoopOutcome:
    """表示整个视口对齐循环的执行结果。"""

    success: bool
    aborted: bool
    last_image: Optional[Image.Image]


CaptureFn = Callable[[], Image.Image]
EvaluateFn = Callable[[Image.Image, int], PanEvaluation]
ExecuteDragFn = Callable[[Image.Image, Any], Image.Image]


def run_pan_loop(
    capture_fn: CaptureFn,
    evaluate_fn: EvaluateFn,
    execute_drag_fn: ExecuteDragFn,
    *,
    max_steps: int,
) -> PanLoopOutcome:
    """统一的视口平移循环。

    Args:
        capture_fn: 获取当前截图。
        evaluate_fn: 根据截图判断是否满足条件，或返回下一次拖拽所需参数。
        execute_drag_fn: 执行拖拽并返回拖拽后的截图。
        max_steps: 最大迭代次数。

    Returns:
        PanLoopOutcome: success 表示目标已满足；aborted 表示外层请求终止。
    """

    screenshot = capture_fn()
    last_image: Optional[Image.Image] = screenshot

    for step_index in range(max_steps):
        if last_image is None:
            break
        evaluation = evaluate_fn(last_image, step_index)
        if evaluation.aborted:
            return PanLoopOutcome(success=False, aborted=True, last_image=last_image)
        if evaluation.satisfied:
            return PanLoopOutcome(success=True, aborted=False, last_image=last_image)
        if evaluation.drag_args is None:
            break
        last_image = execute_drag_fn(last_image, evaluation.drag_args)

    return PanLoopOutcome(success=False, aborted=False, last_image=last_image)


