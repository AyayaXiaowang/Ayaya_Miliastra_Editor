# -*- coding: utf-8 -*-
"""
config_node_steps: 参数配置步骤拆分
将 execute_config_node_merged 的庞大逻辑拆分为可测试的小步骤。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Callable, List
from PIL import Image

from app.automation.editor.executor_protocol import (
    EditorExecutorProtocol,
    EditorExecutorWithViewport,
    AutomationStepContext,
)
from app.automation import capture as editor_capture
from app.automation.editor import executor_utils as _exec_utils
from app.automation.ports._ports import is_data_input_port, is_flow_output_port
from app.automation.ports.port_picker import pick_port_center_for_node
from app.automation.input.common import build_graph_region_overlay, sleep_seconds
from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import NodeModel
from app.automation.vision import list_ports as list_ports_for_bbox
from app.automation.vision.ocr_utils import (
    normalize_ocr_bbox,
    get_bbox_center,
    fingerprint_region,
)

from app.automation.config.config_params_helpers import (
    compute_port_ordinal_in_model,
    filter_screen_input_candidates,
    format_candidates_brief,
    pick_unused_port_center,
    check_center_used,
)
from app.automation.ports.vector3_input_handler import (
    input_vector3_by_ocr,
    input_vector3_by_geometry,
)
from app.automation.editor.visualization_helpers import emit_node_and_port_overlays
from .enum_dropdown_utils import (
    normalize_dropdown_option_text,
    infer_order_based_click_index,
    infer_missing_option_center_y_by_order,
)


def visualize_node_and_ports(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    node_title: str,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]]
) -> None:
    """可视化：显示节点图区域、所有节点和当前节点的端口。"""
    emit_node_and_port_overlays(
        executor,
        screenshot,
        node_bbox,
        visual_callback,
        port_label_mode="normalized",
    )


def log_port_candidates_debug(
    executor: EditorExecutorProtocol,
    node: NodeModel,
    param_name: str,
    expected_kind: str,
    log_callback: Optional[Callable[[str], None]]
) -> None:
    """日志输出：模型端口顺序与屏幕候选（用于调试序号映射）。"""
    from engine.utils.graph.graph_utils import is_flow_port_name
    
    # 模型端口顺序
    model_inputs_seq = [(p.name, ("flow" if is_flow_port_name(p.name) else "data")) for p in (node.inputs or [])]
    executor.log(
        "[序号] 模型端口顺序(输入): "
        + ", ".join([f"{i}:{n}[{k}]" for i, (n, k) in enumerate(model_inputs_seq)]),
        log_callback,
    )


def locate_input_port(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node: NodeModel,
    node_bbox: Tuple[int, int, int, int],
    param_name: str,
    expected_kind: str,
    used_centers: List[Tuple[int, int]],
    log_callback: Optional[Callable[[str], None]],
    ports_snapshot: Optional[list] = None,
) -> Optional[Tuple[int, int]]:
    """定位输入端口中心，避免重复使用已配置过的端口。
    
    Returns:
        端口中心坐标 (x, y)，失败返回None
    """
    # 计算计划序号
    planned_ordinal = compute_port_ordinal_in_model(node, param_name, expected_kind)
    
    # 获取屏幕候选并输出调试日志
    if ports_snapshot is not None:
        ports_all_debug = ports_snapshot
    else:
        list_ports_func = globals().get("list_ports_for_bbox")
        if list_ports_func is None:
            executor.log("✗ 未提供端口识别函数 list_ports_for_bbox，无法定位输入端口", log_callback)
            return None
        ports_all_debug = list_ports_func(screenshot, node_bbox)
    screen_candidates = filter_screen_input_candidates(ports_all_debug, expected_kind)

    executor.log(f"[序号] 屏幕候选(输入-从上到下): {format_candidates_brief(screen_candidates)}", log_callback)
    executor.log(
        f"[序号] 计划序号(输入): {str(planned_ordinal) if planned_ordinal is not None else 'None'} 对应端口='{param_name}'",
        log_callback,
    )
    
    # 定位端口中心
    port_center = pick_port_center_for_node(
        executor,
        screenshot,
        node_bbox,
        param_name,
        want_output=False,
        expected_kind=expected_kind,
        log_callback=log_callback,
        ordinal_fallback_index=planned_ordinal,
        ports_list=ports_all_debug,
        list_ports_for_bbox_func=list_ports_for_bbox,
    )
    
    if port_center == (0, 0):
        executor.log(f"✗ 未能定位端口: {param_name}", log_callback)
        return None
    
    # 若定位到的端口中心已被使用，则改用未使用的下一个候选
    if check_center_used(port_center, used_centers):
        alt = pick_unused_port_center(screen_candidates, planned_ordinal, used_centers)
        if isinstance(alt, tuple) and len(alt) == 2:
            executor.log(
                f"[参数配置] 端口中心已使用，改用未使用候选 center(editor)=({int(alt[0])},{int(alt[1])})",
                log_callback,
            )
            port_center = (int(alt[0]), int(alt[1]))

    executor.log(
        f"[参数配置] 端口 '{param_name}' 定位 center(editor)=({int(port_center[0])},{int(port_center[1])})",
        log_callback,
    )

    return port_center


def _find_warning_region_generic(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    log_callback: Optional[Callable[[str], None]],
    *,
    log_prefix: str,
    port_selector,
    search_side: str,
    no_ports_msg: Optional[str],
    missing_current_msg: str,
    ports_snapshot: Optional[List[Any]] = None,
) -> Optional[Tuple[Tuple[int, int, int, int], Any, Any]]:
    if ports_snapshot is not None:
        ports_all = list(ports_snapshot)
    else:
        list_ports_func = globals().get("list_ports_for_bbox")
        if list_ports_func is None:
            executor.log(f"{log_prefix} ✗ 未提供端口识别函数 list_ports_for_bbox，无法计算 Warning 区域", log_callback)
            return None
        ports_all = list_ports_func(screenshot, node_bbox)
    ports_filtered = [p for p in ports_all if port_selector(p)]
    if len(ports_filtered) == 0:
        if no_ports_msg:
            executor.log(no_ports_msg, log_callback)
        return None

    current_center_y = int(port_center[1])
    current_port = None
    if port_name:
        named = [p for p in ports_filtered if str(getattr(p, 'name_cn', '') or '') == port_name]
        if len(named) > 0:
            current_port = named[0]
    if current_port is None and len(ports_filtered) > 0:
        current_port = sorted(ports_filtered, key=lambda p: abs(int(getattr(p, 'center', (0, 0))[1]) - current_center_y))[0]

    if current_port is None:
        executor.log(missing_current_msg, log_callback)
        return None

    current_top_y = int(current_port.bbox[1])
    next_ports = sorted(
        [p for p in ports_filtered if int(p.bbox[1]) > current_top_y],
        key=lambda p: int(p.bbox[1]),
    )
    next_port = next_ports[0] if len(next_ports) > 0 else None

    node_left = int(node_bbox[0])
    node_top = int(node_bbox[1])
    node_right = int(node_bbox[0] + node_bbox[2])
    node_bottom = int(node_bbox[1] + node_bbox[3])

    if search_side == "right":
        search_left = int(port_center[0])
        search_right = node_right - 4
    else:
        search_left = node_left + 4
        search_right = max(node_left + 5, int(port_center[0] - 6))

    center_y = int(port_center[1])
    v_top = max(node_top, center_y - 18)
    v_bottom = min(node_bottom, center_y + 18)

    if search_right <= search_left or v_bottom <= v_top:
        executor.log(f"{log_prefix} ✗ Warning 搜索区域非法", log_callback)
        return None

    search_region = (
        int(search_left),
        int(v_top),
        int(search_right - search_left),
        int(v_bottom - v_top),
    )
    executor.log(
        f"{log_prefix} Warning 模板搜索区域 editor=({search_region[0]},{search_region[1]},{search_region[2]},{search_region[3]})",
        log_callback,
    )

    current_name = str(getattr(current_port, 'name_cn', '') or '')
    current_index = str(getattr(current_port, 'index', ''))
    current_bbox = tuple(int(v) for v in getattr(current_port, 'bbox', (0, 0, 0, 0)))
    if next_port is not None:
        next_name = str(getattr(next_port, 'name_cn', '') or '')
        next_index = str(getattr(next_port, 'index', ''))
        next_bbox = tuple(int(v) for v in getattr(next_port, 'bbox', (0, 0, 0, 0)))
        executor.log(
            f"{log_prefix} 基准端口: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → 下一(name='{next_name}', index={next_index}, bbox={next_bbox})",
            log_callback,
        )
    else:
        executor.log(
            f"{log_prefix} 基准端口: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → 下一(None, 使用节点底部={int(node_bottom)})",
            log_callback,
        )
    return (search_region, current_port, next_port)


def handle_boolean_param(
    executor: EditorExecutorWithViewport,
    port_center: Tuple[int, int],
    param_name: str,
    param_value: str,
    log_callback: Optional[Callable[[str], None]]
) -> bool:
    """处理布尔参数（统一执行两次点击，根据目标值调整第二次点击位置）。

    Returns:
        是否需要继续后续处理（布尔处理完毕后返回 False 表示跳过后续 Warning / 普通参数流程）
    """
    is_param_value_yes = param_value == "是"
    if is_param_value_yes:
        executor.log(f"· 布尔『{param_name}』=是，执行两次点击设置为“是”", log_callback)
    else:
        executor.log(f"· 布尔『{param_name}』≠是，执行两次点击设置为“否”", log_callback)

    port_x, port_y = int(port_center[0]), int(port_center[1])
    
    # 点击第一次
    click1_x, click1_y = executor.convert_editor_to_screen_coords(port_x + 50, port_y + 25)
    executor.log(f"[参数配置/布尔] 点击#1 偏移(+50,+25) screen=({click1_x},{click1_y})", log_callback)
    _exec_utils.click_and_verify(executor, click1_x, click1_y, "[参数配置/布尔] 点击#1", log_callback)

    # 无论是否处于快速链模式，布尔参数两次点击之间都固定等待 0.5 秒
    executor.log("等待 0.50 秒（布尔参数固定节奏）", log_callback)
    sleep_seconds(0.5)

    # 点击第二次
    second_click_offset_y = 65 if is_param_value_yes else 45
    click2_x, click2_y = executor.convert_editor_to_screen_coords(port_x + 50, port_y + second_click_offset_y)
    executor.log(
        f"[参数配置/布尔] 点击#2 偏移(+50,+{second_click_offset_y}) screen=({click2_x},{click2_y})",
        log_callback,
    )
    _exec_utils.click_and_verify(executor, click2_x, click2_y, "[参数配置/布尔] 点击#2", log_callback)
    
    return False  # 布尔处理完毕，跳过后续


def find_warning_region_for_port(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    param_name: str,
    log_callback: Optional[Callable[[str], None]],
    *,
    ports_snapshot: Optional[List[Any]] = None,
) -> Optional[Tuple[Tuple[int, int, int, int], Any, Any]]:
    return _find_warning_region_generic(
        executor,
        screenshot,
        node_bbox,
        port_center,
        param_name,
        log_callback,
        log_prefix="[参数配置/非布尔]",
        port_selector=is_data_input_port,
        search_side="right",
        no_ports_msg=None,
        missing_current_msg="[参数配置/非布尔] ✗ 未在识别结果中找到当前输入端口",
        ports_snapshot=ports_snapshot,
    )


def find_warning_region_for_flow_output(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    log_callback: Optional[Callable[[str], None]],
    *,
    ports_snapshot: Optional[List[Any]] = None,
    log_prefix: str = "[分支配置]",
) -> Optional[Tuple[Tuple[int, int, int, int], Any, Any]]:
    return _find_warning_region_generic(
        executor,
        screenshot,
        node_bbox,
        port_center,
        port_name,
        log_callback,
        log_prefix=log_prefix,
        port_selector=is_flow_output_port,
        search_side="left",
        no_ports_msg=f"{log_prefix} ✗ 未识别到流程输出端口",
        missing_current_msg=f"{log_prefix} ✗ 未在识别结果中找到当前输出端口",
        ports_snapshot=ports_snapshot,
    )


def handle_regular_param_with_warning(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    search_region: Optional[Tuple[int, int, int, int]],
    param_value: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    *,
    log_prefix: str = "[参数配置/非布尔]",
) -> bool:
    """处理普通参数：先找Warning模板，点击后输入值。
    
    Returns:
        成功返回True
    """
    if search_region is None:
        executor.log(f"{log_prefix} 未计算到 Warning 搜索区域：跳过 Warning 尝试，交由调用方走 fallback", log_callback)
        return False

    search_left, search_top, search_width, search_height = search_region
    
    # 可视化：Warning搜索区域
    if visual_callback is not None:
        rects = [{
            'bbox': (search_left, search_top, search_width, search_height),
            'color': (255, 160, 0),
            'label': 'Warning 搜索区域'
        }]
        visual_callback(screenshot, {'rects': rects})
    
    # 模板匹配
    warning_match = editor_capture.match_template(
        screenshot,
        str(executor.node_warning_template_path),
        search_region=search_region
    )
    
    if not warning_match:
        return False  # 未命中，由调用方处理fallback
    
    match_x, match_y, match_w, match_h, conf = warning_match
    warning_x = int(match_x + match_w // 2)
    warning_y = int(match_y + match_h // 2)
    
    screen_x, screen_y = executor.convert_editor_to_screen_coords(warning_x, warning_y)

    executor.log(
        f"{log_prefix} 点击 Warning: editor=({warning_x},{warning_y}) screen=({screen_x},{screen_y}) 模板='Warning.png' 命中bbox=({match_x},{match_y},{match_w},{match_h}) conf={conf:.2f}",
        log_callback,
    )
    
    # 可视化：Warning命中框和点击位置
    if visual_callback is not None:
        rects = [{
            'bbox': (match_x, match_y, match_w, match_h),
            'color': (255, 80, 80),
            'label': f"Warning 命中 {conf:.2f}"
        }]
        circles = [{
            'center': (warning_x, warning_y),
            'radius': 6,
            'color': (0, 220, 0),
            'label': '点击'
        }]
        visual_callback(screenshot, {'rects': rects, 'circles': circles})
    
    _exec_utils.click_and_verify(executor, screen_x, screen_y, f"{log_prefix} 点击 Warning", log_callback)
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    executor.log(f"{log_prefix} 注入参数值: '{param_value}' (len={len(param_value)})", log_callback)
    if not executor.input_text_with_hooks(param_value, pause_hook, allow_continue, log_callback):
        return False
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
    
    return True


def handle_enum_param(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    search_region: Optional[Tuple[int, int, int, int]],
    enum_index: int,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    *,
    log_prefix: str = "[参数配置/枚举]",
    enum_options: Optional[List[str]] = None,
    desired_text: str = "",
    open_click_editor: Optional[Tuple[int, int]] = None,
) -> bool:
    """
    处理枚举/布尔参数：
    1) 基于 Warning 模板定位下拉触发区域并点击展开；
    2) 识别下拉矩形（背景色 D7D7D7）；
    3) OCR 识别选项文本并点击目标文本；
    4) 若目标未出现在当前视图，则在下拉区域内滚动滚轮后重试（每滚动两格截图一次），并自动判断是否滚动到头。

    enum_index:
        从 1 开始的枚举项序号（1 表示第一个选项）。
    """
    match_w = 0
    match_h = 0

    # 1) 打开下拉：优先使用调用方提供的点击点（通常基于端口中心偏移），否则回退到 Warning 模板定位
    if open_click_editor is not None:
        first_click_editor_x = int(open_click_editor[0])
        first_click_editor_y = int(open_click_editor[1])
        executor.log(
            f"{log_prefix} 使用端口偏移点击展开 editor=({first_click_editor_x},{first_click_editor_y})",
            log_callback,
        )
    else:
        if search_region is None:
            executor.log(f"{log_prefix} ✗ 缺少 search_region 且未提供 open_click_editor", log_callback)
            return False

        search_left, search_top, search_width, search_height = search_region
        if visual_callback is not None:
            rects = [{
                'bbox': (search_left, search_top, search_width, search_height),
                'color': (255, 180, 0),
                'label': '枚举 Warning 搜索区域',
            }]
            visual_callback(screenshot, {'rects': rects})

        warning_match = editor_capture.match_template(
            screenshot,
            str(executor.node_warning_template_path),
            search_region=search_region,
        )

        if not warning_match:
            return False

        match_x, match_y, match_w, match_h, conf = warning_match
        warning_center_x = int(match_x + match_w // 2)
        warning_center_y = int(match_y + match_h // 2)

        executor.log(
            f"{log_prefix} 命中 Warning: editor=({warning_center_x},{warning_center_y}) "
            f"bbox=({match_x},{match_y},{match_w},{match_h}) conf={conf:.2f}",
            log_callback,
        )

        # 第一次点击：以 Warning 模板尺寸为单位，点击其左下角外侧一点（用于展开下拉）
        # - 向左偏移一个模板宽度
        # - 向下偏移一个模板高度
        first_click_editor_x = int(warning_center_x - match_w)
        first_click_editor_y = int(warning_center_y + match_h)
    first_screen_x, first_screen_y = executor.convert_editor_to_screen_coords(
        first_click_editor_x,
        first_click_editor_y,
    )
    template_size_suffix = ""
    if int(match_w) > 0 and int(match_h) > 0:
        template_size_suffix = f" 宽度={int(match_w)} 高度={int(match_h)}"
    executor.log(
        f"{log_prefix} 点击#1 基于模板尺寸偏移 editor=({first_click_editor_x},{first_click_editor_y}) "
        f"screen=({first_screen_x},{first_screen_y}){template_size_suffix}",
        log_callback,
    )
    _exec_utils.click_and_verify(
        executor,
        first_screen_x,
        first_screen_y,
        f"{log_prefix} 点击#1",
        log_callback,
    )

    _exec_utils.log_wait_if_needed(executor, 0.2, f"{log_prefix} 等待 0.20 秒", log_callback)

    dropdown_screenshot = editor_capture.capture_window(executor.window_title)
    if not dropdown_screenshot:
        executor.log(f"{log_prefix} ✗ 点击展开后截图失败", log_callback)
        return False

    # === 2) 识别下拉矩形（颜色 D7D7D7）===
    prepared_bgr = editor_capture.prepare_color_scan_image(dropdown_screenshot)
    found_rectangles = editor_capture.find_color_rectangles(
        dropdown_screenshot,
        target_color_hex="D7D7D7",
        color_tolerance=18,
        near_point=(int(first_click_editor_x), int(first_click_editor_y) + 6),
        max_distance=900,
        prepared_bgr=prepared_bgr,
    )

    filtered_rectangles: list[tuple[int, int, int, int, float]] = []
    for rect_x, rect_y, rect_w, rect_h, distance in found_rectangles:
        if int(rect_y) < int(first_click_editor_y) + 6:
            continue
        if int(first_click_editor_x) < int(rect_x) - 60 or int(first_click_editor_x) > int(
            rect_x + rect_w
        ) + 60:
            continue
        filtered_rectangles.append((int(rect_x), int(rect_y), int(rect_w), int(rect_h), float(distance)))

    chosen_rectangle: tuple[int, int, int, int, float] | None = None
    if filtered_rectangles:
        chosen_rectangle = filtered_rectangles[0]
    elif found_rectangles:
        chosen_rectangle = tuple(
            int(v) if index < 4 else float(v) for index, v in enumerate(found_rectangles[0])
        )  # type: ignore[assignment]

    if chosen_rectangle is None:
        executor.log(f"{log_prefix} ✗ 未识别到 D7D7D7 下拉矩形", log_callback)
        if visual_callback is not None:
            visual_callback(
                dropdown_screenshot,
                {
                    "rects": [],
                    "circles": [
                        {
                            "center": (int(first_click_editor_x), int(first_click_editor_y)),
                            "radius": 6,
                            "color": (255, 200, 0),
                            "label": "展开点击点",
                        }
                    ],
                },
            )
        return False

    dropdown_x, dropdown_y, dropdown_w, dropdown_h, dropdown_distance = chosen_rectangle
    dropdown_region = (int(dropdown_x), int(dropdown_y), int(dropdown_w), int(dropdown_h))

    if visual_callback is not None:
        visual_callback(
            dropdown_screenshot,
            {
                "rects": [
                    {
                        "bbox": (int(dropdown_x), int(dropdown_y), int(dropdown_w), int(dropdown_h)),
                        "color": (0, 220, 0),
                        "label": f"下拉矩形 D7D7D7 dist={round(float(dropdown_distance), 1)}",
                    }
                ],
                "circles": [
                    {
                        "center": (int(first_click_editor_x), int(first_click_editor_y)),
                        "radius": 6,
                        "color": (0, 220, 0),
                        "label": "已展开",
                    }
                ],
            },
        )

    # === 3) 解析目标选项 ===
    options_list = list(enum_options or [])
    desired_text_normalized = normalize_dropdown_option_text(str(desired_text or ""))
    if not desired_text_normalized:
        enum_index_safe = int(enum_index) if int(enum_index) > 0 else 1
        if options_list and 0 <= int(enum_index_safe) - 1 < len(options_list):
            desired_text_normalized = normalize_dropdown_option_text(options_list[int(enum_index_safe) - 1])
        else:
            desired_text_normalized = ""

    desired_index_zero_based: Optional[int] = None
    option_norm_to_index: dict[str, int] = {}
    for option_index, option_text in enumerate(options_list):
        norm = normalize_dropdown_option_text(option_text)
        if norm and norm not in option_norm_to_index:
            option_norm_to_index[norm] = int(option_index)

    if desired_text_normalized and desired_text_normalized in option_norm_to_index:
        desired_index_zero_based = option_norm_to_index[desired_text_normalized]

    if desired_index_zero_based is None:
        enum_index_safe = int(enum_index) if int(enum_index) > 0 else 1
        desired_index_zero_based = int(enum_index_safe) - 1

    # === 4) OCR + 滚动循环 ===
    previous_fingerprint = fingerprint_region(dropdown_screenshot, dropdown_region)
    unchanged_scroll_cycles = 0
    max_scroll_cycles = 25

    for scroll_cycle in range(int(max_scroll_cycles)):
        if pause_hook is not None:
            pause_hook()
        if allow_continue is not None and not allow_continue():
            executor.log(f"{log_prefix} 用户终止/暂停，中止枚举选择", log_callback)
            return False

        ocr_text_result, ocr_details = editor_capture.ocr_recognize_region(
            dropdown_screenshot,
            dropdown_region,
            return_details=True,
            exclude_top_pixels=0,
        )
        recognized_entries: list[dict] = []
        if isinstance(ocr_details, list):
            for detail_item in ocr_details:
                if not isinstance(detail_item, (list, tuple)) or len(detail_item) < 2:
                    continue
                bbox_any = detail_item[0]
                text_any = detail_item[1]
                text_value = str(text_any or "").strip()
                if not text_value:
                    continue
                bbox_left, bbox_top, bbox_width, bbox_height = normalize_ocr_bbox(bbox_any)
                if bbox_width <= 0 or bbox_height <= 0:
                    continue
                window_bbox = (
                    int(dropdown_x + bbox_left),
                    int(dropdown_y + bbox_top),
                    int(bbox_width),
                    int(bbox_height),
                )
                center_point = get_bbox_center(bbox_any)
                window_center = (int(dropdown_x + center_point[0]), int(dropdown_y + center_point[1]))
                recognized_entries.append(
                    {
                        "text": text_value,
                        "text_norm": normalize_dropdown_option_text(text_value),
                        "bbox": window_bbox,
                        "center": window_center,
                    }
                )
        recognized_entries.sort(key=lambda entry: int(entry["center"][1]))

        matched_entries: list[dict] = []
        for entry in recognized_entries:
            mapped_index = option_norm_to_index.get(str(entry["text_norm"]))
            if mapped_index is None:
                continue
            matched_entries.append({**entry, "option_index": int(mapped_index)})

        # 识别“是否已全部显示”
        if options_list and matched_entries:
            matched_indices = sorted({int(e["option_index"]) for e in matched_entries})
            if matched_indices and matched_indices[0] == 0 and matched_indices[-1] == int(len(options_list)) - 1:
                executor.log(f"{log_prefix} ✓ 当前下拉已包含全部枚举值（无需滚动）", log_callback)

        # 4.1 直接命中文本 → 点击
        click_target_center: Optional[Tuple[int, int]] = None
        click_target_bbox: Optional[Tuple[int, int, int, int]] = None
        click_label: str = ""

        for entry in recognized_entries:
            if desired_text_normalized and str(entry["text_norm"]) == desired_text_normalized:
                center_value = entry.get("center", (0, 0))
                bbox_value = entry.get("bbox", (0, 0, 0, 0))
                click_target_center = (int(center_value[0]), int(center_value[1]))
                click_target_bbox = (
                    int(bbox_value[0]),
                    int(bbox_value[1]),
                    int(bbox_value[2]),
                    int(bbox_value[3]),
                )
                click_label = f"点击: {entry['text']}"
                break

        # 4.2 缺字推断：利用已匹配项的顺序推断目标 y
        if click_target_center is None and matched_entries:
            desired_index_value = int(desired_index_zero_based)
            matched_anchor_pairs: list[tuple[int, int]] = [
                (int(entry["option_index"]), int(entry["center"][1])) for entry in matched_entries
            ]
            inferred_y = infer_missing_option_center_y_by_order(
                desired_index_zero_based=desired_index_value,
                matched_indices_and_center_y=matched_anchor_pairs,
            )
            if inferred_y is not None:
                inferred_x = int(dropdown_x + dropdown_w // 2)
                if int(dropdown_y) <= int(inferred_y) <= int(dropdown_y + dropdown_h):
                    click_target_center = (int(inferred_x), int(inferred_y))
                    click_label = f"推断点击: #{desired_index_value + 1}"

        # 4.3 顺序兜底：当 OCR 文本无法与枚举定义匹配，但“识别条目数量 == 枚举总数”时，
        #     认为当前下拉无需翻页，按从上到下的顺序映射并点击目标序号。
        order_fallback_index = infer_order_based_click_index(
            desired_index_zero_based=int(desired_index_zero_based),
            expected_options_count=int(len(options_list)) if options_list else 0,
            recognized_entries_count=int(len(recognized_entries)),
            scroll_cycle=int(scroll_cycle),
        )
        if click_target_center is None and order_fallback_index is not None and options_list:
            chosen_entry = recognized_entries[int(order_fallback_index)]
            center_value = chosen_entry.get("center", (0, 0))
            bbox_value = chosen_entry.get("bbox", (0, 0, 0, 0))
            click_target_center = (int(center_value[0]), int(center_value[1]))
            click_target_bbox = (
                int(bbox_value[0]),
                int(bbox_value[1]),
                int(bbox_value[2]),
                int(bbox_value[3]),
            )
            expected_text = str(options_list[int(order_fallback_index)])
            observed_text = str(chosen_entry.get("text", "") or "")
            executor.log(
                f"{log_prefix} ✓ 顺序兜底：OCR 文本未匹配但数量一致({len(options_list)})，"
                f"按顺序点击 #{int(order_fallback_index) + 1}（定义='{expected_text}' OCR='{observed_text}'）",
                log_callback,
            )
            click_label = f"顺序点击: #{int(order_fallback_index) + 1}"

        if click_target_center is not None:
            click_editor_x, click_editor_y = int(click_target_center[0]), int(click_target_center[1])
            click_screen_x, click_screen_y = executor.convert_editor_to_screen_coords(click_editor_x, click_editor_y)
            executor.log(
                f"{log_prefix} ✓ 选择枚举项：editor=({click_editor_x},{click_editor_y}) "
                f"screen=({click_screen_x},{click_screen_y}) {click_label}",
                log_callback,
            )
            if visual_callback is not None:
                rects = []
                if click_target_bbox is not None:
                    rects.append(
                        {
                            "bbox": click_target_bbox,
                            "color": (0, 220, 0),
                            "label": click_label,
                        }
                    )
                rects.append(
                    {
                        "bbox": (int(dropdown_x), int(dropdown_y), int(dropdown_w), int(dropdown_h)),
                        "color": (0, 180, 255),
                        "label": "下拉区域",
                    }
                )
                circles = [
                    {
                        "center": (int(click_editor_x), int(click_editor_y)),
                        "radius": 7,
                        "color": (255, 200, 0),
                        "label": "点击",
                    }
                ]
                visual_callback(dropdown_screenshot, {"rects": rects, "circles": circles})
            _exec_utils.click_and_verify(executor, click_screen_x, click_screen_y, f"{log_prefix} 点击选项", log_callback)
            _exec_utils.log_wait_if_needed(executor, 0.1, f"{log_prefix} 等待 0.10 秒", log_callback)
            return True

        # 未找到目标：决定是否滚动
        if options_list and matched_entries:
            matched_indices = sorted({int(e["option_index"]) for e in matched_entries})
            if matched_indices and matched_indices[-1] >= int(len(options_list)) - 1:
                executor.log(f"{log_prefix} ✗ 已滚动到末尾仍未找到目标选项", log_callback)
                return False

        if int(scroll_cycle) == int(max_scroll_cycles) - 1:
            executor.log(f"{log_prefix} ✗ 超过最大滚动次数仍未找到目标选项", log_callback)
            return False

        # 滚动两格后截图一次
        scroll_center_editor_x = int(dropdown_x + dropdown_w // 2)
        scroll_center_editor_y = int(dropdown_y + dropdown_h // 2)
        scroll_center_screen_x, scroll_center_screen_y = executor.convert_editor_to_screen_coords(
            scroll_center_editor_x, scroll_center_editor_y
        )
        _ = editor_capture.move_mouse(int(scroll_center_screen_x), int(scroll_center_screen_y))
        editor_capture.scroll_wheel(-2)
        sleep_seconds(0.06)

        dropdown_screenshot_next = editor_capture.capture_window(executor.window_title)
        if not dropdown_screenshot_next:
            executor.log(f"{log_prefix} ✗ 滚动后截图失败", log_callback)
            return False

        next_fingerprint = fingerprint_region(dropdown_screenshot_next, dropdown_region)
        if str(next_fingerprint) == str(previous_fingerprint):
            unchanged_scroll_cycles += 1
            executor.log(
                f"{log_prefix} 滚动后内容未变化（可能到头）: unchanged={unchanged_scroll_cycles}",
                log_callback,
            )
        else:
            unchanged_scroll_cycles = 0
            previous_fingerprint = next_fingerprint

        dropdown_screenshot = dropdown_screenshot_next

        if unchanged_scroll_cycles >= 2:
            executor.log(f"{log_prefix} ✗ 判定已滚动到头（内容连续两次未变化）", log_callback)
            return False

    return False


def handle_regular_param_fallback(
    executor: EditorExecutorWithViewport,
    port_center: Tuple[int, int],
    param_value: str,
    effective_type: str,
    node_bbox: Tuple[int, int, int, int],
    current_port: Any,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    *,
    fallback_click_offset: Tuple[int, int] = (50, 25),
    log_prefix: str = "[参数配置/非布尔]",
) -> bool:
    """处理普通参数的fallback路径：Warning未命中时，端口偏移点击后输入。
    
    对于三维向量，会重新截图后使用OCR方式输入。
    
    Returns:
        成功返回True
    """
    port_x, port_y = int(port_center[0]), int(port_center[1])

    executor.log(f"{log_prefix} 主策略未命中，改用端口偏移点击后输入", log_callback)

    offset_x, offset_y = fallback_click_offset
    fallback_x, fallback_y = executor.convert_editor_to_screen_coords(port_x + offset_x, port_y + offset_y)
    executor.log(
        f"{log_prefix} Fallback 点击 偏移({offset_x:+d},{offset_y:+d}) screen=({fallback_x},{fallback_y})",
        log_callback,
    )
    _exec_utils.click_and_verify(executor, fallback_x, fallback_y, f"{log_prefix} Fallback 点击", log_callback)
    
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)
    
    # 三维向量：点击后重新截图，使用 OCR 方式输入
    if isinstance(effective_type, str) and ("三维向量" in effective_type):
        screenshot_vec = editor_capture.capture_window(executor.window_title)
        if not screenshot_vec:
            executor.log("✗ 截图失败（向量OCR）", log_callback)
            return False

        # 重新计算搜索区域（与前面逻辑一致）
        result = find_warning_region_for_port(
            executor,
            screenshot_vec,
            node_bbox,
            port_center,
            "",
            log_callback,
        )
        if result is None:
            return False

        search_region, _cur, _nxt = result

        ctx_vec = AutomationStepContext(
            log_callback=log_callback,
            visual_callback=visual_callback,
            pause_hook=pause_hook,
            allow_continue=allow_continue,
        )

        ok_vec = input_vector3_by_ocr(
            executor,
            screenshot_vec,
            search_region,
            node_bbox,
            param_value,
            ctx_vec,
        )
        if not ok_vec:
            executor.log("✗ 三维向量 OCR 未完成：终止该参数设置", log_callback)
            return False
    else:
        executor.log(f"{log_prefix} 注入参数值: '{param_value}' (len={len(param_value)})", log_callback)
        if not executor.input_text_with_hooks(param_value, pause_hook, allow_continue, log_callback):
            return False
    
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
    
    return True


def compute_regular_param_click_editor_by_port_gap(
    node_bbox: Tuple[int, int, int, int],
    current_port: Any,
    next_port: Optional[Any],
    *,
    dx_port_widths: int = 2,
    dy_port_heights: int = 1,
) -> Optional[Tuple[int, int]]:
    """基于端口矩形与上下端口间距，推导“普通参数输入框”的点击位置（editor 坐标系）。

    适用场景（来自 UI 经验规则）：
    - 当“当前端口”与“下一个端口（或节点底边）”之间存在足够的垂直空隙，
      且该空隙至少能容纳一个端口高度时，输入框会出现在“当前端口下方一行”的固定偏移位置。

    规则（以端口模板矩形为单位）：
    - 从当前端口 bbox 的中心点出发：
      - 向下移动 dy_port_heights * port_h
      - 向右移动 dx_port_widths * port_w

    Returns:
        推导出的 editor 点击点 (x, y)，不可用时返回 None
    """
    if current_port is None:
        return None

    cur_bbox_any = getattr(current_port, "bbox", None)
    if not isinstance(cur_bbox_any, tuple) or len(cur_bbox_any) < 4:
        return None

    cur_x, cur_y, cur_w, cur_h = (
        int(cur_bbox_any[0]),
        int(cur_bbox_any[1]),
        int(cur_bbox_any[2]),
        int(cur_bbox_any[3]),
    )
    if cur_w <= 0 or cur_h <= 0:
        return None

    node_left, node_top, node_w, node_h = (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3]))
    node_right = int(node_left + node_w)
    node_bottom = int(node_top + node_h)

    next_top_y: int
    if next_port is not None:
        next_bbox_any = getattr(next_port, "bbox", None)
        if not isinstance(next_bbox_any, tuple) or len(next_bbox_any) < 4:
            return None
        next_top_y = int(next_bbox_any[1])
    else:
        next_top_y = int(node_bottom)

    cur_bottom_y = int(cur_y + cur_h)
    vertical_gap = int(next_top_y - cur_bottom_y)

    # 以“端口中心点”为基准：优先使用检测结果的 center，缺失则回退 bbox 中心
    center_any = getattr(current_port, "center", None)
    if isinstance(center_any, tuple) and len(center_any) >= 2:
        base_x, base_y = int(center_any[0]), int(center_any[1])
    else:
        base_x = int(cur_x + cur_w // 2)
        base_y = int(cur_y + cur_h // 2)

    click_x = int(base_x + int(dx_port_widths) * int(cur_w))

    # 规则：
    # - 若当前端口与下一端口/底边的间距足够容纳一个端口高度：输入框在下一行 → 下移 1*h
    # - 否则：输入框在当前行右侧 → 不下移，仅右移
    if int(vertical_gap) >= int(cur_h):
        click_y = int(base_y + int(dy_port_heights) * int(cur_h))
    else:
        click_y = int(base_y)

    # 避免点击到节点矩形外（理论上不应发生；发生时宁可让调用方失败退出）
    if not (
        int(node_left) <= int(click_x) <= int(node_right)
        and int(node_top) <= int(click_y) <= int(node_bottom)
    ):
        return None

    return int(click_x), int(click_y)


def handle_regular_param_by_port_gap(
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    current_port: Optional[Any],
    next_port: Optional[Any],
    param_value: str,
    pause_hook: Optional[Callable[[], None]],
    allow_continue: Optional[Callable[[], bool]],
    log_callback: Optional[Callable[[str], None]],
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]],
    *,
    log_prefix: str = "[参数配置/非布尔]",
    dx_port_widths: int = 2,
    dy_port_heights: int = 1,
) -> bool:
    """普通参数输入：优先使用“端口间距 + 固定偏移”定位输入框并输入。

    说明：
    - 不依赖 Warning 模板识别；
    - 仅适用于“输入框在当前端口下一行”的 UI 形态；
    - 若推导失败返回 False，由调用方决定是否 fallback。
    """
    click_point = None
    if current_port is not None:
        click_point = compute_regular_param_click_editor_by_port_gap(
            node_bbox,
            current_port,
            next_port,
            dx_port_widths=int(dx_port_widths),
            dy_port_heights=int(dy_port_heights),
        )

    if click_point is None:
        cur_bbox = tuple(int(v) for v in getattr(current_port, "bbox", (0, 0, 0, 0))) if current_port is not None else None
        nxt_bbox = tuple(int(v) for v in getattr(next_port, "bbox", (0, 0, 0, 0))) if next_port is not None else None
        executor.log(
            f"{log_prefix} 端口间距法不可用：current_bbox={cur_bbox} next_bbox={nxt_bbox}",
            log_callback,
        )
        return False

    click_editor_x, click_editor_y = int(click_point[0]), int(click_point[1])
    click_screen_x, click_screen_y = executor.convert_editor_to_screen_coords(click_editor_x, click_editor_y)

    executor.log(
        f"{log_prefix} 端口间距法点击输入框 editor=({click_editor_x},{click_editor_y}) "
        f"screen=({click_screen_x},{click_screen_y}) 偏移=右{dx_port_widths}*w 下(可选){dy_port_heights}*h",
        log_callback,
    )

    if visual_callback is not None:
        rects = [{"bbox": (int(node_bbox[0]), int(node_bbox[1]), int(node_bbox[2]), int(node_bbox[3])), "color": (120, 200, 255), "label": "节点"}]
        circles = [{"center": (int(click_editor_x), int(click_editor_y)), "radius": 7, "color": (0, 220, 0), "label": "输入点击"}]
        if current_port is not None:
            cur_bbox = getattr(current_port, "bbox", None)
            if isinstance(cur_bbox, tuple) and len(cur_bbox) >= 4:
                rects.append({"bbox": (int(cur_bbox[0]), int(cur_bbox[1]), int(cur_bbox[2]), int(cur_bbox[3])), "color": (255, 180, 0), "label": "当前端口"})
        if next_port is not None:
            nxt_bbox = getattr(next_port, "bbox", None)
            if isinstance(nxt_bbox, tuple) and len(nxt_bbox) >= 4:
                rects.append({"bbox": (int(nxt_bbox[0]), int(nxt_bbox[1]), int(nxt_bbox[2]), int(nxt_bbox[3])), "color": (255, 120, 120), "label": "下一端口"})
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    _exec_utils.click_and_verify(executor, click_screen_x, click_screen_y, f"{log_prefix} 端口间距点击", log_callback)
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    executor.log(f"{log_prefix} 注入参数值: '{param_value}' (len={len(param_value)})", log_callback)
    if not executor.input_text_with_hooks(param_value, pause_hook, allow_continue, log_callback):
        return False
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)

    return True


def find_vertical_context_for_input_port(
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    port_name: str,
    log_callback: Optional[Callable[[str], None]],
    *,
    ports_snapshot: Optional[List[Any]] = None,
    log_prefix: str = "[参数配置/非布尔]",
) -> Optional[Tuple[Any, Optional[Any]]]:
    """查找“当前输入端口”及其下方的“下一输入端口”（用于端口间距法判定）。"""
    if ports_snapshot is not None:
        ports_all = list(ports_snapshot)
    else:
        list_ports_func = globals().get("list_ports_for_bbox")
        if list_ports_func is None:
            executor.log(f"{log_prefix} ✗ 未提供端口识别函数 list_ports_for_bbox", log_callback)
            return None
        ports_all = list_ports_func(screenshot, node_bbox)

    ports_filtered = [p for p in ports_all if is_data_input_port(p)]
    if len(ports_filtered) == 0:
        executor.log(f"{log_prefix} ✗ 未识别到数据输入端口", log_callback)
        return None

    current_center_y = int(port_center[1])
    current_port = None
    if port_name:
        named = [p for p in ports_filtered if str(getattr(p, "name_cn", "") or "") == str(port_name)]
        if len(named) > 0:
            current_port = named[0]
    if current_port is None:
        current_port = sorted(
            ports_filtered,
            key=lambda p: abs(int(getattr(p, "center", (0, 0))[1]) - current_center_y),
        )[0]

    current_top_y = int(getattr(current_port, "bbox", (0, 0, 0, 0))[1])
    next_ports = sorted(
        [p for p in ports_filtered if int(getattr(p, "bbox", (0, 0, 0, 0))[1]) > current_top_y],
        key=lambda p: int(getattr(p, "bbox", (0, 0, 0, 0))[1]),
    )
    next_port = next_ports[0] if len(next_ports) > 0 else None

    current_name = str(getattr(current_port, "name_cn", "") or "")
    current_index = str(getattr(current_port, "index", ""))
    current_bbox = tuple(int(v) for v in getattr(current_port, "bbox", (0, 0, 0, 0)))
    if next_port is not None:
        next_name = str(getattr(next_port, "name_cn", "") or "")
        next_index = str(getattr(next_port, "index", ""))
        next_bbox = tuple(int(v) for v in getattr(next_port, "bbox", (0, 0, 0, 0)))
        executor.log(
            f"{log_prefix} 端口上下文: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → "
            f"下一(name='{next_name}', index={next_index}, bbox={next_bbox})",
            log_callback,
        )
    else:
        node_bottom = int(node_bbox[1] + node_bbox[3])
        executor.log(
            f"{log_prefix} 端口上下文: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → "
            f"下一(None, 使用节点底部={node_bottom})",
            log_callback,
        )

    return current_port, next_port
