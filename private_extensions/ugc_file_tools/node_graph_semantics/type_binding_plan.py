from __future__ import annotations

"""
ugc_file_tools.node_graph_semantics.type_binding_plan

节点图共享语义层：把“类型/实例化(concrete)/indexOfConcrete”的决策收敛成单一 Plan。

目的：
- `.gia` 导出（生成式）与 `.gil` 写回（写回式）在 Writer 策略上允许不同；
  但“如何决定 concrete/runtime_id、字典 K/V、各端口的 indexOfConcrete”应是单一真源，避免两条链路分叉漂移。
- 本模块只做“决策（Plan）”，不做任何 records/pins 的落盘与写回编排。

注意：
- 不使用 try/except；失败直接抛错（fail-fast）。
- 仅依赖 `node_graph_semantics/*` 与 `contracts/*`，禁止反向依赖导出/写回实现域。
"""

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Set, Tuple

from ugc_file_tools.contracts.node_graph_type_mappings import (
    resolve_concrete_id_from_node_data_type_mappings,
    try_map_list_var_type_to_element_var_type_int,
    try_resolve_dict_kv_concrete_mapping,
    try_resolve_t_concrete_mapping,
    try_resolve_t_dict_concrete_mapping,
)
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    parse_dict_key_value_var_types_from_port_type_text,
    resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
)
from ugc_file_tools.var_type_map import try_map_server_port_type_text_to_var_type_id as _try_map_server_port_type_text_to_var_type_id


@dataclass(frozen=True, slots=True)
class NodeTypeBindingPlan:
    """
    仅包含“语义决策结果”，不包含落盘结构（VarBase/pin_msg/records 等由 Writer 决定）。

    字段说明（按常见优先级）：
    - forced_concrete_runtime_id：能由 node_data TypeMappings 唯一确定时写入的 concrete runtime_id。
    - forced_index_of_concrete_by_port：输入端口 ConcreteBase.indexOfConcrete 的强制覆盖（按端口名）。
    - forced_out_index_of_concrete_by_port：输出端口 ConcreteBase.indexOfConcrete 的强制覆盖（按端口名）。
    - dict_key_vt_for_node/dict_value_vt_for_node：当节点存在 “字典” 入参端口时，解析得到的 (K,V) VarType。
      典型用途：将 “键/值” 端口从 GraphModel 的“泛型”收敛为具体 VarType，并用于 concrete 选择。
    - assembly_dict_*：拼装字典(1788) 的 (K,V) VarType（以 键0/值0 为真源证据收敛）。
    - t_dict_*：单泛型 T=字典（TypeMappings: S<T:D<K,V>>）节点的 in/out indexOfConcrete。
    - graph_var_value_type_text：Get/Set 节点图变量的 value type 文本（来自 graph_variables 表，作为真源兜底）。
    - assembly_dict_should_write_len_pin：拼装字典导出 `.gia` 时是否应写 pin0(len)（真源样本存在特例）。
    """

    graph_var_value_type_text: str = ""

    dict_key_vt_for_node: Optional[int] = None
    dict_value_vt_for_node: Optional[int] = None

    assembly_dict_key_vt_for_node: Optional[int] = None
    assembly_dict_value_vt_for_node: Optional[int] = None
    assembly_dict_should_write_len_pin: bool = True

    forced_concrete_runtime_id: Optional[int] = None
    forced_index_of_concrete_by_port: Optional[Dict[str, int]] = None
    forced_out_index_of_concrete_by_port: Optional[Dict[str, int]] = None

    t_dict_in_index_of_concrete: Optional[int] = None
    t_dict_out_index_of_concrete: Optional[int] = None


@dataclass(frozen=True, slots=True)
class VariantConcretePlan:
    """
    Variant/Generic 节点的 concrete runtime_id 决策 Plan。

    约定：
    - Plan 只负责“能否唯一确定 concrete_id（TypeMappings.ConcreteId）”；Writer 决定：
      - `.gia`：写入 NodeInstance.concrete_id
      - `.gil`：写入 NodeProperty(runtime_id)
      - 若无法确定：保留 generic id 或保留模板已有 concrete（写回侧特例）
    """

    resolved_concrete_runtime_id: Optional[int] = None
    primary_var_type_int: Optional[int] = None


