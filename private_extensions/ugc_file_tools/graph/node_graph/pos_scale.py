from __future__ import annotations

import math
from typing import Any, Dict, Mapping


DEFAULT_NODE_POS_SCALE: float = 2.0


def _is_positive_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and (not isinstance(value, bool))
        and math.isfinite(float(value))
        and float(value) > 0.0
    )


def ensure_positive_finite_node_pos_scale(*, value: Any, source: str = "node_pos_scale") -> float:
    if not _is_positive_finite_number(value):
        raise ValueError(f"{source} 必须为有限的正数（got: {value!r}）")
    return float(value)


def resolve_node_pos_scale_from_graph_json(
    *,
    graph_json_object: Mapping[str, Any],
    fallback_scale: float = DEFAULT_NODE_POS_SCALE,
) -> float:
    fallback = ensure_positive_finite_node_pos_scale(value=fallback_scale, source="fallback_scale")
    top_meta = graph_json_object.get("metadata")
    if isinstance(top_meta, Mapping):
        raw_scale = top_meta.get("node_pos_scale")
        if _is_positive_finite_number(raw_scale):
            return float(raw_scale)
    return float(fallback)


def set_node_pos_scale_in_graph_json(*, graph_json_object: Dict[str, Any], node_pos_scale: float) -> float:
    scale = ensure_positive_finite_node_pos_scale(value=node_pos_scale, source="node_pos_scale")
    metadata = graph_json_object.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        graph_json_object["metadata"] = metadata
    metadata["node_pos_scale"] = float(scale)
    return float(scale)


