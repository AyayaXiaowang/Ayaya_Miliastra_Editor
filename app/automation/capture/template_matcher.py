# -*- coding: utf-8 -*-
"""
模板匹配模块
负责在截图中查找模板图片
"""

import os
import cv2
import numpy as np
from typing import Tuple, Optional
from PIL import Image

from .cache import (
    get_template_match_cache,
    get_template_info_cached,
    _hash_ndarray,
    create_lru_cache,
)
from .roi_constraints import resolve_search_region
from .emitters import emit_visual_overlay, emit_log_message
from .reference_panels import build_reference_panel_payload

_TEMPLATE_PIXEL_CACHE_CAPACITY = 32
_TEMPLATE_PIXEL_CACHE = create_lru_cache(_TEMPLATE_PIXEL_CACHE_CAPACITY)


def _get_template_pixels(template_path: str, digest_hex: str) -> np.ndarray:
    """返回指定模板的 BGR 像素，带 LRU 缓存以避免重复加载。"""
    cache_key = f"{digest_hex}:{template_path}"
    cached = _TEMPLATE_PIXEL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    with Image.open(template_path) as template_img:
        template_cv = cv2.cvtColor(np.array(template_img), cv2.COLOR_RGB2BGR)
    _TEMPLATE_PIXEL_CACHE.set(cache_key, template_cv)
    return template_cv


def match_template(
    screenshot: Image.Image,
    template_path: str,
    search_region: Optional[Tuple[int, int, int, int]] = None,
    threshold: float = 0.8,
) -> Optional[Tuple[int, int, int, int, float]]:
    """模板匹配，查找模板图片在截图中的位置
    
    Args:
        screenshot: PIL Image对象
        template_path: 模板图片路径
        search_region: 搜索区域 (x, y, width, height)，如果为None则搜索整个截图
        threshold: 匹配阈值（0.0-1.0）
        
    Returns:
        (match_x, match_y, match_w, match_h, confidence) 或 None
    """
    if not os.path.exists(template_path):
        return None
    
    # 模板基本信息（内容哈希、尺寸、文件名）
    digest_hex, (tpl_w, tpl_h), basename = get_template_info_cached(template_path)

    normalized_region = (
        (int(search_region[0]), int(search_region[1]), int(search_region[2]), int(search_region[3]))
        if search_region
        else None
    )
    effective_region = resolve_search_region(
        screenshot,
        normalized_region,
        log_label="[模板]",
    )
    if effective_region is None and normalized_region is not None:
        effective_region = normalized_region

    # 若限制后区域为空，直接返回未命中并推送一次可视化
    if effective_region and (int(effective_region[2]) <= 0 or int(effective_region[3]) <= 0):
        rects_empty: list[dict] = []
        rects_empty.append({
            'bbox': (int(effective_region[0]), int(effective_region[1]), int(effective_region[2]), int(effective_region[3])),
            'color': (160, 160, 255),
            'label': f"模板搜索: {os.path.basename(str(template_path))}"
        })
        header_text = f"模板匹配: {os.path.basename(str(template_path))} 未命中"
        emit_visual_overlay(screenshot, { 'rects': rects_empty, 'circles': [], 'header': header_text })
        emit_log_message(f"[模板] {os.path.basename(str(template_path))} 命中=否 阈值={float(threshold):.2f}")
        return None

    # 构建搜索图像（区域裁剪）
    if effective_region:
        search_img = screenshot.crop((
            int(effective_region[0]),
            int(effective_region[1]),
            int(effective_region[0]) + int(effective_region[2]),
            int(effective_region[1]) + int(effective_region[3])
        ))
    else:
        search_img = screenshot

    # 将搜索图像转 cv2 并哈希
    search_cv = cv2.cvtColor(np.array(search_img), cv2.COLOR_RGB2BGR)
    search_hash = _hash_ndarray(search_cv)

    # 先尝试从缓存读取匹配结果（max_val, max_loc）
    tm_cache = get_template_match_cache()
    tm_key = f"{digest_hex}|{search_hash}"
    cached = tm_cache.get(tm_key)
    result = None  # 仅在本次计算时可用，用于构建多候选可视化
    if cached is not None:
        max_val, max_loc = float(cached[0]), tuple(cached[1])
    else:
        # 仅当无缓存时才需要加载并转换模板像素
        template_cv = _get_template_pixels(template_path, digest_hex)
        # 边界：若模板尺寸大于搜索图像，直接视为未命中
        sh, sw = search_cv.shape[:2]
        th, tw = template_cv.shape[:2]
        if int(th) > int(sh) or int(tw) > int(sw):
            max_val, max_loc = 0.0, (0, 0)
        else:
            result = cv2.matchTemplate(search_cv, template_cv, cv2.TM_CCOEFF_NORMED)
            _min_val, max_val, _min_loc, max_loc = cv2.minMaxLoc(result)
        tm_cache.set(tm_key, (float(max_val), (int(max_loc[0]), int(max_loc[1]))))

    hit = bool(max_val > float(threshold))
    abs_x = None
    abs_y = None
    if hit:
        match_x, match_y = int(max_loc[0]), int(max_loc[1])
        if effective_region:
            abs_x = int(effective_region[0] + match_x)
            abs_y = int(effective_region[1] + match_y)
        else:
            abs_x = int(match_x)
            abs_y = int(match_y)

    # 可视化与日志（命中与否都推送一次画面）
    rects: list[dict] = []
    if effective_region:
        rects.append({
            'bbox': (int(effective_region[0]), int(effective_region[1]), int(effective_region[2]), int(effective_region[3])),
            'color': (160, 160, 255),
            'label': f"模板搜索: {basename}"
        })

    # 若本次计算得到了完整的匹配结果矩阵，则提取所有高于阈值的候选，用于调试与可视化
    if result is not None:
        ys, xs = np.where(result >= float(threshold))
        if ys.size > 0 and xs.size > 0:
            scores = result[ys, xs]
            order = np.argsort(scores)[::-1]
            max_candidates = 10
            for rank, idx in enumerate(order[:max_candidates]):
                rel_y = int(ys[idx])
                rel_x = int(xs[idx])
                score = float(scores[idx])
                if effective_region:
                    cand_x = int(effective_region[0] + rel_x)
                    cand_y = int(effective_region[1] + rel_y)
                else:
                    cand_x = int(rel_x)
                    cand_y = int(rel_y)
                rects.append({
                    'bbox': (cand_x, cand_y, int(tpl_w), int(tpl_h)),
                    'color': (255, 200, 0),
                    'label': f"候选{rank + 1} {basename} {score:.2f}"
                })

    if hit and abs_x is not None and abs_y is not None:
        # 追加一层“最终命中”高亮框，便于与其它候选区分
        rects.append({
            'bbox': (int(abs_x), int(abs_y), int(tpl_w), int(tpl_h)),
            'color': (255, 120, 120),
            'label': f"命中 {basename} {float(max_val):.2f}"
        })
        emit_log_message(f"[模板] {basename} 命中=是 置信度={float(max_val):.2f} 位置=({int(abs_x)},{int(abs_y)},{int(tpl_w)},{int(tpl_h)})")
    else:
        emit_log_message(f"[模板] {basename} 命中=否 阈值={float(threshold):.2f}")
    header_text = f"模板匹配: {basename} " + ("命中" if hit else "未命中")
    overlay_payload = {
        'rects': rects,
        'circles': [],
        'header': header_text,
        'reference_panel': build_reference_panel_payload(
            title=f"模板: {basename}",
            text=f"阈值 {float(threshold):.2f}",
            image_path=str(template_path),
        ),
    }
    emit_visual_overlay(screenshot, overlay_payload)

    if hit and abs_x is not None and abs_y is not None:
        return (int(abs_x), int(abs_y), int(tpl_w), int(tpl_h), float(max_val))
    return None


