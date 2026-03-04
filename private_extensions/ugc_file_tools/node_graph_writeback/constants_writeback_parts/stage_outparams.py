from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    is_declared_generic_port_type as _is_declared_generic_port_type,
)
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_item_type_server_for_dict as _build_var_base_item_type_server_for_dict,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    try_map_server_dict_type_text_to_kv_var_types as _try_map_server_dict_type_text_to_kv_var_types,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from ..record_codec import _build_node_pin_message, _extract_nested_int
from ..writeback_feature_flags import is_writeback_feature_enabled
from .types import _ConstantsWritebackContext, _ConstantsWritebackNodeState


_ALLOWED_OUTPARAM_VAR_TYPES: set[int] = {
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    17,
    20,
    21,
    22,
    23,
    24,
    25,
    26,
    27,
}

_LIST_OUTPARAM_VAR_TYPES: set[int] = {
    7,  # GUID列表
    8,  # 整数列表
    9,  # 布尔值列表
    10,  # 浮点数列表
    11,  # 字符串列表
    13,  # 实体列表
    15,  # 三维向量列表
    22,  # 配置ID列表
    23,  # 元件ID列表
    24,  # 阵营列表
    26,  # 结构体列表
}


def _extract_index_of_concrete_from_outparam_record_text(record_text: str) -> Optional[int]:
    """
    从 `<binary_data>...` 的 OutParam record 中抽取 ConcreteBase.indexOfConcrete（若存在）。

    返回 None：
    - record 不是 binary_data
    - record 未写入 indexOfConcrete（例如 index=0 或遗漏）
    """
    from ugc_file_tools.decode_gil import decode_bytes_to_python
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    if not isinstance(record_text, str) or not record_text.startswith("<binary_data>"):
        return None
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(record_text))
    if not isinstance(decoded, dict):
        return None
    return _extract_nested_int(decoded, ["field_3", "message", "field_110", "message", "field_1"])


def _extract_concrete_inner_var_base_cls_from_outparam_record_text(record_text: str) -> Optional[int]:
    """从 OutParam record 中抽取 ConcreteBase.inner(field_110.field_2) 的 VarBase.cls(field_1)。"""
    from ugc_file_tools.decode_gil import decode_bytes_to_python
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    if not isinstance(record_text, str) or not record_text.startswith("<binary_data>"):
        return None
    decoded = decode_bytes_to_python(parse_binary_data_hex_text(record_text))
    if not isinstance(decoded, dict):
        return None
    outer_cls = _extract_nested_int(decoded, ["field_3", "message", "field_1"])
    if not (isinstance(outer_cls, int) and int(outer_cls) == 10000):
        return None
    return _extract_nested_int(decoded, ["field_3", "message", "field_110", "message", "field_2", "message", "field_1"])


def _should_rebuild_outparam_record_for_list_type(record_text: str, var_type_int: int) -> bool:
    """
    对齐真源（校验成功样本）：
    - list VarType 的 OUT_PARAM（ConcreteBase.inner）必须为 ArrayBase(10002)，且空数组值通常以 field_109=empty bytes 表达；
    - 若模板残留为 EnumBaseValue(6)+field_106(empty bytes) 等，会导致 VarType 与 VarBase.cls 不一致，官方侧可能校验失败。
    """
    if int(var_type_int) not in _LIST_OUTPARAM_VAR_TYPES:
        return False
    inner_cls = _extract_concrete_inner_var_base_cls_from_outparam_record_text(str(record_text))
    return not (isinstance(inner_cls, int) and int(inner_cls) == 10002)


def _build_outparam_record_text(
    *,
    node_title: str,
    node_type_id_int: int,
    out_port: str,
    out_index: int,
    var_type_int: int,
    forced_index_of_concrete: Optional[int],
) -> str:
    """按 schema 构造最小 OutParam record（用于 declared generic 输出端口表达具体类型）。"""
    pin_msg = _build_node_pin_message(kind=4, index=int(out_index), var_type_int=int(var_type_int), connects=None)
    inner_empty = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
    concrete = _wrap_var_base_as_concrete_base(
        inner=inner_empty,
        index_of_concrete=(
            int(forced_index_of_concrete)
            if isinstance(forced_index_of_concrete, int) and int(forced_index_of_concrete) > 0
            else _infer_index_of_concrete_for_generic_pin(
                node_title=str(node_title),
                port_name=str(out_port),
                is_input=False,
                var_type_int=int(var_type_int),
                node_type_id_int=int(node_type_id_int),
                pin_index=int(out_index),
            )
        ),
    )
    pin_msg["3"] = dict(concrete)
    return format_binary_data_hex_text(encode_message(pin_msg))


