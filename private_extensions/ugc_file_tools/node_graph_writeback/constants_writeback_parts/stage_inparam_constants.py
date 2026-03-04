from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.contracts.signal_meta_binding import (
    resolve_signal_meta_binding_param_pin_indices as _resolve_signal_meta_binding_param_pin_indices,
)
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.enum_codec import resolve_enum_item_id_for_input_constant as _resolve_enum_item_id_for_input_constant
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_declared_generic_port_type as _is_declared_generic_port_type,
    resolve_input_port_name_for_type as _resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.nep_type_expr import is_nep_reflection_type_expr as _is_nep_reflection_type_expr
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
    map_inparam_pin_index_for_node as _map_inparam_pin_index_for_node,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    build_var_base_message_server_for_dict as _build_var_base_message_server_for_dict,
    coerce_constant_value_for_port_type as _coerce_constant_value_for_port_type,
    coerce_constant_value_for_var_type as _coerce_constant_value_for_var_type,
    infer_var_type_int_from_raw_value as _infer_var_type_int_from_raw_value,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    try_map_server_dict_type_text_to_kv_var_types as _try_map_server_dict_type_text_to_kv_var_types,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from ..node_editor_pack import _find_nep_pin_def, resolve_node_editor_pack_pin_indices
from ..record_codec import _build_node_pin_message, _decoded_field_map_to_dump_json_message, _extract_nested_int
from ..writeback_feature_flags import is_writeback_feature_enabled
from .types import _ConstantsWritebackContext, _ConstantsWritebackCounters, _ConstantsWritebackNodeState


CREATE_PREFAB_WRAPPER_NODE_TITLE = "创建元件"
CREATE_PREFAB_PORT_NAME_OVERRIDE_LEVEL = "是否覆写等级"
CREATE_PREFAB_PORT_NAME_LEVEL = "等级"
CREATE_PREFAB_PORT_NAME_TAG_INDEX_LIST = "单位标签索引列表"

# 对齐真源样本：Create_Prefab 的『是否覆写等级』InParam 的 PinIndex2(kernel) 为 7。
# 说明：
# - GraphModel/Graph Code 侧不暴露底层的一个实体输入槽位，导致该节点存在 shell/kernel index 不一致；
# - 若写回侧缺失该 kernel index，官方侧可能按错误端口表解释该 pin，进而表现为“格式不对/端口错位”。
CREATE_PREFAB_OVERRIDE_LEVEL_KERNEL_INDEX = 7

def _infer_dict_kv_var_types_from_constant_value(raw_value: Any) -> Optional[Tuple[int, int]]:
    """
    当端口类型文本无法提供字典 key/value 类型时，按常量字面量兜底推断。
    仅接受非空 dict；类型不唯一时直接报错，避免写出不确定编码。
    """
    if not isinstance(raw_value, dict):
        return None
    if not raw_value:
        return None

    key_vts = {int(_infer_var_type_int_from_raw_value(k)) for k in raw_value.keys()}
    val_vts = {int(_infer_var_type_int_from_raw_value(v)) for v in raw_value.values()}
    if len(key_vts) != 1 or len(val_vts) != 1:
        raise ValueError(
            "字典常量键/值类型不唯一，无法写回："
            f"key_vts={sorted(key_vts)} val_vts={sorted(val_vts)} raw_value={raw_value!r}"
        )

    key_vt = next(iter(key_vts))
    val_vt = next(iter(val_vts))
    if int(key_vt) <= 0 or int(val_vt) <= 0:
        raise ValueError(f"字典常量推断得到非法 VarType：key_vt={key_vt} val_vt={val_vt}")
    return int(key_vt), int(val_vt)


