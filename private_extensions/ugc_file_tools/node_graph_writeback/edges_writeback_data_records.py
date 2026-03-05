from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    encode_message,
    format_binary_data_hex_text,
    parse_binary_data_hex_text,
)
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server_empty_for_dict_kv as _build_var_base_message_server_empty_for_dict_kv,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    build_var_base_message_server_empty_list_value as _build_var_base_message_server_empty_list_value,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from .record_codec import (
    _build_node_pin_message,
    _decoded_field_map_to_dump_json_message,
    _ensure_int_node,
    _extract_nested_int,
    _set_data_record_src_outparam_index,
    _set_data_record_src_port_index,
)


def _strip_zero_field2_in_pin_index_messages_inplace(value: Any) -> None:
    """
    编辑器/真源兼容：PinIndex message 中当 index==0 时，通常应省略 field_2。

    背景：
    - 模板克隆/就地 patch 模式会尽量复用模板 record 的 pin_index 壳；
    - 部分模板可能显式写入 pin_index.field_2=0；
    - 已知这会导致部分 data-link 在编辑器中被忽略，表现为“端口无连线”（尤其是 pin_index=0 的输入端口）。

    本函数会递归遍历 dump-json message（numeric keys），将形如 `{ "1": <kind>, "2": 0 }`
    的 pin_index message 规范化为 `{ "1": <kind> }`。
    """

    def _is_pin_index_message(obj: Dict[str, Any]) -> bool:
        # pin index message 的最小形态：{"1": kind_int, ("2": index_int)?}
        if "1" not in obj:
            return False
        if any(k not in {"1", "2"} for k in obj.keys()):
            return False
        return isinstance(obj.get("1"), int) and (("2" not in obj) or isinstance(obj.get("2"), int))

    if isinstance(value, list):
        for item in list(value):
            _strip_zero_field2_in_pin_index_messages_inplace(item)
        return

    if isinstance(value, dict):
        if _is_pin_index_message(value) and value.get("2") == 0:
            value.pop("2", None)
        for v in list(value.values()):
            _strip_zero_field2_in_pin_index_messages_inplace(v)
        return


def find_existing_unconnected_inparam_record(
    *,
    records: List[Any],
    dst_shell_index: int,
) -> Tuple[Optional[int], Optional[Dict[str, Any]]]:
    existing_record_index: Optional[int] = None
    existing_decoded: Optional[Dict[str, Any]] = None
    for i, record in enumerate(list(records)):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded0 = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded0, dict):
            continue
        kind0 = _extract_nested_int(decoded0, ["field_1", "message", "field_1"])
        idx0 = _extract_nested_int(decoded0, ["field_1", "message", "field_2"])
        idx0_int = 0 if idx0 is None else int(idx0)
        if int(kind0 or -1) != 3:
            continue
        if idx0_int != int(dst_shell_index):
            continue
        # 已是连线 pin：不覆盖（避免隐式覆写同一输入的连接）
        if "field_5" in decoded0:
            continue
        existing_record_index = int(i)
        existing_decoded = decoded0
        break
    return existing_record_index, existing_decoded


