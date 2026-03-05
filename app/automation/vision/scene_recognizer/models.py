from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class RecognizedPort:
    side: str  # 'left' | 'right'
    index: Optional[int]
    kind: str  # 模板名，如 'data', 'flow', 'settings', 'warning'
    bbox: Tuple[int, int, int, int]
    center: Tuple[int, int]
    confidence: float


@dataclass
class RecognizedNode:
    title_cn: str
    rect: Tuple[int, int, int, int]  # x, y, width, height（相对输入图像坐标）
    ports: List[RecognizedPort]
    # 节点标题栏/顶部色块区域的高度（像素，画布坐标系）。
    # 用于在端口模板匹配与 OCR 标题提取时跳过顶部区域，避免误把标题栏内容当作端口或候选文本。
    header_height_px: int = 0


@dataclass
class TemplateMatchDebugInfo:
    """模板匹配调试信息（含被去重抑制的候选）。

    status:
        - "kept"：最终保留并参与端口构建的模板命中
        - "suppressed_nms"：在 NMS 阶段被抑制的候选（空间重叠）
        - "suppressed_same_row"：在同行去重阶段被抑制的候选（同一行仅保留一个）
    suppression_kind:
        - "nms"：NMS 抑制
        - "same_row"：同行去重
        - None：未被抑制
    """

    template_name: str
    bbox: Tuple[int, int, int, int]
    side: str
    index: Optional[int]
    confidence: float
    status: str
    suppression_kind: Optional[str]
    overlap_target_bbox: Optional[Tuple[int, int, int, int]]
    iou: Optional[float]


@dataclass(frozen=True)
class SceneRecognizerTuning:
    """一步式识别的可调阈值集合。

    说明：
    - 这些阈值多数与分辨率/Windows 缩放强相关，调用方应优先从 profile 推导；
    - 本模块保持默认值以兼容旧调用方（未显式传参时行为不变）。
    """

    # 端口模板：同行去重的 Y 容差（像素）
    port_same_row_y_tolerance_px: int = 10

    # 端口模板：NMS 抑制的 IoU 阈值（0-1，越小越严格）
    port_template_nms_iou_threshold: float = 0.10

    # 色块识别：垂直/水平扫描去飞线阈值
    color_scan_min_height_threshold_px: int = 15
    color_scan_min_width_threshold_px: int = 50

    # 色块合并：允许的最大垂直间隔（像素）
    color_merge_max_vertical_gap_px: int = 20


