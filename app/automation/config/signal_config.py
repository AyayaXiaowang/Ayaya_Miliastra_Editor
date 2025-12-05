from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.core.executor_protocol import EditorExecutorWithViewport
from app.automation.core.node_snapshot import NodePortsSnapshotCache
from app.automation.core import executor_utils as _exec_utils
from engine.graph.models.graph_model import GraphModel


def _resolve_signal_text(
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    node_id: str,
) -> str:
    """根据 Todo 与图模型解析用于输入的信号标识文本。

    优先返回**信号名**（人类可读），仅在缺失时才退回到 signal_id：
    - 首选 detail_info["signal_name"]；
    - 其次尝试 GraphModel.get_node_signal_id(node_id) 或 detail_info["signal_id"] 作为兜底。
    """
    # 1) 优先使用 Todo 中携带的信号名（来自节点输入常量“信号名”）
    signal_name_field = todo_item.get("signal_name")
    if isinstance(signal_name_field, str):
        signal_name_text = signal_name_field.strip()
        if signal_name_text:
            return signal_name_text

    # 2) 退回到绑定的 signal_id（若外部确实只接受 ID，可以作为兜底）
    signal_id_text = ""
    get_binding = getattr(graph_model, "get_node_signal_id", None)
    if callable(get_binding):
        bound_id = get_binding(node_id)
        if bound_id:
            signal_id_text = str(bound_id)

    if not signal_id_text:
        signal_id_field = todo_item.get("signal_id")
        if isinstance(signal_id_field, str) and signal_id_field:
            signal_id_text = signal_id_field.strip()

    return signal_id_text


