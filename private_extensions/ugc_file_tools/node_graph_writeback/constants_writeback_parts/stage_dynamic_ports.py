from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.pin_rules import infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    coerce_constant_value_for_var_type as _coerce_constant_value_for_var_type,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from ..record_codec import _build_node_pin_message, _decoded_field_map_to_dump_json_message, _extract_nested_int
from .types import _ConstantsWritebackContext, _ConstantsWritebackNodeState


def patch_dynamic_port_records_inplace(*, ctx: _ConstantsWritebackContext, state: _ConstantsWritebackNodeState) -> None:
    if str(state.title) == "拼装字典":
        _patch_assembly_dict_placeholder_inparam_pins_inplace(ctx=ctx, state=state)
    if str(state.title) == "拼装列表":
        _patch_assembly_list_placeholder_inparam_pins_inplace(ctx=ctx, state=state)


def _patch_assembly_dict_placeholder_inparam_pins_inplace(*, ctx: _ConstantsWritebackContext, state: _ConstantsWritebackNodeState) -> None:
    # ===== 动态端口节点：拼装字典 —— 同步占位 InParam pins 的 VarType =====
    # 背景：
    # - 拼装字典在存档内部通常预置大量 InParam 占位 pins（键0/值0/... 键49/值49，对应 index=1..100）。
    # - 若只写回“实际出现的少数 pin”（例如仅键0/值0 的常量），其余占位 pin 会保留模板默认 VarType（常见为 实体=1）。
    # - 编辑器加载时会基于占位 pins 的类型做端口组收敛，导致表现为“键/值端口都显示成实体”。
    key_vt: Optional[int] = None
    val_vt: Optional[int] = None
    if isinstance(state.assembly_dict_key_vt_for_node, int) and int(state.assembly_dict_key_vt_for_node) > 0:
        key_vt = int(state.assembly_dict_key_vt_for_node)
    if isinstance(state.assembly_dict_value_vt_for_node, int) and int(state.assembly_dict_value_vt_for_node) > 0:
        val_vt = int(state.assembly_dict_value_vt_for_node)

    if not isinstance(key_vt, int) or not isinstance(val_vt, int):
        key_type_text = str(_get_port_type_text(state.node_payload, "键0", is_input=True) or "").strip()
        val_type_text = str(_get_port_type_text(state.node_payload, "值0", is_input=True) or "").strip()
        if key_type_text and val_type_text and ("泛型" not in key_type_text) and ("泛型" not in val_type_text):
            key_vt = int(_map_server_port_type_to_var_type_id(str(key_type_text)))
            val_vt = int(_map_server_port_type_to_var_type_id(str(val_type_text)))

    if not (isinstance(key_vt, int) and isinstance(val_vt, int) and int(key_vt) > 0 and int(val_vt) > 0):
        return

    node_type_id_int = int(state.node_type_id_int_for_node)

    def _port_name_for_pin_index(pin_idx: int) -> str:
        if int(pin_idx) <= 0:
            return ""
        if int(pin_idx) % 2 == 1:
            return f"键{(int(pin_idx) - 1) // 2}"
        return f"值{(int(pin_idx) // 2) - 1}"

    def _build_minimal_entity_var_base() -> Dict[str, Any]:
        # 对齐样本：实体占位 pin 的 VarBase 只写 ItemType（不写 cls/baseValue）
        return {"4": {"1": 1, "100": {"1": 1}}}

    for record_i, record in enumerate(list(state.records)):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            continue
        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        pin_idx = 0 if idx is None else int(idx)
        if int(kind or -1) != 3:
            continue
        if pin_idx <= 0:
            continue

        connects = None
        field_5 = decoded.get("field_5")
        if isinstance(field_5, dict):
            f5_msg = field_5.get("message")
            if isinstance(f5_msg, dict):
                connects = [_decoded_field_map_to_dump_json_message(f5_msg)]
        elif isinstance(field_5, list):
            out = []
            for item in field_5:
                if not isinstance(item, dict):
                    continue
                f5_msg = item.get("message")
                if isinstance(f5_msg, dict):
                    out.append(_decoded_field_map_to_dump_json_message(f5_msg))
            if out:
                connects = list(out)

        port_name = _port_name_for_pin_index(int(pin_idx))
        if port_name == "":
            continue

        desired_vt = int(key_vt) if (pin_idx % 2 == 1) else int(val_vt)
        raw_value = None
        if isinstance(state.input_constants, dict) and port_name in state.input_constants:
            raw_value = state.input_constants.get(port_name)

        if raw_value is None:
            inner = (
                _build_minimal_entity_var_base()
                if int(desired_vt) == 1
                else _build_var_base_message_server_empty(var_type_int=int(desired_vt))
            )
        else:
            coerced = _coerce_constant_value_for_var_type(var_type_int=int(desired_vt), raw_value=raw_value)
            inner = _build_var_base_message_server(var_type_int=int(desired_vt), value=coerced)

        index_of_concrete = _infer_index_of_concrete_for_generic_pin(
            node_title=str(state.title),
            port_name=str(port_name),
            is_input=True,
            var_type_int=int(desired_vt),
            node_type_id_int=int(node_type_id_int),
            pin_index=int(pin_idx),
        )
        var_base = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=index_of_concrete)
        pin_msg = _build_node_pin_message(
            kind=3,
            index=int(pin_idx),
            var_type_int=int(desired_vt),
            connects=connects,
        )
        pin_msg["3"] = dict(var_base)
        state.records[record_i] = format_binary_data_hex_text(encode_message(pin_msg))

    # ===== 对齐 after_game：裁剪未使用的占位 pins（仅保留 GraphModel.inputs 实际出现的键/值端口）=====
    inputs_value = state.node_payload.get("inputs")
    used_ports: set[str] = set()
    if isinstance(inputs_value, list):
        used_ports = {
            str(p)
            for p in inputs_value
            if isinstance(p, str) and (str(p).startswith("键") or str(p).startswith("值"))
        }
    max_needed_pin_idx = 0
    for p in sorted(used_ports):
        raw = str(p)
        if raw.startswith("键"):
            tail = raw[len("键") :].strip()
            if tail.isdigit():
                max_needed_pin_idx = max(max_needed_pin_idx, 1 + 2 * int(tail))
        if raw.startswith("值"):
            tail = raw[len("值") :].strip()
            if tail.isdigit():
                max_needed_pin_idx = max(max_needed_pin_idx, 2 + 2 * int(tail))
    if max_needed_pin_idx <= 0:
        return

    kept: List[Any] = []
    for record in list(state.records):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            kept.append(record)
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            kept.append(record)
            continue
        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        pin_idx2 = 0 if idx is None else int(idx)
        if int(kind or -1) == 3 and int(pin_idx2) > int(max_needed_pin_idx) and ("field_5" not in decoded):
            continue
        kept.append(record)
    state.records[:] = kept


