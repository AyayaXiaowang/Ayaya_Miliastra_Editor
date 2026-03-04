from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .composite_writeback_types import CompositeWritebackArtifacts


def _as_list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in list(value) if isinstance(x, dict)]
    if isinstance(value, dict):
        return [value]
    return []


def _is_resource_locator(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    # resource_locator: {1:origin,2:category,3:kind,5:runtime_id}
    return all(isinstance(obj.get(k), int) for k in ("1", "2", "3", "5"))


def _try_get_node_def_id_int(node_def: Any) -> int | None:
    if not isinstance(node_def, dict):
        return None
    sig = node_def.get("4")
    if not isinstance(sig, dict):
        return None
    shell = sig.get("1")
    if not isinstance(shell, dict):
        return None
    node_def_id = shell.get("5")
    return int(node_def_id) if isinstance(node_def_id, int) else None


def _try_get_signature_graph_runtime_id_int(node_def: Any) -> int | None:
    """
    NodeInterface.signature.graph_ref(runtime_id) 是复合节点“打开后能看到内部内容”的关键引用。
    如果 base 侧该引用缺失/编码异常，保留 base 会导致复合节点表现为空壳。
    """
    if not isinstance(node_def, dict):
        return None
    sig = node_def.get("4")
    if not isinstance(sig, dict):
        return None
    graph_ref = sig.get("4")
    if not _is_resource_locator(graph_ref):
        return None
    runtime_id = graph_ref.get("5")
    return int(runtime_id) if isinstance(runtime_id, int) else None


def _should_preserve_existing_node_def(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    """
    真源对齐策略（修正）：
    - base 已存在且“结构有效 + graph_ref 匹配”时，保留 base（避免覆盖未知字段）。
    - base 若缺少有效 graph_ref 或与 incoming 不一致，则必须用 incoming 覆盖，否则编辑器无法定位复合子图。
    """
    existing_graph_id = _try_get_signature_graph_runtime_id_int(existing)
    incoming_graph_id = _try_get_signature_graph_runtime_id_int(incoming)
    if incoming_graph_id is None:
        return True
    if existing_graph_id is None:
        return False
    return int(existing_graph_id) == int(incoming_graph_id)


def _try_get_composite_graph_id_int(graph_obj: Any) -> int | None:
    if not isinstance(graph_obj, dict):
        return None
    graph_ref = graph_obj.get("1")
    if not _is_resource_locator(graph_ref):
        return None
    gid = graph_ref.get("5")
    return int(gid) if isinstance(gid, int) else None


def _extract_existing_composite_graphs(section10: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    兼容历史/分叉形态：
    - 真源：section10['4'] 为 repeated wrapper list：[{ '1': <CompositeGraph> }, ...]
    - 历史/分叉：也可能是 message(field_1=repeated) 的老形态：{'1': <graph> 或 [graphs]}
    - 兼容：也可能直接落为 list[<CompositeGraph>] / dict(<CompositeGraph>)
    """
    raw = section10.get("4")
    if isinstance(raw, list):
        out: list[Dict[str, Any]] = []
        for item in list(raw):
            if not isinstance(item, dict):
                continue
            # common wrapper shape: {"1": <CompositeGraph>}
            if set(item.keys()) == {"1"} and isinstance(item.get("1"), dict):
                out.append(dict(item["1"]))
                continue
            # already a CompositeGraph
            if _try_get_composite_graph_id_int(item) is not None:
                out.append(dict(item))
                continue
        return out
    if isinstance(raw, dict):
        inner = raw.get("1")
        if isinstance(inner, list):
            return [x for x in list(inner) if isinstance(x, dict)]
        if isinstance(inner, dict):
            return [inner]
        if _try_get_composite_graph_id_int(raw) is not None:
            return [raw]
    return []


def _extract_existing_node_defs(section10: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    NodeInterface 表（section10['2']）的真源形态：
    - section10['2'] 为 repeated wrapper list：[{ '1': <NodeInterface> }, ...]

    兼容历史/错误形态：
    - message(field_1=repeated) 的老形态：{'1': <node_def> 或 [<node_def>, ...]}
    - 直接 list[<node_def>]
    - 直接 dict(<node_def>) / 直接 dict({'1': <node_def>})
    """
    raw = section10.get("2")
    if isinstance(raw, dict):
        inner = raw.get("1")
        if isinstance(inner, list):
            return [x for x in list(inner) if isinstance(x, dict)]
        if isinstance(inner, dict):
            return [inner]
        # raw itself might be a NodeInterface
        if _try_get_node_def_id_int(raw) is not None:
            return [raw]
        return []

    if isinstance(raw, list):
        out: list[Dict[str, Any]] = []
        for item in list(raw):
            if not isinstance(item, dict):
                continue
            # common wrong shape: {"1": <node_def>}
            if set(item.keys()) == {"1"} and isinstance(item.get("1"), dict):
                out.append(dict(item["1"]))
                continue
            # already a node_def
            if _try_get_node_def_id_int(item) is not None:
                out.append(dict(item))
                continue
        return out

    if isinstance(raw, dict):
        return [raw]

    return []


def _pack_repeated_message_field1(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not items:
        return {}
    if len(items) == 1:
        return {"1": dict(items[0])}
    return {"1": list(items)}


def _pack_repeated_wrappers_field1(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    真源对齐：
    - section10['2'] / section10['4'] 使用 repeated wrapper：[{ '1': <obj> }, ...]
    - 而不是 message(field_1=repeated) 的“再包一层”形态：{'1': [<obj>, ...]}
    """
    return [{"1": dict(x)} for x in list(items) if isinstance(x, dict)]


def _as_list_or_single_dict_length(value: Any) -> int:
    if isinstance(value, list):
        return len([x for x in value if isinstance(x, dict)])
    if isinstance(value, dict):
        return 1
    return 0


def _should_preserve_existing_composite_graph(existing: Dict[str, Any], incoming: Dict[str, Any]) -> bool:
    """
    CompositeGraph 的关键内容是：
    - field_3: inner nodes
    - field_4: port_mappings

    写回口径（复合节点可编辑性优先）：
    - 只要 incoming 提供了 inner nodes，就用 incoming 覆盖 base。
      否则会出现“base 曾经写过一次错误/泛型的子图，后续写回永远被保留”的问题。
    - 仅当 incoming 为空（例如构建失败/缺子图）时，才保留 base。
    """
    incoming_nodes_len = _as_list_or_single_dict_length(incoming.get("3"))
    if incoming_nodes_len <= 0:
        return True
    return False


def apply_composite_artifacts_to_payload_root_inplace(
    *,
    payload_root: Dict[str, Any],
    artifacts: CompositeWritebackArtifacts,
) -> None:
    section10 = payload_root.get("10")
    if not isinstance(section10, dict):
        raise ValueError("payload_root['10'] must be dict when applying composite artifacts")

    # === node_def_wrappers: section10['2'] ===
    existing_node_defs = _extract_existing_node_defs(section10)
    existing_by_id: Dict[int, Dict[str, Any]] = {}
    for node_def in list(existing_node_defs):
        node_def_id = _try_get_node_def_id_int(node_def)
        if isinstance(node_def_id, int):
            existing_by_id[int(node_def_id)] = dict(node_def)

    # artifacts.node_def_wrappers 兼容旧形态：既可能是 NodeInterface，也可能是 {"1": NodeInterface}
    incoming_node_defs: list[Dict[str, Any]] = []
    for w in list(artifacts.node_def_wrappers):
        if not isinstance(w, dict):
            continue
        if set(w.keys()) == {"1"} and isinstance(w.get("1"), dict):
            incoming_node_defs.append(dict(w["1"]))
            continue
        incoming_node_defs.append(dict(w))

    for node_def in list(incoming_node_defs):
        node_def_id = _try_get_node_def_id_int(node_def)
        if not isinstance(node_def_id, int):
            continue
        existing = existing_by_id.get(int(node_def_id))
        if existing is None:
            existing_by_id[int(node_def_id)] = dict(node_def)
            continue
        if not _should_preserve_existing_node_def(existing, dict(node_def)):
            existing_by_id[int(node_def_id)] = dict(node_def)
    merged_node_defs = [existing_by_id[k] for k in sorted(existing_by_id.keys())]
    if merged_node_defs:
        section10["2"] = _pack_repeated_wrappers_field1(merged_node_defs)

    # === composite graphs: section10['4'] (field_1 repeated) ===
    existing_graphs = _extract_existing_composite_graphs(section10)
    existing_graph_by_id: Dict[int, Dict[str, Any]] = {}
    for g in list(existing_graphs):
        gid = _try_get_composite_graph_id_int(g)
        if isinstance(gid, int):
            existing_graph_by_id[int(gid)] = dict(g)
    for g in list(artifacts.composite_graph_objs):
        gid = _try_get_composite_graph_id_int(g)
        if not isinstance(gid, int):
            continue
        existing = existing_graph_by_id.get(int(gid))
        if existing is None:
            existing_graph_by_id[int(gid)] = dict(g)
            continue
        if not _should_preserve_existing_composite_graph(existing, dict(g)):
            existing_graph_by_id[int(gid)] = dict(g)
    merged_graphs = [existing_graph_by_id[k] for k in sorted(existing_graph_by_id.keys())]
    if merged_graphs:
        section10["4"] = _pack_repeated_wrappers_field1(merged_graphs)


__all__ = ["apply_composite_artifacts_to_payload_root_inplace"]

