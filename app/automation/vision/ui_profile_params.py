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
from app.automation.vision.ocr_template_profile import (
    get_default_ocr_template_profile,
    resolve_ocr_template_profile_selection,
)


@dataclass(frozen=True)
class AutomationUiProfileParams:
    """自动化识别链路中与 UI 像素强相关的参数集合。"""

    profile_name: str
    port_header_height_px: int
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
_BASE_PORT_HEADER_HEIGHT_PX = 28
_BASE_PARAMS = AutomationUiProfileParams(
    profile_name=_BASE_PROFILE_NAME,
    port_header_height_px=_BASE_PORT_HEADER_HEIGHT_PX,
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
    return AutomationUiProfileParams(
        profile_name=str(profile_name),
        port_header_height_px=int(port_header_height_px),
        ocr_exclude_top_pixels_default=_round_positive_int(float(_BASE_PARAMS.ocr_exclude_top_pixels_default) * scale_factor, minimum=0),
        candidate_search_margin_top_px=_round_positive_int(float(_BASE_PARAMS.candidate_search_margin_top_px) * scale_factor, minimum=0),
        candidate_popup_size_px=scaled_popup,
        zoom_region_size_px=scaled_zoom,
    )


def _fallback_project_root() -> Optional[Path]:
    """在未设置默认 workspace 时，根据目录结构推断根目录。"""
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "assets").exists() and (parent / "tools").exists():
            return parent
    return None


def _resolve_workspace_root(workspace_root: Optional[Path]) -> Optional[Path]:
    if workspace_root is not None:
        return Path(workspace_root).resolve()
    default_root = get_default_workspace_root_or_none()
    if default_root is not None:
        return default_root.resolve()
    return _fallback_project_root()


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


def resolve_automation_ui_params(*, workspace_root: Optional[Path] = None, preferred_locale: str = "CN") -> AutomationUiProfileParams:
    """按当前显示设置/默认 workspace 推导“自动化 UI 参数”。"""
    resolved_root = _resolve_workspace_root(workspace_root)
    if resolved_root is None:
        return _BASE_PARAMS
    if sys.platform != "win32":
        return _BASE_PARAMS

    selection = resolve_ocr_template_profile_selection(resolved_root, preferred_locale=str(preferred_locale or "CN"))
    profile_name = str(selection.selected_profile_name or "").strip()
    detected_display = selection.detected_display
    scale_percent = int(detected_display.scale_percent)
    screen_short_side_px = int(detected_display.short_side_px)

    resolution_short_side_baseline = {
        "4K": 2160,
        "2K": 1440,
        "1080": 1080,
    }
    max_relative_delta = 0.25

    def match_resolution_tag_by_short_side(short_side_px: int) -> Optional[str]:
        best_tag: Optional[str] = None
        best_ratio: Optional[float] = None
        for tag, baseline_px in resolution_short_side_baseline.items():
            baseline_value = int(baseline_px)
            if baseline_value <= 0:
                continue
            ratio = abs(float(short_side_px) - float(baseline_value)) / float(baseline_value)
            if best_ratio is None or ratio < float(best_ratio):
                best_ratio = float(ratio)
                best_tag = str(tag).upper()
        if best_tag is None or best_ratio is None:
            return None
        if float(best_ratio) > float(max_relative_delta):
            return None
        return best_tag

    matched_resolution_tag = match_resolution_tag_by_short_side(screen_short_side_px)

    # 分辨率档位的“标题栏基准高度”（100% 缩放下）
    # - 1080@100%：用户实测 20px
    # - 2K@100%：用户实测 22px
    # - 4K@100%：现有模板基准 28px
    base_header_height_by_resolution_tag = {
        "1080": 20,
        "2K": 22,
        "4K": 28,
    }

    resolution_tag = str(matched_resolution_tag or "").strip().upper()
    base_header_height = int(base_header_height_by_resolution_tag.get(resolution_tag, _BASE_PORT_HEADER_HEIGHT_PX))
    header_height = _round_positive_int(
        float(base_header_height) * (float(scale_percent) / 100.0),
        minimum=1,
    )

    return _build_scaled_from_base(profile_name=profile_name or _BASE_PROFILE_NAME, port_header_height_px=header_height)


def get_port_header_height_px(*, workspace_root: Optional[Path] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root).port_header_height_px)


def get_candidate_search_margin_top_px(*, workspace_root: Optional[Path] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root).candidate_search_margin_top_px)


def get_candidate_popup_size_px(*, workspace_root: Optional[Path] = None) -> Tuple[int, int]:
    return tuple(resolve_automation_ui_params(workspace_root=workspace_root).candidate_popup_size_px)


def get_ocr_exclude_top_pixels_default(*, workspace_root: Optional[Path] = None) -> int:
    return int(resolve_automation_ui_params(workspace_root=workspace_root).ocr_exclude_top_pixels_default)


def get_zoom_region_size_px(*, workspace_root: Optional[Path] = None) -> Tuple[int, int]:
    return tuple(resolve_automation_ui_params(workspace_root=workspace_root).zoom_region_size_px)


