from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image

from app.automation import capture as editor_capture
from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.editor.node_snapshot import NodePortsSnapshotCache
from app.automation.editor import executor_utils as _exec_utils
from app.automation.vision import get_node_header_height_px_for_bbox, get_port_recognition_header_height_px
from app.automation.vision.ocr_utils import get_bbox_center, normalize_ocr_bbox
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


def _find_signal_label_by_ocr(
    *,
    executor: EditorExecutorWithViewport,
    screenshot: Image.Image,
    node_bbox: Tuple[int, int, int, int],
    log_callback,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> Optional[Dict[str, Any]]:
    """在节点 bbox 内通过 OCR 定位【信号名】文本标签。

    返回:
        {
            "bbox": (left, top, width, height),      # window/editor 坐标系
            "center": (center_x, center_y),          # window/editor 坐标系
            "score": float,
            "raw_text": str,
            "cn_text": str,
            "exclude_top_pixels": int,
        }
        找不到返回 None。
    """
    node_left, node_top, node_width, node_height = (
        int(node_bbox[0]),
        int(node_bbox[1]),
        int(node_bbox[2]),
        int(node_bbox[3]),
    )
    if int(node_width) <= 0 or int(node_height) <= 0:
        return None

    # 始终将 OCR 区域裁剪到“节点图布置区域”内，避免节点靠边/超出时 OCR 返回坐标偏移。
    region_x, region_y, region_w, region_h = editor_capture.clip_to_graph_region(
        screenshot,
        (node_left, node_top, node_width, node_height),
    )
    if int(region_w) <= 0 or int(region_h) <= 0:
        return None

    # 优先复用“一步式识别”产出的节点标题栏高度（动态值，来自色块检测阶段），避免再用 profile 固定像素预估。
    exclude_top_pixels = int(
        get_node_header_height_px_for_bbox(
            screenshot,
            (node_left, node_top, node_width, node_height),
        )
        or 0
    )
    # 兜底：若缓存未命中或未提供动态高度，再回退到 profile 推导的静态高度。
    if int(exclude_top_pixels) <= 0:
        exclude_top_pixels = int(get_port_recognition_header_height_px())
    exclude_top_pixels = max(0, min(int(exclude_top_pixels), int(region_h)))

    ocr_text, ocr_details = editor_capture.ocr_recognize_region(
        screenshot,
        (region_x, region_y, region_w, region_h),
        return_details=True,
        exclude_top_pixels=int(exclude_top_pixels),
    )
    _ = ocr_text

    candidates: list[Dict[str, Any]] = []
    if isinstance(ocr_details, list):
        for detail_item in ocr_details:
            if not isinstance(detail_item, (list, tuple)) or len(detail_item) < 2:
                continue
            bbox_any = detail_item[0]
            text_any = detail_item[1]
            raw_text = str(text_any or "").strip()
            if not raw_text:
                continue
            cn_text = executor.extract_chinese(raw_text)
            if not cn_text:
                continue

            match_priority = 0
            if cn_text == "信号名":
                match_priority = 2
            elif "信号名" in cn_text:
                match_priority = 1
            else:
                continue

            bbox_left, bbox_top, bbox_width, bbox_height = normalize_ocr_bbox(bbox_any)
            if int(bbox_width) <= 0 or int(bbox_height) <= 0:
                continue

            score_value = 0.0
            if len(detail_item) > 2 and isinstance(detail_item[2], (int, float)):
                score_value = float(detail_item[2])

            center_x, center_y = get_bbox_center(bbox_any)
            abs_bbox = (
                int(region_x + bbox_left),
                int(region_y + bbox_top),
                int(bbox_width),
                int(bbox_height),
            )
            abs_center = (int(region_x + center_x), int(region_y + center_y))
            candidates.append(
                {
                    "bbox": abs_bbox,
                    "center": abs_center,
                    "score": float(score_value),
                    "raw_text": raw_text,
                    "cn_text": cn_text,
                    "match_priority": int(match_priority),
                }
            )

    if not candidates:
        executor.log(
            f"[信号绑定][OCR] 未在节点内识别到【信号名】文本（exclude_top={exclude_top_pixels}px）",
            log_callback,
        )
        return None

    candidates.sort(
        key=lambda item: (
            -int(item.get("match_priority", 0)),
            -float(item.get("score", 0.0)),
            int(item.get("bbox", (0, 0, 0, 0))[1]),
        )
    )
    best = dict(candidates[0])
    best["exclude_top_pixels"] = int(exclude_top_pixels)

    bbox = best.get("bbox", (0, 0, 0, 0))
    center = best.get("center", (0, 0))
    executor.log(
        f"[信号绑定][OCR] 命中【信号名】: cn='{best.get('cn_text','')}' raw='{best.get('raw_text','')}' "
        f"bbox=({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}) center=({center[0]},{center[1]}) "
        f"score={float(best.get('score', 0.0)):.2f} exclude_top={exclude_top_pixels}px",
        log_callback,
    )

    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": "目标节点",
            },
            {
                "bbox": (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                "color": (255, 120, 120),
                "label": "OCR: 信号名",
            },
        ]
        circles = [
            {
                "center": (int(center[0]), int(center[1])),
                "radius": 6,
                "color": (0, 220, 0),
                "label": "信号名点击",
            }
        ]
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    return best


