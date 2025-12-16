from __future__ import annotations

"""GraphScene 装配辅助函数。"""

from typing import Optional

from engine.graph.models.graph_model import GraphModel
from app.ui.graph.graph_scene import GraphScene


def populate_scene_from_model(
    scene: GraphScene,
    *,
    enable_batch_mode: bool = True,
) -> None:
    """将 GraphModel 的节点与连线一次性添加到场景。

    Args:
        scene: 目标 GraphScene，需已绑定 `model`。
        enable_batch_mode: 是否在批量模式下插入，默认开启以避免重复计算场景边界。
    """
    if not isinstance(scene.model, GraphModel):
        raise ValueError("GraphScene 缺少有效的 GraphModel，无法装配内容")

    previous_bulk_flag = bool(getattr(scene, "is_bulk_adding_items", False))
    if enable_batch_mode:
        scene.is_bulk_adding_items = True

    for node in scene.model.nodes.values():
        scene.add_node_item(node)

    for edge in scene.model.edges.values():
        scene.add_edge_item(edge)

    if enable_batch_mode:
        # 批量装配时：连线创建会延迟“目标节点端口重排”，这里统一 flush 一次，
        # 避免每条边都触发 _layout_ports() 造成 O(E) 的重排开销。
        if hasattr(scene, "flush_deferred_port_layouts"):
            scene.flush_deferred_port_layouts()
        scene.is_bulk_adding_items = previous_bulk_flag

    # 统一刷新场景矩形与小地图缓存，确保视图加载后立即可用
    scene.rebuild_scene_rect_and_minimap()

