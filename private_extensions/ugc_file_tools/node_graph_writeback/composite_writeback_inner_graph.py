from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from ugc_file_tools.node_graph_semantics.graph_model import (
    normalize_edges_list as _normalize_edges_list,
    normalize_nodes_list as _normalize_nodes_list,
)
from ugc_file_tools.node_graph_semantics.layout import (
    build_pos_transform as _build_pos_transform,
    sort_graph_nodes_for_stable_ids as _sort_graph_nodes_for_stable_ids,
)
from ugc_file_tools.node_graph_semantics.type_inference import (
    infer_output_port_type_by_src_node_and_port as _infer_output_port_type_by_src_node_and_port,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_field_map, parse_binary_data_hex_text
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_declared_generic_port_type as _is_declared_generic_port_type,
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
)
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import get_port_type_text as _get_port_type_text
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server_empty_for_dict_kv as _build_var_base_message_server_empty_for_dict_kv,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)
from ugc_file_tools.node_graph_semantics.dict_kv_types import (
    try_resolve_dict_kv_var_types_from_type_text as _try_resolve_dict_kv_var_types_from_type_text,
)

from .constants_writeback import apply_input_constants_and_outparam_types
from .edges_writeback import write_edges_inplace
from .node_build import _build_nodes_list_from_templates
from .node_index import _build_graph_node_id_maps, _resolve_signal_specific_type_id_from_graph_node_payload
from .composite_writeback_proto import resource_locator
from .record_codec import _build_node_pin_message, decoded_field_map_to_dump_json_message, sort_node_pin_records_inplace


# 对齐真源（编辑器保存后的复合子图）：部分“列表/字典”泛型/反射端口需要写入 ConcreteBase.indexOfConcrete，
# 否则编辑器会按默认 concrete 渲染（常见表现：列表端口类型全显示为整数列表；字典端口显示为泛型/默认字典）。
#
# 经验映射（来自 TS_列表字典写入_v1 的真源样本；用于缺少外部 ConcreteMap/TypeMappings 时的确定性落盘）：
# - 字符串列表(11) -> 1
# - 实体列表(13)   -> 2
# - GUID列表(7)    -> 3
# - 浮点数列表(10) -> 4
# - 三维向量列表(15)-> 5
# - 布尔值列表(9)  -> 6
# - 配置ID列表(22) -> 7
# - 元件ID列表(23) -> 8
# - 阵营列表(24)   -> 9
#
# 注：整数列表(8) 在样本中通常不写 indexOfConcrete（保持与真源一致）。
_LIST_VT_TO_INDEX_OF_CONCRETE: dict[int, int] = {
    11: 1,
    13: 2,
    7: 3,
    10: 4,
    15: 5,
    9: 6,
    22: 7,
    23: 8,
    24: 9,
}


def _patch_inner_node_pin_messages_inplace(
    *,
    node_title: str,
    node_def: object,
    node_payload: Mapping[str, object],
    pin_messages: list[dict[str, object]],
) -> None:
    """
    为复合子图 inner node 的 pins 补齐关键类型载体信息（仅修补已有 ConcreteBase，不引入新 pins/records）。
    - 列表：ConcreteBase.indexOfConcrete（缺失会导致编辑器渲染退化）
    - 字典：MapBase 的 K/V 类型 + ConcreteBaseValue.field_5 的类型载体（缺失会导致默认字典）
    """
    inputs_value = node_payload.get("inputs")
    inputs = [str(x) for x in inputs_value] if isinstance(inputs_value, list) else []
    for i, port_name in enumerate(inputs):
        if _is_flow_port_by_node_def(node_def=node_def, port_name=str(port_name), is_input=True):
            continue
        port_type_text = str(_get_port_type_text(node_payload, str(port_name), is_input=True) or "").strip()
        if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
            continue
        desired_vt = int(_map_server_port_type_to_var_type_id(port_type_text))
        pin_msg = _find_pin_message(pin_messages=pin_messages, kind=3, index=int(i))
        if pin_msg is None:
            continue
        concrete = pin_msg.get("3")
        if not (isinstance(concrete, dict) and int(concrete.get("1") or 0) == 10000):
            continue
        v110 = concrete.get("110")
        if not isinstance(v110, dict):
            continue

        if int(desired_vt) == 27:
            kv = _try_resolve_dict_kv_var_types_from_type_text(
                str(port_type_text),
                map_port_type_text_to_var_type_id=_map_server_port_type_to_var_type_id,
                reject_generic=True,
            )
            if isinstance(kv, tuple) and len(kv) == 2:
                key_vt, val_vt = int(kv[0]), int(kv[1])
                inner = _build_var_base_message_server_empty_for_dict_kv(
                    dict_key_var_type_int=int(key_vt),
                    dict_value_var_type_int=int(val_vt),
                )
                pin_msg["4"] = 27
                pin_msg["3"] = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=None)
            continue

        desired_index = _LIST_VT_TO_INDEX_OF_CONCRETE.get(int(desired_vt))
        if desired_index is None:
            continue
        if "1" not in v110:
            v110["1"] = int(desired_index)


