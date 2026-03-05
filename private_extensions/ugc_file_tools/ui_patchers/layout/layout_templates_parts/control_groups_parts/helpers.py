from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..shared import _set_rect_state_canvas_position_and_size


def _extract_name_for_debug(record: Dict[str, Any]) -> str:
    component_list = record.get("505")
    if not isinstance(component_list, list) or not component_list:
        return "<unknown>"
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        return "<unknown>"
    node12 = name_component.get("12")
    if not isinstance(node12, dict):
        return "<unknown>"
    value = node12.get("501")
    return str(value) if isinstance(value, str) else "<unknown>"


def _has_rect_transform_component(record: Dict[str, Any]) -> bool:
    """
    判定 record 是否为“可放置控件”（包含 RectTransform component）。

    约束背景：
    - 像“小地图/队伍信息/角色生命值条”等固有 HUD 控件在样本中不包含 RectTransform，
      不允许被打包进“界面控件组模板”。
    - 我们创建的可放置 UI 控件（按钮/进度条等）应当包含 RectTransform（路径 505[2]/503/13/12/501）。
    """
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 3:
        return False
    rect_component = component_list[2]
    if not isinstance(rect_component, dict):
        return False
    node503 = rect_component.get("503")
    if not isinstance(node503, dict):
        return False
    node13 = node503.get("13")
    if not isinstance(node13, dict):
        return False
    node12 = node13.get("12")
    if not isinstance(node12, dict):
        return False
    state_list = node12.get("501")
    if not isinstance(state_list, list) or not state_list:
        return False
    return True


def _assert_children_are_custom_placeable_controls(
    *,
    child_records: List[Dict[str, Any]],
    context: str,
) -> None:
    """
    护栏：禁止把“固有 HUD 控件”等不可放置 record 打包进控件组模板。
    """
    illegal: List[str] = []
    for rec in child_records:
        if _has_rect_transform_component(rec):
            continue
        name = _extract_name_for_debug(rec)
        guid_list = rec.get("501")
        guid_text = (
            str(guid_list[0])
            if isinstance(guid_list, list) and guid_list and isinstance(guid_list[0], int)
            else "?"
        )
        illegal.append(f"{name}(guid={guid_text})")
    if illegal:
        joined = ", ".join(illegal)
        raise ValueError(f"{context}：检测到不可打包的固有/不可放置控件（缺少 RectTransform），禁止写入控件组模板：{joined}")


def _try_extract_rect_state_canvas_position_and_size(
    *,
    record: Dict[str, Any],
    state_index: int,
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """
    尝试从 record 中提取某个 RectTransform state 的“画布坐标（左下角原点）”与 size。

    备注：
    - 仅支持固定锚点（anchor_min == anchor_max）
    - record 不包含 RectTransform / state 缺失时返回 None
    """
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
    state_list = node12.get("501")
    if not isinstance(state_list, list) or not state_list:
        return None

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
        return None

    transform = target_state.get("502")
    if not isinstance(transform, dict):
        return None

    anchor_min = transform.get("502")
    anchor_max = transform.get("503")
    if not isinstance(anchor_min, dict) or not isinstance(anchor_max, dict):
        return None

    ax = float(anchor_min.get("501") or 0.0) if isinstance(anchor_min.get("501"), (int, float)) else 0.0
    ay = float(anchor_min.get("502") or 0.0) if isinstance(anchor_min.get("502"), (int, float)) else 0.0
    bx = float(anchor_max.get("501") or 0.0) if isinstance(anchor_max.get("501"), (int, float)) else 0.0
    by = float(anchor_max.get("502") or 0.0) if isinstance(anchor_max.get("502"), (int, float)) else 0.0
    if ax != bx or ay != by:
        raise ValueError("stretch anchor 未支持：anchor_min != anchor_max")

    canvas_size = canvas_size_by_state_index.get(int(state_index))
    if canvas_size is None:
        return None
    canvas_w, canvas_h = float(canvas_size[0]), float(canvas_size[1])

    pos = transform.get("504")
    size_node = transform.get("505")
    if not isinstance(pos, dict) or not isinstance(size_node, dict):
        return None

    anchored_x = float(pos.get("501") or 0.0) if isinstance(pos.get("501"), (int, float)) else 0.0
    anchored_y = float(pos.get("502") or 0.0) if isinstance(pos.get("502"), (int, float)) else 0.0
    width = float(size_node.get("501") or 0.0) if isinstance(size_node.get("501"), (int, float)) else 0.0
    height = float(size_node.get("502") or 0.0) if isinstance(size_node.get("502"), (int, float)) else 0.0

    canvas_x = anchored_x + ax * canvas_w
    canvas_y = anchored_y + ay * canvas_h
    return (float(canvas_x), float(canvas_y)), (float(width), float(height))


def _apply_bbox_transform_to_children(
    *,
    child_records: List[Dict[str, Any]],
    state_index: int,
    target_center: Tuple[float, float],
    target_size: Tuple[float, float],
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
) -> None:
    """
    将一组子控件在某个 state 下的 bbox 线性变换到目标中心/尺寸：
    - 平移 + 非等比缩放（sx, sy）
    - 同时缩放各控件的 size
    """
    items: List[Tuple[Dict[str, Any], Tuple[float, float], Tuple[float, float]]] = []
    for rec in child_records:
        extracted = _try_extract_rect_state_canvas_position_and_size(
            record=rec,
            state_index=int(state_index),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )
        if extracted is None:
            continue
        pos, size = extracted
        items.append((rec, pos, size))

    if not items:
        raise ValueError(f"child_records 中没有可用的 RectTransform（state_index={int(state_index)}）")

    min_x = min(p[0] - s[0] / 2.0 for _, p, s in items)
    max_x = max(p[0] + s[0] / 2.0 for _, p, s in items)
    min_y = min(p[1] - s[1] / 2.0 for _, p, s in items)
    max_y = max(p[1] + s[1] / 2.0 for _, p, s in items)

    src_w = float(max_x - min_x)
    src_h = float(max_y - min_y)
    if src_w <= 0 or src_h <= 0:
        raise ValueError("child_records bbox 尺寸非法（<=0），无法缩放。")

    src_cx = float(min_x + max_x) / 2.0
    src_cy = float(min_y + max_y) / 2.0

    dst_cx = float(target_center[0])
    dst_cy = float(target_center[1])
    dst_w = float(target_size[0])
    dst_h = float(target_size[1])
    if dst_w <= 0 or dst_h <= 0:
        raise ValueError("target_size 必须为正数")

    sx = dst_w / src_w
    sy = dst_h / src_h

    for rec, (x, y), (w, h) in items:
        nx = dst_cx + (float(x) - src_cx) * sx
        ny = dst_cy + (float(y) - src_cy) * sy
        nw = float(w) * sx
        nh = float(h) * sy
        _set_rect_state_canvas_position_and_size(
            record=rec,
            state_index=int(state_index),
            canvas_position=(float(nx), float(ny)),
            size=(float(nw), float(nh)),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )


__all__ = [
    "_extract_name_for_debug",
    "_has_rect_transform_component",
    "_assert_children_are_custom_placeable_controls",
    "_try_extract_rect_state_canvas_position_and_size",
    "_apply_bbox_transform_to_children",
]

