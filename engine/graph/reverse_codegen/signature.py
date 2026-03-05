from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping

from engine.graph.models import GraphModel, NodeModel

from engine.graph.reverse_codegen._common import (
    _COPY_MARKER,
    _is_data_node_copy,
    _is_local_var_relay_node_id,
    _strip_copy_suffix,
)


def build_semantic_signature(model: GraphModel, *, wl_iterations: int = 4) -> Dict[str, Any]:
    """构造“忽略 node/edge id 与布局 pos 的语义签名”，用于 round-trip 比较。"""
    node_hashes = _compute_wl_node_hashes(model, iterations=wl_iterations)
    node_multiset: Dict[str, int] = {}
    for _node_id, h in node_hashes.items():
        node_multiset[h] = node_multiset.get(h, 0) + 1

    edge_multiset: Dict[str, int] = {}
    for edge in (model.edges or {}).values():
        src_hash = node_hashes.get(edge.src_node, "<missing>")
        dst_hash = node_hashes.get(edge.dst_node, "<missing>")
        key = f"{src_hash}|{edge.src_port}=>{dst_hash}|{edge.dst_port}"
        edge_multiset[key] = edge_multiset.get(key, 0) + 1

    return {
        "graph_id": str(getattr(model, "graph_id", "") or ""),
        "graph_name": str(getattr(model, "graph_name", "") or ""),
        "description": str(getattr(model, "description", "") or ""),
        "graph_variables": _normalize_graph_variables(getattr(model, "graph_variables", []) or []),
        "metadata": _normalize_graph_metadata(getattr(model, "metadata", {}) or {}),
        "nodes": dict(sorted(node_multiset.items(), key=lambda item: item[0])),
        "edges": dict(sorted(edge_multiset.items(), key=lambda item: item[0])),
    }


def diff_semantic_signature(sig_a: Mapping[str, Any], sig_b: Mapping[str, Any]) -> List[str]:
    """对两个语义签名做差分，返回人类可读的差异信息列表。"""
    diffs: List[str] = []

    def _diff_field(field: str) -> None:
        if sig_a.get(field) != sig_b.get(field):
            diffs.append(f"{field} 不一致：A={sig_a.get(field)!r} B={sig_b.get(field)!r}")

    _diff_field("graph_id")
    _diff_field("graph_name")
    _diff_field("description")
    _diff_field("graph_variables")
    _diff_field("metadata")

    if sig_a.get("nodes") != sig_b.get("nodes"):
        diffs.append("节点集合（按结构哈希）不一致")
    if sig_a.get("edges") != sig_b.get("edges"):
        diffs.append("连线集合（按结构哈希）不一致")

    return diffs


