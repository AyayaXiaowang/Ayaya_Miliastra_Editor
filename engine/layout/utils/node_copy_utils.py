"""
数据节点复制工具

为跨块共享的数据节点创建真实副本。
"""

from __future__ import annotations
from typing import Optional, List, Tuple, Dict
from dataclasses import replace

from engine.graph.models import GraphModel, NodeModel, PortModel


def create_data_node_copy(
    original_node: NodeModel,
    model: GraphModel,
    block_id: str,
    copy_counter: int,
) -> NodeModel:
    """
    创建数据节点的真实副本
    
    Args:
        original_node: 原始节点
        model: 图模型
        block_id: 块ID（如"block_2"）
        copy_counter: 副本计数器（同一节点在不同块的副本序号）
    
    Returns:
        副本节点对象
    """
    # 生成副本ID
    copy_id = f"{original_node.id}_copy_{block_id}_{copy_counter}"

    # 深拷贝节点
    copy_node = replace(
        original_node,
        id=copy_id,
        is_data_node_copy=True,
        original_node_id=original_node.id,
        copy_block_id=block_id,
        # 深拷贝端口列表
        inputs=[PortModel(name=port.name, is_input=True) for port in original_node.inputs],
        outputs=[PortModel(name=port.name, is_input=False) for port in original_node.outputs],
        # 深拷贝常量
        input_constants=dict(original_node.input_constants) if original_node.input_constants else {},
    )

    # 重建端口映射
    copy_node._rebuild_port_maps()

    # 添加到模型
    model.nodes[copy_id] = copy_node

    return copy_node


