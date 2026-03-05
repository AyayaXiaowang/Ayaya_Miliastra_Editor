# -*- coding: utf-8 -*-
"""
基于 OCR 模板 profile 的“自动化 UI 参数”解析。

目标：
- 将分辨率/Windows 缩放强相关的硬编码像素值集中到同一处；
- 复用现有 `ocr_template_profile` 的自动选择结果（例如 2K-100-CN、4K-125-CN）；
- 避免在各处散落 `28/150/160/500/650/140/70` 等 magic number。

说明：
- 本模块不做异常吞没；若调用方在无 workspace/非 Windows 环境下强行解析 profile，可能抛错。
- 调用方若处于“无默认 workspace”的上下文（例如纯工具脚本），建议显式传入 workspace_root。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app.automation.editor.node_library_provider import get_default_workspace_root_or_none
from engine.utils.workspace import infer_workspace_root_or_none
from app.automation.vision.ocr_template_profile import (
    get_default_ocr_template_profile,
    resolve_ocr_template_profile_selection,
)


@dataclass(frozen=True)
class AutomationUiProfileParams:
    """自动化识别链路中与 UI 像素强相关的参数集合。"""

    profile_name: str
    port_header_height_px: int
    node_view_size_px: Tuple[int, int]

    # 节点去重（根源层过滤重复 bbox）
    node_dedup_grid_size_px: int
    node_dedup_iou_threshold: float
    node_dedup_containment_ratio: float
    node_dedup_center_distance_px: float
    node_dedup_axis_overlap_ratio: float

    # 一步式识别（端口/节点矩形）：同行去重、NMS 与飞线过滤阈值
    port_same_row_y_tolerance_px: int
    port_template_nms_iou_threshold: float
    color_scan_min_height_threshold_px: int
    color_scan_min_width_threshold_px: int
    color_merge_max_vertical_gap_px: int
    ocr_exclude_top_pixels_default: int
    candidate_search_margin_top_px: int
    candidate_popup_size_px: Tuple[int, int]
    zoom_region_size_px: Tuple[int, int]


def _round_positive_int(value: float, *, minimum: int = 1) -> int:
    output = int(round(float(value)))
    return int(max(int(minimum), output))


def _scale_pair(pair_px: Tuple[int, int], factor: float) -> Tuple[int, int]:
    return (
        _round_positive_int(float(pair_px[0]) * float(factor), minimum=1),
        _round_positive_int(float(pair_px[1]) * float(factor), minimum=1),
    )


_BASE_PROFILE_NAME = "4K-100-CN"
_BASE_PORT_HEADER_HEIGHT_PX = 21
# 节点基础几何尺寸（用于坐标换算/缩放估计/ROI 推导等）。该值会在不同 profile 下按比例推导。
_BASE_NODE_VIEW_SIZE_PX = (200, 100)
# 端口识别跳过节点顶部标题栏的最小像素高度（避免 1080/2K@100% 下排除区域过小）
_MIN_PORT_HEADER_HEIGHT_PX = 20
# 端口识别排除顶部区域的最大像素高度（用户实测 4K125 只需 26px）
_MAX_PORT_HEADER_HEIGHT_PX = 26
_BASE_PARAMS = AutomationUiProfileParams(
    profile_name=_BASE_PROFILE_NAME,
    port_header_height_px=_BASE_PORT_HEADER_HEIGHT_PX,
    node_view_size_px=_BASE_NODE_VIEW_SIZE_PX,
    node_dedup_grid_size_px=256,
    node_dedup_iou_threshold=0.35,
    node_dedup_containment_ratio=0.85,
    node_dedup_center_distance_px=28.0,
    node_dedup_axis_overlap_ratio=0.65,
    port_same_row_y_tolerance_px=10,
    port_template_nms_iou_threshold=0.10,
    color_scan_min_height_threshold_px=15,
    color_scan_min_width_threshold_px=50,
    color_merge_max_vertical_gap_px=20,
    ocr_exclude_top_pixels_default=150,
    candidate_search_margin_top_px=160,
    candidate_popup_size_px=(500, 650),
    zoom_region_size_px=(140, 70),
)


def _build_scaled_from_base(*, profile_name: str, port_header_height_px: int) -> AutomationUiProfileParams:
    """基于“端口标题栏高度”作为 UI 缩放代表值，对其它像素参数做同比例缩放。"""
    scale_factor = float(port_header_height_px) / float(_BASE_PORT_HEADER_HEIGHT_PX) if _BASE_PORT_HEADER_HEIGHT_PX > 0 else 1.0
    scaled_popup = _scale_pair(_BASE_PARAMS.candidate_popup_size_px, scale_factor)
    scaled_zoom = _scale_pair(_BASE_PARAMS.zoom_region_size_px, scale_factor)
    scaled_node_view = _scale_pair(_BASE_PARAMS.node_view_size_px, scale_factor)
    return AutomationUiProfileParams(
        profile_name=str(profile_name),
        port_header_height_px=int(port_header_height_px),
        node_view_size_px=scaled_node_view,
        node_dedup_grid_size_px=_round_positive_int(float(_BASE_PARAMS.node_dedup_grid_size_px) * scale_factor, minimum=64),
        node_dedup_iou_threshold=float(_BASE_PARAMS.node_dedup_iou_threshold),
        node_dedup_containment_ratio=float(_BASE_PARAMS.node_dedup_containment_ratio),
        node_dedup_center_distance_px=float(_BASE_PARAMS.node_dedup_center_distance_px) * float(scale_factor),
        node_dedup_axis_overlap_ratio=float(_BASE_PARAMS.node_dedup_axis_overlap_ratio),
        port_same_row_y_tolerance_px=_round_positive_int(float(_BASE_PARAMS.port_same_row_y_tolerance_px) * scale_factor, minimum=4),
        port_template_nms_iou_threshold=float(_BASE_PARAMS.port_template_nms_iou_threshold),
        color_scan_min_height_threshold_px=_round_positive_int(float(_BASE_PARAMS.color_scan_min_height_threshold_px) * scale_factor, minimum=6),
        color_scan_min_width_threshold_px=_round_positive_int(float(_BASE_PARAMS.color_scan_min_width_threshold_px) * scale_factor, minimum=20),
        color_merge_max_vertical_gap_px=_round_positive_int(float(_BASE_PARAMS.color_merge_max_vertical_gap_px) * scale_factor, minimum=8),
        ocr_exclude_top_pixels_default=_round_positive_int(float(_BASE_PARAMS.ocr_exclude_top_pixels_default) * scale_factor, minimum=0),
        candidate_search_margin_top_px=_round_positive_int(float(_BASE_PARAMS.candidate_search_margin_top_px) * scale_factor, minimum=0),
        candidate_popup_size_px=scaled_popup,
        zoom_region_size_px=scaled_zoom,
    )


def _resolve_workspace_root(workspace_root: Optional[Path]) -> Optional[Path]:
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    default_root = get_default_workspace_root_or_none()
    if default_root is not None:
        return default_root.resolve()
    return infer_workspace_root_or_none(Path(__file__).resolve())


def resolve_selected_profile_name(*, workspace_root: Optional[Path], preferred_locale: str = "CN") -> str:
    """解析当前应使用的 OCR 模板 profile 名称。"""
    resolved_root = _resolve_workspace_root(workspace_root)
    if resolved_root is None:
        return ""
    cached_default = get_default_ocr_template_profile(resolved_root)
    if isinstance(cached_default, str) and cached_default.strip():
        return str(cached_default).strip()
    selection = resolve_ocr_template_profile_selection(resolved_root, preferred_locale=str(preferred_locale or "CN"))
    return str(selection.selected_profile_name)


def _parse_profile_name_components(profile_name: str) -> tuple[str, Optional[int]]:
    """从 profile 名中解析 (resolution_tag, scale_percent_or_none)。"""
    text = str(profile_name or "").strip()
    if not text:
        return "", None
    parts = [part.strip() for part in text.split("-") if part.strip()]
    if not parts:
        return "", None
    resolution_tag = str(parts[0]).upper()
    scale_percent: Optional[int] = None
    if len(parts) >= 2 and str(parts[1]).isdigit():
        scale_percent = int(parts[1])
    return resolution_tag, scale_percent


def resolve_automation_ui_params(
    *,
    workspace_root: Optional[Path] = None,
    preferred_locale: str = "CN",
    profile_name_override: Optional[str] = None,
) -> AutomationUiProfileParams:
    """按当前显示设置/默认 workspace 推导“自动化 UI 参数”。

    - 正常运行：根据 Windows 显示设置自动选择 OCR 模板 profile，并据此推导像素参数；
    - 离线回归/工具：可通过 `profile_name_override` 显式指定 profile（避免与本机显示设置耦合）。
    """
    resolved_root = _resolve_workspace_root(workspace_root)
    if resolved_root is None:
        return _BASE_PARAMS
    if isinstance(profile_name_override, str) and profile_name_override.strip():
        forced_profile_name = str(profile_name_override).strip()
        forced_resolution_tag, forced_scale_percent = _parse_profile_name_components(forced_profile_name)
        base_header_height_by_resolution_tag = {
            "1080": 17,
            "2K": 17,
            "4K": 21,
        }
        resolution_tag = str(forced_resolution_tag or "").strip().upper()
        base_header_height = int(base_header_height_by_resolution_tag.get(resolution_tag, _BASE_PORT_HEADER_HEIGHT_PX))
        scale_percent = int(forced_scale_percent) if forced_scale_percent is not None else 100
        header_height = _round_positive_int(float(base_header_height) * (float(scale_percent) / 100.0), minimum=1)
        header_height = min(header_height, _MAX_PORT_HEADER_HEIGHT_PX)
        return _build_scaled_from_base(profile_name=forced_profile_name, port_header_height_px=header_height)
    if sys.platform != "win32":
        return _BASE_PARAMS

    selection = resolve_ocr_template_profile_selection(resolved_root, preferred_locale=str(preferred_locale or "CN"))
    profile_name = str(selection.selected_profile_name or "").strip()
    detected_display = selection.detected_display
    selected_profile = selection.selected_profile
    resolution_tag_from_selected = str(getattr(selected_profile, "resolution_tag", "") or "").strip().upper()
    scale_percent_from_selected = getattr(selected_profile, "scale_percent", None)

    scale_percent = int(scale_percent_from_selected) if scale_percent_from_selected is not None else int(detected_display.scale_percent)
    resolution_tag_from_name, _scale_from_name = _parse_profile_name_components(profile_name)
    resolution_tag = str(resolution_tag_from_selected or resolution_tag_from_name or "").strip().upper()
    if not resolution_tag:
        resolution_tag = str(selection.matched_resolution_tag or "").strip().upper()

    # 分辨率档位的"标题栏基准高度"（100% 缩放下）
    # - 1080@100%：用户实测 17px
    # - 2K@100%：用户实测 17px
    # - 4K@100%：用户实测 21px（4K125 应为 26px -> 21 * 1.25 ≈ 26）
    # 所有分辨率排除区域最大不超过 _MAX_PORT_HEADER_HEIGHT_PX (26px)
    base_header_height_by_resolution_tag = {
        "1080": 17,
        "2K": 17,
        "4K": 21,
    }
    base_header_height = int(base_header_height_by_resolution_tag.get(resolution_tag, _BASE_PORT_HEADER_HEIGHT_PX))
    header_height = _round_positive_int(
        float(base_header_height) * (float(scale_percent) / 100.0),
        minimum=1,
    )
    # 强制限制最大高度，确保所有分辨率都不超过上限
    header_height = min(header_height, _MAX_PORT_HEADER_HEIGHT_PX)

    return _build_scaled_from_base(profile_name=profile_name or _BASE_PROFILE_NAME, port_header_height_px=header_height)


def _clamp_port_header_height_px(header_height_px: int) -> int:
    return int(max(_MIN_PORT_HEADER_HEIGHT_PX, min(int(header_height_px), _MAX_PORT_HEADER_HEIGHT_PX)))


def get_port_header_height_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    raw_value = int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).port_header_height_px)
    return _clamp_port_header_height_px(raw_value)


def get_candidate_search_margin_top_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).candidate_search_margin_top_px)


def get_candidate_popup_size_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> Tuple[int, int]:
    return tuple(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).candidate_popup_size_px)


def get_ocr_exclude_top_pixels_default(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).ocr_exclude_top_pixels_default)


def get_zoom_region_size_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> Tuple[int, int]:
    return tuple(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).zoom_region_size_px)


def get_node_view_size_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> Tuple[int, int]:
    return tuple(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_view_size_px)


def get_node_dedup_grid_size_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_dedup_grid_size_px)


def get_node_dedup_iou_threshold(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> float:
    return float(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_dedup_iou_threshold)


def get_node_dedup_containment_ratio(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> float:
    return float(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_dedup_containment_ratio)


def get_node_dedup_center_distance_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> float:
    return float(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_dedup_center_distance_px)


def get_node_dedup_axis_overlap_ratio(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> float:
    return float(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).node_dedup_axis_overlap_ratio)


def get_port_same_row_y_tolerance_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).port_same_row_y_tolerance_px)


def get_port_template_nms_iou_threshold(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> float:
    return float(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).port_template_nms_iou_threshold)


def get_color_scan_min_height_threshold_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).color_scan_min_height_threshold_px)


def get_color_scan_min_width_threshold_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).color_scan_min_width_threshold_px)


def get_color_merge_max_vertical_gap_px(*, workspace_root: Optional[Path] = None, profile_name_override: Optional[str] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root, profile_name_override=profile_name_override).color_merge_max_vertical_gap_px)