def patch_existing_unconnected_inparam_record_inplace(
    *,
    records: List[Any],
    existing_record_index: int,
    existing_decoded: Dict[str, Any],
    connect_msg: Dict[str, Any],
    dst_title: str,
    dst_port: str,
    dst_var_type_int: int,
    dst_type_id_int: int,
    dst_shell_index: int,
    should_wrap_as_concrete: bool,
    forced_index: Optional[int],
    signal_param_composite_pin_index: Optional[int],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]],
    dict_kv_vts: Optional[Tuple[int, int]],
) -> None:
    dump_msg = _decoded_field_map_to_dump_json_message(existing_decoded)
    if isinstance(dst_var_type_int, int):
        dump_msg["4"] = int(dst_var_type_int)
        if int(dst_var_type_int) != 27:
            # 与 GIA 一致：连接 pin 的默认值结构按“解析后的最终 VarType”重建，
            # 不沿用模板残留（例如 GUID 模板导致整数端口显示错误）。
            inner_empty = _build_var_base_message_server_empty(var_type_int=int(dst_var_type_int))
            dump_msg["3"] = (
                _wrap_var_base_as_concrete_base(
                    inner=inner_empty,
                    index_of_concrete=(
                        int(forced_index)
                        if isinstance(forced_index, int)
                        else _infer_index_of_concrete_for_generic_pin(
                            node_title=str(dst_title),
                            port_name=str(dst_port),
                            is_input=True,
                            var_type_int=int(dst_var_type_int),
                            node_type_id_int=int(dst_type_id_int),
                            pin_index=int(dst_shell_index),
                        )
                    ),
                )
                if bool(should_wrap_as_concrete)
                else inner_empty
            )
    dump_msg["5"] = dict(connect_msg)
    if isinstance(signal_param_composite_pin_index, int):
        dump_msg["7"] = int(signal_param_composite_pin_index)
    elif record_id_by_node_type_id_and_inparam_index is not None and "7" not in dump_msg:
        record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(dst_type_id_int)) or {}).get(int(dst_shell_index))
        if isinstance(record_id_int, int) and int(record_id_int) > 0:
            dump_msg["7"] = int(record_id_int)
    # 字典入参：补齐/覆盖 MapBase 的 key/value 类型信息（否则 UI 可能显示为“实体-实体字典”并收敛上游类型）
    vt0 = dump_msg.get("4")
    if isinstance(vt0, int) and int(vt0) == 27 and isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2:
        key_vt, val_vt = int(dict_kv_vts[0]), int(dict_kv_vts[1])
        inner = _build_var_base_message_server_empty_for_dict_kv(
            dict_key_var_type_int=int(key_vt),
            dict_value_var_type_int=int(val_vt),
        )
        dump_msg["3"] = _wrap_var_base_as_concrete_base(
            inner=inner,
            index_of_concrete=(
                int(forced_index)
                if isinstance(forced_index, int)
                else _infer_index_of_concrete_for_generic_pin(
                    node_title=str(dst_title),
                    port_name=str(dst_port),
                    is_input=True,
                    var_type_int=27,
                    node_type_id_int=int(dst_type_id_int),
                    pin_index=int(dst_shell_index),
                )
            ),
        )

    # 真源对齐（有错的节点挑出来.gil）：创建元件组 的『整数列表』入参在连线时也需要显式空 ArrayBase
    # （否则编辑器端可能把该端口当作未初始化列表，导致类型/显示异常）。
    if (
        str(dst_title) == "创建元件组"
        and isinstance(dst_var_type_int, int)
        and int(dst_var_type_int) in (7, 8, 9, 10, 11, 13, 15, 22, 23, 24, 26)
        and "3" not in dump_msg
    ):
        dump_msg["3"] = _build_var_base_message_server_empty_list_value(var_type_int=int(dst_var_type_int))

    # 编辑器兼容：pin_index.index==0 时应省略 field_2，否则部分节点的 data-link 可能被忽略（表现为“端口无连线”）。
    _strip_zero_field2_in_pin_index_messages_inplace(dump_msg)

    records[int(existing_record_index)] = format_binary_data_hex_text(encode_message(dump_msg))


