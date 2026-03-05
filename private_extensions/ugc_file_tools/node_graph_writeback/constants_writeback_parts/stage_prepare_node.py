from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    is_declared_generic_port_type as _is_declared_generic_port_type,
    resolve_input_port_name_for_type as _resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.nep_type_expr import (
    is_nep_reflection_type_expr as _is_nep_reflection_type_expr,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
    parse_dict_key_value_var_types_from_port_type_text as _parse_dict_key_value_var_types_from_port_type_text,
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.signal_binding import (
    build_server_send_signal_binding_plan as _build_server_send_signal_binding_plan,
    build_listen_signal_binding_plan as _build_listen_signal_binding_plan,
    build_send_signal_binding_plan as _build_send_signal_binding_plan,
    is_listen_signal_node_type as _is_listen_signal_node_type,
    is_send_signal_node_type as _is_send_signal_node_type,
    is_server_send_signal_node_type as _is_server_send_signal_node_type,
)
from ugc_file_tools.node_graph_semantics.type_binding_plan import (
    build_node_type_binding_plan as _build_node_type_binding_plan,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)
from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text

from ..node_editor_pack import _find_nep_pin_def
from ..record_codec import _build_node_pin_message, _ensure_record_list, _extract_nested_int
from ..writeback_feature_flags import is_writeback_feature_enabled
from .types import _ConstantsWritebackContext, _ConstantsWritebackNodeState


def _prune_dynamic_inparam_constants_inplace(*, node_title: str, records: List[Any]) -> None:
    """
    动态端口节点：曾用于清理模板遗留的多余“常量 InParam pins”。

    结论更新（对齐 test4 校准样本后确认）：
    - 【拼装列表/拼装字典】的大量 InParam 常量 pin 不是“可删的噪音”，而是动态端口占位结构本体；
      删除会导致节点端口结构不完整/索引错位（例如拼装列表 pin0=数量 丢失、元素 pin 偏移错误）。
    - 因此当前实现不再清理这些 records。
    """
    return


def _prune_struct_modify_field_constant_records_inplace(*, records: List[Any]) -> None:
    """
    『修改结构体』节点：清理模板遗留的字段赋值常量（避免“模板默认值泄漏”导致未指定字段也被写入）。

    规则：
    - 仅清理 InParam(kind=3) 且 pin_index>=2 的“纯常量 record”（无 field_5 连接）；
    - pin0/pin1（结构体实例/结构体名）不动；OutParam/其它 record 不动。
    """
    kept: List[Any] = []
    for record in list(records):
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
        if int(kind or -1) == 3 and int(idx_int) >= 2 and ("field_5" not in decoded):
            continue
        kept.append(record)
    records[:] = kept


def _maybe_patch_assembly_list_pin0_count_inplace(*, node_title: str, records: List[Any], data_inputs: List[str]) -> None:
    # ===== 特例：拼装列表 pin0 为“元素数量”，需与当前 inputs 数量保持一致 =====
    if str(node_title) != "拼装列表" or not data_inputs:
        return
    desired_count = int(len(data_inputs))

    # 寻找并替换 pin_index=0 的“纯常量 InParam record”；若不存在则追加
    existing_record_index: Optional[int] = None
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
        if idx_int != 0:
            continue
        if "field_5" in decoded:
            continue
        existing_record_index = int(i)
        break

    # 对齐样本：pin0 为整数且不使用 ConcreteBase 包装（VarBase.cls=2）
    inner_var_base = _build_var_base_message_server(var_type_int=3, value=int(desired_count))
    pin_msg = _build_node_pin_message(kind=3, index=0, var_type_int=3, connects=None)
    pin_msg["3"] = dict(inner_var_base)
    record_text = format_binary_data_hex_text(encode_message(pin_msg))
    if isinstance(existing_record_index, int):
        records[existing_record_index] = record_text
    else:
        records.append(record_text)


def _maybe_patch_assembly_dict_pin0_len_inplace(
    *,
    node_title: str,
    records: List[Any],
    data_inputs: List[str],
    should_write_len_pin: bool,
) -> None:
    # ===== 特例：拼装字典 pin0 为“键/值端口数量(len)”，真源通常存在该隐藏 InParam =====
    if str(node_title) != "拼装字典":
        return

    # 约束：键/值成对出现
    desired_len = int(len(list(data_inputs or [])))
    if desired_len < 0:
        raise ValueError(f"拼装字典 data_inputs 非法：len={desired_len}")
    if desired_len % 2 != 0:
        raise ValueError(f"拼装字典 data_inputs 数量必须为偶数（键/值成对），got len={desired_len} data_inputs={data_inputs!r}")

    # concrete 特例：部分真源样本（如 Int-Bool）不写 pin0(len)
    if not bool(should_write_len_pin):
        kept: List[Any] = []
        for record in list(records):
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
            if int(kind or -1) == 3 and int(idx_int) == 0 and ("field_5" not in decoded):
                continue
            kept.append(record)
        records[:] = kept
        return

    # 寻找并替换 pin_index=0 的“纯常量 InParam record”；若不存在则追加
    existing_record_index: Optional[int] = None
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
        if idx_int != 0:
            continue
        if "field_5" in decoded:
            continue
        existing_record_index = int(i)
        break

    # 对齐样本：pin0 为整数且不使用 ConcreteBase 包装（VarBase.cls=2）
    inner_var_base = _build_var_base_message_server(var_type_int=3, value=int(desired_len))
    pin_msg = _build_node_pin_message(kind=3, index=0, var_type_int=3, connects=None)
    pin_msg["3"] = dict(inner_var_base)
    record_text = format_binary_data_hex_text(encode_message(pin_msg))
    if isinstance(existing_record_index, int):
        records[existing_record_index] = record_text
    else:
        records.append(record_text)


def prepare_node_state_for_constants_writeback(
    *,
    ctx: _ConstantsWritebackContext,
    node_item: Tuple[float, float, str, str, Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    signal_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_listen_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_server_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_send_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_param_var_type_ids_by_signal_name: Optional[Dict[str, List[int]]] = None,
    # base `.gil` 提取：signal_name -> signal_index_int（signal_entry.field_6）
    signal_index_by_signal_name: Optional[Dict[str, int]] = None,
) -> _ConstantsWritebackNodeState | None:
    (_y, _x, title, node_id, node_payload) = node_item
    node_def = node_defs_by_name.get(str(title))
    if node_def is None and isinstance(node_payload, dict):
        # 兼容：监听信号“事件节点”（GraphModel: node_def_ref.kind=event, title/key=信号名）。
        # 该节点在写回时会回退到通用 runtime（300001=监听信号），但 GraphModel.title 并不是节点库中的 NodeDef 名称。
        # 因此这里按事件节点语义回退使用【监听信号】NodeDef，以便后续阶段能正确判定流程口/端口顺序并执行必要的 records 修剪。
        node_def_ref = node_payload.get("node_def_ref")
        if isinstance(node_def_ref, dict) and str(node_def_ref.get("kind") or "").strip().lower() == "event":
            outputs0 = node_payload.get("outputs")
            if isinstance(outputs0, list) and any(str(x) == "信号来源实体" for x in outputs0):
                node_def = node_defs_by_name.get("监听信号")
    if node_def is None:
        return None

    node_id_int = int(node_id_int_by_graph_node_id[node_id])
    node_obj = node_object_by_node_id_int.get(int(node_id_int))
    if not isinstance(node_obj, dict):
        return None
    records = _ensure_record_list(node_obj)

    _prune_dynamic_inparam_constants_inplace(node_title=str(title), records=records)
    if str(title) == "修改结构体":
        _prune_struct_modify_field_constant_records_inplace(records=records)

    input_constants_raw = node_payload.get("input_constants")
    input_constants: Optional[Dict[str, Any]] = dict(input_constants_raw) if isinstance(input_constants_raw, dict) else None
    inputs_value = node_payload.get("inputs")
    data_inputs: List[str] = []
    if isinstance(inputs_value, list):
        data_inputs = [
            str(p)
            for p in inputs_value
            if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=True)
        ]

    variant_primary_vt_candidates: set[int] = set()
    node_type_id_int_for_node = int(node_type_id_by_graph_node_id.get(node_id, 0))

    nep_node_record_for_node = ctx.nep_nodes_by_id.get(int(node_type_id_int_for_node))
    type_plan = _build_node_type_binding_plan(
        graph_scope=str(ctx.graph_scope),
        graph_node_id=str(node_id),
        node_title=str(title),
        node_type_id_int=int(node_type_id_int_for_node),
        node_payload=node_payload,
        node_def=node_def,
        data_inputs=list(data_inputs),
        input_constants=(dict(input_constants) if isinstance(input_constants, dict) else None),
        node_entry_by_id=dict(ctx.node_entry_by_id),
        graph_variable_type_text_by_name=dict(ctx.graph_variable_type_text_map),
        inferred_in_type_text=dict(ctx.inferred_in_type_text),
        inferred_out_type_text=dict(ctx.inferred_out_type_text),
        nep_node_record=nep_node_record_for_node,
        enable_t_dict_inference_from_input_value_port=bool(
            is_writeback_feature_enabled("type_plan_t_dict_infer_from_input_value_port")
        ),
    )

    dict_key_vt_for_node = type_plan.dict_key_vt_for_node
    dict_value_vt_for_node = type_plan.dict_value_vt_for_node
    assembly_dict_key_vt_for_node = type_plan.assembly_dict_key_vt_for_node
    assembly_dict_value_vt_for_node = type_plan.assembly_dict_value_vt_for_node
    forced_concrete_runtime_id = type_plan.forced_concrete_runtime_id
    forced_index_of_concrete_by_port = type_plan.forced_index_of_concrete_by_port
    forced_out_index_of_concrete_by_port = type_plan.forced_out_index_of_concrete_by_port
    assembly_dict_should_write_len_pin = bool(type_plan.assembly_dict_should_write_len_pin)

    # ===== 节点图变量 Get/Set：非字典类型将“主泛型 T”加入候选集，用于后续按 TypeMappings 反推 concrete_id =====
    graph_var_value_type_text = str(type_plan.graph_var_value_type_text or "")
    t_dict_in_index_of_concrete = type_plan.t_dict_in_index_of_concrete
    t_dict_out_index_of_concrete = type_plan.t_dict_out_index_of_concrete
    if graph_var_value_type_text and graph_var_value_type_text != "流程" and ("泛型" not in graph_var_value_type_text):
        if _parse_dict_key_value_var_types_from_port_type_text(str(graph_var_value_type_text)) is None:
            if graph_var_value_type_text.startswith("结构体列表"):
                variant_primary_vt_candidates.add(26)
            elif graph_var_value_type_text.startswith("结构体"):
                variant_primary_vt_candidates.add(25)
            else:
                variant_primary_vt_candidates.add(int(_map_server_port_type_to_var_type_id(str(graph_var_value_type_text))))

    signal_binding_role = ""
    signal_binding_name = ""
    signal_binding_source_ref_node_def_id_int: Optional[int] = None
    signal_binding_param_port_indices: Optional[List[int]] = None
    signal_binding_signal_name_port_index: Optional[int] = None
    signal_binding_param_var_type_ids: Optional[List[int]] = None
    signal_binding_signal_index_int: Optional[int] = None

    def _try_lookup_signal_index(signal_name: str) -> Optional[int]:
        if not isinstance(signal_index_by_signal_name, dict):
            return None
        v = signal_index_by_signal_name.get(str(signal_name))
        if isinstance(v, int) and int(v) >= 0:
            return int(v)
        return None

    # 兼容：监听信号“事件节点”（GraphModel: node_def_ref.kind=event 且 outputs 含“信号来源实体”）
    # - 该节点可能缺失 input_constants['信号名'] / '__signal_id'
    # - 信号名可能出现在 node_def_ref.key 或 title（直接是信号名）
    node_def_ref = node_payload.get("node_def_ref")
    is_listen_signal_event_node = False
    listen_signal_name_from_event: str = ""
    if isinstance(node_def_ref, dict) and str(node_def_ref.get("kind") or "").strip().lower() == "event":
        outputs0 = node_payload.get("outputs")
        if isinstance(outputs0, list) and any(str(x) == "信号来源实体" for x in outputs0):
            is_listen_signal_event_node = True
            listen_signal_name_from_event = str(node_def_ref.get("key") or "").strip()
            if listen_signal_name_from_event == "":
                listen_signal_name_from_event = str(title).strip()

    if bool(is_listen_signal_event_node):
        # 为 META binding 兜底补齐信号名字符串常量（仅用于写回 META pins；不会写入常量 InParam pin）
        if input_constants is None:
            input_constants = {}
        existing_signal_name = input_constants.get("信号名")
        if not (isinstance(existing_signal_name, str) and str(existing_signal_name).strip()):
            input_constants["信号名"] = str(listen_signal_name_from_event).strip()

    if isinstance(input_constants, dict):
        # 注意：
        # - 即使 GraphModel 未携带隐藏语义键 `__signal_id`，只要“信号名端口无 data 入边 + 信号名为字符串常量”，
        #   仍应启用 META pins 绑定（与 `.gia` 导出同口径），否则参数 pins 会整体错位并导致真源侧报错。
        # - 当上游启用 prefer_signal_specific_type_id 时，信号节点的 node_type_id 可能已被替换为
        #   signal-specific runtime_id（常见 0x6000xxxx/0x6080xxxx）。但信号静态绑定（META pins）与参数 pin 编号规则
        #   仍应按『发送信号/监听信号/向服务器发送信号』的 canonical 语义执行。
        #
        # 因此：这里优先按 title 判定“信号节点语义类型”，并将 build_*_signal_binding_plan 的
        # node_type_id_int 固定为通用 runtime（300000/300001/300002）；避免在 prefer 开启时漏写 META pins。
        title_text = str(title)
        if title_text == "发送信号":
            send_plan = _build_send_signal_binding_plan(
                graph_node_id=str(node_id),
                node_type_id_int=300000,
                input_constants=input_constants,
                send_signal_nodes_with_signal_name_in_edge=set(ctx.send_signal_nodes_with_signal_name_in_edge),
                signal_send_node_def_id_by_signal_name=signal_send_node_def_id_by_signal_name,
                signal_send_signal_name_port_index_by_signal_name=signal_send_signal_name_port_index_by_signal_name,
                signal_send_param_port_indices_by_signal_name=signal_send_param_port_indices_by_signal_name,
                signal_send_param_var_type_ids_by_signal_name=signal_param_var_type_ids_by_signal_name,
                node_index_int=int(node_id_int),
            )
            if bool(send_plan.use_meta_binding):
                signal_binding_role = "send"
                signal_binding_name = str(send_plan.signal_name or "")
                signal_binding_signal_index_int = _try_lookup_signal_index(str(signal_binding_name))
                signal_binding_source_ref_node_def_id_int = (
                    int(send_plan.send_node_def_id_int) if isinstance(send_plan.send_node_def_id_int, int) else None
                )
                signal_binding_signal_name_port_index = (
                    int(send_plan.signal_name_port_index) if isinstance(send_plan.signal_name_port_index, int) else None
                )
                signal_binding_param_port_indices = (
                    list(send_plan.param_port_indices) if isinstance(send_plan.param_port_indices, list) else None
                )
                signal_binding_param_var_type_ids = (
                    list(send_plan.param_var_type_ids) if isinstance(send_plan.param_var_type_ids, list) else None
                )
        elif title_text == "监听信号" or bool(is_listen_signal_event_node):
            listen_plan = _build_listen_signal_binding_plan(
                graph_node_id=str(node_id),
                node_type_id_int=300001,
                input_constants=input_constants,
                listen_signal_nodes_with_signal_name_in_edge=set(ctx.listen_signal_nodes_with_signal_name_in_edge),
                listen_node_def_id_by_signal_name=signal_listen_node_def_id_by_signal_name,
                listen_signal_name_port_index_by_signal_name=signal_listen_signal_name_port_index_by_signal_name,
                listen_param_port_indices_by_signal_name=signal_listen_param_port_indices_by_signal_name,
                node_index_int=int(node_id_int),
            )
            if bool(listen_plan.use_meta_binding):
                signal_binding_role = "listen"
                signal_binding_name = str(listen_plan.signal_name or "")
                signal_binding_signal_index_int = _try_lookup_signal_index(str(signal_binding_name))
                signal_binding_source_ref_node_def_id_int = (
                    int(listen_plan.listen_node_def_id_int)
                    if isinstance(listen_plan.listen_node_def_id_int, int)
                    else None
                )
                signal_binding_signal_name_port_index = (
                    int(listen_plan.signal_name_port_index)
                    if isinstance(listen_plan.signal_name_port_index, int)
                    else None
                )
                signal_binding_param_port_indices = (
                    list(listen_plan.param_port_indices) if isinstance(listen_plan.param_port_indices, list) else None
                )
        elif title_text in {"发送信号到服务端", "向服务器节点图发送信号"}:
            server_plan = _build_server_send_signal_binding_plan(
                graph_node_id=str(node_id),
                node_type_id_int=300002,
                input_constants=input_constants,
                server_send_signal_nodes_with_signal_name_in_edge=set(ctx.server_send_signal_nodes_with_signal_name_in_edge),
                server_send_node_def_id_by_signal_name=signal_server_send_node_def_id_by_signal_name,
                server_send_signal_name_port_index_by_signal_name=signal_server_send_signal_name_port_index_by_signal_name,
                server_send_param_port_indices_by_signal_name=signal_server_send_param_port_indices_by_signal_name,
                signal_param_var_type_ids_by_signal_name=signal_param_var_type_ids_by_signal_name,
                node_index_int=int(node_id_int),
            )
            if bool(server_plan.use_meta_binding):
                signal_binding_role = "server_send"
                signal_binding_name = str(server_plan.signal_name or "")
                signal_binding_signal_index_int = _try_lookup_signal_index(str(signal_binding_name))
                signal_binding_source_ref_node_def_id_int = (
                    int(server_plan.server_send_node_def_id_int)
                    if isinstance(server_plan.server_send_node_def_id_int, int)
                    else None
                )
                signal_binding_signal_name_port_index = (
                    int(server_plan.signal_name_port_index)
                    if isinstance(server_plan.signal_name_port_index, int)
                    else None
                )
                signal_binding_param_port_indices = (
                    list(server_plan.param_port_indices) if isinstance(server_plan.param_port_indices, list) else None
                )
                signal_binding_param_var_type_ids = (
                    list(server_plan.param_var_type_ids) if isinstance(server_plan.param_var_type_ids, list) else None
                )

    # 信号节点（发送/监听/向服务器发送）：当“信号名”无入边且满足 META binding 时，
    # 按真实写法将其视为 META 绑定端口，不占用 data 端口索引位，避免参数 pin 整体错位。
    if (
        isinstance(input_constants, dict)
        and "信号名" in data_inputs
        and signal_binding_role != ""
    ):
        data_inputs = [p for p in data_inputs if p != "信号名"]

    _maybe_patch_assembly_list_pin0_count_inplace(node_title=str(title), records=records, data_inputs=list(data_inputs))
    _maybe_patch_assembly_dict_pin0_len_inplace(
        node_title=str(title),
        records=records,
        data_inputs=list(data_inputs),
        should_write_len_pin=bool(assembly_dict_should_write_len_pin),
    )

    # ===== Variant/Generic concrete 收敛：无常量时也要纳入“已知具体类型”的反射端口 =====
    if signal_binding_role == "" and data_inputs and str(title) not in {"发送信号", "监听信号", "发送信号到服务端"}:
        input_declared_types_map = node_payload.get("input_port_declared_types")
        nep_node_record_for_node = ctx.nep_nodes_by_id.get(int(node_type_id_int_for_node))
        for port_name in list(data_inputs):
            resolved_port_name = _resolve_input_port_name_for_type(node_def=node_def, port_name=str(port_name))
            declared_type_text = ""
            if isinstance(input_declared_types_map, dict):
                dt = input_declared_types_map.get(str(port_name))
                if isinstance(dt, str):
                    declared_type_text = dt.strip()
            if declared_type_text == "":
                declared_type_text = str(node_def.get_port_type(str(resolved_port_name), is_input=True) or "").strip()
            if not _is_declared_generic_port_type(str(declared_type_text)):
                continue

            slot_index = int(data_inputs.index(str(port_name)))

            nep_hit = _find_nep_pin_def(
                nep_node_record_for_node,
                is_flow=False,
                direction="In",
                port_name=str(resolved_port_name),
                ordinal=int(slot_index),
            )
            is_nep_reflection = bool(
                nep_hit is not None and _is_nep_reflection_type_expr(str(getattr(nep_hit, "type_expr", "") or ""))
            )
            force_reflection_concrete = bool(
                (int(node_type_id_int_for_node) == 18 and str(port_name) == "初始值")
                or (int(node_type_id_int_for_node) == 3 and int(slot_index) in (0, 1))
            )
            # 兼容：release/裁剪环境可能缺失 NodeEditorPack(data.json) 或缺少该 node_type_id 的画像。
            # 此时仍应尽量用 GraphModel typed JSON / edges 推断的端口类型收敛 concrete runtime_id，
            # 否则会导致 Variant/Generic 节点（如 Equal/Set_Local_Variable）无法写出 concrete_id，进而丢边。
            # 兼容：即便 NEP 节点画像存在，也可能因为端口名/ordinal 不一致导致无法命中 pin_def。
            # 此时仍应回退到 typed JSON / 连线推断收敛 concrete（避免 runtime_id 退化为 generic）。
            should_collect_variant = (
                bool(force_reflection_concrete)
                or bool(is_nep_reflection)
                or (nep_node_record_for_node is None)
                or (nep_hit is None)
            )
            if not bool(should_collect_variant):
                continue

            raw_constant_value: Any = None
            if isinstance(input_constants, dict):
                if str(port_name) in input_constants:
                    raw_constant_value = input_constants.get(str(port_name))
                elif str(resolved_port_name) in input_constants:
                    raw_constant_value = input_constants.get(str(resolved_port_name))

            port_type_text = str(_get_port_type_text(node_payload, str(port_name), is_input=True) or "").strip()
            if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                inferred_port_type = ctx.inferred_in_type_text.get((str(node_id), str(port_name)))
                if isinstance(inferred_port_type, str):
                    inferred_port_type_text = inferred_port_type.strip()
                    if inferred_port_type_text and inferred_port_type_text != "流程":
                        port_type_text = inferred_port_type_text
            if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                # 无有效类型信息时，仅在“端口有常量证据”场景允许继续推断；否则避免误用保守兜底字符串(6)造成错收敛。
                if raw_constant_value is None:
                    continue

            var_type_int = int(
                _resolve_server_var_type_int_for_port(
                    graph_scope=str(ctx.graph_scope),
                    node_id=str(node_id),
                    port_name=str(port_name),
                    is_input=True,
                    node_payload=node_payload,
                    graph_variable_type_text_by_name=dict(ctx.graph_variable_type_text_map),
                    inferred_out_type_text=dict(ctx.inferred_out_type_text),
                    inferred_in_type_text=dict(ctx.inferred_in_type_text),
                    raw_constant_value=raw_constant_value,
                    nep_node_record=nep_node_record_for_node,
                    nep_port_name=str(resolved_port_name),
                    nep_ordinal=int(slot_index),
                )
            )
            if int(var_type_int) <= 0 or int(var_type_int) == 27:
                continue
            # Multiple_Branches(type_id=3)：主泛型仅由 slot0 决定（与常量写回口径对齐）
            if int(node_type_id_int_for_node) == 3 and int(slot_index) != 0:
                continue
            variant_primary_vt_candidates.add(int(var_type_int))

    # ===== 对齐 after_game：确保『对字典设置或新增键值对』的『值』端口占位 pin 存在 =====
    # 说明：
    # - after_game 真源样本中该节点通常保留 InParam(index=2) 的占位 pin（未连线时 connects_count=0），用于稳定端口结构；
    # - 写回侧模板库可能挑到“缺少该 pin 的样本”，导致 direct 产物缺 pin（missing pins diff）。
    if is_writeback_feature_enabled("dict_set_value_pin2_ensure_placeholder") and str(title) == "对字典设置或新增键值对":
        desired_vt = int(dict_value_vt_for_node) if isinstance(dict_value_vt_for_node, int) and int(dict_value_vt_for_node) > 0 else 6
        has_pin2 = False
        for record in list(records):
            if not isinstance(record, str) or not record.startswith("<binary_data>"):
                continue
            decoded = decode_bytes_to_python(parse_binary_data_hex_text(record))
            if not isinstance(decoded, dict):
                continue
            kind0 = _extract_nested_int(decoded, ["field_1", "message", "field_1"])
            idx0 = _extract_nested_int(decoded, ["field_1", "message", "field_2"])
            idx0_int = 0 if idx0 is None else int(idx0)
            if int(kind0 or -1) == 3 and int(idx0_int) == 2:
                has_pin2 = True
                break
        if not has_pin2:
            # 对齐真源：该占位 pin 通常携带 ConcreteBase(indexOfConcrete=5) + 空字符串默认值。
            # 注意：目前只在 Str(6) 场景写入 indexOfConcrete=5，以避免其它类型误绑定。
            inner = (
                _build_var_base_message_server(var_type_int=int(desired_vt), value="")
                if int(desired_vt) == 6
                else _build_var_base_message_server_empty(var_type_int=int(desired_vt))
            )
            var_base = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=(5 if int(desired_vt) == 6 else None))
            pin_msg = _build_node_pin_message(kind=3, index=2, var_type_int=int(desired_vt), connects=None)
            pin_msg["3"] = dict(var_base)
            records.append(format_binary_data_hex_text(encode_message(pin_msg)))

    return _ConstantsWritebackNodeState(
        title=str(title),
        node_id=str(node_id),
        node_payload=dict(node_payload),
        node_def=node_def,
        node_id_int=int(node_id_int),
        node_obj=node_obj,
        records=records,
        data_inputs=list(data_inputs),
        node_type_id_int_for_node=int(node_type_id_int_for_node),
        input_constants=(dict(input_constants) if isinstance(input_constants, dict) else None),
        dict_key_vt_for_node=(int(dict_key_vt_for_node) if isinstance(dict_key_vt_for_node, int) else None),
        dict_value_vt_for_node=(int(dict_value_vt_for_node) if isinstance(dict_value_vt_for_node, int) else None),
        assembly_dict_key_vt_for_node=(
            int(assembly_dict_key_vt_for_node) if isinstance(assembly_dict_key_vt_for_node, int) else None
        ),
        assembly_dict_value_vt_for_node=(
            int(assembly_dict_value_vt_for_node) if isinstance(assembly_dict_value_vt_for_node, int) else None
        ),
        graph_var_value_type_text=str(graph_var_value_type_text),
        t_dict_in_index_of_concrete=(int(t_dict_in_index_of_concrete) if isinstance(t_dict_in_index_of_concrete, int) else None),
        t_dict_out_index_of_concrete=(int(t_dict_out_index_of_concrete) if isinstance(t_dict_out_index_of_concrete, int) else None),
        variant_primary_vt_candidates=set(int(x) for x in variant_primary_vt_candidates),
        forced_concrete_runtime_id=(int(forced_concrete_runtime_id) if isinstance(forced_concrete_runtime_id, int) else None),
        forced_index_of_concrete_by_port=(
            dict(forced_index_of_concrete_by_port) if isinstance(forced_index_of_concrete_by_port, dict) else None
        ),
        forced_out_index_of_concrete_by_port=(
            dict(forced_out_index_of_concrete_by_port)
            if isinstance(forced_out_index_of_concrete_by_port, dict)
            else None
        ),
        signal_binding_role=str(signal_binding_role),
        signal_binding_name=str(signal_binding_name),
        signal_binding_source_ref_node_def_id_int=(
            int(signal_binding_source_ref_node_def_id_int)
            if isinstance(signal_binding_source_ref_node_def_id_int, int)
            else None
        ),
        signal_binding_param_port_indices=(
            list(signal_binding_param_port_indices) if isinstance(signal_binding_param_port_indices, list) else None
        ),
        signal_binding_signal_name_port_index=(
            int(signal_binding_signal_name_port_index) if isinstance(signal_binding_signal_name_port_index, int) else None
        ),
        signal_binding_signal_index_int=(
            int(signal_binding_signal_index_int) if isinstance(signal_binding_signal_index_int, int) else None
        ),
        signal_binding_param_var_type_ids=(
            list(signal_binding_param_var_type_ids) if isinstance(signal_binding_param_var_type_ids, list) else None
        ),
    )

