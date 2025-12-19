# -*- coding: utf-8 -*-
"""
dict_port_type_steps: 字典端口类型设置相关步骤。

封装通过 Dictionary 图标与“键/值”标签模板为端口设置字典键/值类型的完整流程，
供 `port_type_steps` 在输入/输出类型设置阶段复用。
"""

from __future__ import annotations

from typing import Optional, Tuple, Callable, Dict
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor import executor_utils as _exec_utils
from app.automation.editor.executor_protocol import EditorExecutorProtocol, AutomationStepContext
from app.automation.ports.port_type_inference import (
    is_generic_type_name,
    is_non_empty_str,
)
from app.automation.ports.port_type_ui_core import (
    apply_type_in_open_search_dialog,
    set_port_type_with_settings,
)
from app.automation.ports.settings_locator import find_icon_center_on_row


def _ensure_dict_icon_center(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    side: str,
    dict_icon_path,
    ports_list: list,
    ctx: AutomationStepContext,
) -> Tuple[Optional[Image.Image], int, int]:
    """确认并返回 Dictionary 图标在编辑器坐标系中的位置；必要时先将端口类型切换为“字典”。

    返回值：
        (最新截图, settings_x, settings_y)，若任一步骤失败则返回 (None, 0, 0)。
    """

    log_callback = ctx.log_callback
    visual_callback = ctx.visual_callback
    pause_hook = ctx.pause_hook
    allow_continue = ctx.allow_continue

    settings_x, settings_y = find_icon_center_on_row(
        executor,
        screenshot,
        node_bbox,
        port_center,
        side,
        str(dict_icon_path),
        y_tolerance=12,
        log_callback=log_callback,
    )

    if (settings_x, settings_y) != (0, 0):
        return screenshot, settings_x, settings_y

    executor.log(
        f"[端口类型/字典] 当前未发现 Dictionary 图标，尝试先通过 Settings 将端口 '{port_name}' 设置为'字典'",
        log_callback,
    )

    base_dict_type = "字典"
    base_set_ok = set_port_type_with_settings(
        executor,
        screenshot,
        node_bbox,
        port_center,
        port_name,
        base_dict_type,
        side,
        ports_list,
        ctx,
    )
    if not base_set_ok:
        executor.log(
            f"[端口类型/字典] 通过 Settings 将端口 '{port_name}' 设置为'字典'失败，放弃字典键/值类型配置",
            log_callback,
        )
        return None, 0, 0

    refreshed = editor_capture.capture_window(executor.window_title)
    if not refreshed:
        executor.log(
            "[端口类型/字典] 重新截图失败，无法在切换为字典后定位 Dictionary 图标",
            log_callback,
        )
        return None, 0, 0

    screenshot = refreshed
    settings_x, settings_y = find_icon_center_on_row(
        executor,
        screenshot,
        node_bbox,
        port_center,
        side,
        str(dict_icon_path),
        y_tolerance=12,
        log_callback=log_callback,
    )
    if (settings_x, settings_y) == (0, 0):
        executor.log(
            f"[端口类型/字典] 已将端口 '{port_name}' 设置为'字典'，但仍未发现 Dictionary 图标，放弃字典键/值类型配置",
            log_callback,
        )
        return None, 0, 0

    return screenshot, settings_x, settings_y


def _open_dict_dialog(
    executor: EditorExecutorProtocol,
    settings_x: int,
    settings_y: int,
    ctx: AutomationStepContext,
) -> None:
    """点击 Dictionary 图标并等待字典设置对话框稳定出现。"""
    log_callback = ctx.log_callback
    pause_hook = ctx.pause_hook
    allow_continue = ctx.allow_continue

    screen_x, screen_y = executor.convert_editor_to_screen_coords(settings_x, settings_y)
    executor.log(
        f"[端口类型/字典] 点击设置按钮: editor=({settings_x},{settings_y}) screen=({screen_x},{screen_y})",
        log_callback,
    )
    _exec_utils.click_and_verify(
        executor,
        screen_x,
        screen_y,
        "[端口类型/字典] 点击设置按钮",
        log_callback,
    )
    _exec_utils.log_wait_if_needed(
        executor,
        0.5,
        "等待 0.50 秒（打开字典设置）",
        log_callback,
        pause_hook,
        allow_continue,
    )


