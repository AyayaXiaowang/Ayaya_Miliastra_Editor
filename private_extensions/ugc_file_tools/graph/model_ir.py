from __future__ import annotations

"""
GraphModel IR（中间表示）：

- 提供 GraphModel(JSON) 的“结构归一化 + 遍历口径”单一真源；
- 供 pipeline / 导出 / 写回等链路复用，避免跨模块依赖彼此的私有适配函数；
- 这里的 API 以“尽可能兼容历史产物形态”为目标，但不会吞错：输入不是预期结构时返回空结果。
"""

from typing import Any, Dict, Iterator, List, Tuple


def normalize_graph_model_payload(graph_json_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    将“可能包裹过的 GraphModel JSON”归一化为 graph_model dict：

    兼容：
    - export_graph_model_json_from_graph_code.py 的输出结构：{metadata, graph_model}
    - GraphResultDataBuilder 的结构：{data: {...}}
    - 直接 GraphModel.serialize()：{nodes, edges, graph_variables, ...}
    """
    gm = graph_json_object.get("graph_model")
    if isinstance(gm, dict):
        return gm
    data = graph_json_object.get("data")
    if isinstance(data, dict):
        return data
    return graph_json_object


def _looks_like_graph_model_payload(obj: object) -> bool:
    """保守判断一个 dict 是否“看起来像 GraphModel payload”。

    说明：
    - GraphModel payload 约定包含 nodes/edges（至少其一）；
    - 仅以 "data 是 dict" 视为 payload 会导致未来 result_data.data 再套一层时误判。
    """
    if not isinstance(obj, dict):
        return False
    return ("nodes" in obj) or ("edges" in obj)


def pick_graph_model_payload_and_metadata(graph_json_object: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """兼容多种 GraphModel JSON 包裹形态：返回 (metadata, graph_model_payload)。

    兼容输入形态（示例）：
    - typed export（旧）：{metadata:{...}, graph_model:{...}}
    - typed export（现）：{graph_id/name/graph_type/... , data:{nodes:[...], edges:[...]}}
    - GraphResultDataBuilder：{data:{nodes/edges/...}}
    - raw graph_model json：{nodes, edges, ...}

    约定：
    - metadata 必须是“轻量 dict”，禁止直接返回整个顶层对象（避免把大块 data 一并塞进 metadata）。
    - metadata 尽量提供稳定字段：graph_id / graph_name / graph_type / graph_scope（若可推断）。
    """
    meta_obj = graph_json_object.get("metadata")
    metadata: Dict[str, Any] = dict(meta_obj) if isinstance(meta_obj, dict) else {}

    gm_obj = graph_json_object.get("graph_model")
    if isinstance(gm_obj, dict):
        graph_model = gm_obj
    else:
        data_obj = graph_json_object.get("data")
        if _looks_like_graph_model_payload(data_obj):
            graph_model = data_obj  # type: ignore[assignment]
        else:
            graph_model = graph_json_object

    # ---- 统一补齐/对齐常用 metadata 字段（不覆盖已存在值）----
    # graph_id
    if "graph_id" not in metadata:
        v = graph_json_object.get("graph_id")
        if v is not None:
            metadata["graph_id"] = v
        else:
            v2 = graph_model.get("graph_id") if isinstance(graph_model, dict) else None
            if v2 is not None:
                metadata["graph_id"] = v2

    # graph_type / graph_scope（scope）
    if "graph_type" not in metadata:
        v = graph_json_object.get("graph_type")
        if v is not None:
            metadata["graph_type"] = v
        else:
            v2 = graph_model.get("graph_type") if isinstance(graph_model, dict) else None
            if v2 is not None:
                metadata["graph_type"] = v2
    if "graph_scope" not in metadata:
        v = graph_json_object.get("graph_scope")
        if v is not None:
            metadata["graph_scope"] = v

    # graph_name（优先使用顶层 name，其次 graph_name，其次 data.graph_name）
    if "graph_name" not in metadata:
        name0 = graph_json_object.get("name")
        if isinstance(name0, str) and name0.strip():
            metadata["graph_name"] = name0.strip()
        else:
            name1 = graph_json_object.get("graph_name")
            if isinstance(name1, str) and name1.strip():
                metadata["graph_name"] = name1.strip()
            else:
                name2 = graph_model.get("graph_name") if isinstance(graph_model, dict) else None
                if isinstance(name2, str) and name2.strip():
                    metadata["graph_name"] = name2.strip()

    return metadata, graph_model


def _extract_node_payload_dict(node_obj: object) -> Dict[str, Any] | None:
    """
    GraphModel.nodes 的单元素兼容提取：
    - dict：直接视为 payload
    - tuple/list：从末尾向前找第一个 dict（历史兼容：payload dict 常位于末尾）
    """
    if isinstance(node_obj, dict):
        return node_obj
    if isinstance(node_obj, (list, tuple)):
        for item in reversed(node_obj):
            if isinstance(item, dict):
                return item
    return None


def iter_node_payload_dicts(graph_model: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """
    以“payload dict”为单位遍历 nodes（兼容多种 nodes 形态）。

    支持：
    - nodes: dict[id->payload]
    - nodes: list[payload]
    - nodes: list[tuple/list]（payload dict 位于末尾）
    """
    nodes_obj = graph_model.get("nodes")

    if isinstance(nodes_obj, dict):
        for node in nodes_obj.values():
            payload = _extract_node_payload_dict(node)
            if payload is not None:
                yield payload
        return

    if isinstance(nodes_obj, list):
        for node in nodes_obj:
            payload = _extract_node_payload_dict(node)
            if payload is not None:
                yield payload
        return


def normalize_nodes_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将 nodes 归一化为 `list[payload_dict]`（会丢弃非 dict payload）。"""
    return list(iter_node_payload_dicts(graph_model))


def iter_edge_dicts(graph_model: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
    """遍历 edges（仅保留 dict edge）。"""
    edges_obj = graph_model.get("edges")

    if isinstance(edges_obj, dict):
        for edge in edges_obj.values():
            if isinstance(edge, dict):
                yield edge
        return

    if isinstance(edges_obj, list):
        for edge in edges_obj:
            if isinstance(edge, dict):
                yield edge
        return


def normalize_edges_list(graph_model: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将 edges 归一化为 `list[edge_dict]`（会丢弃非 dict）。"""
    return list(iter_edge_dicts(graph_model))


