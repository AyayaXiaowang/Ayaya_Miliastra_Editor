from __future__ import annotations

import copy
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)

from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_for_concrete_string_list as _build_var_base_message_server_for_concrete_string_list,
)


def _build_node_pin_value_message(*, kind: int, index: int, var_type_int: int, value: Any) -> Dict[str, Any]:
    msg = _build_node_pin_message(kind=int(kind), index=int(index), var_type_int=int(var_type_int), connects=None)
    msg["3"] = _build_var_base_message_server(var_type_int=int(var_type_int), value=value)
    return msg


def _build_pin_index_message(*, kind: int, index: int) -> Dict[str, Any]:
    # 对齐真源样本：index=0 时常省略 field_2（默认值为 0）
    msg: Dict[str, Any] = {"1": int(kind)}
    if int(index) != 0:
        msg["2"] = int(index)
    return msg


def _build_node_connection_message(
    *,
    other_node_id_int: int,
    kind: int,
    index: int,
    index2: Optional[int] = None,
) -> Dict[str, Any]:
    idx1_msg = _build_pin_index_message(kind=int(kind), index=int(index))
    idx2_value = int(index) if index2 is None else int(index2)
    idx2_msg = _build_pin_index_message(kind=int(kind), index=int(idx2_value))
    return {"1": int(other_node_id_int), "2": dict(idx1_msg), "3": dict(idx2_msg)}