def execute_bind_signal(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """执行“设置信号”步骤：定位节点 → 点击 Signal 图标 → 点击其正下方一行输入区域并输入 → 在节点外附近点击一次画布空白位置收尾。

    约定：
    - 模板路径统一来自执行器：`node_signal_template_path`；
    - 不再识别 Warning 图标位置，而是以命中的 Signal 模板为锚点，沿 Y 轴向下平移一个模板高度作为输入点击位置，
      保持“Signal → 下方输入行”的固定几何关系，降低对 Warning 样式的依赖。
    """
    node_id_field = todo_item.get("node_id")
    node_id = str(node_id_field or "")
    if not node_id or node_id not in graph_model.nodes:
        executor.log("✗ 信号绑定步骤缺少节点或节点不存在", log_callback)
        return False

    node = graph_model.nodes[node_id]
    input_text = _resolve_signal_text(todo_item, graph_model, node_id)
    if not input_text:
        executor.log("✗ 信号绑定步骤缺少可用的 signal_id / 信号名 文本", log_callback)
        return False

    # 1. 确保节点进入视口
    executor.ensure_program_point_visible(
        node.pos[0],
        node.pos[1],
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

    # 2. 截图并定位节点 bbox
    snapshot = NodePortsSnapshotCache(executor, node, log_callback)
    if not snapshot.ensure(reason="信号绑定-初始截图", require_bbox=True):
        return False
    screenshot = snapshot.screenshot
    node_bbox = snapshot.node_bbox
    node_left, node_top, node_width, node_height = (
        int(node_bbox[0]),
        int(node_bbox[1]),
        int(node_bbox[2]),
        int(node_bbox[3]),
    )

    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": f"目标节点: {node.title}",
            }
        ]
        visual_callback(screenshot, {"rects": rects})

    # 3. 在节点内查找 Signal 图标
    match = editor_capture.match_template(
        screenshot,
        str(executor.node_signal_template_path),
        search_region=(node_left, node_top, node_width, node_height),
    )
    if not match:
        executor.log("✗ 未在节点内找到 Signal 图标模板", log_callback)
        return False

    sig_x, sig_y, sig_w, sig_h, sig_conf = match
    signal_center_editor_x = int(sig_x + sig_w // 2)
    signal_center_editor_y = int(sig_y + sig_h // 2)
    signal_screen_x, signal_screen_y = executor.convert_editor_to_screen_coords(
        signal_center_editor_x,
        signal_center_editor_y,
    )
    executor.log(
        f"[信号绑定] 点击 Signal: editor=({signal_center_editor_x},{signal_center_editor_y}) "
        f"screen=({signal_screen_x},{signal_screen_y}) 模板='Signal.png' "
        f"命中bbox=({sig_x},{sig_y},{sig_w},{sig_h}) conf={sig_conf:.2f}",
        log_callback,
    )

    # 可视化：节点 + Signal 命中框
    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": f"目标节点: {node.title}",
            },
            {
                "bbox": (int(sig_x), int(sig_y), int(sig_w), int(sig_h)),
                "color": (255, 200, 0),
                "label": f"Signal 模板 {sig_conf:.2f}",
            },
        ]
        circles = [
            {
                "center": (signal_center_editor_x, signal_center_editor_y),
                "radius": 6,
                "color": (0, 220, 0),
                "label": "Signal 点击",
            }
        ]
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    _exec_utils.click_and_verify(
        executor,
        signal_screen_x,
        signal_screen_y,
        "[信号绑定] 点击 Signal（打开面板）",
        log_callback,
    )
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    # 4. 基于 Signal 模板命中位置，向下平移一个模板高度点击输入区域并输入文本
    offset_pixels = int(sig_h)
    input_center_editor_x = signal_center_editor_x
    input_center_editor_y = int(signal_center_editor_y + offset_pixels)
    input_screen_x, input_screen_y = executor.convert_editor_to_screen_coords(
        input_center_editor_x,
        input_center_editor_y,
    )

    executor.log(
        f"[信号绑定] 点击 Signal 下方输入区域: editor=({input_center_editor_x},{input_center_editor_y}) "
        f"screen=({input_screen_x},{input_screen_y}) offset=+{offset_pixels}px",
        log_callback,
    )

    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": f"目标节点: {node.title}",
            },
            {
                "bbox": (int(sig_x), int(sig_y), int(sig_w), int(sig_h)),
                "color": (255, 200, 0),
                "label": f"Signal 模板 {sig_conf:.2f}",
            },
        ]
        circles = [
            {
                "center": (signal_center_editor_x, signal_center_editor_y),
                "radius": 6,
                "color": (0, 220, 0),
                "label": "Signal 点击",
            },
            {
                "center": (input_center_editor_x, input_center_editor_y),
                "radius": 6,
                "color": (0, 180, 255),
                "label": "输入点击",
            },
        ]
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    _exec_utils.click_and_verify(
        executor,
        input_screen_x,
        input_screen_y,
        "[信号绑定] 点击 Signal 下方输入区域",
        log_callback,
    )
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    executor.log(
        f"[信号绑定] 注入信号标识: '{input_text}' (len={len(input_text)})",
        log_callback,
    )
    if not executor.input_text_with_hooks(
        input_text,
        pause_hook,
        allow_continue,
        log_callback,
    ):
        return False
    _exec_utils.log_wait_if_needed(executor, 0.1, "等待 0.10 秒", log_callback)

    # 5. 在节点附近点击一次画布空白位置，视为收尾
    # 复用统一的画布空白点击 helper：以节点中心附近为起点，在画布区域内寻找安全空白点。
    blank_start_editor_x = int(node_left + node_width // 2)
    blank_start_editor_y = int(node_top + node_height // 2)
    blank_start_screen_x, blank_start_screen_y = executor.convert_editor_to_screen_coords(
        blank_start_editor_x,
        blank_start_editor_y,
    )
    _exec_utils.click_canvas_blank_near_screen_point(
        executor,
        int(blank_start_screen_x),
        int(blank_start_screen_y),
        log_prefix="[信号绑定] 信号文本输入完成，",
        wait_seconds=0.1,
        wait_message="等待 0.10 秒（信号设置完成后画布状态稳定）",
        log_callback=log_callback,
        visual_callback=visual_callback,
    )

    # 标记节点快照为脏，后续步骤需重新识别端口与布局
    snapshot.mark_dirty(require_bbox=True)
    return True



