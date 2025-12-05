from __future__ import annotations

from typing import Iterable, Optional

from app.automation.input.common import build_graph_region_overlay
from app.automation.vision import list_nodes, list_ports as list_ports_for_bbox
from app.automation.ports._ports import normalize_kind_text


def emit_node_and_port_overlays(
    executor,
    screenshot,
    node_bbox: tuple[int, int, int, int],
    visual_callback,
    *,
    ports: Optional[Iterable] = None,
    port_label_mode: str = "normalized",
    annotate_nodes: bool = True,
) -> None:
    """统一输出节点图区域、所有节点与端口叠加层。

    Args:
        executor: 执行器实例（需提供 `emit_visual` 与 `extract_chinese`）。
        screenshot: 当前截图。
        node_bbox: 目标节点的窗口坐标矩形。
        visual_callback: 可视化回调；为 None 时直接返回。
        ports: 可选端口列表，未提供时根据 node_bbox 自动识别。
        port_label_mode: 'normalized' 使用归一化 kind，'raw' 显示原始 kind。
        annotate_nodes: 是否输出全局节点矩形。
    """
    if visual_callback is None:
        return

    executor.emit_visual(screenshot, build_graph_region_overlay(screenshot), visual_callback)

    if annotate_nodes:
        rects_detected = []
        for detected_node in list_nodes(screenshot):
            bbox_x, bbox_y, bbox_w, bbox_h = detected_node.bbox
            label_cn = executor.extract_chinese(getattr(detected_node, "name_cn", "") or "")
            rects_detected.append(
                {
                    "bbox": (int(bbox_x), int(bbox_y), int(bbox_w), int(bbox_h)),
                    "color": (120, 200, 255),
                    "label": label_cn,
                }
            )
        if rects_detected:
            executor.emit_visual(screenshot, {"rects": rects_detected}, visual_callback)

    ports_list = list(ports) if ports is not None else list_ports_for_bbox(screenshot, node_bbox)
    if not ports_list:
        return

    rects_ports = []
    for port in ports_list:
        bbox_x, bbox_y, bbox_w, bbox_h = int(port.bbox[0]), int(port.bbox[1]), int(port.bbox[2]), int(port.bbox[3])
        side_text = str(getattr(port, "side", ""))
        index_text = str(getattr(port, "index", ""))
        name_cn = str(getattr(port, "name_cn", "") or "")
        if port_label_mode == "raw":
            kind_label = str(getattr(port, "kind", "") or "")
        else:
            kind_label = normalize_kind_text(getattr(port, "kind", ""))
        color = (255, 160, 80) if side_text == "right" else (0, 200, 120)
        rects_ports.append(
            {
                "bbox": (bbox_x, bbox_y, bbox_w, bbox_h),
                "color": color,
                "label": f"{side_text}#{index_text}:{name_cn or '?'}[{kind_label}]",
            }
        )

    executor.emit_visual(screenshot, {"rects": rects_ports}, visual_callback)


__all__ = ["emit_node_and_port_overlays"]

