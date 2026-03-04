from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    is_declared_generic_port_type as _is_declared_generic_port_type,
    resolve_input_port_name_for_type as _resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.nep_type_expr import (
    is_nep_reflection_type_expr as _is_nep_reflection_type_expr,
)
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
    map_inparam_pin_index_for_node as _map_inparam_pin_index_for_node,
)
from ugc_file_tools.node_graph_semantics.type_binding_plan import (
    build_node_type_binding_plan as _build_node_type_binding_plan,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_empty_for_dict_kv as _build_var_base_message_server_empty_for_dict_kv,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    build_var_base_message_server_empty_list_value as _build_var_base_message_server_empty_list_value,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    try_map_server_dict_type_text_to_kv_var_types as _try_map_server_dict_type_text_to_kv_var_types,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)
from ugc_file_tools.contracts.signal_meta_binding import (
    resolve_signal_meta_binding_param_pin_indices as _resolve_signal_meta_binding_param_pin_indices,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.node_data_index import load_node_entry_by_id_map as _load_node_entry_by_id_map
from ugc_file_tools.node_data_index import resolve_default_node_data_index_path as _resolve_default_node_data_index_path

from .edges_writeback_common import resolve_node_def_for_graph_node
from .writeback_feature_flags import is_writeback_feature_enabled
from .edges_writeback_data_records import (
    build_minimal_data_link_record_text,
    build_template_data_link_record_text,
    find_existing_unconnected_inparam_record,
    patch_existing_unconnected_inparam_record_inplace,
)
from .node_editor_pack import _find_nep_pin_def, _load_node_editor_pack_nodes_by_id, resolve_node_editor_pack_pin_indices
from .record_codec import (
    _build_node_connection_message,
    _ensure_record_list,
    _build_node_pin_message,
    _decoded_field_map_to_dump_json_message,
    _extract_nested_int,
)


def _ensure_inparam_bool_true_record(
    *,
    records: List[Any],
    pin_index: int,
    node_type_id_int: int,
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]],
) -> None:
    """
    确保存在一个 InParam(pin_index) 的 bool=True 常量 record（用于修改结构体的『是否修改_*』开关）。

    说明：
    - 优先 patch 既有 record（保留 field_1/field_2 的真源 pin 映射，以及 field_7(record_id)）；
    - 若不存在则按最小 schema 合成，并尽量补齐 field_7。
    """
    record_id_int = None
    if record_id_by_node_type_id_and_inparam_index is not None:
        record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(node_type_id_int)) or {}).get(int(pin_index))

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
        if int(kind or -1) != 3:
            continue
        if idx_int != int(pin_index):
            continue
        if "field_5" in decoded:
            continue
        existing_record_index = int(i)
        existing_decoded = decoded
        break

    bool_var_base = _build_var_base_message_server(var_type_int=4, value=True)

    if isinstance(existing_record_index, int) and isinstance(existing_decoded, dict):
        dump_msg = _decoded_field_map_to_dump_json_message(existing_decoded)
        dump_msg["4"] = 4
        dump_msg["3"] = dict(bool_var_base)
        if isinstance(record_id_int, int) and int(record_id_int) > 0 and "7" not in dump_msg:
            dump_msg["7"] = int(record_id_int)
        records[int(existing_record_index)] = format_binary_data_hex_text(encode_message(dump_msg))
        return

    index2 = 0 if int(pin_index) <= 0 else int(pin_index) - 1
    pin_msg = _build_node_pin_message(kind=3, index=int(pin_index), index2=int(index2), var_type_int=4, connects=None)
    pin_msg["3"] = dict(bool_var_base)
    if isinstance(record_id_int, int) and int(record_id_int) > 0:
        pin_msg["7"] = int(record_id_int)
    records.append(format_binary_data_hex_text(encode_message(pin_msg)))


