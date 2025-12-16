from __future__ import annotations

"""
port_type_ui_core: 端口类型设置相关的基础 UI 操作集合。

职责：
- 在已打开的类型搜索框中，根据目标类型完成文本搜索与选中；
- 在给定节点截图与端口列表的前提下，通过 Settings 按钮打开类型搜索框，
  并复用统一的等待与日志策略；
- 为上层的 `port_type_ui_steps` 与 `dict_port_type_steps` 提供稳定的 UI 原语，
  避免在高层步骤模块之间直接互相引用导致循环依赖。

注意：
- 本模块仅关注“点击/等待/日志”层面的 UI 细节，不参与类型推断或端口遍历；
- 调用方负责在合适的时机提供截图、端口列表与目标类型文本；
- 所有等待均统一委托 `_exec_utils.log_wait_if_needed`，以兼容 fast_chain_mode 与暂停/终止钩子。
"""

from typing import Callable, Optional, Tuple

from PIL import Image

from app.automation.editor import editor_nodes
from app.automation.editor import executor_utils as _exec_utils
from app.automation.editor.executor_protocol import (
    EditorExecutorProtocol,
    EditorExecutorWithViewport,
    AutomationStepContext,
)
from app.automation.ports.port_picker import pick_settings_center_by_recognition
from app.automation.ports.port_type_inference import (
    is_generic_type_name,
    is_non_empty_str,
)
from app.automation.ports.settings_locator import find_icon_center_on_row


def apply_type_in_open_search_dialog(
    executor: EditorExecutorProtocol,
    target_type: str,
    log_prefix: str,
    ctx: AutomationStepContext,
    *,
    wait_seconds: float = 0.5,
    wait_message: Optional[str] = None,
) -> None:
    """在已弹出的类型搜索框中选择目标类型并等待应用完成。

    该 helper 仅负责“在已打开的类型搜索框内完成文本搜索与选择”的通用流程，
    不负责点击 Settings/Dictionary 图标或键/值标签本身。
    """
    if not is_non_empty_str(target_type):
        return

    wait_value = float(wait_seconds)
    if wait_value < 0:
        wait_value = 0.0

    effective_wait_message = wait_message or f"等待 {wait_value:.2f} 秒"

    log_callback = ctx.log_callback
    visual_callback = ctx.visual_callback
    pause_hook = ctx.pause_hook
    allow_continue = ctx.allow_continue

    executor.log(f"{log_prefix} 设置类型: '{target_type}'", log_callback)
    editor_nodes.click_type_search_and_choose(
        executor,
        target_type,
        log_callback,
        visual_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
    )
    _exec_utils.log_wait_if_needed(
        executor,
        wait_value,
        effective_wait_message,
        log_callback,
        pause_hook,
        allow_continue,
    )


def set_port_type_with_settings(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    target_type: str,
    side: str,
    ports_list: list,
    ctx: AutomationStepContext,
) -> bool:
    """通过 Settings 按钮设置端口类型。

    优先使用识别到的 Settings 行，失败则回退到模板搜索。
    """
    log_callback = ctx.log_callback
    visual_callback = ctx.visual_callback
    pause_hook = ctx.pause_hook
    allow_continue = ctx.allow_continue

    # 优先使用识别到的 Settings 行
    settings_x, settings_y = pick_settings_center_by_recognition(
        executor,
        screenshot,
        node_bbox,
        int(port_center[1]),
        y_tolerance=14,
        desired_side=side,
        ports_list=ports_list,
    )

    if (settings_x, settings_y) == (0, 0):
        # 回退到模板搜索
        settings_x, settings_y = find_icon_center_on_row(
            executor,
            screenshot,
            node_bbox,
            port_center,
            side,
            str(executor.node_settings_template_path),
            y_tolerance=12,
            log_callback=log_callback,
        )
        if (settings_x, settings_y) == (0, 0):
            executor.log(f"[端口类型/{side}] 未发现设置按钮，跳过端口 '{port_name}'", log_callback)
            return False

    # 点击 Settings 按钮
    screen_x, screen_y = executor.convert_editor_to_screen_coords(settings_x, settings_y)
    executor.log(
        f"[端口类型/{side}] 点击设置按钮: editor=({settings_x},{settings_y}) "
        f"screen=({screen_x},{screen_y})",
        log_callback,
    )
    _exec_utils.click_and_verify(
        executor,
        screen_x,
        screen_y,
        f"[端口类型/{side}] 点击设置按钮",
        log_callback,
    )

    _exec_utils.log_wait_if_needed(
        executor,
        0.5,
        "等待 0.50 秒",
        log_callback,
        pause_hook,
        allow_continue,
    )

    # 硬性防护：禁止将端口类型设置为"泛型家族"
    if is_generic_type_name(target_type):
        executor.log(
            f"[端口类型/{side}] 计算得到泛型类型 '{target_type}'，出于安全跳过设置（永不将类型设置为泛型）",
            log_callback,
        )
        return False

    # 设置类型（复用通用 helper，保持统一的等待与日志策略）
    apply_type_in_open_search_dialog(
        executor,
        target_type,
        log_prefix=f"[端口类型/{side}]",
        ctx=ctx,
        wait_seconds=0.5,
        wait_message="等待 0.50 秒",
    )

    return True


__all__ = [
    "apply_type_in_open_search_dialog",
    "set_port_type_with_settings",
]


