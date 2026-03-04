from __future__ import annotations

from typing import Tuple


def compute_fast_preview_auto_eligible(
    *,
    fast_preview_enabled: bool,
    can_persist: bool,
    node_count: int,
    edge_count: int,
    node_threshold: int,
    edge_threshold: int,
) -> bool:
    """GraphScene 的 fast_preview_mode 自动启用判定（纯逻辑）。

    约定（与 UI 保持一致）：
    - 仅在会话不可落盘（can_persist=False）时自动启用；
    - 节点数或连线数达到阈值即视为“超大图”。
    """
    if not bool(fast_preview_enabled):
        return False
    if bool(can_persist):
        return False
    n = int(node_count or 0)
    e = int(edge_count or 0)
    nt = int(node_threshold or 0)
    et = int(edge_threshold or 0)
    return bool((n >= nt) or (e >= et))


def compute_enable_batched_edge_layer(
    *,
    fast_preview_mode: bool,
    batched_edges_enabled: bool,
    read_only_batched_enabled: bool,
    is_read_only: bool,
    edge_count: int,
    read_only_edge_threshold: int,
    force_disable: bool = False,
) -> bool:
    """GraphScene 是否启用“批量边渲染层”（fast_preview / 只读大图）判定（纯逻辑）。"""
    if bool(force_disable):
        return False

    enable = bool(fast_preview_mode and batched_edges_enabled)
    if (
        (not enable)
        and bool(batched_edges_enabled)
        and bool(read_only_batched_enabled)
        and bool(is_read_only)
        and int(edge_count or 0) >= int(read_only_edge_threshold or 0)
    ):
        enable = True
    return bool(enable)


def compute_should_skip_ports_sync_on_scale_change(
    *,
    is_view_panning: bool,
    pan_hide_icons_enabled: bool,
) -> bool:
    """缩放变化时是否跳过端口 LOD 同步（panning 期间由交互控制接管）。"""
    return bool(is_view_panning) and bool(pan_hide_icons_enabled)


def is_blocks_only_overview_supported(
    *,
    graph_block_overview_enabled: bool,
    graph_lod_enabled: bool,
    basic_blocks: object,
) -> bool:
    """是否允许进入 blocks-only overview（鸟瞰）模式（纯逻辑）。"""
    if not bool(graph_block_overview_enabled):
        return False
    if not bool(graph_lod_enabled):
        return False
    return bool(basic_blocks)


def _as_float(value: object, *, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(default)


def _compute_default_exit_scale(*, enter_scale: float, ratio: float, offset: float) -> float:
    e = float(enter_scale)
    return max(e * float(ratio), e + float(offset))


def normalize_enter_exit_scales(
    *,
    enter_scale_value: object,
    exit_scale_value: object,
    default_enter_scale: float,
    default_exit_ratio: float,
    default_exit_offset: float,
) -> Tuple[float, float]:
    """将 enter/exit scale 归一化为 (enter, exit)，并保证 exit >= enter（无 try/except）。"""
    enter_scale = _as_float(enter_scale_value, default=float(default_enter_scale))
    if enter_scale < 0:
        enter_scale = 0.0

    exit_scale_raw = exit_scale_value if isinstance(exit_scale_value, (int, float)) else None
    if exit_scale_raw is None:
        exit_scale = _compute_default_exit_scale(
            enter_scale=enter_scale,
            ratio=float(default_exit_ratio),
            offset=float(default_exit_offset),
        )
    else:
        exit_scale = float(exit_scale_raw)

    if exit_scale < enter_scale:
        exit_scale = float(enter_scale)

    return float(enter_scale), float(exit_scale)


def compute_enabled_below_scale_with_hysteresis(
    *,
    prev_enabled: bool,
    scale_hint: float,
    enter_scale: float,
    exit_scale: float,
) -> bool:
    """回滞开关：当 scale < enter 时开启；当 scale > exit 时关闭；否则保持原状。"""
    prev = bool(prev_enabled)
    s = float(scale_hint or 1.0)
    enter = float(enter_scale)
    exit_s = float(exit_scale)
    if exit_s < enter:
        exit_s = enter

    if (not prev) and (s < enter):
        return True
    if prev and (s > exit_s):
        return False
    return prev


def compute_blocks_only_overview_mode(
    *,
    supported: bool,
    prev_enabled: bool,
    scale_hint: float,
    enter_scale_value: object,
    exit_scale_value: object,
) -> bool:
    if not bool(supported):
        return False

    enter, exit_s = normalize_enter_exit_scales(
        enter_scale_value=enter_scale_value,
        exit_scale_value=exit_scale_value,
        default_enter_scale=0.10,
        default_exit_ratio=1.15,
        default_exit_offset=0.02,
    )
    return compute_enabled_below_scale_with_hysteresis(
        prev_enabled=prev_enabled,
        scale_hint=scale_hint,
        enter_scale=enter,
        exit_scale=exit_s,
    )


def compute_lod_ports_hidden_mode(
    *,
    lod_enabled: bool,
    prev_enabled: bool,
    scale_hint: float,
    enter_scale_value: object,
    exit_scale_value: object,
) -> bool:
    if not bool(lod_enabled):
        return False

    enter, exit_s = normalize_enter_exit_scales(
        enter_scale_value=enter_scale_value,
        exit_scale_value=exit_scale_value,
        default_enter_scale=0.30,
        default_exit_ratio=1.08,
        default_exit_offset=0.02,
    )
    return compute_enabled_below_scale_with_hysteresis(
        prev_enabled=prev_enabled,
        scale_hint=scale_hint,
        enter_scale=enter,
        exit_scale=exit_s,
    )


def compute_lod_edges_culled_mode(
    *,
    lod_enabled: bool,
    prev_enabled: bool,
    scale_hint: float,
    enter_scale_value: object,
    exit_scale_value: object,
) -> bool:
    if not bool(lod_enabled):
        return False

    enter, exit_s = normalize_enter_exit_scales(
        enter_scale_value=enter_scale_value,
        exit_scale_value=exit_scale_value,
        default_enter_scale=0.22,
        default_exit_ratio=1.08,
        default_exit_offset=0.02,
    )
    return compute_enabled_below_scale_with_hysteresis(
        prev_enabled=prev_enabled,
        scale_hint=scale_hint,
        enter_scale=enter,
        exit_scale=exit_s,
    )


__all__ = [
    "compute_blocks_only_overview_mode",
    "compute_enable_batched_edge_layer",
    "compute_enabled_below_scale_with_hysteresis",
    "compute_fast_preview_auto_eligible",
    "compute_lod_edges_culled_mode",
    "compute_lod_ports_hidden_mode",
    "compute_should_skip_ports_sync_on_scale_change",
    "is_blocks_only_overview_supported",
    "normalize_enter_exit_scales",
]

