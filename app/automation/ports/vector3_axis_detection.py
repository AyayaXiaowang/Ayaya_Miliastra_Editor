# -*- coding: utf-8 -*-
"""
vector3_axis_detection: 三维向量轴标签检测与补全。

职责：
- 从 OCR 文本条目中解析 X/Y/Z 轴标签；
- 将 OCR 结果转换为统一的 bbox 映射；
- 在至少识别到两个轴时，基于等距关系推断缺失轴的相对位置。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
import re

from app.automation.vision.ocr_utils import normalize_ocr_bbox


AxisLabel = str
BBox = Tuple[int, int, int, int]


def match_axis_label_from_ocr(text_raw: str) -> Optional[AxisLabel]:
    """从 OCR 文本中匹配轴标签（X/Y/Z），带常见噪声容错。"""
    text = (text_raw or "").strip()
    if not text:
        return None

    text_upper = text.upper()
    text_normalized = text_upper.replace(" ", "")
    text_cleaned = (
        text_normalized.replace(":", "")
        .replace("：", "")
        .replace("=", "")
        .replace("-", "")
    )

    # 精确匹配
    if text_cleaned in ("X", "Y", "Z"):
        return text_cleaned

    # 容错：YO/Z0/X0/XO 等（尾随 O/0）
    if re.match(r"^[XYZ][O0]$", text_cleaned):
        return text_cleaned[0]

    # 容错：尾随一个标点
    if re.match(r"^[XYZ][:：=\-]$", text_normalized):
        return text_normalized[0]

    # 容错：尾随中文"轴/值"
    if (
        len(text_cleaned) == 2
        and text_cleaned[0] in ("X", "Y", "Z")
        and text_cleaned[1] in ("轴", "值")
    ):
        return text_cleaned[0]

    # 前缀匹配（最长3字符）：以 X/Y/Z 开头且其余仅包含允许字符
    if (len(text_cleaned) <= 3) and (text_cleaned[0] in ("X", "Y", "Z")):
        tail = text_cleaned[1:]
        if all(ch in ("O", "0") for ch in tail):
            return text_cleaned[0]

    return None


def build_axis_label_bbox_map(
    ocr_details: List[object],
) -> Dict[AxisLabel, BBox]:
    """从 OCR 详细结果构建 轴标签 → bbox 的映射。

    说明：
    - bbox 采用相对于 OCR 搜索区域的坐标系；
    - 只收集成功匹配到 X/Y/Z 轴标签的条目。
    """
    label_to_bbox: Dict[AxisLabel, BBox] = {}

    if not isinstance(ocr_details, list) or len(ocr_details) == 0:
        return label_to_bbox

    for item in ocr_details:
        if not isinstance(item, (list, tuple)):
            continue

        bbox_any = item[0] if len(item) > 0 else None
        text_item = str(item[1] if len(item) > 1 else "").strip()

        if not text_item:
            continue

        axis = match_axis_label_from_ocr(text_item)
        if axis is None:
            continue

        label_left, label_top, label_width, label_height = normalize_ocr_bbox(bbox_any)
        if label_width <= 0 or label_height <= 0:
            continue

        label_to_bbox[axis] = (label_left, label_top, label_width, label_height)

    return label_to_bbox


def infer_missing_axis_positions(
    recognized_labels: Dict[AxisLabel, BBox],
    search_region: Tuple[int, int, int, int],
) -> Dict[AxisLabel, BBox]:
    """基于已识别的轴标签推断缺失轴的位置（等距推断）。

    仅当至少识别到两个轴时才进行推断。
    """
    result: Dict[AxisLabel, BBox] = dict(recognized_labels)

    recognized_axes: List[AxisLabel] = [
        axis for axis in ("X", "Y", "Z") if axis in result
    ]
    if len(recognized_axes) < 2:
        return result

    widths = [int(result[axis][2]) for axis in recognized_axes]
    heights = [int(result[axis][3]) for axis in recognized_axes]
    average_width = int(sum(widths) / len(widths)) if widths else 12
    average_height = int(sum(heights) / len(heights)) if heights else 12

    centers = {
        axis: (
            int(result[axis][0] + result[axis][2] // 2),
            int(result[axis][1] + result[axis][3] // 2),
        )
        for axis in recognized_axes
    }
    average_center_y = int(
        sum(center[1] for center in centers.values()) / len(centers)
    )

    region_width = int(search_region[2])
    region_height = int(search_region[3])

    def clip_value(value: int, lower_bound: int, upper_bound: int) -> int:
        if value < lower_bound:
            return lower_bound
        if value > upper_bound:
            return upper_bound
        return value

    def infer_center_x_for_missing(missing_axis: AxisLabel) -> int:
        if missing_axis == "X" and ("Y" in centers and "Z" in centers):
            spacing = int(centers["Z"][0] - centers["Y"][0])
            return int(centers["Y"][0] - spacing)
        if missing_axis == "Z" and ("X" in centers and "Y" in centers):
            spacing = int(centers["Y"][0] - centers["X"][0])
            return int(centers["Y"][0] + spacing)
        if missing_axis == "Y" and ("X" in centers and "Z" in centers):
            return int((centers["X"][0] + centers["Z"][0]) / 2)
        return centers.get("Y", (0, 0))[0]

    for missing_axis in ("X", "Y", "Z"):
        if missing_axis in result:
            continue

        center_x = infer_center_x_for_missing(missing_axis)
        center_x = clip_value(
            center_x,
            average_width // 2,
            region_width - average_width // 2,
        )
        center_y = clip_value(
            average_center_y,
            average_height // 2,
            region_height - average_height // 2,
        )

        relative_left = int(center_x - average_width // 2)
        relative_top = int(center_y - average_height // 2)
        result[missing_axis] = (
            relative_left,
            relative_top,
            average_width,
            average_height,
        )

    return result


