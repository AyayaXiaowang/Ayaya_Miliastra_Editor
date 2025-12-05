# -*- coding: utf-8 -*-
"""
port_type_context: 端口类型推断所需的图上下文工具。

职责：
- 为 GraphModel 构建入/出边索引，加速类型推断阶段的查询；
- 标准化 GraphModel.metadata['port_type_overrides'] 结构；
- 处理 copy_block 节点的 ID 归一化与覆盖表查询；
- 提供在有无 EdgeLookup 的前提下统一的入/出边遍历辅助函数。

模块定位：
- 作为 `app.automation.ports` 包的内部实现模块，仅供本包内部使用；
- 包外调用方如需构建端口类型推断上下文，应通过
  `app.automation.ports.port_type_inference` 导入公共 API（例如 `EdgeLookup`、
  `build_edge_lookup`、`build_port_type_overrides` 等），不要直接依赖本模块或其
  下划线辅助函数。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Literal

from engine.graph.models.graph_model import GraphModel
from app.automation.ports.port_type_common import (
    is_flow_type_name,
    is_generic_type_name,
)


@dataclass(frozen=True)
class EdgeLookup:
    incoming: Dict[str, Dict[str, List[Any]]]
    outgoing: Dict[str, Dict[str, List[Any]]]


def _compute_edges_signature(edges: Dict[str, Any]) -> Tuple[int, int]:
    """基于边集合构建轻量级签名，用于 EdgeLookup 缓存失效判断。

    说明：
    - 使用“边数量 + 基于端点信息的异或哈希”构成签名，避免在图结构未变更时重复重建索引；
    - 仅依赖于边的 ID、src/dst 节点与端口名，与运行时对象身份无关。
    """
    checksum = 0
    count = 0
    for edge_id, edge in edges.items():
        count += 1
        src_node = getattr(edge, "src_node", "")
        src_port = getattr(edge, "src_port", "")
        dst_node = getattr(edge, "dst_node", "")
        dst_port = getattr(edge, "dst_port", "")
        checksum ^= hash((str(edge_id), str(src_node), str(src_port), str(dst_node), str(dst_port)))
    return count, checksum


def build_port_type_overrides(graph_model: GraphModel) -> Dict[str, Dict[str, str]]:
    """标准化 GraphModel.metadata['port_type_overrides'] 结构.

    说明：
    - 将 metadata 中的端口类型覆盖信息收敛为 {node_id: {port_name: type_text}} 形式；
    - 仅保留 key/value 均为字符串的条目，避免后续使用时做重复类型判断；
    - 不在此处做“去泛型/去流程”过滤，由调用方按各自语义决定是否忽略。
    """
    # 若已在 GraphModel 上构建过覆盖表，则直接复用缓存，避免在每次类型推断时重复扫描 metadata。
    cached_overrides = getattr(graph_model, "_automation_port_type_overrides_cache", None)
    if isinstance(cached_overrides, dict):
        return cached_overrides

    overrides_result: Dict[str, Dict[str, str]] = {}
    metadata_object = getattr(graph_model, "metadata", {}) or {}
    overrides_raw = metadata_object.get("port_type_overrides")
    if not isinstance(overrides_raw, dict):
        setattr(graph_model, "_automation_port_type_overrides_cache", overrides_result)
        return overrides_result

    for node_key, mapping in overrides_raw.items():
        if not isinstance(node_key, str) or not isinstance(mapping, dict):
            continue
        normalized_mapping: Dict[str, str] = {}
        for port_name, type_text in mapping.items():
            if not isinstance(port_name, str) or not isinstance(type_text, str):
                continue
            normalized_mapping[port_name] = type_text
        if normalized_mapping:
            overrides_result[node_key] = normalized_mapping

    setattr(graph_model, "_automation_port_type_overrides_cache", overrides_result)
    return overrides_result


def build_edge_lookup(graph_model: GraphModel) -> EdgeLookup:
    """构建节点入/出边的索引，加速类型推断阶段的查询。

    内部会基于边集合的签名在 GraphModel 实例上做一次性缓存：
    - 当边数量与签名均未发生变化时，复用已有 EdgeLookup；
    - 当图结构发生变化（增加/删除/重连边）时，自动重建索引。
    """
    edges = getattr(graph_model, "edges", {})
    if not isinstance(edges, dict):
        edges = {}

    signature = _compute_edges_signature(edges)
    cached_lookup = getattr(graph_model, "_automation_edge_lookup_cache", None)
    cached_signature = getattr(graph_model, "_automation_edge_lookup_signature", None)
    if isinstance(cached_lookup, EdgeLookup) and cached_signature == signature:
        return cached_lookup

    incoming: Dict[str, Dict[str, List[Any]]] = {}
    outgoing: Dict[str, Dict[str, List[Any]]] = {}
    for edge in edges.values():
        incoming.setdefault(edge.dst_node, {}).setdefault(edge.dst_port, []).append(edge)
        outgoing.setdefault(edge.src_node, {}).setdefault(edge.src_port, []).append(edge)

    lookup = EdgeLookup(incoming=incoming, outgoing=outgoing)
    setattr(graph_model, "_automation_edge_lookup_cache", lookup)
    setattr(graph_model, "_automation_edge_lookup_signature", signature)
    return lookup


def normalize_node_id_for_overrides(node_id: object) -> str:
    """将可能带有 copy_block 后缀的节点 ID 归一化为原始节点 ID。

    例如：
        "node_以键查询字典值_446c5c6c_copy_block_2_1" → "node_以键查询字典值_446c5c6c"
    """
    if not isinstance(node_id, str):
        return ""

    raw_id_text = node_id.strip()
    if raw_id_text == "":
        return ""

    marker_text = "_copy_block_"
    marker_index = raw_id_text.find(marker_text)
    if marker_index > 0:
        return raw_id_text[:marker_index]
    return raw_id_text


def get_node_port_type_overrides_for_id(
    overrides_mapping: Dict[str, Dict[str, str]],
    node_identifier: object,
) -> Optional[Dict[str, str]]:
    """根据节点 ID 获取端口类型覆盖信息，自动兼容 copy_block 节点。

    查找顺序：
    1）尝试以完整 ID 精确匹配；
    2）若未命中，则将 ID 归一化为“去掉 _copy_block_ 后缀”的形式再查找。
    """
    if not isinstance(overrides_mapping, dict):
        return None
    if not isinstance(node_identifier, str):
        return None

    direct_mapping = overrides_mapping.get(node_identifier)
    if isinstance(direct_mapping, Dict):
        return direct_mapping

    normalized_id = normalize_node_id_for_overrides(node_identifier)
    if normalized_id and normalized_id != node_identifier:
        base_mapping = overrides_mapping.get(normalized_id)
        if isinstance(base_mapping, Dict):
            return base_mapping

    return None


def resolve_port_type_with_overrides(
    overrides_mapping: Dict[str, Dict[str, str]],
    node_identifier: object,
    port_name: object,
) -> Optional[str]:
    """根据覆盖表解析端口类型，只返回“非空、非泛型、非流程”的有效类型。

    规则：
    - 若对应节点或端口在覆盖表中不存在，则返回 None；
    - 若覆盖值为空字符串、泛型类型（如“泛型/泛型列表/泛型字典”等）或流程类型，则忽略返回 None；
    - 其余情况返回去除首尾空白后的类型名。
    """
    if not isinstance(overrides_mapping, dict):
        return None

    if not isinstance(port_name, str):
        return None

    node_overrides = get_node_port_type_overrides_for_id(overrides_mapping, node_identifier)
    if not isinstance(node_overrides, dict):
        return None

    raw_type = node_overrides.get(port_name)
    if not isinstance(raw_type, str):
        return None

    text = raw_type.strip()
    if not text:
        return None

    if is_generic_type_name(text):
        return None

    if is_flow_type_name(text):
        return None

    return text


def _iter_edges(
    node_id: str,
    port_name: str,
    graph_model: GraphModel,
    edge_lookup: EdgeLookup | None,
    direction: Literal["in", "out"],
) -> List[Any]:
    """遍历指定节点端口的所有入/出边，在有无 EdgeLookup 场景下提供统一实现。

    参数 direction:
        - "in": 遍历入边（dst_* 指向给定节点端口）；
        - "out": 遍历出边（src_* 从给定节点端口出发）。
    """
    if edge_lookup is not None:
        if direction == "in":
            return edge_lookup.incoming.get(node_id, {}).get(port_name, [])
        return edge_lookup.outgoing.get(node_id, {}).get(port_name, [])

    edges_sequence = getattr(graph_model, "edges", {}).values()
    if direction == "in":
        return [
            edge
            for edge in edges_sequence
            if edge.dst_node == node_id and edge.dst_port == port_name
        ]
    return [
        edge
        for edge in edges_sequence
        if edge.src_node == node_id and edge.src_port == port_name
    ]


def _iter_incoming_edges(
    node_id: str,
    port_name: str,
    graph_model: GraphModel,
    edge_lookup: EdgeLookup | None,
) -> List[Any]:
    """遍历指定节点端口的所有入边，在有无 EdgeLookup 场景下提供统一接口。"""
    return _iter_edges(node_id, port_name, graph_model, edge_lookup, "in")


def _iter_outgoing_edges(
    node_id: str,
    port_name: str,
    graph_model: GraphModel,
    edge_lookup: EdgeLookup | None,
) -> List[Any]:
    """遍历指定节点端口的所有出边，在有无 EdgeLookup 场景下提供统一接口。"""
    return _iter_edges(node_id, port_name, graph_model, edge_lookup, "out")


__all__ = [
    "EdgeLookup",
    "build_edge_lookup",
    "build_port_type_overrides",
    "normalize_node_id_for_overrides",
    "get_node_port_type_overrides_for_id",
    "resolve_port_type_with_overrides",
]


