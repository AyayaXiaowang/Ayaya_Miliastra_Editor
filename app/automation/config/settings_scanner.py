# -*- coding: utf-8 -*-
"""
settings_scanner: 扫描节点的"设置"按钮所在端口并建立映射。

注意：
- 不新增异常捕获；保持与原实现一致的失败返回与日志输出。
- 仅做职责拆分与复用，不改变对外行为与时序。
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Callable, List
from PIL import Image

from engine.graph.models.graph_model import GraphModel
from app.automation.core.node_snapshot import capture_node_ports_snapshot
from engine.nodes.port_index_mapper import map_port_index_to_name
from app.automation.ports.settings_locator import collect_settings_rows


def execute_scan_settings(
    executor,
    todo_item: Dict[str, Any],
    graph_model: GraphModel,
    log_callback=None,
    pause_hook: Optional[Callable[[], None]] = None,
    allow_continue: Optional[Callable[[], bool]] = None,
    visual_callback: Optional[Callable[[Image.Image, Optional[dict]], None]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """扫描一批节点的"设置"按钮所在端口并建立映射，返回 {node_id -> settings 列表}。

    规则：
    - 仅识别端口行内 kind=='settings' 的标记，并记录其 side/index；
    - 通过节点定义库将 (side, index) → 端口名；
    - 仅做记录与可视化，不在此步进行任何点击。
    """
    if pause_hook is not None:
        pause_hook()
    if allow_continue is not None and not allow_continue():
        executor._log("用户终止/暂停，放弃设置扫描", log_callback)
        return {}
    screenshot = executor.capture_and_emit(label="设置扫描", overlays_builder=None, visual_callback=visual_callback)
    if not screenshot:
        executor._log("✗ 截图失败（设置扫描）", log_callback)
        return {}

    node_ids = []
    di = todo_item or {}
    if isinstance(di.get("node_ids"), list):
        node_ids = [str(x) for x in di.get("node_ids")]

    scanned: Dict[str, List[Dict[str, object]]] = {}
    for nid in node_ids:
        node = graph_model.nodes.get(nid)
        if node is None:
            continue
        debug: Dict[str, Any] = {}
        snap, bbox, ports = capture_node_ports_snapshot(
            executor,
            node,
            screenshot=screenshot,
            debug=debug,
            log_callback=log_callback,
            label="[设置扫描]",
        )
        if snap is None or int(bbox[2]) <= 0:
            continue
        settings_rows = collect_settings_rows(ports)
        if len(settings_rows) == 0:
            executor._log(f"[设置扫描] 无设置按钮: {node.title}({nid})", log_callback)
            continue
        items: List[Dict[str, object]] = []
        for snapshot in settings_rows:
            side = snapshot.side or "unknown"
            index_val = snapshot.index
            mapped_name = None
            if isinstance(index_val, int):
                mapped_name = map_port_index_to_name(node.title, side, int(index_val))
            items.append({
                'side': side,
                'index': index_val,
                'port_name': None if mapped_name is None else str(mapped_name),
            })
        scanned[nid] = items
        executor._log(
            f"[设置扫描] {node.title}({nid}) 命中 {len(items)} 项: " + \
            ", ".join([f"{it.get('side','?')}#{it.get('index','?')}→{it.get('port_name','?')}" for it in items]),
            log_callback
        )

    return scanned

