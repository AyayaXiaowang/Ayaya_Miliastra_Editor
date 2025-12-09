"""
数据节点复制工具

提供数据节点复制相关的基础工具函数。

新流程：
- 复制逻辑主要由 GlobalCopyManager 管理
- 此模块保留基础工具函数供复用
"""

from __future__ import annotations
from typing import Optional, List, Dict
from dataclasses import replace

from engine.graph.models import GraphModel, NodeModel, PortModel


def _resolve_canonical_original_id(node: NodeModel) -> str:
    """解析数据节点副本链的"根原始节点 ID"。
    
    - 若节点本身已带有 original_node_id，则使用该字段；
    - 否则根据命名约定去掉 `_copy_...` 后缀获得原始 ID。
    """
    if getattr(node, "original_node_id", ""):
        return node.original_node_id
    return _strip_copy_suffix(getattr(node, "id", ""))


def create_data_node_copy(
    original_node: NodeModel,
    model: GraphModel,
    block_id: str,
    copy_counter: int,
) -> NodeModel:
    """创建数据节点的真实副本
    
    Args:
        original_node: 作为复制来源的节点（可能本身就是副本）
        model: 图模型
        block_id: 块ID（如"block_2"）
        copy_counter: 副本计数器
    
    Returns:
        副本节点对象
    """
    # 统一以"根原始节点 ID"作为副本链的来源
    canonical_original_id = _resolve_canonical_original_id(original_node)
    source_node = original_node
    if canonical_original_id and canonical_original_id in model.nodes:
        source_node = model.nodes[canonical_original_id]

    # 生成副本ID
    base_id = canonical_original_id or source_node.id
    copy_id = f"{base_id}_copy_{block_id}_{copy_counter}"

    # 深拷贝节点
    copy_node = replace(
        source_node,
        id=copy_id,
        is_data_node_copy=True,
        original_node_id=canonical_original_id or base_id,
        copy_block_id=block_id,
        inputs=[PortModel(name=port.name, is_input=True) for port in source_node.inputs],
        outputs=[PortModel(name=port.name, is_input=False) for port in source_node.outputs],
        input_constants=dict(source_node.input_constants) if source_node.input_constants else {},
    )

    copy_node._rebuild_port_maps()
    model.nodes[copy_id] = copy_node

    return copy_node


def remove_data_nodes(
    model: GraphModel,
    node_ids: List[str],
    edge_indices: Optional[dict] = None,
) -> None:
    """批量移除纯数据节点及其相关的数据边"""
    if not node_ids:
        return

    nodes_to_remove = [node_id for node_id in node_ids if node_id in model.nodes]
    if not nodes_to_remove:
        return

    data_in_index = (edge_indices or {}).get("data_in_edges_by_dst") if edge_indices else None
    data_out_index = (edge_indices or {}).get("data_out_edges_by_src") if edge_indices else None

    edges_to_purge: List[str] = []

    for node_id in nodes_to_remove:
        if data_in_index is not None:
            for edge in data_in_index.get(node_id, []):
                edges_to_purge.append(edge.id)
        if data_out_index is not None:
            for edge in data_out_index.get(node_id, []):
                edges_to_purge.append(edge.id)
        if data_in_index is None or data_out_index is None:
            for edge in model.edges.values():
                if edge.src_node == node_id or edge.dst_node == node_id:
                    edges_to_purge.append(edge.id)

    for edge_id in set(edges_to_purge):
        edge = model.edges.pop(edge_id, None)
        if edge is None:
            continue
        if data_in_index is not None and edge.dst_node in data_in_index:
            data_in_index[edge.dst_node] = [
                existing for existing in data_in_index[edge.dst_node] if existing.id != edge_id
            ]
        if data_out_index is not None and edge.src_node in data_out_index:
            data_out_index[edge.src_node] = [
                existing for existing in data_out_index[edge.src_node] if existing.id != edge_id
            ]

    for node_id in nodes_to_remove:
        model.nodes.pop(node_id, None)


