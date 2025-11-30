# -*- coding: utf-8 -*-
"""
config_node_steps: 参数配置步骤拆分
将 execute_config_node_merged 的庞大逻辑拆分为可测试的小步骤。
"""

from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Callable, List
from PIL import Image

from app.automation.core.executor_protocol import EditorExecutorProtocol
from app.automation import capture as editor_capture
from app.automation.core import executor_utils as _exec_utils
from app.automation.ports._ports import is_data_input_port, is_flow_output_port
from app.automation.ports.port_picker import pick_port_center_for_node
from app.automation.input.common import build_graph_region_overlay, sleep_seconds
from app.automation.ports._type_utils import infer_type_from_value
from engine.graph.models.graph_model import NodeModel

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
from app.automation.core.visualization_helpers import emit_node_and_port_overlays


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
    model_inputs_seq = [(p.name, ('flow' if is_flow_port_name(p.name) else 'data')) for p in (node.inputs or [])]
    executor._log(
        "[序号] 模型端口顺序(输入): " + ", ".join([f"{i}:{n}[{k}]" for i, (n, k) in enumerate(model_inputs_seq)]),
        log_callback
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
    ports_all_debug = ports_snapshot if ports_snapshot is not None else list_ports_for_bbox(screenshot, node_bbox)
    screen_candidates = filter_screen_input_candidates(ports_all_debug, expected_kind)
    
    executor._log(f"[序号] 屏幕候选(输入-从上到下): {format_candidates_brief(screen_candidates)}", log_callback)
    executor._log(
        f"[序号] 计划序号(输入): {str(planned_ordinal) if planned_ordinal is not None else 'None'} 对应端口='{param_name}'",
        log_callback
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
    )
    
    if port_center == (0, 0):
        executor._log(f"✗ 未能定位端口: {param_name}", log_callback)
        return None
    
    # 若定位到的端口中心已被使用，则改用未使用的下一个候选
    if check_center_used(port_center, used_centers):
        alt = pick_unused_port_center(screen_candidates, planned_ordinal, used_centers)
        if isinstance(alt, tuple) and len(alt) == 2:
            executor._log(f"[参数配置] 端口中心已使用，改用未使用候选 center(editor)=({int(alt[0])},{int(alt[1])})", log_callback)
            port_center = (int(alt[0]), int(alt[1]))
    
    executor._log(f"[参数配置] 端口 '{param_name}' 定位 center(editor)=({int(port_center[0])},{int(port_center[1])})", log_callback)
    
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
    ports_all = list(ports_snapshot) if ports_snapshot is not None else list_ports_for_bbox(screenshot, node_bbox)
    ports_filtered = [p for p in ports_all if port_selector(p)]
    if len(ports_filtered) == 0:
        if no_ports_msg:
            executor._log(no_ports_msg, log_callback)
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
        executor._log(missing_current_msg, log_callback)
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
        executor._log(f"{log_prefix} ✗ Warning 搜索区域非法", log_callback)
        return None

    search_region = (
        int(search_left),
        int(v_top),
        int(search_right - search_left),
        int(v_bottom - v_top),
    )
    executor._log(
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
        executor._log(
            f"{log_prefix} 基准端口: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → 下一(name='{next_name}', index={next_index}, bbox={next_bbox})",
            log_callback,
        )
    else:
        executor._log(
            f"{log_prefix} 基准端口: 当前(name='{current_name}', index={current_index}, bbox={current_bbox}) → 下一(None, 使用节点底部={int(node_bottom)})",
            log_callback,
        )
    return (search_region, current_port, next_port)


def handle_boolean_param(
    executor: EditorExecutorProtocol,
    port_center: Tuple[int, int],
    param_name: str,
    param_value: str,
    log_callback: Optional[Callable[[str], None]]
) -> bool:
    """处理布尔参数（值为"否"时点击两次）。
    
    Returns:
        是否需要继续后续处理（值为"是"时返回False表示跳过）
    """
    if param_value == "是":
        executor._log(f"· 布尔『{param_name}』=是，无需额外操作", log_callback)
        return False  # 跳过
    
    port_x, port_y = int(port_center[0]), int(port_center[1])
    
    # 点击第一次
    click1_x, click1_y = executor.convert_editor_to_screen_coords(port_x + 50, port_y + 25)
    executor._log(f"[参数配置/布尔] 点击#1 偏移(+50,+25) screen=({click1_x},{click1_y})", log_callback)
    _exec_utils.click_and_verify(executor, click1_x, click1_y, "[参数配置/布尔] 点击#1", log_callback)

    # 无论是否处于快速链模式，布尔参数两次点击之间都固定等待 0.5 秒
    executor._log("等待 0.50 秒（布尔参数固定节奏）", log_callback)
    sleep_seconds(0.5)

    # 点击第二次
    click2_x, click2_y = executor.convert_editor_to_screen_coords(port_x + 50, port_y + 45)
    executor._log(f"[参数配置/布尔] 点击#2 偏移(+50,+45) screen=({click2_x},{click2_y})", log_callback)
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
) -> Optional[Tuple[int, int, int, int, Any, Any]]:
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
    executor: EditorExecutorProtocol,
    screenshot: Image.Image,
    search_region: Tuple[int, int, int, int],
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
    
    executor._log(
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
    
    executor._log(f"{log_prefix} 注入参数值: '{param_value}' (len={len(param_value)})", log_callback)
    if not executor._input_text_with_hooks(param_value, pause_hook, allow_continue, log_callback):
        return False
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
    
    return True


def handle_regular_param_fallback(
    executor: EditorExecutorProtocol,
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
    
    executor._log(f"{log_prefix} Warning 未命中，改用端口偏移点击后输入", log_callback)
    
    offset_x, offset_y = fallback_click_offset
    fallback_x, fallback_y = executor.convert_editor_to_screen_coords(port_x + offset_x, port_y + offset_y)
    executor._log(
        f"{log_prefix} Fallback 点击 偏移({offset_x:+d},{offset_y:+d}) screen=({fallback_x},{fallback_y})",
        log_callback,
    )
    _exec_utils.click_and_verify(executor, fallback_x, fallback_y, f"{log_prefix} Fallback 点击", log_callback)
    
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)
    
    # 三维向量：点击后重新截图，使用OCR方式输入
    if isinstance(effective_type, str) and ("三维向量" in effective_type):
        screenshot_vec = editor_capture.capture_window(executor.window_title)
        if not screenshot_vec:
            executor._log("✗ 截图失败（向量OCR）", log_callback)
            return False
        
        # 重新计算搜索区域（与前面逻辑一致）
        result = find_warning_region_for_port(executor, screenshot_vec, node_bbox, port_center, "", log_callback)
        if result is None:
            return False
        
        search_region, _cur, _nxt = result
        
        ok_vec = input_vector3_by_ocr(
            executor, screenshot_vec, search_region, node_bbox, param_value,
            pause_hook, allow_continue, log_callback, visual_callback
        )
        if not ok_vec:
            executor._log("✗ 三维向量 OCR 未完成：终止该参数设置", log_callback)
            return False
    else:
        executor._log(f"{log_prefix} 注入参数值: '{param_value}' (len={len(param_value)})", log_callback)
        if not executor._input_text_with_hooks(param_value, pause_hook, allow_continue, log_callback):
            return False
    
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)
    
    return True

