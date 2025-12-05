# -*- coding: utf-8 -*-
"""
OCR 模块
负责文字识别功能

说明：
- 为了避免在未实际使用 OCR 时就强制加载 RapidOCR/ONNXRuntime，
  本模块对 RapidOCR 采用惰性导入，仅在第一次调用 ``get_ocr_engine`` 时才导入依赖。
"""

from __future__ import annotations

from typing import Tuple, List, Any, Union, Optional, TYPE_CHECKING

import numpy as np
from PIL import Image

from .cache import get_ocr_cache, _hash_ndarray
from .roi_constraints import clip_region_with_graph
from .emitters import emit_visual_overlay, emit_log_message
from .overlay_helpers import build_overlay_for_text_region
from .reference_panels import build_reference_panel_payload

if TYPE_CHECKING:
    # 仅用于类型检查，运行时不导入 RapidOCR，避免环境缺失时在导入阶段就失败
    from rapidocr_onnxruntime import RapidOCR

_OCR_ENGINE: Optional["RapidOCR"] = None


def get_ocr_engine() -> "RapidOCR":
    """懒加载并复用 RapidOCR 引擎实例。"""
    global _OCR_ENGINE
    if _OCR_ENGINE is None:
        # 在首次实际使用时才导入 RapidOCR，避免在未使用 OCR 的场景中强依赖 onnxruntime
        from rapidocr_onnxruntime import RapidOCR as RapidOCRImpl

        _OCR_ENGINE = RapidOCRImpl()
    return _OCR_ENGINE


def ocr_recognize_region(
    screenshot: Image.Image,
    region: Tuple[int, int, int, int],
    return_details: bool = False,
    exclude_top_pixels: int = 0,
) -> Union[str, Tuple[str, List[Any]]]:
    """使用RapidOCR识别指定区域的文字（实现方式与 capture_beyondeditor.py 一致）
    
    Args:
        screenshot: PIL Image对象
        region: 区域坐标 (x, y, width, height)
        return_details: 是否返回详细结果（包含坐标信息）
        exclude_top_pixels: 排除顶部N像素的区域（用于排除搜索框等UI元素）
    
    Returns:
        如果return_details=False: 识别的文本字符串
        如果return_details=True: (文本字符串, 详细结果列表)
                              详细结果格式: [(bbox, text, score), ...]
                              如果设置了exclude_top_pixels，结果会自动过滤掉顶部区域的文本
    """
    region_tuple = (int(region[0]), int(region[1]), int(region[2]), int(region[3]))
    x, y, w, h = clip_region_with_graph(
        screenshot,
        region_tuple,
        log_label="[OCR]",
    )
    
    if w <= 0 or h <= 0:
        return ("", []) if return_details else ""
    
    if w < 20 or h < 10:
        return ("", []) if return_details else ""
    
    max_dimension = 4000
    if w > max_dimension or h > max_dimension:
        return ("", []) if return_details else ""
    
    region_image = screenshot.crop((x, y, x + w, y + h))
    img_array = np.array(region_image)

    # 基于内容哈希的 OCR 结果缓存（缓存 raw result，参数过滤在下方执行）
    ocr_cache = get_ocr_cache()
    ocr_key = _hash_ndarray(img_array)
    cached_raw = ocr_cache.get(ocr_key)
    if cached_raw is None:
        ocr_engine = get_ocr_engine()
        result, _elapse = ocr_engine(img_array)
        ocr_cache.set(ocr_key, result or [])
    else:
        result = cached_raw

    # 构建叠加层（统一推送到监控）：始终标注识别区域，若有明细则追加每行文本框
    texts_joined = ""
    if result:
        # 如果设置了排除顶部区域，过滤结果
        if exclude_top_pixels > 0:
            filtered_result = []
            for item in result:
                bbox = item[0]
                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    if isinstance(bbox[0], (list, tuple)):
                        center_y = (float(bbox[0][1]) + float(bbox[1][1]) + float(bbox[2][1]) + float(bbox[3][1])) / 4.0
                    else:
                        center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
                    if center_y >= float(exclude_top_pixels):
                        filtered_result.append(item)
            result = filtered_result

        texts = [str(line[1]) for line in result]
        texts_joined = ' '.join(texts).strip()

    overlay_rect = build_overlay_for_text_region(
        (int(x), int(y), int(w), int(h)),
        result,
        base_label="OCR 区域",
        detail_color=(0, 200, 120),
    )
    header_text = (
        "OCR: " + (texts_joined[:60] + ("…" if len(texts_joined) > 60 else ""))
        if texts_joined
        else "OCR 识别"
    )
    overlays = {
        **overlay_rect,
        'circles': [],
        'header': header_text,
        'reference_panel': build_reference_panel_payload(
            title='OCR 文本',
            text=texts_joined if texts_joined else "（无识别结果）",
        ),
    }
    emit_visual_overlay(screenshot, overlays)
    preview = texts_joined if texts_joined else ""
    if preview:
        emit_log_message(f"[OCR] 区域=({int(x)},{int(y)},{int(w)},{int(h)}) 文本='{preview[:60]}'")
    else:
        emit_log_message(f"[OCR] 区域=({int(x)},{int(y)},{int(w)},{int(h)}) 文本=''")

    if return_details:
        return (texts_joined, result or [])
    else:
        return texts_joined