def build_variant_concrete_plan(
    *,
    node_entry_by_id: Mapping[int, Mapping[str, Any]],
    node_type_id_int: int,
    forced_concrete_runtime_id: int | None,
    variant_primary_vt_candidates: Set[int] | Sequence[int] | None,
) -> VariantConcretePlan:
    """
    统一口径：按 node_data TypeMappings 解析 Variant/Generic 节点 concrete_id。

    优先级：
    - forced_concrete_runtime_id（来自更高优先级的语义决策，例如 dict K/V / t_dict）
    - 若主泛型候选 VarType 唯一，则用 TypeMappings(S<T:...>) 反推出 ConcreteId
    - 否则返回 None（Writer 做保守策略）
    """

    if isinstance(forced_concrete_runtime_id, int) and int(forced_concrete_runtime_id) > 0:
        return VariantConcretePlan(resolved_concrete_runtime_id=int(forced_concrete_runtime_id), primary_var_type_int=None)

    candidates: set[int] = set()
    raw = variant_primary_vt_candidates or []
    if isinstance(raw, set):
        candidates = {int(x) for x in raw if isinstance(x, int)}
    else:
        candidates = {int(x) for x in list(raw) if isinstance(x, int)}

    if len(candidates) != 1:
        # 兼容：对部分列表泛型节点，Writer 可能同时收集到：
        # - 列表容器 VarType（例如 实体列表=13）
        # - 元素 VarType（例如 实体=1）
        #
        # 这种情况下 `T` 的“主泛型”应以元素类型为准；若不做归一化，会导致 len(candidates)!=1，
        # runtime_id 无法写回，从而回退到 generic concrete（常见表现：列表迭代循环 导入后退化为布尔列表）。
        #
        # 规则：当同时存在 `L<T>` 与 `T` 时，丢弃 `L<T>`，保留 `T`。
        pruned = set(candidates)
        for vt in list(candidates):
            elem_vt = try_map_list_var_type_to_element_var_type_int(int(vt))
            if isinstance(elem_vt, int) and int(elem_vt) in pruned:
                pruned.discard(int(vt))
        candidates = set(pruned)

    if len(candidates) != 1:
        return VariantConcretePlan(resolved_concrete_runtime_id=None, primary_var_type_int=None)

    only_vt = next(iter(candidates))
    resolved = resolve_concrete_id_from_node_data_type_mappings(
        node_entry_by_id={
            int(k): dict(v)
            for k, v in dict(node_entry_by_id).items()
            if isinstance(k, int) and isinstance(v, Mapping)
        },
        node_type_id_int=int(node_type_id_int),
        var_type_int=int(only_vt),
    )
    if isinstance(resolved, int) and int(resolved) > 0:
        return VariantConcretePlan(resolved_concrete_runtime_id=int(resolved), primary_var_type_int=int(only_vt))
    return VariantConcretePlan(resolved_concrete_runtime_id=None, primary_var_type_int=int(only_vt))


def _normalize_port_name_set(data_inputs: Sequence[str]) -> set[str]:
    return {str(x).strip() for x in list(data_inputs) if str(x).strip() != ""}


