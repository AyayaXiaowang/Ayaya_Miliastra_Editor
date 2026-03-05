from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
    resolve_input_port_name_for_type as _resolve_input_port_name_for_type,
)
from ugc_file_tools.node_graph_semantics.pin_rules import map_inparam_pin_index_for_node as _map_inparam_pin_index_for_node
from ugc_file_tools.node_graph_semantics.signal_binding import (
    map_send_signal_inparam_indices_for_dst_port,
    should_use_listen_signal_meta_binding,
    should_use_send_signal_meta_binding,
)

from .asset_bundle_builder_node_editor_pack import _resolve_pin_indices
from .asset_bundle_builder_proto_helpers import _make_node_connection

EdgeTuple = Tuple[str, str, str, str]


def build_flow_conns_by_src_pin(
    *,
    flow_edges: List[EdgeTuple],
    node_index_by_graph_node_id: Mapping[str, int],
    node_title_by_graph_node_id: Mapping[str, str],
    node_def_by_graph_node_id: Mapping[str, Any],
    node_payload_by_graph_node_id: Mapping[str, Dict[str, Any]],
    node_type_id_int_by_graph_node_id: Mapping[str, int],
    node_record_by_graph_node_id: Mapping[str, Mapping[str, Any] | None],
) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
    """
    将 GraphModel flow edges 聚合为：
    - key=(src_node_index, src_out_flow_shell_index)
    - value=[NodeConnection, ...]
    """
    flow_conns_by_src_pin: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}

    for src_node_id, src_port, dst_node_id, dst_port in flow_edges:
        src_node_index = node_index_by_graph_node_id.get(str(src_node_id))
        dst_node_index = node_index_by_graph_node_id.get(str(dst_node_id))
        if not isinstance(src_node_index, int) or not isinstance(dst_node_index, int):
            raise ValueError("flow edge 引用了未知节点 id")

        src_title = node_title_by_graph_node_id.get(str(src_node_id), "")
        dst_title = node_title_by_graph_node_id.get(str(dst_node_id), "")
        src_def = node_def_by_graph_node_id.get(str(src_node_id))
        dst_def = node_def_by_graph_node_id.get(str(dst_node_id))
        if src_def is None or dst_def is None:
            raise ValueError("flow edge 缺少 NodeDef（node_def_ref 缺失/解析失败）")

        src_payload = node_payload_by_graph_node_id[str(src_node_id)]
        dst_payload = node_payload_by_graph_node_id[str(dst_node_id)]
        src_outputs = src_payload.get("outputs")
        dst_inputs = dst_payload.get("inputs")
        if not isinstance(src_outputs, list) or not isinstance(dst_inputs, list):
            raise ValueError("flow edge 节点 inputs/outputs 不是 list")

        src_flow_outputs = [str(p) for p in src_outputs if _is_flow_port_by_node_def(node_def=src_def, port_name=str(p), is_input=False)]
        dst_flow_inputs = [str(p) for p in dst_inputs if _is_flow_port_by_node_def(node_def=dst_def, port_name=str(p), is_input=True)]
        if str(src_port) not in src_flow_outputs:
            raise ValueError(f"src_port 不在 src_node.outputs(flow) 中：{src_title!r}.{src_port!r} outputs={src_flow_outputs!r}")
        if str(dst_port) not in dst_flow_inputs:
            raise ValueError(f"dst_port 不在 dst_node.inputs(flow) 中：{dst_title!r}.{dst_port!r} inputs={dst_flow_inputs!r}")

        src_node_type_id_int = node_type_id_int_by_graph_node_id.get(str(src_node_id))
        # Multiple_Branches(type_id=3) 是动态分支节点：
        # - OUT_FLOW 的 index 必须与 cases 列表长度对齐（默认=0，cases 从 1 开始），否则会出现“分支连错/导入后端口漂移”。
        # - GraphModel.outputs 往往包含动态分支的“显示名”，这里用其顺序推断 cases 的稳定顺序。
        if isinstance(src_node_type_id_int, int) and int(src_node_type_id_int) == 3:
            src_cases_labels = [p for p in list(src_flow_outputs) if str(p).strip() != "默认"]
            if str(src_port).strip() == "默认":
                src_flow_out_ordinal = 0
            else:
                if str(src_port) not in src_cases_labels:
                    raise ValueError(
                        "Multiple_Branches OUT_FLOW 端口未在 cases_labels 中："
                        f"src={src_title!r}.{str(src_port)!r} cases_labels={src_cases_labels!r}"
                    )
                src_flow_out_ordinal = 1 + int(src_cases_labels.index(str(src_port)))
        else:
            src_flow_out_ordinal = int(src_flow_outputs.index(str(src_port)))
        dst_flow_in_ordinal = int(dst_flow_inputs.index(str(dst_port)))

        src_record = node_record_by_graph_node_id.get(str(src_node_id))
        dst_record = node_record_by_graph_node_id.get(str(dst_node_id))
        if isinstance(src_node_type_id_int, int) and int(src_node_type_id_int) == 3:
            # 真源对齐：Multiple_Branches 的 flow pins 索引直接使用 outflow ordinal（shell=kernel=ordinal）
            src_shell_index, src_kernel_index = int(src_flow_out_ordinal), int(src_flow_out_ordinal)
        else:
            src_shell_index, src_kernel_index = _resolve_pin_indices(
                src_record,
                is_flow=True,
                direction="Out",
                port_name=str(src_port),
                ordinal=int(src_flow_out_ordinal),
                fallback_index=int(src_flow_out_ordinal),
            )
        dst_shell_index, dst_kernel_index = _resolve_pin_indices(
            dst_record,
            is_flow=True,
            direction="In",
            port_name=str(dst_port),
            ordinal=int(dst_flow_in_ordinal),
            fallback_index=int(dst_flow_in_ordinal),
        )

        flow_conns_by_src_pin.setdefault((int(src_node_index), int(src_shell_index)), []).append(
            _make_node_connection(
                target_node_index=int(dst_node_index),
                target_kind_int=1,  # IN_FLOW
                target_shell_index_int=int(dst_shell_index),
                target_kernel_index_int=int(dst_kernel_index),
            )
        )

    return flow_conns_by_src_pin