def build_minimal_data_link_record_text(
    *,
    dst_title: str,
    dst_port: str,
    dst_type_id_int: int,
    dst_shell_index: int,
    dst_kernel_index: int,
    dst_var_type_int: Optional[int],
    connect_msg: Dict[str, Any],
    should_wrap_as_concrete: bool,
    forced_index: Optional[int],
    signal_param_composite_pin_index: Optional[int],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]],
    dict_kv_vts: Optional[Tuple[int, int]],
) -> str:
    index2 = None
    if str(dst_title) == "修改结构体":
        index2 = 0 if int(dst_shell_index) <= 0 else int(dst_shell_index) - 1
    elif isinstance(signal_param_composite_pin_index, int):
        # 信号 META binding 参数端口：必须显式写入 kernel index（即便与 shell 相同），禁止依赖“省略 field_2 的默认 0”。
        index2 = int(dst_kernel_index)
    elif int(dst_kernel_index) != int(dst_shell_index):
        index2 = int(dst_kernel_index)
    pin_msg = _build_node_pin_message(
        kind=3,  # InParam
        index=int(dst_shell_index),
        index2=(int(index2) if isinstance(index2, int) else None),
        var_type_int=(int(dst_var_type_int) if isinstance(dst_var_type_int, int) else None),
        connects=[connect_msg],
    )
    if isinstance(signal_param_composite_pin_index, int):
        pin_msg["7"] = int(signal_param_composite_pin_index)
    elif record_id_by_node_type_id_and_inparam_index is not None:
        record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(dst_type_id_int)) or {}).get(int(dst_shell_index))
        if isinstance(record_id_int, int) and int(record_id_int) > 0:
            pin_msg["7"] = int(record_id_int)
    # 字典入参：若能确定 key/value 类型，则补齐最小 ConcreteBase(MapBase) 表达字典 key/value
    if isinstance(dst_var_type_int, int) and int(dst_var_type_int) == 27 and isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2:
        key_vt, val_vt = int(dict_kv_vts[0]), int(dict_kv_vts[1])
        inner = _build_var_base_message_server_empty_for_dict_kv(
            dict_key_var_type_int=int(key_vt),
            dict_value_var_type_int=int(val_vt),
        )
        pin_msg["3"] = _wrap_var_base_as_concrete_base(
            inner=inner,
            index_of_concrete=(
                int(forced_index)
                if isinstance(forced_index, int)
                else _infer_index_of_concrete_for_generic_pin(
                    node_title=str(dst_title),
                    port_name=str(dst_port),
                    is_input=True,
                    var_type_int=27,
                    node_type_id_int=int(dst_type_id_int),
                    pin_index=int(dst_shell_index),
                )
            ),
        )
    # 反射/泛型入参：即便已连线，也需要写 ConcreteBase + indexOfConcrete 表达“实例化到具体 T”
    if (
        bool(should_wrap_as_concrete)
        and isinstance(dst_var_type_int, int)
        and int(dst_var_type_int) > 0
        and int(dst_var_type_int) != 27
        and "3" not in pin_msg
    ):
        inner_empty = _build_var_base_message_server_empty(var_type_int=int(dst_var_type_int))
        pin_msg["3"] = _wrap_var_base_as_concrete_base(
            inner=inner_empty,
            index_of_concrete=(
                int(forced_index)
                if isinstance(forced_index, int)
                else _infer_index_of_concrete_for_generic_pin(
                    node_title=str(dst_title),
                    port_name=str(dst_port),
                    is_input=True,
                    var_type_int=int(dst_var_type_int),
                    node_type_id_int=int(dst_type_id_int),
                    pin_index=int(dst_shell_index),
                )
            ),
        )
    # 创建元件组：列表入参连线也需要显式空 ArrayBase
    if (
        str(dst_title) == "创建元件组"
        and isinstance(dst_var_type_int, int)
        and int(dst_var_type_int) in (7, 8, 9, 10, 11, 13, 15, 22, 23, 24, 26)
        and "3" not in pin_msg
    ):
        pin_msg["3"] = _build_var_base_message_server_empty_list_value(var_type_int=int(dst_var_type_int))
    return format_binary_data_hex_text(encode_message(pin_msg))


