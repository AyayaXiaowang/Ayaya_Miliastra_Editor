from __future__ import annotations

from typing import Tuple, Optional

from engine.graph.models.graph_config import GraphConfig
from engine.graph.models.graph_model import GraphModel
from engine.resources.resource_manager import ResourceType, ResourceManager


def deserialize_model(graph_data: dict) -> GraphModel:
    """将图数据反序列化为 GraphModel。"""
    return GraphModel.deserialize(graph_data or {})


def load_graph_by_id(resource_manager: ResourceManager, graph_id: str) -> Tuple[Optional[GraphConfig], Optional[GraphModel]]:
    """
    按 ID 加载节点图配置与模型。
    返回 (GraphConfig | None, GraphModel | None)。
    """
    data = resource_manager.load_resource(ResourceType.GRAPH, graph_id)
    if not data:
        return None, None
    graph_config = GraphConfig.deserialize(data)
    model = GraphModel.deserialize(graph_config.data or {})
    return graph_config, model


