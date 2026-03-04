from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    resolve_server_var_type_int_for_port as _resolve_server_var_type_int_for_port,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server_empty,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from .asset_bundle_builder_constants import _LIST_LIKE_VAR_TYPES
from .asset_bundle_builder_node_editor_pack import (
    _iter_nep_pins,
    _map_nep_type_expr_to_server_var_type_int,
)
from .asset_bundle_builder_proto_helpers import (
    _make_pin_sig,
    _pin_sig_kind_index,
)


def fill_missing_pins_from_node_editor_pack(
    *,
    pins: List[Dict[str, Any]],
    node_record: Mapping[str, Any],
    node_type_id_int: int,
    multibranch_needed_outflow_count: int | None,
    graph_scope: str,
    graph_node_id: str,
    title: str,
    payload: Mapping[str, Any],
    input_constants: Mapping[str, Any],
    graph_variable_type_text_by_name: Mapping[str, str],
    inferred_out_type_text: Mapping[Tuple[str, str], str],
    inferred_in_type_text: Mapping[Tuple[str, str], str],
    skip_ports: set[str],
) -> None:
    """
    使用 NodeEditorPack `data.json` 的 pin 画像补齐“GraphModel 未显式出现的 pins”（flow/data）。

    说明：
    - 该步骤用于保证导入到编辑器时端口结构稳定（避免缺 pin 导致端口错位/连线断开）。
    - 对多分支（Multiple_Branches, type_id=3）必须严格限制 OUT_FLOW 数量，不可补齐到“最大分支数”。
    """
    existing_in_flow_indices: set[int] = set()
    existing_out_flow_indices: set[int] = set()
    existing_in_param_indices: set[int] = set()
    existing_out_param_indices: set[int] = set()

    for p in list(pins):
        if not isinstance(p, Mapping):
            continue
        k, idx = _pin_sig_kind_index(p)
        if int(k) == 1:
            existing_in_flow_indices.add(int(idx))
        elif int(k) == 2:
            existing_out_flow_indices.add(int(idx))
        elif int(k) == 3:
            existing_in_param_indices.add(int(idx))
        elif int(k) == 4:
            existing_out_param_indices.add(int(idx))

    nep_flow_pins = _iter_nep_pins(node_record, is_flow=True)
    for nep_pin in nep_flow_pins:
        if str(nep_pin.direction) == "In":
            if int(nep_pin.shell_index) in existing_in_flow_indices:
                continue
            pins.append(
                {
                    "1": _make_pin_sig(kind_int=1, index_int=int(nep_pin.shell_index)),
                    "2": _make_pin_sig(kind_int=1, index_int=int(nep_pin.kernel_index)),
                }
            )
        elif str(nep_pin.direction) == "Out":
            # Multiple_Branches(type_id=3)：不要从 NodeEditorPack 画像补齐“最大分支数”的 OUT_FLOW，
            # 必须严格跟随 cases 长度（outflows=1+len(cases)），否则会出现导入后分支数量/索引漂移。
            if int(node_type_id_int) == 3 and isinstance(multibranch_needed_outflow_count, int):
                if int(nep_pin.shell_index) >= int(multibranch_needed_outflow_count):
                    continue
            if int(nep_pin.shell_index) in existing_out_flow_indices:
                continue
            pins.append(
                {
                    "1": _make_pin_sig(kind_int=2, index_int=int(nep_pin.shell_index)),
                    "2": _make_pin_sig(kind_int=2, index_int=int(nep_pin.kernel_index)),
                }
            )

    nep_data_pins = _iter_nep_pins(node_record, is_flow=False)
    for nep_pin in nep_data_pins:
        if str(nep_pin.direction) == "In":
            if int(node_type_id_int) == 1788 and int(nep_pin.shell_index) == 0:
                # 拼装字典的 pin0(len) 为内部端口，不作为 GraphModel 可见输入写出。
                continue
            if (nep_pin.label_zh and nep_pin.label_zh in skip_ports) or (nep_pin.identifier and nep_pin.identifier in skip_ports):
                continue
            if int(nep_pin.shell_index) in existing_in_param_indices:
                continue

            port_name_hint = str(nep_pin.label_zh or nep_pin.identifier or "").strip()
            raw_const = input_constants.get(port_name_hint) if port_name_hint else None
            vt = int(_map_nep_type_expr_to_server_var_type_int(str(nep_pin.type_expr)))

            # 对 R<T> / L<R<T>> 这类泛型输入，优先从 GraphModel 的 effective_input_types/input_port_types 推断具体类型；
            # 缺失时再走 “按常量推断/保守字符串” 的兜底。
            if port_name_hint:
                vt = int(
                    _resolve_server_var_type_int_for_port(
                        graph_scope=str(graph_scope),
                        node_id=str(graph_node_id),
                        port_name=str(port_name_hint),
                        is_input=True,
                        node_payload=dict(payload),
                        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
                        inferred_out_type_text=dict(inferred_out_type_text),
                        inferred_in_type_text=dict(inferred_in_type_text),
                        raw_constant_value=raw_const,
                        nep_node_record=node_record,
                        nep_port_name=str(port_name_hint),
                        nep_ordinal=0,
                    )
                )
            if int(vt) <= 0:
                vt = 6

            inner = build_var_base_message_server_empty(var_type_int=int(vt))
            wrap_as_generic = (int(vt) == 27) or (int(vt) in _LIST_LIKE_VAR_TYPES)

            # 特例：Multiple_Branches(type_id=3) 的控制表达式 pin（shell=0）是 R<T> 反射端口，
            # 即使 vt 已推断为 Int，也需要 ConcreteBase(indexOfConcrete) 才能让编辑器不显示“泛型”。
            if int(node_type_id_int) == 3 and int(nep_pin.shell_index) == 0:
                wrap_as_generic = True

            if bool(wrap_as_generic):
                index_of_concrete = None
                if int(node_type_id_int) == 3 and int(nep_pin.shell_index) == 0:
                    index_of_concrete = _infer_index_of_concrete_for_generic_pin(
                        node_title=str(title),
                        port_name=str(port_name_hint or "控制表达式"),
                        is_input=True,
                        var_type_int=int(vt),
                        node_type_id_int=int(node_type_id_int),
                        pin_index=int(nep_pin.shell_index),
                    )
                var_base = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=index_of_concrete)
            else:
                var_base = dict(inner)

            pins.append(
                {
                    "1": _make_pin_sig(kind_int=3, index_int=int(nep_pin.shell_index)),
                    "2": _make_pin_sig(kind_int=3, index_int=int(nep_pin.kernel_index)),
                    "3": dict(var_base),
                    "4": int(vt),
                }
            )
        elif str(nep_pin.direction) == "Out":
            if int(nep_pin.shell_index) in existing_out_param_indices:
                continue

            port_name_hint = str(nep_pin.label_zh or nep_pin.identifier or "").strip()
            vt = int(_map_nep_type_expr_to_server_var_type_int(str(nep_pin.type_expr)))

            if port_name_hint:
                vt = int(
                    _resolve_server_var_type_int_for_port(
                        graph_scope=str(graph_scope),
                        node_id=str(graph_node_id),
                        port_name=str(port_name_hint),
                        is_input=False,
                        node_payload=dict(payload),
                        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name),
                        inferred_out_type_text=dict(inferred_out_type_text),
                        inferred_in_type_text=dict(inferred_in_type_text),
                        raw_constant_value=None,
                        nep_node_record=node_record,
                        nep_port_name=str(port_name_hint),
                        nep_ordinal=0,
                    )
                )
            if int(vt) <= 0:
                vt = 6

            inner = build_var_base_message_server_empty(var_type_int=int(vt))
            if int(vt) == 27 or int(vt) in _LIST_LIKE_VAR_TYPES:
                var_base = _wrap_var_base_as_concrete_base(inner=inner, index_of_concrete=None)
            else:
                var_base = dict(inner)

            pins.append(
                {
                    "1": _make_pin_sig(kind_int=4, index_int=int(nep_pin.shell_index)),
                    "2": _make_pin_sig(kind_int=4, index_int=int(nep_pin.kernel_index)),
                    "3": dict(var_base),
                    "4": int(vt),
                }
            )

