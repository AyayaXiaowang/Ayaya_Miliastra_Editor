# -*- coding: utf-8 -*-
"""
dict_port_type_steps: 字典端口类型设置相关步骤。

封装通过 Dictionary 图标与“键/值”标签模板为端口设置字典键/值类型的完整流程，
供 `port_type_steps` 在输入/输出类型设置阶段复用。
"""

from __future__ import annotations

from typing import Optional, Tuple, Callable
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core import executor_utils as _exec_utils
from app.automation.core import editor_nodes
from app.automation.core.executor_protocol import EditorExecutorProtocol
from app.automation.input.common import sleep_seconds
from app.automation.ports.port_type_inference import is_generic_type_name
from app.automation.ports.settings_locator import find_icon_center_on_row


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
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
) -> bool:
    """通过 Settings / Dictionary 图标为“字典”端口分别设置键/值类型。

    步骤：
    1. 优先尝试直接点击 Dictionary 图标进入字典设置区域；
    2. 若当前端口仍为通用 Settings 形式，则先通过通用类型设置流程将其类型切换为“字典”，
       再次截图并重新查找 Dictionary 图标；
    3. 在字典设置区域内，分别匹配“键”与“值”标签模板并弹出类型搜索框，为两侧设置类型。
    """
    # 避免循环依赖：在函数内部按需导入通用 Settings 流程
    from app.automation.ports import port_type_steps as _port_type_steps

    templates_root = executor.workspace_path / "assets" / "ocr_templates" / "4K-CN"
    node_templates_root = templates_root / "Node"
    dict_icon_path = node_templates_root / "Dictionary.png"

    settings_x: int = 0
    settings_y: int = 0

    # 1) 首选：直接通过 Dictionary 图标定位设置入口（端口已经是字典类型）
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
        # 2) 回退：端口当前仍为通用 Settings 形式时，先将其类型设置为“字典”
        executor._log(
            f"[端口类型/字典] 当前未发现 Dictionary 图标，尝试先通过 Settings 将端口 '{port_name}' 设置为'字典'",
            log_callback,
        )

        base_dict_type = "字典"
        base_set_ok = _port_type_steps.set_port_type_with_settings(
            executor,
            screenshot,
            node_bbox,
            port_center,
            port_name,
            base_dict_type,
            side,
            ports_list,
            log_callback,
            visual_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
        )
        if not base_set_ok:
            executor._log(
                f"[端口类型/字典] 通过 Settings 将端口 '{port_name}' 设置为'字典'失败，放弃字典键/值类型配置",
                log_callback,
            )
            return False

        refreshed = editor_capture.capture_window(executor.window_title)
        if not refreshed:
            executor._log(
                "[端口类型/字典] 重新截图失败，无法在切换为字典后定位 Dictionary 图标",
                log_callback,
            )
            return False
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
            executor._log(
                f"[端口类型/字典] 已将端口 '{port_name}' 设置为'字典'，但仍未发现 Dictionary 图标，放弃字典键/值类型配置",
                log_callback,
            )
            return False

    executor._log(
        f"[端口类型/字典] 使用 Dictionary 图标定位设置入口: editor=({settings_x},{settings_y}) path='{dict_icon_path}'",
        log_callback,
    )

    screen_x, screen_y = executor.convert_editor_to_screen_coords(settings_x, settings_y)
    executor._log(
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
    # 该等待不受 fast_chain_mode 影响，始终等待 0.5 秒，以确保字典设置弹窗稳定出现。
    executor._log("等待 0.50 秒（打开字典设置）", log_callback)
    sleep_seconds(0.5)

    key_template_path = templates_root / "jian.png"
    value_template_path = templates_root / "zhi.png"

    def _click_label_and_choose_type(
        label: str,
        template_path,
        target_type: str,
    ) -> bool:
        if not isinstance(target_type, str) or target_type.strip() == "":
            executor._log(f"[端口类型/字典] {label}类型目标为空，跳过此侧", log_callback)
            return False
        if is_generic_type_name(target_type):
            executor._log(
                f"[端口类型/字典] {label}类型计算为泛型 '{target_type}'，出于安全跳过设置",
                log_callback,
            )
            return False

        dialog_screenshot = editor_capture.capture_window(executor.window_title)
        if not dialog_screenshot:
            executor._log("[端口类型/字典] 重新截图失败，无法匹配字典键/值标签", log_callback)
            return False

        hit = editor_capture.match_template(dialog_screenshot, str(template_path))
        if hit is None:
            executor._log(
                f"[端口类型/字典] 当前画面未找到{label}标签模板: {template_path}",
                log_callback,
            )
            return False
        hit_left, hit_top, hit_w, hit_h, _ = hit
        label_editor_x = int(hit_left + hit_w // 2)
        label_editor_y = int(hit_top + hit_h // 2)
        label_screen_x, label_screen_y = executor.convert_editor_to_screen_coords(label_editor_x, label_editor_y)
        executor._log(
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

        executor._log(f"[端口类型/字典] 为{label}设置类型: '{target_type}'", log_callback)
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
            0.5,
            f"等待 0.50 秒（{label}类型选择应用）",
            log_callback,
            pause_hook,
            allow_continue,
        )
        return True

    key_ok = _click_label_and_choose_type("键", key_template_path, key_type)
    value_ok = _click_label_and_choose_type("值", value_template_path, value_type)

    # 若键和值两侧的类型都已成功设置，则在继续后续步骤前，点击一次画布空白位置，
    # 以关闭字典设置对话框并让节点图回到稳定状态。空白点查找复用拖拽/右键逻辑中
    # 的画布吸附工具，避免在已有节点上误点。
    if key_ok and value_ok:
        # 以端口中心附近作为初始位置，在画布区域内寻找安全空白点。
        blank_start_editor_x, blank_start_editor_y = int(port_center[0]), int(port_center[1])
        blank_start_screen_x, blank_start_screen_y = executor.convert_editor_to_screen_coords(
            blank_start_editor_x,
            blank_start_editor_y,
        )
        snapped_blank = _exec_utils.snap_screen_point_to_canvas_background(
            executor,
            int(blank_start_screen_x),
            int(blank_start_screen_y),
            log_callback=log_callback,
            visual_callback=visual_callback,
        )
        if snapped_blank is not None:
            blank_screen_x, blank_screen_y = int(snapped_blank[0]), int(snapped_blank[1])
            executor._log(
                "[端口类型/字典] 键/值类型设置完成，点击画布空白位置以结束字典配置",
                log_callback,
            )
            _exec_utils.click_and_verify(
                executor,
                blank_screen_x,
                blank_screen_y,
                "[端口类型/字典] 键/值设置完成后点击空白处",
                log_callback,
            )
            _exec_utils.log_wait_if_needed(
                executor,
                0.3,
                "等待 0.30 秒（字典设置完成后画布状态稳定）",
                log_callback,
                pause_hook,
                allow_continue,
            )

    return bool(key_ok or value_ok)