def write_data_edges_inplace(
    *,
    data_edges: List[Tuple[str, str, str, str]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_title_by_graph_node_id: Dict[str, str],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    data_link_record_template_by_dst_type_id_and_slot_index: Dict[int, Dict[int, str]],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]],
    graph_scope: str = "server",
    graph_variable_type_text_by_name: Optional[Dict[str, str]] = None,
    inferred_out_type_text: Optional[Dict[Tuple[str, str], str]] = None,
    inferred_in_type_text: Optional[Dict[Tuple[str, str], str]] = None,
    signal_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_listen_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_server_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_param_var_type_ids_by_signal_name: Optional[Dict[str, List[int]]] = None,
) -> int:
    added_data_edges = 0
    graph_variable_type_text_map = dict(graph_variable_type_text_by_name or {})
    inferred_out_type_text_map = dict(inferred_out_type_text or {})
    inferred_in_type_text_map = dict(inferred_in_type_text or {})
    nep_nodes_by_id = _load_node_editor_pack_nodes_by_id()
    node_entry_by_id = _load_node_entry_by_id_map(_resolve_default_node_data_index_path())
    # Writer 内部缓存：同一节点在多条边中会重复用到 dict KV / 拼装字典 K/V 的决策。
    type_plan_by_dst_node_id: Dict[str, Any] = {}
    send_signal_nodes_with_signal_name_in_edge: set[str] = set()
    listen_signal_nodes_with_signal_name_in_edge: set[str] = set()
    server_send_signal_nodes_with_signal_name_in_edge: set[str] = set()
    for _src_node_id0, _src_port0, dst_node_id0, dst_port0 in list(data_edges):
        if str(dst_port0) != "信号名":
            continue
        dst_title0 = str(node_title_by_graph_node_id.get(str(dst_node_id0), "") or "")
        dst_type_id0 = node_type_id_by_graph_node_id.get(str(dst_node_id0))
        if dst_title0 == "发送信号" or (isinstance(dst_type_id0, int) and int(dst_type_id0) == 300000):
            send_signal_nodes_with_signal_name_in_edge.add(str(dst_node_id0))
        if dst_title0 == "监听信号" or (isinstance(dst_type_id0, int) and int(dst_type_id0) == 300001):
            listen_signal_nodes_with_signal_name_in_edge.add(str(dst_node_id0))
        if dst_title0 in {"发送信号到服务端", "向服务器节点图发送信号"} or (
            isinstance(dst_type_id0, int) and int(dst_type_id0) == 300002
        ):
            server_send_signal_nodes_with_signal_name_in_edge.add(str(dst_node_id0))

    for src_node_id, src_port, dst_node_id, dst_port in list(data_edges):
        src_node_id_int = node_id_int_by_graph_node_id.get(src_node_id)
        dst_node_id_int = node_id_int_by_graph_node_id.get(dst_node_id)
        if not isinstance(src_node_id_int, int) or not isinstance(dst_node_id_int, int):
            continue

        dst_type_id_int = int(node_type_id_by_graph_node_id[dst_node_id])

        dst_node_payload = graph_node_by_graph_node_id.get(dst_node_id)
        if not isinstance(dst_node_payload, dict):
            raise ValueError(f"graph_model 缺少 dst_node: {dst_node_id!r}")
        dst_inputs = dst_node_payload.get("inputs")
        if not isinstance(dst_inputs, list):
            raise ValueError(f"dst_node.inputs 不是 list: {dst_node_id!r}")
        dst_title = node_title_by_graph_node_id.get(dst_node_id, "")
        dst_def = resolve_node_def_for_graph_node(
            node_id=str(dst_node_id),
            node_title=str(dst_title),
            node_payload=dst_node_payload,
            node_defs_by_name=node_defs_by_name,
        )
        if dst_def is None:
            raise ValueError(f"data edge 缺少 dst NodeDef: {dst_title!r}")
        dst_data_inputs = [
            str(p) for p in dst_inputs if not _is_flow_port_by_node_def(node_def=dst_def, port_name=str(p), is_input=True)
        ]
        is_send_signal_node = bool(int(dst_type_id_int) == 300000 or str(dst_title) == "发送信号")
        is_listen_signal_node = bool(int(dst_type_id_int) == 300001 or str(dst_title) == "监听信号")
        is_server_send_signal_node = bool(
            int(dst_type_id_int) == 300002 or str(dst_title) in {"发送信号到服务端", "向服务器节点图发送信号"}
        )
        signal_binding_param_port_indices: Optional[List[int]] = None
        signal_binding_param_var_type_ids: Optional[List[int]] = None
        is_signal_meta_binding_node = False
        dst_input_constants = dst_node_payload.get("input_constants")
        signal_name = ""
        # 信号节点 META binding 判定：不依赖隐藏语义键 `__signal_id`。
        # 只要『信号名』端口无 data 入边且 input_constants['信号名'] 为非空字符串常量，即可视为 META binding，
        # 否则参数端口 slot 会整体偏移，且若 NEP 的 KernelIndex 形态为“固定 0”会写坏 pin_index2。
        if isinstance(dst_input_constants, dict) and "信号名" in dst_data_inputs:
            signal_name_value = dst_input_constants.get("信号名")
            if isinstance(signal_name_value, str) and str(signal_name_value).strip() != "":
                signal_name = str(signal_name_value).strip()
                if bool(is_send_signal_node) and str(dst_node_id) not in send_signal_nodes_with_signal_name_in_edge:
                    dst_data_inputs = [p for p in dst_data_inputs if p != "信号名"]
                    is_signal_meta_binding_node = True
                    if isinstance(signal_send_param_port_indices_by_signal_name, dict):
                        raw = signal_send_param_port_indices_by_signal_name.get(str(signal_name))
                        if isinstance(raw, list):
                            signal_binding_param_port_indices = [int(x) for x in raw if isinstance(x, int)]
                elif bool(is_listen_signal_node) and str(dst_node_id) not in listen_signal_nodes_with_signal_name_in_edge:
                    dst_data_inputs = [p for p in dst_data_inputs if p != "信号名"]
                    is_signal_meta_binding_node = True
                    if isinstance(signal_listen_param_port_indices_by_signal_name, dict):
                        raw = signal_listen_param_port_indices_by_signal_name.get(str(signal_name))
                        if isinstance(raw, list):
                            signal_binding_param_port_indices = [int(x) for x in raw if isinstance(x, int)]
                elif bool(is_server_send_signal_node) and str(dst_node_id) not in server_send_signal_nodes_with_signal_name_in_edge:
                    dst_data_inputs = [p for p in dst_data_inputs if p != "信号名"]
                    is_signal_meta_binding_node = True
                    if isinstance(signal_server_send_param_port_indices_by_signal_name, dict):
                        raw = signal_server_send_param_port_indices_by_signal_name.get(str(signal_name))
                        if isinstance(raw, list):
                            signal_binding_param_port_indices = [int(x) for x in raw if isinstance(x, int)]
                if bool(is_signal_meta_binding_node) and isinstance(signal_param_var_type_ids_by_signal_name, dict):
                    raw_vts = signal_param_var_type_ids_by_signal_name.get(str(signal_name))
                    if isinstance(raw_vts, list):
                        signal_binding_param_var_type_ids = [int(x) for x in raw_vts if isinstance(x, int)]
        if str(dst_port) not in dst_data_inputs:
            raise ValueError(
                f"dst_port 不在 dst_node.inputs 中：dst_node={dst_node_id!r} dst_port={dst_port!r} inputs={dst_data_inputs!r}"
            )
        dst_slot_index = int(dst_data_inputs.index(str(dst_port)))
        signal_param_composite_pin_index: Optional[int] = None
        if isinstance(signal_binding_param_port_indices, list) and 0 <= int(dst_slot_index) < len(signal_binding_param_port_indices):
            cpi = signal_binding_param_port_indices[int(dst_slot_index)]
            if isinstance(cpi, int) and int(cpi) >= 0:
                signal_param_composite_pin_index = int(cpi)
        resolved_dst_port_name = str(dst_port)
        dst_pin_fallback_index = _map_inparam_pin_index_for_node(
            node_title=str(dst_title),
            port_name=str(dst_port),
            slot_index=int(dst_slot_index),
        )
        if bool(is_signal_meta_binding_node):
            # 对齐真源 `.gil`：信号参数 pin 的 i2(index2/kernel) 与 shell index 一致（slot_index）。
            dst_shell_index, dst_kernel_index = _resolve_signal_meta_binding_param_pin_indices(
                slot_index=int(dst_slot_index)
            )
        elif int(dst_type_id_int) == 3:
            # 真源对齐：Multiple_Branches 的 InParam 索引为 0/1（shell=kernel=slot）
            dst_shell_index = int(dst_slot_index)
            dst_kernel_index = int(dst_slot_index)
        elif str(dst_title) == "拼装字典":
            # 拼装字典在存档里的可见 InParam 从 pin1 开始；
            # pin0 是内部 len，不对应 GraphModel 的键值端口。
            dst_shell_index = int(dst_pin_fallback_index)
            dst_kernel_index = int(dst_pin_fallback_index)
        else:
            resolved_dst_port_name = _resolve_input_port_name_for_type(node_def=dst_def, port_name=str(dst_port))
            dst_shell_index, dst_kernel_index = resolve_node_editor_pack_pin_indices(
                node_type_id_int=int(dst_type_id_int),
                is_flow=False,
                direction="In",
                port_name=str(resolved_dst_port_name),
                ordinal=int(dst_slot_index),
                fallback_index=int(dst_pin_fallback_index),
            )

        # 兜底对齐真源：信号节点参数端口的 kernel index 必须与 shell index 一致（shell=kernel=slot）。
        # 这是跨域契约；禁止依赖 NEP 的 KernelIndex（已观测存在“固定为 0”的画像，导致写出坏 record）。
        if (bool(is_send_signal_node) or bool(is_listen_signal_node) or bool(is_server_send_signal_node)) and str(dst_port) != "信号名":
            dst_kernel_index = int(dst_shell_index)
        should_enable_struct_modify_field = (
            str(dst_title) == "修改结构体"
            and str(dst_port) not in {"结构体名", "结构体实例"}
            and (not str(dst_port).startswith("__"))
        )

        # 与 GIA 导出同口径：端口最终 VarType 统一由 _resolve_server_var_type_int_for_port 决定。
        # 同时保留端口类型文本（供字典 key/value 推断）。
        dst_port_type_text = str(_get_port_type_text(dst_node_payload, str(dst_port), is_input=True) or "").strip()
        if dst_port_type_text == "":
            resolved = _resolve_input_port_name_for_type(node_def=dst_def, port_name=str(dst_port))
            dst_port_type_text = str(dst_def.get_port_type(str(resolved), is_input=True)).strip()
        # data-link 写回：dst 端口已连线时，忽略 input_constants 的字面值，
        # 避免常量兜底推断覆盖“连线已确定的类型”（典型：泛型端口 + 常量 "123" + 实际连线为字符串）。
        dst_nep_node_record = nep_nodes_by_id.get(int(dst_type_id_int))
        # 反射/泛型端口：已连线时仍需写 ConcreteBase + indexOfConcrete，否则编辑器端口收敛不稳定（尤其是 GraphVariables 节点）。
        declared_type_text = ""
        declared_map = dst_node_payload.get("input_port_declared_types")
        if isinstance(declared_map, dict):
            dt = declared_map.get(str(dst_port))
            if isinstance(dt, str):
                declared_type_text = dt.strip()
        if declared_type_text == "":
            type_dict = getattr(dst_def, "input_types", None)
            if isinstance(type_dict, dict):
                raw_dt = type_dict.get(str(resolved_dst_port_name))
                if isinstance(raw_dt, str):
                    declared_type_text = raw_dt.strip()
        is_declared_generic_input = bool(_is_declared_generic_port_type(str(declared_type_text)))

        # dict KV / 拼装字典 K/V 的“决策 Plan”与 constants_writeback 统一口径（避免两处落点分叉覆盖）。
        dst_type_plan = type_plan_by_dst_node_id.get(str(dst_node_id))
        if dst_type_plan is None:
            dst_type_plan = _build_node_type_binding_plan(
                graph_scope=str(graph_scope),
                graph_node_id=str(dst_node_id),
                node_title=str(dst_title),
                node_type_id_int=int(dst_type_id_int),
                node_payload=dst_node_payload,
                node_def=dst_def,
                data_inputs=list(dst_data_inputs),
                input_constants=(dict(dst_input_constants) if isinstance(dst_input_constants, dict) else None),
                node_entry_by_id=dict(node_entry_by_id),
                graph_variable_type_text_by_name=dict(graph_variable_type_text_map),
                inferred_in_type_text=dict(inferred_in_type_text_map),
                inferred_out_type_text=dict(inferred_out_type_text_map),
                nep_node_record=dst_nep_node_record,
                enable_t_dict_inference_from_input_value_port=bool(
                    is_writeback_feature_enabled("type_plan_t_dict_infer_from_input_value_port")
                ),
            )
            type_plan_by_dst_node_id[str(dst_node_id)] = dst_type_plan
        dst_var_type_int = int(
            _resolve_server_var_type_int_for_port(
                graph_scope=str(graph_scope),
                node_id=str(dst_node_id),
                port_name=str(dst_port),
                is_input=True,
                node_payload=dst_node_payload,
                graph_variable_type_text_by_name=graph_variable_type_text_map,
                inferred_out_type_text=inferred_out_type_text_map,
                inferred_in_type_text=inferred_in_type_text_map,
                raw_constant_value=None,
                nep_node_record=dst_nep_node_record,
                nep_port_name=str(resolved_dst_port_name),
                nep_ordinal=int(dst_slot_index),
            )
        )
        if (
            bool(is_signal_meta_binding_node)
            and (bool(is_send_signal_node) or bool(is_server_send_signal_node))
            and isinstance(signal_binding_param_var_type_ids, list)
            and 0 <= int(dst_slot_index) < len(signal_binding_param_var_type_ids)
        ):
            vt_override = signal_binding_param_var_type_ids[int(dst_slot_index)]
            if isinstance(vt_override, int) and int(vt_override) > 0:
                dst_var_type_int = int(vt_override)

        # 字典泛型节点：当 GraphModel 的 键/值 端口仍是“泛型”时，优先跟随 “字典” 端口推断到的 (K,V)。
        # 避免被 raw_constant_value 的字面值兜底推断（例如 "123" 被当作整数）覆盖，导致与 GIA/常量写回口径不一致。
        if isinstance(getattr(dst_type_plan, "dict_key_vt_for_node", None), int) and isinstance(
            getattr(dst_type_plan, "dict_value_vt_for_node", None), int
        ):
            if str(dst_port) == "键":
                dst_var_type_int = int(getattr(dst_type_plan, "dict_key_vt_for_node"))
            elif str(dst_port) == "值":
                dst_var_type_int = int(getattr(dst_type_plan, "dict_value_vt_for_node"))

        forced_index: Optional[int] = None
        forced_index_map = getattr(dst_type_plan, "forced_index_of_concrete_by_port", None)
        if isinstance(forced_index_map, dict):
            if str(dst_port) in forced_index_map:
                forced_index = forced_index_map.get(str(dst_port))
            elif str(dst_port).startswith("键") and "键" in forced_index_map:
                forced_index = forced_index_map.get("键")
            elif str(dst_port).startswith("值") and "值" in forced_index_map:
                forced_index = forced_index_map.get("值")

        nep_hit = _find_nep_pin_def(
            dst_nep_node_record,
            is_flow=False,
            direction="In",
            port_name=str(resolved_dst_port_name),
            ordinal=int(dst_slot_index),
        )
        is_nep_reflection = bool(
            nep_hit is not None and _is_nep_reflection_type_expr(str(getattr(nep_hit, "type_expr", "") or ""))
        )
        force_reflection_concrete = bool(
            (int(dst_type_id_int) == 18 and str(dst_port) == "初始值")
            or (int(dst_type_id_int) == 3 and int(dst_slot_index) in (0, 1))
        )
        # 对齐真源/测试契约：泛型/Variant 节点的 data 入参即便“已连线”，也必须写 ConcreteBase + indexOfConcrete
        # （例如 是否相等(14) 输入为实体时；设置局部变量(19) 输入为 Vec 时）。
        # 注意：信号 META 绑定节点的参数端口是例外（与 GIA 口径一致，不包 ConcreteBase）。
        should_wrap_as_concrete = bool(is_declared_generic_input) and (not bool(is_signal_meta_binding_node))

        template_by_slot = data_link_record_template_by_dst_type_id_and_slot_index.get(dst_type_id_int) or {}
        template_record_text = template_by_slot.get(int(dst_shell_index))

        # 先计算 src data 输出索引
        src_node_payload = graph_node_by_graph_node_id.get(src_node_id)
        if not isinstance(src_node_payload, dict):
            raise ValueError(f"graph_model 缺少 src_node: {src_node_id!r}")
        src_outputs = src_node_payload.get("outputs")
        if not isinstance(src_outputs, list):
            raise ValueError(f"src_node.outputs 不是 list: {src_node_id!r}")
        src_title = node_title_by_graph_node_id.get(src_node_id, "")
        src_def = resolve_node_def_for_graph_node(
            node_id=str(src_node_id),
            node_title=str(src_title),
            node_payload=src_node_payload,
            node_defs_by_name=node_defs_by_name,
        )
        if src_def is None:
            raise ValueError(f"data edge 缺少 src NodeDef: {src_title!r}")
        src_data_outputs = [
            str(p) for p in src_outputs if not _is_flow_port_by_node_def(node_def=src_def, port_name=str(p), is_input=False)
        ]
        if str(src_port) not in src_data_outputs:
            raise ValueError(
                f"src_port 不在 src_node.outputs(data) 中：src_node={src_node_id!r} src_port={src_port!r} outputs={src_data_outputs!r}"
            )
        src_data_output_ordinal = int(src_data_outputs.index(str(src_port)))
        src_type_id_int = int(node_type_id_by_graph_node_id.get(src_node_id, 0))
        src_shell_index, src_kernel_index = resolve_node_editor_pack_pin_indices(
            node_type_id_int=int(src_type_id_int),
            is_flow=False,
            direction="Out",
            port_name=str(src_port),
            ordinal=int(src_data_output_ordinal),
            fallback_index=int(src_data_output_ordinal),
        )

        # src 输出端口的“具体类型文本”（用于：dst 端泛型反推、字典 key/value 类型传播）
        src_port_type_text = str(_get_port_type_text(src_node_payload, str(src_port), is_input=False) or "").strip()
        if (not src_port_type_text) or src_port_type_text == "流程" or ("泛型" in src_port_type_text):
            # 特例：节点图变量 Get/Set 的 “变量值” 输出类型来自 graph_variables 表
            if str(src_title) in {"获取节点图变量", "设置节点图变量"} and str(src_port) == "变量值":
                input_constants = src_node_payload.get("input_constants")
                if isinstance(input_constants, dict):
                    var_name = input_constants.get("变量名")
                    if isinstance(var_name, str) and var_name.strip():
                        gv_type_text = str(graph_variable_type_text_map.get(var_name.strip()) or "").strip()
                        if gv_type_text and gv_type_text != "流程" and ("泛型" not in gv_type_text):
                            src_port_type_text = gv_type_text
        if (not src_port_type_text) or src_port_type_text == "流程" or ("泛型" in src_port_type_text):
            inferred_text = inferred_out_type_text_map.get((str(src_node_id), str(src_port)))
            if isinstance(inferred_text, str) and inferred_text.strip() and inferred_text.strip() != "流程" and ("泛型" not in inferred_text):
                src_port_type_text = inferred_text.strip()
        if (not src_port_type_text) or src_port_type_text == "流程" or ("泛型" in src_port_type_text):
            src_port_type_text = str(src_def.get_port_type(str(src_port), is_input=False)).strip()

        # 字典类型传播：尽可能提取 dict_key/dict_val 的 VarType（用于让编辑器正确展示“别名字典”）
        #
        # 重要：优先信任 **src 输出端口** 的字典类型（producer），再回退 dst 输入端口快照。
        # 原因：dst 侧类型快照在“接地/裁剪/缺少 graph_variables”时容易退化为字符串-字符串，
        # 若抢占优先级会把正确的 src 字典类型覆盖掉，导致同一 data-edge 的两端 KV 不一致。
        src_dict_kv_vts = _try_map_server_dict_type_text_to_kv_var_types(str(src_port_type_text))
        dst_dict_kv_vts = _try_map_server_dict_type_text_to_kv_var_types(str(dst_port_type_text))
        dict_kv_vts = src_dict_kv_vts or dst_dict_kv_vts
        if dict_kv_vts is None:
            if str(src_title) == "拼装字典" and str(src_port) == "字典":
                kt = str(_get_port_type_text(src_node_payload, "键0", is_input=True) or "").strip()
                vt = str(_get_port_type_text(src_node_payload, "值0", is_input=True) or "").strip()
                if kt and vt and ("泛型" not in kt) and ("泛型" not in vt):
                    dict_kv_vts = (
                        _map_server_port_type_to_var_type_id(kt),
                        _map_server_port_type_to_var_type_id(vt),
                    )
        if dict_kv_vts is None and isinstance(getattr(dst_type_plan, "dict_key_vt_for_node", None), int) and isinstance(
            getattr(dst_type_plan, "dict_value_vt_for_node", None), int
        ):
            # 兜底：当端口类型文本不足以解析别名字典时，允许使用共享 Plan 已推断到的 (K,V)。
            # 典型：接地/快照形态下“字典”端口仍为泛型，但“键/值”端口已有明确类型证据。
            dict_kv_vts = (
                int(getattr(dst_type_plan, "dict_key_vt_for_node")),
                int(getattr(dst_type_plan, "dict_value_vt_for_node")),
            )
        if dict_kv_vts is None and isinstance(dst_var_type_int, int) and int(dst_var_type_int) == 27:
            raise ValueError(
                "字典 data-edge 缺少可落地的 K/V 类型信息（禁止回退写入）："
                f"dst_node={str(dst_node_id)!r} dst_title={str(dst_title)!r} dst_port={str(dst_port)!r} "
                f"dst_port_type={str(dst_port_type_text)!r} src_node={str(src_node_id)!r} src_title={str(src_title)!r} "
                f"src_port={str(src_port)!r} src_port_type={str(src_port_type_text)!r}"
            )

        # ===== 优先“就地打补丁”：若 dst 节点已存在对应 InParam 占位 pin，则直接写入连接 =====
        # 背景：
        # - 动态端口节点（如 拼装列表/拼装字典）可能预置大量 InParam pins；
        # - 若再追加一个 template data-link record，会导致同一 pin_index 重复记录，编辑器可能按旧 record 解析。
        dst_node_obj = node_object_by_node_id_int[int(dst_node_id_int)]
        dst_records = _ensure_record_list(dst_node_obj)

        existing_record_index, existing_decoded = find_existing_unconnected_inparam_record(
            records=dst_records,
            dst_shell_index=int(dst_shell_index),
        )

        connect_msg = _build_node_connection_message(
            other_node_id_int=int(src_node_id_int),
            kind=4,  # OutParam
            index=int(src_shell_index),
            index2=int(src_kernel_index),
        )

        if isinstance(existing_record_index, int) and isinstance(existing_decoded, dict):
            patch_existing_unconnected_inparam_record_inplace(
                records=dst_records,
                existing_record_index=int(existing_record_index),
                existing_decoded=dict(existing_decoded),
                connect_msg=dict(connect_msg),
                dst_title=str(dst_title),
                dst_port=str(dst_port),
                dst_var_type_int=int(dst_var_type_int),
                dst_type_id_int=int(dst_type_id_int),
                dst_shell_index=int(dst_shell_index),
                should_wrap_as_concrete=bool(should_wrap_as_concrete),
                forced_index=(int(forced_index) if isinstance(forced_index, int) else None),
                signal_param_composite_pin_index=(
                    int(signal_param_composite_pin_index) if isinstance(signal_param_composite_pin_index, int) else None
                ),
                record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
                dict_kv_vts=(
                    (int(dict_kv_vts[0]), int(dict_kv_vts[1]))
                    if isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2
                    else None
                ),
            )
            added_data_edges += 1
            if should_enable_struct_modify_field:
                _ensure_inparam_bool_true_record(
                    records=dst_records,
                    pin_index=int(dst_shell_index) + 1,
                    node_type_id_int=int(dst_type_id_int),
                    record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
                )
            continue

        # 若 dst 端为泛型且无法直接映射 VarType，则用 src 输出端口类型（typed JSON）反推
        if not isinstance(dst_var_type_int, int):
            if src_port_type_text and src_port_type_text != "流程" and ("泛型" not in src_port_type_text):
                dst_var_type_int = _map_server_port_type_to_var_type_id(str(src_port_type_text))

        # 无样本 record：按 NodePin/NodeConnection 规则构造最小 data-link pin record
        if not isinstance(template_record_text, str):
            record_text = build_minimal_data_link_record_text(
                dst_title=str(dst_title),
                dst_port=str(dst_port),
                dst_type_id_int=int(dst_type_id_int),
                dst_shell_index=int(dst_shell_index),
                dst_kernel_index=int(dst_kernel_index),
                dst_var_type_int=(int(dst_var_type_int) if isinstance(dst_var_type_int, int) else None),
                connect_msg=dict(connect_msg),
                should_wrap_as_concrete=bool(should_wrap_as_concrete),
                forced_index=(int(forced_index) if isinstance(forced_index, int) else None),
                signal_param_composite_pin_index=(
                    int(signal_param_composite_pin_index) if isinstance(signal_param_composite_pin_index, int) else None
                ),
                record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
                dict_kv_vts=(
                    (int(dict_kv_vts[0]), int(dict_kv_vts[1]))
                    if isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2
                    else None
                ),
            )
            dst_records.append(str(record_text))
            added_data_edges += 1
            if should_enable_struct_modify_field:
                _ensure_inparam_bool_true_record(
                    records=dst_records,
                    pin_index=int(dst_shell_index) + 1,
                    node_type_id_int=int(dst_type_id_int),
                    record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
                )
            continue

        record_text2 = build_template_data_link_record_text(
            template_record_text=str(template_record_text),
            src_node_id_int=int(src_node_id_int),
            src_shell_index=int(src_shell_index),
            src_kernel_index=int(src_kernel_index),
            dst_title=str(dst_title),
            dst_port=str(dst_port),
            dst_var_type_int=(int(dst_var_type_int) if isinstance(dst_var_type_int, int) else None),
            dst_type_id_int=int(dst_type_id_int),
            dst_shell_index=int(dst_shell_index),
            should_wrap_as_concrete=bool(should_wrap_as_concrete),
            forced_index=(int(forced_index) if isinstance(forced_index, int) else None),
            signal_param_composite_pin_index=(
                int(signal_param_composite_pin_index) if isinstance(signal_param_composite_pin_index, int) else None
            ),
            dict_kv_vts=(
                (int(dict_kv_vts[0]), int(dict_kv_vts[1]))
                if isinstance(dict_kv_vts, tuple) and len(dict_kv_vts) == 2
                else None
            ),
        )
        _ensure_record_list(dst_node_obj).append(str(record_text2))
        added_data_edges += 1
        if should_enable_struct_modify_field:
            _ensure_inparam_bool_true_record(
                records=dst_records,
                pin_index=int(dst_shell_index) + 1,
                node_type_id_int=int(dst_type_id_int),
                record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
            )

    return int(added_data_edges)

