from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ugc_file_tools.node_graph_semantics.enum_codec import (
    build_entry_by_id_map as _build_entry_by_id_map,
    load_node_data_index_doc as _load_node_data_index_doc,
)
from ugc_file_tools.node_graph_semantics.port_type_inference import (
    infer_input_type_text_by_dst_node_and_port as _infer_input_type_text_by_dst_node_and_port,
)
from ugc_file_tools.node_graph_semantics.type_inference import (
    infer_output_port_type_by_src_node_and_port as _infer_output_port_type_by_src_node_and_port,
)

from ..node_editor_pack import _load_node_editor_pack_nodes_by_id
from ..edges_writeback import _prune_data_edges_like_after_game_for_known_nodes
from ..writeback_feature_flags import is_writeback_feature_enabled
from .types import _ConstantsWritebackContext


def _build_constants_writeback_context(
    *,
    sorted_nodes: List[Tuple[float, float, str, str, Dict[str, Any]]],
    edges: List[Dict[str, Any]],
    graph_scope: str,
    graph_variable_type_text_by_name: Dict[str, str] | None,
) -> _ConstantsWritebackContext:
    # NOTE: constants/outparam 推断必须与 edges 写回使用同一口径的 edge 归一化/裁剪；
    # 否则会出现“常量/OUT_PARAM 按未裁剪 edges 推断写入，但 edges 实际写回时被裁剪掉”，
    # 进而造成 pins mismatches（典型：数据类型转换 OUT_PARAM 被写成 Str，但 after_game 与最终连线都无出边）。
    if is_writeback_feature_enabled("prune_data_edges_like_after_game__data_type_conversion_to_dict_set_value"):
        edges = _prune_data_edges_like_after_game_for_known_nodes(
            edges=list(edges),
            node_title_by_graph_node_id={
                str(node_id0): str(node_payload0.get("title") or "")
                for (_y0, _x0, _title0, node_id0, node_payload0) in list(sorted_nodes)
                if isinstance(node_payload0, dict)
            },
        )

    node_data_doc = _load_node_data_index_doc()
    node_entry_by_id = _build_entry_by_id_map(node_data_doc.get("NodesList"))
    enum_entry_by_id = _build_entry_by_id_map(node_data_doc.get("EnumList"))

    nep_nodes_by_id = _load_node_editor_pack_nodes_by_id()
    send_signal_nodes_with_signal_name_in_edge: set[str] = set()
    listen_signal_nodes_with_signal_name_in_edge: set[str] = set()
    server_send_signal_nodes_with_signal_name_in_edge: set[str] = set()

    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]] = {}
    for (_y0, _x0, _title0, node_id0, node_payload0) in sorted_nodes:
        if isinstance(node_payload0, dict):
            graph_node_by_graph_node_id[str(node_id0)] = node_payload0

    inferred_out_type_text = _infer_output_port_type_by_src_node_and_port(
        edges=list(edges),
        graph_node_by_graph_node_id=dict(graph_node_by_graph_node_id),
    )
    graph_variable_type_text_map = dict(graph_variable_type_text_by_name or {})
    inferred_in_type_text = _infer_input_type_text_by_dst_node_and_port(
        edges=list(edges),
        graph_node_by_graph_node_id=dict(graph_node_by_graph_node_id),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_map),
    )

    for edge in list(edges):
        if not isinstance(edge, dict):
            continue
        dst_node = str(edge.get("dst_node") or "")
        dst_port = str(edge.get("dst_port") or "")
        if dst_node == "" or dst_port != "信号名":
            continue
        dst_payload0 = None
        for (_y0, _x0, _title0, node_id0, node_payload0) in sorted_nodes:
            if str(node_id0) == dst_node:
                dst_payload0 = node_payload0
                break
        if not isinstance(dst_payload0, dict):
            continue
        title0 = str(dst_payload0.get("title") or "")
        if title0 == "发送信号":
            send_signal_nodes_with_signal_name_in_edge.add(str(dst_node))
        if title0 == "监听信号":
            listen_signal_nodes_with_signal_name_in_edge.add(str(dst_node))
        if title0 in {"发送信号到服务端", "向服务器节点图发送信号"}:
            server_send_signal_nodes_with_signal_name_in_edge.add(str(dst_node))

    return _ConstantsWritebackContext(
        graph_scope=str(graph_scope),
        graph_variable_type_text_map=dict(graph_variable_type_text_map),
        node_entry_by_id=dict(node_entry_by_id),
        enum_entry_by_id=dict(enum_entry_by_id),
        nep_nodes_by_id=dict(nep_nodes_by_id),
        inferred_out_type_text=dict(inferred_out_type_text),
        inferred_in_type_text=dict(inferred_in_type_text),
        send_signal_nodes_with_signal_name_in_edge=set(send_signal_nodes_with_signal_name_in_edge),
        listen_signal_nodes_with_signal_name_in_edge=set(listen_signal_nodes_with_signal_name_in_edge),
        server_send_signal_nodes_with_signal_name_in_edge=set(server_send_signal_nodes_with_signal_name_in_edge),
    )