def _find_existing_outparam_record_indices(*, records: List[Any], out_index: int) -> List[int]:
    """查找所有可替换的 OutParam record(kind=4,index=out_index,且非连线)。"""
    from ugc_file_tools.decode_gil import decode_bytes_to_python
    from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

    found: List[int] = []
    for i, record in enumerate(list(records)):
        if not isinstance(record, str) or not record.startswith("<binary_data>"):
            continue
        decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
        if not isinstance(decoded, dict):
            continue
        k = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
        idx = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
        idx_int = 0 if idx is None else int(idx)
        if int(k or -1) != 4:
            continue
        if idx_int != int(out_index):
            continue
        if "field_5" in decoded:
            continue
        found.append(int(i))
    return list(found)


def write_outparam_types_inplace(
    *,
    ctx: _ConstantsWritebackContext,
    state: _ConstantsWritebackNodeState,
    outparam_record_template_by_type_id_and_index_and_var_type: Dict[int, Dict[int, Dict[int, str]]],
) -> None:
    # 信号 META 绑定节点：不写 OutParam 类型（与原逻辑一致）
    if state.signal_binding_role != "":
        return

    # ===== 监听信号事件节点（GraphModel: node_def_ref.kind=event 且 outputs 含“信号来源实体”）=====
    # 对齐真源：该类事件节点的“信号参数输出端口”由信号规格动态展开；
    # 因此不应在 records 中保留/写入显式 OutParam(kind=4) 占位记录，否则会误导编辑器端口解释并导致错位。
    node_def_ref = state.node_payload.get("node_def_ref")
    if isinstance(node_def_ref, dict) and str(node_def_ref.get("kind") or "").strip().lower() == "event":
        outputs0 = state.node_payload.get("outputs")
        if isinstance(outputs0, list) and any(str(x) == "信号来源实体" for x in outputs0):
            from ugc_file_tools.decode_gil import decode_bytes_to_python
            from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

            kept_records: List[Any] = []
            for record in list(state.records):
                if not isinstance(record, str) or not record.startswith("<binary_data>"):
                    kept_records.append(record)
                    continue
                decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
                if not isinstance(decoded, dict):
                    kept_records.append(record)
                    continue
                kind = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
                if isinstance(kind, int) and int(kind) == 4:
                    continue
                kept_records.append(record)
            state.records[:] = kept_records
            return

    output_port_types_map = state.node_payload.get("output_port_types")
    if not isinstance(output_port_types_map, dict):
        # GraphModel(JSON) 产物中 output_port_types 可能缺失；此时仍可能需要根据其它真源推断 OUT_PARAM。
        output_port_types_map = {}

    outputs_value = state.node_payload.get("outputs")
    if isinstance(outputs_value, list):
        data_outputs = [
            str(p) for p in outputs_value if not _is_flow_port_by_node_def(node_def=state.node_def, port_name=str(p), is_input=False)
        ]
    else:
        data_outputs = []
    if not data_outputs:
        return

    node_type_id_int = int(state.node_type_id_int_for_node)
    for out_index, out_port_name in enumerate(data_outputs):
        # 对齐 after_game 行为：当「数据类型转换」的输出端口没有任何出边时，不强制写 OUT_PARAM 类型，
        # 保留模板默认值（真源导入/编译后常会裁剪其出边，且保留该节点 OUT_PARAM 为默认类型）。
        #
        # 证据来源：
        # - ctx.inferred_out_type_text 由 edges 推断而来：只包含“确实存在出边”的 (src_node_id, src_port)；
        # - 若 key 不存在，则说明该输出端口在本图中未被使用。
        if (
            is_writeback_feature_enabled("skip_unused_data_type_conversion_outparam_type_writeback")
            and (str(state.title) == "数据类型转换" or int(node_type_id_int) == 180)
            and str(out_port_name) == "输出"
        ):
            if (str(state.node_id), str(out_port_name)) not in dict(ctx.inferred_out_type_text or {}):
                # 去重模板残留重复 records（保持至少 1 个 record，避免写成“空端口”）
                existing_outparam_indices = _find_existing_outparam_record_indices(records=state.records, out_index=int(out_index))
                if len(existing_outparam_indices) > 1:
                    for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i)]
                continue

        out_declared_type_text = ""
        out_declared_map = state.node_payload.get("output_port_declared_types")
        if isinstance(out_declared_map, dict):
            dt = out_declared_map.get(out_port_name)
            if isinstance(dt, str):
                out_declared_type_text = dt.strip()
        if not out_declared_type_text:
            raw_out_type = output_port_types_map.get(out_port_name)
            if isinstance(raw_out_type, str):
                out_declared_type_text = raw_out_type.strip()
        if not out_declared_type_text:
            type_dict = getattr(state.node_def, "output_types", None)
            if isinstance(type_dict, dict):
                raw_out_type2 = type_dict.get(str(out_port_name))
                if isinstance(raw_out_type2, str):
                    out_declared_type_text = raw_out_type2.strip()
        if not out_declared_type_text:
            out_declared_type_text = "泛型"

        is_declared_generic_output = _is_declared_generic_port_type(str(out_declared_type_text))

        # ===== 清理模板残留的重复 OutParam records =====
        existing_outparam_indices = _find_existing_outparam_record_indices(records=state.records, out_index=int(out_index))
        forced_out_index_for_port = (
            state.forced_out_index_of_concrete_by_port.get(str(out_port_name))
            if isinstance(state.forced_out_index_of_concrete_by_port, dict)
            else None
        )

        # 特例：拼装字典 输出端口本体必须是“字典”(VarType=27)
        if str(state.title) == "拼装字典" and str(out_port_name) == "字典":
            key_type_text = str(_get_port_type_text(state.node_payload, "键0", is_input=True) or "").strip()
            val_type_text = str(_get_port_type_text(state.node_payload, "值0", is_input=True) or "").strip()
            if (not key_type_text) or (not val_type_text):
                continue
            key_vt = _map_server_port_type_to_var_type_id(key_type_text)
            val_vt = _map_server_port_type_to_var_type_id(val_type_text)

            empty = format_binary_data_hex_text(b"")
            map_base_inner: Dict[str, Any] = {
                "1": 10003,  # MapBase
                "4": _build_var_base_item_type_server_for_dict(
                    dict_key_var_type_int=int(key_vt),
                    dict_value_var_type_int=int(val_vt),
                ),
                "112": empty,  # empty MapBaseValue
            }
            var_base_outer = _wrap_var_base_as_concrete_base(inner=map_base_inner, index_of_concrete=None)
            pin_msg = _build_node_pin_message(
                kind=4,  # OutParam
                index=int(out_index),
                var_type_int=27,
                connects=None,
            )
            pin_msg["3"] = dict(var_base_outer)
            template_record_text = format_binary_data_hex_text(encode_message(pin_msg))

            if existing_outparam_indices:
                keep_i = int(existing_outparam_indices[0])
                state.records[keep_i] = template_record_text
                for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                    del state.records[int(del_i)]
            else:
                state.records.append(template_record_text)
            continue

        # 非泛型输出端口：不需要 OutParam record 表达具体类型（与写回合约/报告口径对齐）
        if not bool(is_declared_generic_output):
            if existing_outparam_indices:
                for del_i in sorted(existing_outparam_indices, reverse=True):
                    del state.records[int(del_i)]
            continue

        desired_type_text = str(_get_port_type_text(state.node_payload, str(out_port_name), is_input=False) or "").strip()
        if (not desired_type_text) or desired_type_text == "流程" or ("泛型" in desired_type_text):
            # 特例：节点图变量 Get/Set 的“变量值”类型以 graph_variables 为真源（typed JSON 可能缺失或被裁剪）。
            if str(state.title) in {"获取节点图变量", "设置节点图变量"} and str(out_port_name) == "变量值":
                graph_var_value_type_text = str(state.graph_var_value_type_text or "").strip()
                if (
                    graph_var_value_type_text != ""
                    and graph_var_value_type_text != "流程"
                    and ("泛型" not in graph_var_value_type_text)
                ):
                    desired_type_text = graph_var_value_type_text

        if (not desired_type_text) or desired_type_text == "流程" or ("泛型" in desired_type_text):
            # bisect/diagnostics：允许禁用“对泛型输出端口做兜底类型推断并写 OUT_PARAM”的修复分支，
            # 用于回到旧行为（保留模板默认值），以便在游戏侧二分定位“到底哪处推断导致可识别/不可识别”。
            if not is_writeback_feature_enabled("outparam_infer_types_for_generic_outputs"):
                if len(existing_outparam_indices) > 1:
                    for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i)]
                continue

            # 兜底：当 GraphModel 仅携带快照字段/或输出端口仍为“泛型”时，
            # 仍尝试从 shared 推断（edges/graph_variables/variant candidates）推导 OUT_PARAM 的 VarType，
            # 避免保留模板默认值导致端口类型错误（典型：局部变量/字典修改节点）。

            # 字典输出端口：若 Plan 已推断到 (K,V)，即便缺失别名字典文本，也应写出 MapBase(K,V)。
            if str(out_port_name) == "字典" and isinstance(state.dict_key_vt_for_node, int) and isinstance(state.dict_value_vt_for_node, int):
                key_vt, val_vt = int(state.dict_key_vt_for_node), int(state.dict_value_vt_for_node)

                empty = format_binary_data_hex_text(b"")
                map_base_inner = {
                    "1": 10003,  # MapBase
                    "4": _build_var_base_item_type_server_for_dict(
                        dict_key_var_type_int=int(key_vt),
                        dict_value_var_type_int=int(val_vt),
                    ),
                    "112": empty,
                }
                var_base_outer = _wrap_var_base_as_concrete_base(
                    inner=map_base_inner,
                    index_of_concrete=(
                        int(state.t_dict_out_index_of_concrete)
                        if isinstance(state.t_dict_out_index_of_concrete, int) and int(state.t_dict_out_index_of_concrete) > 0
                        else int(forced_out_index_for_port)
                        if isinstance(forced_out_index_for_port, int) and int(forced_out_index_for_port) > 0
                        else _infer_index_of_concrete_for_generic_pin(
                            node_title=str(state.title),
                            port_name=str(out_port_name),
                            is_input=False,
                            var_type_int=27,
                            node_type_id_int=int(node_type_id_int),
                            pin_index=int(out_index),
                        )
                    ),
                )
                pin_msg = _build_node_pin_message(kind=4, index=int(out_index), var_type_int=27, connects=None)
                pin_msg["3"] = dict(var_base_outer)
                template_record_text = format_binary_data_hex_text(encode_message(pin_msg))

                if existing_outparam_indices:
                    keep_i = int(existing_outparam_indices[0])
                    state.records[keep_i] = template_record_text
                    for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i)]
                else:
                    state.records.append(template_record_text)
                continue

            # Variant/Generic：若主泛型候选唯一，则用它来写 OUT_PARAM（避免端口保留模板默认值）。
            vt_candidates = {int(x) for x in set(state.variant_primary_vt_candidates or set()) if isinstance(x, int) and int(x) > 0}
            inferred_vt: Optional[int] = None
            if len(vt_candidates) == 1:
                inferred_vt = next(iter(vt_candidates))
            else:
                nep_node_record_for_node = ctx.nep_nodes_by_id.get(int(node_type_id_int))
                inferred_vt = int(
                    _resolve_server_var_type_int_for_port(
                        graph_scope=str(ctx.graph_scope),
                        node_id=str(state.node_id),
                        port_name=str(out_port_name),
                        is_input=False,
                        node_payload=state.node_payload,
                        graph_variable_type_text_by_name=dict(ctx.graph_variable_type_text_map),
                        inferred_out_type_text=dict(ctx.inferred_out_type_text),
                        inferred_in_type_text=dict(ctx.inferred_in_type_text),
                        raw_constant_value=None,
                        nep_node_record=nep_node_record_for_node,
                        nep_port_name=str(out_port_name),
                        nep_ordinal=int(out_index),
                    )
                )

            # 关键：若推断为“字典”(VarType=27)，必须写出 MapBase(K,V) 的 VarBase，
            # 即便端口名不是“字典”（典型：获取自定义变量/获取节点图变量 的 out_port="变量值"）。
            # 否则编辑器/运行时可能忽略该 OUT_PARAM record 并回退为 NodeEditorPack 默认类型（常见表现：字典被当成整数）。
            if isinstance(inferred_vt, int) and int(inferred_vt) == 27:
                inferred_type_text = str(ctx.inferred_out_type_text.get((str(state.node_id), str(out_port_name))) or "").strip()
                kv2 = _try_map_server_dict_type_text_to_kv_var_types(inferred_type_text)
                if kv2 is None:
                    raise ValueError(
                        "推断到字典 OUT_PARAM 但缺少可落地的 K/V 类型信息（禁止回退写入）："
                        f"title={str(state.title)!r} out_port={str(out_port_name)!r} inferred_type={inferred_type_text!r}"
                    )
                key_vt2, val_vt2 = int(kv2[0]), int(kv2[1])

                empty2 = format_binary_data_hex_text(b"")
                map_base_inner2: Dict[str, Any] = {
                    "1": 10003,  # MapBase
                    "4": _build_var_base_item_type_server_for_dict(
                        dict_key_var_type_int=int(key_vt2),
                        dict_value_var_type_int=int(val_vt2),
                    ),
                    "112": empty2,
                }
                var_base_outer2 = _wrap_var_base_as_concrete_base(
                    inner=map_base_inner2,
                    index_of_concrete=(
                        int(state.t_dict_out_index_of_concrete)
                        if isinstance(state.t_dict_out_index_of_concrete, int) and int(state.t_dict_out_index_of_concrete) > 0
                        else int(forced_out_index_for_port)
                        if isinstance(forced_out_index_for_port, int) and int(forced_out_index_for_port) > 0
                        else _infer_index_of_concrete_for_generic_pin(
                            node_title=str(state.title),
                            port_name=str(out_port_name),
                            is_input=False,
                            var_type_int=27,
                            node_type_id_int=int(node_type_id_int),
                            pin_index=int(out_index),
                        )
                    ),
                )
                pin_msg2 = _build_node_pin_message(kind=4, index=int(out_index), var_type_int=27, connects=None)
                pin_msg2["3"] = dict(var_base_outer2)
                template_record_text2 = format_binary_data_hex_text(encode_message(pin_msg2))

                if existing_outparam_indices:
                    keep_i2 = int(existing_outparam_indices[0])
                    state.records[keep_i2] = template_record_text2
                    for del_i2 in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i2)]
                else:
                    state.records.append(template_record_text2)
                continue

            if isinstance(inferred_vt, int) and int(inferred_vt) > 0 and int(inferred_vt) in _ALLOWED_OUTPARAM_VAR_TYPES:
                template_record_text = _build_outparam_record_text(
                    node_title=str(state.title),
                    node_type_id_int=int(node_type_id_int),
                    out_port=str(out_port_name),
                    out_index=int(out_index),
                    var_type_int=int(inferred_vt),
                    forced_index_of_concrete=(
                        int(forced_out_index_for_port)
                        if isinstance(forced_out_index_for_port, int) and int(forced_out_index_for_port) > 0
                        else None
                    ),
                )
                if existing_outparam_indices:
                    keep_i = int(existing_outparam_indices[0])
                    state.records[keep_i] = str(template_record_text)
                    for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i)]
                else:
                    state.records.append(str(template_record_text))
                continue

            # 没有可落地的具体类型：尽量保留一个现有 record，避免把端口类型写成空。
            if len(existing_outparam_indices) > 1:
                for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                    del state.records[int(del_i)]
            continue

        var_type_int = int(_map_server_port_type_to_var_type_id(desired_type_text))
        forced_out_index = (
            state.forced_out_index_of_concrete_by_port.get(str(out_port_name))
            if isinstance(state.forced_out_index_of_concrete_by_port, dict)
            else None
        )

        # Variant/Generic concrete_id 推断候选：主泛型 T 通常由“泛型输出端口”的具体类型决定。
        # 注：字典(27)需要额外依赖 K/V 与 TypeMappings(S<T:D<K,V>>) 解析 concrete_id，因此不放入候选集。
        # 特例：拼装列表(Assembly_List) 的输出端口类型是“列表容器类型”(L<T>)，
        # 但其 TypeMappings 的 concrete 映射使用的是“元素类型 T”（例如 Str=6 → concrete=170）。
        # 因此这里不要把列表 VarType(7/8/10/11/13/...) 加入候选集，否则会与输入侧的 T 候选冲突，
        # 导致 len(candidates)!=1 而无法写回 concrete runtime_id。
        if int(var_type_int) != 27 and not (str(state.title) == "拼装列表" and str(out_port_name) == "列表"):
            state.variant_primary_vt_candidates.add(int(var_type_int))

        # 字典 OUT_PARAM：必须显式写入 key/value 类型信息（MapBase.ItemType.type_server.field_101），
        # 否则编辑器可能回退显示为“实体-实体字典”，并进一步影响泛型收敛。
        if int(var_type_int) == 27:
            kv = _try_map_server_dict_type_text_to_kv_var_types(str(desired_type_text))
            # 特例：节点图变量 Get/Set 的“变量值”类型以 graph_variables 为真源（typed JSON 可能缺失或被裁剪）。
            if kv is None and state.graph_var_value_type_text and str(out_port_name) == "变量值":
                kv = _try_map_server_dict_type_text_to_kv_var_types(str(state.graph_var_value_type_text))
            if kv is None:
                raise ValueError(
                    "字典 OUT_PARAM 缺少可落地的 K/V 类型信息（禁止回退写入）："
                    f"title={str(state.title)!r} out_port={str(out_port_name)!r} desired_type={str(desired_type_text)!r} "
                    f"graph_var_value_type={str(state.graph_var_value_type_text or '')!r}"
                )
            if isinstance(kv, tuple) and len(kv) == 2:
                key_vt, val_vt = int(kv[0]), int(kv[1])

                # 单泛型 T=字典：用 TypeMappings(S<T:D<K,V>>) 解析 concrete_id 与 OUT_PARAM 的 indexOfConcrete
                # 说明：TypeMappings(S<T:D<K,V>>) 的 concrete/indexOfConcrete 决策由共享 Plan 统一计算（stage_prepare_node）。

                empty = format_binary_data_hex_text(b"")
                map_base_inner = {
                    "1": 10003,  # MapBase
                    "4": _build_var_base_item_type_server_for_dict(
                        dict_key_var_type_int=int(key_vt),
                        dict_value_var_type_int=int(val_vt),
                    ),
                    "112": empty,
                }
                var_base_outer = _wrap_var_base_as_concrete_base(
                    inner=map_base_inner,
                    index_of_concrete=(
                        int(state.t_dict_out_index_of_concrete)
                        if isinstance(state.t_dict_out_index_of_concrete, int) and int(state.t_dict_out_index_of_concrete) > 0
                        else None
                    ),
                )
                pin_msg = _build_node_pin_message(kind=4, index=int(out_index), var_type_int=27, connects=None)
                pin_msg["3"] = dict(var_base_outer)
                template_record_text = format_binary_data_hex_text(encode_message(pin_msg))

                if existing_outparam_indices:
                    keep_i = int(existing_outparam_indices[0])
                    state.records[keep_i] = template_record_text
                    for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                        del state.records[int(del_i)]
                else:
                    state.records.append(template_record_text)
                continue

        # 真源对齐：拼装列表的 OutParam（尤其是浮点数列表）需要正确的 indexOfConcrete（例如浮点数列表=4）。
        # 这里不依赖模板 outparam record，统一按 schema 构造最小 record。
        if str(state.title) == "拼装列表" and str(out_port_name) == "列表":
            template_record_text = _build_outparam_record_text(
                node_title=str(state.title),
                node_type_id_int=int(node_type_id_int),
                out_port=str(out_port_name),
                out_index=int(out_index),
                var_type_int=int(var_type_int),
                forced_index_of_concrete=forced_out_index,
            )
            if existing_outparam_indices:
                keep_i = int(existing_outparam_indices[0])
                state.records[keep_i] = str(template_record_text)
                for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                    del state.records[int(del_i)]
            else:
                state.records.append(str(template_record_text))
            continue

        templates_for_node = outparam_record_template_by_type_id_and_index_and_var_type.get(int(node_type_id_int), {})
        templates_for_index = templates_for_node.get(int(out_index), {})
        template_record_text = templates_for_index.get(int(var_type_int))
        if not isinstance(template_record_text, str):
            # 样本库未覆盖的 OutParam 组合：按 schema 构造最小 record（不再强依赖模板）。
            if int(var_type_int) not in set(int(v) for v in _ALLOWED_OUTPARAM_VAR_TYPES):
                continue
            template_record_text = _build_outparam_record_text(
                node_title=str(state.title),
                node_type_id_int=int(node_type_id_int),
                out_port=str(out_port_name),
                out_index=int(out_index),
                var_type_int=int(var_type_int),
                forced_index_of_concrete=forced_out_index,
            )

        # ===== 修复：模板残留可能漏写 indexOfConcrete（尤其是 K/V 双泛型节点的 OUT_PARAM）=====
        # 若我们能从 node_data TypeMappings 或显式 forced_out_index 推断出非零 index，则强制覆盖写入。
        if is_writeback_feature_enabled("outparam_fix_missing_index_of_concrete"):
            expected_index = (
                int(forced_out_index)
                if isinstance(forced_out_index, int) and int(forced_out_index) > 0
                else _infer_index_of_concrete_for_generic_pin(
                    node_title=str(state.title),
                    port_name=str(out_port_name),
                    is_input=False,
                    var_type_int=int(var_type_int),
                    node_type_id_int=int(node_type_id_int),
                    pin_index=int(out_index),
                )
            )
            if isinstance(expected_index, int) and int(expected_index) > 0:
                actual_index = _extract_index_of_concrete_from_outparam_record_text(str(template_record_text))
                if not isinstance(actual_index, int) or int(actual_index) != int(expected_index):
                    template_record_text = _build_outparam_record_text(
                        node_title=str(state.title),
                        node_type_id_int=int(node_type_id_int),
                        out_port=str(out_port_name),
                        out_index=int(out_index),
                        var_type_int=int(var_type_int),
                        forced_index_of_concrete=int(expected_index),
                    )

        # ===== 修复：模板/历史 record 可能把 list VarType 的 inner VarBase 写成 EnumBaseValue 等错误 cls =====
        # 这类错误在 Graph IR 层不一定可见，但官方校验可能更严格（VarType 与 VarBase.cls 必须一致）。
        if (
            is_writeback_feature_enabled("outparam_fix_wrong_inner_var_base_cls_for_list_types")
            and _should_rebuild_outparam_record_for_list_type(str(template_record_text), int(var_type_int))
        ):
            # 复用 record 内已有 indexOfConcrete（若存在），避免无谓漂移；否则回退 forced_out_index / 推断。
            existing_index = _extract_index_of_concrete_from_outparam_record_text(str(template_record_text))
            template_record_text = _build_outparam_record_text(
                node_title=str(state.title),
                node_type_id_int=int(node_type_id_int),
                out_port=str(out_port_name),
                out_index=int(out_index),
                var_type_int=int(var_type_int),
                forced_index_of_concrete=(
                    int(existing_index)
                    if isinstance(existing_index, int) and int(existing_index) > 0
                    else (int(forced_out_index) if isinstance(forced_out_index, int) and int(forced_out_index) > 0 else None)
                ),
            )

        if existing_outparam_indices:
            keep_i = int(existing_outparam_indices[0])
            state.records[keep_i] = str(template_record_text)
            for del_i in sorted(existing_outparam_indices[1:], reverse=True):
                del state.records[int(del_i)]
        else:
            state.records.append(str(template_record_text))

