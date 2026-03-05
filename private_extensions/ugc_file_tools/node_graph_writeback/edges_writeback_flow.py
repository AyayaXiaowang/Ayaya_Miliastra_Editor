from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.node_graph_semantics.graph_generater import (
    is_flow_port_by_node_def as _is_flow_port_by_node_def,
)

from .edges_writeback_common import resolve_node_def_for_graph_node
from .node_editor_pack import resolve_node_editor_pack_pin_indices
from .record_codec import _build_flow_link_record_text, _ensure_record_list


def write_flow_edges_inplace(
    *,
    flow_edges: List[Tuple[str, str, str, str]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_title_by_graph_node_id: Dict[str, str],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    signal_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
) -> int:
    added_flow_edges = 0
    for src_node_id, src_port, dst_node_id, dst_port in list(flow_edges):
        src_node_id_int = node_id_int_by_graph_node_id.get(src_node_id)
        dst_node_id_int = node_id_int_by_graph_node_id.get(dst_node_id)
        if not isinstance(src_node_id_int, int) or not isinstance(dst_node_id_int, int):
            continue

        src_title = node_title_by_graph_node_id.get(src_node_id, "")
        dst_title = node_title_by_graph_node_id.get(dst_node_id, "")
        if src_title == "" or dst_title == "":
            raise ValueError("flow edge 引用了未知节点 title")

        src_node_payload = graph_node_by_graph_node_id.get(src_node_id)
        dst_node_payload = graph_node_by_graph_node_id.get(dst_node_id)
        if not isinstance(src_node_payload, dict) or not isinstance(dst_node_payload, dict):
            raise ValueError("flow edge 引用了缺失 node payload")
        src_def = resolve_node_def_for_graph_node(
            node_id=str(src_node_id),
            node_title=str(src_title),
            node_payload=src_node_payload,
            node_defs_by_name=node_defs_by_name,
        )
        dst_def = resolve_node_def_for_graph_node(
            node_id=str(dst_node_id),
            node_title=str(dst_title),
            node_payload=dst_node_payload,
            node_defs_by_name=node_defs_by_name,
        )
        if src_def is None or dst_def is None:
            raise ValueError(f"flow edge 缺少 NodeDef：src={src_title!r} dst={dst_title!r}")
        src_outputs = src_node_payload.get("outputs")
        dst_inputs = dst_node_payload.get("inputs")
        if not isinstance(src_outputs, list) or not isinstance(dst_inputs, list):
            raise ValueError("flow edge 节点 inputs/outputs 不是 list")

        src_flow_outputs = [
            str(p) for p in src_outputs if _is_flow_port_by_node_def(node_def=src_def, port_name=str(p), is_input=False)
        ]
        dst_flow_inputs = [
            str(p) for p in dst_inputs if _is_flow_port_by_node_def(node_def=dst_def, port_name=str(p), is_input=True)
        ]
        if str(src_port) not in src_flow_outputs:
            raise ValueError(f"src_port 不在 src_node.outputs(flow) 中：{src_title!r}.{src_port!r} outputs={src_flow_outputs!r}")
        if str(dst_port) not in dst_flow_inputs:
            raise ValueError(f"dst_port 不在 dst_node.inputs(flow) 中：{dst_title!r}.{dst_port!r} inputs={dst_flow_inputs!r}")

        src_type_id_int = int(node_type_id_by_graph_node_id.get(str(src_node_id), 0))
        if int(src_type_id_int) == 3:
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

        if int(src_type_id_int) == 3:
            src_flow_out_index = int(src_flow_out_ordinal)
            src_flow_out_kernel_index = int(src_flow_out_ordinal)
        else:
            src_flow_out_index, src_flow_out_kernel_index = resolve_node_editor_pack_pin_indices(
                node_type_id_int=int(src_type_id_int),
                is_flow=True,
                direction="Out",
                port_name=str(src_port),
                ordinal=int(src_flow_out_ordinal),
                fallback_index=int(src_flow_out_ordinal),
            )
        dst_type_id_int = int(node_type_id_by_graph_node_id.get(str(dst_node_id), 0))
        dst_flow_in_index, dst_flow_in_kernel_index = resolve_node_editor_pack_pin_indices(
            node_type_id_int=int(dst_type_id_int),
            is_flow=True,
            direction="In",
            port_name=str(dst_port),
            ordinal=int(dst_flow_in_ordinal),
            fallback_index=int(dst_flow_in_ordinal),
        )

        src_signal_flow_cpi: Optional[int] = None

        is_listen_signal_event_node = False
        node_def_ref = src_node_payload.get("node_def_ref")
        if isinstance(node_def_ref, dict):
            kind = str(node_def_ref.get("kind") or "").strip().lower()
            if kind == "event":
                outputs = src_node_payload.get("outputs")
                if isinstance(outputs, list) and any(str(x) == "信号来源实体" for x in outputs):
                    is_listen_signal_event_node = True

        src_signal_name = ""
        src_input_constants = src_node_payload.get("input_constants")
        if isinstance(src_input_constants, dict):
            # 首选：GraphModel 语义层给出的静态绑定元信息
            const_signal_name = src_input_constants.get("信号名")
            if isinstance(const_signal_name, str) and str(const_signal_name).strip() != "":
                src_signal_name = str(const_signal_name).strip()
        if src_signal_name == "" and bool(is_listen_signal_event_node) and isinstance(node_def_ref, dict):
            # 兼容：监听信号事件节点通常不带 input_constants（也无 __signal_id），信号名来自 node_def_ref.key 或 title
            key_name = str(node_def_ref.get("key") or "").strip()
            title_name = str(src_title).strip()
            src_signal_name = key_name or (title_name if title_name != "监听信号" else "")

        if src_signal_name != "":
            src_signal_name_port_index: Optional[int] = None
            if bool(is_listen_signal_event_node) and isinstance(signal_listen_signal_name_port_index_by_signal_name, dict):
                v = signal_listen_signal_name_port_index_by_signal_name.get(str(src_signal_name))
                if isinstance(v, int):
                    src_signal_name_port_index = int(v)
            elif str(src_title) == "发送信号" and isinstance(signal_send_signal_name_port_index_by_signal_name, dict):
                v = signal_send_signal_name_port_index_by_signal_name.get(str(src_signal_name))
                if isinstance(v, int):
                    src_signal_name_port_index = int(v)
            elif str(src_title) == "监听信号" and isinstance(signal_listen_signal_name_port_index_by_signal_name, dict):
                v = signal_listen_signal_name_port_index_by_signal_name.get(str(src_signal_name))
                if isinstance(v, int):
                    src_signal_name_port_index = int(v)
            elif str(src_title) in {"发送信号到服务端", "向服务器节点图发送信号"} and isinstance(
                signal_server_send_signal_name_port_index_by_signal_name, dict
            ):
                v = signal_server_send_signal_name_port_index_by_signal_name.get(str(src_signal_name))
                if isinstance(v, int):
                    src_signal_name_port_index = int(v)
            # 真源对齐：generic runtime（300000/300001/300002）信号节点的 flow records 不写 compositePinIndex，
            # 避免 field_7 误导编辑器端口解释；仅当节点 runtime 已切换为 signal-specific（0x4000xxxx+）时才写入。
            if (
                isinstance(src_signal_name_port_index, int)
                and int(src_signal_name_port_index) > 0
                and int(src_type_id_int) >= 0x40000000
            ):
                src_signal_flow_cpi = int(src_signal_name_port_index) - 1

        record_text = _build_flow_link_record_text(
            src_flow_out_index=int(src_flow_out_index),
            dst_node_id_int=int(dst_node_id_int),
            dst_flow_in_index=int(dst_flow_in_index),
            src_flow_out_kernel_index=int(src_flow_out_kernel_index),
            dst_flow_in_kernel_index=int(dst_flow_in_kernel_index),
            src_composite_pin_index=src_signal_flow_cpi,
        )

        src_node_obj = node_object_by_node_id_int[int(src_node_id_int)]
        _ensure_record_list(src_node_obj).append(record_text)
        added_flow_edges += 1

    return int(added_flow_edges)