def _write_or_patch_inparam_constant_record(
    *,
    records: List[Any],
    pin_index: int,
    var_type_int: int,
    var_base_message: Dict[str, Any],
    index2: Optional[int],
    record_id_int: Optional[int],
) -> None:
    """
    写入/替换一个『纯常量 InParam record』（kind=3,无 field_5 连接）。

    重要：优先就地 patch 既有 record，以保留真源中的 pin_index 映射（field_1.index 与 field_2.index 可能不同）
    以及 record.field_7(record_id) 等附加字段；仅在不存在模板 record 时才合成最小 record。
    """
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

    if isinstance(existing_record_index, int) and isinstance(existing_decoded, dict):
        dump_msg = _decoded_field_map_to_dump_json_message(existing_decoded)
        dump_msg["4"] = int(var_type_int)
        dump_msg["3"] = dict(var_base_message)
        if isinstance(record_id_int, int) and int(record_id_int) > 0 and "7" not in dump_msg:
            dump_msg["7"] = int(record_id_int)
        records[int(existing_record_index)] = format_binary_data_hex_text(encode_message(dump_msg))
        return

    if isinstance(record_id_int, int) and int(record_id_int) > 0:
        rid = int(record_id_int)
    else:
        rid = None

    pin_msg = _build_node_pin_message(
        kind=3,
        index=int(pin_index),
        index2=(int(index2) if isinstance(index2, int) else None),
        var_type_int=int(var_type_int),
        connects=None,
    )
    pin_msg["3"] = dict(var_base_message)
    if isinstance(rid, int):
        pin_msg["7"] = int(rid)
    records.append(format_binary_data_hex_text(encode_message(pin_msg)))


def _resolve_signal_param_composite_pin_index(
    *,
    param_port_indices: Optional[List[int]],
    param_slot_index: int,
) -> Optional[int]:
    if not isinstance(param_port_indices, list):
        return None
    i = int(param_slot_index)
    if i < 0 or i >= len(param_port_indices):
        return None
    value = param_port_indices[i]
    if isinstance(value, int) and int(value) >= 0:
        return int(value)
    return None


