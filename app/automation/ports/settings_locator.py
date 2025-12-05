from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple, Any

from app.automation.core import executor_utils as _exec_utils
from app.automation.ports._ports import (
    normalize_kind_text,
    get_port_category,
    get_port_center_x,
    get_port_center_y,
)
from app.automation.capture.template_matcher import match_template_candidates


@dataclass(frozen=True)
class SettingsPortSnapshot:
    side: str
    index: Optional[int]
    center: Tuple[int, int]
    bbox: Tuple[int, int, int, int]
    name_cn: str
    raw_kind: str


def _iter_settings_ports_with_raw_kind(
    ports: Iterable[Any],
) -> Iterable[Tuple[Any, str]]:
    """在端口列表中筛选 kind 归一化后为 'settings' 的端口，返回 (port, raw_kind)。"""
    for port_object in ports or []:
        raw_kind = str(getattr(port_object, "kind", "") or "")
        if normalize_kind_text(raw_kind) != "settings":
            continue
        yield port_object, raw_kind


def collect_settings_rows(ports: Iterable[Any]) -> List[SettingsPortSnapshot]:
    """收敛 kind=='settings' 的端口，返回统一的快照结构。"""
    rows: List[SettingsPortSnapshot] = []
    for port_object, raw_kind in _iter_settings_ports_with_raw_kind(ports):
        center = getattr(port_object, "center", (0, 0))
        bbox = getattr(port_object, "bbox", (0, 0, 0, 0))
        index_value = getattr(port_object, "index", None)
        rows.append(
            SettingsPortSnapshot(
                side=str(getattr(port_object, "side", "")),
                index=None if index_value is None else int(index_value),
                center=(int(center[0]), int(center[1])),
                bbox=(
                    int(bbox[0]),
                    int(bbox[1]),
                    int(bbox[2]),
                    int(bbox[3]),
                ),
                name_cn=str(getattr(port_object, "name_cn", "") or ""),
                raw_kind=raw_kind,
            )
        )
    return rows


def select_settings_center(
    *,
    ports: List[Any],
    node_bbox: Tuple[int, int, int, int],
    row_center_y: int,
    desired_side: Optional[str] = None,
    y_tolerance: int = 14,
    log_fn: Optional[Callable[[str], None]] = None,
) -> Tuple[int, int]:
    """在识别到的端口中选择 Settings 行的中心点，带统一回退策略。"""

    def _log(message: str) -> None:
        if log_fn is not None:
            log_fn(message)

    ports_all = list(ports or [])
    settings_ports = [
        port_object for port_object, _ in _iter_settings_ports_with_raw_kind(ports_all)
    ]

    def _filter_by_y(port_list: List[Any]) -> List[Any]:
        kept: List[Any] = []
        for candidate in port_list:
            center_y = get_port_center_y(candidate)
            if abs(center_y - int(row_center_y)) <= int(y_tolerance):
                kept.append(candidate)
        return kept

    def _filter_by_confidence(port_list: List[Any]) -> List[Any]:
        kept: List[Any] = []
        for candidate in port_list:
            raw_confidence = getattr(candidate, "confidence", None)
            if isinstance(raw_confidence, (int, float)):
                confidence_value = float(raw_confidence)
            else:
                continue
            if confidence_value >= 0.8:
                kept.append(candidate)
        return kept

    settings_near_row_all = _filter_by_y(settings_ports)
    settings_near_row = _filter_by_confidence(settings_near_row_all)

    if len(settings_near_row) == 0 and len(settings_near_row_all) > 0:
        _log(
            "[端口类型] Settings 候选存在但置信度均低于 0.8，放弃一步式识别，交由调用方回退模板搜索"
        )
        return (0, 0)

    if len(settings_near_row) > 0:
        pool = settings_near_row
        if isinstance(desired_side, str) and desired_side in ("left", "right"):
            preferred = [p for p in pool if str(getattr(p, "side", "")) == desired_side]
            if len(preferred) == 0:
                # 行内虽然有 Settings，但不在期望侧别上：不跨侧复用，交由调用方回退
                _log(
                    f"[端口类型] 行内存在 Settings 但无 {desired_side} 侧候选，放弃一步式识别，交由调用方回退",
                )
                return (0, 0)
            pool = preferred
        pool.sort(
            key=lambda candidate: (
                abs(get_port_center_y(candidate) - int(row_center_y)),
                -get_port_center_x(candidate),
            )
        )
        best = pool[0]
        return (
            int(best.center[0]),
            int(best.center[1]),
        )

    if len(settings_ports) == 0:
        row_candidates: List[Any] = []
        for port in ports_all:
            center_y = get_port_center_y(port)
            dy = abs(center_y - int(row_center_y))
            if dy <= int(y_tolerance):
                row_candidates.append(port)
        # 选取“行内非数据/流程端口”作为 Settings 候选，包括各类行内按钮/图标。
        non_connectable_like: List[Any] = [
            port
            for port in row_candidates
            if get_port_category(port)
            not in ("data_input", "data_output", "flow_input", "flow_output")
        ]
        if len(non_connectable_like) > 0:
            if isinstance(desired_side, str) and desired_side in ("left", "right"):
                pool = [
                    p
                    for p in non_connectable_like
                    if str(getattr(p, "side", "")) == desired_side
                ]
                if len(pool) == 0:
                    pool = non_connectable_like
            else:
                pool = non_connectable_like
            bx, by, bw, bh = (
                int(node_bbox[0]),
                int(node_bbox[1]),
                int(node_bbox[2]),
                int(node_bbox[3]),
            )
            if desired_side == "right":
                min_x = int(bx + bw * 0.60)
                pool = [p for p in pool if get_port_center_x(p) >= min_x]
            elif desired_side == "left":
                max_x = int(bx + bw * 0.40)
                pool = [p for p in pool if get_port_center_x(p) <= max_x]
            if len(pool) > 0:
                pool.sort(key=lambda p: get_port_center_x(p), reverse=True)
                best_any = pool[0]
                cx_any, cy_any = int(best_any.center[0]), int(best_any.center[1])
                _log(f"[端口类型] 识别缺少 Settings 标签：改用行内最右非数据元素 center=({cx_any},{cy_any})")
                return (cx_any, cy_any)
        return (0, 0)

    return (0, 0)


