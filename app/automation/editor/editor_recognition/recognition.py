# -*- coding: utf-8 -*-
"""
editor_recognition.recognition

兼容层：保留历史导入路径与对外 API。

原 `recognition.py` 过大，已按职责拆分为多个模块：
- `prewarm.py`：截图预热
- `view_mapping.py`：视口映射（原点投票/相对锚点/单锚点等算法编排）
- `visible_nodes.py`：可见节点识别与 bbox 绑定
- `position_sync.py`：识别后坐标偏移同步
"""

from __future__ import annotations

from .position_sync import synchronize_visible_nodes_positions
from .prewarm import prepare_for_connect
from .view_mapping import verify_and_update_view_mapping_by_recognition
from .visible_nodes import (
    _find_best_node_bbox,
    is_node_visible_by_id,
    recognize_visible_nodes,
)

__all__ = [
    "prepare_for_connect",
    "recognize_visible_nodes",
    "is_node_visible_by_id",
    "verify_and_update_view_mapping_by_recognition",
    "synchronize_visible_nodes_positions",
    "_find_best_node_bbox",
]