def execute_bind_signal(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    """执行“设置信号”步骤：定位节点 → OCR 定位【信号名】标签并点击 → 点击其正下方一行输入区域并输入 → 在节点外附近点击一次画布空白位置收尾。

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

    # 3. OCR 定位【信号名】标签（优先），失败时回退模板匹配
    ocr_match = _find_signal_label_by_ocr(
        executor=executor,
        screenshot=screenshot,
        node_bbox=(node_left, node_top, node_width, node_height),
        log_callback=log_callback,
        visual_callback=visual_callback,
    )
    match = None
    if ocr_match is None:
        executor.log("[信号绑定] OCR 未命中，回退模板匹配 Signal.png", log_callback)
        match = editor_capture.match_template(
            screenshot,
            str(executor.node_signal_template_path),
            search_region=(node_left, node_top, node_width, node_height),
        )
        if not match:
            executor.log("✗ 未在节点内找到 Signal 模板，且 OCR 也未命中【信号名】", log_callback)
            return False

        sig_x, sig_y, sig_w, sig_h, sig_conf = match
        label_bbox = (int(sig_x), int(sig_y), int(sig_w), int(sig_h))
        label_center_editor_x = int(sig_x + sig_w // 2)
        label_center_editor_y = int(sig_y + sig_h // 2)
        label_score = float(sig_conf)
        label_source = "模板"
    else:
        label_bbox = tuple(int(v) for v in (ocr_match.get("bbox") or (0, 0, 0, 0)))
        label_center = tuple(int(v) for v in (ocr_match.get("center") or (0, 0)))
        label_center_editor_x = int(label_center[0])
        label_center_editor_y = int(label_center[1])
        label_score = float(ocr_match.get("score", 0.0))
        label_source = "OCR"

    label_screen_x, label_screen_y = executor.convert_editor_to_screen_coords(
        label_center_editor_x,
        label_center_editor_y,
    )
    executor.log(
        f"[信号绑定] 点击信号名标签({label_source}): editor=({label_center_editor_x},{label_center_editor_y}) "
        f"screen=({label_screen_x},{label_screen_y}) bbox=({label_bbox[0]},{label_bbox[1]},{label_bbox[2]},{label_bbox[3]}) "
        f"score={label_score:.2f}",
        log_callback,
    )

    # 可视化：节点 + 标签框
    if visual_callback is not None:
        rects = [
            {
                "bbox": (node_left, node_top, node_width, node_height),
                "color": (120, 200, 255),
                "label": f"目标节点: {node.title}",
            },
            {
                "bbox": (int(label_bbox[0]), int(label_bbox[1]), int(label_bbox[2]), int(label_bbox[3])),
                "color": (255, 200, 0),
                "label": f"{label_source} 信号名 {label_score:.2f}",
            },
        ]
        circles = [
            {
                "center": (label_center_editor_x, label_center_editor_y),
                "radius": 6,
                "color": (0, 220, 0),
                "label": "标签点击",
            }
        ]
        visual_callback(screenshot, {"rects": rects, "circles": circles})

    _exec_utils.click_and_verify(
        executor,
        label_screen_x,
        label_screen_y,
        "[信号绑定] 点击信号名标签（打开输入）",
        log_callback,
    )
    _exec_utils.log_wait_if_needed(executor, 0.2, "等待 0.20 秒", log_callback)

    # 4. 基于“信号名标签”位置，向下平移一个标签高度点击输入区域并输入文本
    offset_pixels = int(max(1, int(label_bbox[3])))
    input_center_editor_x = int(label_center_editor_x)
    input_center_editor_y = int(label_center_editor_y + offset_pixels)
    input_screen_x, input_screen_y = executor.convert_editor_to_screen_coords(
        input_center_editor_x,
        input_center_editor_y,
    )

    executor.log(
        f"[信号绑定] 点击信号名下方输入区域: editor=({input_center_editor_x},{input_center_editor_y}) "
        f"screen=({input_screen_x},{input_screen_y}) offset=+{offset_pixels}px",
        log_callback,
    )

    if visual_callback is not None:
        circles = [
            {
                "center": (input_center_editor_x, input_center_editor_y),
                "radius": 6,
                "color": (0, 180, 255),
                "label": "输入点击",
            }
        ]
        visual_callback(screenshot, {"circles": circles})

    _exec_utils.click_and_verify(
        executor,
        input_screen_x,
        input_screen_y,
        "[信号绑定] 点击信号名下方输入区域",
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



