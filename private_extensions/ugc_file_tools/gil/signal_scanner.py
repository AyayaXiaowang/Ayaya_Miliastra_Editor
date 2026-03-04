from __future__ import annotations

"""
signal_scanner.py

只读扫描 `.gil` payload 中的“信号定义段（signal entries）”与 NodeGraph 内信号节点使用情况。

目标：
- 用最少的假设提取出可用于 diff/诊断的稳定摘要（不依赖 UI、不依赖写回链路）。
- 适配 dump-json/numeric_message 常见的 “list / scalar / dict” 形态差异。
"""

from typing import Any, Dict, Mapping

from ugc_file_tools.gil_dump_codec.protobuf_like_bridge import (
    binary_data_text_to_numeric_message,
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _extract_int(value: Any) -> int | None:
    if isinstance(value, int):
        return int(value)
    if isinstance(value, Mapping) and isinstance(value.get("int"), int):
        return int(value.get("int"))
    return None


def _index_node_defs_by_id(payload_root: Mapping[str, Any]) -> dict[int, Dict[str, Any]]:
    """
    best-effort：从 payload_root.section10['2'] 提取 node_def_id -> node_def_object。

    用途：
    - 为信号条目补充 send/listen/server 的 signal_name_port_index（包含无参信号）。
    """
    sec10 = payload_root.get("10")
    if not isinstance(sec10, Mapping):
        return {}
    wrappers = sec10.get("2")
    out: dict[int, Dict[str, Any]] = {}
    for w in _as_list(wrappers):
        if not isinstance(w, Mapping):
            continue
        node_def_obj = w.get("1")
        if not isinstance(node_def_obj, Mapping):
            continue
        meta_outer = node_def_obj.get("4")
        meta_inner = meta_outer.get("1") if isinstance(meta_outer, Mapping) else None
        node_def_id = _extract_int(meta_inner.get("5") if isinstance(meta_inner, Mapping) else None)
        if not isinstance(node_def_id, int) or int(node_def_id) <= 0:
            continue
        if int(node_def_id) not in out:
            out[int(node_def_id)] = dict(node_def_obj)
    return out


def _extract_signal_name_port_index_from_node_def(node_def_obj: Any, *, role: str) -> int | None:
    if not isinstance(node_def_obj, Mapping):
        return None
    ports_value = node_def_obj.get("106")
    ports: list[Mapping[str, Any]] = []
    for item in _as_list(ports_value):
        if isinstance(item, Mapping):
            ports.append(item)
    if not ports:
        return None

    role_key = str(role).strip()
    pos = 1 if role_key in ("server", "server_send") else 0
    if pos >= len(ports):
        pos = 0
    port_index = _extract_int(ports[int(pos)].get("8"))
    return int(port_index) if isinstance(port_index, int) and int(port_index) >= 0 else None


def _extract_signal_param_role_port_indices_from_entry(entry: Mapping[str, Any]) -> tuple[list[int], list[int], list[int]]:
    send_ports: list[int] = []
    listen_ports: list[int] = []
    server_ports: list[int] = []
    for raw in _as_list(entry.get("4")):
        decoded: Mapping[str, Any] | None = None
        if isinstance(raw, Mapping):
            decoded = raw
        elif isinstance(raw, str) and raw.startswith("<binary_data>"):
            decoded_obj = binary_data_text_to_numeric_message(raw)
            if isinstance(decoded_obj, Mapping):
                decoded = decoded_obj
        if not isinstance(decoded, Mapping):
            continue
        send_idx = _extract_int(decoded.get("4") if "4" in decoded else decoded.get("field_4"))
        listen_idx = _extract_int(decoded.get("5") if "5" in decoded else decoded.get("field_5"))
        server_idx = _extract_int(decoded.get("6") if "6" in decoded else decoded.get("field_6"))
        if isinstance(send_idx, int):
            send_ports.append(int(send_idx))
        if isinstance(listen_idx, int):
            listen_ports.append(int(listen_idx))
        if isinstance(server_idx, int):
            server_ports.append(int(server_idx))
    return send_ports, listen_ports, server_ports


def _infer_signal_name_port_index_from_param_ports(role: str, ports: list[int]) -> int | None:
    if not (isinstance(ports, list) and ports):
        return None
    first = min(int(x) for x in list(ports) if isinstance(x, int))
    role_key = str(role).strip()
    if role_key == "send":
        inferred = int(first) - 10
    elif role_key == "listen":
        inferred = int(first) - 9
    elif role_key in ("server", "server_send"):
        inferred = int(first) - 3
    else:
        return None
    return int(inferred) if int(inferred) >= 0 else None


def _extract_meta_id_int(meta: Any) -> int | None:
    """
    signal entry 中的 send/listen/server meta 通常包含 `field_5(varint)` 作为 node_def_id/runtime_id。
    meta 的常见形态：
    - dict（numeric_message）
    - "<binary_data> ..."（dump-json bytes）
    """
    if isinstance(meta, Mapping) and isinstance(meta.get("5"), int):
        return int(meta["5"])
    if isinstance(meta, str) and meta.startswith("<binary_data>"):
        decoded = binary_data_text_to_numeric_message(meta)
        v = decoded.get("5")
        if isinstance(v, int):
            return int(v)
    return None


def extract_signal_entry_dicts_from_payload_root(payload_root: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """
    从 payload_root 的常见路径提取 signal entries：
    - root4/10/5/3

    返回：entry 的 numeric_message dict 列表（已对 <binary_data> 做一次 decode）。
    """
    sec10 = payload_root.get("10")
    if not isinstance(sec10, Mapping):
        return []
    sec5 = sec10.get("5")
    if not isinstance(sec5, Mapping):
        return []

    raw_entries = _as_list(sec5.get("3"))
    out: list[Dict[str, Any]] = []
    for e in raw_entries:
        if isinstance(e, Mapping):
            out.append(dict(e))
            continue
        if isinstance(e, str) and e.startswith("<binary_data>"):
            out.append(binary_data_text_to_numeric_message(e))
            continue
    return out


def summarize_signal_entries(payload_root: Mapping[str, Any]) -> list[Dict[str, Any]]:
    """
    将 signal entries 归一化为更稳定的摘要（便于 diff）：
    - signal_name: entry['3']
    - param_count: len(entry['4'])（repeated bytes；单元素可能被标量化）
    - send/listen/server_id_int: entry['1'/'2'/'7'].field_5
    """
    node_def_by_id = _index_node_defs_by_id(payload_root)

    summaries: list[Dict[str, Any]] = []
    for entry in extract_signal_entry_dicts_from_payload_root(payload_root):
        signal_name = str(entry.get("3") or "").strip()
        param_count = len([x for x in _as_list(entry.get("4")) if x is not None])

        signal_index_value = entry.get("6")
        signal_index_int = int(signal_index_value) if isinstance(signal_index_value, int) else None

        send_id_int = _extract_meta_id_int(entry.get("1"))
        listen_id_int = _extract_meta_id_int(entry.get("2"))
        server_id_int = _extract_meta_id_int(entry.get("7"))

        send_param_ports, listen_param_ports, server_param_ports = _extract_signal_param_role_port_indices_from_entry(entry)
        send_signal_name_port_index_int = _extract_signal_name_port_index_from_node_def(
            node_def_by_id.get(int(send_id_int)) if isinstance(send_id_int, int) else None,
            role="send",
        )
        listen_signal_name_port_index_int = _extract_signal_name_port_index_from_node_def(
            node_def_by_id.get(int(listen_id_int)) if isinstance(listen_id_int, int) else None,
            role="listen",
        )
        server_signal_name_port_index_int = _extract_signal_name_port_index_from_node_def(
            node_def_by_id.get(int(server_id_int)) if isinstance(server_id_int, int) else None,
            role="server",
        )
        if send_signal_name_port_index_int is None:
            inferred = _infer_signal_name_port_index_from_param_ports("send", send_param_ports)
            if isinstance(inferred, int):
                send_signal_name_port_index_int = int(inferred)
        if listen_signal_name_port_index_int is None:
            inferred = _infer_signal_name_port_index_from_param_ports("listen", listen_param_ports)
            if isinstance(inferred, int):
                listen_signal_name_port_index_int = int(inferred)
        if server_signal_name_port_index_int is None:
            inferred = _infer_signal_name_port_index_from_param_ports("server_send", server_param_ports)
            if isinstance(inferred, int):
                server_signal_name_port_index_int = int(inferred)

        entry_keys = sorted([k for k in entry.keys() if str(k).isdigit()], key=lambda k: int(k))

        summaries.append(
            {
                "signal_name": signal_name,
                "param_count": int(param_count),
                "signal_index_int": signal_index_int,
                "send_id_int": send_id_int,
                "listen_id_int": listen_id_int,
                "server_id_int": server_id_int,
                "send_signal_name_port_index_int": send_signal_name_port_index_int,
                "listen_signal_name_port_index_int": listen_signal_name_port_index_int,
                "server_signal_name_port_index_int": server_signal_name_port_index_int,
                "send_param_port_indices_int": send_param_ports,
                "listen_param_port_indices_int": listen_param_ports,
                "server_param_port_indices_int": server_param_ports,
                "entry_keys": entry_keys,
            }
        )

    # 稳定排序：便于 diff（不依赖原始顺序）
    summaries.sort(
        key=lambda s: (
            str(s.get("signal_name") or ""),
            int(s.get("param_count") or 0),
            int(s.get("send_id_int") or 0),
        )
    )
    return summaries


def build_signal_node_type_map(signal_summaries: list[Mapping[str, Any]]) -> dict[int, Dict[str, Any]]:
    """
    从 signal summaries 构建 NodeGraph 侧的 “node_type_id_int -> {signal_name, role, param_count}” 映射。
    """
    mapping: dict[int, Dict[str, Any]] = {}
    for s in signal_summaries:
        signal_name = str(s.get("signal_name") or "").strip()
        param_count = int(s.get("param_count") or 0)
        for role in ("send", "listen", "server"):
            tid = s.get(f"{role}_id_int")
            if isinstance(tid, int):
                mapping[int(tid)] = {
                    "signal_name": signal_name,
                    "role": role,
                    "param_count": param_count,
                }
    return mapping


def build_signal_name_role_to_id_map(
    signal_summaries: list[Mapping[str, Any]],
) -> dict[str, Dict[str, int]]:
    """
    构建 “signal_name -> {role -> type_id_int}” 映射。

    用途：
    - 做跨 `.gil` 对照：验证同名信号的 send/listen/server id 是否保持一致
      （避免“看起来渲染正确，但运行时按另一套主键查表/分发导致卡死/无法开始游戏”）。
    """
    out: dict[str, Dict[str, int]] = {}
    for s in signal_summaries:
        name = str(s.get("signal_name") or "").strip()
        if name == "":
            continue
        m = out.setdefault(name, {})
        for role in ("send", "listen", "server"):
            tid = s.get(f"{role}_id_int")
            if isinstance(tid, int):
                m[role] = int(tid)
    return out


def extract_signal_nodes_from_graph_ir(
    graph_ir: Mapping[str, Any],
    *,
    signal_type_map: Mapping[int, Mapping[str, Any]],
) -> list[Dict[str, Any]]:
    """
    从 Graph IR 中抽取信号节点实例（send/listen/server）。
    依赖：graph_ir 节点的 node_type_id_int 在 signal_type_map 中可命中。
    """
    nodes = graph_ir.get("nodes")
    if not isinstance(nodes, list):
        return []

    out: list[Dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        tid = node.get("node_type_id_int")
        if not isinstance(tid, int):
            continue
        info = signal_type_map.get(int(tid))
        if info is None:
            continue

        pins = node.get("pins")
        pins_list = pins if isinstance(pins, list) else []

        pins_order: list[Dict[str, Any]] = []
        pins_order_keys: list[tuple[int, int]] = []
        for p in pins_list:
            if not isinstance(p, Mapping):
                continue
            k = p.get("kind_int")
            idx = p.get("index_int")
            pins_order.append({"kind_int": k, "index_int": idx})
            if isinstance(k, int) and isinstance(idx, int):
                pins_order_keys.append((int(k), int(idx)))
        pins_order_is_sorted = pins_order_keys == sorted(pins_order_keys, key=lambda t: (int(t[0]), int(t[1])))

        meta_pin = None
        param_pins: list[Dict[str, Any]] = []
        for p in pins_list:
            if not isinstance(p, Mapping):
                continue
            kind_int = p.get("kind_int")
            index_int = p.get("index_int")
            if kind_int == 5 and int(index_int or 0) == 0:
                meta_pin = {
                    "index_int": index_int,
                    "value": p.get("value"),
                    "composite_pin_index_int": p.get("composite_pin_index_int"),
                }
            if kind_int == 3:
                connects = p.get("connects")
                connects_count = len(connects) if isinstance(connects, list) else 0
                param_pins.append(
                    {
                        "index_int": index_int,
                        "type_id_int": p.get("type_id_int"),
                        "type_expr": p.get("type_expr"),
                        "value": p.get("value"),
                        "connects_count": connects_count,
                        "composite_pin_index_int": p.get("composite_pin_index_int"),
                    }
                )

        out.append(
            {
                "node_index_int": node.get("node_index_int"),
                "node_type_id_int": int(tid),
                "node_type_name": node.get("node_type_name"),
                "role": str(info.get("role") or ""),
                "signal_name": str(info.get("signal_name") or ""),
                "signal_param_count": int(info.get("param_count") or 0),
                "pins_order": pins_order,
                "pins_order_is_sorted_by_kind_index": bool(pins_order_is_sorted),
                "meta_pin": meta_pin,
                "param_pins": sorted(param_pins, key=lambda x: int(x.get("index_int") or 0)),
            }
        )

    out.sort(key=lambda x: int(x.get("node_index_int") or 0))
    return out


__all__ = [
    "extract_signal_entry_dicts_from_payload_root",
    "summarize_signal_entries",
    "build_signal_node_type_map",
    "build_signal_name_role_to_id_map",
    "extract_signal_nodes_from_graph_ir",
]