def find_icon_center_on_row(
    executor,
    screenshot,
    node_bbox: Tuple[int, int, int, int],
    port_center: Tuple[int, int],
    side: str,
    template_path: str,
    *,
    y_tolerance: int = 12,
    log_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[int, int]:
    """在指定端口行附近按侧别搜索行内图标模板，返回命中中心点坐标。

    说明：
    - 统一封装“根据端口中心与节点宽度估算横向搜索区间”的几何逻辑；
    - 调用方负责决定模板路径与后续点击/类型选择行为。
    """
    row_center_y = int(port_center[1])
    node_left = int(node_bbox[0])
    node_width = int(node_bbox[2])
    node_right = int(node_bbox[0] + node_width)

    side_normalized = str(side or "").lower()
    if side_normalized == "left":
        left_bound = max(int(port_center[0]) + 5, node_left + 4)
        right_bound = node_right - 4
    else:
        right_bound = max(0, int(port_center[0]) - 5)
        left_bound = max(node_left + 4, right_bound - node_width)

    # 先走原有模板匹配路径，以保持日志与可视化行为不变
    hit = _exec_utils.find_template_on_row(
        executor,
        screenshot,
        str(template_path),
        row_center_y,
        left_bound,
        right_bound,
        y_tolerance=int(y_tolerance),
        log_callback=log_callback,
    )

    band_top = int(max(0, row_center_y - int(y_tolerance)))
    band_bottom = int(row_center_y + int(y_tolerance))
    if band_bottom <= band_top or right_bound <= left_bound:
        if hit is None:
            return (0, 0)
        center_x_fallback, center_y_fallback, _ = hit
        return int(center_x_fallback), int(center_y_fallback)

    search_region = (
        int(left_bound),
        int(band_top),
        int(right_bound - left_bound),
        int(band_bottom - band_top),
    )

    # 在当前行的模板候选中，选择“置信度≥threshold 且离端口中心最近”的一个
    candidates = match_template_candidates(
        screenshot,
        str(template_path),
        search_region=search_region,
        threshold=0.8,
    )
    if len(candidates) == 0:
        if hit is None:
            return (0, 0)
        center_x_fallback, center_y_fallback, _ = hit
        return int(center_x_fallback), int(center_y_fallback)

    target_x = int(port_center[0])
    target_y = int(port_center[1])
    best_center_x = None
    best_center_y = None
    best_dist2 = None
    for center_x, center_y, score in candidates:
        if float(score) < 0.8:
            continue
        dx = int(center_x) - target_x
        dy = int(center_y) - target_y
        dist2 = dx * dx + dy * dy
        if best_dist2 is None or dist2 < best_dist2:
            best_dist2 = dist2
            best_center_x = int(center_x)
            best_center_y = int(center_y)

    if best_center_x is None or best_center_y is None:
        if hit is None:
            return (0, 0)
        center_x_fallback, center_y_fallback, _ = hit
        return int(center_x_fallback), int(center_y_fallback)

    return best_center_x, best_center_y

