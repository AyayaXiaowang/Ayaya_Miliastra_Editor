# -*- coding: utf-8 -*-
"""
editor_recognition

识别与视口映射子包入口：聚合高层 API 并暴露数据结构，具体实现分布在
`recognition`, `mappings`, `fallbacks`, `constants`, `models`, `logging_utils` 等子模块中。
"""

from .models import MappingData, PairCollections, ViewMappingFitResult
from .recognition import (
    _find_best_node_bbox,
    is_node_visible_by_id,
    prepare_for_connect,
    recognize_visible_nodes,
    synchronize_visible_nodes_positions,
    verify_and_update_view_mapping_by_recognition,
)

__all__ = [
    "MappingData",
    "PairCollections",
    "ViewMappingFitResult",
    "_find_best_node_bbox",
    "prepare_for_connect",
    "recognize_visible_nodes",
    "synchronize_visible_nodes_positions",
    "is_node_visible_by_id",
    "verify_and_update_view_mapping_by_recognition",
]