def _get_input_port_type_text(node_payload: Mapping[str, Any], port_name: str) -> str:
    """
    获取输入端口类型文本（尽可能兼容不同 GraphModel JSON 形态）。

    约定优先级：
    - input_port_types：工具链 enrich 后的“具体类型”（可包含泛型端口的实例化结果）
    - effective_input_types：GraphModel/graph_cache 的类型快照
    - input_port_declared_types：NodeDef 声明类型（可能为“泛型/泛型字典”，通常仅用于固定类型端口兜底）
    """
    port = str(port_name or "").strip()
    if port == "":
        return ""
    for key in ("input_port_types", "effective_input_types", "input_port_declared_types"):
        type_map = node_payload.get(key)
        if not isinstance(type_map, Mapping):
            continue
        raw = type_map.get(port)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def _get_output_port_type_text(node_payload: Mapping[str, Any], port_name: str) -> str:
    """
    获取输出端口类型文本（尽可能兼容不同 GraphModel JSON 形态）。

    约定优先级：
    - output_port_types：工具链 enrich 后的“具体类型”（可包含泛型端口的实例化结果）
    - effective_output_types：GraphModel/graph_cache 的类型快照
    - output_port_declared_types：NodeDef 声明类型（可能为“泛型/泛型字典”，通常仅用于固定类型端口兜底）
    """
    port = str(port_name or "").strip()
    if port == "":
        return ""
    for key in ("output_port_types", "effective_output_types", "output_port_declared_types"):
        type_map = node_payload.get(key)
        if not isinstance(type_map, Mapping):
            continue
        raw = type_map.get(port)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def build_node_type_binding_plan(
    *,
    graph_scope: str,
    graph_node_id: str,
    node_title: str,
    node_type_id_int: int,
    node_payload: Mapping[str, Any],
    node_def: Any,
    data_inputs: Sequence[str],
    input_constants: Mapping[str, Any] | None,
    node_entry_by_id: Mapping[int, Mapping[str, Any]],
    graph_variable_type_text_by_name: Mapping[str, str] | None,
    inferred_in_type_text: Mapping[Tuple[str, str], str] | None,
    inferred_out_type_text: Mapping[Tuple[str, str], str] | None,
    nep_node_record: Mapping[str, Any] | None,
    # bisect/diagnostics: allow writer to disable specific inference branches without making semantics depend on writeback.
    enable_t_dict_inference_from_input_value_port: bool = True,
) -> NodeTypeBindingPlan:
    """
    构建“类型/绑定决策 Plan”（不落盘）。

    约定：
    - Writer（GIA/GIL）负责决定“写不写/写到哪里/如何 patch”，Plan 只提供可复用的确定性决策结果；
    - 当缺少证据无法唯一确定时，Plan 会保持字段为 None（由 Writer 做“保守写回/保留模板/生成最小结构”等策略）。
    """

    input_constants_map = dict(input_constants or {})
    inferred_in_map: Dict[Tuple[str, str], str] = dict(inferred_in_type_text or {})
    _ = dict(inferred_out_type_text or {})  # 保留入参：Plan 默认不依赖 inferred_out（避免语义误用）
    graph_var_type_map = dict(graph_variable_type_text_by_name or {})

    dict_key_vt_for_node: int | None = None
    dict_value_vt_for_node: int | None = None
    assembly_dict_key_vt_for_node: int | None = None
    assembly_dict_value_vt_for_node: int | None = None

    forced_concrete_runtime_id: int | None = None
    forced_index_of_concrete_by_port: Dict[str, int] | None = None
    forced_out_index_of_concrete_by_port: Dict[str, int] | None = None

    t_dict_in_index_of_concrete: int | None = None
    t_dict_out_index_of_concrete: int | None = None

    graph_var_value_type_text = ""
    assembly_dict_should_write_len_pin = True

    data_input_names = _normalize_port_name_set(data_inputs)
    output_names: set[str] = set()
    outputs_value = node_payload.get("outputs")
    if isinstance(outputs_value, list):
        data_outputs = [
            str(p)
            for p in outputs_value
            if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)
        ]
        output_names = _normalize_port_name_set(data_outputs)

    # ===== 字典泛型节点（K/V）：优先从 “字典” 端口类型（含 inferred_in）解析 (K,V) 与 concrete 映射 =====
    if "字典" in data_input_names:
        dict_port_type_text = _get_input_port_type_text(node_payload, "字典")
        if (not dict_port_type_text) or dict_port_type_text == "流程" or ("泛型" in dict_port_type_text):
            inferred = inferred_in_map.get((str(graph_node_id), "字典"))
            if isinstance(inferred, str):
                inferred_text = inferred.strip()
                if inferred_text and inferred_text != "流程" and ("泛型" not in inferred_text):
                    dict_port_type_text = inferred_text

        kv = parse_dict_key_value_var_types_from_port_type_text(str(dict_port_type_text))
        if kv is None and ("键" in data_input_names) and ("值" in data_input_names):
            # 兼容：部分 GraphModel（尤其是接地/快照形态）可能无法直接在“字典”端口上得到别名字典类型，
            # 但 “键/值” 端口已经有可用的具体类型证据（typed JSON 或连线反推）。
            #
            # 约束：这里仅使用“已明确的类型文本”（不使用 raw_constant_value 字面值兜底），
            # 避免出现 "123" 这种数字字符串被误判为整数并写坏字典 key 类型的问题。
            key_type_text = _get_input_port_type_text(node_payload, "键")
            val_type_text = _get_input_port_type_text(node_payload, "值")
            if (not key_type_text) or key_type_text == "流程" or ("泛型" in key_type_text):
                inferred_key = inferred_in_map.get((str(graph_node_id), "键"))
                if isinstance(inferred_key, str):
                    inferred_key_text = inferred_key.strip()
                    if inferred_key_text and inferred_key_text != "流程" and ("泛型" not in inferred_key_text):
                        key_type_text = inferred_key_text
            if (not val_type_text) or val_type_text == "流程" or ("泛型" in val_type_text):
                inferred_val = inferred_in_map.get((str(graph_node_id), "值"))
                if isinstance(inferred_val, str):
                    inferred_val_text = inferred_val.strip()
                    if inferred_val_text and inferred_val_text != "流程" and ("泛型" not in inferred_val_text):
                        val_type_text = inferred_val_text

            if (
                key_type_text
                and val_type_text
                and key_type_text != "流程"
                and val_type_text != "流程"
                and ("泛型" not in key_type_text)
                and ("泛型" not in val_type_text)
            ):
                key_vt = _try_map_server_port_type_text_to_var_type_id(str(key_type_text))
                val_vt = _try_map_server_port_type_text_to_var_type_id(str(val_type_text))
                if isinstance(key_vt, int) and isinstance(val_vt, int) and int(key_vt) > 0 and int(val_vt) > 0:
                    kv = (int(key_vt), int(val_vt))
        if kv is not None:
            dict_key_vt_for_node = int(kv[0])
            dict_value_vt_for_node = int(kv[1])
            resolved = try_resolve_dict_kv_concrete_mapping(
                node_entry_by_id={int(k): dict(v) for k, v in dict(node_entry_by_id).items() if isinstance(k, int) and isinstance(v, Mapping)},
                node_type_id_int=int(node_type_id_int),
                dict_key_vt=int(dict_key_vt_for_node),
                dict_value_vt=int(dict_value_vt_for_node),
            )
            if resolved is not None:
                concrete_id_int, index_map = resolved
                if isinstance(concrete_id_int, int) and int(concrete_id_int) > 0:
                    forced_concrete_runtime_id = int(concrete_id_int)
                if isinstance(index_map, dict):
                    resolved_index_map = {str(k): int(v) for k, v in dict(index_map).items() if isinstance(v, int)}
                    forced_index_of_concrete_by_port = dict(resolved_index_map)

                    # 兼容：Query_Dictionary_Value_by_Key(1158) 等“字典+键 → 值”的 K/V 双泛型节点，
                    # TypeMappings 的 OutputsIndexOfConcrete 需要写到 OUT_PARAM(值) 的 ConcreteBase.indexOfConcrete。
                    #
                    # 说明：
                    # - try_resolve_dict_kv_concrete_mapping 返回的 index_map 统一使用 {"字典","键","值"} 键；
                    # - 对仅在输出端口出现的端口名（典型：值），需要同步到 forced_out_index_of_concrete_by_port；
                    # - 仅当该端口确实存在于本节点的“数据输出端口列表”时才写入（避免误写到输入-only 节点）。
                    if output_names:
                        out_hits = {k: v for k, v in resolved_index_map.items() if str(k) in output_names}
                        if out_hits:
                            if forced_out_index_of_concrete_by_port is None:
                                forced_out_index_of_concrete_by_port = {}
                            for k, v in out_hits.items():
                                forced_out_index_of_concrete_by_port.setdefault(str(k), int(v))

    # ===== 拼装字典(Assembly_Dictionary, 1788)：以 键0/值0 的“可证据类型”收敛 (K,V) 并命中 TypeMappings =====
    if str(node_title) == "拼装字典" or int(node_type_id_int) == 1788:
        key0_port_name = "键0"
        value0_port_name = "值0"
        if key0_port_name in data_input_names and value0_port_name in data_input_names:
            key0_type_text = _get_input_port_type_text(node_payload, key0_port_name)
            value0_type_text = _get_input_port_type_text(node_payload, value0_port_name)

            has_key0_explicit_type = bool(key0_type_text) and key0_type_text != "流程" and ("泛型" not in key0_type_text)
            has_value0_explicit_type = bool(value0_type_text) and value0_type_text != "流程" and ("泛型" not in value0_type_text)
            has_key0_constant = key0_port_name in input_constants_map
            has_value0_constant = value0_port_name in input_constants_map

            inferred_key0 = inferred_in_map.get((str(graph_node_id), key0_port_name))
            inferred_value0 = inferred_in_map.get((str(graph_node_id), value0_port_name))
            has_key0_inferred_type = (
                isinstance(inferred_key0, str)
                and inferred_key0.strip() != ""
                and inferred_key0.strip() != "流程"
                and ("泛型" not in inferred_key0.strip())
            )
            has_value0_inferred_type = (
                isinstance(inferred_value0, str)
                and inferred_value0.strip() != ""
                and inferred_value0.strip() != "流程"
                and ("泛型" not in inferred_value0.strip())
            )

            should_resolve_key0 = bool(has_key0_explicit_type or has_key0_constant or has_key0_inferred_type)
            should_resolve_value0 = bool(has_value0_explicit_type or has_value0_constant or has_value0_inferred_type)

            if bool(should_resolve_key0) and bool(should_resolve_value0):
                # slot_index：以 data_inputs 的顺序为准（Writer 已排除 flow，并处理了特殊节点的端口剔除规则）
                key0_slot_index = int(list(data_inputs).index(key0_port_name))
                value0_slot_index = int(list(data_inputs).index(value0_port_name))

                key0_resolved_port_name = resolve_input_port_name_for_type(node_def=node_def, port_name=str(key0_port_name))
                value0_resolved_port_name = resolve_input_port_name_for_type(node_def=node_def, port_name=str(value0_port_name))

                def _get_const_value(port_name: str, resolved_name: str) -> Any:
                    if port_name in input_constants_map:
                        return input_constants_map.get(port_name)
                    if resolved_name in input_constants_map:
                        return input_constants_map.get(resolved_name)
                    return None

                key0_raw = _get_const_value(str(key0_port_name), str(key0_resolved_port_name))
                value0_raw = _get_const_value(str(value0_port_name), str(value0_resolved_port_name))

                key0_vt = int(
                    resolve_server_var_type_int_for_port(
                        graph_scope=str(graph_scope),
                        node_id=str(graph_node_id),
                        port_name=str(key0_port_name),
                        is_input=True,
                        node_payload=node_payload,
                        graph_variable_type_text_by_name=dict(graph_var_type_map),
                        inferred_out_type_text=dict(inferred_out_type_text or {}),
                        inferred_in_type_text=dict(inferred_in_type_text or {}),
                        raw_constant_value=key0_raw,
                        nep_node_record=nep_node_record,
                        nep_port_name=str(key0_resolved_port_name),
                        nep_ordinal=int(key0_slot_index),
                    )
                )
                value0_vt = int(
                    resolve_server_var_type_int_for_port(
                        graph_scope=str(graph_scope),
                        node_id=str(graph_node_id),
                        port_name=str(value0_port_name),
                        is_input=True,
                        node_payload=node_payload,
                        graph_variable_type_text_by_name=dict(graph_var_type_map),
                        inferred_out_type_text=dict(inferred_out_type_text or {}),
                        inferred_in_type_text=dict(inferred_in_type_text or {}),
                        raw_constant_value=value0_raw,
                        nep_node_record=nep_node_record,
                        nep_port_name=str(value0_resolved_port_name),
                        nep_ordinal=int(value0_slot_index),
                    )
                )
                if int(key0_vt) > 0 and int(value0_vt) > 0:
                    assembly_dict_key_vt_for_node = int(key0_vt)
                    assembly_dict_value_vt_for_node = int(value0_vt)
                    resolved_assembly = try_resolve_dict_kv_concrete_mapping(
                        node_entry_by_id={
                            int(k): dict(v)
                            for k, v in dict(node_entry_by_id).items()
                            if isinstance(k, int) and isinstance(v, Mapping)
                        },
                        node_type_id_int=int(node_type_id_int),
                        dict_key_vt=int(assembly_dict_key_vt_for_node),
                        dict_value_vt=int(assembly_dict_value_vt_for_node),
                    )
                    if resolved_assembly is None and int(node_type_id_int) != 1788:
                        resolved_assembly = try_resolve_dict_kv_concrete_mapping(
                            node_entry_by_id={
                                int(k): dict(v)
                                for k, v in dict(node_entry_by_id).items()
                                if isinstance(k, int) and isinstance(v, Mapping)
                            },
                            node_type_id_int=1788,
                            dict_key_vt=int(assembly_dict_key_vt_for_node),
                            dict_value_vt=int(assembly_dict_value_vt_for_node),
                        )
                    if resolved_assembly is not None:
                        concrete_id_int2, index_map2 = resolved_assembly
                        if isinstance(concrete_id_int2, int) and int(concrete_id_int2) > 0:
                            forced_concrete_runtime_id = int(concrete_id_int2)
                            if int(concrete_id_int2) == 1831:
                                assembly_dict_should_write_len_pin = False
                        if isinstance(index_map2, dict):
                            forced_index_of_concrete_by_port = {
                                str(k): int(v) for k, v in dict(index_map2).items() if isinstance(v, int)
                            }

        if isinstance(forced_concrete_runtime_id, int) and int(forced_concrete_runtime_id) == 1831:
            assembly_dict_should_write_len_pin = False

    # ===== 节点图变量 Get/Set：主泛型 T 的具体类型来自 graph_variables（单一真源兜底） =====
    if str(node_title) in {"获取节点图变量", "设置节点图变量"}:
        var_name = input_constants_map.get("变量名")
        if isinstance(var_name, str) and var_name.strip():
            graph_var_value_type_text = str(graph_var_type_map.get(var_name.strip()) or "").strip()

    # ===== 单泛型 T=字典（TypeMappings: S<T:D<K,V>>）兜底：不只限于“节点图变量” =====
    #
    # 典型问题：
    # - 获取自定义变量(Get_Custom_Variable, type_id=50) 的 out_port="变量值" 声明为泛型；
    # - 即便我们写出了 OUT_PARAM(MapBase KV)，若缺少 TypeMappings 对应的 concrete runtime_id 与 indexOfConcrete，
    #   编辑器仍可能回退到默认 concrete（常见表现：把字典端口当成整数）。
    #
    # 规则：
    # - 当 GraphModel 已能给出“变量值”为别名字典(K,V)时，可直接用 node_data TypeMappings(S<T:D<K,V>>)
    #   反推出 concrete_id 与 out_index_of_concrete（常见为 20），并写入 Plan 供 Writer 侧落盘。
    out_value_type_text = _get_output_port_type_text(node_payload, "变量值")
    if out_value_type_text and out_value_type_text != "流程" and ("泛型" not in out_value_type_text):
        kv0 = parse_dict_key_value_var_types_from_port_type_text(str(out_value_type_text))
        if kv0 is not None:
            k0, v0 = int(kv0[0]), int(kv0[1])
            resolved_t_dict0 = try_resolve_t_dict_concrete_mapping(
                node_entry_by_id={int(k): dict(v) for k, v in dict(node_entry_by_id).items() if isinstance(k, int) and isinstance(v, Mapping)},
                node_type_id_int=int(node_type_id_int),
                dict_key_vt=int(k0),
                dict_value_vt=int(v0),
            )
            if resolved_t_dict0 is not None:
                concrete_id_int0, in_idx0, out_idx0 = resolved_t_dict0
                if isinstance(concrete_id_int0, int) and int(concrete_id_int0) > 0:
                    # 不覆盖其它更明确的 forced_concrete_runtime_id（例如 K/V 双泛型字典节点）
                    if forced_concrete_runtime_id is None:
                        forced_concrete_runtime_id = int(concrete_id_int0)
                if isinstance(in_idx0, int) and int(in_idx0) > 0:
                    t_dict_in_index_of_concrete = int(in_idx0)
                    if forced_index_of_concrete_by_port is None:
                        forced_index_of_concrete_by_port = {}
                    forced_index_of_concrete_by_port.setdefault("变量值", int(in_idx0))
                if isinstance(out_idx0, int) and int(out_idx0) > 0:
                    t_dict_out_index_of_concrete = int(out_idx0)
                    if forced_out_index_of_concrete_by_port is None:
                        forced_out_index_of_concrete_by_port = {}
                    forced_out_index_of_concrete_by_port.setdefault("变量值", int(out_idx0))

    # 兼容：部分节点（典型：设置自定义变量 Set_Custom_Variable, type_id=22）只有“变量值”输入端口且声明为泛型，
    # 不存在同名输出端口，因此需要同时支持从 input_port_types/input_types 推断 T=字典(K,V) 的 concrete/indexOfConcrete。
    if bool(enable_t_dict_inference_from_input_value_port):
        in_value_type_text = _get_input_port_type_text(node_payload, "变量值")
        if in_value_type_text and in_value_type_text != "流程" and ("泛型" not in in_value_type_text):
            kv_in = parse_dict_key_value_var_types_from_port_type_text(str(in_value_type_text))
            if kv_in is not None:
                k_in, v_in = int(kv_in[0]), int(kv_in[1])
                resolved_t_dict_in = try_resolve_t_dict_concrete_mapping(
                    node_entry_by_id={
                        int(k): dict(v)
                        for k, v in dict(node_entry_by_id).items()
                        if isinstance(k, int) and isinstance(v, Mapping)
                    },
                    node_type_id_int=int(node_type_id_int),
                    dict_key_vt=int(k_in),
                    dict_value_vt=int(v_in),
                )
                if resolved_t_dict_in is not None:
                    concrete_id_int_in, in_idx_in, out_idx_in = resolved_t_dict_in
                    if isinstance(concrete_id_int_in, int) and int(concrete_id_int_in) > 0:
                        if forced_concrete_runtime_id is None:
                            forced_concrete_runtime_id = int(concrete_id_int_in)
                    if isinstance(in_idx_in, int) and int(in_idx_in) > 0:
                        t_dict_in_index_of_concrete = int(in_idx_in)
                        if forced_index_of_concrete_by_port is None:
                            forced_index_of_concrete_by_port = {}
                        forced_index_of_concrete_by_port.setdefault("变量值", int(in_idx_in))
                    if isinstance(out_idx_in, int) and int(out_idx_in) > 0:
                        t_dict_out_index_of_concrete = int(out_idx_in)
                        if forced_out_index_of_concrete_by_port is None:
                            forced_out_index_of_concrete_by_port = {}
                        forced_out_index_of_concrete_by_port.setdefault("变量值", int(out_idx_in))

    if graph_var_value_type_text and graph_var_value_type_text != "流程" and ("泛型" not in graph_var_value_type_text):
        kv2 = parse_dict_key_value_var_types_from_port_type_text(str(graph_var_value_type_text))
        if kv2 is not None:
            gv_key_vt, gv_val_vt = int(kv2[0]), int(kv2[1])
            resolved_t_dict = try_resolve_t_dict_concrete_mapping(
                node_entry_by_id={int(k): dict(v) for k, v in dict(node_entry_by_id).items() if isinstance(k, int) and isinstance(v, Mapping)},
                node_type_id_int=int(node_type_id_int),
                dict_key_vt=int(gv_key_vt),
                dict_value_vt=int(gv_val_vt),
            )
            if resolved_t_dict is not None:
                concrete_id_int3, in_idx3, out_idx3 = resolved_t_dict
                if isinstance(concrete_id_int3, int) and int(concrete_id_int3) > 0:
                    # 不覆盖其它更明确的 forced_concrete_runtime_id（例如 K/V 双泛型字典节点）
                    if forced_concrete_runtime_id is None:
                        forced_concrete_runtime_id = int(concrete_id_int3)
                if isinstance(in_idx3, int) and int(in_idx3) > 0:
                    t_dict_in_index_of_concrete = int(in_idx3)
                    if forced_index_of_concrete_by_port is None:
                        forced_index_of_concrete_by_port = {}
                    forced_index_of_concrete_by_port.setdefault("变量值", int(in_idx3))
                if isinstance(out_idx3, int) and int(out_idx3) > 0:
                    t_dict_out_index_of_concrete = int(out_idx3)
                    if forced_out_index_of_concrete_by_port is None:
                        forced_out_index_of_concrete_by_port = {}
                    forced_out_index_of_concrete_by_port.setdefault("变量值", int(out_idx3))
        else:
            # 非字典：TypeMappings(S<T:...>) 可唯一给出 concrete_id 与（单一）indexOfConcrete。
            # 典型用例：
            # - Get_Node_Graph_Variable(337) 输出 Vec: out_index=11
            # - Set_Node_Graph_Variable(323) 输入 Vec: in_index=11
            vt3: int | None = None
            if str(graph_var_value_type_text).startswith("结构体列表"):
                vt3 = 26
            elif str(graph_var_value_type_text).startswith("结构体"):
                vt3 = 25
            else:
                vt3 = int(_map_server_port_type_to_var_type_id(str(graph_var_value_type_text)))

            if isinstance(vt3, int) and int(vt3) > 0 and int(vt3) != 27:
                resolved_t = try_resolve_t_concrete_mapping(
                    node_entry_by_id={
                        int(k): dict(v)
                        for k, v in dict(node_entry_by_id).items()
                        if isinstance(k, int) and isinstance(v, Mapping)
                    },
                    node_type_id_int=int(node_type_id_int),
                    var_type_int=int(vt3),
                )
                if resolved_t is not None:
                    concrete_id_int4, in_idx4, out_idx4 = resolved_t
                    if isinstance(concrete_id_int4, int) and int(concrete_id_int4) > 0:
                        if forced_concrete_runtime_id is None:
                            forced_concrete_runtime_id = int(concrete_id_int4)
                    if isinstance(in_idx4, int) and int(in_idx4) > 0:
                        if forced_index_of_concrete_by_port is None:
                            forced_index_of_concrete_by_port = {}
                        forced_index_of_concrete_by_port.setdefault("变量值", int(in_idx4))
                    if isinstance(out_idx4, int) and int(out_idx4) > 0:
                        if forced_out_index_of_concrete_by_port is None:
                            forced_out_index_of_concrete_by_port = {}
                        forced_out_index_of_concrete_by_port.setdefault("变量值", int(out_idx4))

    return NodeTypeBindingPlan(
        graph_var_value_type_text=str(graph_var_value_type_text),
        dict_key_vt_for_node=(int(dict_key_vt_for_node) if isinstance(dict_key_vt_for_node, int) else None),
        dict_value_vt_for_node=(int(dict_value_vt_for_node) if isinstance(dict_value_vt_for_node, int) else None),
        assembly_dict_key_vt_for_node=(
            int(assembly_dict_key_vt_for_node) if isinstance(assembly_dict_key_vt_for_node, int) else None
        ),
        assembly_dict_value_vt_for_node=(
            int(assembly_dict_value_vt_for_node) if isinstance(assembly_dict_value_vt_for_node, int) else None
        ),
        assembly_dict_should_write_len_pin=bool(assembly_dict_should_write_len_pin),
        forced_concrete_runtime_id=(int(forced_concrete_runtime_id) if isinstance(forced_concrete_runtime_id, int) else None),
        forced_index_of_concrete_by_port=(
            dict(forced_index_of_concrete_by_port) if isinstance(forced_index_of_concrete_by_port, dict) else None
        ),
        forced_out_index_of_concrete_by_port=(
            dict(forced_out_index_of_concrete_by_port) if isinstance(forced_out_index_of_concrete_by_port, dict) else None
        ),
        t_dict_in_index_of_concrete=(int(t_dict_in_index_of_concrete) if isinstance(t_dict_in_index_of_concrete, int) else None),
        t_dict_out_index_of_concrete=(int(t_dict_out_index_of_concrete) if isinstance(t_dict_out_index_of_concrete, int) else None),
    )


__all__ = [
    "NodeTypeBindingPlan",
    "VariantConcretePlan",
    "build_node_type_binding_plan",
    "build_variant_concrete_plan",
]

