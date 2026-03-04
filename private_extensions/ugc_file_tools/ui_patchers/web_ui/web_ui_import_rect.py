from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    set_rect_state_canvas_position_and_size as _set_rect_state_canvas_position_and_size,
)


def parse_float_pair(value: Any, *, name: str) -> Tuple[float, float]:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], (int, float))
        and isinstance(value[1], (int, float))
    ):
        return float(value[0]), float(value[1])
    raise ValueError(f"{name} must be [x,y] numeric list, got: {value!r}")


def web_top_left_to_canvas_position(
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    pivot: Tuple[float, float],
    canvas_height: float,
) -> Tuple[float, float]:
    """
    Web JSON:
    - position = (left, top), 原点在画布左上角，y 向下

    RectTransform：
    - 写回的是 pivot 的“画布坐标”（原点在画布左下角，y 向上）
    """
    pivot_x, pivot_y = float(pivot[0]), float(pivot[1])
    x_top_left = float(left) + pivot_x * float(width)
    y_top_left = float(top) + (1.0 - pivot_y) * float(height)
    return float(x_top_left), float(canvas_height) - float(y_top_left)


def _choose_fixed_anchor_component(value01: float) -> float:
    """
    将归一化坐标（0..1）吸附到 {0, 0.5, 1}：
    - 贴边元素（靠左/靠右、靠上/靠下）应使用边缘 anchor，避免画布尺寸变化时“相对中心漂移”
    - 中间元素使用 0.5 保持居中语义
    """
    v = float(value01)
    if not math.isfinite(v):
        return 0.5
    # 经验阈值：<35% 视为靠左/下，>65% 视为靠右/上
    if v <= 0.35:
        return 0.0
    if v >= 0.65:
        return 1.0
    return 0.5


def _ensure_vec2_node(parent: Dict[str, Any], field_key: str) -> Dict[str, Any]:
    node = parent.get(field_key)
    if not isinstance(node, dict):
        node = {}
        parent[field_key] = node
    return node


def _set_fixed_anchor_min_max_in_place(transform: Dict[str, Any], *, ax: float, ay: float) -> None:
    anchor_min = _ensure_vec2_node(transform, "502")
    anchor_max = _ensure_vec2_node(transform, "503")
    anchor_min["501"] = float(ax)
    anchor_min["502"] = float(ay)
    anchor_max["501"] = float(ax)
    anchor_max["502"] = float(ay)


def write_rect_states_from_web_rect(
    record: Dict[str, Any],
    *,
    web_left: float,
    web_top: float,
    web_width: float,
    web_height: float,
    reference_pc_canvas_size: Tuple[float, float],
    canvas_size_by_state_index: Dict[int, Tuple[float, float]],
    supported_state_indices: Tuple[int, ...] = (0, 1, 2, 3),
) -> Dict[int, Dict[str, Tuple[float, float]]]:
    """
    将 Web top-left 坐标（以 reference_pc_canvas_size 为基准）写回到 record 的 RectTransform 多端 state。

    返回：
      state_index -> {"canvas_position": (x,y), "size": (w,h)}
    """
    pc_w, pc_h = float(reference_pc_canvas_size[0]), float(reference_pc_canvas_size[1])
    if pc_w <= 0 or pc_h <= 0:
        raise ValueError(f"invalid reference_pc_canvas_size: {reference_pc_canvas_size!r}")

    out: Dict[int, Dict[str, Tuple[float, float]]] = {}
    for state_index in supported_state_indices:
        idx = int(state_index)
        if not has_rect_transform_state(record, state_index=idx):
            continue
        canvas_size = canvas_size_by_state_index.get(idx)
        if canvas_size is None:
            raise ValueError(f"missing canvas_size for state_index={int(idx)}")
        canvas_w, canvas_h = float(canvas_size[0]), float(canvas_size[1])
        if canvas_w <= 0 or canvas_h <= 0:
            raise ValueError(f"invalid canvas_size for state_index={int(idx)}: {canvas_size!r}")

        scale_x = canvas_w / pc_w
        scale_y = canvas_h / pc_h

        left = float(web_left) * float(scale_x)
        top = float(web_top) * float(scale_y)
        width = float(web_width) * float(scale_x)
        height = float(web_height) * float(scale_y)

        pivot = extract_rect_pivot_from_state(record, state_index=idx)
        canvas_pos = web_top_left_to_canvas_position(
            left=float(left),
            top=float(top),
            width=float(width),
            height=float(height),
            pivot=pivot,
            canvas_height=float(canvas_h),
        )

        # 关键：Web UI 的绝对坐标在“同一平台内不同画布尺寸（例如 1920×1080 vs 1600×900）”切换时仍应保持贴边/居中语义。
        # 若沿用样本 record 的 anchor（常见为 0.5），小画布会出现“左上角按钮飞出屏幕”的问题。
        # 这里按控件的“pivot 画布坐标”选择固定 anchor（0/0.5/1），并写回 anchor_min/max，
        # 再由 shared.py 按 anchor 计算 anchored_position。
        transform = extract_rect_transform_from_state(record, state_index=idx)
        px01 = float(canvas_pos[0]) / float(canvas_w) if canvas_w > 0 else 0.5
        py01 = float(canvas_pos[1]) / float(canvas_h) if canvas_h > 0 else 0.5
        ax = _choose_fixed_anchor_component(px01)
        ay = _choose_fixed_anchor_component(py01)
        _set_fixed_anchor_min_max_in_place(transform, ax=ax, ay=ay)

        _set_rect_state_canvas_position_and_size(
            record=record,
            state_index=idx,
            canvas_position=canvas_pos,
            size=(float(width), float(height)),
            canvas_size_by_state_index=canvas_size_by_state_index,
        )
        out[idx] = {
            "canvas_position": (float(canvas_pos[0]), float(canvas_pos[1])),
            "size": (float(width), float(height)),
        }
    return out


