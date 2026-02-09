from __future__ import annotations

from typing import Dict, List

import numpy as np
from PIL import Image


def _ocr_titles_for_rectangles(
    screenshot: Image.Image,
    rectangles: List[dict],
    *,
    header_height: int = 28,
) -> Dict[int, str]:
    if len(rectangles) == 0:
        return {}

    from app.automation.vision.ocr_utils import extract_chinese, get_ocr_engine

    ocr_engine = get_ocr_engine()

    min_tile_height = 48
    tile_gap = 8
    tile_padding = 2
    max_row_width = 2400

    block_tiles: List[dict] = []
    for idx, rect in enumerate(rectangles, 1):
        rect_x = rect["x"]
        rect_y = rect["y"]
        rect_width = rect["width"]
        header_height_for_rect = int(rect.get("header_height", header_height) or header_height)
        rect_height_value = int(rect.get("height", 0) or 0)
        if rect_height_value > 0:
            header_height_for_rect = max(0, min(int(header_height_for_rect), int(rect_height_value)))
        header_top = rect_y
        header_bottom = min(rect_y + header_height_for_rect, screenshot.size[1])
        header_left = rect_x
        header_right = min(rect_x + rect_width, screenshot.size[0])
        left = max(0, header_left + tile_padding)
        top = max(0, header_top + tile_padding)
        right = min(screenshot.size[0], header_right - tile_padding)
        bottom = min(screenshot.size[1], header_bottom - tile_padding)
        if right <= left or bottom <= top:
            continue
        roi = screenshot.crop((left, top, right, bottom))
        scale_height = min_tile_height / float(max(1, roi.size[1])) if roi.size[1] < min_tile_height else 1.0
        scale_width_cap = max_row_width / float(max(1, roi.size[0]))
        scale_factor = min(scale_width_cap, max(1.0, scale_height))
        if abs(scale_factor - 1.0) > 1e-3:
            new_w = max(1, int(roi.size[0] * scale_factor))
            new_h = max(1, int(roi.size[1] * scale_factor))
            roi = roi.resize((new_w, new_h), Image.BILINEAR)
        block_tiles.append({"idx": idx, "image": roi})

    placements: List[tuple[int, int]] = []
    current_x = tile_gap
    current_y = tile_gap
    row_height = 0
    for tile in block_tiles:
        tw, th = tile["image"].size
        if current_x + tw + tile_gap > max_row_width:
            current_x = tile_gap
            current_y += row_height + tile_gap
            row_height = 0
        placements.append((current_x, current_y))
        current_x += tw + tile_gap
        if th > row_height:
            row_height = th
    canvas_width = max_row_width
    canvas_height = current_y + row_height + tile_gap if len(block_tiles) > 0 else (tile_gap * 2)

    montage = Image.new("RGB", (canvas_width, canvas_height), (0, 0, 0))
    for tile, (px, py) in zip(block_tiles, placements):
        montage.paste(tile["image"], (px, py))

    tile_rects: List[dict] = []
    for tile, (px, py) in zip(block_tiles, placements):
        tw, th = tile["image"].size
        tile_rects.append({"idx": tile["idx"], "x": px, "y": py, "w": tw, "h": th})

    montage_array = np.array(montage)
    ocr_result_full, _ = ocr_engine(montage_array)

    texts_by_rect: Dict[int, List[tuple[int, int, str]]] = {i: [] for i in range(1, len(rectangles) + 1)}
    if ocr_result_full:
        for item in ocr_result_full:
            box = item[0]
            text = item[1]
            xs = [int(pt[0]) for pt in box]
            ys = [int(pt[1]) for pt in box]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            for rect in tile_rects:
                if rect["x"] <= cx <= rect["x"] + rect["w"] and rect["y"] <= cy <= rect["y"] + rect["h"]:
                    texts_by_rect[rect["idx"]].append((y1, x1, text))
                    break

    ocr_results: Dict[int, str] = {}
    for idx in range(1, len(rectangles) + 1):
        items = texts_by_rect[idx]
        if len(items) == 0:
            continue
        items.sort(key=lambda t: (t[0], t[1]))
        merged_text = " ".join([t[2] for t in items]).strip()
        chinese_only = extract_chinese(merged_text)
        if chinese_only:
            ocr_results[idx] = chinese_only
    return ocr_results



