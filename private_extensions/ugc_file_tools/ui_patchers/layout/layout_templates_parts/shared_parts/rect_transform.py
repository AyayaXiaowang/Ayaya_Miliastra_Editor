from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _set_rect_state_canvas_position_and_size(
    *,
    record: Dict[str, Any],
    state_index: int,
    canvas_position: Tuple[float, float],
    size: Tuple[float, float],
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
) -> None:
    """
    将“画布坐标（左下角原点）”写回为 RectTransform 的 anchored_position（固定锚点）。
    """
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        raise ValueError("record missing RectTransform component at field 505[2]")
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        raise ValueError("record field 505[2] must be dict")
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        raise ValueError("record field 505[2]/503 must be dict")
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        raise ValueError("record field 505[2]/503/13 must be dict")
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        raise ValueError("record field 505[2]/503/13/12 must be dict")
    state_list = node12.get("501")
    if not isinstance(state_list, list) or not state_list:
        raise ValueError("record field 505[2]/503/13/12/501 must be list and non-empty")

    target_state: Optional[Dict[str, Any]] = None
    for state in state_list:
        if not isinstance(state, dict):
            continue
        idx_value = state.get("501")
        idx = int(idx_value) if isinstance(idx_value, int) else 0
        if idx == int(state_index):
            target_state = state
            break
    if target_state is None:
        raise ValueError(f"record missing RectTransform state_index={int(state_index)}")

    transform = target_state.get("502")
    if not isinstance(transform, dict):
        raise ValueError("record rect state/502 must be dict")

    # anchor_min/max：protobuf 语义缺失为 0.0
    anchor_min = transform.get("502")
    anchor_max = transform.get("503")
    if not isinstance(anchor_min, dict) or not isinstance(anchor_max, dict):
        raise ValueError("record rect transform missing anchor_min/anchor_max")

    ax = float(anchor_min.get("501") or 0.0) if isinstance(anchor_min.get("501"), (int, float)) else 0.0
    ay = float(anchor_min.get("502") or 0.0) if isinstance(anchor_min.get("502"), (int, float)) else 0.0
    bx = float(anchor_max.get("501") or 0.0) if isinstance(anchor_max.get("501"), (int, float)) else 0.0
    by = float(anchor_max.get("502") or 0.0) if isinstance(anchor_max.get("502"), (int, float)) else 0.0
    if ax != bx or ay != by:
        raise ValueError("stretch anchor 未支持：anchor_min != anchor_max")

    canvas_size = canvas_size_by_state_index.get(int(state_index))
    if canvas_size is None:
        raise ValueError(f"missing canvas_size for state_index={int(state_index)}")
    canvas_w, canvas_h = float(canvas_size[0]), float(canvas_size[1])

    canvas_x, canvas_y = float(canvas_position[0]), float(canvas_position[1])
    width, height = float(size[0]), float(size[1])

    anchored_x = canvas_x - ax * canvas_w
    anchored_y = canvas_y - ay * canvas_h

    pos = transform.get("504")
    # 兼容：部分存档里 position 可能缺失或为占位 `<binary_data>`，写回时直接覆盖为标准 vec2 dict。
    if not isinstance(pos, dict):
        pos = {}
        transform["504"] = pos
    pos["501"] = float(anchored_x)
    pos["502"] = float(anchored_y)

    size_node = transform.get("505")
    # 兼容：部分存档里 size 可能缺失或为占位 `<binary_data>`，写回时直接覆盖为标准 vec2 dict。
    if not isinstance(size_node, dict):
        size_node = {}
        transform["505"] = size_node
    size_node["501"] = float(width)
    size_node["502"] = float(height)


def _set_rect_transform_layer(record: Dict[str, Any], layer: int) -> None:
    """
    样本字段路径：record['505'][2]['503']['13']['12']['503'] = layer

    备注：该字段缺失时视为默认；写入时直接加上 int 字段即可。
    """
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        raise ValueError("record missing RectTransform component at field 505[2]")
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        raise ValueError("record field 505[2] must be dict")
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        raise ValueError("record field 505[2]/503 must be dict")
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        raise ValueError("record field 505[2]/503/13 must be dict")
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        raise ValueError("record field 505[2]/503/13/12 must be dict")

    node12["503"] = int(layer)


def _try_extract_rect_transform_layer(record: Dict[str, Any]) -> Optional[int]:
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        return None
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        return None
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        return None
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        return None
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        return None
    value = node12.get("503")
    return int(value) if isinstance(value, int) else None


__all__ = [
    "_set_rect_state_canvas_position_and_size",
    "_set_rect_transform_layer",
    "_try_extract_rect_transform_layer",
]