def extract_rect_pivot_from_state(record: Dict[str, Any], *, state_index: int) -> Tuple[float, float]:
    transform = extract_rect_transform_from_state(record, state_index=state_index)
    pivot_node = transform.get("506")
    if not isinstance(pivot_node, dict):
        return 0.5, 0.5
    px = pivot_node.get("501")
    py = pivot_node.get("502")
    pivot_x = float(px) if isinstance(px, (int, float)) else 0.5
    pivot_y = float(py) if isinstance(py, (int, float)) else 0.5
    return pivot_x, pivot_y


def extract_rect_transform_from_state(record: Dict[str, Any], *, state_index: int) -> Dict[str, Any]:
    transform = try_extract_rect_transform_from_state(record, state_index=state_index)
    if transform is None:
        raise ValueError(f"record missing RectTransform state_index={int(state_index)}")
    return transform


def try_extract_rect_transform_from_state(record: Dict[str, Any], *, state_index: int) -> Optional[Dict[str, Any]]:
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

    for state in state_list:
        if not isinstance(state, dict):
            continue
        idx_value = state.get("501")
        idx = int(idx_value) if isinstance(idx_value, int) else 0
        if idx != int(state_index):
            continue
        transform = state.get("502")
        if not isinstance(transform, dict):
            return None
        return transform
    return None


def has_rect_transform_state(record: Dict[str, Any], *, state_index: int) -> bool:
    return try_extract_rect_transform_from_state(record, state_index=state_index) is not None


def try_extract_widget_name(record: Dict[str, Any]) -> Optional[str]:
    component_list = record.get("505")
    if not isinstance(component_list, list) or not component_list:
        return None
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        return None
    node12 = name_component.get("12")
    if not isinstance(node12, dict):
        return None
    name = node12.get("501")
    if not isinstance(name, str):
        return None
    return name


def try_extract_textbox_text_node(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    尝试从一个 UI record 中提取 TextBox 的“文本配置节点”（node19）。

    约定样本路径（但这里不硬编码 component index）：
    - record['505'][?]['503']['19']['505']['501'] 为文本内容（string）
    - record['505'][?]['503']['19']['502'] 为字号（int）
    - record['505'][?]['503']['19']['503'/'504'] 为对齐相关 code（int，可选）
    """
    component_list = record.get("505")
    if not isinstance(component_list, list):
        return None
    for component in component_list:
        if not isinstance(component, dict):
            continue
        nested = component.get("503")
        if not isinstance(nested, dict):
            continue
        node19 = nested.get("19")
        if not isinstance(node19, dict):
            continue
        # 样本中 node19['505'] 为 dict，包含文本 string 在 ['501']
        node505 = node19.get("505")
        if isinstance(node505, dict):
            return node19
        # 也允许 node19 已存在但缺少 505（写回时会补齐）
        return node19
    return None

