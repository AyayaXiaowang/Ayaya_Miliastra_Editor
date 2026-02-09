from __future__ import annotations

from typing import Dict, List, Set, Tuple

from engine.graph.models import EdgeModel, GraphModel

from .ids import (
    LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX,
    LOCAL_VAR_RELAY_EDGE_ID_MARKER,
    is_local_var_relay_node_id,
)


def _restore_original_edges_and_remove_existing_relays(
    *,
    model: GraphModel,
    local_var_input_port_name: str,
) -> Tuple[Set[str], bool]:
    """
    方案B（清理→重建）的“清理阶段”：
    - 将既有 relay 结构（relay 节点 + relay 链边 + 被改写的 *_localvar_relay_* 边）从 model 中移除；
    - 并尽可能从 relay 边中恢复被替换掉的“原始长边”，使后续插入逻辑始终基于干净输入运行。

    重要：该逻辑不依赖 node_registry，仅基于“确定性 ID 约定 + 端口名约定”工作。

    Returns:
        stale_relay_node_ids: 被清理掉的 relay node_id 集合（用于从 GlobalCopyManager 的归属中剔除）
        did_mutate: 是否对 model 产生了结构性修改
    """
    stale_relay_node_ids: Set[str] = set()
    for node_id in list(model.nodes.keys()):
        if is_local_var_relay_node_id(node_id):
            stale_relay_node_ids.add(str(node_id))

    if not stale_relay_node_ids:
        return set(), False

    did_mutate = False

    # 同步清理类型覆盖：relay 节点属于布局结构增强基础设施，
    # 若上次排版写入了 port_type_overrides，则必须在重建前剔除旧节点的覆盖项，避免残留污染后续推断。
    meta = getattr(model, "metadata", None) or {}
    if isinstance(meta, dict):
        overrides_raw = meta.get("port_type_overrides")
        if isinstance(overrides_raw, dict):
            overrides = dict(overrides_raw)
            removed_any = False
            for relay_node_id in stale_relay_node_ids:
                if relay_node_id in overrides:
                    overrides.pop(relay_node_id, None)
                    removed_any = True
            if removed_any:
                meta["port_type_overrides"] = overrides
                model.metadata = meta
                did_mutate = True

    # 入边索引：用于从 relay 节点追溯到原始源节点
    in_edges_by_dst: Dict[str, List[EdgeModel]] = {}
    for edge in list(model.edges.values()):
        in_edges_by_dst.setdefault(str(edge.dst_node), []).append(edge)

    def _trace_upstream_source_from_relay(relay_node_id: str) -> Tuple[str, str]:
        """
        从某个 relay 节点向上游追溯，找到第一个非 relay 的源节点与其输出端口名。

        Returns:
            (src_node_id, src_port_name)；若无法追溯则返回 ("", "")
        """
        cursor = str(relay_node_id or "")
        last_src_port = ""
        visited: Set[str] = set()
        while cursor and is_local_var_relay_node_id(cursor) and cursor not in visited:
            visited.add(cursor)
            incoming_edges = [
                e
                for e in (in_edges_by_dst.get(cursor, []) or [])
                if str(getattr(e, "dst_port", "") or "") == str(local_var_input_port_name)
            ]
            if not incoming_edges:
                return "", ""
            incoming_edges.sort(key=lambda e: str(getattr(e, "id", "") or ""))
            chosen = incoming_edges[0]
            last_src_port = str(getattr(chosen, "src_port", "") or "")
            cursor = str(getattr(chosen, "src_node", "") or "")
        if cursor and (not is_local_var_relay_node_id(cursor)) and last_src_port:
            return cursor, last_src_port
        return "", ""

    # 1) 恢复被替换掉的原始长边：扫描 `*_localvar_relay_*` 的“最终段”（dst 非 relay）
    # 说明：
    # - within-block/pure-data 共享链：只有最后一段使用 `_localvar_relay_`；
    # - cross-block 链：每一段都使用 `_localvar_relay_`，但最终段同样满足 dst 非 relay。
    final_segment_by_original_edge_id: Dict[str, EdgeModel] = {}
    for edge in list(model.edges.values()):
        edge_id_text = str(getattr(edge, "id", "") or "")
        if LOCAL_VAR_RELAY_EDGE_ID_MARKER not in edge_id_text:
            continue
        # 仅处理“确实与 relay 有关”的边，避免误伤其它命名
        if (str(edge.src_node) not in stale_relay_node_ids) and (str(edge.dst_node) not in stale_relay_node_ids):
            continue

        marker_index = edge_id_text.find(LOCAL_VAR_RELAY_EDGE_ID_MARKER)
        if marker_index <= 0:
            continue
        original_edge_id = edge_id_text[:marker_index]
        # 防御：二次错误改写可能把 chain edge 当“original_edge_id”，这种不应恢复
        if original_edge_id.startswith(LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX):
            continue
        # 仅“最终段”用于恢复原边
        if is_local_var_relay_node_id(str(edge.dst_node)):
            continue
        if original_edge_id not in final_segment_by_original_edge_id:
            final_segment_by_original_edge_id[original_edge_id] = edge
            continue
        existing = final_segment_by_original_edge_id[original_edge_id]
        if edge_id_text < str(getattr(existing, "id", "") or ""):
            final_segment_by_original_edge_id[original_edge_id] = edge

    # 预收集“非 relay 的 获取自身实体”候选（用于无法追溯链路的 self-entity relay 恢复）
    self_entity_candidates: List[str] = sorted(
        [
            str(node.id)
            for node in model.nodes.values()
            if (not is_local_var_relay_node_id(str(node.id)))
            and (str(getattr(node, "category", "") or "") == "查询节点")
            and (str(getattr(node, "title", "") or "") == "获取自身实体")
        ]
    )

    for original_edge_id, final_edge in final_segment_by_original_edge_id.items():
        dst_node_id = str(getattr(final_edge, "dst_node", "") or "")
        dst_port_name = str(getattr(final_edge, "dst_port", "") or "")
        if not dst_node_id or not dst_port_name:
            continue

        src_node_id = str(getattr(final_edge, "src_node", "") or "")
        src_port_name = str(getattr(final_edge, "src_port", "") or "")

        if is_local_var_relay_node_id(src_node_id):
            traced_src_node, traced_src_port = _trace_upstream_source_from_relay(src_node_id)
            if traced_src_node and traced_src_port:
                src_node_id = traced_src_node
                src_port_name = traced_src_port
            else:
                # 特例：self_entity relay（复制【获取自身实体】节点）没有入边；此时回退到任一非 relay 的 获取自身实体
                relay_node_obj = model.nodes.get(src_node_id)
                if relay_node_obj is not None and str(getattr(relay_node_obj, "title", "") or "") == "获取自身实体":
                    if self_entity_candidates:
                        src_node_id = self_entity_candidates[0]
                        # self_entity relay 的 final_edge.src_port 仍然是原始输出端口名
                    else:
                        continue
                else:
                    continue

        if not src_node_id or not src_port_name:
            continue
        if is_local_var_relay_node_id(src_node_id) or is_local_var_relay_node_id(dst_node_id):
            continue

        model.edges[str(original_edge_id)] = EdgeModel(
            id=str(original_edge_id),
            src_node=str(src_node_id),
            src_port=str(src_port_name),
            dst_node=str(dst_node_id),
            dst_port=str(dst_port_name),
        )
        did_mutate = True

    # 2) 移除 relay 边（以及任何与 relay 节点相连的边）
    edge_ids_to_remove: List[str] = []
    for edge_id, edge in list(model.edges.items()):
        edge_id_text = str(edge_id)
        if edge_id_text.startswith(LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX):
            edge_ids_to_remove.append(edge_id_text)
            continue
        if LOCAL_VAR_RELAY_EDGE_ID_MARKER in edge_id_text:
            edge_ids_to_remove.append(edge_id_text)
            continue
        if str(getattr(edge, "src_node", "") or "") in stale_relay_node_ids:
            edge_ids_to_remove.append(edge_id_text)
            continue
        if str(getattr(edge, "dst_node", "") or "") in stale_relay_node_ids:
            edge_ids_to_remove.append(edge_id_text)
            continue

    for edge_id in edge_ids_to_remove:
        if edge_id in model.edges:
            model.edges.pop(edge_id, None)
            did_mutate = True

    # 3) 移除 relay 节点
    for relay_node_id in stale_relay_node_ids:
        if relay_node_id in model.nodes:
            model.nodes.pop(relay_node_id, None)
            did_mutate = True

    return set(stale_relay_node_ids), bool(did_mutate)


__all__ = ["_restore_original_edges_and_remove_existing_relays"]



