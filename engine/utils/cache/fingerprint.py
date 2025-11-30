# -*- coding: utf-8 -*-
"""
邻域相对距离指纹（名称+左上角几何，不使用尺寸）

- 仅使用节点左上角坐标构建局部几何“比例向量”作为指纹
- 对模型（程序坐标）与检测（像素坐标）分别构建指纹
- 指纹比较使用 L1 距离（越小越相似），仅在近邻重叠数足够时才有效
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Sequence, Hashable, TypeVar
import json
import math

from engine.utils.graph.graph_utils import compute_stable_md5_from_data
from .cache_paths import get_graph_cache_dir


@dataclass
class Fingerprint:
    """单点邻域指纹（不包含名称信息）"""
    ratios: List[float]           # 归一化比例序列 [d2/d1, d3/d1, ...]
    nearest_distance: float       # d1 原始距离（便于调试）
    neighbor_count: int           # 参与的邻居数量（与 ratios 长度一致或一致-1）
    neighbors_indices: Optional[List[int]] = None  # 可选：邻居索引（模型=节点序号，检测=检测序号）
    center: Tuple[float, float] = (0.0, 0.0)       # 中心点坐标


Identifier = TypeVar("Identifier", bound=Hashable)


def _pairwise_dist(ax: float, ay: float, bx: float, by: float) -> float:
    dx = float(ax) - float(bx)
    dy = float(ay) - float(by)
    return math.hypot(dx, dy)


def _median_distance(values: List[float]) -> float:
    if not values:
        return 1.0
    mid_index = len(values) // 2
    if len(values) % 2 == 1:
        return float(values[mid_index]) if values[mid_index] > 1e-8 else 1.0
    median = 0.5 * (float(values[mid_index - 1]) + float(values[mid_index]))
    return median if median > 1e-8 else 1.0


def _build_fingerprint_map(
    identifiers: Sequence[Identifier],
    coordinates: Sequence[Tuple[float, float]],
    k_neighbors: int,
    round_ratio_digits: int,
) -> Dict[Identifier, Fingerprint]:
    if len(identifiers) != len(coordinates):
        raise ValueError("identifiers 与 coordinates 长度必须一致")

    total_points = len(identifiers)
    result: Dict[Identifier, Fingerprint] = {}
    if total_points == 0:
        return result

    xs = [float(point[0]) for point in coordinates]
    ys = [float(point[1]) for point in coordinates]

    for point_index, identifier in enumerate(identifiers):
        distance_pairs: List[Tuple[float, int]] = []
        for neighbor_index in range(total_points):
            if neighbor_index == point_index:
                continue
            distance_value = _pairwise_dist(xs[point_index], ys[point_index], xs[neighbor_index], ys[neighbor_index])
            distance_pairs.append((distance_value, neighbor_index))
        distance_pairs.sort(key=lambda item: item[0])

        if not distance_pairs:
            result[identifier] = Fingerprint(
                ratios=[],
                nearest_distance=0.0,
                neighbor_count=0,
                neighbors_indices=[],
                center=(xs[point_index], ys[point_index]),
            )
            continue

        neighbor_slice = distance_pairs[: max(1, k_neighbors)]
        nearest_distance = float(neighbor_slice[0][0])
        reference_distance = nearest_distance
        if reference_distance <= 1e-8:
            sorted_values = [float(distance) for distance, _ in neighbor_slice]
            reference_distance = _median_distance(sorted_values)

        ratios: List[float] = []
        for slice_index, (distance_value, _neighbor_idx) in enumerate(neighbor_slice):
            if slice_index == 0:
                continue
            ratios.append(round(float(distance_value) / float(reference_distance), int(round_ratio_digits)))

        neighbor_indices = [neighbor_idx for (_distance_value, neighbor_idx) in neighbor_slice]
        result[identifier] = Fingerprint(
            ratios=ratios,
            nearest_distance=nearest_distance,
            neighbor_count=len(neighbor_slice),
            neighbors_indices=neighbor_indices,
            center=(xs[point_index], ys[point_index]),
        )

    return result


def compute_layout_signature_for_model(nodes: List[Tuple[str, str, float, float]], round_digits: int = 3) -> str:
    """
    计算布局签名：使用 (中文名, 四舍五入坐标) 的稳定 MD5。
    nodes: [(node_id, title_cn, x, y), ...]
    """
    items = [
        (title_cn, round(float(x), round_digits), round(float(y), round_digits))
        for (_nid, title_cn, x, y) in nodes
    ]
    # 排序以获得稳定签名（名称、x、y）
    items_sorted = sorted(items, key=lambda t: (t[0], t[1], t[2]))
    return compute_stable_md5_from_data(items_sorted)


def build_graph_fingerprints_for_model(
    nodes: List[Tuple[str, float, float]],
    k_neighbors: int = 10,
    round_ratio_digits: int = 3,
) -> Dict[str, Fingerprint]:
    """
    为模型节点（程序坐标）构建指纹。
    nodes: [(node_id, x, y), ...]
    返回：{node_id: Fingerprint}
    """
    identifiers = [node_id for (node_id, _x, _y) in nodes]
    coordinates = [(float(x), float(y)) for (_node_id, x, y) in nodes]
    return _build_fingerprint_map(
        identifiers,
        coordinates,
        k_neighbors=k_neighbors,
        round_ratio_digits=round_ratio_digits,
    )


def build_fingerprints_for_detections(
    detections_xy: List[Tuple[float, float]],
    k_neighbors: int = 10,
    round_ratio_digits: int = 3,
) -> Dict[int, Fingerprint]:
    """
    为检测结果（像素坐标）构建指纹。
    detections_xy: [(x, y), ...] 与检测序号对齐
    返回：{det_index: Fingerprint}
    """
    identifiers = list(range(len(detections_xy)))
    coordinates = [(float(x), float(y)) for (x, y) in detections_xy]
    return _build_fingerprint_map(
        identifiers,
        coordinates,
        k_neighbors=k_neighbors,
        round_ratio_digits=round_ratio_digits,
    )


def compare_fingerprints_l1(
    fp_model: Fingerprint,
    fp_detect: Fingerprint,
    min_overlap_neighbors: int = 4,
) -> float:
    """
    计算两个指纹的 L1 距离（越小越相似）。不足重叠邻居数则返回一个大值。
    仅比较比例向量的最小长度前缀。
    """
    if fp_model is None or fp_detect is None:
        return float("inf")
    # ratios 长度代表 (neighbor_count - 1)
    overlap = min(len(fp_model.ratios), len(fp_detect.ratios))
    if overlap < int(min_overlap_neighbors):
        return float("inf")
    s = 0.0
    for i in range(overlap):
        s += abs(float(fp_model.ratios[i]) - float(fp_detect.ratios[i]))
    return float(s) / float(overlap)


def load_cached_fingerprints(
    workspace_path: Path,
    graph_id: str,
) -> Optional[dict]:
    """
    读取 app/runtime/cache/graph_cache/<graph_id>.json 中 result_data.metadata.fingerprints
    返回完整 fingerprints 字典（包含 version/layout_signature/params/items），不存在返回 None。
    """
    cache_dir = get_graph_cache_dir(Path(workspace_path))
    cache_file = cache_dir / f"{graph_id}.json"
    if not cache_file.exists():
        return None
    with open(cache_file, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if "result_data" not in payload:
        return None
    result_data = payload.get("result_data") or {}
    metadata = result_data.get("metadata") or {}
    fps = metadata.get("fingerprints")
    return fps