def redirect_edges_to_copy(
    model: GraphModel,
    original_id: str,
    copy_id: str,
    current_block_flow_ids: set,
    current_block_data_ids: set,
    edge_indices: dict = None,  # 边索引，用于更新
    block_id: str = None,  # 当前块ID（直接传参，避免字符串解析）
    copy_map: dict = None,  # 原始ID→副本ID的映射（避免全节点扫描）
) -> None:
    """
    将当前块内指向原始节点的边重定向到副本
    
    策略：
    1. 重定向当前块内指向原始节点的输入边到副本
    2. 将原始节点连接到当前块的输出边改为从副本发出
    3. 删除原始节点到当前块的输出边（避免重复连接）
    
    Args:
        model: 图模型
        original_id: 原始节点ID
        copy_id: 副本节点ID
        current_block_flow_ids: 当前块的流程节点ID集合
        current_block_data_ids: 当前块已放置的数据节点ID集合
        edge_indices: 边索引字典（可选），包含data_in_edges_by_dst和data_out_edges_by_src
        block_id: 当前块ID（如"block_5"）（避免字符串解析）
        copy_map: 原始ID→副本ID的映射（避免全节点扫描查找副本）
    """
    # 使用传入的块ID（避免字符串解析）
    current_block_id = block_id

    # 如果未传入块ID，回退到字符串解析（兼容性）
    if current_block_id is None and "_copy_" in copy_id:
        parts = copy_id.split("_copy_")
        if len(parts) == 2:
            block_parts = parts[1].split("_")
            if len(block_parts) >= 2 and block_parts[0] == "block":
                current_block_id = f"block_{block_parts[1]}"

    # 辅助函数：检查节点是否属于当前块
    def is_node_in_current_block(node_id: str) -> bool:
        """检查节点是否在当前块内（包括原始节点和副本节点）"""
        # 直接在流程或数据节点集合中
        if node_id in current_block_flow_ids or node_id in current_block_data_ids:
            return True

        # 检查是否是当前块的副本节点（使用副本映射快速查询）
        if copy_map and node_id in copy_map.values():
            node = model.nodes.get(node_id)
            if node and getattr(node, "copy_block_id", None) == current_block_id:
                return True

        return False

    edges_to_redirect = []
    edges_to_replace = []  # 原始节点→当前块的边，需要替换为 副本→当前块
    edges_to_create = []  # 需要创建的新边（当源和/或目标在当前块存在副本时）

    # 辅助函数：查找节点在当前块的副本ID（优化：使用副本映射）
    def find_copy_in_current_block(node_id: str) -> Optional[str]:
        """查找节点在当前块的副本ID"""
        if node_id == copy_id:
            return copy_id

        # 使用副本映射快速查找（O(1)）
        if copy_map and node_id in copy_map:
            candidate_copy_id = copy_map[node_id]
            # 验证副本是否属于当前块
            node = model.nodes.get(candidate_copy_id)
            if node and getattr(node, "copy_block_id", None) == current_block_id:
                return candidate_copy_id

        return None

    # 优化：只遍历相关边的索引，避免O(E)全表扫描

    # 处理指向原始节点的输入边
    if edge_indices and "data_in_edges_by_dst" in edge_indices:
        input_edges = edge_indices["data_in_edges_by_dst"].get(original_id, [])
    else:
        # 回退：从全图扫描（兼容性）
        input_edges = [edge for edge in model.edges.values() if edge.dst_node == original_id]

    for edge in input_edges:
        # 检查源节点是否在当前块内（原始节点或副本）
        src_copy_id = find_copy_in_current_block(edge.src_node)

        if src_copy_id:
            # 源节点在当前块（可能是副本）
            if src_copy_id == edge.src_node:
                # 源是原始节点或已经是副本ID，直接重定向
                edges_to_redirect.append((edge.id, "dst", copy_id, edge))
            else:
                # 源有副本，需要创建新边 源副本→目标副本
                # 注意：不删除旧块内的原始边（原始→原始），避免破坏旧块结构
                edges_to_create.append((edge, src_copy_id, copy_id))
        elif is_node_in_current_block(edge.src_node) or edge.src_node == copy_id:
            # 源在当前块但不是需要复制的节点（例如流程节点）
            edges_to_redirect.append((edge.id, "dst", copy_id, edge))

    # 处理从原始节点发出的输出边
    if edge_indices and "data_out_edges_by_src" in edge_indices:
        output_edges = edge_indices["data_out_edges_by_src"].get(original_id, [])
    else:
        # 回退：从全图扫描（兼容性）
        output_edges = [edge for edge in model.edges.values() if edge.src_node == original_id]

    for edge in output_edges:
        # 若目标在当前块存在副本，则创建 副本→目标副本 的新边（不删除原始跨块边）
        dst_copy_id = find_copy_in_current_block(edge.dst_node)
        if dst_copy_id:
            # 源与目标在当前块均有副本：新增 副本→副本
            # 注意：不删除旧块内的原始边（原始→原始），避免破坏旧块结构
            edges_to_create.append((edge, copy_id, dst_copy_id))
        elif is_node_in_current_block(edge.dst_node) or edge.dst_node == copy_id:
            # 这条边属于当前块，需要替换为从副本发出
            edges_to_replace.append((edge.id, edge))

    # 执行重定向（修改目标为副本）
    for edge_id, direction, new_id, original_edge in edges_to_redirect:
        edge = model.edges.get(edge_id)
        if edge is None:
            # 边可能已在前序步骤中被删除或合并，跳过以保持幂等
            continue
        if direction == "dst":
            # 从原始节点的输入边列表中移除
            if edge_indices and "data_in_edges_by_dst" in edge_indices:
                data_in_index = edge_indices["data_in_edges_by_dst"]
                if original_id in data_in_index and edge in data_in_index[original_id]:
                    data_in_index[original_id].remove(edge)

            # 修改边
            edge.dst_node = new_id

            # 添加到副本的输入边列表
            if edge_indices and "data_in_edges_by_dst" in edge_indices:
                data_in_index = edge_indices["data_in_edges_by_dst"]
                data_in_index.setdefault(new_id, []).append(edge)

    # 替换边（删除原始边，创建从副本发出的新边）
    from engine.graph.models import EdgeModel
    import uuid
    from engine.utils.graph.graph_utils import is_flow_port_name

    for original_edge_id, original_edge in edges_to_replace:
        # 从原始节点的输出边列表中移除原始边
        if edge_indices and "data_out_edges_by_src" in edge_indices:
            data_out_index = edge_indices["data_out_edges_by_src"]
            if original_id in data_out_index and original_edge in data_out_index[original_id]:
                data_out_index[original_id].remove(original_edge)

        # 从目标节点的输入边列表中移除原始边
        if edge_indices and "data_in_edges_by_dst" in edge_indices:
            data_in_index = edge_indices["data_in_edges_by_dst"]
            if original_edge.dst_node in data_in_index and original_edge in data_in_index[original_edge.dst_node]:
                data_in_index[original_edge.dst_node].remove(original_edge)

        # 删除原始边；若边已不存在，说明已在前序步骤完成重定向，此处跳过保持幂等
        if original_edge_id not in model.edges:
            continue
        del model.edges[original_edge_id]

        # 创建新边：副本 → 目标
        new_edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        new_edge = EdgeModel(
            id=new_edge_id,
            src_node=copy_id,  # 源改为副本
            src_port=original_edge.src_port,
            dst_node=original_edge.dst_node,  # 目标不变
            dst_port=original_edge.dst_port,
        )
        model.edges[new_edge_id] = new_edge

        # 更新索引：添加到副本的输出边列表
        if edge_indices:
            if "data_out_edges_by_src" in edge_indices:
                data_out_index = edge_indices["data_out_edges_by_src"]
                data_out_index.setdefault(copy_id, []).append(new_edge)

            # 添加到目标的输入边列表
            if "data_in_edges_by_dst" in edge_indices:
                data_in_index = edge_indices["data_in_edges_by_dst"]
                dst_node = model.nodes.get(new_edge.dst_node)
                if dst_node:
                    dst_port = dst_node.get_input_port(new_edge.dst_port)
                    if dst_port and not is_flow_port_name(dst_port.name):
                        # 这是数据边
                        data_in_index.setdefault(new_edge.dst_node, []).append(new_edge)

    # 创建新边（当源和/或目标在当前块存在副本时）
    for original_edge, src_copy_id, dst_copy_id in edges_to_create:
        new_edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        new_edge = EdgeModel(
            id=new_edge_id,
            src_node=src_copy_id,  # 源副本
            src_port=original_edge.src_port,
            dst_node=dst_copy_id,  # 目标副本
            dst_port=original_edge.dst_port,
        )
        model.edges[new_edge_id] = new_edge

        # 更新索引
        if edge_indices:
            if "data_out_edges_by_src" in edge_indices:
                data_out_index = edge_indices["data_out_edges_by_src"]
                data_out_index.setdefault(src_copy_id, []).append(new_edge)

            if "data_in_edges_by_dst" in edge_indices:
                data_in_index = edge_indices["data_in_edges_by_dst"]
                data_in_index.setdefault(dst_copy_id, []).append(new_edge)


