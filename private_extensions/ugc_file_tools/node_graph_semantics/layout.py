from __future__ import annotations

from typing import Any, Callable, Dict, List, Sequence, Tuple

from ugc_file_tools.graph.node_graph.pos_scale import resolve_node_pos_scale_from_graph_json


_SortedNode = Tuple[float, float, str, str, Dict[str, Any]]  # (y, x, title, node_id, node_payload)

# Public type alias (no leading underscore). Keep the private alias for internal readability.
SortedNode = _SortedNode


def _sort_graph_nodes_for_stable_ids(nodes: Sequence[Dict[str, Any]]) -> List[_SortedNode]:
    # 稳定分配 node_id_int：按 (y,x,title,id) 排序
    sorted_nodes: List[_SortedNode] = []
    for node in list(nodes):
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "")
        title = str(node.get("title") or "").strip()
        pos = node.get("pos")
        x = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        y = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        sorted_nodes.append((y, x, title, node_id, node))
    sorted_nodes.sort(key=lambda t: (t[0], t[1], t[2], t[3]))
    return sorted_nodes


# ---------------------------------------------------------------------------
# Public API (no leading underscores)
#
# Import policy: cross-module imports must not import underscored private names.


def sort_graph_nodes_for_stable_ids(nodes: Sequence[Dict[str, Any]]) -> List[SortedNode]:
    return _sort_graph_nodes_for_stable_ids(nodes)


def _build_pos_transform(
    *,
    graph_json_object: Dict[str, Any],
    template_entry: Dict[str, Any],
    sorted_nodes: Sequence[SortedNode],
) -> Callable[[float, float], Tuple[float, float]]:
    # ===== 坐标写回策略（与 GIA 导出统一）=====
    # 统一使用：
    # - 节点坐标按同一 scale 缩放（默认 2.0）；
    # - X 轴整体居中到 0（仅平移，不改变相对布局）；
    # 这样 GIL / GIA 对同一 GraphModel 的“坐标密度”保持一致。
    _ = template_entry  # 保留签名兼容，当前策略不再依赖模板 bbox。

    node_pos_scale = resolve_node_pos_scale_from_graph_json(
        graph_json_object=graph_json_object,
        fallback_scale=2.0,
    )

    xs = [float(_x) * float(node_pos_scale) for (_y, _x, _t, _id, _n) in sorted_nodes]
    x_offset = -((min(xs) + max(xs)) / 2.0) if xs else 0.0

    def _transform_pos(x: float, y: float) -> Tuple[float, float]:
        return (
            float(float(x) * float(node_pos_scale) + float(x_offset)),
            float(float(y) * float(node_pos_scale)),
        )

    return _transform_pos


def build_pos_transform(
    *,
    graph_json_object: Dict[str, Any],
    template_entry: Dict[str, Any],
    sorted_nodes: Sequence[SortedNode],
) -> Callable[[float, float], Tuple[float, float]]:
    """对外稳定入口：构造坐标变换函数（缩放 + X 轴居中），供 `.gil` 写回与 `.gia` 导出共同复用。"""
    return _build_pos_transform(
        graph_json_object=dict(graph_json_object),
        template_entry=dict(template_entry),
        sorted_nodes=list(sorted_nodes),
    )

