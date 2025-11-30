from __future__ import annotations

"""
内部色块/节点检测模块（复制自外部 color_block_detector 的思路），仅保留对给定 Image 的处理，
提供：
- detect_nodes_with_centers(image) -> list[NodeDetected]

约束：
- 不进行窗口截屏、磁盘文件写入与调试图片输出；
- 不使用 try/except；
- 变量命名清晰可读；
- 名称仅保留中文作为匹配依据。
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Dict
from PIL import Image
from app.automation.vision.ocr_utils import get_ocr_engine
from app.automation.vision.ocr_utils import extract_chinese


 


@dataclass
class NodeDetected:
    name_cn: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    center: Tuple[int, int]
    area: int


def _detect_bright_regions(image: Image.Image) -> Tuple[List[Dict], np.ndarray]:
    """
    基于 HSV + 形态学 + 20x20窗口 + 双向扫描去飞线，生成稳定的色块区域。
    返回：color_blocks（带 x,y,w,h, area），mask_final（二值图）
    """
    image_array_rgb = np.array(image)
    image_bgr = cv2.cvtColor(image_array_rgb, cv2.COLOR_RGB2BGR)
    image_hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)

    saturation_channel = image_hsv[:, :, 1]
    value_channel = image_hsv[:, :, 2]

    mask_colorful = ((saturation_channel > 50) & (value_channel > 60)).astype(np.uint8) * 255
    mask_white = ((saturation_channel < 50) & (value_channel > 150)).astype(np.uint8) * 255

    kernel_close_color = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    kernel_close_white = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))

    mask_colorful = cv2.morphologyEx(mask_colorful, cv2.MORPH_CLOSE, kernel_close_color, iterations=2)
    mask_colorful = cv2.morphologyEx(mask_colorful, cv2.MORPH_OPEN, kernel_open, iterations=1)
    mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_CLOSE, kernel_close_white, iterations=1)
    mask_white = cv2.morphologyEx(mask_white, cv2.MORPH_OPEN, kernel_open, iterations=1)

    mask_bright = cv2.bitwise_or(mask_colorful, mask_white)

    min_rect_size = 20
    contours_all, _ = cv2.findContours(mask_bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    mask_filtered = np.zeros_like(mask_bright)
    for contour in contours_all:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_rect_size or h < min_rect_size:
            continue
        roi_mask = mask_bright[y:y + h, x:x + w]

        can_fit = False
        for delta_y in range(h - min_rect_size + 1):
            if can_fit:
                break
            for delta_x in range(w - min_rect_size + 1):
                window = roi_mask[delta_y:delta_y + min_rect_size, delta_x:delta_x + min_rect_size]
                if np.all(window == 255):
                    can_fit = True
                    break

        if can_fit:
            cv2.drawContours(mask_filtered, [contour], -1, 255, thickness=-1)

    # 垂直扫描去除细小飞线
    scan_width = 5
    min_height_threshold = 15
    mask_no_lines = mask_filtered.copy()
    image_height, image_width = mask_filtered.shape
    for position_x in range(0, image_width, scan_width):
        position_x_end = min(position_x + scan_width, image_width)
        scan_strip = mask_no_lines[:, position_x:position_x_end].copy()
        contours_in_strip, _ = cv2.findContours(scan_strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            coordinate_x, coordinate_y, coordinate_w, coordinate_h = cv2.boundingRect(contour)
            if coordinate_h < min_height_threshold:
                cv2.drawContours(scan_strip, [contour], -1, 0, thickness=-1)
        mask_no_lines[:, position_x:position_x_end] = scan_strip

    # 横向扫描去除细小飞线
    scan_height = 1
    min_width_threshold = 50
    mask_no_lines_h = mask_no_lines.copy()
    for position_y in range(0, image_height, scan_height):
        position_y_end = min(position_y + scan_height, image_height)
        scan_strip = mask_no_lines_h[position_y:position_y_end, :].copy()
        contours_in_strip, _ = cv2.findContours(scan_strip, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours_in_strip:
            coordinate_x, coordinate_y, coordinate_w, coordinate_h = cv2.boundingRect(contour)
            if coordinate_w < min_width_threshold:
                cv2.drawContours(scan_strip, [contour], -1, 0, thickness=-1)
        mask_no_lines_h[position_y:position_y_end, :] = scan_strip

    mask_final = mask_no_lines_h
    contours, _ = cv2.findContours(mask_final, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    color_blocks: List[Dict] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = int(w * h)
        color_blocks.append({
            "x": int(x),
            "y": int(y),
            "width": int(w),
            "height": int(h),
            "area": area,
        })

    color_blocks.sort(key=lambda b: b["area"], reverse=True)
    return color_blocks, mask_final


def _ocr_texts_for_blocks(image: Image.Image, color_blocks: List[Dict], ocr_engine) -> Dict[int, str]:
    """
    将每个色块的 ROI 预处理后拼接成蒙太奇图，进行一次 OCR，
    再将识别框按中心点归属回各自色块，合并为块内文本。
    返回：字典 idx->合并文本（仅中文）。
    """
    minimum_tile_height = 48
    maximum_tile_width = 800
    tile_gap_pixels = 8
    tile_padding_pixels = 2
    maximum_row_width = 2400

    block_tiles: List[Dict] = []
    for index, block in enumerate(color_blocks, 1):
        block_x = block["x"]
        block_y = block["y"]
        block_w = block["width"]
        block_h = block["height"]

        left = max(0, block_x + tile_padding_pixels)
        top = max(0, block_y + tile_padding_pixels)
        right = min(image.size[0], block_x + block_w - tile_padding_pixels)
        bottom = min(image.size[1], block_y + block_h - tile_padding_pixels)
        if right <= left or bottom <= top:
            continue

        region = image.crop((left, top, right, bottom))

        scale_height = minimum_tile_height / float(max(1, region.size[1])) if region.size[1] < minimum_tile_height else 1.0
        scale_width_cap = maximum_tile_width / float(max(1, region.size[0]))
        scale_factor = min(scale_width_cap, max(1.0, scale_height))
        if abs(scale_factor - 1.0) > 1e-3:
            new_w = max(1, int(region.size[0] * scale_factor))
            new_h = max(1, int(region.size[1] * scale_factor))
            region = region.resize((new_w, new_h), Image.BILINEAR)

        block_tiles.append({
            "idx": index,
            "image": region,
        })

    placements: List[Tuple[int, int]] = []
    current_x = tile_gap_pixels
    current_y = tile_gap_pixels
    row_height = 0
    for tile in block_tiles:
        tile_w, tile_h = tile["image"].size
        if current_x + tile_w + tile_gap_pixels > maximum_row_width:
            current_x = tile_gap_pixels
            current_y += row_height + tile_gap_pixels
            row_height = 0
        placements.append((current_x, current_y))
        current_x += tile_w + tile_gap_pixels
        if tile_h > row_height:
            row_height = tile_h
    canvas_width = maximum_row_width
    canvas_height = current_y + row_height + tile_gap_pixels if len(block_tiles) > 0 else (tile_gap_pixels * 2)

    montage = Image.new("RGB", (canvas_width, canvas_height), (0, 0, 0))
    for tile, (paste_x, paste_y) in zip(block_tiles, placements):
        montage.paste(tile["image"], (paste_x, paste_y))

    tile_rects: List[Dict] = []
    for tile, (paste_x, paste_y) in zip(block_tiles, placements):
        tile_w, tile_h = tile["image"].size
        tile_rects.append({
            "idx": tile["idx"],
            "x": paste_x,
            "y": paste_y,
            "w": tile_w,
            "h": tile_h,
        })

    montage_array = np.array(montage)
    ocr_result_full, elapsed = ocr_engine(montage_array)

    texts_by_block: Dict[int, List[Tuple[int, int, str]]] = {}
    for idx in range(1, len(color_blocks) + 1):
        texts_by_block[idx] = []

    if ocr_result_full:
        for item in ocr_result_full:
            box = item[0]
            text = item[1]
            xs = [int(point[0]) for point in box]
            ys = [int(point[1]) for point in box]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            center_x = (x1 + x2) / 2.0
            center_y = (y1 + y2) / 2.0

            for rect in tile_rects:
                if rect["x"] <= center_x <= rect["x"] + rect["w"] and rect["y"] <= center_y <= rect["y"] + rect["h"]:
                    texts_by_block[rect["idx"]].append((y1, x1, text))
                    break

    merged_texts: Dict[int, str] = {}
    for idx in range(1, len(color_blocks) + 1):
        items = texts_by_block[idx]
        if len(items) == 0:
            continue
        items.sort(key=lambda t: (t[0], t[1]))
        merged = " ".join([t[2] for t in items]).strip()
        chinese_only = extract_chinese(merged)
        if chinese_only:
            merged_texts[idx] = chinese_only

    return merged_texts


def detect_nodes_with_centers(image: Image.Image, min_area: int = 400) -> List[NodeDetected]:
    """
    对给定图像检测节点色块，返回每个节点的中文名、bbox 与中心。
    - 名称来自单次 OCR 蒙太奇识别并按块合并，仅保留中文。
    - 过滤过小区域（面积 < min_area）。
    """
    color_blocks, mask = _detect_bright_regions(image)

    filtered_blocks: List[Dict] = []
    for block in color_blocks:
        if block["area"] >= int(min_area):
            filtered_blocks.append(block)

    if len(filtered_blocks) == 0:
        return []

    ocr_engine = get_ocr_engine()
    merged_texts = _ocr_texts_for_blocks(image, filtered_blocks, ocr_engine)

    detected: List[NodeDetected] = []
    for index, block in enumerate(filtered_blocks, 1):
        block_x = block["x"]
        block_y = block["y"]
        block_w = block["width"]
        block_h = block["height"]
        center_x = int(block_x + block_w / 2)
        center_y = int(block_y + block_h / 2)
        area = int(block["area"])
        name_cn = merged_texts.get(index, "")
        detected.append(NodeDetected(
            name_cn=name_cn,
            bbox=(block_x, block_y, block_w, block_h),
            center=(center_x, center_y),
            area=area,
        ))

    return detected