def _apply_key_value_types(
    executor: EditorExecutorProtocol,
    templates_root,
    key_type: str,
    value_type: str,
    ctx: AutomationStepContext,
) -> Tuple[bool, bool]:
    """在已打开的字典设置对话框中，为“键/值”两侧应用目标类型。

    返回值：
        (key_ok, value_ok)
    """
    log_callback = ctx.log_callback
    visual_callback = ctx.visual_callback
    pause_hook = ctx.pause_hook
    allow_continue = ctx.allow_continue

    key_template_path = templates_root / "jian.png"
    value_template_path = templates_root / "zhi.png"

    dialog_screenshot = editor_capture.capture_window(executor.window_title)
    if not dialog_screenshot:
        executor.log("[端口类型/字典] 重新截图失败，无法匹配字典键/值标签", log_callback)
        return False, False

    template_hit_cache: Dict[str, Optional[Tuple[int, int, int, int, float]]] = {}

    def _get_cached_template_hit(template_path) -> Optional[Tuple[int, int, int, int, float]]:
        cache_key = str(template_path)
        if cache_key not in template_hit_cache:
            template_hit_cache[cache_key] = editor_capture.match_template(dialog_screenshot, str(template_path))
        return template_hit_cache[cache_key]

    def _click_label_and_choose_type(
        label: str,
        template_path,
        target_type: str,
    ) -> bool:
        if not is_non_empty_str(target_type):
            executor.log(f"[端口类型/字典] {label}类型目标为空，跳过此侧", log_callback)
            return False
        if is_generic_type_name(target_type):
            executor.log(
                f"[端口类型/字典] {label}类型计算为泛型 '{target_type}'，出于安全跳过设置",
                log_callback,
            )
            return False

        hit = _get_cached_template_hit(template_path)
        if hit is None:
            executor.log(
                f"[端口类型/字典] 当前画面未找到{label}标签模板: {template_path}",
                log_callback,
            )
            return False
        hit_left, hit_top, hit_w, hit_h, _ = hit
        label_editor_x = int(hit_left + hit_w // 2)
        label_editor_y = int(hit_top + hit_h // 2)
        label_screen_x, label_screen_y = executor.convert_editor_to_screen_coords(label_editor_x, label_editor_y)
        executor.log(
            f"[端口类型/字典] 点击{label}标签: editor=({label_editor_x},{label_editor_y}) "
            f"screen=({label_screen_x},{label_screen_y})",
            log_callback,
        )
        _exec_utils.click_and_verify(
            executor,
            label_screen_x,
            label_screen_y,
            f"[端口类型/字典] 点击{label}标签",
            log_callback,
        )
        _exec_utils.log_wait_if_needed(
            executor,
            0.3,
            f"等待 0.30 秒（{label}类型搜索框弹出）",
            log_callback,
            pause_hook,
            allow_continue,
        )

        apply_type_in_open_search_dialog(
            executor,
            target_type,
            log_prefix=f"[端口类型/字典] 为{label}",
            ctx=ctx,
            wait_seconds=0.5,
            wait_message=f"等待 0.50 秒（{label}类型选择应用）",
        )
        return True

    key_ok = _click_label_and_choose_type("键", key_template_path, key_type)
    value_ok = _click_label_and_choose_type("值", value_template_path, value_type)
    return key_ok, value_ok


def _close_dict_dialog_with_blank_click_if_needed(
    executor: EditorExecutorProtocol,
    port_center: Tuple[int, int],
    key_ok: bool,
    value_ok: bool,
    ctx: AutomationStepContext,
) -> None:
    """键和值两侧都设置成功时，点击画布空白位置关闭字典设置对话框。"""
    if not (key_ok and value_ok):
        return

    blank_start_editor_x, blank_start_editor_y = int(port_center[0]), int(port_center[1])
    blank_start_screen_x, blank_start_screen_y = executor.convert_editor_to_screen_coords(
        blank_start_editor_x,
        blank_start_editor_y,
    )
    _exec_utils.click_canvas_blank_near_screen_point(
        executor,
        int(blank_start_screen_x),
        int(blank_start_screen_y),
        log_prefix="[端口类型/字典] 键/值类型设置完成，",
        wait_seconds=0.3,
        wait_message="等待 0.30 秒（字典设置完成后画布状态稳定）",
        log_callback=ctx.log_callback,
        visual_callback=ctx.visual_callback,
        pause_hook=ctx.pause_hook,
        allow_continue=ctx.allow_continue,
    )


def set_dict_port_type_with_settings(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    key_type: str,
    value_type: str,
    side: str,
    ports_list: list,
    ctx: AutomationStepContext,
) -> bool:
    """通过 Settings / Dictionary 图标为“字典”端口分别设置键/值类型。"""
    template_profile_value = getattr(executor, "ocr_template_profile", None)
    template_profile = str(template_profile_value or "4K-CN")
    templates_root = executor.workspace_path / "assets" / "ocr_templates" / template_profile
    node_templates_root = templates_root / "Node"
    dict_icon_path = node_templates_root / "Dictionary.png"

    screenshot_new, settings_x, settings_y = _ensure_dict_icon_center(
        executor=executor,
        screenshot=screenshot,
        node_bbox=node_bbox,
        port_center=port_center,
        port_name=port_name,
        side=side,
        dict_icon_path=dict_icon_path,
        ports_list=ports_list,
        ctx=ctx,
    )
    if screenshot_new is None or (settings_x, settings_y) == (0, 0):
        return False

    screenshot = screenshot_new
    executor.log(
        f"[端口类型/字典] 使用 Dictionary 图标定位设置入口: editor=({settings_x},{settings_y}) path='{dict_icon_path}'",
        ctx.log_callback,
    )

    _open_dict_dialog(
        executor=executor,
        settings_x=settings_x,
        settings_y=settings_y,
        ctx=ctx,
    )

    key_ok, value_ok = _apply_key_value_types(
        executor=executor,
        templates_root=templates_root,
        key_type=key_type,
        value_type=value_type,
        ctx=ctx,
    )

    _close_dict_dialog_with_blank_click_if_needed(
        executor=executor,
        port_center=port_center,
        key_ok=key_ok,
        value_ok=value_ok,
        ctx=ctx,
    )

    return bool(key_ok or value_ok)