def build_data_conns_by_dst_pin(
    *,
    data_edges: List[EdgeTuple],
    node_index_by_graph_node_id: Mapping[str, int],
    node_title_by_graph_node_id: Mapping[str, str],
    node_def_by_graph_node_id: Mapping[str, Any],
    node_payload_by_graph_node_id: Mapping[str, Dict[str, Any]],
    node_type_id_int_by_graph_node_id: Mapping[str, int],
    node_record_by_graph_node_id: Mapping[str, Mapping[str, Any] | None],
    send_signal_nodes_with_signal_name_in_edge: set[str],
    listen_signal_nodes_with_signal_name_in_edge: set[str],
) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
    """
    将 GraphModel data edges 聚合为：
    - key=(dst_node_index, dst_in_param_shell_index)
    - value=[NodeConnection, ...]（指向 src 的 OUT_PARAM）
    """
    data_conns_by_dst_pin: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}

    for src_node_id, src_port, dst_node_id, dst_port in data_edges:
        src_node_index = node_index_by_graph_node_id.get(str(src_node_id))
        dst_node_index = node_index_by_graph_node_id.get(str(dst_node_id))
        if not isinstance(src_node_index, int) or not isinstance(dst_node_index, int):
            raise ValueError("data edge 引用了未知节点 id")

        dst_title = node_title_by_graph_node_id.get(str(dst_node_id), "")
        dst_def = node_def_by_graph_node_id.get(str(dst_node_id))
        if dst_def is None:
            raise ValueError(f"data edge 缺少 dst NodeDef: {dst_title!r}")
        dst_payload = node_payload_by_graph_node_id[str(dst_node_id)]
        dst_inputs = dst_payload.get("inputs")
        if not isinstance(dst_inputs, list):
            raise ValueError("dst_node.inputs 不是 list")
        dst_data_inputs = [str(p) for p in dst_inputs if not _is_flow_port_by_node_def(node_def=dst_def, port_name=str(p), is_input=True)]
        if str(dst_port) not in dst_data_inputs:
            raise ValueError(f"dst_port 不在 dst_node.inputs(data) 中：dst={dst_title!r}.{dst_port!r} inputs={dst_data_inputs!r}")

        dst_type_id_int = node_type_id_int_by_graph_node_id.get(str(dst_node_id))
        send_signal_use_meta_binding = should_use_send_signal_meta_binding(
            node_type_id_int=(int(dst_type_id_int) if isinstance(dst_type_id_int, int) else None),
            graph_node_id=str(dst_node_id),
            send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge or set()),
        )
        listen_signal_use_meta_binding = should_use_listen_signal_meta_binding(
            node_type_id_int=(int(dst_type_id_int) if isinstance(dst_type_id_int, int) else None),
            graph_node_id=str(dst_node_id),
            listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge or set()),
        )

        if bool(send_signal_use_meta_binding) or bool(listen_signal_use_meta_binding):
            dst_slot_index, dst_shell_index, dst_kernel_index = map_send_signal_inparam_indices_for_dst_port(
                dst_data_inputs=list(dst_data_inputs),
                dst_port=str(dst_port),
                use_meta_binding=True,
                dst_title=str(dst_title),
            )
        else:
            dst_slot_index = int(dst_data_inputs.index(str(dst_port)))
            dst_pin_fallback_index = int(_map_inparam_pin_index_for_node(node_title=str(dst_title), port_name=str(dst_port), slot_index=int(dst_slot_index)))
            if str(dst_title) == "拼装字典":
                # 拼装字典的可见 InParam 从 pin1 开始（键0=1, 值0=2 ...）；
                # NodeEditorPack pin0 是内部 len，不对应 GraphModel 的键值输入端口。
                dst_shell_index = int(dst_pin_fallback_index)
                dst_kernel_index = int(dst_pin_fallback_index)
            else:
                dst_record = node_record_by_graph_node_id.get(str(dst_node_id))
                resolved_dst_port = _resolve_input_port_name_for_type(node_def=dst_def, port_name=str(dst_port))
                dst_shell_index, dst_kernel_index = _resolve_pin_indices(
                    dst_record,
                    is_flow=False,
                    direction="In",
                    port_name=str(resolved_dst_port),
                    ordinal=int(dst_slot_index),
                    fallback_index=int(dst_pin_fallback_index),
                )

        src_title = node_title_by_graph_node_id.get(str(src_node_id), "")
        src_def = node_def_by_graph_node_id.get(str(src_node_id))
        if src_def is None:
            raise ValueError(f"data edge 缺少 src NodeDef: {src_title!r}")
        src_payload = node_payload_by_graph_node_id[str(src_node_id)]
        src_outputs = src_payload.get("outputs")
        if not isinstance(src_outputs, list):
            raise ValueError("src_node.outputs 不是 list")
        src_data_outputs = [str(p) for p in src_outputs if not _is_flow_port_by_node_def(node_def=src_def, port_name=str(p), is_input=False)]
        if str(src_port) not in src_data_outputs:
            raise ValueError(f"src_port 不在 src_node.outputs(data) 中：src={src_title!r}.{src_port!r} outputs={src_data_outputs!r}")
        src_out_ordinal = int(src_data_outputs.index(str(src_port)))
        src_record = node_record_by_graph_node_id.get(str(src_node_id))
        src_shell_index, src_kernel_index = _resolve_pin_indices(
            src_record,
            is_flow=False,
            direction="Out",
            port_name=str(src_port),
            ordinal=int(src_out_ordinal),
            fallback_index=int(src_out_ordinal),
        )

        data_conns_by_dst_pin.setdefault((int(dst_node_index), int(dst_shell_index)), []).append(
            _make_node_connection(
                target_node_index=int(src_node_index),
                target_kind_int=4,  # OUT_PARAM
                target_shell_index_int=int(src_shell_index),
                target_kernel_index_int=int(src_kernel_index),
            )
        )

    return data_conns_by_dst_pin