def remove_data_nodes(
    model: GraphModel,
    node_ids: List[str],
    edge_indices: Optional[dict] = None,
) -> None:
    """
    批量移除纯数据节点及其相关的数据边，并保持索引同步。
    """
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
    """
    合并已存在的重复副本节点（同一个原始节点在同一块被复制多次）。

    - 选择首个副本作为“规范副本”；
    - 将其余副本的所有入/出边指向规范副本；
    - 移除多余副本节点，并去重可能产生的重复边。

    Returns:
        实际移除的副本节点数量
    """

    seen: Dict[Tuple[str, str], str] = {}
    duplicates: Dict[Tuple[str, str], List[str]] = {}

    for node in list(model.nodes.values()):
        if not getattr(node, "is_data_node_copy", False):
            continue

        original_id = node.original_node_id or _strip_copy_suffix(node.id)
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
    for edge in model.edges.values():
        if edge.src_node == source_id:
            edge.src_node = canonical_id
        if edge.dst_node == source_id:
            edge.dst_node = canonical_id


def _dedupe_edges(model: GraphModel) -> None:
    seen_edges: Dict[Tuple[str, str, str, str], str] = {}
    for edge_id in list(model.edges.keys()):
        edge = model.edges[edge_id]
        key = (edge.src_node, edge.src_port, edge.dst_node, edge.dst_port)
        if key in seen_edges:
            del model.edges[edge_id]
        else:
            seen_edges[key] = edge_id


def _prune_basic_blocks(model: GraphModel) -> None:
    if not model.basic_blocks:
        return
    existing_ids = set(model.nodes.keys())
    for block in model.basic_blocks:
        block.nodes = [node_id for node_id in block.nodes if node_id in existing_ids]


def _strip_copy_suffix(node_id: str) -> str:
    if not node_id:
        return ""
    marker = "_copy_"
    idx = node_id.find(marker)
    return node_id[:idx] if idx != -1 else node_id


def _infer_copy_block_id_from_node_id(node_id: str) -> str:
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