def write_input_constants_inplace(
    *,
    ctx: _ConstantsWritebackContext,
    state: _ConstantsWritebackNodeState,
    counters: _ConstantsWritebackCounters,
    skipped_enum_constants: List[Dict[str, Any]],
    node_type_id_by_graph_node_id: Dict[str, int],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]] = None,
) -> None:
    input_constants = state.input_constants if isinstance(state.input_constants, dict) else None
    if not (isinstance(input_constants, dict) and input_constants and state.data_inputs):
        return

    override_level_value = input_constants.get(CREATE_PREFAB_PORT_NAME_OVERRIDE_LEVEL)
    create_prefab_override_level_is_false = (
        str(state.title) == CREATE_PREFAB_WRAPPER_NODE_TITLE and override_level_value is False
    )

    for port_name_raw, raw_value in input_constants.items():
        port_name = str(port_name_raw)

        # 隐藏语义键（如 __struct_id/__signal_id）不对应真实端口：不写入 record
        if port_name.startswith("__"):
            continue
        # 结构体节点的『结构体名』为选择端口：真源中通常不以 InParam record 写入
        if str(state.title) == "修改结构体" and port_name == "结构体名":
            continue
        if port_name not in state.data_inputs:
            continue

        # Create_Prefab：当『是否覆写等级』为 False 时，等级/标签列表端口即便在 Graph Code 中传入，
        # 真源样本也不会落盘对应常量 pin；写回侧对齐该口径，避免产生多余 pins 干扰 diff/导入。
        if create_prefab_override_level_is_false and port_name in {
            CREATE_PREFAB_PORT_NAME_LEVEL,
            CREATE_PREFAB_PORT_NAME_TAG_INDEX_LIST,
        }:
            raw_value = None

        slot_index = int(state.data_inputs.index(port_name))
        pin_fallback_index = _map_inparam_pin_index_for_node(
            node_title=str(state.title), port_name=str(port_name), slot_index=int(slot_index)
        )
        node_type_id_int_for_pin = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
        resolved_port_name = _resolve_input_port_name_for_type(node_def=state.node_def, port_name=str(port_name))

        if state.signal_binding_role != "":
            # 对齐真源 `.gil`：信号参数 pin 的 i2(index2/kernel) 与 shell index 一致（slot_index）。
            pin_index, pin_index2 = _resolve_signal_meta_binding_param_pin_indices(slot_index=int(slot_index))
        elif int(node_type_id_int_for_pin) == 3:
            # 真源对齐：Multiple_Branches 的 InParam 为 0/1（shell=kernel=slot）
            pin_index = int(slot_index)
            pin_index2 = int(slot_index)
        elif str(state.title) == "拼装字典":
            # 拼装字典的 GraphModel 端口顺序是 键0/值0/...；
            # 真实存档 InParam 需要从 pin1 开始（key0=1, val0=2...）。
            # NodeEditorPack 中 pin0 为内部 len，占位端口不应用于 GraphModel 写回。
            pin_index = int(pin_fallback_index)
            pin_index2 = int(pin_fallback_index)
        else:
            pin_index, pin_index2 = resolve_node_editor_pack_pin_indices(
                node_type_id_int=int(node_type_id_int_for_pin),
                is_flow=False,
                direction="In",
                port_name=str(resolved_port_name),
                ordinal=int(slot_index),
                fallback_index=int(pin_fallback_index),
            )

        # 兜底对齐真源：信号节点参数端口的 kernel index 必须与 shell index 一致（shell=kernel=slot）。
        # 避免 NEP 画像或旧逻辑导致 pin_index2 固定为 0，从而出现“多参数端口错位/串号”。
        if str(state.title) in {"发送信号", "监听信号", "发送信号到服务端", "向服务器节点图发送信号"} and str(port_name) != "信号名":
            pin_index2 = int(pin_index)

        # Create_Prefab：对齐真源样本的 kernel index（PinIndex2）。
        if str(state.title) == CREATE_PREFAB_WRAPPER_NODE_TITLE and str(port_name) == CREATE_PREFAB_PORT_NAME_OVERRIDE_LEVEL:
            pin_index2 = int(CREATE_PREFAB_OVERRIDE_LEVEL_KERNEL_INDEX)

        # 工程化：GraphModel 中允许用 `None` 表达“该端口不写常量”（缺省语义）。
        # 写回阶段不得尝试将 None 强制转换为 Int/Str/Bool 等基础类型，否则会抛错并中断导出。
        # 若模板克隆场景下该 pin 已存在“纯常量 InParam record”，这里会将其删除以保持未设置语义。
        if raw_value is None:
            # 对齐 after_game：部分节点（如『对字典设置或新增键值对』的『值』端口）在真源样本中即便未连线/未设置，
            # 仍保留一个占位 InParam pin record（value_summary 为空，connects_count=0），用于稳定端口结构。
            # 因此这里不要删除该类 pin 的纯常量 record。
            if (
                is_writeback_feature_enabled("dict_set_value_pin_keep_placeholder_when_constant_none")
                and str(state.title) == "对字典设置或新增键值对"
                and str(port_name) == "值"
            ):
                continue
            existing_record_index: Optional[int] = None
            for i, record in enumerate(list(state.records)):
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
                break
            if isinstance(existing_record_index, int):
                del state.records[existing_record_index]
            continue

        signal_param_composite_pin_index = (
            _resolve_signal_param_composite_pin_index(
                param_port_indices=state.signal_binding_param_port_indices,
                param_slot_index=int(slot_index),
            )
            if state.signal_binding_role != ""
            else None
        )

        nep_node_record = ctx.nep_nodes_by_id.get(int(node_type_id_int_for_pin))
        nep_hit = _find_nep_pin_def(
            nep_node_record,
            is_flow=False,
            direction="In",
            port_name=str(resolved_port_name),
            ordinal=int(slot_index),
        )
        is_nep_reflection = bool(
            nep_hit is not None and _is_nep_reflection_type_expr(str(getattr(nep_hit, "type_expr", "") or ""))
        )
        force_reflection_concrete = (int(node_type_id_int_for_pin) == 18 and str(port_name) == "初始值") or (
            int(node_type_id_int_for_pin) == 3 and int(slot_index) in (0, 1)
        )

        # 优先使用 GraphModel(JSON) 导出的端口类型（可包含泛型端口的具体类型；兼容 input_types 快照字段）
        port_type_text = str(_get_port_type_text(state.node_payload, str(port_name), is_input=True) or "").strip()
        if not port_type_text:
            resolved_name = _resolve_input_port_name_for_type(node_def=state.node_def, port_name=port_name)
            port_type_text = str(state.node_def.get_port_type(str(resolved_name), is_input=True)).strip()
        if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
            inferred_port_type = ctx.inferred_in_type_text.get((str(state.node_id), str(port_name)))
            if isinstance(inferred_port_type, str):
                inferred_port_type_text = inferred_port_type.strip()
                if inferred_port_type_text and inferred_port_type_text != "流程":
                    port_type_text = inferred_port_type_text

        # ===== 特例：获取局部变量 的“初始值”常量 =====
        # 用户修正样本：当初始值为纯数字字符串（校准占位常见为 "0"）时，
        # 该端口不应按“整数常量”写入，而应写入 GUID 类型的空值占位（仅表达类型），
        # 避免编辑器把该端口收敛为整数导致后续泛型推断异常。
        if str(state.title) == "获取局部变量" and str(port_name) == "初始值":
            raw_text = str(raw_value).strip() if isinstance(raw_value, str) else ""
            if raw_text != "" and raw_text.isdigit():
                # 仅在“端口已能确定为 GUID”时才做该补丁：
                # - 避免把合法的整数初始值（例如 "0"/"123"）强行写成 GUID，导致用户实际变量类型被改坏。
                desired_vt_without_constant = int(
                    _resolve_server_var_type_int_for_port(
                        graph_scope=str(ctx.graph_scope),
                        node_id=str(state.node_id),
                        port_name=str(port_name),
                        is_input=True,
                        node_payload=state.node_payload,
                        graph_variable_type_text_by_name=dict(ctx.graph_variable_type_text_map),
                        inferred_out_type_text=dict(ctx.inferred_out_type_text),
                        inferred_in_type_text=dict(ctx.inferred_in_type_text),
                        raw_constant_value=None,  # 关键：不要被 "0" 的字面值误推断成整数
                        nep_node_record=nep_node_record,
                        nep_port_name=str(resolved_port_name),
                        nep_ordinal=int(slot_index),
                    )
                )
                if int(desired_vt_without_constant) == 2:
                    node_type_id_int = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))

                    # 强制 GUID(2)，并写入空 IdBaseValue（保留 alreadySetVal=1 的结构口径）
                    var_type_int = 2
                    inner_var_base = {
                        "1": 1,  # IdBaseValue
                        "2": 1,  # alreadySetVal
                        "4": {"1": 1, "100": {"1": 2}},  # ItemType(GUID)
                        "101": format_binary_data_hex_text(b""),  # empty bytes
                    }
                    forced_index = (
                        state.forced_index_of_concrete_by_port.get(str(port_name))
                        if isinstance(state.forced_index_of_concrete_by_port, dict)
                        else None
                    )
                    var_base = _wrap_var_base_as_concrete_base(
                        inner=inner_var_base,
                        index_of_concrete=(
                            int(forced_index)
                            if isinstance(forced_index, int)
                            else _infer_index_of_concrete_for_generic_pin(
                                node_title=str(state.title),
                                port_name=str(port_name),
                                is_input=True,
                                var_type_int=int(var_type_int),
                                node_type_id_int=int(node_type_id_int),
                                pin_index=int(pin_index),
                            )
                        ),
                    )
                    pin_msg = _build_node_pin_message(
                        kind=3,
                        index=int(pin_index),
                        index2=(int(pin_index2) if int(pin_index2) != int(pin_index) else None),
                        var_type_int=int(var_type_int),
                        connects=None,
                    )
                    pin_msg["3"] = dict(var_base)
                    record_text = format_binary_data_hex_text(encode_message(pin_msg))

                    existing_record_index: Optional[int] = None
                    for i, record in enumerate(list(state.records)):
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
                        break

                    if isinstance(existing_record_index, int):
                        state.records[existing_record_index] = record_text
                    else:
                        state.records.append(record_text)
                    state.variant_primary_vt_candidates.add(int(var_type_int))
                    counters.input_constants_written += 1
                    continue

        enum_constant_written_this_port = False
        var_type_int = int(
            _resolve_server_var_type_int_for_port(
                graph_scope=str(ctx.graph_scope),
                node_id=str(state.node_id),
                port_name=str(port_name),
                is_input=True,
                node_payload=state.node_payload,
                graph_variable_type_text_by_name=dict(ctx.graph_variable_type_text_map),
                inferred_out_type_text=dict(ctx.inferred_out_type_text),
                inferred_in_type_text=dict(ctx.inferred_in_type_text),
                raw_constant_value=raw_value,
                nep_node_record=nep_node_record,
                nep_port_name=str(resolved_port_name),
                nep_ordinal=int(slot_index),
            )
        )

        if isinstance(state.dict_key_vt_for_node, int) and isinstance(state.dict_value_vt_for_node, int):
            if str(port_name) == "键":
                var_type_int = int(state.dict_key_vt_for_node)
            elif str(port_name) == "值":
                var_type_int = int(state.dict_value_vt_for_node)

        # 信号节点（发送信号/发送信号到服务端）：参数端口 VarType 以信号规格为真源覆写，
        # 避免 GraphModel 端口仍为“泛型”时按 raw_value 推断/保守兜底导致写错类型。
        if state.signal_binding_role in {"send", "server_send"} and isinstance(state.signal_binding_param_var_type_ids, list):
            if 0 <= int(slot_index) < len(state.signal_binding_param_var_type_ids):
                vt_override = state.signal_binding_param_var_type_ids[int(slot_index)]
                if isinstance(vt_override, int) and int(vt_override) > 0:
                    var_type_int = int(vt_override)

        if int(var_type_int) == 14:
            node_type_id_int = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
            counters.enum_constants_total += 1
            resolved_enum_item_id = _resolve_enum_item_id_for_input_constant(
                node_type_id_int=int(node_type_id_int),
                slot_index=int(slot_index),
                port_name=str(port_name),
                raw_value=raw_value,
                node_def=state.node_def,
                node_entry_by_id=ctx.node_entry_by_id,
                enum_entry_by_id=ctx.enum_entry_by_id,
            )
            if resolved_enum_item_id is None:
                skipped_enum_constants.append(
                    {
                        "node": str(state.title),
                        "type_id": int(node_type_id_int),
                        "port": str(port_name),
                        "slot_index": int(slot_index),
                        "raw_value": raw_value,
                    }
                )
                continue
            coerced_value = int(resolved_enum_item_id)
            enum_constant_written_this_port = True
        else:
            mapped_port_type_vt: Optional[int] = None
            if port_type_text and port_type_text != "流程" and ("泛型" not in port_type_text):
                mapped_port_type_vt = int(_map_server_port_type_to_var_type_id(str(port_type_text)))
            if isinstance(mapped_port_type_vt, int) and int(mapped_port_type_vt) == int(var_type_int):
                coerced_value = _coerce_constant_value_for_port_type(port_type=str(port_type_text), raw_value=raw_value)
            else:
                coerced_value = _coerce_constant_value_for_var_type(var_type_int=int(var_type_int), raw_value=raw_value)

        dict_kv_var_types: Optional[Tuple[int, int]] = None
        if int(var_type_int) == 27:
            dict_kv_var_types = _try_map_server_dict_type_text_to_kv_var_types(str(port_type_text or ""))
            if dict_kv_var_types is None:
                dict_kv_var_types = _infer_dict_kv_var_types_from_constant_value(coerced_value)
            if dict_kv_var_types is None:
                raise ValueError(
                    "写回字典输入常量失败：无法确定 key/value 类型。"
                    f" node={state.title!r} port={port_name!r} port_type={port_type_text!r} raw_value={raw_value!r}"
                )

        # 寻找并替换同 pin_index 的“纯常量 InParam record”；若不存在则追加
        existing_record_index: Optional[int] = None
        for i, record in enumerate(list(state.records)):
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
            break

        if int(var_type_int) == 27:
            key_vt, val_vt = dict_kv_var_types
            inner_var_base = _build_var_base_message_server_for_dict(
                dict_key_var_type_int=int(key_vt),
                dict_value_var_type_int=int(val_vt),
                default_value=coerced_value,
            )
        else:
            inner_var_base = _build_var_base_message_server(var_type_int=int(var_type_int), value=coerced_value)

        # 对齐真源/测试契约：
        # - 泛型/Variant 节点的 InParam 常量需要写 ConcreteBase + indexOfConcrete（即便端口最终类型已可解析为具体 VarType）。
        # - 例外：信号 META 绑定节点的“参数端口”与 GIA 一致，直接写基础 VarBase，不包 ConcreteBase；
        #   否则编辑器中可能出现“端口可见但值无法编辑/写入”的异常表现。
        # declared generic 判定：优先使用 GraphModel 的 declared_types（更贴近导出/写回真实数据来源），
        # 仅在缺失时才回退 NodeDef 的 declared type。
        declared_type_text = ""
        declared_map = state.node_payload.get("input_port_declared_types")
        if isinstance(declared_map, dict):
            raw = declared_map.get(str(port_name))
            if isinstance(raw, str) and raw.strip():
                declared_type_text = raw.strip()
        if not declared_type_text:
            declared_type_text = str(state.node_def.get_port_type(str(resolved_port_name), is_input=True)).strip()

        is_declared_generic_input = bool(_is_declared_generic_port_type(str(declared_type_text)))
        should_wrap_as_concrete = bool(is_declared_generic_input) and state.signal_binding_role == ""

        forced_index = None
        if isinstance(state.forced_index_of_concrete_by_port, dict):
            if str(port_name) in state.forced_index_of_concrete_by_port:
                forced_index = state.forced_index_of_concrete_by_port.get(str(port_name))
            elif str(port_name).startswith("键") and "键" in state.forced_index_of_concrete_by_port:
                forced_index = state.forced_index_of_concrete_by_port.get("键")
            elif str(port_name).startswith("值") and "值" in state.forced_index_of_concrete_by_port:
                forced_index = state.forced_index_of_concrete_by_port.get("值")

        var_base = (
            _wrap_var_base_as_concrete_base(
                inner=inner_var_base,
                index_of_concrete=(
                    int(forced_index)
                    if isinstance(forced_index, int)
                    else _infer_index_of_concrete_for_generic_pin(
                        node_title=str(state.title),
                        port_name=str(port_name),
                        is_input=True,
                        var_type_int=int(var_type_int),
                        node_type_id_int=int(node_type_id_by_graph_node_id.get(str(state.node_id), 0)),
                        pin_index=int(pin_index),
                    )
                ),
            )
            if should_wrap_as_concrete
            else inner_var_base
        )

        if bool(is_nep_reflection) and isinstance(var_type_int, int):
            if int(node_type_id_int_for_pin) == 3:
                if int(slot_index) == 0:
                    state.variant_primary_vt_candidates.add(int(var_type_int))
            else:
                state.variant_primary_vt_candidates.add(int(var_type_int))

        if str(state.title) == "修改结构体":
            # 真源：修改结构体的 InParam record 的 field_1/field_2.index 不总相同，必须优先 patch 模板 record
            node_type_id_int = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
            record_id_int = None
            if record_id_by_node_type_id_and_inparam_index is not None:
                record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(node_type_id_int)) or {}).get(int(pin_index))
            index2 = 0 if int(pin_index) <= 0 else int(pin_index) - 1
            _write_or_patch_inparam_constant_record(
                records=state.records,
                pin_index=int(pin_index),
                var_type_int=int(var_type_int),
                var_base_message=dict(var_base),
                index2=int(index2),
                record_id_int=(int(record_id_int) if isinstance(record_id_int, int) else None),
            )

            # 字段赋值：同时写入『是否修改_<字段>』的 bool=1 记录（pin = value_pin + 1）
            if port_name not in {"结构体实例"}:
                bool_pin_index = int(pin_index) + 1
                bool_record_id_int = None
                if record_id_by_node_type_id_and_inparam_index is not None:
                    bool_record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(node_type_id_int)) or {}).get(int(bool_pin_index))
                bool_index2 = 0 if bool_pin_index <= 0 else int(bool_pin_index) - 1
                bool_var_base = _build_var_base_message_server(var_type_int=4, value=True)
                _write_or_patch_inparam_constant_record(
                    records=state.records,
                    pin_index=int(bool_pin_index),
                    var_type_int=4,
                    var_base_message=dict(bool_var_base),
                    index2=int(bool_index2),
                    record_id_int=(int(bool_record_id_int) if isinstance(bool_record_id_int, int) else None),
                )
        else:
            node_type_id_int = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
            record_id_int: Optional[int] = None
            if record_id_by_node_type_id_and_inparam_index is not None:
                record_id_int = (record_id_by_node_type_id_and_inparam_index.get(int(node_type_id_int)) or {}).get(int(pin_index))

            # field_7 的语义：
            # - 信号参数端口：写入信号规格端口块的 compositePinIndex（对齐真源）
            # - 复合节点等：写入 NodeInterface 的 persistent_uid（record_id_map），用于稳定映射外部虚拟端口
            desired_field_7: Optional[int] = None
            if (
                isinstance(signal_param_composite_pin_index, int)
                and isinstance(state.signal_binding_source_ref_node_def_id_int, int)
                and int(state.signal_binding_source_ref_node_def_id_int) >= 0x40000000
            ):
                desired_field_7 = int(signal_param_composite_pin_index)
            elif isinstance(record_id_int, int) and int(record_id_int) > 0:
                desired_field_7 = int(record_id_int)

            _write_or_patch_inparam_constant_record(
                records=state.records,
                pin_index=int(pin_index),
                var_type_int=int(var_type_int),
                var_base_message=dict(var_base),
                index2=(int(pin_index2) if int(pin_index2) != int(pin_index) else None),
                record_id_int=desired_field_7,
            )

        counters.input_constants_written += 1
        if enum_constant_written_this_port:
            counters.enum_constants_written += 1

    _maybe_patch_dict_remove_key_node_key_type_inplace(ctx=ctx, state=state, node_type_id_by_graph_node_id=node_type_id_by_graph_node_id)


