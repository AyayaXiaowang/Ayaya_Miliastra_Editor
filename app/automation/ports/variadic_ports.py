# -*- coding: utf-8 -*-
"""
variadic_ports: 为节点添加变参输入端口。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, List, Tuple
import re
from PIL import Image

from app.automation.editor.executor_protocol import EditorExecutorWithViewport
from app.automation.editor.node_snapshot import NodePortsSnapshotCache
from app.automation.ports._add_ports_common import execute_add_ports_generic
from app.automation.ports._ports import is_data_input_port
from engine.graph.models.graph_model import GraphModel


def _compute_variadic_final_add_count(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    node_model,
    add_count_initial: int,
    list_ports_for_bbox_func: Optional[Callable[[Image.Image, tuple[int, int, int, int]], List[Any]]],
    log_callback=None,
) -> Tuple[bool, int]:
    """根据当前端口数量与目标数量计算变参端口最终新增数量。

    返回:
        (ok, final_add_count)
    """
    add_count = int(add_count_initial or 0)
    if add_count > 0:
        return True, add_count

    desired_total = 0
    values = todo_item.get("values") or todo_item.get("items")
    target_count_field = todo_item.get("target_count") or todo_item.get("target_total")
    if isinstance(target_count_field, int):
        desired_total = int(target_count_field)
    elif isinstance(values, (list, tuple)):
        desired_total = int(len(values))

    if desired_total <= 0:
        return True, add_count

    # 统一使用 NodePortsSnapshotCache 获取端口列表，避免在本模块重复实现截图与节点定位逻辑
    snapshot_cache = NodePortsSnapshotCache(executor, node_model, log_callback)
    ok_snapshot = snapshot_cache.ensure(
        reason="变参端口统计",
        require_bbox=False,
    )
    if not ok_snapshot:
        executor.log("✗ 未能刷新节点端口快照（统计变参端口）", log_callback)
        return False, 0

    ports_now = list(snapshot_cache.ports)
    current_numeric_inputs = [
        port
        for port in ports_now
        if is_data_input_port(port)
        and isinstance(getattr(port, "name_cn", None), str)
        and re.match(r"^\d+$", str(getattr(port, "name_cn", "") or "")) is not None
    ]
    cur_count = int(len(current_numeric_inputs))
    add_count = max(0, desired_total - cur_count)
    executor.log(f"· 变参端口：当前{cur_count}，目标{desired_total}，计划新增{add_count}", log_callback)

    return True, add_count


def execute_add_variadic_inputs(
    executor: EditorExecutorWithViewport,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
    *,
    list_ports_for_bbox_func: Optional[Callable[[Image.Image, tuple[int, int, int, int]], List[Any]]] = None,
) -> bool:
    return execute_add_ports_generic(
        executor,
        todo_item,
        graph_model,
        feature_label="变参端口添加",
        prefer_multi=False,
        log_callback=log_callback,
        pause_hook=pause_hook,
        allow_continue=allow_continue,
        visual_callback=visual_callback,
        list_ports_for_bbox_func=list_ports_for_bbox_func,
        compute_final_add_count=_compute_variadic_final_add_count,
    )

