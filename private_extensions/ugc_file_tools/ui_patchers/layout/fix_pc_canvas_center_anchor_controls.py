from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.ui.readable_dump import extract_ui_record_list as _extract_ui_record_list

from ugc_file_tools.ui_patchers.layout.layout_templates_parts.shared import (
    dump_gil_to_raw_json_object as _dump_gil_to_raw_json_object,
    find_record_by_guid as _find_record_by_guid,
    write_back_modified_gil_by_reencoding_payload as _write_back_modified_gil_by_reencoding_payload,
)
from .web_ui_import_rect import try_extract_rect_transform_from_state


@dataclass(frozen=True, slots=True)
class FixedAnchorPlan:
    guid: int
    # interpret old pivot_canvas using this baseline canvas
    baseline_canvas_size: Tuple[float, float]
    # write new fixed anchor for state_index=0
    new_anchor: Tuple[float, float]


def _require_vec2(node: Any, *, name: str) -> Dict[str, Any]:
    if not isinstance(node, dict):
        raise ValueError(f"{name} must be dict vec2 node")
    return node


def _require_float(node: Dict[str, Any], key: str, *, name: str) -> float:
    value = node.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name}.{key} must be number")
    return float(value)


def _ensure_vec2(parent: Dict[str, Any], key: str) -> Dict[str, Any]:
    node = parent.get(key)
    if not isinstance(node, dict):
        node = {}
        parent[key] = node
    return node


def _compute_pivot_canvas_from_transform(
    transform: Dict[str, Any],
    *,
    baseline_canvas_size: Tuple[float, float],
) -> Tuple[float, float]:
    canvas_w, canvas_h = float(baseline_canvas_size[0]), float(baseline_canvas_size[1])
    if canvas_w <= 0 or canvas_h <= 0:
        raise ValueError(f"invalid baseline_canvas_size: {baseline_canvas_size!r}")

    anchor_min = _require_vec2(transform.get("502"), name="anchor_min")
    anchor_max = _require_vec2(transform.get("503"), name="anchor_max")
    ax0 = _require_float(anchor_min, "501", name="anchor_min")
    ay0 = _require_float(anchor_min, "502", name="anchor_min")
    ax1 = _require_float(anchor_max, "501", name="anchor_max")
    ay1 = _require_float(anchor_max, "502", name="anchor_max")
    if ax0 != ax1 or ay0 != ay1:
        raise ValueError("stretch anchor unsupported for this fixer")

    pos = _require_vec2(transform.get("504"), name="anchored_position")
    px = _require_float(pos, "501", name="anchored_position")
    py = _require_float(pos, "502", name="anchored_position")

    return ax0 * canvas_w + px, ay0 * canvas_h + py


def _write_fixed_anchor_for_state0(
    record: Dict[str, Any],
    *,
    baseline_canvas_size: Tuple[float, float],
    new_anchor: Tuple[float, float],
) -> None:
    transform = try_extract_rect_transform_from_state(record, state_index=0)
    if not isinstance(transform, dict):
        raise ValueError("record missing RectTransform state_index=0")

    pivot_canvas_x, pivot_canvas_y = _compute_pivot_canvas_from_transform(transform, baseline_canvas_size=baseline_canvas_size)

    ax_new, ay_new = float(new_anchor[0]), float(new_anchor[1])
    if ax_new < 0 or ax_new > 1 or ay_new < 0 or ay_new > 1:
        raise ValueError(f"invalid new_anchor: {new_anchor!r}")

    # set anchor_min/max (fixed)
    anchor_min = _ensure_vec2(transform, "502")
    anchor_max = _ensure_vec2(transform, "503")
    anchor_min["501"] = float(ax_new)
    anchor_min["502"] = float(ay_new)
    anchor_max["501"] = float(ax_new)
    anchor_max["502"] = float(ay_new)

    # recompute anchored_position so that pivot_canvas stays invariant on baseline canvas
    canvas_w, canvas_h = float(baseline_canvas_size[0]), float(baseline_canvas_size[1])
    anchored_x = float(pivot_canvas_x) - float(ax_new) * canvas_w
    anchored_y = float(pivot_canvas_y) - float(ay_new) * canvas_h
    pos = _ensure_vec2(transform, "504")
    pos["501"] = float(anchored_x)
    pos["502"] = float(anchored_y)


def fix_pc_canvas_center_anchor_controls(
    *,
    input_gil_path: Path,
    output_gil_path: Path,
    plans: List[FixedAnchorPlan],
) -> Dict[str, Any]:
    """
    修复“PC 画布尺寸切换（例如 1920×1080 → 1600×900）导致左上角按钮飞出屏幕”的问题。

    根因：这些控件的 RectTransform state0 使用 anchor=(0.5,0.5)（中心锚点），anchored_position 以 1920×1080 为基准；
    当画布宽度变小（1600）时，中心点右移量变化会把控件整体推到负 x。

    修复：把 state0 的 anchor_min/max 改为固定锚点（例如 top-left=(0,1)），并重算 anchored_position，
    使控件的 pivot_canvas 坐标在基准画布下保持不变，从而在任意 PC 画布尺寸下都不会漂移。
    """
    raw_dump_object = _dump_gil_to_raw_json_object(input_gil_path)
    ui_records = _extract_ui_record_list(raw_dump_object)

    changed_total = 0
    changed_guids: List[int] = []
    for plan in plans:
        rec = _find_record_by_guid(ui_records, int(plan.guid))
        if rec is None:
            raise ValueError(f"record not found: guid={int(plan.guid)}")
        _write_fixed_anchor_for_state0(
            rec,
            baseline_canvas_size=tuple(plan.baseline_canvas_size),
            new_anchor=tuple(plan.new_anchor),
        )
        changed_total += 1
        changed_guids.append(int(plan.guid))

    _write_back_modified_gil_by_reencoding_payload(
        raw_dump_object=raw_dump_object,
        input_gil_path=input_gil_path,
        output_gil_path=output_gil_path,
    )

    return {
        "input_gil": str(input_gil_path),
        "output_gil": str(output_gil_path),
        "changed_total": int(changed_total),
        "changed_guids": changed_guids,
        "note": "本修复仅处理 state_index=0 的 fixed-anchor 场景；不支持 stretch anchor。",
    }


__all__ = [
    "FixedAnchorPlan",
    "fix_pc_canvas_center_anchor_controls",
]