def _build_node_pin_message(
    *,
    kind: int,
    index: int,
    index2: Optional[int] = None,
    var_type_int: Optional[int],
    connects: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    idx1_msg = _build_pin_index_message(kind=int(kind), index=int(index))
    secondary_index = int(index) if index2 is None else int(index2)
    idx2_msg = _build_pin_index_message(kind=int(kind), index=int(secondary_index))
    msg: Dict[str, Any] = {"1": dict(idx1_msg), "2": dict(idx2_msg)}
    if isinstance(var_type_int, int):
        msg["4"] = int(var_type_int)
    if connects:
        if len(connects) == 1:
            msg["5"] = dict(connects[0])
        else:
            msg["5"] = list(connects)
    return msg


def _build_flow_link_record_text(
    *,
    src_flow_out_index: int,
    dst_node_id_int: int,
    dst_flow_in_index: int,
    src_flow_out_kernel_index: Optional[int] = None,
    dst_flow_in_kernel_index: Optional[int] = None,
    src_composite_pin_index: Optional[int] = None,
) -> str:
    """按 gia.proto(NodePin/NodeConnection) 构造最小 flow link record（OutFlow -> InFlow）。"""

    def _flow_index(kind: int, index: int) -> Dict[str, Any]:
        # 对齐样本：index=0 时常省略 field_2
        msg: Dict[str, Any] = {"1": int(kind)}
        if int(index) != 0:
            msg["2"] = int(index)
        return msg

    out_idx_shell = _flow_index(2, int(src_flow_out_index))  # OutFlow(shell)
    out_idx_kernel = _flow_index(
        2,
        int(src_flow_out_index) if src_flow_out_kernel_index is None else int(src_flow_out_kernel_index),
    )
    in_idx_shell = _flow_index(1, int(dst_flow_in_index))  # InFlow(shell)
    in_idx_kernel = _flow_index(
        1,
        int(dst_flow_in_index) if dst_flow_in_kernel_index is None else int(dst_flow_in_kernel_index),
    )
    conn = {"1": int(dst_node_id_int), "2": dict(in_idx_shell), "3": dict(in_idx_kernel)}
    pin = {"1": dict(out_idx_shell), "2": dict(out_idx_kernel), "5": dict(conn)}
    if isinstance(src_composite_pin_index, int) and int(src_composite_pin_index) >= 0:
        pin["7"] = int(src_composite_pin_index)
    return format_binary_data_hex_text(encode_message(pin))


def _encode_varint(value: int) -> bytes:
    v = int(value)
    if v < 0:
        raise ValueError("varint 不支持负数")
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _encode_string_value_message_bytes(text: str) -> bytes:
    """编码一个仅包含 field_1=string 的 protobuf-like message（用于多分支的分支值）。"""
    data = str(text).encode("utf-8")
    # field_number=1, wire_type=2 -> 0x0a
    return b"\x0a" + _encode_varint(len(data)) + data


def _build_multibranch_case_values_record_text(*, case_values: List[str]) -> str:
    """按 schema 构造『多分支』的分支值列表 record（缺样本时使用）。"""
    var_base = _build_var_base_message_server_for_concrete_string_list(values=[str(x) for x in list(case_values)])
    # 样本：NodePin.kind=InParam(3), index=1
    # 对齐真源：该 pin 的 VarType 应为 字符串列表(L<Str>)=11；缺失会导致 type_id_int=null。
    pin = _build_node_pin_message(kind=3, index=1, var_type_int=11, connects=None)
    pin["3"] = var_base
    return format_binary_data_hex_text(encode_message(pin))


def _get_multibranch_value_entries(decoded_record: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    cursor: Any = decoded_record
    path = [
        "field_3",
        "message",
        "field_110",
        "message",
        "field_2",
        "message",
        "field_109",
        "message",
        "field_1",
    ]
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if isinstance(cursor, list):
        return cursor
    return None


def _node_has_multibranch_value_record(node_obj: Dict[str, Any]) -> bool:
    records = node_obj.get("4")
    if not isinstance(records, list):
        return False
    for record in records:
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            continue
        if _get_multibranch_value_entries(decoded) is not None:
            return True
    return False


def _patch_multibranch_case_values_in_node(*, node_obj: Dict[str, Any], case_values: List[str]) -> None:
    """将多分支节点的“分支值列表”record 写回为给定 case_values（顺序即 index=1..N）。"""
    records = node_obj.get("4")
    if not isinstance(records, list):
        raise ValueError("多分支节点缺少 records(node['4'])")

    target_index: Optional[int] = None
    target_decoded: Optional[Dict[str, Any]] = None
    for i, record in enumerate(records):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            continue
        if _get_multibranch_value_entries(decoded) is None:
            continue
        target_index = int(i)
        target_decoded = decoded
        break

    if target_index is None or target_decoded is None:
        # 无样本 record：仅当存在动态 case 时需要写入
        if not case_values:
            return
        records.append(_build_multibranch_case_values_record_text(case_values=list(case_values)))
        return

    entries = _get_multibranch_value_entries(target_decoded)
    if not isinstance(entries, list):
        raise ValueError("多分支分支值列表路径不是 list")
    if not entries:
        # 记录存在但为空：直接用 schema 生成一个新 record 替换（当 case_values 为空则无需写）
        if not case_values:
            return
        records[int(target_index)] = _build_multibranch_case_values_record_text(case_values=list(case_values))
        return

    entry_template = copy.deepcopy(entries[0])
    new_entries: List[Dict[str, Any]] = []
    for text in case_values:
        entry_obj = copy.deepcopy(entry_template)
        msg = entry_obj.get("message")
        if not isinstance(msg, dict):
            raise ValueError("多分支分支值 entry 缺少 message")
        msg["field_105"] = {
            "raw_hex": _encode_string_value_message_bytes(str(text)).hex(),
            "utf8": str(text),
        }
        new_entries.append(entry_obj)

    entries[:] = new_entries

    dump_json_message = _decoded_field_map_to_dump_json_message(target_decoded)
    # 对齐真源：分支值列表 pin(kind=3,index=1) 的 VarType 必须为 字符串列表(L<Str>)=11。
    dump_json_message["4"] = 11
    record_bytes = encode_message(dump_json_message)
    records[target_index] = format_binary_data_hex_text(record_bytes)


def _extract_nested_int(decoded_record: Dict[str, Any], path: List[str]) -> Optional[int]:
    cursor: Any = decoded_record
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    if not isinstance(cursor, dict):
        return None
    number = cursor.get("int")
    if isinstance(number, int):
        return int(number)
    return None


def _ensure_int_node(decoded_fields: Dict[str, Any], key: str, value: int) -> None:
    node = decoded_fields.get(key)
    if not isinstance(node, dict):
        raise ValueError(f"expected decoded int node at {key!r}, got {type(node).__name__}")
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def _set_int_node(decoded_fields: Dict[str, Any], key: str, value: int) -> None:
    """设置/创建一个 decoded int node（用于模板补丁中缺失 field_2 的场景）。"""
    node = decoded_fields.get(key)
    if node is None:
        decoded_fields[key] = {}
        node = decoded_fields.get(key)
    if not isinstance(node, dict):
        raise ValueError(f"expected decoded int node at {key!r}, got {type(node).__name__}")
    node["int"] = int(value)
    lower32 = int(value) & 0xFFFFFFFF
    node["int32_high16"] = lower32 >> 16
    node["int32_low16"] = lower32 & 0xFFFF


def _extract_data_record_slot_index(decoded_record: Dict[str, Any]) -> int:
    """
    从 data record 中提取“端口序号/槽位序号”。

    经验结论（来自校准图样本）：
    - data record/常量 record 会在 field_1.message.field_2 中携带端口序号（0/1/2/...）；
    - 第一个数据输入端口常见缺失该字段（视为 0）。
    """
    slot = _extract_nested_int(decoded_record, ["field_1", "message", "field_2"])
    return int(slot) if isinstance(slot, int) else 0


def _extract_data_record_src_port_index(decoded_record: Dict[str, Any]) -> Optional[int]:
    a = _extract_nested_int(decoded_record, ["field_5", "message", "field_2", "message", "field_1"])
    if isinstance(a, int):
        return int(a)
    b = _extract_nested_int(decoded_record, ["field_5", "message", "field_3", "message", "field_1"])
    if isinstance(b, int):
        return int(b)
    return None


def _set_data_record_src_port_index(*, field_5_msg: Dict[str, Any], src_port_index_int: int) -> None:
    wrote_any = False
    for key in ("field_2", "field_3"):
        wrapper = field_5_msg.get(key)
        if not isinstance(wrapper, dict):
            continue
        nested = wrapper.get("message")
        if not isinstance(nested, dict):
            continue
        _ensure_int_node(nested, "field_1", int(src_port_index_int))
        wrote_any = True
    if not wrote_any:
        raise ValueError("data record 缺少 field_5.message.field_2/field_3，无法设置 src_port_index")


def _set_data_record_src_outparam_index(
    *,
    field_5_msg: Dict[str, Any],
    out_index: int,
    out_kernel_index: Optional[int] = None,
) -> None:
    """为 data record 的 NodeConnection.connect/connect2 写入 OutParam 的 index（field_2）。"""
    kernel_index_value = int(out_index) if out_kernel_index is None else int(out_kernel_index)
    key_and_index = (("field_2", int(out_index)), ("field_3", int(kernel_index_value)))
    for key, index_value in key_and_index:
        wrapper = field_5_msg.get(key)
        if not isinstance(wrapper, dict):
            continue
        nested = wrapper.get("message")
        if not isinstance(nested, dict):
            continue
        # kind 已在模板中或由 _set_data_record_src_port_index 写为 4（OutParam）
        if int(index_value) == 0:
            nested.pop("field_2", None)
        else:
            _set_int_node(nested, "field_2", int(index_value))


def _decoded_field_map_to_dump_json_message(decoded_fields: Mapping[str, Any]) -> Dict[str, Any]:
    message: Dict[str, Any] = {}
    for key, value in decoded_fields.items():
        if not isinstance(key, str) or not key.startswith("field_"):
            continue
        suffix = key.replace("field_", "")
        if not suffix.isdigit():
            continue
        message[str(int(suffix))] = _decoded_value_to_dump_json_value(value)
    return message


def _decoded_value_to_dump_json_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decoded_value_to_dump_json_value(item) for item in value]

    if isinstance(value, Mapping):
        if "message" in value:
            nested = value.get("message")
            if not isinstance(nested, Mapping):
                raise ValueError("decoded message is not dict")
            return _decoded_field_map_to_dump_json_message(nested)

        if "int" in value:
            raw_int = value.get("int")
            if not isinstance(raw_int, int):
                raise ValueError("decoded int node missing int")
            return int(raw_int)

        if "fixed32_float" in value:
            float_value = value.get("fixed32_float")
            if not isinstance(float_value, float):
                raise ValueError("decoded fixed32_float node missing fixed32_float")
            return float(float_value)

        if "fixed64_double" in value:
            double_value = value.get("fixed64_double")
            if not isinstance(double_value, float):
                raise ValueError("decoded fixed64_double node missing fixed64_double")
            return float(double_value)

        if "raw_hex" in value:
            raw_hex = value.get("raw_hex")
            if not isinstance(raw_hex, str):
                raise ValueError("decoded raw_hex node missing raw_hex")
            raw_bytes = bytes.fromhex(raw_hex)
            return format_binary_data_hex_text(raw_bytes)

        raise ValueError(f"unsupported decoded node: keys={sorted(value.keys())}")

    raise ValueError(f"unsupported decoded value type: {type(value).__name__}")


def _decode_type_id_from_node(node_object: Dict[str, Any]) -> int:
    binary_text = node_object.get("2")
    if not isinstance(binary_text, str) or not binary_text.startswith("<binary_data>"):
        raise ValueError("node['2'] 不是 <binary_data> 字符串，无法提取 type_id")
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(binary_text))
    if not isinstance(decoded, dict):
        raise ValueError("node['2'] decode 结果不是 dict")
    field_5 = decoded.get("field_5")
    if not isinstance(field_5, dict) or not isinstance(field_5.get("int"), int):
        raise ValueError("node['2'] decode 缺少 field_5.int(type_id)")
    return int(field_5["int"])


