from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional


@dataclass
class PortDetected:
    """视觉识别到的端口信息（核心共享类型）。

    说明：
    - 上层依赖该结构进行端口筛选与连线决策；
    - kind 字段来自模板/识别的原始类型字符串；
      上层可通过 core.automation._ports.normalize_kind_text 归一化为 flow/data/other；
    - confidence 表示底层模板匹配的置信度（0~1），仅在视觉识别链路可用时填充，用于调试展示。
    """
    name_cn: str
    bbox: Tuple[int, int, int, int]  # x, y, w, h（窗口坐标系）
    center: Tuple[int, int]          # 端口中心（窗口坐标系）
    side: str                        # "left" | "right" | "unknown"
    kind: str = "unknown"           # 模板类型：data/list/generic/process/settings/warning/unknown
    index: Optional[int] = None      # 同侧序号（0基），不含 settings/warning
    confidence: Optional[float] = None  # 模板匹配置信度（0~1），可选


__all__ = ["PortDetected"]