def _patch_assembly_list_placeholder_inparam_pins_inplace(*, ctx: _ConstantsWritebackContext, state: _ConstantsWritebackNodeState) -> None:
    node_type_id_int = int(state.node_type_id_int_for_node)
    list_type_text = str(_get_port_type_text(state.node_payload, "列表", is_input=False) or "").strip()

    # ===== 动态端口节点：拼装列表 —— 同步/补齐 1..100 的元素占位 pins（对齐真源）=====
    # 约定（真源样本：列表正确.gil + test4 校准图）：
    # - IN_PARAM(index=0): 隐藏“元素数量(Int)”由上游 stage_prepare_node 负责
    # - IN_PARAM(index=1..100): 元素输入（标签为 "0".."99"）
    #
    # 需求：
    # - 即便 GraphModel 只包含少量元素输入端口，也需要把占位 pins 的 VarType/Concrete 写全，
    #   否则编辑器会按模板默认类型收敛端口，表现为“端口类型错/连线断开”。
    # 优先使用元素端口的类型证据（更可靠；非严格 GraphModel 下输出端口可能仍为“泛型列表”）。
    elem_type_text = str(_get_port_type_text(state.node_payload, "0", is_input=True) or "").strip()
    if (not elem_type_text) or ("泛型" in elem_type_text) or elem_type_text.endswith("列表"):
        inferred = (getattr(ctx, "inferred_in_type_text", None) or {}).get((str(state.node_id), "0"))
        if isinstance(inferred, str) and inferred.strip():
            elem_type_text = inferred.strip()
    if (not elem_type_text) or ("泛型" in elem_type_text) or elem_type_text.endswith("列表"):
        if not list_type_text.endswith("列表"):
            # 兜底：尝试使用 inferred_out 的输出端口类型（例如下游约束推断得到“字符串列表”）
            inferred_out = (getattr(ctx, "inferred_out_type_text", None) or {}).get((str(state.node_id), "列表"))
            if isinstance(inferred_out, str) and inferred_out.strip():
                list_type_text = inferred_out.strip()
            else:
                return
        elem_type_text = str(list_type_text[: -len("列表")]).strip()
    if (not elem_type_text) or ("泛型" in elem_type_text) or elem_type_text.endswith("列表"):
        return
    desired_elem_vt = int(_map_server_port_type_to_var_type_id(str(elem_type_text)))
    if int(desired_elem_vt) <= 0:
        # 非严格/缺证据场景：输出端口与元素端口都可能仍为“泛型”，但 stage_prepare_node 可能已收集到唯一的元素类型候选。
        candidates = [int(v) for v in (getattr(state, "variant_primary_vt_candidates", None) or set()) if int(v) > 0]
        if len(candidates) == 1:
            desired_elem_vt = int(candidates[0])
        else:
            return

    desired_index = _infer_index_of_concrete_for_generic_pin(
        node_title=str(state.title),
        port_name="0",
        is_input=True,
        var_type_int=int(desired_elem_vt),
        node_type_id_int=int(node_type_id_int),
        pin_index=1,
    )

    # 仅对“输入端口存在的元素”(GraphModel.inputs 中的数字端口)写回常量 alreadySet；
    # 未出现的占位 pin 仅表达类型，不标记为已设置（对齐真源：大量占位 pins 常 inner.alreadySetVal 为空）。
    inputs_value = state.node_payload.get("inputs")
    active_ports: set[str] = set()
    if isinstance(inputs_value, list):
        for p in inputs_value:
            s = str(p)
            if s.isdigit():
                active_ports.add(s)

    def _extract_connects(decoded: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        field_5 = decoded.get("field_5")
        if isinstance(field_5, dict):
            f5_msg = field_5.get("message")
            if isinstance(f5_msg, dict):
                return [_decoded_field_map_to_dump_json_message(f5_msg)]
            return None
        if isinstance(field_5, list):
            out: List[Dict[str, Any]] = []
            for item in field_5:
                if not isinstance(item, dict):
                    continue
                f5_msg = item.get("message")
                if isinstance(f5_msg, dict):
                    out.append(_decoded_field_map_to_dump_json_message(f5_msg))
            return list(out) if out else None
        return None

    existing_by_pin: Dict[int, int] = {}
    for record_i, record in enumerate(list(state.records)):
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
        if idx_int <= 0:
            continue
        existing_by_pin[int(idx_int)] = int(record_i)

    minimal_entity_inner = {"4": {"1": 1, "100": {"1": 1}}}

    # 对齐 after_game：仅处理 GraphModel.inputs 中“实际出现的元素端口”对应的 pins，
    # 避免无条件补齐 1..100 造成大量 extra placeholder pins diff 噪声。
    max_needed_pin_idx = 0
    for p in sorted(active_ports):
        if str(p).isdigit():
            max_needed_pin_idx = max(max_needed_pin_idx, int(p) + 1)
    if max_needed_pin_idx <= 0:
        return

    for pin_idx in range(1, int(max_needed_pin_idx) + 1):
        existing_i = existing_by_pin.get(int(pin_idx))
        connects = None
        if isinstance(existing_i, int):
            decoded = decode_bytes_to_python(parse_binary_data_hex_text(state.records[int(existing_i)]))
            if isinstance(decoded, dict):
                connects = _extract_connects(decoded)

        port_name = str(int(pin_idx) - 1)
        raw_value = None
        if isinstance(state.input_constants, dict) and port_name in state.input_constants:
            raw_value = state.input_constants.get(port_name)

        # 默认：仅表达类型（inner.alreadySetVal 为空）；实体占位按真源只写 ItemType
        if raw_value is None:
            inner = (
                minimal_entity_inner
                if int(desired_elem_vt) == 1
                else _build_var_base_message_server_empty(var_type_int=int(desired_elem_vt))
            )
        else:
            inner = (
                minimal_entity_inner
                if int(desired_elem_vt) == 1
                else _build_var_base_message_server_empty(var_type_int=int(desired_elem_vt))
            )
            if port_name in active_ports and connects is None:
                coerced = _coerce_constant_value_for_var_type(var_type_int=int(desired_elem_vt), raw_value=raw_value)
                inner = _build_var_base_message_server(var_type_int=int(desired_elem_vt), value=coerced)

        var_base = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=desired_index)
        pin_msg = _build_node_pin_message(
            kind=3,
            index=int(pin_idx),
            var_type_int=int(desired_elem_vt),
            connects=connects,
        )
        pin_msg["3"] = dict(var_base)
        record_text = format_binary_data_hex_text(encode_message(pin_msg))
        if isinstance(existing_i, int):
            state.records[int(existing_i)] = record_text
        else:
            state.records.append(record_text)

    # 裁剪超出 max_needed 的未连线占位 pins（若模板/样本带有大量预置占位）
    kept: List[Any] = []
    for record in list(state.records):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            kept.append(record)
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            kept.append(record)
            continue
        kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        idx_int = 0 if idx is None else int(idx)
        if int(kind or -1) == 3 and int(idx_int) > int(max_needed_pin_idx) and ("field_5" not in decoded):
            continue
        kept.append(record)
    state.records[:] = kept