def _is_link_record(*, record_bytes: bytes, node_id_set: set[int]) -> Tuple[bool, str]:
    decoded = decode_bytes_to_python(record_bytes)
    if not isinstance(decoded, dict):
        return False, ""
    # 先确认它看起来像一个 NodePin message：
    # - field_1/field_2 为 PinIndex（kind/index），且两者一致
    kind1 = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
    kind2 = _extract_nested_int(decoded, ["field_2", "message", "field_1"])
    if not isinstance(kind1, int) or not isinstance(kind2, int):
        return False, ""
    if int(kind1) not in (1, 2, 3, 4):
        return False, ""
    if int(kind2) != int(kind1):
        return False, ""
    # 注意：真源样本中存在“同一 pin 的双索引编码”（field_1.index 与 field_2.index 不相同），例如【修改结构体】：
    # - field_1.index = 2（字段值 pin）
    # - field_2.index = 1（内部映射槽位）
    # 因此这里不再强约束 idx1 == idx2，只要求 kind 一致，后续以 field_5(other_node_id) 判定 link record。

    other_node_id = _extract_nested_int(decoded, ["field_5", "message", "field_1"])
    if not isinstance(other_node_id, int):
        return False, ""
    if int(other_node_id) <= 0:
        return False, ""
    # 注意：不要求 other_node_id 必须属于 node_id_set。
    #
    # 原因：真实导出样本可能存在“悬空连接”（例如某个被工具注入的 source 节点被编辑器剔除，
    # 导致 data-link record 仍保留，但 other_node_id 指向图内并不存在的 node_id）。
    #
    # 在这种情况下：
    # - 模板克隆应剥离这类 link record，避免污染新图；
    # - 模板库提取也应允许复用这类 record 结构（写回阶段会重写 other_node_id）。
    is_data = "field_4" in decoded
    return True, ("data" if is_data else "flow")