def _maybe_patch_dict_remove_key_node_key_type_inplace(
    *,
    ctx: _ConstantsWritebackContext,
    state: _ConstantsWritebackNodeState,
    node_type_id_by_graph_node_id: Dict[str, int],
) -> None:
    # ===== 字典类节点：以键对字典移除键值对 —— 键类型应跟随字典别名 =====
    # 用户修正样本：当字典端口具体类型为“字符串_字符串字典”时，即便键常量是纯数字，也应按字符串写入。
    if str(state.title) != "以键对字典移除键值对":
        return

    dict_type_text = str(_get_port_type_text(state.node_payload, "字典", is_input=True) or "").strip()

    def _parse_typed_dict_alias(type_text: str) -> Tuple[bool, str, str]:
        t = str(type_text or "").strip()
        if not t.endswith("字典"):
            return False, "", ""
        core = t[: -len("字典")]
        if "-" in core:
            left, right = core.split("-", 1)
        elif "_" in core:
            left, right = core.split("_", 1)
        else:
            return False, "", ""
        key = str(left).strip()
        val = str(right).strip()
        if key == "" or val == "":
            return False, "", ""
        return True, key, val

    ok, dict_key_type, _dict_val_type = _parse_typed_dict_alias(dict_type_text)
    if not ok:
        return
    if dict_key_type != "字符串":
        return
    if not (isinstance(state.input_constants, dict) and ("键" in state.input_constants)):
        return

    # 定位『键』端口对应的 pin_index
    if "键" in state.data_inputs:
        slot_index = int(state.data_inputs.index("键"))
        pin_fallback_index = _map_inparam_pin_index_for_node(
            node_title=str(state.title), port_name="键", slot_index=int(slot_index)
        )
        node_type_id_int_for_pin = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
        resolved_port_name = _resolve_input_port_name_for_type(node_def=state.node_def, port_name="键")
        pin_index, pin_index2 = resolve_node_editor_pack_pin_indices(
            node_type_id_int=int(node_type_id_int_for_pin),
            is_flow=False,
            direction="In",
            port_name=str(resolved_port_name),
            ordinal=int(slot_index),
            fallback_index=int(pin_fallback_index),
        )
    else:
        pin_index = 1
        pin_index2 = 1

    raw_value = state.input_constants.get("键") if isinstance(state.input_constants, dict) else None
    coerced_value = _coerce_constant_value_for_port_type(port_type="字符串", raw_value=raw_value)
    inner_var_base = _build_var_base_message_server(var_type_int=6, value=str(coerced_value))
    node_type_id_int = int(node_type_id_by_graph_node_id.get(str(state.node_id), 0))
    var_base = _wrap_var_base_as_concrete_base(
        inner=inner_var_base,
        index_of_concrete=_infer_index_of_concrete_for_generic_pin(
            node_title=str(state.title),
            port_name="键",
            is_input=True,
            var_type_int=6,
            node_type_id_int=int(node_type_id_int),
            pin_index=int(pin_index),
        ),
    )
    pin_msg = _build_node_pin_message(
        kind=3,
        index=int(pin_index),
        index2=(int(pin_index2) if int(pin_index2) != int(pin_index) else None),
        var_type_int=6,
        connects=None,
    )
    pin_msg["3"] = dict(var_base)
    record_text = format_binary_data_hex_text(encode_message(pin_msg))

    existing_record_index: Optional[int] = None
    for i, record in enumerate(list(state.records)):
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
        break

    if isinstance(existing_record_index, int):
        state.records[existing_record_index] = record_text
    else:
        state.records.append(record_text)

