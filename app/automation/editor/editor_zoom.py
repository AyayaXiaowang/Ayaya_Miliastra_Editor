# -*- coding: utf-8 -*-
"""
画布缩放相关能力：
- OCR 缩放区域并确保为 50%
"""

from typing import Any, Optional, Callable
from PIL import Image

from app.automation import capture as editor_capture
from app.automation.input.common import sleep_seconds
from app.automation.vision.ocr_utils import normalize_ocr_bbox
from app.automation.editor.ui_constants import ZOOM_ACTION_WAIT_SECONDS, CONTEXT_MENU_APPEAR_WAIT_SECONDS


def ensure_zoom_ratio_50(
    executor,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> bool:
    if allow_continue is not None and not allow_continue():
        executor.log("用户终止/暂停，放弃缩放检查", log_callback)
        return False

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        executor.log("✗ 截图失败（缩放检查）", log_callback)
        return False

    region_x, region_y, region_w, region_h = editor_capture.get_region_rect(screenshot, "节点图缩放区域")
    executor.emit_visual(
        screenshot,
        { 'rects': [ { 'bbox': (int(region_x), int(region_y), int(region_w), int(region_h)), 'color': (120, 200, 255), 'label': '节点图缩放区域' } ] },
        visual_callback,
    )

    def _extract_zoom_value_from_text(text: str) -> Optional[int]:
        import re as _re

        raw = str(text or "")
        compact = raw.strip().replace(" ", "")
        if not compact:
            return None
        compact = (
            compact.replace("％", "%")
            .replace("O", "0")
            .replace("o", "0")
            .replace("▼", "")
            .replace("▽", "")
            .replace("v", "")
            .replace("V", "")
        )
        match = _re.search(r"(\d{1,3})", compact)
        if not match:
            return None
        return int(match.group(1))

    def _summarize_ocr(text: str, details: list[Any], *, max_items: int = 8) -> str:
        preview = str(text or "").strip().replace("\n", " ")
        if len(preview) > 80:
            preview = preview[:80] + "…"
        detail_texts: list[str] = []
        for item in list(details or []):
            line_text = str(item[1] or "").strip() if isinstance(item, (list, tuple)) and len(item) > 1 else ""
            if not line_text:
                continue
            detail_texts.append(line_text)
        if len(detail_texts) > max_items:
            detail_texts = detail_texts[:max_items] + ["…"]
        return f"text='{preview}' details={detail_texts}"

    def _find_numeric_in_details(details: list[Any]) -> tuple[Optional[int], Optional[tuple[int, int, int, int]]]:
        best_value: Optional[int] = None
        best_bbox: Optional[tuple[int, int, int, int]] = None
        for item in details:
            bbox = item[0]
            text = str(item[1] or "")
            value = _extract_zoom_value_from_text(text)
            if value is None:
                continue
            normalized = normalize_ocr_bbox(bbox)
            if int(value) == 50:
                return (50, normalized)
            if best_value is None:
                best_value = int(value)
                best_bbox = normalized
        return (best_value, best_bbox)

    def _ocr_region_once(img: Image.Image, rx: int, ry: int, rw: int, rh: int, return_details: bool = True):
        if rw <= 0 or rh <= 0:
            return ("", [])
        # 注意：缩放控件位于“节点图布置区域”下方的底部栏中；执行步骤通常启用“强制节点图 ROI”，
        # 若不在此处临时关闭，OCR 区域会被裁剪到节点图布置区域，导致高度=0 的空截图从而识别失败。
        with editor_capture.disable_graph_roi_context():
            text, details = editor_capture.ocr_recognize_region(img, (rx, ry, rw, rh), return_details=True)
        return (str(text or ""), list(details or []))

    def _click_editor_xy(ex: int, ey: int, label: str) -> None:
        sx, sy = executor.convert_editor_to_screen_coords(int(ex), int(ey))
        editor_capture.click_left_button(int(sx), int(sy))
        executor.log(f"[鼠标] 点击 {label}：screen=({int(sx)},{int(sy)})", log_callback)

    if int(region_w) <= 0 or int(region_h) <= 0:
        executor.log(f"✗ 缩放区域 ROI 无效：region=({int(region_x)},{int(region_y)},{int(region_w)},{int(region_h)})", log_callback)
        return False

    ocr_summary1: Optional[str] = None
    text0, details0 = _ocr_region_once(screenshot, region_x, region_y, region_w, region_h)
    val0, bbox0 = _find_numeric_in_details(details0)
    ocr_summary0 = _summarize_ocr(text0, details0)

    if val0 is None:
        center_x0 = int(region_x + region_w // 2)
        center_y0 = int(region_y + region_h // 2)
        _click_editor_xy(center_x0, center_y0, "缩放区域中心")
        executor.log(f"等待 {ZOOM_ACTION_WAIT_SECONDS:.2f} 秒", log_callback)
        sleep_seconds(ZOOM_ACTION_WAIT_SECONDS)
        screenshot = editor_capture.capture_window(executor.window_title)
        if not screenshot:
            return False
        text1, details1 = _ocr_region_once(screenshot, region_x, region_y, region_w, region_h)
        val1, bbox1 = _find_numeric_in_details(details1)
        ocr_summary1 = _summarize_ocr(text1, details1)
        val0, bbox0 = val1, bbox1
        rects1 = [
            {
                "bbox": (int(region_x), int(region_y), int(region_w), int(region_h)),
                "color": (120, 200, 255),
                "label": "缩放区域(激活后)",
            }
        ]
        if details1:
            for d in details1:
                box_d = d[0] if len(d) > 0 else None
                text_d = d[1] if len(d) > 1 else ""
                if isinstance(box_d, (list, tuple)) and len(box_d) == 4:
                    if isinstance(box_d[0], (list, tuple)):
                        xs = [float(box_d[k][0]) for k in range(4)]
                        ys = [float(box_d[k][1]) for k in range(4)]
                        lx = min(xs)
                        ty = min(ys)
                        rx = max(xs)
                        by = max(ys)
                        bw = max(1, int(rx - lx))
                        bh = max(1, int(by - ty))
                        rects1.append(
                            {
                                "bbox": (int(region_x + lx), int(region_y + ty), int(bw), int(bh)),
                                "color": (0, 200, 0),
                                "label": str(text_d),
                            }
                        )
                    else:
                        lx = float(box_d[0])
                        ty = float(box_d[1])
                        rx = float(box_d[2])
                        by = float(box_d[3])
                        rects1.append(
                            {
                                "bbox": (
                                    int(region_x + lx),
                                    int(region_y + ty),
                                    int(max(1, rx - lx)),
                                    int(max(1, by - ty)),
                                ),
                                "color": (0, 200, 0),
                                "label": str(text_d),
                            }
                        )
        executor.emit_visual(screenshot, {"rects": rects1}, visual_callback)

    if val0 is None:
        details_log = (
            f"✗ 缩放未识别为数值：region=({int(region_x)},{int(region_y)},{int(region_w)},{int(region_h)}) "
            f"首次OCR({ocr_summary0})"
        )
        if ocr_summary1 is not None:
            details_log += f" 激活后OCR({ocr_summary1})"
        executor.log(details_log, log_callback)
        return False

    if int(val0) == 50:
        return True

    num_left, num_top, num_w, num_h = (0, 0, 0, 0) if bbox0 is None else bbox0
    click_x = int(region_x + num_left + max(1, num_w) // 2) if num_w > 0 else int(region_x + region_w // 2)
    click_y = int(region_y + num_top + max(1, num_h) // 2) if num_h > 0 else int(region_y + region_h // 2)
    _click_editor_xy(click_x, click_y, "当前缩放数字")
    executor.log(f"等待 {ZOOM_ACTION_WAIT_SECONDS:.2f} 秒", log_callback)
    if not executor.wait_with_hooks(ZOOM_ACTION_WAIT_SECONDS, pause_hook, allow_continue, 0.1, log_callback):
        return False

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        return False

    search_top = max(0, int(region_y + (num_top if num_h > 0 else 0) - 300))
    search_bottom = int(region_y + (num_top if num_h > 0 else 0))
    if search_bottom <= search_top:
        search_bottom = int(search_top + 1)
    search_region = (int(region_x), int(search_top), int(region_w), int(search_bottom - search_top))
    _, details_up = _ocr_region_once(screenshot, *search_region)
    rects_up = [ { 'bbox': (int(search_region[0]), int(search_region[1]), int(search_region[2]), int(search_region[3])), 'color': (255, 180, 0), 'label': '上方搜索(找 50/50%)' } ]
    if details_up:
        sx0, sy0 = search_region[0], search_region[1]
        for d in details_up:
            box_d = d[0] if len(d) > 0 else None
            text_d = d[1] if len(d) > 1 else ''
            if isinstance(box_d, (list, tuple)) and len(box_d) == 4:
                if isinstance(box_d[0], (list, tuple)):
                    xs = [float(box_d[k][0]) for k in range(4)]
                    ys = [float(box_d[k][1]) for k in range(4)]
                    lx = min(xs); ty = min(ys); rx = max(xs); by = max(ys)
                    rects_up.append({ 'bbox': (int(sx0 + lx), int(sy0 + ty), int(max(1, rx - lx)), int(max(1, by - ty))), 'color': (0, 200, 0), 'label': str(text_d) })
                else:
                    lx = float(box_d[0]); ty = float(box_d[1]); rx = float(box_d[2]); by = float(box_d[3])
                    rects_up.append({ 'bbox': (int(sx0 + lx), int(sy0 + ty), int(max(1, rx - lx)), int(max(1, by - ty))), 'color': (0, 200, 0), 'label': str(text_d) })
    executor.emit_visual(screenshot, { 'rects': rects_up }, visual_callback)

    chosen_bbox_up: Optional[tuple[int, int, int, int]] = None
    for item in details_up:
        t = str(item[1] or "").strip().replace(" ", "")
        if t in ("50", "50%"):
            chosen_bbox_up = normalize_ocr_bbox(item[0])
            break

    if chosen_bbox_up is not None:
        bx, by, bw, bh = chosen_bbox_up
        click2_x = int(search_region[0] + bx + max(1, bw) // 2)
        click2_y = int(search_region[1] + by + max(1, bh) // 2)
        circles_up = [ { 'center': (int(click2_x), int(click2_y)), 'radius': 6, 'color': (255, 60, 60), 'label': '点击 50' } ]
        executor.emit_visual(screenshot, { 'circles': circles_up }, visual_callback)
        _click_editor_xy(click2_x, click2_y, "上方列表中的 50")
        executor.log(f"等待 {CONTEXT_MENU_APPEAR_WAIT_SECONDS:.2f} 秒", log_callback)
        sleep_seconds(CONTEXT_MENU_APPEAR_WAIT_SECONDS)

    screenshot = editor_capture.capture_window(executor.window_title)
    if not screenshot:
        return False
    text2, details2 = _ocr_region_once(screenshot, region_x, region_y, region_w, region_h)
    val2, _ = _find_numeric_in_details(details2)
    rects_final = [ { 'bbox': (int(region_x), int(region_y), int(region_w), int(region_h)), 'color': (120, 200, 255), 'label': f"复核缩放: {str(text2 or '').strip()}" } ]
    if details2:
        for d in details2:
            box_d = d[0] if len(d) > 0 else None
            text_d = d[1] if len(d) > 1 else ''
            if isinstance(box_d, (list, tuple)) and len(box_d) == 4:
                if isinstance(box_d[0], (list, tuple)):
                    xs = [float(box_d[k][0]) for k in range(4)]
                    ys = [float(box_d[k][1]) for k in range(4)]
                    lx = min(xs); ty = min(ys); rx = max(xs); by = max(ys)
                    rects_final.append({ 'bbox': (int(region_x + lx), int(region_y + ty), int(max(1, rx - lx)), int(max(1, by - ty))), 'color': (0, 200, 0), 'label': str(text_d) })
                else:
                    lx = float(box_d[0]); ty = float(box_d[1]); rx = float(box_d[2]); by = float(box_d[3])
                    rects_final.append({ 'bbox': (int(region_x + lx), int(region_y + ty), int(max(1, rx - lx)), int(max(1, by - ty))), 'color': (0, 200, 0), 'label': str(text_d) })
    executor.emit_visual(screenshot, { 'rects': rects_final }, visual_callback)
    return bool(val2 == 50)


