from __future__ import annotations

from typing import Dict

from engine.graph.models.graph_model import GraphModel


def get_or_build_graph_model(
    graph_identifier: str,
    *,
    graph_data: dict,
    cache: Dict[str, GraphModel],
) -> GraphModel:
    """根据 graph_id 和原始 graph_data 返回 GraphModel，并使用简单缓存。

    该模块与 Qt 与 UI 解耦，只负责：
    - 维护 graph_id → GraphModel 的内存缓存；
    - 在缓存未命中时使用 GraphModel.deserialize 进行反序列化。
    """
    existing_model = cache.get(graph_identifier)
    if existing_model is not None:
        return existing_model

    model = GraphModel.deserialize(graph_data)
    cache[graph_identifier] = model
    return model


