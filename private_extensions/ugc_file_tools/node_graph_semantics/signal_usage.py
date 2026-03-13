from __future__ import annotations


SIGNAL_NAME_PORT = "信号名"
SIGNAL_SOURCE_ENTITY_OUTPUT = "信号来源实体"
NODE_DEF_REF_KIND_EVENT = "event"

SIGNAL_NODE_TITLES = frozenset({"发送信号", "监听信号", "向服务器节点图发送信号", "发送信号到服务端"})


def iter_static_signal_names_from_graph_model_payload(*, graph_model_payload: object) -> list[str]:
    """从 GraphModel.payload 中收集“静态绑定”的信号名列表（保留重复）。"""
    out: list[str] = []
    payload = graph_model_payload if isinstance(graph_model_payload, dict) else None
    if not isinstance(payload, dict):
        return out

    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        return out

    nodes_with_signal_name_in_edge: set[str] = set()
    edges = payload.get("edges")
    if isinstance(edges, list):
        for e in edges:
            if not isinstance(e, dict):
                continue
            dst_node = str(e.get("dst_node") or "").strip()
            dst_port = str(e.get("dst_port") or "").strip()
            if dst_node != "" and dst_port == SIGNAL_NAME_PORT:
                nodes_with_signal_name_in_edge.add(dst_node)

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_id = str(node.get("id") or node.get("node_id") or "").strip()
        if node_id != "" and node_id in nodes_with_signal_name_in_edge:
            continue

        title = str(node.get("title") or "").strip()
        input_constants = node.get("input_constants")
        input_constants_dict = dict(input_constants) if isinstance(input_constants, dict) else None

        if title in SIGNAL_NODE_TITLES:
            name = _try_read_static_signal_name_from_input_constants(input_constants_dict)
            if name is not None:
                out.append(name)
                continue
            if _is_listen_signal_event_node_payload(node):
                key = _try_read_signal_name_from_node_def_ref_key(node)
                if key is not None:
                    out.append(key)
            continue

        if not _is_listen_signal_event_node_payload(node):
            continue

        name2 = _try_read_static_signal_name_from_input_constants(input_constants_dict)
        if name2 is not None:
            out.append(name2)
            continue

        key2 = _try_read_signal_name_from_node_def_ref_key(node)
        if key2 is not None:
            out.append(key2)
            continue

        if title != "":
            out.append(title)

    return out


def collect_static_signal_names_from_graph_model_payload(*, graph_model_payload: object) -> set[str]:
    """从 GraphModel.payload 中收集“静态绑定”的信号名集合。"""
    return set(iter_static_signal_names_from_graph_model_payload(graph_model_payload=graph_model_payload))


def collect_signal_name_counts_from_graph_model_payload(*, graph_model_payload: object) -> dict[str, int]:
    """从 GraphModel.payload 中收集“静态绑定”的信号名计数（name->count）。"""
    names = iter_static_signal_names_from_graph_model_payload(graph_model_payload=graph_model_payload)
    counts: dict[str, int] = {}
    for name in names:
        key = str(name or "").strip()
        if key == "":
            continue
        counts[key] = int(counts.get(key, 0)) + 1
    return counts


def _try_read_static_signal_name_from_input_constants(input_constants: dict | None) -> str | None:
    """从 input_constants 中读取静态绑定的信号名。"""
    if input_constants is None:
        return None
    sig_name = input_constants.get(SIGNAL_NAME_PORT)
    if not isinstance(sig_name, str):
        return None
    name = str(sig_name).strip()
    return name if name != "" else None


def _is_listen_signal_event_node_payload(node_payload: dict) -> bool:
    """判断节点 payload 是否为“监听信号”的 event 节点兼容形态。"""
    node_def_ref = node_payload.get("node_def_ref")
    if not isinstance(node_def_ref, dict):
        return False
    if str(node_def_ref.get("kind") or "").strip().lower() != NODE_DEF_REF_KIND_EVENT:
        return False
    outputs = node_payload.get("outputs")
    return isinstance(outputs, list) and any(str(x) == SIGNAL_SOURCE_ENTITY_OUTPUT for x in outputs)


def _try_read_signal_name_from_node_def_ref_key(node_payload: dict) -> str | None:
    """从 node_def_ref.key 读取兼容形态的信号名。"""
    node_def_ref = node_payload.get("node_def_ref")
    if not isinstance(node_def_ref, dict):
        return None
    key = str(node_def_ref.get("key") or "").strip()
    return key if key != "" else None

