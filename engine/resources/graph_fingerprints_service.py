"""节点图指纹计算服务。

职责：
- 将“布局签名 + 指纹 items”计算逻辑从 GraphResourceService 中抽离，供加载与缓存增量更新复用。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from engine.configs.settings import settings
from engine.graph.models.graph_model import GraphModel
from engine.utils.cache.fingerprint import (
    build_graph_fingerprints_for_model,
    compute_layout_signature_for_model,
)


class GraphFingerprintsService:
    """负责生成 `metadata["fingerprints"]` 的统一实现。"""

    def build_fingerprints_from_graph_model(self, graph_model: GraphModel) -> Optional[Dict[str, Any]]:
        if not bool(getattr(settings, "FINGERPRINT_ENABLED", False)):
            return None

        nodes_for_signature: List[Tuple[str, str, float, float]] = []
        nodes_for_fingerprints: List[Tuple[str, float, float]] = []

        for node_obj in graph_model.nodes.values():
            node_id = str(getattr(node_obj, "id", "") or "")
            title_cn = str(getattr(node_obj, "title", "") or "")
            position = getattr(node_obj, "pos", (0.0, 0.0)) or (0.0, 0.0)
            x_pos = float(position[0]) if len(position) > 0 else 0.0
            y_pos = float(position[1]) if len(position) > 1 else 0.0

            nodes_for_signature.append((node_id, title_cn, x_pos, y_pos))
            nodes_for_fingerprints.append((node_id, x_pos, y_pos))

        return self._build_fingerprints(nodes_for_signature, nodes_for_fingerprints)

    def build_fingerprints_from_serialized_nodes(
        self,
        nodes_list: Iterable[Dict[str, Any]],
        *,
        require_nodes: bool = True,
    ) -> Optional[Dict[str, Any]]:
        if not bool(getattr(settings, "FINGERPRINT_ENABLED", False)):
            return None

        nodes_for_signature: List[Tuple[str, str, float, float]] = []
        nodes_for_fingerprints: List[Tuple[str, float, float]] = []

        for node_dict in nodes_list:
            if not isinstance(node_dict, dict):
                continue
            node_id = str(node_dict.get("id", "") or "")
            title_cn = str(node_dict.get("title", "") or "")
            position = node_dict.get("pos", node_dict.get("position", [0.0, 0.0]))
            position = position or [0.0, 0.0]
            x_pos = float(position[0]) if len(position) > 0 else 0.0
            y_pos = float(position[1]) if len(position) > 1 else 0.0

            nodes_for_signature.append((node_id, title_cn, x_pos, y_pos))
            nodes_for_fingerprints.append((node_id, x_pos, y_pos))

        if require_nodes and not nodes_for_fingerprints:
            return None

        return self._build_fingerprints(nodes_for_signature, nodes_for_fingerprints)

    @staticmethod
    def _build_fingerprints(
        nodes_for_signature: List[Tuple[str, str, float, float]],
        nodes_for_fingerprints: List[Tuple[str, float, float]],
    ) -> Dict[str, Any]:
        layout_signature = compute_layout_signature_for_model(nodes_for_signature)
        fingerprint_map = build_graph_fingerprints_for_model(
            nodes_for_fingerprints,
            k_neighbors=int(getattr(settings, "FINGERPRINT_K", 6)),
            round_ratio_digits=int(getattr(settings, "FINGERPRINT_ROUND_DIGITS", 3)),
        )

        items: Dict[str, Dict[str, Any]] = {}
        for node_id, fingerprint in fingerprint_map.items():
            items[node_id] = {
                "ratios": list(fingerprint.ratios),
                "nearest_distance": float(fingerprint.nearest_distance),
                "neighbor_count": int(fingerprint.neighbor_count),
                "center": [float(fingerprint.center[0]), float(fingerprint.center[1])],
            }

        return {
            "version": 1,
            "layout_signature": layout_signature,
            "params": {
                "k": int(getattr(settings, "FINGERPRINT_K", 6)),
                "round": int(getattr(settings, "FINGERPRINT_ROUND_DIGITS", 3)),
            },
            "items": items,
        }


