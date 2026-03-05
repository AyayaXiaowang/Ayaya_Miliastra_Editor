from __future__ import annotations

"""
长连线中转节点插入器（布局增强）。

目标：
- 在“跨块复制（GlobalCopyManager）完成后、块内排版前”扫描长距离数据边；
- 对“同一块内跨越过多流程节点（沿 block.flow_nodes 顺序）”的数据边自动插入【获取局部变量】节点作为中转，
  将长边拆成多段短边（每段不超过阈值）；
- 对“同一块内的纯数据节点（无流程端口，如【以GUID查询实体】）→ 远端消费者”的数据边：
  以“该源端口的最早消费者流程节点位置”为锚点计算跨度，并同样按阈值插入【获取局部变量】中转链，
  让多个远端消费者复用同一条 relay 链，避免一条输出端口插多套 relay。
- 对源节点为【获取自身实体】的长连线：优先通过“复制【获取自身实体】查询节点”作为中继点，
  避免引入不必要的【获取局部变量】中转节点（该节点本身无副作用且可安全重复计算）；
- （兼容）对跨块数据边仍可按块路径跨度拆分。
- 生成的节点参与后续排版与任务清单创建。

约束：
- 仅当节点库中的【获取局部变量】具备“初始值 → 值”的透传端口形态时启用（通常为 server 侧节点定义）。
- 会尝试根据端口类型/泛型约束判断该边是否允许通过局部变量承载；若无法判断或疑似字典类型，则跳过。
- 不使用 try/except 吞错；任何结构不一致问题应直接抛出以暴露建模错误。
"""

from collections import deque
from typing import Dict, Iterable, List, Optional, Set, Tuple, TYPE_CHECKING

from engine.graph.models import EdgeModel, GraphModel, NodeModel, PortModel
from engine.type_registry import (
    TYPE_GENERIC,
    TYPE_GENERIC_DICT,
    TYPE_GENERIC_LIST,
    is_dict_type_name,
    normalize_type_text,
)

from ..graph_query_utils import is_data_edge
from .block_graph import _build_block_children_map, _find_shortest_block_path
from .cleanup import _restore_original_edges_and_remove_existing_relays
from .ids import _build_relay_chain_edge_id, _build_relay_edge_id, _build_relay_node_id, is_local_var_relay_node_id
from .type_checks import _edge_supported_by_local_var_relay, _is_self_entity_query_node

if TYPE_CHECKING:
    from engine.nodes.node_definition_loader import NodeDef
    from engine.nodes.node_registry import NodeRegistry
    from engine.layout.internal.layout_models import LayoutBlock
    from engine.layout.utils.global_copy_manager import GlobalCopyManager


