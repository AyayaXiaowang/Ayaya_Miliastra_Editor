# -*- coding: utf-8 -*-
"""
editor_recognition.models

数据结构定义：识别映射构建过程中的配对信息以及拟合结果。
"""

from dataclasses import dataclass
from typing import Dict

from engine.graph.models.graph_model import NodeModel


@dataclass
class MappingData:
    name_to_model_nodes: Dict[str, list[NodeModel]]
    name_to_detections: Dict[str, list[tuple[int, int, int, int]]]
    name_to_det_indices: Dict[str, list[int]]
    shared_names: list[str]
    unique_model_names: list[str]
    unique_detected_names: list[str]


@dataclass
class PairCollections:
    base_pairs_prog: list[tuple[float, float]]
    base_pairs_win: list[tuple[float, float]]
    all_pairs_prog: list[tuple[float, float]]
    all_pairs_win: list[tuple[float, float]]


@dataclass
class ViewMappingFitResult:
    success: bool
    strategy: str