def collapse_duplicate_data_copies(model: GraphModel) -> int:
    """合并已存在的重复副本节点
    
    选择首个副本作为"规范副本"，将其余副本的所有入/出边指向规范副本，
    移除多余副本节点，并去重可能产生的重复边。

    Returns:
        实际移除的副本节点数量
    """
    from typing import Tuple

    seen: Dict[Tuple[str, str], str] = {}
    duplicates: Dict[Tuple[str, str], List[str]] = {}

    for node in list(model.nodes.values()):
        if not getattr(node, "is_data_node_copy", False):
            continue

        original_id = _resolve_canonical_original_id(node)
        copy_block_id = node.copy_block_id or _infer_copy_block_id_from_node_id(node.id)
        if not original_id or not copy_block_id:
            continue

        key = (original_id, copy_block_id)
        if key in seen:
            duplicates.setdefault(key, []).append(node.id)
        else:
            seen[key] = node.id

    removed: List[str] = []
    for key, duplicate_ids in duplicates.items():
        canonical_id = seen.get(key)
        if not canonical_id or canonical_id not in model.nodes:
            continue
        for duplicate_id in duplicate_ids:
            if duplicate_id == canonical_id or duplicate_id not in model.nodes:
                continue
            _redirect_edges_to_canonical(model, duplicate_id, canonical_id)
            removed.append(duplicate_id)

    if not removed:
        return 0

    for node_id in removed:
        model.nodes.pop(node_id, None)

    _dedupe_edges(model)
    _prune_basic_blocks(model)

    return len(removed)


def _redirect_edges_to_canonical(model: GraphModel, source_id: str, canonical_id: str) -> None:
    """将指向 source_id 的边重定向到 canonical_id"""
    for edge in model.edges.values():
        if edge.src_node == source_id:
            edge.src_node = canonical_id
        if edge.dst_node == source_id:
            edge.dst_node = canonical_id


def _dedupe_edges(model: GraphModel, edge_indices: Optional[dict] = None) -> None:
    """去除重复边"""
    from typing import Tuple
    from engine.graph.models import EdgeModel
    
    seen_edges: Dict[Tuple[str, str, str, str], str] = {}
    for edge_id in list(model.edges.keys()):
        edge = model.edges[edge_id]
        key = (edge.src_node, edge.src_port, edge.dst_node, edge.dst_port)
        if key in seen_edges:
            del model.edges[edge_id]
        else:
            seen_edges[key] = edge_id

    if edge_indices:
        data_in_index = edge_indices.get("data_in_edges_by_dst") or {}
        data_out_index = edge_indices.get("data_out_edges_by_src") or {}

        def _filter_edges(edge_list: List) -> List:
            filtered: List = []
            seen_ids: set = set()
            for item in edge_list:
                if item.id in seen_ids:
                    continue
                if item.id not in model.edges:
                    continue
                seen_ids.add(item.id)
                filtered.append(item)
            return filtered

        for dst_id, edges in list(data_in_index.items()):
            data_in_index[dst_id] = _filter_edges(edges)
        for src_id, edges in list(data_out_index.items()):
            data_out_index[src_id] = _filter_edges(edges)


def _prune_basic_blocks(model: GraphModel) -> None:
    """清理基本块中的无效节点引用"""
    if not model.basic_blocks:
        return
    existing_ids = set(model.nodes.keys())
    for block in model.basic_blocks:
        block.nodes = [node_id for node_id in block.nodes if node_id in existing_ids]


def _strip_copy_suffix(node_id: str) -> str:
    """去除节点ID中的副本后缀"""
    if not node_id:
        return ""
    marker = "_copy_"
    idx = node_id.find(marker)
    return node_id[:idx] if idx != -1 else node_id


def _infer_copy_block_id_from_node_id(node_id: str) -> str:
    """从节点ID推断副本所属块ID"""
    if not node_id:
        return ""
    marker = "_copy_"
    if marker not in node_id:
        return ""
    suffix = node_id.rsplit(marker, 1)[-1]
    parts = suffix.split("_")
    if len(parts) >= 2 and parts[0] == "block" and parts[1].isdigit():
        return f"block_{parts[1]}"
    return ""