def match_template_candidates(
    screenshot: Image.Image,
    template_path: str,
    search_region: Optional[Tuple[int, int, int, int]] = None,
    threshold: float = 0.8,
) -> list[Tuple[int, int, float]]:
    """模板匹配（多候选版），返回所有置信度不低于阈值的候选中心点及其置信度。
    
    说明：
    - 不做可视化与日志输出，仅用于在同一行/区域内根据“距离目标点最近”的原则挑选模板命中；
    - 仅返回 (center_x, center_y, confidence) 列表，调用方负责结合端口位置与侧别做最终决策。
    """
    if not os.path.exists(template_path):
        return []

    digest_hex, (tpl_w, tpl_h), _ = get_template_info_cached(template_path)

    normalized_region = (
        (int(search_region[0]), int(search_region[1]), int(search_region[2]), int(search_region[3]))
        if search_region
        else None
    )
    effective_region = resolve_search_region(
        screenshot,
        normalized_region,
        log_label="[模板]",
    )
    if effective_region is None and normalized_region is not None:
        effective_region = normalized_region

    if effective_region and (int(effective_region[2]) <= 0 or int(effective_region[3]) <= 0):
        return []

    if effective_region:
        search_img = screenshot.crop((
            int(effective_region[0]),
            int(effective_region[1]),
            int(effective_region[0]) + int(effective_region[2]),
            int(effective_region[1]) + int(effective_region[3])
        ))
    else:
        search_img = screenshot

    search_cv = cv2.cvtColor(np.array(search_img), cv2.COLOR_RGB2BGR)
    template_cv = _get_template_pixels(template_path, digest_hex)

    search_height, search_width = search_cv.shape[:2]
    template_height, template_width = template_cv.shape[:2]
    if int(template_height) > int(search_height) or int(template_width) > int(search_width):
        return []

    result = cv2.matchTemplate(search_cv, template_cv, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(result >= float(threshold))
    if ys.size == 0 or xs.size == 0:
        return []

    scores = result[ys, xs]
    order = np.argsort(scores)[::-1]
    max_candidates = 32
    candidates: list[Tuple[int, int, float]] = []
    for idx in order[:max_candidates]:
        rel_y = int(ys[idx])
        rel_x = int(xs[idx])
        score = float(scores[idx])
        if effective_region:
            top_left_x = int(effective_region[0] + rel_x)
            top_left_y = int(effective_region[1] + rel_y)
        else:
            top_left_x = int(rel_x)
            top_left_y = int(rel_y)
        center_x = int(top_left_x + int(tpl_w) // 2)
        center_y = int(top_left_y + int(tpl_h) // 2)
        candidates.append((center_x, center_y, score))
    return candidates