def build_template_data_link_record_text(
    *,
    template_record_text: str,
    src_node_id_int: int,
    src_shell_index: int,
    src_kernel_index: int,
    dst_title: str,
    dst_port: str,
    dst_var_type_int: Optional[int],
    dst_type_id_int: int,
    dst_shell_index: int,
    should_wrap_as_concrete: bool,
    forced_index: Optional[int],
    signal_param_composite_pin_index: Optional[int],
    dict_kv_vts: Optional[Tuple[int, int]],
) -> str:
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(template_record_text))
    if not isinstance(decoded, dict):
        raise ValueError("data record 模板 decode 结果不是 dict")
    if "field_4" not in decoded:
        raise ValueError("data record 模板不包含 field_4（期望为 data record）")

    # GIA 同口径：模板 record 只提供“结构壳”，最终类型与默认值由统一类型解析器决定。

    field_5 = decoded.get("field_5")
    if not isinstance(field_5, dict) or not isinstance(field_5.get("message"), dict):
        raise ValueError("data record 模板缺少 field_5.message")
    field_5_msg = field_5.get("message")
    if not isinstance(field_5_msg, dict):
        raise ValueError("data record 模板 field_5.message 不是 dict")

    _ensure_int_node(field_5_msg, "field_1", int(src_node_id_int))
    _set_data_record_src_port_index(field_5_msg=field_5_msg, src_port_index_int=4)
    _set_data_record_src_outparam_index(
        field_5_msg=field_5_msg,
        out_index=int(src_shell_index),
        out_kernel_index=int(src_kernel_index),
    )

    dump_json_message = _decoded_field_map_to_dump_json_message(decoded)
    if isinstance(dst_var_type_int, int):
        dump_json_message["4"] = int(dst_var_type_int)
        if int(dst_var_type_int) != 27:
            # 覆盖模板默认 VarBase，避免模板类型与解析结果不一致（例如 GUID/整数串型）。
            inner_empty = _build_var_base_message_server_empty(var_type_int=int(dst_var_type_int))
            dump_json_message["3"] = (
                _wrap_var_base_as_concrete_base(
                    inner=inner_empty,
                    index_of_concrete=(
                        int(forced_index)
                        if isinstance(forced_index, int)
                        else _infer_index_of_concrete_for_generic_pin(
                            node_title=str(dst_title),
                            port_name=str(dst_port),
                            is_input=True,
                            var_type_int=int(dst_var_type_int),
                            node_type_id_int=int(dst_type_id_int),
                            pin_index=int(dst_shell_index),
                        )
                    ),
                )
                if bool(should_wrap_as_concrete)
                else inner_empty
            )
    if isinstance(signal_param_composite_pin_index, int):
        dump_json_message["7"] = int(signal_param_composite_pin_index)
        # 信号 META binding 参数端口：确保写入 pin_index2(kernel) 与 shell 一致（并显式落盘）。
        # 模板 record 可能缺失该字段，若省略则会默认成 0，导致端口对齐漂移。
        dump_json_message["2"] = {"1": 3, "2": int(dst_shell_index)}
    # 字典入参：若能确定 key/value 类型，则强制覆盖模板中的默认值（常见为 entity-entity）
    vt_template = dump_json_message.get("4")
    if isinstance(vt_template, int) and int(vt_template) == 27 and isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2:
        key_vt, val_vt = int(dict_kv_vts[0]), int(dict_kv_vts[1])
        inner = _build_var_base_message_server_empty_for_dict_kv(
            dict_key_var_type_int=int(key_vt),
            dict_value_var_type_int=int(val_vt),
        )
        dump_json_message["3"] = _wrap_var_base_as_concrete_base(
            inner=inner,
            index_of_concrete=(
                int(forced_index)
                if isinstance(forced_index, int)
                else _infer_index_of_concrete_for_generic_pin(
                    node_title=str(dst_title),
                    port_name=str(dst_port),
                    is_input=True,
                    var_type_int=27,
                    node_type_id_int=int(dst_type_id_int),
                    pin_index=int(dst_shell_index),
                )
            ),
        )

    # 创建元件组：列表入参连线也需要显式空 ArrayBase（模板可能缺失 field_3）
    if (
        str(dst_title) == "创建元件组"
        and isinstance(vt_template, int)
        and int(vt_template) in (7, 8, 9, 10, 11, 13, 15, 22, 23, 24, 26)
        and "3" not in dump_json_message
    ):
        dump_json_message["3"] = _build_var_base_message_server_empty_list_value(var_type_int=int(vt_template))

    # 编辑器兼容：模板 record 可能显式写入 pin_index.field_2=0；写回前统一规范化为“省略 field_2”。
    _strip_zero_field2_in_pin_index_messages_inplace(dump_json_message)

    return format_binary_data_hex_text(encode_message(dump_json_message))

