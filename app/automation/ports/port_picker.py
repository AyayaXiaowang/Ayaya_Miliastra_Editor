# -*- coding: utf-8 -*-
"""
port_picker: 端口挑选与几何/命名/序号回退逻辑
从 editor_connect.py 拆分，提供端口中心定位与 Settings 行识别功能。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Tuple, List, Any, Callable, NamedTuple
import re

from app.automation.ports._ports import (
    filter_ports_for_screen_candidates as _filter_ports_for_screen,
    get_port_category,
    get_port_center_y,
)
from app.automation.ports.settings_locator import select_settings_center
from engine.utils.graph.graph_utils import is_flow_port_name
from app.automation.core import executor_utils as _exec_utils
from app.automation import capture as editor_capture
from app.automation.input import win_input


def filter_screen_port_candidates(
    ports_all: List[Any],
    preferred_side: Optional[str],
    expected_kind: Optional[str],
) -> List[Any]:
    """
    按侧别/类型筛选端口候选，并按垂直位置排序。

    具体过滤规则委托给 `_ports.filter_ports_for_screen_candidates`，这里仅作为便捷包装。
    """
    return _filter_ports_for_screen(
        ports_all=ports_all,
        preferred_side=preferred_side,
        expected_kind=expected_kind,
    )


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

    约定：
    - 调用方需提供 ports_list（基于视觉识别得到的端口列表），本函数不再直接调用视觉识别；
    - 当 ports_list 为空或 None 时，返回 (0, 0)，由上层决定是否重试识别或走模板搜索等回退路径。
    """
    ports = list(ports_list) if ports_list is not None else []
    log = _exec_utils.make_executor_log_fn(executor, None)
    if len(ports) == 0:
        log(
            "[端口类型/Settings] 未提供端口识别结果，无法基于识别结果选择 Settings 行（返回 (0,0)）",
        )
        return (0, 0)

    return select_settings_center(
        ports=ports,
        node_bbox=node_bbox,
        row_center_y=row_center_y,
        desired_side=desired_side,
        y_tolerance=y_tolerance,
        log_fn=log,
    )


def _pick_port_center_from_ports(
    executor,
    ports: List[Any],
    desired_port: str,
    want_output: bool,
    expected_kind: str | None,
    log_callback=None,
    ordinal_fallback_index: Optional[int] = None,
) -> Tuple[int, int]:
    target_side = "right" if want_output else "left"

    effective_expected_kind = expected_kind
    if effective_expected_kind is None and desired_port:
        effective_expected_kind = "flow" if is_flow_port_name(desired_port) else "data"

    log_kind_miss = _exec_utils.make_executor_log_fn(executor, log_callback)

    candidates = _filter_ports_for_screen(
        ports_all=ports,
        preferred_side=target_side,
        expected_kind=effective_expected_kind,
        log_kind_miss=log_kind_miss,
    )

    desired_port_text = str(desired_port or "").strip()
    ordered_candidates = _order_port_candidates(candidates)

    context = PortPickContext(
        executor=executor,
        candidates=candidates,
        ordered_candidates=ordered_candidates,
        desired_port=desired_port,
        desired_port_text=desired_port_text,
        expected_kind=effective_expected_kind,
        ordinal_fallback_index=ordinal_fallback_index,
        log_callback=log_callback,
    )

    strategies: List[PortPickStrategy] = [
        _strategy_pick_by_name,
        _strategy_pick_by_ordinal_index,
        _strategy_pick_by_numeric_name,
        _strategy_pick_by_index_suffix,
        _strategy_pick_first_fallback,
    ]

    for strategy in strategies:
        chosen = strategy(context)
        if chosen is not None:
            return _extract_port_center(chosen)

    return (0, 0)


class PortPickContext(NamedTuple):
    executor: Any
    candidates: List[Any]
    ordered_candidates: List[Any]
    desired_port: str
    desired_port_text: str
    expected_kind: str | None
    ordinal_fallback_index: Optional[int]
    log_callback: Any


PortPickStrategy = Callable[[PortPickContext], Any | None]


