from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.var_base import build_var_base_message_server as _build_var_base_message_server

from ..record_codec import _decoded_field_map_to_dump_json_message, _extract_nested_int
from ..writeback_feature_flags import is_writeback_feature_enabled


def _infer_signal_name_port_index_from_param_port_indices(
    *,
    role: str,
    param_port_indices: List[int],
) -> Optional[int]:
    """
    当 base `.gil` 缺失 node_def（或 node_def['106'] 缺失）时，退化为仅用“参数端口 index”反推信号名端口 index。

    依据真源端口块布局（与 signal_writeback 的块分配一致）：
    - send:        signal_name=+2, first_send_param=+12  => diff=10
    - listen:      signal_name=+4, first_listen_param=+13 => diff=9
    - server_send: signal_name=+11, first_server_param=+14 => diff=3
    """
    if not (isinstance(param_port_indices, list) and param_port_indices):
        return None
    first = min(int(x) for x in list(param_port_indices) if isinstance(x, int))
    role_key = str(role).strip()
    if role_key == "send":
        inferred = int(first) - 10
    elif role_key == "listen":
        inferred = int(first) - 9
    elif role_key == "server_send":
        inferred = int(first) - 3
    else:
        return None
    return int(inferred) if int(inferred) >= 0 else None


def _write_or_patch_signal_meta_pin_record(
    *,
    records: List[Any],
    signal_name: str,
    node_runtime_id_int: int,
    source_ref_node_def_id_int: Optional[int],
    composite_pin_index_int: Optional[int],
) -> None:
    if str(signal_name).strip() == "":
        return

    node_runtime_is_signal_specific = bool(int(node_runtime_id_int) >= 0x40000000)
    has_source_ref = bool(isinstance(source_ref_node_def_id_int, int) and int(source_ref_node_def_id_int) >= 0x40000000)

    index_msg: Dict[str, Any] = {"1": 5}
    # 对齐真源：当节点 runtime 已切换为 signal-specific（0x4000xxxx）时，
    # META pin 通常省略 source_ref（node_def_id）字段；generic runtime 才需要显式写入 source_ref 绑定具体信号。
    if bool(has_source_ref) and (not bool(node_runtime_is_signal_specific)):
        index_msg["100"] = {"1": int(source_ref_node_def_id_int)}

    meta_msg: Dict[str, Any] = {
        "1": dict(index_msg),
        "3": _build_var_base_message_server(var_type_int=6, value=str(signal_name)),
        "6": {"1": 6, "2": 1},
    }
    # 对齐真源（已观测的“校验成功”样本）：
    # META pin 的 “信号名字符串 VarBase” 的 ItemType.type_server(field_100) 常为 empty bytes，
    # 而不是显式写入 `{field_1=6(Str)}`；若写入显式 type_server，官方侧可能更严格校验失败。
    vb = meta_msg.get("3")
    if isinstance(vb, dict) and int(vb.get("1") or 0) == 5:
        item_type = vb.get("4")
        if isinstance(item_type, dict) and int(item_type.get("1") or 0) == 1:
            type_server = item_type.get("100")
            if isinstance(type_server, dict) and dict(type_server) == {"1": 6}:
                item_type["100"] = format_binary_data_hex_text(b"")
    if bool(has_source_ref) and isinstance(composite_pin_index_int, int) and int(composite_pin_index_int) >= 0:
        meta_msg["7"] = int(composite_pin_index_int)

    existing_record_index: Optional[int] = None
    existing_decoded: Optional[Dict[str, Any]] = None
    for i, record in enumerate(list(records)):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            continue
        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        idx_int = 0 if idx is None else int(idx)
        if int(kind or -1) != 5:
            continue
        if idx_int != 0:
            continue
        existing_record_index = int(i)
        existing_decoded = decoded
        break

    if isinstance(existing_record_index, int) and isinstance(existing_decoded, dict):
        dump_msg = _decoded_field_map_to_dump_json_message(existing_decoded)
        dump_msg["1"] = dict(index_msg)

        # 对齐真源：generic(300000/300001/300002) 信号节点的 META pin 通常保留 field_2；
        # signal-specific runtime 节点（0x40000000+）则常省略 field_2。
        if bool(node_runtime_is_signal_specific):
            dump_msg.pop("2", None)
        elif "2" not in dump_msg:
            dump_msg["2"] = {"1": 5}

        dump_msg["3"] = dict(meta_msg["3"])
        dump_msg["6"] = dict(meta_msg["6"])

        # 实测约束（generic runtime=300000/300001/300002）：
        # META pin 缺少 field_4(VarType) 时，编辑器/真源可能无法稳定识别端口类型，
        # 导致信号绑定与参数端口展开/排序出现错位。
        #
        # 但 signal-specific runtime（常见 0x6000xxxx/0x6080xxxx）样本中 META pin 通常会省略 field_4，
        # 因此仅在 generic runtime 下强制写入 field_4=6(Str)。
        if bool(node_runtime_is_signal_specific):
            dump_msg.pop("4", None)
        else:
            dump_msg["4"] = 6

        # META pin 的 compositePinIndex / source_ref：当 base `.gil` 提供 node_def_id 映射时写入（即便节点 runtime 保持 generic）。
        if bool(has_source_ref) and isinstance(composite_pin_index_int, int) and int(composite_pin_index_int) >= 0:
            dump_msg["7"] = int(composite_pin_index_int)
        else:
            dump_msg.pop("7", None)

        dump_msg.pop("5", None)
        records[int(existing_record_index)] = format_binary_data_hex_text(encode_message(dump_msg))
        return

    if not bool(node_runtime_is_signal_specific):
        meta_msg["2"] = {"1": 5}
    # 强制写入 META pin VarType=Str（generic runtime 才需要；signal-specific runtime 样本常省略 field_4）
    if not bool(node_runtime_is_signal_specific):
        meta_msg["4"] = 6

    records.append(format_binary_data_hex_text(encode_message(meta_msg)))


