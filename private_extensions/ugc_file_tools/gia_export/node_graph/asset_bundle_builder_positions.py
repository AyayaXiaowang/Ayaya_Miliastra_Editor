from __future__ import annotations

from typing import Any, Dict, Mapping, Tuple

from ugc_file_tools.graph.node_graph.pos_scale import resolve_node_pos_scale_from_graph_json


def build_node_positions(
    *,
    graph_json_object: Dict[str, Any],
    node_index_by_graph_node_id: Mapping[str, int],
    node_payload_by_graph_node_id: Mapping[str, Dict[str, Any]],
    fallback_scale: float,
) -> Tuple[Dict[str, Tuple[float, float]], float]:
    """
    计算导出 `.gia` 用的节点坐标：
    - GraphModel.payload.pos: Graph_Generater 画布坐标系
    - 导出时对 x/y 同步乘以 node_pos_scale
    - 再做一次 X 轴居中偏移（bbox 中心对齐到 X=0），对齐编辑器画布语义

    返回：
    - pos_by_graph_node_id: {graph_node_id: (x, y)}（已缩放，未叠加 x_offset）
    - x_offset: 需要叠加到所有 x 上的偏移量
    """
    pos_by_graph_node_id: Dict[str, Tuple[float, float]] = {}
    xs: list[float] = []

    node_pos_scale = resolve_node_pos_scale_from_graph_json(
        graph_json_object=graph_json_object,
        fallback_scale=float(fallback_scale),
    )

    for graph_node_id in node_index_by_graph_node_id.keys():
        payload = node_payload_by_graph_node_id.get(str(graph_node_id))
        if not isinstance(payload, dict):
            continue
        pos = payload.get("pos")
        x0 = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        y0 = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        x = float(x0) * float(node_pos_scale)
        y = float(y0) * float(node_pos_scale)
        pos_by_graph_node_id[str(graph_node_id)] = (float(x), float(y))
        xs.append(float(x))

    x_offset = 0.0
    if xs:
        x_offset = -((min(xs) + max(xs)) / 2.0)

    return pos_by_graph_node_id, float(x_offset)