def _port_matches_expected_kind(port_obj: Any, expected_kind: str | None) -> bool:
    """统一判断端口是否符合期望的 kind（flow/data）。

    通过 `_ports.get_port_category` 映射到高层语义，避免在此处重复维护
    对 flow/data/行内元素的细节判断逻辑。
    """
    if expected_kind not in ("flow", "data"):
        return True

    category = get_port_category(port_obj)
    if expected_kind == "flow":
        return category in ("flow_input", "flow_output")
    return category in ("data_input", "data_output")


def _pick_candidate_with_kind_preference(
    primary_candidates: List[Any],
    all_candidates: List[Any],
    expected_kind: str | None,
) -> Any | None:
    """在给定候选集中根据期望 kind 挑选端口。

    优先顺序：
    1. primary_candidates 的首个元素；
    2. primary_candidates 中首个 kind 匹配 expected_kind 的元素；
    3. all_candidates 中首个 kind 匹配 expected_kind 的元素；
    若均未命中，则回退到 primary_candidates[0]。
    """
    if len(primary_candidates) == 0:
        return None

    chosen = primary_candidates[0]
    if _port_matches_expected_kind(chosen, expected_kind):
        return chosen

    same_kind_primary = [
        port_obj
        for port_obj in primary_candidates
        if _port_matches_expected_kind(port_obj, expected_kind)
    ]
    if len(same_kind_primary) > 0:
        return same_kind_primary[0]

    same_kind_all = [
        port_obj
        for port_obj in all_candidates
        if _port_matches_expected_kind(port_obj, expected_kind)
    ]
    if len(same_kind_all) > 0:
        return same_kind_all[0]

    return chosen


def _order_port_candidates(candidates: List[Any]) -> List[Any]:
    def _sort_key(port_obj: Any) -> Tuple[int, int]:
        index_attr = getattr(port_obj, "index", None)
        index_value = int(index_attr) if index_attr is not None else 10 ** 6
        center_y = get_port_center_y(port_obj)
        return index_value, center_y

    return sorted(candidates, key=_sort_key)


def _extract_port_center(port_obj: Any) -> Tuple[int, int]:
    center_value = getattr(port_obj, "center")
    return int(center_value[0]), int(center_value[1])


def _log_picked_port(
    executor,
    chosen: Any,
    prefix: str,
    log_callback=None,
) -> None:
    center_x, center_y = _extract_port_center(chosen)
    log = _exec_utils.make_executor_log_fn(executor, log_callback)
    log(
        f"{prefix} center=({center_x},{center_y}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))} name='{str(getattr(chosen,'name_cn',''))}'",
    )


def _strategy_pick_by_name(context: PortPickContext) -> Any | None:
    return _pick_port_by_name(
        executor=context.executor,
        candidates=context.candidates,
        desired_port=context.desired_port,
        desired_port_text=context.desired_port_text,
        expected_kind=context.expected_kind,
        log_callback=context.log_callback,
    )


def _strategy_pick_by_ordinal_index(context: PortPickContext) -> Any | None:
    return _pick_port_by_ordinal_index(
        executor=context.executor,
        ordered_candidates=context.ordered_candidates,
        ordinal_fallback_index=context.ordinal_fallback_index,
        log_callback=context.log_callback,
    )


def _strategy_pick_by_numeric_name(context: PortPickContext) -> Any | None:
    return _pick_port_by_numeric_name(
        executor=context.executor,
        ordered_candidates=context.ordered_candidates,
        desired_port_text=context.desired_port_text,
        log_callback=context.log_callback,
    )


def _strategy_pick_by_index_suffix(context: PortPickContext) -> Any | None:
    return _pick_port_by_index_suffix(
        executor=context.executor,
        candidates=context.candidates,
        desired_port_text=context.desired_port_text,
        expected_kind=context.expected_kind,
        log_callback=context.log_callback,
    )


def _strategy_pick_first_fallback(context: PortPickContext) -> Any | None:
    return _pick_port_first_fallback(
        executor=context.executor,
        ordered_candidates=context.ordered_candidates,
        log_callback=context.log_callback,
    )


