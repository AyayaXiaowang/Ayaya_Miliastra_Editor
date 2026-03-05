from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

from ugc_file_tools.node_data_index import load_node_entry_by_id_map, resolve_default_node_data_index_path
from ugc_file_tools.node_graph_semantics.enum_codec import (
    build_entry_by_id_map as _build_entry_by_id_map,
    load_node_data_index_doc as _load_node_data_index_doc,
    resolve_enum_item_id_for_input_constant as _resolve_enum_item_id_for_input_constant,
)
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    resolve_input_port_name_for_type as _resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
    map_inparam_pin_index_for_node as _map_inparam_pin_index_for_node,
)
from ugc_file_tools.node_graph_semantics.nep_type_expr import (
    is_nep_reflection_type_expr as _is_nep_reflection_type_expr,
)
from ugc_file_tools.node_graph_semantics.signal_binding import (
    SIGNAL_NAME_PORT,
    build_listen_signal_binding_plan,
    build_send_signal_binding_plan,
    is_listen_signal_node_type,
    is_send_signal_node_type,
)
from ugc_file_tools.node_graph_semantics.type_binding_plan import (
    build_node_type_binding_plan,
    build_variant_concrete_plan,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server,
    build_var_base_message_server_empty,
    build_var_base_message_server_for_dict,
    coerce_constant_value_for_var_type as _coerce_constant_value_for_var_type,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)
from ugc_file_tools.contracts.node_graph_type_mappings import (
    try_resolve_t_dict_concrete_mapping as _contract_try_resolve_t_dict_concrete_mapping,
)
from ugc_file_tools.contracts.signal_meta_binding import (
    resolve_signal_meta_binding_param_pin_indices as _resolve_signal_meta_binding_param_pin_indices,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_declared_type_text as _get_port_declared_type_text,
    get_port_type_text as _get_port_type_text,
    infer_dict_kv_var_types_from_default_value as _infer_dict_kv_var_types_from_default_value,
    iter_list as _iter_list,
    parse_dict_key_value_var_types_from_port_type_text as _parse_dict_key_value_var_types_from_port_type_text,
    try_parse_dict_key_value_var_types_from_nep_type_expr as _try_parse_dict_kv_from_nep_type_expr,
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)

from .asset_bundle_builder_constants import _LIST_LIKE_VAR_TYPES
from .asset_bundle_builder_nep_pin_filler import fill_missing_pins_from_node_editor_pack
from .asset_bundle_builder_node_editor_pack import (
    _find_nep_pin_def,
    _resolve_pin_indices,
)
from .asset_bundle_builder_proto_helpers import (
    _make_pin_sig,
    _make_pin_sig_with_source_ref,
    _make_resource_locator,
    _pin_sig_kind_index,
    _pin_sort_key,
)
from .asset_bundle_builder_positions import build_node_positions
from .asset_bundle_builder_types import GiaAssetBundleGraphExportHints

def _try_resolve_t_dict_concrete_mapping(
    *,
    node_entry_by_id: dict[int, dict[str, Any]],
    node_type_id_int: int,
    dict_key_vt: int,
    dict_value_vt: int,
) -> tuple[int, int | None, int | None] | None:
    return _contract_try_resolve_t_dict_concrete_mapping(
        node_entry_by_id=dict(node_entry_by_id),
        node_type_id_int=int(node_type_id_int),
        dict_key_vt=int(dict_key_vt),
        dict_value_vt=int(dict_value_vt),
    )