def _is_node_pin_dump_json_message(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    # NodePin message: {1:<PinIndex>, 2:<PinIndex>, 4:<var_type?>, 3:<VarBase?>, 5:<connect?>, 7:<compositePinIndex?>}
    idx1 = obj.get("1")
    idx2 = obj.get("2")
    if not isinstance(idx1, dict):
        return False
    # 对齐真源：signal-specific runtime 的 META pin 常省略 field_2（PinIndex2）。
    # 因此这里接受 field_2 缺失的 NodePin，并在 decode 阶段补齐为与 field_1 相同的 PinIndex。
    if idx2 is not None and (not isinstance(idx2, dict)):
        return False
    if not isinstance(idx1.get("1"), int):
        return False
    if isinstance(idx2, dict) and (not isinstance(idx2.get("1"), int)):
        return False
    return True


def _decode_pin_records_from_node_records(records: list[object]) -> list[dict[str, object]]:
    """
    CompositeGraph.inner_nodes[*].field_4 的真源形态是 repeated NodePin message：
    - list[ {1:PinIndex,2:PinIndex,3:VarBase/ConcreteBase,4:VarType,5:connects,...}, ... ]
    写回侧复用 NodeGraph writeback 的“records list”(binary NodePin) 来构造该字段：
    - 只挑出可解码为 NodePin 的 records
    - 统一转换为 dump-json 风格（数值键 dict）
    """
    out: list[dict[str, object]] = []
    for r in list(records):
        if not isinstance(r, str) or not r.startswith("<binary_data>"):
            continue
        raw = parse_binary_data_hex_text(str(r))
        field_map, consumed = decode_message_to_field_map(
            data_bytes=raw,
            start_offset=0,
            end_offset=len(raw),
            remaining_depth=16,
        )
        if consumed != len(raw):
            continue
        msg = decoded_field_map_to_dump_json_message(field_map)
        if _is_node_pin_dump_json_message(msg):
            # 对齐真源：某些 NodePin（典型：signal-specific runtime 的 META pin）会省略 field_2，
            # 但写回侧后续逻辑与排序更希望 “1/2” 形态稳定，因此在这里做归一化补齐。
            idx1 = msg.get("1")
            if "2" not in msg and isinstance(idx1, dict):
                msg["2"] = dict(idx1)
            out.append(msg)
    return out


def _find_pin_message(*, pin_messages: list[dict[str, object]], kind: int, index: int) -> dict[str, object] | None:
    for m in list(pin_messages):
        if not isinstance(m, dict):
            continue
        idx = m.get("1")
        if not isinstance(idx, dict):
            continue
        if int(idx.get("1") or -1) != int(kind):
            continue
        got_index = int(idx.get("2") or 0)
        if int(got_index) != int(index):
            continue
        return m
    return None


def _sort_pin_messages_inplace(pin_messages: list[dict[str, object]]) -> None:
    def _key(m: dict[str, object]) -> tuple[int, int]:
        idx = m.get("1")
        if not isinstance(idx, dict):
            return (10_000, 10_000)
        k = idx.get("1")
        i = idx.get("2")
        kind_int = int(k) if isinstance(k, int) else 10_000
        index_int = int(i) if isinstance(i, int) else 0
        return (kind_int, index_int)

    pin_messages.sort(key=_key)


def _ensure_generic_type_carrier_pins_inplace(
    *,
    node_title: str,
    node_type_id_int: int,
    node_def: object,
    node_payload: dict[str, object],
    pin_messages: list[dict[str, object]],
) -> None:
    """
    对齐真源（用户样本：局部变量设置好类型.gil）：
    - 复合子图里某些 Variant/Generic 节点（典型：获取局部变量/设置局部变量）即使没有常量/边，
      也会在 CompositeGraph.inner_nodes[*].field_4 中保留“类型载体 pin”，用于让编辑器渲染为具体类型而非泛型。

    这里按通用规则补齐：
    - declared generic 的 data input pins：kind=3(InParam)
    - declared generic 的 data output pins：kind=4(OutParam)
    """
    if not hasattr(node_def, "input_types") or not hasattr(node_def, "output_types"):
        return
    input_types = getattr(node_def, "input_types")
    output_types = getattr(node_def, "output_types")
    inputs_value = node_payload.get("inputs")
    outputs_value = node_payload.get("outputs")
    inputs = [str(x) for x in inputs_value] if isinstance(inputs_value, list) else []
    outputs = [str(x) for x in outputs_value] if isinstance(outputs_value, list) else []

    for i, port_name in enumerate(inputs):
        if _is_flow_port_by_node_def(node_def=node_def, port_name=str(port_name), is_input=True):
            continue
        declared = ""
        if isinstance(input_types, dict):
            v = input_types.get(str(port_name))
            if isinstance(v, str):
                declared = v.strip()
        if not _is_declared_generic_port_type(str(declared)):
            continue
        port_type_text = str(_get_port_type_text(node_payload, str(port_name), is_input=True) or "").strip()
        if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
            continue
        var_type_int = int(_map_server_port_type_to_var_type_id(port_type_text))
        if _find_pin_message(pin_messages=pin_messages, kind=3, index=int(i)) is not None:
            continue
        inner_empty = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
        concrete = _wrap_var_base_as_concrete_base(
            inner=inner_empty,
            index_of_concrete=_infer_index_of_concrete_for_generic_pin(
                node_title=str(node_title),
                port_name=str(port_name),
                is_input=True,
                var_type_int=int(var_type_int),
                node_type_id_int=int(node_type_id_int),
                pin_index=int(i),
            ),
        )
        pin_msg = _build_node_pin_message(kind=3, index=int(i), var_type_int=int(var_type_int), connects=None)
        pin_msg["3"] = dict(concrete)
        pin_messages.append(dict(pin_msg))

    for i, port_name in enumerate(outputs):
        if _is_flow_port_by_node_def(node_def=node_def, port_name=str(port_name), is_input=False):
            continue
        declared = ""
        if isinstance(output_types, dict):
            v = output_types.get(str(port_name))
            if isinstance(v, str):
                declared = v.strip()
        if not _is_declared_generic_port_type(str(declared)):
            continue
        port_type_text = str(_get_port_type_text(node_payload, str(port_name), is_input=False) or "").strip()
        if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
            continue
        var_type_int = int(_map_server_port_type_to_var_type_id(port_type_text))
        if _find_pin_message(pin_messages=pin_messages, kind=4, index=int(i)) is not None:
            continue
        inner_empty = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
        concrete = _wrap_var_base_as_concrete_base(
            inner=inner_empty,
            index_of_concrete=_infer_index_of_concrete_for_generic_pin(
                node_title=str(node_title),
                port_name=str(port_name),
                is_input=False,
                var_type_int=int(var_type_int),
                node_type_id_int=int(node_type_id_int),
                pin_index=int(i),
            ),
        )
        pin_msg = _build_node_pin_message(kind=4, index=int(i), var_type_int=int(var_type_int), connects=None)
        pin_msg["3"] = dict(concrete)
        pin_messages.append(dict(pin_msg))

    _sort_pin_messages_inplace(pin_messages)


def _build_composite_inner_node(
    *,
    node_id_int: int,
    shell_type_id_int: int,
    kernel_type_id_int: int,
    pin_messages: list[dict[str, object]],
    x: float | None,
    y: float | None,
    signal_index_int: int | None,
) -> dict[str, object]:
    def _resource_locator_kind_for_runtime_id(runtime_id_int: int) -> int:
        # 对齐 node_property._build_server_node_property_binary_text：
        # - builtin 节点：kind=22000
        # - 自定义 node_def（0x4000/0x4080/0x6000/0x6080 前缀）：kind=22001
        scope_prefix = int(runtime_id_int) & int(0xFF800000)
        return 22001 if scope_prefix in {0x40000000, 0x40800000, 0x60000000, 0x60800000} else 22000

    node: dict[str, object] = {
        "1": int(node_id_int),
        "2": resource_locator(
            origin=10001,
            category=20000,
            kind=int(_resource_locator_kind_for_runtime_id(int(shell_type_id_int))),
            runtime_id=int(shell_type_id_int),
        ),
        "3": resource_locator(
            origin=10001,
            category=20000,
            kind=int(_resource_locator_kind_for_runtime_id(int(kernel_type_id_int))),
            runtime_id=int(kernel_type_id_int),
        ),
        "4": list(pin_messages),
    }
    if isinstance(x, (int, float)):
        node["5"] = float(x)
    if isinstance(y, (int, float)):
        node["6"] = float(y)
    if isinstance(signal_index_int, int):
        node["9"] = int(signal_index_int)
    return node


def _try_extract_runtime_id_from_node_property_text(node_property_text: object) -> int | None:
    """
    NodeProperty(binary) 中包含 runtime_id（decoded.field_5）。
    - 对 NodeGraph：node['2']=generic NodeProperty，node['3']=concrete NodeProperty（经 stage_runtime_id 写回）
    - 对 CompositeGraph：我们会把上述 runtime_id 映射到 resource_locator.runtime_id
    """
    if not isinstance(node_property_text, str) or not node_property_text.startswith("<binary_data>"):
        return None
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(str(node_property_text)))
    if not isinstance(decoded, dict):
        return None
    v = decoded.get("field_5")
    if isinstance(v, int) and int(v) > 0:
        return int(v)
    inner = v.get("int") if isinstance(v, dict) else None
    if isinstance(inner, int) and int(inner) > 0:
        return int(inner)
    return None


