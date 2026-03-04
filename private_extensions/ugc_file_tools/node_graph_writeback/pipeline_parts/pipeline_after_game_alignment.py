from __future__ import annotations

from typing import Any, Dict, List


def _calc_used_assembly_list_max_pin_index(*, node_id: str, node_payload: Dict[str, Any], edges: List[Dict[str, Any]]) -> int:
    used_ports: set[str] = set()
    input_constants0 = node_payload.get("input_constants")
    if isinstance(input_constants0, dict):
        for k, v in input_constants0.items():
            kk = str(k)
            if kk.isdigit() and v is not None:
                used_ports.add(kk)
    for e in list(edges):
        if not isinstance(e, dict):
            continue
        if str(e.get("dst_node") or "") != str(node_id):
            continue
        dst_port = str(e.get("dst_port") or "")
        if dst_port.isdigit():
            used_ports.add(dst_port)
    if not used_ports:
        return 0
    max_port = max(int(p) for p in used_ports)
    return int(max_port + 1)  # element0 -> pin1


def _prune_unconnected_inparam_records_after_max_index_inplace(*, node_obj: Dict[str, Any], max_pin_index: int) -> None:
    from ugc_file_tools.decode_gil import decode_bytes_to_python
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    from ..record_codec import extract_nested_int as _extract_nested_int_public

    records_value = node_obj.get("4")
    if not isinstance(records_value, list) or not records_value:
        return
    kept: List[Any] = []
    for record in list(records_value):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            kept.append(record)
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            kept.append(record)
            continue
        kind = _extract_nested_int_public(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int_public(decoded, ["field_1", "message", "field_2"])
        idx_int = 0 if idx is None else int(idx)
        if int(kind or -1) == 3 and idx_int > int(max_pin_index) and ("field_5" not in decoded):
            continue
        kept.append(record)
    node_obj["4"] = kept


def prune_assembly_list_unused_high_index_inparam_pins_inplace(
    *,
    sorted_nodes: List[Any],
    edges: List[Dict[str, Any]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
) -> None:
    """
    对齐 after_game：裁剪“拼装列表”的未使用高 index 未连线占位 InParam pins。
    保持与原 pipeline.py 相同的触发与裁剪规则（不做额外兜底/静默降级）。
    """
    for (_y0, _x0, title0, node_id0, node_payload0) in list(sorted_nodes):
        if str(title0) != "拼装列表":
            continue
        if not isinstance(node_payload0, dict):
            continue
        max_pin_index = _calc_used_assembly_list_max_pin_index(
            node_id=str(node_id0),
            node_payload=dict(node_payload0),
            edges=list(edges),
        )
        if int(max_pin_index) <= 0:
            continue
        node_id_int0 = node_id_int_by_graph_node_id.get(str(node_id0))
        if not isinstance(node_id_int0, int):
            continue
        node_obj0 = node_object_by_node_id_int.get(int(node_id_int0))
        if not isinstance(node_obj0, dict):
            continue
        _prune_unconnected_inparam_records_after_max_index_inplace(node_obj=node_obj0, max_pin_index=int(max_pin_index))