def build_node_instances(
    *,
    graph_json_object: Dict[str, Any],
    graph_scope: str,
    consts: Mapping[str, Any],
    hints: GiaAssetBundleGraphExportHints,
    node_index_by_graph_node_id: Mapping[str, int],
    node_payload_by_graph_node_id: Mapping[str, Dict[str, Any]],
    node_type_id_int_by_graph_node_id: Mapping[str, int],
    node_is_composite_by_graph_node_id: Mapping[str, bool],
    node_record_by_graph_node_id: Mapping[str, Mapping[str, Any] | None],
    node_def_by_graph_node_id: Mapping[str, Any],
    flow_conns_by_src_pin: Mapping[Tuple[int, int], List[Dict[str, Any]]],
    data_conns_by_dst_pin: Mapping[Tuple[int, int], List[Dict[str, Any]]],
    inferred_out_type_text: Mapping[Tuple[str, str], str],
    inferred_in_type_text: Mapping[Tuple[str, str], str],
    graph_variable_type_text_by_name: Mapping[str, str],
    send_signal_nodes_with_signal_name_in_edge: set[str],
    listen_signal_nodes_with_signal_name_in_edge: set[str],
) -> List[Dict[str, Any]]:
    """
    GraphModel nodes → NodeInstance(field_4 pins ...) 列表构造。

    说明：
    - 该函数只负责构造 NodeInstance 列表，不负责组装 NodeGraph/AssetBundle 外层容器。
    - 依赖调用方已完成：NodeDef/NEP record 解析、类型推断、连接聚合（flow/data conns）。
    """
    node_instances: List[Dict[str, Any]] = []

    # enum 常量：需要把“中文选项”映射成 enum item id
    node_data_doc = _load_node_data_index_doc()
    node_entry_by_id = _build_entry_by_id_map(node_data_doc.get("NodesList"))
    enum_entry_by_id = _build_entry_by_id_map(node_data_doc.get("EnumList"))
    node_data_node_entry_by_id = load_node_entry_by_id_map(resolve_default_node_data_index_path())

    # === node positions（工程化：X 轴居中对齐） ===
    pos_by_graph_node_id, x_offset = build_node_positions(
        graph_json_object=graph_json_object,
        node_index_by_graph_node_id=node_index_by_graph_node_id,
        node_payload_by_graph_node_id=node_payload_by_graph_node_id,
        fallback_scale=float(getattr(hints, "node_pos_scale", 2.0)),
    )

    for graph_node_id, node_index_int in node_index_by_graph_node_id.items():
        payload = node_payload_by_graph_node_id.get(str(graph_node_id))
        if not isinstance(payload, dict):
            continue
        title = str(payload.get("title") or "").strip()
        if title == "":
            raise ValueError(f"node.title 为空：node_id={graph_node_id!r}")

        node_type_id_int = node_type_id_int_by_graph_node_id.get(str(graph_node_id))
        if not isinstance(node_type_id_int, int) or int(node_type_id_int) <= 0:
            raise KeyError(f"node_type_semantic_map 未覆盖该节点（无法导出 .gia）：{title!r}")
        is_composite = bool(node_is_composite_by_graph_node_id.get(str(graph_node_id), False))
        node_record = node_record_by_graph_node_id.get(str(graph_node_id))

        is_send_signal_node = bool(is_send_signal_node_type(int(node_type_id_int)))
        is_listen_signal_node = bool(is_listen_signal_node_type(int(node_type_id_int)))

        node_kind_int = 22001 if is_composite else int(consts["NodeKind"])

        x, y = pos_by_graph_node_id.get(str(graph_node_id), (0.0, 0.0))
        x = float(x) + float(x_offset)
        y = float(y)

        input_ports = list(_iter_list(payload.get("inputs")))
        output_ports = list(_iter_list(payload.get("outputs")))
        node_def = node_def_by_graph_node_id.get(str(graph_node_id))
        if node_def is None:
            raise KeyError(f"Graph_Generater 节点库未找到节点定义：node_id={graph_node_id!r} title={title!r}")

        input_constants = payload.get("input_constants")
        if not isinstance(input_constants, dict):
            input_constants = {}

        pins: List[Dict[str, Any]] = []

        composite_id_for_node = str(payload.get("composite_id") or "").strip() if bool(is_composite) else ""

        # Get_Local_Variable(type_id=18) 是 Variant/Generic 反射节点：
        # - 其 NodeInstance.concrete_id(field_3) 应写入具体 concrete id（例如 Str=2656），否则编辑器可能仍显示为“泛型”；
        # - 其 R<T> 端口（初始值/值）的 VarBase 必须用 ConcreteBase(field_110) 包装并写 indexOfConcrete。
        # 这里缓存“初始值”最终落盘的 VarType，用于后续决定 concrete_id。
        get_local_var_value_vt: int | None = None
        variant_primary_vt_candidates: set[int] = set()

        # 复合节点虚拟引脚的 pin_index（真源口径）映射：key=(kind_int, pin_name) -> pin_index_int
        composite_pin_index_by_kind_and_name: Dict[Tuple[int, str], int] | None = None

        def _ensure_composite_pin_index_map() -> Dict[Tuple[int, str], int]:
            nonlocal composite_pin_index_by_kind_and_name
            if composite_pin_index_by_kind_and_name is not None:
                return composite_pin_index_by_kind_and_name
            if composite_id_for_node == "":
                composite_pin_index_by_kind_and_name = {}
                return composite_pin_index_by_kind_and_name

            from engine.nodes.composite_node_manager import get_composite_node_manager

            manager = get_composite_node_manager(workspace_path=Path(hints.graph_generater_root).resolve(), verbose=False)
            if not manager.load_subgraph_if_needed(str(composite_id_for_node)):
                raise ValueError(f"复合节点子图加载失败：composite_id={composite_id_for_node!r}")
            composite = manager.get_composite_node(str(composite_id_for_node))
            if composite is None:
                raise ValueError(f"未找到复合节点定义：composite_id={composite_id_for_node!r}")

            mapping: Dict[Tuple[int, str], int] = {}
            for vp in list(getattr(composite, "virtual_pins", []) or []):
                pn = str(getattr(vp, "pin_name", "") or "").strip()
                if pn == "":
                    continue
                is_flow = bool(getattr(vp, "is_flow", False))
                is_input = bool(getattr(vp, "is_input", False))
                kind_int = 1 if (is_flow and is_input) else 2 if (is_flow and (not is_input)) else 3 if ((not is_flow) and is_input) else 4
                pin_index_int = int(getattr(vp, "pin_index", 0) or 0)
                mapping[(int(kind_int), str(pn))] = int(pin_index_int)

            composite_pin_index_by_kind_and_name = mapping
            return composite_pin_index_by_kind_and_name

        def _maybe_set_composite_pin_index(pin_msg: Dict[str, Any], *, kind_int: int, port_name: str) -> None:
            """
            真源约定（gia.proto）：
            - NodePin.field_7 = compositePinIndex（仅在调用复合节点时写入）
            - 其值应对齐 CompositeDef 的 ControlFlow/ParameterFlow.pinIndex（field_8）
              用于在 ShellIndex/KernelIndex 发生漂移时仍能稳定对齐端口。
            """
            if composite_id_for_node == "":
                return
            pn = str(port_name or "").strip()
            if pn == "":
                return
            mapping = _ensure_composite_pin_index_map()
            pin_index = mapping.get((int(kind_int), str(pn)))
            if not isinstance(pin_index, int) or int(pin_index) <= 0:
                raise ValueError(
                    "复合节点虚拟引脚缺少稳定 pin_index（无法写入 compositePinIndex）："
                    f"composite_id={composite_id_for_node!r} kind_int={int(kind_int)} pin_name={pn!r} pin_index={pin_index!r}"
                )
            pin_msg["7"] = int(pin_index)

        send_signal_plan = build_send_signal_binding_plan(
            graph_node_id=str(graph_node_id),
            node_type_id_int=int(node_type_id_int),
            input_constants=input_constants,
            send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge or set()),
            signal_send_node_def_id_by_signal_name=hints.signal_send_node_def_id_by_signal_name,
            signal_send_signal_name_port_index_by_signal_name=hints.signal_send_signal_name_port_index_by_signal_name,
            signal_send_param_port_indices_by_signal_name=hints.signal_send_param_port_indices_by_signal_name,
            signal_send_param_var_type_ids_by_signal_name=hints.signal_send_param_var_type_ids_by_signal_name,
            node_index_int=int(node_index_int),
        )
        listen_input_constants = dict(input_constants)
        # event 节点（GraphModel.kind="event"）的信号名通常体现在 node_def_ref.key / title，
        # 而不是作为 "信号名" 端口常量或入边。导出侧需把该信号名注入到 input_constants，
        # 供 META pins 绑定计划使用（保持 fail-fast：若取不到信号名仍会抛错）。
        node_def_ref = payload.get("node_def_ref")
        if isinstance(node_def_ref, Mapping) and str(node_def_ref.get("kind") or "").strip() == "event":
            if SIGNAL_NAME_PORT not in listen_input_constants:
                event_key = str(node_def_ref.get("key") or "").strip()
                if event_key:
                    listen_input_constants[SIGNAL_NAME_PORT] = event_key
                else:
                    title2 = str(payload.get("title") or "").strip()
                    if title2:
                        listen_input_constants[SIGNAL_NAME_PORT] = title2

        listen_signal_plan = build_listen_signal_binding_plan(
            graph_node_id=str(graph_node_id),
            node_type_id_int=int(node_type_id_int),
            input_constants=listen_input_constants,
            listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge or set()),
            listen_node_def_id_by_signal_name=hints.listen_node_def_id_by_signal_name,
            listen_signal_name_port_index_by_signal_name=hints.listen_signal_name_port_index_by_signal_name,
            listen_param_port_indices_by_signal_name=hints.listen_param_port_indices_by_signal_name,
            node_index_int=int(node_index_int),
        )

        send_signal_use_meta_binding = bool(send_signal_plan.use_meta_binding) and bool(is_send_signal_node)
        listen_signal_use_meta_binding = bool(listen_signal_plan.use_meta_binding) and bool(is_listen_signal_node)

        resolved_signal_name: str | None = send_signal_plan.signal_name if bool(is_send_signal_node) else listen_signal_plan.signal_name
        send_node_def_id_int: int | None = send_signal_plan.send_node_def_id_int
        listen_node_def_id_int: int | None = listen_signal_plan.listen_node_def_id_int

        data_inputs_no_flow = [str(p) for p in input_ports if (not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=True))]
        if bool(is_send_signal_node):
            data_inputs = send_signal_plan.data_inputs_without_flow(input_ports=list(data_inputs_no_flow))
        elif bool(is_listen_signal_node):
            data_inputs = [p for p in list(data_inputs_no_flow) if (not bool(listen_signal_use_meta_binding) or str(p).strip() != SIGNAL_NAME_PORT)]
        else:
            data_inputs = list(data_inputs_no_flow)

        # === 类型/实例化(concrete) 决策 Plan：收敛字典 KV / t_dict(indexOfConcrete) / 拼装字典 concrete 选择 ===
        #
        # 说明：
        # - Plan 仅决定“应该是什么”（concrete/runtime_id/indexOfConcrete/KV），Writer 决定“怎么写”（生成式/写回式）。
        # - 导出侧仍保留其它 Writer 策略（例如 signal runtime 提升、pin 填充等）。
        type_plan = build_node_type_binding_plan(
            graph_scope=str(graph_scope),
            graph_node_id=str(graph_node_id),
            node_title=str(title),
            node_type_id_int=int(node_type_id_int),
            node_payload=payload,
            node_def=node_def,
            data_inputs=list(data_inputs),
            input_constants=dict(input_constants),
            node_entry_by_id=dict(node_data_node_entry_by_id),
            graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
            inferred_in_type_text=dict(inferred_in_type_text),
            inferred_out_type_text=dict(inferred_out_type_text),
            nep_node_record=node_record,
        )

        dict_key_vt_for_node = type_plan.dict_key_vt_for_node
        dict_value_vt_for_node = type_plan.dict_value_vt_for_node
        forced_concrete_runtime_id = type_plan.forced_concrete_runtime_id
        forced_index_of_concrete_by_port = type_plan.forced_index_of_concrete_by_port
        forced_out_index_of_concrete_by_port = type_plan.forced_out_index_of_concrete_by_port

        assembly_dict_forced_key_index_of_concrete: int | None = None
        assembly_dict_forced_value_index_of_concrete: int | None = None
        assembly_dict_should_write_len_pin = bool(type_plan.assembly_dict_should_write_len_pin)
        if int(node_type_id_int) == 1788 and isinstance(forced_index_of_concrete_by_port, dict):
            k_idx = forced_index_of_concrete_by_port.get("键")
            v_idx = forced_index_of_concrete_by_port.get("值")
            if isinstance(k_idx, int):
                assembly_dict_forced_key_index_of_concrete = int(k_idx)
            if isinstance(v_idx, int):
                assembly_dict_forced_value_index_of_concrete = int(v_idx)

        # === 补齐 IN_FLOW pins（复合节点无 NodeEditorPack 画像时必需）===
        # 说明：
        # - 非复合节点可依赖 NodeEditorPack 画像补齐缺失 pins；
        # - 复合节点没有 NodeEditorPack 记录，若不显式生成 IN_FLOW，则编辑器侧可能只显示端口但无法编辑数据输入默认值。
        flow_inputs = [str(p) for p in input_ports if _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=True)]
        for flow_in_index, port_name in enumerate(flow_inputs):
            flow_in_fallback_index = int(flow_in_index)
            flow_in_shell_index, flow_in_kernel_index = _resolve_pin_indices(
                node_record,
                is_flow=True,
                direction="In",
                port_name=str(port_name),
                ordinal=int(flow_in_index),
                fallback_index=int(flow_in_fallback_index),
            )
            in_flow_pin: Dict[str, Any] = {
                "1": _make_pin_sig(kind_int=1, index_int=int(flow_in_shell_index)),  # IN_FLOW
                "2": _make_pin_sig(kind_int=1, index_int=int(flow_in_kernel_index)),
            }
            if bool(is_composite):
                _maybe_set_composite_pin_index(in_flow_pin, kind_int=1, port_name=str(port_name))
            pins.append(in_flow_pin)

        # 真源对齐：多分支节点（type_id=3）的 “cases 列表” 决定编辑器展开多少个分支出口：
        # - IN_PARAM(index=0): 控制表达式（R<T>）
        # - IN_PARAM(index=1): cases（L<R<T>>），长度 = outflows-1（不含默认）
        #
        # GraphModel 中该端口常缺失（属于编译产物），且 input_constants 也未必显式携带。
        # 导出时必须基于“动态 outflow 端口”反推 cases，否则会出现：
        # - 导入后只剩默认分支；
        # - 或端口数量/索引与连线不一致导致分支错连。
        multibranch_cases_labels: list[str] | None = None
        multibranch_control_vt: int | None = None
        multibranch_cases_vt: int | None = None
        if int(node_type_id_int) == 3:
            flow_outputs_in_graph = [str(p) for p in output_ports if _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)]
            multibranch_cases_labels = [p for p in list(flow_outputs_in_graph) if str(p).strip() != "默认"]

            # 控制表达式只支持 整数/字符串；优先读取 GraphModel 的 input_port_types/effective_input_types。
            raw_control_type_text = ""
            ipt = payload.get("input_port_types")
            it = payload.get("effective_input_types")
            if isinstance(ipt, Mapping):
                raw_control_type_text = str(ipt.get("控制表达式") or "").strip()
            if raw_control_type_text == "" and isinstance(it, Mapping):
                raw_control_type_text = str(it.get("控制表达式") or "").strip()
            if raw_control_type_text in {"整数", "整数值", "int", "Int"}:
                multibranch_control_vt = 3
            else:
                multibranch_control_vt = 6  # 默认按字符串
            multibranch_cases_vt = 8 if int(multibranch_control_vt) == 3 else 11
            # Variant/Generic 节点 concrete_id 需要由“主泛型 T”决定：
            # - Multiple_Branches 的 cases pin 是 L<R<T>>（list varType），不能用 list 的 VarType 作为 T。
            # - 这里提前把控制表达式的基础类型（Int/Str）加入候选集，供后续 TypeMappings 反推 concrete_id。
            variant_primary_vt_candidates.add(int(multibranch_control_vt))

            existing_cases = input_constants.get("判断参数")
            if existing_cases is None:
                existing_cases = input_constants.get("cases")
            if isinstance(existing_cases, list):
                cases_value = list(existing_cases)
            else:
                cases_value = list(multibranch_cases_labels)

            # 类型对齐：整数分支需落盘为 int 列表；字符串分支为 str 列表。
            if int(multibranch_control_vt) == 3:
                coerced_cases: list[int] = []
                for x in list(cases_value):
                    if isinstance(x, int):
                        coerced_cases.append(int(x))
                    else:
                        s = str(x).strip()
                        if not s or (not s.lstrip("-").isdigit()):
                            raise ValueError(f"Multiple_Branches cases 需要整数列表，但遇到非法值：{x!r}")
                        coerced_cases.append(int(s))
                cases_value = coerced_cases
            else:
                cases_value = [str(x) for x in list(cases_value)]

            # 统一使用中文端口名 “判断参数” 作为导出端口名（对齐内部口径；避免在其它规则里分裂）。
            input_constants["判断参数"] = list(cases_value)
            data_inputs = ["控制表达式", "判断参数"]

        # 真源对齐：拼装列表(Assembly_List, type_id=169) 的 data pins 结构为：
        # - IN_PARAM(index=0): 隐藏的“元素数量(Int)”（决定展开多少个 R<T> 元素输入）
        # - IN_PARAM(index=1..100): 元素输入（标签为 "0".."99"）
        #
        # GraphModel(JSON) 通常只包含元素输入端口（"0"/"1"/...），不包含 index=0 的隐藏计数端口。
        # 若不写入该计数端口，编辑器导入后会按 0 处理，从而隐藏/忽略元素输入（表现为“拼装列表填空不对/全空”）。
        if int(node_type_id_int) == 169:
            element_indices: list[int] = []
            for p in list(data_inputs):
                s = str(p or "").strip()
                if s.isdigit():
                    element_indices.append(int(s))
            element_count = (max(element_indices) + 1) if element_indices else 0
            count_shell_index, count_kernel_index = _resolve_pin_indices(
                node_record,
                is_flow=False,
                direction="In",
                port_name="",  # 兜底按顺序命中第一个 data pin（ShellIndex=0）
                ordinal=0,
                fallback_index=0,
            )
            pins.append(
                {
                    "1": _make_pin_sig(kind_int=3, index_int=int(count_shell_index)),  # IN_PARAM
                    "2": _make_pin_sig(kind_int=3, index_int=int(count_kernel_index)),
                    "3": build_var_base_message_server(var_type_int=3, value=int(element_count)),
                    "4": 3,  # Int
                }
            )

        # 拼装字典(Assembly_Dictionary, 1788)：
        # - pin0 为隐藏的 len(Int)，表示“键/值输入 pin 数量”（偶数）；
        # - 可见键值输入仍按 pin1.. 写入（键0=1, 值0=2 ...）。
        if int(node_type_id_int) == 1788 and bool(assembly_dict_should_write_len_pin):
            pair_indices: list[int] = []
            for p in list(data_inputs):
                s = str(p or "").strip()
                if len(s) >= 2 and (s[0] == "键" or s[0] == "值"):
                    suffix = s[1:]
                    if suffix.isdigit():
                        pair_indices.append(int(suffix))
            pair_count = (max(pair_indices) + 1) if pair_indices else 0
            kv_items_len = int(pair_count) * 2
            count_shell_index, count_kernel_index = _resolve_pin_indices(
                node_record,
                is_flow=False,
                direction="In",
                port_name="",
                ordinal=0,
                fallback_index=0,
            )
            pins.append(
                {
                    "1": _make_pin_sig(kind_int=3, index_int=int(count_shell_index)),
                    "2": _make_pin_sig(kind_int=3, index_int=int(count_kernel_index)),
                    "3": build_var_base_message_server(var_type_int=3, value=int(kv_items_len)),
                    "4": 3,
                }
            )

        for slot_index, port_name in enumerate(data_inputs):
            raw_port_name = str(port_name)
            # Multiple_Branches 的 cases 端口并非 Graph_Generater NodeDef 的显式输入（编译产物），
            # 这里直接使用原始端口名，避免 NodeDef 侧做“类型名归一化”导致找不到 pin。
            if int(node_type_id_int) == 3:
                resolved_port_name = str(raw_port_name)
            else:
                resolved_port_name = _resolve_input_port_name_for_type(node_def=node_def, port_name=str(raw_port_name))

            # “信号 meta binding” 节点（Send/Listen 的自包含 node_def 模式）：
            # 真源样本中 InParam 的 kernel index 通常固定为 0，仅依赖 compositePinIndex(field_7) 做稳定对齐；
            # 若把 kernel index 也写成 slot_index，会导致编辑器/游戏侧忽略默认值（表现为“填空全空”）。
            is_signal_meta_binding_node = bool(send_signal_use_meta_binding) or bool(listen_signal_use_meta_binding)
            if bool(is_signal_meta_binding_node):
                pin_shell_index, pin_kernel_index = _resolve_signal_meta_binding_param_pin_indices(slot_index=int(slot_index))
            else:
                if int(node_type_id_int) == 3:
                    # 真源对齐：Multiple_Branches 的 InParam 索引固定为 0/1（shell=kernel=slot_index）
                    pin_shell_index, pin_kernel_index = int(slot_index), int(slot_index)
                elif int(node_type_id_int) == 1788:
                    # 拼装字典：GraphModel.inputs 仅包含 键N/值N，可见 InParam 需映射到 pin1..。
                    pin_fallback_index = int(
                        _map_inparam_pin_index_for_node(
                            node_title=str(title),
                            port_name=str(raw_port_name),
                            slot_index=int(slot_index),
                        )
                    )
                    pin_shell_index, pin_kernel_index = int(pin_fallback_index), int(pin_fallback_index)
                else:
                    pin_fallback_index = int(_map_inparam_pin_index_for_node(node_title=str(title), port_name=str(raw_port_name), slot_index=int(slot_index)))
                    pin_shell_index, pin_kernel_index = _resolve_pin_indices(
                        node_record,
                        is_flow=False,
                        direction="In",
                        port_name=str(resolved_port_name),
                        ordinal=int(slot_index),
                        fallback_index=int(pin_fallback_index),
                    )

            raw_port_key = str(raw_port_name or "").strip()
            resolved_port_key = str(resolved_port_name or "").strip()
            has_constant = raw_port_key in input_constants or resolved_port_key in input_constants
            const_value = input_constants.get(raw_port_key) if raw_port_key in input_constants else input_constants.get(resolved_port_key)

            server_vt = _resolve_server_var_type_int_for_port(
                graph_scope=str(graph_scope),
                node_id=str(graph_node_id),
                port_name=str(raw_port_key),
                is_input=True,
                node_payload=payload,
                graph_variable_type_text_by_name=graph_variable_type_text_by_name,
                inferred_out_type_text=inferred_out_type_text,
                inferred_in_type_text=inferred_in_type_text,
                raw_constant_value=const_value,
                nep_node_record=node_record,
                nep_port_name=str(resolved_port_name),
                nep_ordinal=int(slot_index),
            )
            if int(node_type_id_int) == 3 and int(slot_index) == 0 and isinstance(multibranch_control_vt, int):
                server_vt = int(multibranch_control_vt)
            if int(node_type_id_int) == 3 and int(slot_index) == 1 and isinstance(multibranch_cases_vt, int):
                server_vt = int(multibranch_cases_vt)
            if bool(is_send_signal_node):
                server_vt = int(send_signal_plan.override_param_var_type(param_index=int(slot_index), fallback_var_type_int=int(server_vt)))

            # 字典泛型节点：键/值端口的 VarType 必须由“字典端口的 key/value 类型”决定（GraphModel 常误推为字符串）。
            raw_port_key = str(raw_port_name or "").strip()
            if isinstance(dict_key_vt_for_node, int) and isinstance(dict_value_vt_for_node, int):
                if raw_port_key == "键":
                    server_vt = int(dict_key_vt_for_node)
                elif raw_port_key == "值":
                    server_vt = int(dict_value_vt_for_node)
            pin_type_id = int(server_vt)

            declared_type_text = _get_port_declared_type_text(payload, raw_port_key, is_input=True)
            # 注意：
            # - declared_type_text 为空不等价于“泛型”；
            # - “信号 meta binding” 场景下，GraphModel 往往把参数端口标为“泛型”，但真源 .gia 的参数 pin
            #   仍按具体 VarType 直接写入基础 VarBase（不包 ConcreteBase）。若错误包一层 ConcreteBase，
            #   游戏导入后会丢默认值（表现为“填空类端口全空”）。
            force_reflection_concrete = False
            # 特例：Get_Local_Variable 的初始值端口在真源为 R<T>，必须按反射端口处理（写 ConcreteBase/indexOfConcrete）。
            if int(node_type_id_int) == 18 and str(raw_port_key) == "初始值":
                force_reflection_concrete = True
            # 特例：Multiple_Branches(type_id=3) 的控制表达式 pin（slot_index=0）在真源为 R<T>。
            if int(node_type_id_int) == 3 and int(slot_index) == 0:
                force_reflection_concrete = True
            # 特例：Multiple_Branches(type_id=3) 的 cases pin（slot_index=1）在真源为 L<R<T>>。
            if int(node_type_id_int) == 3 and int(slot_index) == 1:
                force_reflection_concrete = True

            # 通用：若 NodeEditorPack 画像中该 pin 为 R<T>/L<R<T>> 反射端口，则必须写 ConcreteBase。
            nep_hit = _find_nep_pin_def(
                node_record,
                is_flow=False,
                direction="In",
                port_name=str(resolved_port_name),
                ordinal=int(slot_index),
            )
            is_nep_reflection = bool(nep_hit is not None and _is_nep_reflection_type_expr(str(nep_hit.type_expr)))

            port_type_text = _get_port_type_text(payload, raw_port_key, is_input=True)
            if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                inferred_text = inferred_in_type_text.get((str(graph_node_id), str(raw_port_key)))
                if isinstance(inferred_text, str) and inferred_text.strip():
                    port_type_text = inferred_text.strip()

            dict_key_type_int: int | None = None
            dict_value_type_int: int | None = None
            if int(server_vt) == 27:
                kv = _parse_dict_key_value_var_types_from_port_type_text(str(port_type_text))
                if kv is None and title in {"获取节点图变量", "设置节点图变量"} and str(raw_port_key).strip() == "变量值":
                    # GraphModel 的 `变量值` 端口在 dict 场景下常保持为泛型/字典，
                    # 这里必须从 GraphVariables(name→type) 反推别名字典(K/V) 作为 KV 证据。
                    ic = payload.get("input_constants")
                    if isinstance(ic, Mapping):
                        var_name = ic.get("变量名")
                        if isinstance(var_name, str) and var_name.strip():
                            gv_text = str(graph_variable_type_text_by_name.get(var_name.strip()) or "").strip()
                            if gv_text:
                                port_type_text = gv_text
                                kv = _parse_dict_key_value_var_types_from_port_type_text(str(port_type_text))
                if kv is None and bool(has_constant):
                    kv = _infer_dict_kv_var_types_from_default_value(const_value)
                if kv is None and isinstance(declared_type_text, str) and declared_type_text.strip():
                    kv = _parse_dict_key_value_var_types_from_port_type_text(str(declared_type_text))
                if kv is None and nep_hit is not None:
                    kv = _try_parse_dict_kv_from_nep_type_expr(str(nep_hit.type_expr))
                if kv is None:
                    # 端口名可能携带 K/V（例如：字典_字符串到整数）
                    kv = _parse_dict_key_value_var_types_from_port_type_text(str(raw_port_key))
                if kv is None and isinstance(dict_key_vt_for_node, int) and isinstance(dict_value_vt_for_node, int):
                    # 泛型字典端口（如 D<R<K>,R<V>>）的具体 K/V 往往来自同节点的“键/值”端口或连线推断；
                    # 该信息已在 type_plan 中收敛，这里复用以构造 dict VarBase（.gia 必须携带 K/V）。
                    kv = (int(dict_key_vt_for_node), int(dict_value_vt_for_node))
                if kv is not None:
                    dict_key_type_int, dict_value_type_int = int(kv[0]), int(kv[1])

                    # 单泛型 T=字典：从 node_data TypeMappings(S<T:D<K,V>>) 解析 concrete_id 与 indexOfConcrete
                    # - 典型节点：获取/设置节点图变量（Get/Set_Node_Graph_Variable）
                    # - 若不写 NodeInstance.concrete_id / ConcreteBase.indexOfConcrete，编辑器会按默认 concrete 回退
                    need_t_dict_resolve = bool(
                        forced_concrete_runtime_id is None
                        or (not isinstance(forced_index_of_concrete_by_port, dict))
                        or (str(raw_port_key) not in forced_index_of_concrete_by_port)
                    )
                    if bool(need_t_dict_resolve):
                        resolved_t_dict = _try_resolve_t_dict_concrete_mapping(
                            node_entry_by_id=dict(node_data_node_entry_by_id),
                            node_type_id_int=int(node_type_id_int),
                            dict_key_vt=int(dict_key_type_int),
                            dict_value_vt=int(dict_value_type_int),
                        )
                        if resolved_t_dict is not None:
                            concrete_id_int3, in_idx3, _out_idx3 = resolved_t_dict
                            if isinstance(concrete_id_int3, int) and int(concrete_id_int3) > 0:
                                # 不覆盖其它更明确的 forced_concrete_runtime_id（如双泛型 K/V 字典节点）
                                if forced_concrete_runtime_id is None:
                                    forced_concrete_runtime_id = int(concrete_id_int3)
                            if isinstance(in_idx3, int) and int(in_idx3) > 0:
                                if forced_index_of_concrete_by_port is None:
                                    forced_index_of_concrete_by_port = {}
                                # 仅在本 pin 需要 ConcreteBase 时才有意义
                                forced_index_of_concrete_by_port.setdefault(str(raw_port_key), int(in_idx3))

            value_for_var_base: Any = None
            if bool(has_constant) and not (data_conns_by_dst_pin.get((int(node_index_int), int(pin_shell_index))) or []):
                value_for_var_base = const_value

            if int(server_vt) == 14 and value_for_var_base is not None and isinstance(value_for_var_base, (str, int)):
                node_type_id_int2 = int(node_type_id_int_by_graph_node_id.get(str(graph_node_id), 0))
                if node_type_id_int2 <= 0:
                    raise ValueError(f"enum 常量映射失败：node_type_id_int 无效：{title!r}")
                resolved_item_id = _resolve_enum_item_id_for_input_constant(
                    node_type_id_int=int(node_type_id_int2),
                    slot_index=int(slot_index),
                    port_name=str(raw_port_key),
                    raw_value=value_for_var_base,
                    node_def=node_def,
                    node_entry_by_id=node_entry_by_id,
                    enum_entry_by_id=enum_entry_by_id,
                )
                if resolved_item_id is not None:
                    value_for_var_base = int(resolved_item_id)
                else:
                    value_for_var_base = None

            if int(server_vt) == 27:
                if not isinstance(dict_key_type_int, int) or not isinstance(dict_value_type_int, int):
                    nep_expr = str(nep_hit.type_expr) if nep_hit is not None else ""
                    raise ValueError(
                        "字典端口缺少 key/value 类型："
                        f"node={title!r} port={raw_port_name!r} "
                        f"type_text={port_type_text!r} declared_type={declared_type_text!r} nep_type_expr={nep_expr!r}"
                    )
                inner_var_base = build_var_base_message_server_for_dict(
                    dict_key_var_type_int=int(dict_key_type_int),
                    dict_value_var_type_int=int(dict_value_type_int),
                    default_value=value_for_var_base,
                )
            elif value_for_var_base is None:
                inner_var_base = build_var_base_message_server_empty(var_type_int=int(server_vt))
            else:
                coerced = _coerce_constant_value_for_var_type(var_type_int=int(server_vt), raw_value=value_for_var_base)
                inner_var_base = build_var_base_message_server(var_type_int=int(server_vt), value=coerced)

            # 是否需要 ConcreteBase（反射/泛型端口）。
            #
            # 关键点：不要仅凭 declared_type_text 包含“泛型”就包 ConcreteBase。
            # - 对 “信号 meta binding” 的参数端口，真源使用基础 VarBase（不包 ConcreteBase）；
            # - 只有“反射端口（R<T>/L<R<T>>）”或少数已知反射特例才需要 ConcreteBase/indexOfConcrete。
            _ = declared_type_text  # 保留变量：用于解释性注释（避免误用“泛型”判断）
            wrap_as_concrete_base = bool(is_nep_reflection) or bool(force_reflection_concrete)

            # 对齐回归：当类型 Plan 已能稳定给出该端口的 indexOfConcrete 时，说明该端口属于“泛型家族/需要 ConcreteBase”。
            # 典型：对字典设置或新增键值对(948) 的 键/值 端口（GraphModel 仍为泛型，但连线已收敛到具体 dict(K,V)）。
            if (not bool(is_signal_meta_binding_node)) and isinstance(forced_index_of_concrete_by_port, dict):
                if str(raw_port_key) in forced_index_of_concrete_by_port:
                    wrap_as_concrete_base = True

            # NodeEditorPack 缺失时（repo 未包含第三方 node_data/data.json），仍需尽可能对齐真源：
            # - GraphModel 端口可能标注为“泛型”，但通过连线/常量/类型推断已收敛出具体 VarType；
            # - 若该端口能稳定推断出 indexOfConcrete，则说明它属于“反射/泛型端口”族（需要 ConcreteBase），
            #   否则导入到编辑器会显示为“泛型”并与金样快照不一致。
            if (not bool(wrap_as_concrete_base)) and (not bool(is_signal_meta_binding_node)):
                # NodeEditorPack 缺失时：用“能否稳定推断 indexOfConcrete”反推出该端口是否属于泛型家族。
                node_type_id_int3_for_hint = int(node_type_id_int_by_graph_node_id.get(str(graph_node_id), 0))
                port_name_for_concrete_hint = (
                    str(raw_port_name) if int(node_type_id_int) == 3 else str(resolved_port_name)
                )
                inferred_hint_index = _infer_index_of_concrete_for_generic_pin(
                    node_title=str(title),
                    port_name=str(port_name_for_concrete_hint),
                    is_input=True,
                    var_type_int=int(server_vt),
                    node_type_id_int=int(node_type_id_int3_for_hint),
                    pin_index=int(pin_shell_index),
                )
                if isinstance(inferred_hint_index, int):
                    wrap_as_concrete_base = True
            index_of_concrete = None
            if bool(wrap_as_concrete_base):
                node_type_id_int3 = int(node_type_id_int_by_graph_node_id.get(str(graph_node_id), 0))
                forced_index = None
                if int(node_type_id_int) == 1788:
                    if isinstance(assembly_dict_forced_key_index_of_concrete, int) and raw_port_key.startswith("键"):
                        forced_index = int(assembly_dict_forced_key_index_of_concrete)
                    elif isinstance(assembly_dict_forced_value_index_of_concrete, int) and raw_port_key.startswith("值"):
                        forced_index = int(assembly_dict_forced_value_index_of_concrete)
                if forced_index is None:
                    forced_index = (
                        forced_index_of_concrete_by_port.get(raw_port_key)
                        if isinstance(forced_index_of_concrete_by_port, dict) and raw_port_key in forced_index_of_concrete_by_port
                        else None
                    )
                if isinstance(forced_index, int):
                    index_of_concrete = int(forced_index)
                else:
                    port_name_for_concrete = (
                        str(raw_port_name) if int(node_type_id_int) == 3 else str(resolved_port_name)
                    )
                    index_of_concrete = _infer_index_of_concrete_for_generic_pin(
                        node_title=str(title),
                        port_name=str(port_name_for_concrete),
                        is_input=True,
                        var_type_int=int(server_vt),
                        node_type_id_int=int(node_type_id_int3),
                        pin_index=int(pin_shell_index),
                    )
                var_base = _wrap_var_base_as_concrete_base(inner=inner_var_base, index_of_concrete=index_of_concrete)
            else:
                var_base = dict(inner_var_base)

            if int(node_type_id_int) == 18 and str(raw_port_key) == "初始值":
                get_local_var_value_vt = int(server_vt)
            if bool(wrap_as_concrete_base) and isinstance(server_vt, int):
                # Multiple_Branches(type_id=3)：
                # - slot_index=0: R<T>（基础类型 Int/Str）
                # - slot_index=1: L<R<T>>（list 类型，不能作为 T）
                # 因此这里仅把“控制表达式”的基础类型计入候选集，避免 list VarType 干扰 concrete_id 选择。
                if int(node_type_id_int) == 3:
                    if isinstance(multibranch_control_vt, int):
                        variant_primary_vt_candidates.add(int(multibranch_control_vt))
                else:
                    variant_primary_vt_candidates.add(int(server_vt))

            pin_msg: Dict[str, Any] = {
                "1": _make_pin_sig(kind_int=3, index_int=int(pin_shell_index)),  # IN_PARAM
                "2": _make_pin_sig(kind_int=3, index_int=int(pin_kernel_index)),
                "4": int(pin_type_id),
            }
            # 真源对齐：对“已连线”的 InParam，部分节点（尤其是信号 meta binding）会省略 field_3(VarBase)。
            # 我们在这里按“有默认值或反射端口才写 VarBase”的口径落盘，以避免游戏侧把默认值判定为无效从而清空输入框。
            if value_for_var_base is not None or bool(wrap_as_concrete_base):
                pin_msg["3"] = dict(var_base)

            if bool(is_composite):
                _maybe_set_composite_pin_index(pin_msg, kind_int=3, port_name=str(raw_port_key))

            if bool(is_send_signal_node):
                pin_msg["7"] = int(send_signal_plan.param_composite_pin_index(param_index=int(slot_index), fallback_index=int(pin_shell_index)))

            conns = data_conns_by_dst_pin.get((int(node_index_int), int(pin_shell_index))) or []
            if conns:
                pin_msg["5"] = list(conns)

            pins.append(pin_msg)

        if bool(is_send_signal_node) and bool(send_signal_plan.has_meta_pin) and resolved_signal_name is not None:
            source_ref_id = int(send_node_def_id_int) if isinstance(send_node_def_id_int, int) and int(send_node_def_id_int) > 0 else None
            composite_pin_index = int(send_signal_plan.meta_pin_composite_index())
            meta_pin: Dict[str, Any] = {
                "1": _make_pin_sig_with_source_ref(kind_int=5, index_int=0, source_ref_id_int=source_ref_id),
                "2": _make_pin_sig_with_source_ref(kind_int=5, index_int=0, source_ref_id_int=source_ref_id),
                "3": build_var_base_message_server(var_type_int=6, value=str(resolved_signal_name)),
                "6": _make_pin_sig(kind_int=6, index_int=1),
            }
            if isinstance(composite_pin_index, int):
                meta_pin["7"] = int(composite_pin_index)
            pins.append(meta_pin)

        if bool(is_listen_signal_node) and bool(listen_signal_plan.has_meta_pin) and resolved_signal_name is not None:
            source_ref_id = int(listen_node_def_id_int) if isinstance(listen_node_def_id_int, int) and int(listen_node_def_id_int) > 0 else None
            composite_pin_index = int(listen_signal_plan.meta_pin_composite_index())
            listen_meta_pin: Dict[str, Any] = {
                "1": _make_pin_sig_with_source_ref(kind_int=5, index_int=0, source_ref_id_int=source_ref_id),
                "2": _make_pin_sig_with_source_ref(kind_int=5, index_int=0, source_ref_id_int=source_ref_id),
                "3": build_var_base_message_server(var_type_int=6, value=str(resolved_signal_name)),
                "6": _make_pin_sig(kind_int=6, index_int=1),
            }
            listen_meta_pin["7"] = int(composite_pin_index)
            pins.append(listen_meta_pin)

        data_outputs = [str(p) for p in output_ports if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)]
        for out_index, port_name in enumerate(data_outputs):
            server_vt = _resolve_server_var_type_int_for_port(
                graph_scope=str(graph_scope),
                node_id=str(graph_node_id),
                port_name=str(port_name),
                is_input=False,
                node_payload=payload,
                graph_variable_type_text_by_name=graph_variable_type_text_by_name,
                inferred_out_type_text=inferred_out_type_text,
                inferred_in_type_text=inferred_in_type_text,
                raw_constant_value=None,
                nep_node_record=node_record,
                nep_port_name=str(port_name),
                nep_ordinal=int(out_index),
            )
            pin_type_id = int(server_vt)
            # Get_Local_Variable(type_id=18)：真源端口顺序为：
            # - OUT_PARAM(index=0): Loc（固定句柄）
            # - OUT_PARAM(index=1): 值
            #
            # GraphModel 常只携带“值”端口。为保证导出稳定，需要把“值”的 fallback_index 提升为 1，
            # 让后续补齐的 Loc 占用 index=0（与回归用例/真源一致）。
            out_fallback_index = int(out_index)
            if int(node_type_id_int) == 18 and str(port_name).strip() == "值":
                out_fallback_index = 1

            out_shell_index, out_kernel_index = _resolve_pin_indices(
                node_record,
                is_flow=False,
                direction="Out",
                port_name=str(port_name),
                ordinal=int(out_index),
                fallback_index=int(out_fallback_index),
            )
            declared_out_type_text = _get_port_declared_type_text(payload, str(port_name), is_input=False)
            is_declared_generic_out = "泛型" in declared_out_type_text
            # 特例：Get_Local_Variable 的 “值” 输出端口在真源为 R<T>，必须按泛型反射端口处理（写 ConcreteBase/indexOfConcrete）。
            if int(node_type_id_int) == 18 and str(port_name).strip() == "值":
                is_declared_generic_out = True
            # 通用：若 NodeEditorPack 画像中该 pin 为 R<T>/L<R<T>> 反射端口，则必须写 ConcreteBase。
            nep_hit_out = _find_nep_pin_def(
                node_record,
                is_flow=False,
                direction="Out",
                port_name=str(port_name),
                ordinal=int(out_index),
            )
            is_nep_reflection_out = bool(nep_hit_out is not None and _is_nep_reflection_type_expr(str(nep_hit_out.type_expr)))
            if bool(is_nep_reflection_out):
                is_declared_generic_out = True
            out_var_base_inner: Dict[str, Any]
            if int(server_vt) == 27:
                port_type_text = _get_port_type_text(payload, str(port_name), is_input=False)
                if (not port_type_text) or ("泛型" in str(port_type_text)):
                    inferred_text = inferred_out_type_text.get((str(graph_node_id), str(port_name)))
                    if isinstance(inferred_text, str) and inferred_text.strip() and ("泛型" not in inferred_text):
                        port_type_text = inferred_text.strip()
                if (not port_type_text) or ("泛型" in str(port_type_text)):
                    if title in {"获取节点图变量", "设置节点图变量"} and str(port_name).strip() == "变量值":
                        ic = payload.get("input_constants")
                        if isinstance(ic, Mapping):
                            var_name = ic.get("变量名")
                            if isinstance(var_name, str) and var_name.strip():
                                gv_text = str(graph_variable_type_text_by_name.get(var_name.strip()) or "").strip()
                                if gv_text:
                                    port_type_text = gv_text

                kv = _parse_dict_key_value_var_types_from_port_type_text(str(port_type_text))
                if kv is None and isinstance(declared_out_type_text, str) and declared_out_type_text.strip():
                    kv = _parse_dict_key_value_var_types_from_port_type_text(str(declared_out_type_text))
                if kv is None and nep_hit_out is not None:
                    kv = _try_parse_dict_kv_from_nep_type_expr(str(nep_hit_out.type_expr))
                if kv is None:
                    # 端口名可能携带 K/V（例如：字典_字符串到整数）
                    kv = _parse_dict_key_value_var_types_from_port_type_text(str(port_name))
                if kv is None and isinstance(dict_key_vt_for_node, int) and isinstance(dict_value_vt_for_node, int):
                    kv = (int(dict_key_vt_for_node), int(dict_value_vt_for_node))
                if kv is None:
                    nep_out_expr = str(nep_hit_out.type_expr) if nep_hit_out is not None else ""
                    raise ValueError(
                        "字典 OUT_PARAM 缺少 key/value 类型信息，可能导致编辑器断线："
                        f"node={title!r} port={str(port_name)!r} "
                        f"type_text={port_type_text!r} declared_type={declared_out_type_text!r} nep_type_expr={nep_out_expr!r}"
                    )

                # 单泛型 T=字典：从 node_data TypeMappings(S<T:D<K,V>>) 解析 concrete_id 与 out 的 indexOfConcrete
                need_t_dict_resolve_out = bool(
                    forced_concrete_runtime_id is None
                    or (not isinstance(forced_out_index_of_concrete_by_port, dict))
                    or (str(port_name) not in forced_out_index_of_concrete_by_port)
                )
                if bool(need_t_dict_resolve_out):
                    resolved_t_dict_out = _try_resolve_t_dict_concrete_mapping(
                        node_entry_by_id=dict(node_data_node_entry_by_id),
                        node_type_id_int=int(node_type_id_int),
                        dict_key_vt=int(kv[0]),
                        dict_value_vt=int(kv[1]),
                    )
                    if resolved_t_dict_out is not None:
                        concrete_id_int4, _in_idx4, out_idx4 = resolved_t_dict_out
                        if isinstance(concrete_id_int4, int) and int(concrete_id_int4) > 0:
                            if forced_concrete_runtime_id is None:
                                forced_concrete_runtime_id = int(concrete_id_int4)
                        if isinstance(out_idx4, int) and int(out_idx4) > 0:
                            if forced_out_index_of_concrete_by_port is None:
                                forced_out_index_of_concrete_by_port = {}
                            forced_out_index_of_concrete_by_port.setdefault(str(port_name), int(out_idx4))
                out_var_base_inner = build_var_base_message_server_for_dict(
                    dict_key_var_type_int=int(kv[0]),
                    dict_value_var_type_int=int(kv[1]),
                    default_value=None,
                )
            else:
                out_var_base_inner = build_var_base_message_server_empty(var_type_int=int(server_vt))
            if int(server_vt) in _LIST_LIKE_VAR_TYPES or int(server_vt) == 27 or bool(is_declared_generic_out):
                node_type_id_int4 = int(node_type_id_int_by_graph_node_id.get(str(graph_node_id), 0))
                forced_out_idx = (
                    forced_out_index_of_concrete_by_port.get(str(port_name))
                    if isinstance(forced_out_index_of_concrete_by_port, dict)
                    else None
                )
                if isinstance(forced_out_idx, int) and int(forced_out_idx) > 0:
                    index_of_concrete = int(forced_out_idx)
                else:
                    # 真源对齐：多数字典 OUT_PARAM 的 ConcreteBase 不写 indexOfConcrete（仅依赖 KV 类型描述即可稳定显示）。
                    # 例外：单泛型反射节点（TypeMappings: S<T:D<K,V>>）需要按 TypeMappings 写入 indexOfConcrete（常见为 20）。
                    # 若写错 indexOfConcrete，编辑器可能会忽略/错配 KV 类型，回退为 D<?,?> 或断线。
                    index_of_concrete = None if int(server_vt) == 27 else _infer_index_of_concrete_for_generic_pin(
                        node_title=str(title),
                        port_name=str(port_name),
                        is_input=False,
                        var_type_int=int(server_vt),
                        node_type_id_int=int(node_type_id_int4),
                        pin_index=int(out_shell_index),
                    )
                out_var_base = _wrap_var_base_as_concrete_base(inner=out_var_base_inner, index_of_concrete=index_of_concrete)
            else:
                out_var_base = dict(out_var_base_inner)
            out_param_pin: Dict[str, Any] = {
                "1": _make_pin_sig(kind_int=4, index_int=int(out_shell_index)),  # OUT_PARAM
                "2": _make_pin_sig(kind_int=4, index_int=int(out_kernel_index)),
                "3": dict(out_var_base),
                "4": int(pin_type_id),
            }
            if bool(is_composite):
                _maybe_set_composite_pin_index(out_param_pin, kind_int=4, port_name=str(port_name))
            pins.append(out_param_pin)

            if bool(is_nep_reflection_out) and isinstance(server_vt, int):
                variant_primary_vt_candidates.add(int(server_vt))

        flow_outputs = [str(p) for p in output_ports if _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)]
        multibranch_needed_outflow_count: int | None = None
        if int(node_type_id_int) == 3 and isinstance(multibranch_cases_labels, list):
            # outflows = 1(default) + len(cases)
            multibranch_needed_outflow_count = 1 + len(list(multibranch_cases_labels))
            for out_i in range(int(multibranch_needed_outflow_count)):
                conns = flow_conns_by_src_pin.get((int(node_index_int), int(out_i))) or []
                out_flow_pin: Dict[str, Any] = {
                    "1": _make_pin_sig(kind_int=2, index_int=int(out_i)),  # OUT_FLOW
                    "2": _make_pin_sig(kind_int=2, index_int=int(out_i)),
                }
                if conns:
                    out_flow_pin["5"] = list(conns)
                pins.append(out_flow_pin)
        else:
            for flow_out_index, port_name in enumerate(flow_outputs):
                flow_shell_index, flow_kernel_index = _resolve_pin_indices(
                    node_record,
                    is_flow=True,
                    direction="Out",
                    port_name=str(port_name),
                    ordinal=int(flow_out_index),
                    fallback_index=int(flow_out_index),
                )
                conns = flow_conns_by_src_pin.get((int(node_index_int), int(flow_shell_index))) or []
                # 真源对齐：信号节点（发送/监听）在无连线时常省略 OUT_FLOW pin；
                # 导出侧不主动补齐（避免与金样快照漂移）。
                if (not conns) and (bool(is_send_signal_node) or bool(is_listen_signal_node)):
                    continue
                out_flow_pin = {
                    "1": _make_pin_sig(kind_int=2, index_int=int(flow_shell_index)),  # OUT_FLOW
                    "2": _make_pin_sig(kind_int=2, index_int=int(flow_kernel_index)),
                }
                if conns:
                    out_flow_pin["5"] = list(conns)
                if bool(is_composite):
                    _maybe_set_composite_pin_index(out_flow_pin, kind_int=2, port_name=str(port_name))
                pins.append(out_flow_pin)

        if isinstance(node_record, Mapping) and not (bool(is_send_signal_node) and bool(send_signal_use_meta_binding)):
            skip_ports = {
                str(x).strip()
                for x in (
                    (send_signal_plan.skip_input_ports if bool(is_send_signal_node) else listen_signal_plan.skip_input_ports) or set()
                )
                if str(x).strip()
            }
            fill_missing_pins_from_node_editor_pack(
                pins=pins,
                node_record=node_record,
                node_type_id_int=int(node_type_id_int),
                multibranch_needed_outflow_count=multibranch_needed_outflow_count,
                graph_scope=str(graph_scope),
                graph_node_id=str(graph_node_id),
                title=str(title),
                payload=payload,
                input_constants=input_constants,
                graph_variable_type_text_by_name=graph_variable_type_text_by_name,
                inferred_out_type_text=inferred_out_type_text,
                inferred_in_type_text=inferred_in_type_text,
                skip_ports=set(skip_ports),
            )

        # --- 真源对齐补齐：Get_Local_Variable(type_id=18) 的固定输出 pin（局部变量句柄 Loc） ---
        #
        # 说明：
        # - 该节点固定存在一个 Loc 输出（shell=0, kernel=0），GraphModel 可能会因“未被消费”而省略；
        # - 若最终 pins 中仍缺少 OUT_PARAM(0)，这里做最后兜底补齐，避免编辑器端口结构异常。
        if int(node_type_id_int) == 18:
            existing_out_param_indices: set[int] = set()
            for p in list(pins):
                if not isinstance(p, Mapping):
                    continue
                k, idx = _pin_sig_kind_index(p)
                if int(k) == 4:
                    existing_out_param_indices.add(int(idx))
            if 0 not in existing_out_param_indices:
                out_var_base_inner = build_var_base_message_server_empty(var_type_int=16)
                pins.append(
                    {
                        "1": _make_pin_sig(kind_int=4, index_int=0),  # OUT_PARAM
                        "2": _make_pin_sig(kind_int=4, index_int=0),
                        "3": dict(out_var_base_inner),
                        "4": 16,
                    }
                )

        pins.sort(key=_pin_sort_key)

        effective_runtime_id = int(node_type_id_int)
        # 真源对齐：
        # - Send_Signal(300000) 的 NodeInstance.runtime_id 必须保持 builtin runtime_id（300000）；
        #   send_node_def_id(0x6000xxxx) 仅用于 META pin 的 PinSignature.source_ref 去歧义。
        # - Listen_Signal(300001) 在命中“自包含 listen node_def_id(0x6000xxxx)”时，
        #   允许将 NodeInstance.runtime_id 替换为该 node_def_id，并将 kind 置为 22001（对齐开源工具/真源样本）。
        if bool(is_listen_signal_node) and isinstance(listen_node_def_id_int, int) and int(listen_node_def_id_int) > 0:
            effective_runtime_id = int(listen_node_def_id_int)
            node_kind_int = 22001

        # 真源对齐（golden snapshot）：
        # 当节点已被“信号规格/基底存档”提升为 signal-specific runtime_id（0x4000xxxx/0x4080xxxx）时，
        # 该节点在 `.gia` 中属于“自包含 NodeDef(kind=22001)”，而不是普通 builtin Node(kind=22000)。
        # 否则编辑器/工具链可能按 builtin 端口表解释，出现端口索引错位与快照漂移。
        if 0x40000000 <= int(effective_runtime_id) < 0x50000000:
            node_kind_int = 22001

        # Get_Local_Variable：补齐 NodeInstance.concrete_id（field_3）
        # concrete_id 应对应具体的 Variant KernelID（如 Str=2656），否则编辑器会按 generic id 显示为“泛型”。
        concrete_runtime_id = int(effective_runtime_id)
        if isinstance(get_local_var_value_vt, int):
            variant_primary_vt_candidates.add(int(get_local_var_value_vt))
        variant_plan = build_variant_concrete_plan(
            node_entry_by_id=dict(node_data_node_entry_by_id),
            node_type_id_int=int(effective_runtime_id),
            forced_concrete_runtime_id=(
                int(forced_concrete_runtime_id) if isinstance(forced_concrete_runtime_id, int) else None
            ),
            variant_primary_vt_candidates=set(int(x) for x in set(variant_primary_vt_candidates or set()) if isinstance(x, int)),
        )
        if isinstance(variant_plan.resolved_concrete_runtime_id, int) and int(variant_plan.resolved_concrete_runtime_id) > 0:
            concrete_runtime_id = int(variant_plan.resolved_concrete_runtime_id)

        node_locator_generic = _make_resource_locator(
            origin=int(consts["NodeOrigin"]),
            category=int(consts["NodeCategory"]),
            kind=int(node_kind_int),
            guid=0,
            runtime_id=int(effective_runtime_id),
        )
        node_locator_concrete = (
            _make_resource_locator(
                origin=int(consts["NodeOrigin"]),
                category=int(consts["NodeCategory"]),
                kind=int(node_kind_int),
                guid=0,
                runtime_id=int(concrete_runtime_id),
            )
            if int(concrete_runtime_id) != int(effective_runtime_id)
            else dict(node_locator_generic)
        )

        node_instances.append(
            {
                "1": int(node_index_int),
                "2": node_locator_generic,
                # 真源对齐：NodeInstance.concrete_id（field_3）需要存在。
                # 复合节点/部分节点在编辑器侧依赖该字段生成可编辑的输入参数 UI；
                # 真源样本通常令 concrete_id == generic_id。
                "3": node_locator_concrete,
                "4": pins,
                "5": float(x),
                "6": float(y),
            }
        )

    return node_instances