def _try_resolve_signal_specific_type_id_for_inner_node(
    *,
    node_title: str,
    node_payload: Mapping[str, object],
    signal_maps: Any,
) -> int | None:
    """
    对齐真源：当信号节点满足“静态绑定”（信号名为字符串常量且无 data 入边）且 base 映射可用时，
    其 inner node 的 shell/kernel runtime_id 都应写为 signal-specific id（send/listen/server id）。

    若只写 kernel 为 signal-specific，而 shell 仍为通用节点（300000/300001/300002），
    编辑器会按通用端口表解释动态端口，导致“信号引用存在但动态端口索引错位”。
    """
    payload_dict = dict(node_payload) if isinstance(node_payload, Mapping) else {}
    resolved = _resolve_signal_specific_type_id_from_graph_node_payload(
        node_title=str(node_title),
        node_payload=payload_dict,
        signal_send_node_def_id_by_signal_name=getattr(signal_maps, "send_node_def_id_by_signal_name", None),
        signal_listen_node_def_id_by_signal_name=getattr(signal_maps, "listen_node_def_id_by_signal_name", None),
        signal_server_node_def_id_by_signal_name=getattr(signal_maps, "server_send_node_def_id_by_signal_name", None),
    )
    return int(resolved) if isinstance(resolved, int) and int(resolved) > 0 else None


