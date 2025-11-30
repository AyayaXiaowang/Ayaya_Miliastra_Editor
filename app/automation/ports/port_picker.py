# -*- coding: utf-8 -*-
"""
port_picker: 端口挑选与几何/命名/序号回退逻辑
从 editor_connect.py 拆分，提供端口中心定位与 Settings 行识别功能。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Any
import re

from app.automation.ports._ports import (
    normalize_kind_text,
    is_non_connectable_kind,
)
from app.automation.ports.settings_locator import select_settings_center
from engine.utils.graph.graph_utils import is_flow_port_name


def filter_screen_port_candidates(
    ports_all: List[Any],
    preferred_side: Optional[str],
    expected_kind: Optional[str],
) -> List[Any]:
    """
    按侧别/类型筛选端口候选，并按垂直位置排序。

    Args:
        ports_all: 识别到的端口列表
        preferred_side: 'left' 或 'right'，None 表示不限制
        expected_kind: 'flow' / 'data' / None
    """
    candidates = list(ports_all)
    side = (preferred_side or "").lower()
    if side in ("left", "right"):
        specific = [p for p in candidates if str(getattr(p, "side", "")).lower() == side]
        if len(specific) > 0:
            candidates = specific
    candidates = [p for p in candidates if not is_non_connectable_kind(getattr(p, "kind", ""))]
    if expected_kind in ("flow", "data"):
        kind_norm = expected_kind
        by_kind = [p for p in candidates if normalize_kind_text(getattr(p, "kind", "")) == kind_norm]
        if len(by_kind) > 0:
            candidates = by_kind
    candidates = sorted(candidates, key=lambda p: int(getattr(p, "center", (0, 0))[1]))
    return candidates


def pick_settings_center_by_recognition(
    executor,
    screenshot,
    node_bbox: Tuple[int, int, int, int],
    row_center_y: int,
    y_tolerance: int = 14,
    desired_side: Optional[str] = None,  # 'left' / 'right' 优先选择该侧的 Settings
    ports_list: Optional[List[Any]] = None,
) -> Tuple[int, int]:
    """
    基于一步式识别结果，选择与给定行 y 最接近的 Settings 行中心点。
    - 不依赖行内模板横向搜索，直接使用识别到的 'settings' 端口（按侧优先）。
    - 若在容差内未找到，返回 (0, 0) 由调用方决定回退策略。
    """
    from app.automation.vision import list_ports as list_ports_for_bbox
    ports = ports_list if ports_list is not None else list_ports_for_bbox(screenshot, node_bbox)

    def _log(message: str) -> None:
        executor._log(message, None)

    return select_settings_center(
        ports=ports,
        node_bbox=node_bbox,
        row_center_y=row_center_y,
        desired_side=desired_side,
        y_tolerance=y_tolerance,
        log_fn=_log,
    )


def pick_port_center_for_node(
    executor,
    screenshot,
    node_bbox: Tuple[int, int, int, int],
    desired_port: str,
    want_output: bool,
    expected_kind: str | None = None,
    log_callback=None,
    ordinal_fallback_index: Optional[int] = None,
    ports_list: Optional[List[Any]] = None,
) -> Tuple[int, int]:
    """
    为节点选择端口中心点。

    选择策略（优先级从高到低）：
    1. 序号优先（ordinal_fallback_index 不为 None 时）：按模型顺序的 0-based 序号选择第 N 个端口
    2. 数字端口名：按识别顺序（自上而下）选择第 N 个（1-based）
    3. 命名匹配：按端口名精确匹配
    4. 索引匹配：提取末尾数字作为索引匹配
    5. 回退首项：选择第一个候选

    参数：
    - executor: 执行器实例
    - screenshot: 当前截图
    - node_bbox: 节点边界框 (x, y, w, h)
    - desired_port: 期望端口名
    - want_output: True=输出端口(右侧), False=输入端口(左侧)
    - expected_kind: 期望端口类型 ('flow' / 'data' / None)
    - log_callback: 日志回调
    - ordinal_fallback_index: 模型顺序的序号（0-based），若提供则优先使用
    - ports_list: 可选的预识别端口列表，避免重复识别

    返回：
    - (center_x, center_y) 或 (0, 0) 表示未找到
    """
    from app.automation.vision import list_ports as list_ports_for_bbox
    ports = ports_list if ports_list is not None else list_ports_for_bbox(screenshot, node_bbox)

    target_side = 'right' if want_output else 'left'
    base_candidates = filter_screen_port_candidates(
        ports,
        preferred_side=target_side,
        expected_kind=None,
    )
    kind_expected = expected_kind
    if kind_expected is None and desired_port:
        kind_expected = 'flow' if is_flow_port_name(desired_port) else 'data'
    candidates = base_candidates
    if kind_expected in ('flow', 'data'):
        candidates_by_kind = [p for p in base_candidates if normalize_kind_text(getattr(p, 'kind', '')) == kind_expected]
        if len(candidates_by_kind) == 0:
            # 不再直接失败：保留原 candidates，继续尝试命名/索引/序号回退
            executor._log(f"[端口定位] 期望类型 '{kind_expected}' 无候选，改为不限制类型继续匹配", log_callback)
        else:
            candidates = candidates_by_kind

    ordered_candidates_cache: List[Any] | None = None

    def _get_ordered_candidates() -> List[Any]:
        nonlocal ordered_candidates_cache
        if ordered_candidates_cache is None:
            def _sort_key(port_obj):
                idx_attr = getattr(port_obj, 'index', None)
                idx_val = int(idx_attr) if idx_attr is not None else 10**6
                center_val = getattr(port_obj, 'center', (0, 0))
                center_y = int(center_val[1]) if isinstance(center_val, tuple) and len(center_val) >= 2 else 0
                return (idx_val, center_y)
            ordered_candidates_cache = sorted(candidates, key=_sort_key)
        return ordered_candidates_cache

    dp = str(desired_port or "").strip()
    if desired_port:
        named = [p for p in candidates if str(getattr(p, 'name_cn', '') or '') == dp]
        if len(named) > 0:
            chosen = named[0]
            if kind_expected in ('flow','data') and normalize_kind_text(getattr(chosen, 'kind', '')) != kind_expected:
                same_kind = [p for p in named if normalize_kind_text(getattr(p,'kind','')) == kind_expected]
                if len(same_kind) == 0:
                    same_kind = [p for p in candidates if normalize_kind_text(getattr(p,'kind','')) == kind_expected]
                if len(same_kind) > 0:
                    chosen = same_kind[0]
            executor._log(
                f"[端口定位] 命名优先: 端口='{desired_port}' 选择 center=({int(chosen.center[0])},{int(chosen.center[1])}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))}",
                log_callback
            )
            return (int(chosen.center[0]), int(chosen.center[1]))

    # 优先遵循调用方提供的序号（来自模型顺序的 0-based 序号）
    if ordinal_fallback_index is not None and len(candidates) > 0:
        ord_idx = int(ordinal_fallback_index)
        if ord_idx < 0:
            ord_idx = 0
        ordered = _get_ordered_candidates()
        if ord_idx >= len(ordered):
            ord_idx = len(ordered) - 1
        chosen = ordered[ord_idx]
        executor._log(
            f"[端口定位] 序号优先: ordinal={int(ord_idx)} 选择 center=({int(chosen.center[0])},{int(chosen.center[1])}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))} name='{str(getattr(chosen,'name_cn',''))}'",
            log_callback
        )
        return (int(chosen.center[0]), int(chosen.center[1]))

    # 数字端口名：按定义序号（优先 index，其次垂直顺序）选择第 N 个（1-based）
    if dp.isdigit():
        ord_val = int(dp)
        if ord_val >= 1 and len(candidates) > 0:
            ordered = _get_ordered_candidates()
            if ord_val <= len(ordered):
                chosen = ordered[ord_val - 1]
                executor._log(
                    f"[端口定位] 序号优先: ordinal={int(ord_val)} 选择 center=({int(chosen.center[0])},{int(chosen.center[1])}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))} name='{str(getattr(chosen,'name_cn',''))}'",
                    log_callback
                )
                return (int(chosen.center[0]), int(chosen.center[1]))

    idx_val: int | None = None
    # 兼容带数字后缀的命名（如 '分支_2'）：提取末尾数字作为索引匹配
    if not dp.isdigit():
        m = re.search(r"(\d+)\s*$", dp)
        if m:
            idx_val = int(m.group(1))
    if idx_val is not None:
        by_index = [p for p in candidates if getattr(p, 'index', None) is not None and int(p.index) == int(idx_val)]
        if len(by_index) > 0:
            chosen = by_index[0]
            if kind_expected in ('flow','data') and normalize_kind_text(getattr(chosen, 'kind', '')) != kind_expected:
                same_kind = [p for p in by_index if normalize_kind_text(getattr(p,'kind','')) == kind_expected]
                if len(same_kind) > 0:
                    chosen = same_kind[0]
            executor._log(
                f"[端口定位] 索引优先: index={int(idx_val)} 选择 center=({int(chosen.center[0])},{int(chosen.center[1])}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))} name='{str(getattr(chosen,'name_cn',''))}'",
                log_callback
            )
            return (int(chosen.center[0]), int(chosen.center[1]))

    # 注：若未提供 ordinal，后续不再进行"序号回退"，只保留最终首项回退。

    if len(candidates) > 0:
        ordered = _get_ordered_candidates()
        chosen = ordered[0]
        executor._log(
            f"[端口定位] 回退首项: center=({int(chosen.center[0])},{int(chosen.center[1])}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))} name='{str(getattr(chosen,'name_cn',''))}'",
            log_callback
        )
        return (int(chosen.center[0]), int(chosen.center[1]))

    executor._log("[端口定位] 无可用候选", log_callback)
    return (0, 0)

