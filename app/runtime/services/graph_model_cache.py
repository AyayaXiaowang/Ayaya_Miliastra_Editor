from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Tuple

from engine.graph.models.graph_model import GraphModel


@dataclass(frozen=True, slots=True)
class GraphModelCacheEntry:
    signature: str
    model: GraphModel


def _safe_float_pair(value: object) -> Tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        x_raw, y_raw = value[0], value[1]
        x_val = float(x_raw) if isinstance(x_raw, (int, float)) else 0.0
        y_val = float(y_raw) if isinstance(y_raw, (int, float)) else 0.0
        return (x_val, y_val)
    return (0.0, 0.0)


def _compute_graph_data_signature(graph_data: dict) -> str:
    """
    为 graph_data 计算稳定签名，用于在图内容变化时自动失效 GraphModel 缓存。

    注意：该签名必须覆盖“位置”等布局结果，否则会出现“自动排版后仍复用旧布局”的幽灵问题。
    """
    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []

    node_hasher = hashlib.sha1()
    edge_hasher = hashlib.sha1()

    if isinstance(nodes, list):
        node_tokens = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "")
            title_text = str(node.get("title") or "")
            pos = node.get("pos")
            if pos is None:
                pos = node.get("position")
            x_val, y_val = _safe_float_pair(pos)
            node_tokens.append((node_id, title_text, x_val, y_val))
        for node_id, title_text, x_val, y_val in sorted(node_tokens):
            node_hasher.update(node_id.encode("utf-8"))
            node_hasher.update(b"|")
            node_hasher.update(title_text.encode("utf-8"))
            node_hasher.update(b"|")
            node_hasher.update(str(x_val).encode("utf-8"))
            node_hasher.update(b",")
            node_hasher.update(str(y_val).encode("utf-8"))
            node_hasher.update(b"\x00")

    if isinstance(edges, list):
        edge_tokens = []
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            edge_id = str(edge.get("id") or "")
            src_node = str(edge.get("src_node") or "")
            dst_node = str(edge.get("dst_node") or "")
            src_port = str(edge.get("src_port") or "")
            dst_port = str(edge.get("dst_port") or "")
            edge_tokens.append((edge_id, src_node, src_port, dst_node, dst_port))
        for edge_id, src_node, src_port, dst_node, dst_port in sorted(edge_tokens):
            edge_hasher.update(edge_id.encode("utf-8"))
            edge_hasher.update(b"|")
            edge_hasher.update(src_node.encode("utf-8"))
            edge_hasher.update(b":")
            edge_hasher.update(src_port.encode("utf-8"))
            edge_hasher.update(b"->")
            edge_hasher.update(dst_node.encode("utf-8"))
            edge_hasher.update(b":")
            edge_hasher.update(dst_port.encode("utf-8"))
            edge_hasher.update(b"\x00")

    return f"v1:{node_hasher.hexdigest()}:{edge_hasher.hexdigest()}"


def get_or_build_graph_model(
    graph_identifier: str,
    *,
    graph_data: dict,
    cache: Dict[str, GraphModelCacheEntry],
) -> GraphModel:
    """根据 graph_id 和原始 graph_data 返回 GraphModel，并使用简单缓存。

    该模块与 Qt 与 UI 解耦，只负责：
    - 维护 graph_id → GraphModel 的内存缓存；
    - 当 graph_data 发生变化时，自动失效旧的 GraphModel，避免使用过期模型。
    """
    signature = _compute_graph_data_signature(graph_data)
    existing_entry = cache.get(graph_identifier)
    if existing_entry is not None and existing_entry.signature == signature:
        return existing_entry.model

    model = GraphModel.deserialize(graph_data)
    cache[graph_identifier] = GraphModelCacheEntry(signature=signature, model=model)
    return model