def _normalize_graph_variables(graph_variables: List[Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for item in graph_variables:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        items.append(entry)
    items.sort(key=lambda d: str(d.get("name", "")))
    return items


def _normalize_graph_metadata(metadata: Mapping[str, Any]) -> Dict[str, Any]:
    # 只比较“语义相关”字段，忽略 parsed_at/source_file 等解析时信息
    allow_keys = {
        "graph_type",
        "folder_path",
        "signal_bindings",
        "struct_bindings",
        "custom_variable_file",
    }
    result: Dict[str, Any] = {}
    for key in allow_keys:
        if key in metadata:
            if key == "signal_bindings":
                result[key] = _normalize_signal_bindings(metadata.get(key))
                continue
            if key == "struct_bindings":
                result[key] = _normalize_struct_bindings(metadata.get(key))
                continue
            result[key] = metadata.get(key)
    return result


def _normalize_signal_bindings(value: Any) -> List[Dict[str, Any]]:
    """将 {node_id: {...}} 规范化为与 node_id 无关的稳定列表。"""
    if not isinstance(value, dict):
        return []
    entries: List[Dict[str, Any]] = []
    for info in value.values():
        if not isinstance(info, dict):
            continue
        signal_id = info.get("signal_id")
        entry: Dict[str, Any] = {}
        if isinstance(signal_id, str) and signal_id.strip():
            entry["signal_id"] = signal_id.strip()
        if entry:
            entries.append(entry)
    entries.sort(key=lambda d: (str(d.get("signal_id", "")), json.dumps(d, ensure_ascii=False, sort_keys=True)))
    return entries


def _normalize_struct_bindings(value: Any) -> List[Dict[str, Any]]:
    """将 {node_id: {...}} 规范化为与 node_id 无关的稳定列表。"""
    if not isinstance(value, dict):
        return []
    entries: List[Dict[str, Any]] = []
    for info in value.values():
        if not isinstance(info, dict):
            continue
        entry: Dict[str, Any] = {}
        struct_id = info.get("struct_id")
        struct_name = info.get("struct_name")
        field_names = info.get("field_names")
        if isinstance(struct_id, str) and struct_id.strip():
            entry["struct_id"] = struct_id.strip()
        if isinstance(struct_name, str) and struct_name.strip():
            entry["struct_name"] = struct_name.strip()
        if isinstance(field_names, list):
            entry["field_names"] = [str(x) for x in field_names if str(x).strip() != ""]
        if entry:
            entries.append(entry)
    entries.sort(key=lambda d: json.dumps(d, ensure_ascii=False, sort_keys=True))
    return entries


def _compute_wl_node_hashes(model: GraphModel, *, iterations: int) -> Dict[str, str]:
    raw_nodes = dict(getattr(model, "nodes", {}) or {})
    raw_edges = list((getattr(model, "edges", {}) or {}).values())

    # 语义归一化：对“已连线输入端口”的常量做剔除。
    #
    # 说明：
    # - 解析器在某些场景会同时写入 input_constants 与数据连线（例如：变量既被视为命名常量，
    #   又在 VarEnv 中有连线来源时，两条路径都会生效），但运行期/导出期以连线为准；
    # - 因此“连线覆盖常量”，常量在该端口上等价于冗余信息，不应影响语义签名。
    # 另外：忽略布局层插入的 localvar relay / data copy：
    # - relay/copy 本质是“结构增强/排版辅助”，不应影响 round-trip 语义一致性判断；
    # - 对这些节点的边做“透传/归一化”，再进入 WL hashing。

    # 1) canonical node id（copy -> original；relay 仍保留 id 以便后续透传）
    def _canonical_node_id(node_id: str) -> str:
        node_id_text = str(node_id or "")
        node_obj = raw_nodes.get(node_id_text)
        if node_obj is not None and (_is_data_node_copy(node_obj) or (_COPY_MARKER in node_id_text)):
            original = str(getattr(node_obj, "original_node_id", "") or "") or node_id_text
            return _strip_copy_suffix(original) or node_id_text
        if _COPY_MARKER in node_id_text:
            return _strip_copy_suffix(node_id_text) or node_id_text
        return node_id_text

    # 2) 原始入边索引（供 relay 透传）
    raw_in_by_port: Dict[tuple[str, str], tuple[str, str]] = {}
    for e in raw_edges:
        raw_in_by_port[(str(getattr(e, "dst_node", "") or ""), str(getattr(e, "dst_port", "") or ""))] = (
            str(getattr(e, "src_node", "") or ""),
            str(getattr(e, "src_port", "") or ""),
        )

    def _resolve_relay_source(src_node_id: str, src_port: str, *, depth: int = 0) -> tuple[str, str]:
        if depth > 50:
            return str(src_node_id), str(src_port)
        nid = _canonical_node_id(str(src_node_id))
        port = str(src_port)
        if _is_local_var_relay_node_id(nid) and port == "值":
            upstream = raw_in_by_port.get((nid, "初始值"))
            if upstream is not None:
                return _resolve_relay_source(upstream[0], upstream[1], depth=depth + 1)
        return nid, port

    # 3) 收敛节点集合：剔除 relay/copy 节点（relay 通过透传边表达）
    nodes: Dict[str, NodeModel] = {}
    for node_id, node in raw_nodes.items():
        if node is None:
            continue
        canonical = _canonical_node_id(str(node_id))
        if _is_local_var_relay_node_id(canonical):
            continue
        if canonical not in nodes or _is_data_node_copy(nodes[canonical]) and (not _is_data_node_copy(node)):
            nodes[canonical] = node

    # 4) 重写边：copy 归一 + relay 透传；并丢弃“指向 relay/copy 的边”
    rewritten_edges: List[tuple[str, str, str, str]] = []
    for e in raw_edges:
        src_node_raw = str(getattr(e, "src_node", "") or "")
        dst_node_raw = str(getattr(e, "dst_node", "") or "")
        src_port = str(getattr(e, "src_port", "") or "")
        dst_port = str(getattr(e, "dst_port", "") or "")
        if not src_node_raw or not dst_node_raw or not src_port or not dst_port:
            continue

        dst_node = _canonical_node_id(dst_node_raw)
        if _is_local_var_relay_node_id(dst_node):
            # relay 节点本身被剔除：其入边不参与语义比较
            continue
        if dst_node not in nodes:
            continue

        src_node, src_port_resolved = _resolve_relay_source(src_node_raw, src_port)
        if _is_local_var_relay_node_id(src_node):
            # relay 的非“值”输出不参与语义比较（理论上不应出现）
            continue
        if src_node not in nodes:
            continue

        rewritten_edges.append((src_node, src_port_resolved, dst_node, dst_port))

    connected_inputs: Dict[str, set[str]] = {nid: set() for nid in nodes.keys()}
    for (src_node_id, _src_port, dst_node_id, dst_port) in rewritten_edges:
        connected_inputs.setdefault(dst_node_id, set()).add(str(dst_port))

    base_label: Dict[str, str] = {}
    for node_id, node in nodes.items():
        input_constants = dict(getattr(node, "input_constants", {}) or {})
        connected = connected_inputs.get(node_id)
        if connected:
            for k in list(input_constants.keys()):
                if str(k) in connected:
                    input_constants.pop(k, None)
        label_obj = {
            "category": str(getattr(node, "category", "") or ""),
            "title": str(getattr(node, "title", "") or ""),
            "composite_id": str(getattr(node, "composite_id", "") or ""),
            "inputs": [str(getattr(p, "name", "") or "") for p in (getattr(node, "inputs", []) or [])],
            "outputs": [str(getattr(p, "name", "") or "") for p in (getattr(node, "outputs", []) or [])],
            "input_constants": input_constants,
        }
        base_label[node_id] = _stable_hash_from_obj(label_obj)

    incoming: Dict[str, List[tuple[str, str, str]]] = {nid: [] for nid in nodes.keys()}
    outgoing: Dict[str, List[tuple[str, str, str]]] = {nid: [] for nid in nodes.keys()}
    for (src_node_id, src_port, dst_node_id, dst_port) in rewritten_edges:
        if src_node_id not in nodes or dst_node_id not in nodes:
            continue
        outgoing[src_node_id].append((str(src_port), str(dst_port), str(dst_node_id)))
        incoming[dst_node_id].append((str(src_port), str(dst_port), str(src_node_id)))

    current = dict(base_label)
    for _ in range(max(0, int(iterations))):
        next_hash: Dict[str, str] = {}
        for node_id in nodes.keys():
            in_features = [
                f"i:{src_port}->{dst_port}:{current.get(src_node, '<missing>')}"
                for (src_port, dst_port, src_node) in incoming.get(node_id, [])
            ]
            out_features = [
                f"o:{src_port}->{dst_port}:{current.get(dst_node, '<missing>')}"
                for (src_port, dst_port, dst_node) in outgoing.get(node_id, [])
            ]
            in_features.sort()
            out_features.sort()
            combined = {
                "base": base_label.get(node_id, ""),
                "in": in_features,
                "out": out_features,
            }
            next_hash[node_id] = _stable_hash_from_obj(combined)
        current = next_hash
    return current


def _stable_hash_from_obj(obj: Any) -> str:
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()