def _strip_all_link_records_from_node(*, node: Dict[str, Any], template_node_id_set: set[int]) -> None:
    records_value = node.get("4")
    if not isinstance(records_value, list):
        return
    kept: List[Any] = []
    for record in records_value:
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            kept.append(record)
            continue
        record_bytes = parse_binary_data_hex_text(record)
        is_link, _kind = _is_link_record(record_bytes=record_bytes, node_id_set=template_node_id_set)
        if is_link:
            continue
        kept.append(record)
    node["4"] = kept


def _ensure_record_list(node: Dict[str, Any]) -> List[Any]:
    value = node.get("4")
    if isinstance(value, list):
        return value
    if value is None:
        node["4"] = []
        return node["4"]
    raise ValueError(f"node['4'] 期望为 list 或缺失，但收到: {type(value).__name__}")




# -------------------- Public helpers (reusable) --------------------


def build_node_connection_message(
    *,
    other_node_id_int: int,
    kind: int,
    index: int,
    index2: Optional[int] = None,
) -> Dict[str, Any]:
    return _build_node_connection_message(
        other_node_id_int=int(other_node_id_int),
        kind=int(kind),
        index=int(index),
        index2=(int(index2) if isinstance(index2, int) else None),
    )


def build_node_pin_message(
    *,
    kind: int,
    index: int,
    index2: Optional[int] = None,
    var_type_int: Optional[int],
    connects: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    return _build_node_pin_message(
        kind=int(kind),
        index=int(index),
        index2=(int(index2) if isinstance(index2, int) else None),
        var_type_int=(int(var_type_int) if isinstance(var_type_int, int) else None),
        connects=connects,
    )


def extract_nested_int(decoded_record: Dict[str, Any], path: List[str]) -> Optional[int]:
    return _extract_nested_int(decoded_record, path)


def decoded_field_map_to_dump_json_message(decoded_fields: Mapping[str, Any]) -> Dict[str, Any]:
    return _decoded_field_map_to_dump_json_message(decoded_fields)


def decode_type_id_from_node(node_object: Dict[str, Any]) -> int:
    return _decode_type_id_from_node(node_object)


def ensure_record_list(node: Dict[str, Any]) -> List[Any]:
    return _ensure_record_list(node)


def sort_node_pin_records_inplace(node: Dict[str, Any]) -> None:
    """
    对齐真源 `.gil` 的常见落盘形态：同一节点的 pins(records) 往往按 (kind,index) 稳定排序。

    背景：
    - 写回链路在“常量写回/连线写回/信号 meta 补丁”等多个阶段可能会 append 新 pin record；
      若不做归一化，最终 records 的顺序会依赖阶段顺序与“哪个 pin 被后补”。
    - 已观测：信号节点的参数 pin 若被追加到末尾（例如 param0 在 data-edge 阶段才生成），
      编辑器可渲染但运行时可能更严格，出现“无法开始游戏”的现象。

    说明：
    - 这里仅做顺序归一化，不修改任何 pin 内容（connect/value/var_type/compositePinIndex 等）。
    - 对无法解析出 (kind,index) 的 record，保持相对顺序并放到末尾（稳定排序）。
    """
    records_value = node.get("4")
    if not isinstance(records_value, list) or len(records_value) <= 1:
        return

    decorated: List[Tuple[Tuple[int, int, int], Any]] = []
    for i, record in enumerate(list(records_value)):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            decorated.append(((10_000, 10_000, int(i)), record))
            continue

        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            decorated.append(((10_000, 10_000, int(i)), record))
            continue

        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        kind_int = int(kind) if isinstance(kind, int) else 10_000
        idx_int = int(idx) if isinstance(idx, int) else 0
        decorated.append(((int(kind_int), int(idx_int), int(i)), record))

    decorated.sort(key=lambda x: x[0])
    node["4"] = [r for (_k, r) in decorated]