def _pick_port_by_name(
    executor,
    candidates: List[Any],
    desired_port: str,
    desired_port_text: str,
    expected_kind: str | None,
    log_callback=None,
) -> Any | None:
    if not desired_port:
        return None

    named_candidates = [
        port_obj
        for port_obj in candidates
        if str(getattr(port_obj, "name_cn", "") or "") == desired_port_text
    ]

    chosen = _pick_candidate_with_kind_preference(
        primary_candidates=named_candidates,
        all_candidates=candidates,
        expected_kind=expected_kind,
    )
    if chosen is None:
        return None

    center_x, center_y = _extract_port_center(chosen)
    executor.log(
        f"[端口定位] 命名优先: 端口='{desired_port}' 选择 center=({center_x},{center_y}) side={str(chosen.side)} kind={str(getattr(chosen,'kind',''))}",
        log_callback,
    )
    return chosen


def _pick_port_by_ordinal_index(
    executor,
    ordered_candidates: List[Any],
    ordinal_fallback_index: Optional[int],
    log_callback=None,
) -> Any | None:
    if ordinal_fallback_index is None or len(ordered_candidates) == 0:
        return None

    ordinal_index_value = int(ordinal_fallback_index)
    if ordinal_index_value < 0:
        ordinal_index_value = 0
    if ordinal_index_value >= len(ordered_candidates):
        ordinal_index_value = len(ordered_candidates) - 1

    chosen = ordered_candidates[ordinal_index_value]
    _log_picked_port(
        executor,
        chosen,
        f"[端口定位] 序号优先: ordinal={int(ordinal_index_value)} 选择",
        log_callback,
    )
    return chosen


def _pick_port_by_numeric_name(
    executor,
    ordered_candidates: List[Any],
    desired_port_text: str,
    log_callback=None,
) -> Any | None:
    if not desired_port_text.isdigit() or len(ordered_candidates) == 0:
        return None

    ordinal_value = int(desired_port_text)
    if ordinal_value < 1:
        return None
    if ordinal_value > len(ordered_candidates):
        return None

    chosen = ordered_candidates[ordinal_value - 1]
    _log_picked_port(
        executor,
        chosen,
        f"[端口定位] 序号优先: ordinal={int(ordinal_value)} 选择",
        log_callback,
    )
    return chosen


def _pick_port_by_index_suffix(
    executor,
    candidates: List[Any],
    desired_port_text: str,
    expected_kind: str | None,
    log_callback=None,
) -> Any | None:
    if desired_port_text.isdigit():
        return None

    match = re.search(r"(\d+)\s*$", desired_port_text)
    if not match:
        return None

    index_value = int(match.group(1))
    index_candidates = [
        port_obj
        for port_obj in candidates
        if getattr(port_obj, "index", None) is not None
        and int(port_obj.index) == int(index_value)
    ]

    chosen = _pick_candidate_with_kind_preference(
        primary_candidates=index_candidates,
        all_candidates=index_candidates,
        expected_kind=expected_kind,
    )
    if chosen is None:
        return None

    _log_picked_port(
        executor,
        chosen,
        f"[端口定位] 索引优先: index={int(index_value)} 选择",
        log_callback,
    )
    return chosen


def _pick_port_first_fallback(
    executor,
    ordered_candidates: List[Any],
    log_callback=None,
) -> Any | None:
    if len(ordered_candidates) == 0:
        return None

    chosen = ordered_candidates[0]
    _log_picked_port(
        executor,
        chosen,
        "[端口定位] 回退首项:",
        log_callback,
    )
    return chosen