def build_inner_graph_nodes_for_composite(
    *,
    composite_graph_model: Any,
    graph_json_object: Dict[str, Any],
    graph_scope: str,
    graph_generater_root: Path,
    mapping_path: Path,
    node_defs_by_name: Dict[str, Any],
    signal_maps: Any,
    graph_variable_type_text_by_name: Dict[str, str],
    record_id_by_node_type_id_and_inparam_index: Dict[int, Dict[int, int]],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, int]]:
    nodes = _normalize_nodes_list(composite_graph_model)
    if not nodes:
        raise ValueError("复合节点子图 nodes 为空")
    sorted_nodes = _sort_graph_nodes_for_stable_ids(nodes)
    transform_pos = _build_pos_transform(graph_json_object=graph_json_object, template_entry={}, sorted_nodes=sorted_nodes)

    from .type_id_map import build_node_def_key_to_type_id, build_node_name_to_type_id

    name_to_type_id = build_node_name_to_type_id(mapping_path=Path(mapping_path), scope=str(graph_scope))
    node_def_key_to_type_id = build_node_def_key_to_type_id(
        mapping_path=Path(mapping_path),
        scope=str(graph_scope),
        graph_generater_root=Path(graph_generater_root),
    )

    (
        node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id,
        node_title_by_graph_node_id,
        graph_node_by_graph_node_id,
    ) = _build_graph_node_id_maps(
        sorted_nodes=sorted_nodes,
        name_to_type_id=name_to_type_id,
        node_def_key_to_type_id=node_def_key_to_type_id,
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        prefer_signal_specific_type_id=False,
    )

    edges = _normalize_edges_list(composite_graph_model)
    inferred_output_port_type_by_src_node_and_port = _infer_output_port_type_by_src_node_and_port(
        edges=edges,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
    )

    new_nodes_list, node_object_by_node_id_int, _missing = _build_nodes_list_from_templates(
        sorted_nodes=sorted_nodes,
        transform_pos=transform_pos,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_template_by_type_id={},
        inferred_output_port_type_by_src_node_and_port=inferred_output_port_type_by_src_node_and_port,
    )

    apply_input_constants_and_outparam_types(
        sorted_nodes=sorted_nodes,
        edges=edges,
        node_defs_by_name=node_defs_by_name,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_object_by_node_id_int=node_object_by_node_id_int,
        outparam_record_template_by_type_id_and_index_and_var_type={},
        record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
        signal_send_node_def_id_by_signal_name=signal_maps.send_node_def_id_by_signal_name,
        signal_listen_node_def_id_by_signal_name=signal_maps.listen_node_def_id_by_signal_name,
        signal_server_send_node_def_id_by_signal_name=signal_maps.server_send_node_def_id_by_signal_name,
        signal_send_signal_name_port_index_by_signal_name=signal_maps.send_signal_name_port_index_by_signal_name,
        signal_send_param_port_indices_by_signal_name=signal_maps.send_param_port_indices_by_signal_name,
        signal_listen_signal_name_port_index_by_signal_name=signal_maps.listen_signal_name_port_index_by_signal_name,
        signal_listen_param_port_indices_by_signal_name=signal_maps.listen_param_port_indices_by_signal_name,
        signal_server_send_signal_name_port_index_by_signal_name=signal_maps.server_send_signal_name_port_index_by_signal_name,
        signal_server_send_param_port_indices_by_signal_name=signal_maps.server_send_param_port_indices_by_signal_name,
        signal_param_var_type_ids_by_signal_name=signal_maps.param_var_type_ids_by_signal_name,
        signal_index_by_signal_name=signal_maps.signal_index_by_signal_name,
        graph_scope=str(graph_scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
    )

    write_edges_inplace(
        edges=edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        data_link_record_template_by_dst_type_id_and_slot_index={},
        record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
        graph_scope=str(graph_scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
        signal_send_signal_name_port_index_by_signal_name=signal_maps.send_signal_name_port_index_by_signal_name,
        signal_listen_signal_name_port_index_by_signal_name=signal_maps.listen_signal_name_port_index_by_signal_name,
        signal_server_send_signal_name_port_index_by_signal_name=signal_maps.server_send_signal_name_port_index_by_signal_name,
        signal_send_param_port_indices_by_signal_name=signal_maps.send_param_port_indices_by_signal_name,
        signal_listen_param_port_indices_by_signal_name=signal_maps.listen_param_port_indices_by_signal_name,
        signal_server_send_param_port_indices_by_signal_name=signal_maps.server_send_param_port_indices_by_signal_name,
        signal_param_var_type_ids_by_signal_name=signal_maps.param_var_type_ids_by_signal_name,
    )

    for node_obj in list(new_nodes_list):
        if isinstance(node_obj, dict):
            sort_node_pin_records_inplace(node_obj)

    # === NodeGraph records(list[binary NodePin]) → CompositeGraph.inner_nodes(list[Node + repeated NodePin message]) ===
    # 参考真源（用户样本：局部变量设置好类型.gil）：CompositeGraph 中每个 inner node 的 field_4 是 repeated NodePin，
    # 而不是单个 pin message dict。
    #
    # 这里复用 NodeGraph writeback 已生成的 records，并将其中的 NodePin records 解码为 dump-json message。
    id_to_graph_node_id: dict[int, str] = {int(v): str(k) for k, v in node_id_int_by_graph_node_id.items()}
    composite_nodes: list[dict[str, object]] = []
    for node_obj in list(new_nodes_list):
        if not isinstance(node_obj, dict):
            continue
        node_ids = node_obj.get("1")
        node_id_int = int(node_ids[0]) if isinstance(node_ids, list) and node_ids and isinstance(node_ids[0], int) else None
        if not isinstance(node_id_int, int):
            continue
        graph_node_id = id_to_graph_node_id.get(int(node_id_int))
        if not graph_node_id:
            continue
        node_payload = graph_node_by_graph_node_id.get(str(graph_node_id))
        if not isinstance(node_payload, dict):
            continue
        title = str(node_payload.get("title") or "").strip()

        signal_specific_type_id_int = _try_resolve_signal_specific_type_id_for_inner_node(
            node_title=str(title),
            node_payload=dict(node_payload),
            signal_maps=signal_maps,
        )
        # kernel type id：优先取 stage_runtime_id 写回后的 concrete runtime_id（node['3'] NodeProperty.field_5）
        kernel_type_id_int = int(_try_extract_runtime_id_from_node_property_text(node_obj.get("3")) or 0)
        if kernel_type_id_int <= 0:
            kernel_type_id_int = int(node_type_id_by_graph_node_id.get(str(graph_node_id)) or 0)
        if kernel_type_id_int <= 0:
            continue
        if isinstance(signal_specific_type_id_int, int) and int(signal_specific_type_id_int) > 0:
            kernel_type_id_int = int(signal_specific_type_id_int)

        # shell type id：优先用 node_def_ref.key 的映射；回退 title 映射；再回退 kernel（避免缺映射直接崩）
        node_def_ref = node_payload.get("node_def_ref")
        node_def_key = str(node_def_ref.get("key") or "").strip() if isinstance(node_def_ref, dict) else ""
        shell_type_id_int = int(node_def_key_to_type_id.get(node_def_key) or 0) if node_def_key else 0
        if shell_type_id_int <= 0:
            shell_type_id_int = int(name_to_type_id.get(title) or 0)
        if isinstance(signal_specific_type_id_int, int) and int(signal_specific_type_id_int) > 0:
            # 关键：信号节点必须写成 signal-specific runtime_id（shell/kernel 对齐），否则动态端口会错位。
            shell_type_id_int = int(signal_specific_type_id_int)
        elif shell_type_id_int <= 0:
            shell_type_id_int = int(kernel_type_id_int)

        node_def = node_defs_by_name.get(str(title))
        if node_def is None:
            # 复合子图 title 应可在 node_defs_by_name 命中；缺失说明上游语义映射不一致
            raise KeyError(f"复合子图节点未找到 node_def：title={title!r}")

        pin_messages = _decode_pin_records_from_node_records(
            node_obj.get("4") if isinstance(node_obj.get("4"), list) else []
        )
        _ensure_generic_type_carrier_pins_inplace(
            node_title=str(title),
            node_type_id_int=int(kernel_type_id_int),
            node_def=node_def,
            node_payload=node_payload,
            pin_messages=pin_messages,
        )
        _patch_inner_node_pin_messages_inplace(
            node_title=str(title),
            node_def=node_def,
            node_payload=node_payload,
            pin_messages=pin_messages,
        )
        signal_index_int = node_obj.get("9") if isinstance(node_obj.get("9"), int) else None
        composite_nodes.append(
            _build_composite_inner_node(
                node_id_int=int(node_id_int),
                shell_type_id_int=int(shell_type_id_int),
                kernel_type_id_int=int(kernel_type_id_int),
                pin_messages=list(pin_messages),
                x=node_obj.get("5") if isinstance(node_obj.get("5"), (int, float)) else None,
                y=node_obj.get("6") if isinstance(node_obj.get("6"), (int, float)) else None,
                signal_index_int=(int(signal_index_int) if isinstance(signal_index_int, int) else None),
            )
        )

    return (
        list(composite_nodes),
        dict(node_id_int_by_graph_node_id),
        dict(graph_node_by_graph_node_id),
        dict(node_title_by_graph_node_id),
        dict(node_type_id_by_graph_node_id),
    )


__all__ = ["build_inner_graph_nodes_for_composite"]

