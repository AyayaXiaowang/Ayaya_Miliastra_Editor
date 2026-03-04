from __future__ import annotations

import copy
from typing import Any, Callable, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text
from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_declared_generic_port_type as _is_declared_generic_port_type,
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
)
from ugc_file_tools.node_graph_semantics.layout import SortedNode as _SortedNode
from ugc_file_tools.node_graph_semantics.pin_rules import (
    infer_index_of_concrete_for_generic_pin as _infer_index_of_concrete_for_generic_pin,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    get_port_type_text as _get_port_type_text,
)
from ugc_file_tools.node_graph_semantics.var_base import (
    build_var_base_message_server as _build_var_base_message_server,
    build_var_base_message_server_empty as _build_var_base_message_server_empty,
    map_server_port_type_to_var_type_id as _map_server_port_type_to_var_type_id,
    wrap_var_base_as_concrete_base as _wrap_var_base_as_concrete_base,
)

from .node_property import _build_server_node_property_binary_text
from .record_codec import (
    _build_node_pin_message,
    _ensure_record_list,
    _extract_nested_int,
    _patch_multibranch_case_values_in_node,
    _strip_all_link_records_from_node,
)
from .template_library import _NodeTemplate


def _build_nodes_list_from_templates(
    *,
    sorted_nodes: List[_SortedNode],
    transform_pos: Callable[[float, float], Tuple[float, float]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_defs_by_name: Dict[str, Any],
    node_template_by_type_id: Dict[int, _NodeTemplate],
    inferred_output_port_type_by_src_node_and_port: Dict[Tuple[str, str], str],
) -> Tuple[List[Dict[str, Any]], Dict[int, Dict[str, Any]], List[str]]:
    """
    GraphModel nodes → GIL nodes list：
    - 有样本：克隆模板节点并剔除旧连线记录；
    - 无样本：按最小 schema 合成节点，并为 data outputs 合成 OutParam pins（可写入空 ConcreteBase 仅表达类型）。
    """
    new_nodes_list: List[Dict[str, Any]] = []
    node_object_by_node_id_int: Dict[int, Dict[str, Any]] = {}
    missing_node_templates: List[str] = []

    def _is_signal_listen_event_node_payload(payload: Dict[str, Any]) -> bool:
        node_def_ref = payload.get("node_def_ref")
        if not isinstance(node_def_ref, dict):
            return False
        if str(node_def_ref.get("kind") or "").strip().lower() != "event":
            return False
        outputs = payload.get("outputs")
        return isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs)

    for (_y, _x, title, node_id, node_payload) in sorted_nodes:
        type_id_int = int(node_type_id_by_graph_node_id[node_id])
        template_bundle = node_template_by_type_id.get(type_id_int)
        template_node = template_bundle.node if isinstance(template_bundle, _NodeTemplate) else None
        if not isinstance(template_node, dict):
            # 无样本节点：按 schema 构造一个最小节点（NodeProperty + 坐标 + 可选 OutParam pins）
            node_def = node_defs_by_name.get(str(title))
            if node_def is None:
                # 兼容“监听信号事件节点”（GraphModel: kind=event, title/key=信号名）：
                # - 该节点在画布上标题为“信号名”，但其实际节点定义应为【监听信号】；
                # - 当模板库覆盖不足（例如 template_library_dir 未包含 300001 样本）时，会走到“无样本合成”路径；
                #   此时不能用 `title=信号名` 去查 node_def，否则会抛 KeyError。
                node_def_ref = node_payload.get("node_def_ref") if isinstance(node_payload, dict) else None
                if isinstance(node_def_ref, dict) and str(node_def_ref.get("kind") or "").strip().lower() == "event":
                    outputs = node_payload.get("outputs") if isinstance(node_payload, dict) else None
                    if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                        node_def = node_defs_by_name.get("监听信号")
            if node_def is None:
                raise KeyError(f"Graph_Generater 节点库未找到节点定义：{title!r}")

            pos = node_payload.get("pos")
            x = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
            y = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
            x, y = transform_pos(float(x), float(y))

            new_node_id_int = int(node_id_int_by_graph_node_id[node_id])
            # 注意：沿用原实现的入参（node_id_int=type_id_int），避免行为变化
            node_prop_text = _build_server_node_property_binary_text(node_id_int=int(type_id_int))

            records_list: List[str] = []

            # ===== 动态端口节点：拼装列表 =====
            # 对齐校准样本：
            # - InParam.index=0 为“元素数量”
            # - 元素端口从 1 开始（元素0=pin1, 元素1=pin2, ...）
            # - 通常预置 0~99 的占位 pins（用于在编辑器中呈现完整变参端口结构）
            if str(title) == "拼装列表":
                inputs_value = node_payload.get("inputs")
                data_inputs = [str(p) for p in inputs_value] if isinstance(inputs_value, list) else []
                desired_count = int(len(data_inputs))

                # 优先从 typed JSON 推断元素类型（用于 VarType）；若缺失则保守回退为整数（校准图用例）。
                elem_port_type_text = ""
                t0 = str(_get_port_type_text(node_payload, "0", is_input=True) or "").strip()
                if t0 and t0 != "流程" and ("泛型" not in t0):
                    elem_port_type_text = t0
                if not elem_port_type_text:
                    for p in list(data_inputs):
                        t1 = str(_get_port_type_text(node_payload, str(p), is_input=True) or "").strip()
                        if t1 and t1 != "流程" and ("泛型" not in t1):
                            elem_port_type_text = t1
                            break
                elem_var_type_int: Optional[int] = None
                if elem_port_type_text:
                    elem_var_type_int = _map_server_port_type_to_var_type_id(str(elem_port_type_text))
                elem_vt = int(elem_var_type_int) if isinstance(elem_var_type_int, int) else 3

                # pin0：数量（IntBaseValue，非 ConcreteBase）
                pin0_var_base = _build_var_base_message_server(var_type_int=3, value=int(desired_count))
                pin0_msg = _build_node_pin_message(kind=3, index=0, var_type_int=3, connects=None)
                pin0_msg["3"] = dict(pin0_var_base)
                records_list.append(format_binary_data_hex_text(encode_message(pin0_msg)))

                # pin1..pin99：占位（ConcreteBase 包裹空 inner，仅表达类型）
                inner_empty = _build_var_base_message_server_empty(var_type_int=int(elem_vt))
                placeholder_var_base = _wrap_var_base_as_concrete_base(inner=inner_empty, index_of_concrete=None)
                for pin_index in range(1, 100):
                    pin_msg = _build_node_pin_message(kind=3, index=int(pin_index), var_type_int=int(elem_vt), connects=None)
                    pin_msg["3"] = dict(placeholder_var_base)
                    records_list.append(format_binary_data_hex_text(encode_message(pin_msg)))
            outputs_value = node_payload.get("outputs")
            if not isinstance(outputs_value, list):
                raise ValueError(f"graph node outputs 不是 list: {node_id!r}")
            data_outputs = [
                str(p)
                for p in outputs_value
                if not _is_flow_port_by_node_def(node_def=node_def, port_name=str(p), is_input=False)
            ]
            # typed JSON / GraphModel 快照可能提供 output_port_types / output_types，
            # 用于解决 NodeDef.get_port_type 返回“泛型”导致无法映射 VarType 的问题。
            output_port_declared_types_map = node_payload.get("output_port_declared_types")
            for out_index, port_name in enumerate(data_outputs):
                # 仅为“声明为泛型”的输出端口写 OutParam record；
                # 固定类型输出端口通常不需要 OutParam record（对齐校准样本：如 是否相等/获取自身实体/列表是否包含该值 等）。
                declared_type_text = ""
                if isinstance(output_port_declared_types_map, dict):
                    dt = output_port_declared_types_map.get(str(port_name))
                    if isinstance(dt, str):
                        declared_type_text = dt.strip()
                if not declared_type_text:
                    declared_type_text = str(node_def.get_port_type(str(port_name), is_input=False)).strip()
                if not _is_declared_generic_port_type(str(declared_type_text)):
                    continue

                port_type_text = str(_get_port_type_text(node_payload, str(port_name), is_input=False) or "").strip()

                # 进一步回退：若仍为泛型，则尝试通过连线目标输入端口类型反推输出类型
                if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                    inferred = inferred_output_port_type_by_src_node_and_port.get((str(node_id), str(port_name)))
                    if isinstance(inferred, str):
                        inferred_text = inferred.strip()
                        if inferred_text and inferred_text != "流程" and ("泛型" not in inferred_text):
                            port_type_text = inferred_text

                # 进一步回退：若仍为泛型，则尝试使用本节点输入端口的已推断类型（常见：运算类节点输出=输入类型）
                if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                    inputs_value = node_payload.get("inputs")
                    if isinstance(inputs_value, list):
                        for p in list(inputs_value):
                            _t_text = str(_get_port_type_text(node_payload, str(p), is_input=True) or "").strip()
                            if _t_text and _t_text != "流程" and ("泛型" not in _t_text):
                                port_type_text = _t_text
                                break

                if (not port_type_text) or port_type_text == "流程" or ("泛型" in port_type_text):
                    port_type_text = str(node_def.get_port_type(str(port_name), is_input=False)).strip()

                # 若仍为泛型：OutParam 不写具体 var_type（保持端口为泛型）
                var_type_int: Optional[int] = None
                if port_type_text and port_type_text != "流程" and ("泛型" not in port_type_text):
                    var_type_int = _map_server_port_type_to_var_type_id(str(port_type_text))
                pin_msg = _build_node_pin_message(
                    kind=4,  # OutParam
                    index=int(out_index),
                    var_type_int=int(var_type_int) if isinstance(var_type_int, int) else None,
                    connects=None,
                )
                # 对齐正确样本：OutParam record 通常包含 field_3(ConcreteBase/VarBase)。
                # 这里为“无样本节点”也补齐一个空 ConcreteBase value（仅表达类型，不表达具体值）。
                if isinstance(var_type_int, int):
                    inner_empty = _build_var_base_message_server_empty(var_type_int=int(var_type_int))
                    var_base = _wrap_var_base_as_concrete_base(
                        inner=inner_empty,
                        index_of_concrete=_infer_index_of_concrete_for_generic_pin(
                            node_title=str(title),
                            port_name=str(port_name),
                            is_input=False,
                            var_type_int=int(var_type_int),
                            node_type_id_int=int(type_id_int),
                            pin_index=int(out_index),
                        ),
                    )
                    pin_msg["3"] = dict(var_base)
                records_list.append(format_binary_data_hex_text(encode_message(pin_msg)))

            synthesized_node: Dict[str, Any] = {
                "1": [int(new_node_id_int)],
                "2": str(node_prop_text),
                "3": str(node_prop_text),
                "4": list(records_list),
            }
            # 对齐真源样本：坐标为 0.0 时通常省略对应字段，避免 dump diff 噪声且更贴近官方导出编码。
            if float(x) != 0.0:
                synthesized_node["5"] = float(x)
            if float(y) != 0.0:
                synthesized_node["6"] = float(y)
            # 对齐真源与用户修复样本：signal listen 事件节点（title=信号名）不写 concrete_id。
            if _is_signal_listen_event_node_payload(node_payload):
                synthesized_node.pop("3", None)
            # 多分支：无样本节点时也要写入“分支值列表”record，否则动态端口可能丢失
            if str(title) == "多分支":
                outputs_value = node_payload.get("outputs")
                if not isinstance(outputs_value, list):
                    raise ValueError("多分支节点 outputs 不是 list")
                case_values = [str(p) for p in outputs_value if str(p) != "默认"]
                _patch_multibranch_case_values_in_node(node_obj=synthesized_node, case_values=case_values)
            new_nodes_list.append(synthesized_node)
            node_object_by_node_id_int[int(new_node_id_int)] = synthesized_node
            continue

        new_node = copy.deepcopy(template_node)
        new_node_id_int = int(node_id_int_by_graph_node_id[node_id])
        new_node["1"] = [new_node_id_int]

        pos = node_payload.get("pos")
        x = float(pos[0]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        y = float(pos[1]) if isinstance(pos, (list, tuple)) and len(pos) >= 2 else 0.0
        x, y = transform_pos(float(x), float(y))
        # 对齐真源样本：坐标为 0.0 时通常省略对应字段。
        if float(x) != 0.0:
            new_node["5"] = float(x)
        else:
            new_node.pop("5", None)
        if float(y) != 0.0:
            new_node["6"] = float(y)
        else:
            new_node.pop("6", None)

        strip_id_set = template_bundle.template_node_id_set if isinstance(template_bundle, _NodeTemplate) else set()
        _strip_all_link_records_from_node(node=new_node, template_node_id_set=set(strip_id_set))
        _ensure_record_list(new_node)

        # ===== 监听信号事件节点（GraphModel: kind=event, title/key=信号名）对齐 =====
        # 模板库中的 Monitor_Signal(300001) 可能残留 OutParam 占位 records（具体类型/端口组可能与当前信号不一致），
        # 导致编辑器端口解释与连线出现错位。
        # 对齐真源样本：事件节点只保留流程口，数据端口由信号规格动态展开；且不写 concrete_id。
        if _is_signal_listen_event_node_payload(node_payload):
            records = _ensure_record_list(new_node)
            kept_records: List[Any] = []
            for record in list(records):
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
            new_node["4"] = kept_records
            new_node.pop("3", None)

        # 多分支：同步写回“分支值列表”record（支持字符串动态端口）
        if str(title) == "多分支":
            outputs_value = node_payload.get("outputs")
            if not isinstance(outputs_value, list):
                raise ValueError("多分支节点 outputs 不是 list")
            case_values = [str(p) for p in outputs_value if str(p) != "默认"]
            _patch_multibranch_case_values_in_node(node_obj=new_node, case_values=case_values)

        new_nodes_list.append(new_node)
        node_object_by_node_id_int[new_node_id_int] = new_node

    return new_nodes_list, node_object_by_node_id_int, missing_node_templates