def insert_local_variable_relays_after_global_copy(
    *,
    model: GraphModel,
    layout_blocks: List["LayoutBlock"],
    global_copy_manager: "GlobalCopyManager",
    max_block_distance: int,
    node_registry: Optional["NodeRegistry"],
) -> Tuple[Dict[str, Set[str]], Set[str], bool]:
    """
    在全局复制完成后插入局部变量中转节点。

    Returns:
        forced_relay_nodes_by_block_id:
            block_id -> relay node_ids（这些节点应强制放置在对应 block）
        all_relay_node_ids:
            所有 relay node_id 集合（用于从 GlobalCopyManager 的 block_data_nodes 中剔除）
        did_mutate_model:
            是否对 model 进行了结构修改（新增节点/新增边/移除旧边）
    """
    did_mutate_model = False

    threshold = int(max_block_distance)
    if threshold < 3:
        threshold = 3
    if threshold > 10:
        threshold = 10

    if node_registry is None:
        return {}, set(), False

    local_var_node_def = node_registry.get_node_by_alias("查询节点", "获取局部变量")
    if local_var_node_def is None:
        return {}, set(), False

    self_entity_node_def = node_registry.get_node_by_alias("查询节点", "获取自身实体")

    # 仅支持 server 形态：初始值（输入）+ 值（输出）
    local_var_input_port_name = "初始值"
    local_var_output_port_name = "值"
    if local_var_input_port_name not in (local_var_node_def.inputs or []):
        return {}, set(), False
    if local_var_output_port_name not in (local_var_node_def.outputs or []):
        return {}, set(), False

    # 端口类型覆盖：为 relay 节点写入 `metadata.port_type_overrides`，用于：
    # - UI/工具链展示“值端口的具体类型”（避免长期显示泛型）
    # - 推断/自动化：让 relay 链中间节点的类型可以沿边传播（上游 `值` 端口不再是纯泛型）
    meta = getattr(model, "metadata", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    overrides_raw = meta.get("port_type_overrides")
    overrides: Dict[str, Dict[str, str]] = dict(overrides_raw) if isinstance(overrides_raw, dict) else {}

    allowed_by_local_var = set(local_var_node_def.get_generic_constraints(local_var_input_port_name, is_input=True) or [])

    def _is_generic_family_type(type_name: object) -> bool:
        text = normalize_type_text(type_name)
        return (text == "") or (text in {TYPE_GENERIC, TYPE_GENERIC_LIST, TYPE_GENERIC_DICT})

    def _normalize_concrete_type(type_name: object) -> str:
        text = normalize_type_text(type_name)
        if text == "" or _is_generic_family_type(text):
            return ""
        if is_dict_type_name(text):
            return ""
        if normalize_type_text(text) == TYPE_GENERIC_DICT:
            return ""
        return text

    def _get_override_type_for_port(node_id: str, port_name: str) -> str:
        node_overrides = overrides.get(str(node_id))
        if not isinstance(node_overrides, dict):
            return ""
        raw = node_overrides.get(str(port_name))
        return _normalize_concrete_type(raw)

    def _get_snapshot_type_for_port(node_obj: NodeModel, port_name: str, *, is_input: bool) -> str:
        mapping = getattr(node_obj, "input_types" if is_input else "output_types", {}) or {}
        if not isinstance(mapping, dict):
            return ""
        raw = mapping.get(str(port_name), "")
        return _normalize_concrete_type(raw)

    def _get_concrete_port_type_for_node_port(
        node_obj: NodeModel,
        node_def: "NodeDef",
        port_name: str,
        *,
        is_input: bool,
    ) -> str:
        # 1) 节点快照（GraphLoader/缓存可能已补齐）
        snap = _get_snapshot_type_for_port(node_obj, port_name, is_input=is_input)
        if snap:
            return snap
        # 2) overrides（Graph Code 注解或布局增强写入）
        override_type = _get_override_type_for_port(str(getattr(node_obj, "id", "") or ""), port_name)
        if override_type:
            return override_type
        # 3) 节点定义的显式类型（非泛型）
        type_dict = node_def.input_types if is_input else node_def.output_types
        raw = type_dict.get(str(port_name))
        concrete = _normalize_concrete_type(raw)
        return concrete

    def _infer_edge_candidate_types_for_relay(edge: EdgeModel) -> Set[str]:
        src_node = model.nodes.get(edge.src_node)
        dst_node = model.nodes.get(edge.dst_node)
        if src_node is None or dst_node is None:
            return set()

        src_def = node_registry.get_node_by_alias(str(getattr(src_node, "category", "") or ""), str(getattr(src_node, "title", "") or ""))
        dst_def = node_registry.get_node_by_alias(str(getattr(dst_node, "category", "") or ""), str(getattr(dst_node, "title", "") or ""))
        if src_def is None or dst_def is None:
            return set()

        src_type = _get_concrete_port_type_for_node_port(src_node, src_def, str(edge.src_port), is_input=False)
        dst_type = _get_concrete_port_type_for_node_port(dst_node, dst_def, str(edge.dst_port), is_input=True)

        # 明确字典：直接跳过（局部变量禁止字典类型）
        if is_dict_type_name(src_type) or is_dict_type_name(dst_type):
            return set()

        src_candidates: Set[str] = set()
        dst_candidates: Set[str] = set()
        if src_type:
            src_candidates.add(str(src_type))
        else:
            src_candidates.update(src_def.get_generic_constraints(str(edge.src_port), is_input=False))
        if dst_type:
            dst_candidates.add(str(dst_type))
        else:
            dst_candidates.update(dst_def.get_generic_constraints(str(edge.dst_port), is_input=True))

        if src_candidates and dst_candidates:
            candidates = set(src_candidates & dst_candidates)
        else:
            candidates = set(src_candidates or dst_candidates)

        # 过滤：必须属于局部变量允许集合
        if allowed_by_local_var:
            candidates = {t for t in candidates if t in allowed_by_local_var}
        # 再次防御：剔除字典/泛型家族
        candidates = {t for t in candidates if _normalize_concrete_type(t)}
        return candidates

    def _choose_relay_value_type_for_group(
        *,
        src_node_id: str,
        src_port_name: str,
        edges: List[EdgeModel],
    ) -> str:
        src_node = model.nodes.get(str(src_node_id))
        if src_node is None:
            return ""
        src_def = node_registry.get_node_by_alias(str(getattr(src_node, "category", "") or ""), str(getattr(src_node, "title", "") or ""))
        if src_def is not None:
            src_concrete = _get_concrete_port_type_for_node_port(src_node, src_def, str(src_port_name), is_input=False)
            if src_concrete:
                # 确保对所有目标端口均可接受
                ok_for_all = True
                for e in list(edges or []):
                    cand = _infer_edge_candidate_types_for_relay(e)
                    if cand and str(src_concrete) not in cand:
                        ok_for_all = False
                        break
                if ok_for_all:
                    return str(src_concrete)

        intersection: Optional[Set[str]] = None
        for e in list(edges or []):
            cand = _infer_edge_candidate_types_for_relay(e)
            if not cand:
                continue
            if intersection is None:
                intersection = set(cand)
            else:
                intersection &= set(cand)
        if intersection and len(intersection) == 1:
            return sorted(list(intersection))[0]
        return ""

    def _set_relay_output_type_overrides(relay_node_ids: Iterable[str], value_type: str) -> bool:
        """为 relay 节点写入 output 端口 `值` 的具体类型覆盖。

        返回：是否修改了 overrides。
        """
        value_text = _normalize_concrete_type(value_type)
        if not value_text:
            return False
        if allowed_by_local_var and value_text not in allowed_by_local_var:
            return False
        changed = False
        for relay_node_id in list(relay_node_ids or []):
            rid = str(relay_node_id or "")
            if not rid:
                continue
            node_overrides = overrides.get(rid)
            mapping = dict(node_overrides) if isinstance(node_overrides, dict) else {}
            if mapping.get(local_var_output_port_name) != value_text:
                mapping[local_var_output_port_name] = value_text
                overrides[rid] = mapping
                changed = True
        if changed:
            meta["port_type_overrides"] = overrides
            model.metadata = meta
        return changed

    # 0) 方案B：若图中已存在 relay 结构（来自上一次自动排版），先“还原并清理”，
    #    让后续插入逻辑始终基于干净输入运行，避免累积改写导致结构漂移。
    stale_relay_node_ids, did_clean = _restore_original_edges_and_remove_existing_relays(
        model=model,
        local_var_input_port_name=local_var_input_port_name,
    )
    if did_clean:
        did_mutate_model = True

    # 1) 记录 relay node_id（用于从 GlobalCopyManager 的 block_data_nodes 中剔除）
    # 注意：必须包含“本轮清理掉的 relay 节点”，否则 GlobalCopyManager 的归属快照仍可能引用它们。
    forced_relay_nodes_by_block_id: Dict[str, Set[str]] = {}
    all_relay_node_ids: Set[str] = set(stale_relay_node_ids)

    # 2) 构建块关系与节点归属映射（用于计算“跨块跨度 / 块内节点跨度”）
    children_by_block_id = _build_block_children_map(model=model, layout_blocks=layout_blocks)
    block_ids_in_layout = sorted(children_by_block_id.keys())

    node_to_block_id: Dict[str, str] = {}
    flow_order_index_by_flow_node_id: Dict[str, int] = {}
    for layout_block in layout_blocks:
        block_id = f"block_{int(getattr(layout_block, 'order_index', 0) or 0)}"
        flow_nodes = list(getattr(layout_block, "flow_nodes", None) or [])
        for index, flow_node_id in enumerate(flow_nodes):
            flow_node_id_text = str(flow_node_id)
            node_to_block_id[flow_node_id_text] = block_id
            flow_order_index_by_flow_node_id[flow_node_id_text] = int(index)

    for block_id in block_ids_in_layout:
        for data_node_id in sorted(list(global_copy_manager.get_block_data_nodes(block_id) or set())):
            node_to_block_id.setdefault(str(data_node_id), str(block_id))

    # 3) 遍历数据边，识别长跨度并插入 relay
    existing_node_ids = set(model.nodes.keys())
    edges_snapshot: List[EdgeModel] = list(model.edges.values())
    path_cache: Dict[Tuple[str, str], List[str]] = {}
    data_out_edges_by_src_node_id: Dict[str, List[EdgeModel]] = {}
    for edge in edges_snapshot:
        if not is_data_edge(model, edge):
            continue
        data_out_edges_by_src_node_id.setdefault(str(edge.src_node), []).append(edge)

    downstream_min_flow_index_cache: Dict[Tuple[str, str], Optional[int]] = {}

    def infer_min_downstream_flow_index_for_data_node(*, block_id: str, data_node_id: str) -> Optional[int]:
        cache_key = (str(block_id), str(data_node_id))
        cached = downstream_min_flow_index_cache.get(cache_key)
        if cached is not None:
            return cached

        visited_node_ids: Set[str] = set()
        queue: deque[str] = deque([str(data_node_id)])
        min_flow_index: Optional[int] = None

        while queue:
            current_node_id = str(queue.popleft())
            if current_node_id in visited_node_ids:
                continue
            visited_node_ids.add(current_node_id)

            flow_index = flow_order_index_by_flow_node_id.get(current_node_id)
            if flow_index is not None:
                if min_flow_index is None or int(flow_index) < int(min_flow_index):
                    min_flow_index = int(flow_index)
                # 流程节点不再向下游展开
                continue

            for out_edge in data_out_edges_by_src_node_id.get(current_node_id, []) or []:
                next_node_id = str(out_edge.dst_node)
                if node_to_block_id.get(next_node_id, "") != str(block_id):
                    continue
                queue.append(next_node_id)

        downstream_min_flow_index_cache[cache_key] = min_flow_index
        return min_flow_index

    # 3A) 先收集块内需要拆分的长连线（按“源节点+源端口”分组共享 relay 链）
    # key: (block_id, src_node_id, src_port_name)
    within_block_groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    # 3A1) 同块内“纯数据节点（无流程端口）作为源”的长连线：按“最早消费者流程节点位置”为锚点拆分。
    # key: (block_id, src_node_id, src_port_name)
    pure_data_source_groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    # 3A2) 特例：源节点为【获取自身实体】的数据节点 → 流程节点 的长连线（同块内）
    # key: (block_id, src_node_id, src_port_name)
    self_entity_groups: Dict[Tuple[str, str, str], Dict[str, object]] = {}
    cross_block_edges: List[EdgeModel] = []

    for edge in edges_snapshot:
        if not is_data_edge(model, edge):
            continue

        # 已插入的 relay 节点属于“结构增强基础设施”，其入边不应再次被判定为长边并重复拆分：
        # 否则二次运行会把 `src -> relay.初始值` 这条链边当作“远端消费者边”重写，
        # 进而产生 `relay -> relay` 自环并破坏幂等性，导致自动排版多次后 relay 飞走。
        dst_node_id_text = str(getattr(edge, "dst_node", "") or "")
        if is_local_var_relay_node_id(dst_node_id_text):
            continue

        src_block_id = node_to_block_id.get(str(edge.src_node), "")
        dst_block_id = node_to_block_id.get(dst_node_id_text, "")
        if not src_block_id or not dst_block_id:
            continue

        if src_block_id != dst_block_id:
            cross_block_edges.append(edge)
            continue

        src_flow_index = flow_order_index_by_flow_node_id.get(str(edge.src_node))
        dst_flow_index = flow_order_index_by_flow_node_id.get(dst_node_id_text)
        if dst_flow_index is None:
            # 目标为数据节点（如【拼装列表】）时，尝试推断其下游最早的流程消费者位置。
            inferred = infer_min_downstream_flow_index_for_data_node(
                block_id=str(dst_block_id),
                data_node_id=dst_node_id_text,
            )
            if inferred is None:
                continue
            dst_flow_index = int(inferred)

        # 特例：获取自身实体（纯数据节点）不在 flow_nodes 中，因此 src_flow_index 为 None。
        # 这里按“消费者流程节点跨度”触发中继点插入。
        if src_flow_index is None:
            src_node_id_text = str(edge.src_node)
            if is_local_var_relay_node_id(src_node_id_text):
                continue
            src_node = model.nodes.get(src_node_id_text)
            if src_node is None:
                continue

            # 纯数据源：优先处理“获取自身实体”的特殊中继点策略；其它纯数据源走局部变量 relay。
            if _is_self_entity_query_node(src_node):
                group_key = (src_block_id, src_node_id_text, str(edge.src_port))
                group = self_entity_groups.setdefault(
                    group_key,
                    {
                        "min_dst_flow_index": int(dst_flow_index),
                        "edges": [],
                    },
                )
                min_dst_flow_index_raw = group.get("min_dst_flow_index")
                assert isinstance(min_dst_flow_index_raw, int)
                if int(dst_flow_index) < int(min_dst_flow_index_raw):
                    group["min_dst_flow_index"] = int(dst_flow_index)
                edges_list = group.get("edges")
                assert isinstance(edges_list, list)
                edges_list.append(
                    {
                        "edge": edge,
                        "dst_flow_index": int(dst_flow_index),
                    }
                )
                continue

            # 其它纯数据节点作为源：按“最早消费者流程节点位置”作为锚点计算跨度。
            # 仅当该边类型允许通过【获取局部变量】承载时才参与拆分。
            if not _edge_supported_by_local_var_relay(
                edge=edge,
                model=model,
                node_registry=node_registry,
                local_var_node_def=local_var_node_def,
                local_var_input_port_name=local_var_input_port_name,
            ):
                continue

            group_key = (src_block_id, src_node_id_text, str(edge.src_port))
            group = pure_data_source_groups.setdefault(
                group_key,
                {
                    "anchor_flow_index": int(dst_flow_index),
                    "edges": [],
                },
            )
            anchor_raw = group.get("anchor_flow_index")
            assert isinstance(anchor_raw, int)
            if int(dst_flow_index) < int(anchor_raw):
                group["anchor_flow_index"] = int(dst_flow_index)
            edges_list = group.get("edges")
            assert isinstance(edges_list, list)
            edges_list.append(
                {
                    "edge": edge,
                    "dst_flow_index": int(dst_flow_index),
                }
            )
            continue

        if dst_flow_index <= src_flow_index:
            continue

        node_distance = int(dst_flow_index) - int(src_flow_index)
        if node_distance <= threshold:
            continue

        if not _edge_supported_by_local_var_relay(
            edge=edge,
            model=model,
            node_registry=node_registry,
            local_var_node_def=local_var_node_def,
            local_var_input_port_name=local_var_input_port_name,
        ):
            continue

        group_key = (src_block_id, str(edge.src_node), str(edge.src_port))
        group = within_block_groups.setdefault(
            group_key,
            {
                "src_flow_index": int(src_flow_index),
                "edges": [],
            },
        )
        edges_list = group.get("edges")
        assert isinstance(edges_list, list)
        edges_list.append(
            {
                "edge": edge,
                "dst_flow_index": int(dst_flow_index),
                "node_distance": int(node_distance),
            }
        )

    # 3B) 执行块内共享 relay 链插入：
    # - 同一源端口只生成一条 relay 链；
    # - 多个消费者边从“离自己最近的 relay 输出”分叉出去；
    # - 共享链上的前置边不会重复生成（避免 Z/X/Y 各插一套）。
    for (block_id, src_node_id, src_port_name), group in within_block_groups.items():
        src_flow_index_raw = group.get("src_flow_index")
        edges_info_raw = group.get("edges")
        assert isinstance(src_flow_index_raw, int)
        assert isinstance(edges_info_raw, list)
        if not edges_info_raw:
            continue

        max_distance = max(int(item.get("node_distance", 0) or 0) for item in edges_info_raw if isinstance(item, dict))
        relay_steps = [step for step in range(threshold, int(max_distance), threshold)]
        if not relay_steps:
            continue

        chain_key = f"{block_id}:{src_node_id}:{src_port_name}"
        relay_node_id_by_slot: Dict[int, str] = {}

        for relay_index, step in enumerate(relay_steps, start=1):
            forced_slot_index = int(src_flow_index_raw) + int(step)
            relay_node_id = _build_relay_node_id(
                original_edge_key=chain_key,
                relay_index=relay_index,
                target_block_id=block_id,
                target_slot_index=forced_slot_index,
            )
            relay_node_id_by_slot[int(forced_slot_index)] = relay_node_id

            if relay_node_id not in existing_node_ids:
                from engine.graph.models import NodeDefRef
                from engine.nodes import get_canonical_node_def_key

                relay_node = NodeModel(
                    id=relay_node_id,
                    title=str(local_var_node_def.name),
                    category=str(local_var_node_def.category),
                    node_def_ref=NodeDefRef(kind="builtin", key=get_canonical_node_def_key(local_var_node_def)),
                    inputs=[
                        PortModel(name=str(port_name), is_input=True)
                        for port_name in (local_var_node_def.inputs or [])
                    ],
                    outputs=[
                        PortModel(name=str(port_name), is_input=False)
                        for port_name in (local_var_node_def.outputs or [])
                    ],
                )
                relay_node._rebuild_port_maps()
                model.nodes[relay_node_id] = relay_node
                existing_node_ids.add(relay_node_id)
                did_mutate_model = True

            forced_relay_nodes_by_block_id.setdefault(block_id, set()).add(relay_node_id)
            all_relay_node_ids.add(relay_node_id)

        # 为 relay 节点写入“值输出端口”的类型覆盖（用于中间链路类型传播与 UI 展示）
        group_edges: List[EdgeModel] = []
        for item in edges_info_raw:
            if not isinstance(item, dict):
                continue
            e = item.get("edge")
            if isinstance(e, EdgeModel):
                group_edges.append(e)
        relay_value_type = _choose_relay_value_type_for_group(
            src_node_id=str(src_node_id),
            src_port_name=str(src_port_name),
            edges=group_edges,
        )
        if _set_relay_output_type_overrides(relay_node_id_by_slot.values(), relay_value_type):
            did_mutate_model = True

        # 共享链边：src -> relay1 -> relay2 -> ...
        previous_src_node_id = str(src_node_id)
        previous_src_port_name = str(src_port_name)
        link_index = 1

        for slot_index in sorted(relay_node_id_by_slot.keys()):
            relay_node_id = relay_node_id_by_slot[int(slot_index)]
            edge_to_relay_id = _build_relay_chain_edge_id(chain_key=chain_key, link_index=link_index)
            link_index += 1

            existing_edge = model.edges.get(edge_to_relay_id)
            if (
                existing_edge is None
                or str(getattr(existing_edge, "src_node", "")) != str(previous_src_node_id)
                or str(getattr(existing_edge, "src_port", "")) != str(previous_src_port_name)
                or str(getattr(existing_edge, "dst_node", "")) != str(relay_node_id)
                or str(getattr(existing_edge, "dst_port", "")) != str(local_var_input_port_name)
            ):
                model.edges[edge_to_relay_id] = EdgeModel(
                    id=edge_to_relay_id,
                    src_node=previous_src_node_id,
                    src_port=previous_src_port_name,
                    dst_node=relay_node_id,
                    dst_port=local_var_input_port_name,
                )
                did_mutate_model = True

            previous_src_node_id = relay_node_id
            previous_src_port_name = local_var_output_port_name

        # 逐条重写原始长边（只替换最后一段：relay_k -> dst），让多个消费者共享前置链路
        for item in edges_info_raw:
            if not isinstance(item, dict):
                continue
            edge = item.get("edge")
            node_distance = int(item.get("node_distance", 0) or 0)
            if not isinstance(edge, EdgeModel):
                continue
            if node_distance <= threshold:
                continue

            original_edge_id = str(getattr(edge, "id", "") or "")
            if original_edge_id in model.edges:
                model.edges.pop(original_edge_id, None)
                did_mutate_model = True

            last_step = int(((node_distance - 1) // threshold) * threshold)
            forced_slot_index = int(src_flow_index_raw) + int(last_step)
            relay_src_node_id = relay_node_id_by_slot.get(int(forced_slot_index))
            if not relay_src_node_id:
                raise RuntimeError(
                    "局部变量中转插入失败：未找到目标 relay 节点。"
                    f" block_id={block_id}, src={src_node_id}.{src_port_name}, "
                    f"src_index={src_flow_index_raw}, node_distance={node_distance}, "
                    f"forced_slot_index={forced_slot_index}, relay_steps={relay_steps}"
                )

            edge_to_dst_id = _build_relay_edge_id(original_edge_id, 1)
            model.edges[edge_to_dst_id] = EdgeModel(
                id=edge_to_dst_id,
                src_node=str(relay_src_node_id),
                src_port=str(local_var_output_port_name),
                dst_node=str(edge.dst_node),
                dst_port=str(edge.dst_port),
            )
            did_mutate_model = True

    # 3B1) 同块内“纯数据源 → 远端消费者”共享 relay 链插入：
    # - 锚点为该源端口的“最早消费者流程节点位置”（anchor_flow_index）
    # - 仅对距离锚点超过阈值的消费者边进行重写；最早消费者保持原边（源节点通常会靠近它布局）
    for (block_id, src_node_id, src_port_name), group in pure_data_source_groups.items():
        anchor_flow_index_raw = group.get("anchor_flow_index")
        edges_info_raw = group.get("edges")
        assert isinstance(anchor_flow_index_raw, int)
        assert isinstance(edges_info_raw, list)
        if not edges_info_raw:
            continue

        # 计算从锚点到最远消费者的跨度
        max_distance = 0
        for item in edges_info_raw:
            if not isinstance(item, dict):
                continue
            dst_flow_index = int(item.get("dst_flow_index", 0) or 0)
            distance = int(dst_flow_index) - int(anchor_flow_index_raw)
            if distance > max_distance:
                max_distance = distance

        if max_distance <= threshold:
            continue

        relay_steps = [step for step in range(threshold, int(max_distance), threshold)]
        if not relay_steps:
            continue

        chain_key = f"{block_id}:{src_node_id}:{src_port_name}:pure_data"
        relay_node_id_by_slot: Dict[int, str] = {}

        for relay_index, step in enumerate(relay_steps, start=1):
            forced_slot_index = int(anchor_flow_index_raw) + int(step)
            relay_node_id = _build_relay_node_id(
                original_edge_key=chain_key,
                relay_index=relay_index,
                target_block_id=block_id,
                target_slot_index=forced_slot_index,
            )
            relay_node_id_by_slot[int(forced_slot_index)] = relay_node_id

            if relay_node_id not in existing_node_ids:
                relay_node = NodeModel(
                    id=relay_node_id,
                    title=str(local_var_node_def.name),
                    category=str(local_var_node_def.category),
                    inputs=[
                        PortModel(name=str(port_name), is_input=True)
                        for port_name in (local_var_node_def.inputs or [])
                    ],
                    outputs=[
                        PortModel(name=str(port_name), is_input=False)
                        for port_name in (local_var_node_def.outputs or [])
                    ],
                )
                relay_node._rebuild_port_maps()
                model.nodes[relay_node_id] = relay_node
                existing_node_ids.add(relay_node_id)
                did_mutate_model = True

            forced_relay_nodes_by_block_id.setdefault(block_id, set()).add(relay_node_id)
            all_relay_node_ids.add(relay_node_id)

        # 为 relay 节点写入“值输出端口”的类型覆盖（用于中间链路类型传播与 UI 展示）
        group_edges: List[EdgeModel] = []
        for item in edges_info_raw:
            if not isinstance(item, dict):
                continue
            e = item.get("edge")
            if isinstance(e, EdgeModel):
                group_edges.append(e)
        relay_value_type = _choose_relay_value_type_for_group(
            src_node_id=str(src_node_id),
            src_port_name=str(src_port_name),
            edges=group_edges,
        )
        if _set_relay_output_type_overrides(relay_node_id_by_slot.values(), relay_value_type):
            did_mutate_model = True

        # 共享链边：src -> relay1 -> relay2 -> ...
        previous_src_node_id = str(src_node_id)
        previous_src_port_name = str(src_port_name)
        link_index = 1

        for slot_index in sorted(relay_node_id_by_slot.keys()):
            relay_node_id = relay_node_id_by_slot[int(slot_index)]
            edge_to_relay_id = _build_relay_chain_edge_id(chain_key=chain_key, link_index=link_index)
            link_index += 1

            existing_edge = model.edges.get(edge_to_relay_id)
            if (
                existing_edge is None
                or str(getattr(existing_edge, "src_node", "")) != str(previous_src_node_id)
                or str(getattr(existing_edge, "src_port", "")) != str(previous_src_port_name)
                or str(getattr(existing_edge, "dst_node", "")) != str(relay_node_id)
                or str(getattr(existing_edge, "dst_port", "")) != str(local_var_input_port_name)
            ):
                model.edges[edge_to_relay_id] = EdgeModel(
                    id=edge_to_relay_id,
                    src_node=previous_src_node_id,
                    src_port=previous_src_port_name,
                    dst_node=relay_node_id,
                    dst_port=local_var_input_port_name,
                )
                did_mutate_model = True

            previous_src_node_id = relay_node_id
            previous_src_port_name = local_var_output_port_name

        # 重写“超过阈值”的消费者边：用“离自己最近的 relay 输出”作为新 src
        for item in edges_info_raw:
            if not isinstance(item, dict):
                continue
            edge = item.get("edge")
            dst_flow_index = int(item.get("dst_flow_index", 0) or 0)
            if not isinstance(edge, EdgeModel):
                continue

            node_distance = int(dst_flow_index) - int(anchor_flow_index_raw)
            if node_distance <= threshold:
                continue

            original_edge_id = str(getattr(edge, "id", "") or "")
            if original_edge_id in model.edges:
                model.edges.pop(original_edge_id, None)
                did_mutate_model = True

            last_step = int(((node_distance - 1) // threshold) * threshold)
            forced_slot_index = int(anchor_flow_index_raw) + int(last_step)
            relay_src_node_id = relay_node_id_by_slot.get(int(forced_slot_index))
            if not relay_src_node_id:
                raise RuntimeError(
                    "纯数据源的局部变量中转插入失败：未找到目标 relay 节点。"
                    f" block_id={block_id}, src={src_node_id}.{src_port_name}, "
                    f"anchor_index={anchor_flow_index_raw}, node_distance={node_distance}, "
                    f"forced_slot_index={forced_slot_index}, relay_steps={relay_steps}"
                )

            edge_to_dst_id = _build_relay_edge_id(original_edge_id, 1)
            model.edges[edge_to_dst_id] = EdgeModel(
                id=edge_to_dst_id,
                src_node=str(relay_src_node_id),
                src_port=str(local_var_output_port_name),
                dst_node=str(edge.dst_node),
                dst_port=str(edge.dst_port),
            )
            did_mutate_model = True

    # 3B2) 同块内“获取自身实体”中继点：复制查询节点作为 relay（不走局部变量）
    if self_entity_node_def is not None:
        for (block_id, src_node_id, src_port_name), group in self_entity_groups.items():
            min_dst_flow_index_raw = group.get("min_dst_flow_index")
            edges_info_raw = group.get("edges")
            assert isinstance(min_dst_flow_index_raw, int)
            assert isinstance(edges_info_raw, list)
            if not edges_info_raw:
                continue

            anchor_flow_index = int(min_dst_flow_index_raw)
            max_distance = 0
            for item in edges_info_raw:
                if not isinstance(item, dict):
                    continue
                dst_flow_index = int(item.get("dst_flow_index", 0) or 0)
                distance = int(dst_flow_index) - int(anchor_flow_index)
                if distance > max_distance:
                    max_distance = distance

            if max_distance <= threshold:
                continue

            relay_steps = [step for step in range(threshold, int(max_distance), threshold)]
            if not relay_steps:
                continue

            chain_key = f"{block_id}:{src_node_id}:{src_port_name}:self_entity"
            relay_node_id_by_slot: Dict[int, str] = {}

            for relay_index, step in enumerate(relay_steps, start=1):
                forced_slot_index = int(anchor_flow_index) + int(step)
                relay_node_id = _build_relay_node_id(
                    original_edge_key=chain_key,
                    relay_index=relay_index,
                    target_block_id=block_id,
                    target_slot_index=forced_slot_index,
                )
                relay_node_id_by_slot[int(forced_slot_index)] = relay_node_id

                if relay_node_id not in existing_node_ids:
                    relay_node = NodeModel(
                        id=relay_node_id,
                        title=str(self_entity_node_def.name),
                        category=str(self_entity_node_def.category),
                        inputs=[
                            PortModel(name=str(port_name), is_input=True)
                            for port_name in (self_entity_node_def.inputs or [])
                        ],
                        outputs=[
                            PortModel(name=str(port_name), is_input=False)
                            for port_name in (self_entity_node_def.outputs or [])
                        ],
                    )
                    relay_node._rebuild_port_maps()
                    model.nodes[relay_node_id] = relay_node
                    existing_node_ids.add(relay_node_id)
                    did_mutate_model = True

                forced_relay_nodes_by_block_id.setdefault(block_id, set()).add(relay_node_id)
                all_relay_node_ids.add(relay_node_id)

            # 重写原始长边：用“离自己最近的 self relay 输出”作为新 src
            for item in edges_info_raw:
                if not isinstance(item, dict):
                    continue
                edge = item.get("edge")
                dst_flow_index = int(item.get("dst_flow_index", 0) or 0)
                if not isinstance(edge, EdgeModel):
                    continue

                node_distance = int(dst_flow_index) - int(anchor_flow_index)
                if node_distance <= threshold:
                    continue

                original_edge_id = str(getattr(edge, "id", "") or "")
                if original_edge_id in model.edges:
                    model.edges.pop(original_edge_id, None)
                    did_mutate_model = True

                last_step = int(((node_distance - 1) // threshold) * threshold)
                forced_slot_index = int(anchor_flow_index) + int(last_step)
                relay_src_node_id = relay_node_id_by_slot.get(int(forced_slot_index))
                if not relay_src_node_id:
                    raise RuntimeError(
                        "获取自身实体中继点插入失败：未找到目标 relay 节点。"
                        f" block_id={block_id}, src={src_node_id}.{src_port_name}, "
                        f"anchor_index={anchor_flow_index}, node_distance={node_distance}, "
                        f"forced_slot_index={forced_slot_index}, relay_steps={relay_steps}"
                    )

                edge_to_dst_id = _build_relay_edge_id(original_edge_id, 1)
                model.edges[edge_to_dst_id] = EdgeModel(
                    id=edge_to_dst_id,
                    src_node=str(relay_src_node_id),
                    src_port=str(edge.src_port),
                    dst_node=str(edge.dst_node),
                    dst_port=str(edge.dst_port),
                )
                did_mutate_model = True

    # 3C) 跨块长连线：按块路径跨度拆分（兼容旧行为）
    for edge in cross_block_edges:
        src_block_id = node_to_block_id.get(str(edge.src_node), "")
        dst_block_id = node_to_block_id.get(str(edge.dst_node), "")
        if not src_block_id or not dst_block_id or src_block_id == dst_block_id:
            continue

        pair_key = (src_block_id, dst_block_id)
        cached_path = path_cache.get(pair_key)
        if cached_path is None:
            cached_path = _find_shortest_block_path(
                children_by_block_id=children_by_block_id,
                src_block_id=src_block_id,
                dst_block_id=dst_block_id,
            )
            path_cache[pair_key] = cached_path

        if not cached_path:
            continue

        distance = len(cached_path) - 1
        if distance <= threshold:
            continue

        # 类型约束：确认该边可通过局部变量节点承载（避免字典等禁止类型）
        if not _edge_supported_by_local_var_relay(
            edge=edge,
            model=model,
            node_registry=node_registry,
            local_var_node_def=local_var_node_def,
            local_var_input_port_name=local_var_input_port_name,
        ):
            continue

        # 需要插入的 relay 数量：每段最多 threshold
        relay_block_steps = [step for step in range(threshold, distance, threshold)]
        if not relay_block_steps:
            continue

        original_edge_id = str(getattr(edge, "id", "") or "")
        original_edge_key = f"{edge.src_node}:{edge.src_port}->{edge.dst_node}:{edge.dst_port}"
        relay_value_type = _choose_relay_value_type_for_group(
            src_node_id=str(edge.src_node),
            src_port_name=str(edge.src_port),
            edges=[edge],
        )

        # 移除原边，改为链式连线
        if original_edge_id in model.edges:
            model.edges.pop(original_edge_id, None)
            did_mutate_model = True

        previous_src_node_id = str(edge.src_node)
        previous_src_port_name = str(edge.src_port)
        link_index = 1

        for relay_index, step in enumerate(relay_block_steps, start=1):
            target_block_id = str(cached_path[step])
            relay_node_id = _build_relay_node_id(
                original_edge_key=original_edge_key,
                relay_index=relay_index,
                target_block_id=target_block_id,
            )

            if relay_node_id not in existing_node_ids:
                relay_node = NodeModel(
                    id=relay_node_id,
                    title=str(local_var_node_def.name),
                    category=str(local_var_node_def.category),
                    inputs=[PortModel(name=str(port_name), is_input=True) for port_name in (local_var_node_def.inputs or [])],
                    outputs=[
                        PortModel(name=str(port_name), is_input=False) for port_name in (local_var_node_def.outputs or [])
                    ],
                )
                relay_node._rebuild_port_maps()
                model.nodes[relay_node_id] = relay_node
                existing_node_ids.add(relay_node_id)
                did_mutate_model = True

            forced_relay_nodes_by_block_id.setdefault(target_block_id, set()).add(relay_node_id)
            all_relay_node_ids.add(relay_node_id)
            if _set_relay_output_type_overrides([relay_node_id], relay_value_type):
                did_mutate_model = True

            edge_to_relay_id = _build_relay_edge_id(original_edge_id, link_index)
            link_index += 1
            model.edges[edge_to_relay_id] = EdgeModel(
                id=edge_to_relay_id,
                src_node=previous_src_node_id,
                src_port=previous_src_port_name,
                dst_node=relay_node_id,
                dst_port=local_var_input_port_name,
            )
            did_mutate_model = True

            previous_src_node_id = relay_node_id
            previous_src_port_name = local_var_output_port_name

        edge_to_dst_id = _build_relay_edge_id(original_edge_id, link_index)
        model.edges[edge_to_dst_id] = EdgeModel(
            id=edge_to_dst_id,
            src_node=previous_src_node_id,
            src_port=previous_src_port_name,
            dst_node=str(edge.dst_node),
            dst_port=str(edge.dst_port),
        )
        did_mutate_model = True

    if did_mutate_model:
        model.touch_edges_revision()

    return forced_relay_nodes_by_block_id, all_relay_node_ids, did_mutate_model