def _patch_signal_meta_node_records_inplace(
    *,
    records: List[Any],
    signal_binding_role: str,
    node_runtime_id_int: int,
    keep_param_pin_composite_pin_index: bool,
) -> None:
    role = str(signal_binding_role or "").strip()
    if role == "":
        return

    keep_records: List[Any] = []
    node_runtime_is_signal_specific = bool(int(node_runtime_id_int) >= 0x40000000)
    keep_param = bool(keep_param_pin_composite_pin_index)

    for record in list(records):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            keep_records.append(record)
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            keep_records.append(record)
            continue

        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        kind_int = int(kind) if isinstance(kind, int) else -1

        if role == "listen" and kind_int == 4:
            # 真源对齐：监听信号节点不保留显式 OutParam 记录，数据连线仅通过目标 InParam.connect 表达。
            continue

        if kind_int == 2 and (not bool(node_runtime_is_signal_specific)):
            dump_msg = _decoded_field_map_to_dump_json_message(decoded)
            # generic 信号节点（300000/300001/300002）不保留 compositePinIndex，
            # 避免模板残留 field_7 误导编辑器端口解释。
            dump_msg.pop("7", None)
            keep_records.append(format_binary_data_hex_text(encode_message(dump_msg)))
            continue

        if kind_int == 3 and (not bool(keep_param)):
            dump_msg = _decoded_field_map_to_dump_json_message(decoded)
            dump_msg.pop("7", None)
            keep_records.append(format_binary_data_hex_text(encode_message(dump_msg)))
            continue

        keep_records.append(record)

    records[:] = keep_records


def patch_signal_meta_records_if_needed(
    *,
    records: List[Any],
    node_type_id_int: int,
    signal_binding_role: str,
    signal_binding_name: str,
    signal_binding_source_ref_node_def_id_int: Optional[int],
    signal_binding_param_port_indices: Optional[List[int]],
    signal_binding_signal_name_port_index: Optional[int],
) -> None:
    if signal_binding_role == "" or signal_binding_name == "":
        return

    if not isinstance(signal_binding_signal_name_port_index, int):
        inferred = _infer_signal_name_port_index_from_param_port_indices(
            role=str(signal_binding_role),
            param_port_indices=signal_binding_param_port_indices if isinstance(signal_binding_param_port_indices, list) else [],
        )
        if isinstance(inferred, int):
            signal_binding_signal_name_port_index = int(inferred)

    resolved_meta_composite_pin_index_int = (
        int(signal_binding_signal_name_port_index) if isinstance(signal_binding_signal_name_port_index, int) else None
    )
    source_ref_node_def_id_int = (
        int(signal_binding_source_ref_node_def_id_int) if isinstance(signal_binding_source_ref_node_def_id_int, int) else None
    )
    should_write_composite_pin_index = bool(
        isinstance(source_ref_node_def_id_int, int)
        and int(source_ref_node_def_id_int) >= 0x40000000
        and isinstance(resolved_meta_composite_pin_index_int, int)
        and int(resolved_meta_composite_pin_index_int) >= 0
    )
    meta_composite_pin_index_int = int(resolved_meta_composite_pin_index_int) if bool(should_write_composite_pin_index) else None

    _write_or_patch_signal_meta_pin_record(
        records=records,
        signal_name=str(signal_binding_name),
        node_runtime_id_int=int(node_type_id_int),
        source_ref_node_def_id_int=source_ref_node_def_id_int,
        composite_pin_index_int=meta_composite_pin_index_int,
    )
    _patch_signal_meta_node_records_inplace(
        records=records,
        signal_binding_role=str(signal_binding_role),
        node_runtime_id_int=int(node_type_id_int),
        keep_param_pin_composite_pin_index=bool(should_write_composite_pin_index),
    )