def _reinspect_ports_after_moving_cursor_outside_node(
    executor,
    node_bbox: Tuple[int, int, int, int],
    log_callback=None,
    *,
    list_ports_for_bbox_func: Callable[[Any, Tuple[int, int, int, int]], List[Any]],
) -> Tuple[List[Any] | None, Any]:
    """
    当当前帧端口识别结果为空时，先尝试将鼠标移出节点到画布空白区域，再重新识别端口列表。

    仅在执行器具备窗口标题与坐标转换能力时启用；其它执行环境（如离线 real_executor）保持原行为。
    """
    log = _exec_utils.make_executor_log_fn(executor, log_callback)

    if not hasattr(executor, "convert_editor_to_screen_coords") or not hasattr(executor, "window_title"):
        log("[端口定位] 执行器不支持坐标转换/窗口访问，跳过移出节点后重试端口识别")
        return None, None

    nx, ny, nw, nh = node_bbox
    node_center_editor_x = int(nx + nw // 2)
    node_center_editor_y = int(ny + nh // 2)
    node_center_screen_x, node_center_screen_y = executor.convert_editor_to_screen_coords(
        node_center_editor_x,
        node_center_editor_y,
    )

    snapped_blank = _exec_utils.snap_screen_point_to_canvas_background(
        executor,
        int(node_center_screen_x),
        int(node_center_screen_y),
        log_callback=log_callback,
        visual_callback=None,
    )
    if snapped_blank is None:
        log("[端口定位] 未在画布内找到可用空白点，跳过移出节点后重试端口识别")
        return None, None

    blank_screen_x, blank_screen_y = int(snapped_blank[0]), int(snapped_blank[1])
    log(
        f"[端口定位] 本帧端口识别为空，先将鼠标移出节点到画布空白位置 screen=({blank_screen_x},{blank_screen_y}) 后重试一次端口识别",
    )
    win_input.move_mouse_absolute(int(blank_screen_x), int(blank_screen_y))
    _exec_utils.log_wait_if_needed(
        executor,
        0.1,
        "等待 0.10 秒（鼠标移出节点后重试端口识别）",
        log_callback,
    )

    retry_frame = editor_capture.capture_window(executor.window_title)
    if not retry_frame:
        log("[端口定位] 鼠标移出节点后截图失败，放弃本次端口重试")
        return None, None

    retry_ports = list_ports_for_bbox_func(retry_frame, node_bbox)
    return retry_ports, retry_frame


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
    *,
    list_ports_for_bbox_func: Optional[Callable[[Any, Tuple[int, int, int, int]], List[Any]]] = None,
) -> Tuple[int, int]:
    """
    为节点选择端口中心点。

    选择策略（优先级从高到低）：
    1. 命名匹配：按端口名精确匹配
    2. 序号优先（ordinal_fallback_index 不为 None 时）：按模型顺序的 0-based 序号选择第 N 个端口
    3. 数字端口名：按识别顺序（自上而下）选择第 N 个（1-based）
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
    log = _exec_utils.make_executor_log_fn(executor, log_callback)

    ports: List[Any]
    if ports_list is not None:
        ports = list(ports_list)
    else:
        if list_ports_for_bbox_func is None:
            log("[端口定位] 未提供端口识别结果或 list_ports_for_bbox 函数，无法定位端口")
            return (0, 0)
        ports = list(list_ports_for_bbox_func(screenshot, node_bbox))

    center = _pick_port_center_from_ports(
        executor,
        ports,
        desired_port,
        want_output,
        expected_kind,
        log_callback,
        ordinal_fallback_index,
    )
    if int(center[0]) != 0 or int(center[1]) != 0:
        return center

    if len(ports) == 0 and list_ports_for_bbox_func is not None:
        retry_ports, _retry_frame = _reinspect_ports_after_moving_cursor_outside_node(
            executor,
            node_bbox,
            log_callback,
            list_ports_for_bbox_func=list_ports_for_bbox_func,
        )
        if retry_ports is not None and len(retry_ports) > 0:
            center_retry = _pick_port_center_from_ports(
                executor,
                retry_ports,
                desired_port,
                want_output,
                expected_kind,
                log_callback,
                ordinal_fallback_index,
            )
            if int(center_retry[0]) != 0 or int(center_retry[1]) != 0:
                log("[端口定位] 鼠标移出节点后重试端口识别成功")
                return center_retry

    log("[端口定位] 无可用候选")
    return (0, 0)

