# -*- coding: utf-8 -*-
"""
OCR 工具与中文文本辅助函数。

职责：
- 提供 RapidOCR 引擎的进程内懒加载与复用；
- 提供中文提取等与 OCR 结果后处理相关的小工具。
"""

from __future__ import annotations

from typing import Any, List, Tuple
from PIL import Image
import hashlib

from app.automation import capture as editor_capture


def get_ocr_engine() -> Any:
    """统一入口：返回全局 OCR 引擎实例，由 editor_capture 管理生命周期。"""
    return editor_capture.get_ocr_engine()


def extract_chinese(text: str) -> str:
    """从给定文本中提取连续中文字符，保留原始顺序。

    说明：
    - 主要用于从 OCR 结果中提取中文标题；
    - 非中文字符会被忽略。
    """
    if text is None:
        return ""
    result_chars: List[str] = []
    for ch in str(text):
        code = ord(ch)
        if 0x4E00 <= code <= 0x9FFF:
            result_chars.append(ch)
    return "".join(result_chars)


def normalize_ocr_bbox(bbox_any: Any) -> Tuple[int, int, int, int]:
    """将 OCR 返回的多种 bbox 格式统一为 (left, top, width, height)。"""
    if isinstance(bbox_any, (list, tuple)) and len(bbox_any) == 4:
        if isinstance(bbox_any[0], (list, tuple)):
            xs = [float(bbox_any[k][0]) for k in range(4)]
            ys = [float(bbox_any[k][1]) for k in range(4)]
            left_x = int(min(xs))
            top_y = int(min(ys))
            right_x = int(max(xs))
            bottom_y = int(max(ys))
            return (left_x, top_y, max(1, right_x - left_x), max(1, bottom_y - top_y))
        left = int(float(bbox_any[0]))
        top = int(float(bbox_any[1]))
        right = int(float(bbox_any[2]))
        bottom = int(float(bbox_any[3]))
        return (left, top, max(1, right - left), max(1, bottom - top))
    return (0, 0, 0, 0)


def get_bbox_anchor_topleft(bbox_any: Any) -> Tuple[int, int]:
    """返回 OCR bbox 的锚点坐标（窗口坐标系），统一采用左上角。

    所有与“节点位置”相关的几何逻辑（视口拟合 / 可见性判定 / 创建锚点推断等）
    必须使用该函数返回的左上角坐标，保持与 `GraphModel.NodeModel.pos` 的语义一致。
    """
    left, top, _width, _height = normalize_ocr_bbox(bbox_any)
    return (int(left), int(top))


def get_bbox_center(bbox_any: Any) -> Tuple[int, int]:
    """返回 OCR bbox 的几何中心坐标（窗口坐标系）。

    仅用于需要“视觉居中”效果的场景（例如点击文本框中心、绘制圆形高亮等）。
    与节点几何基准（左上角）无关的地方可以继续使用该函数。
    """
    left, top, width, height = normalize_ocr_bbox(bbox_any)
    return (
        int(left + max(1, width) / 2),
        int(top + max(1, height) / 2),
    )


def fingerprint_region(image: Image.Image, region: Tuple[int, int, int, int]) -> str:
    """对指定区域生成内容摘要哈希，用于检测画面是否发生变化。"""
    rx, ry, rw, rh = region
    crop = image.crop((int(rx), int(ry), int(rx + rw), int(ry + rh)))
    hasher = hashlib.blake2b(digest_size=16)
    hasher.update(crop.tobytes())
    hasher.update(str(crop.size).encode("ascii"))
    return hasher.hexdigest()



