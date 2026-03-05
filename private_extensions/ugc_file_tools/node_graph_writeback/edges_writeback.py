from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.node_graph_semantics.port_type_inference import (
    infer_input_type_text_by_dst_node_and_port as _infer_input_type_text_by_dst_node_and_port,
)
from ugc_file_tools.node_graph_semantics.type_inference import (
    infer_output_port_type_by_src_node_and_port as _infer_output_port_type_by_src_node_and_port,
)

from .edges_writeback_data import write_data_edges_inplace
from .edges_writeback_flow import write_flow_edges_inplace
from .edges_writeback_split import split_edges_by_flow_or_data
from .writeback_feature_flags import is_writeback_feature_enabled


def _prune_data_edges_like_after_game_for_known_nodes(
    *,
    edges: List[Dict[str, Any]],
    node_title_by_graph_node_id: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    对齐真源（游戏导入/编译后再导出）的一个已观测裁剪行为：

    - GraphModel(JSON) 中存在的部分 data edges 在 after_game `.gil` 中会消失；
    - 当前已稳定复现的模式为：
      Data_Type_Conversion(数据类型转换).输出  ->  Set_or_Add_Key_Value_Pairs_to_Dictionary(对字典设置或新增键值对).值

    说明：
    - 该裁剪会显著影响 payload Graph IR diff 的“extra edges”噪声；
    - 本函数以 after_game 导出的实际 wire 行为为真源：当命中该模式且“目标端口仍有其它数据供给”时才裁剪，
      避免裁剪掉唯一入边导致语义/类型推断退化（例如数据类型转换输出端口被错误回退为模板默认类型）。
    - 这里按节点中文 title + 端口名做保守匹配（避免依赖 node_type_id 映射/样本覆盖差异）。
    """
    if not edges:
        return []

    _TITLE_DATA_TYPE_CONVERSION = "数据类型转换"
    _TITLE_DICT_SET = "对字典设置或新增键值对"
    _SRC_PORT_OUTPUT = "输出"
    _DST_PORT_VALUE = "值"

    pruned: List[Dict[str, Any]] = []
    edges_list = list(edges)
    for edge_index, e in enumerate(edges_list):
        if not isinstance(e, dict):
            continue
        src_node = str(e.get("src_node") or "").strip()
        dst_node = str(e.get("dst_node") or "").strip()
        src_port = str(e.get("src_port") or "").strip()
        dst_port = str(e.get("dst_port") or "").strip()
        if not src_node or not dst_node:
            pruned.append(e)
            continue

        src_title = str(node_title_by_graph_node_id.get(src_node) or "").strip()
        dst_title = str(node_title_by_graph_node_id.get(dst_node) or "").strip()

        should_drop = (
            src_title == _TITLE_DATA_TYPE_CONVERSION
            and src_port == _SRC_PORT_OUTPUT
            and dst_title == _TITLE_DICT_SET
            and dst_port == _DST_PORT_VALUE
        )
        if should_drop:
            # 仅当目标端口仍有其它数据入边时才裁剪（避免裁剪唯一入边改变语义/类型推断证据）。
            has_other_incoming = False
            for other_i, other in enumerate(edges_list):
                if int(other_i) == int(edge_index):
                    continue
                if not isinstance(other, dict):
                    continue
                other_dst_node = str(other.get("dst_node") or "").strip()
                other_dst_port = str(other.get("dst_port") or "").strip()
                if other_dst_node == dst_node and other_dst_port == dst_port:
                    has_other_incoming = True
                    break
            if has_other_incoming:
                continue
        pruned.append(e)
    return list(pruned)


def write_edges_inplace(
    *,
    edges: List[Dict[str, Any]],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_title_by_graph_node_id: Dict[str, str],
    graph_node_by_graph_node_id: Dict[str, Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    data_link_record_template_by_dst_type_id_and_slot_index: Dict[int, Dict[int, str]],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]] = None,
    graph_scope: str = "server",
    graph_variable_type_text_by_name: Optional[Dict[str, str]] = None,
    signal_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_listen_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_server_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_param_var_type_ids_by_signal_name: Optional[Dict[str, List[int]]] = None,
) -> Dict[str, int]:
    if is_writeback_feature_enabled("prune_data_edges_like_after_game__data_type_conversion_to_dict_set_value"):
        edges = _prune_data_edges_like_after_game_for_known_nodes(
            edges=list(edges),
            node_title_by_graph_node_id=dict(node_title_by_graph_node_id),
        )
    flow_edges, data_edges = split_edges_by_flow_or_data(
        edges=edges,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
    )
    inferred_out_type_text = _infer_output_port_type_by_src_node_and_port(
        edges=list(edges),
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
    )
    inferred_in_type_text = _infer_input_type_text_by_dst_node_and_port(
        edges=list(edges),
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name or {}),
    )

    added_flow_edges = write_flow_edges_inplace(
        flow_edges=flow_edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        signal_send_signal_name_port_index_by_signal_name=signal_send_signal_name_port_index_by_signal_name,
        signal_listen_signal_name_port_index_by_signal_name=signal_listen_signal_name_port_index_by_signal_name,
        signal_server_send_signal_name_port_index_by_signal_name=signal_server_send_signal_name_port_index_by_signal_name,
    )
    added_data_edges = write_data_edges_inplace(
        data_edges=data_edges,
        node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
        node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
        node_title_by_graph_node_id=node_title_by_graph_node_id,
        graph_node_by_graph_node_id=graph_node_by_graph_node_id,
        node_defs_by_name=node_defs_by_name,
        node_object_by_node_id_int=node_object_by_node_id_int,
        data_link_record_template_by_dst_type_id_and_slot_index=data_link_record_template_by_dst_type_id_and_slot_index,
        record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
        graph_scope=str(graph_scope),
        graph_variable_type_text_by_name=dict(graph_variable_type_text_by_name or {}),
        inferred_out_type_text=dict(inferred_out_type_text),
        inferred_in_type_text=dict(inferred_in_type_text),
        signal_send_param_port_indices_by_signal_name=signal_send_param_port_indices_by_signal_name,
        signal_listen_param_port_indices_by_signal_name=signal_listen_param_port_indices_by_signal_name,
        signal_server_send_param_port_indices_by_signal_name=signal_server_send_param_port_indices_by_signal_name,
        signal_param_var_type_ids_by_signal_name=signal_param_var_type_ids_by_signal_name,
    )

    return {
        "flow_edges_in_graph_model": int(len(flow_edges)),
        "flow_edges_written": int(added_flow_edges),
        "data_edges_in_graph_model": int(len(data_edges)),
        "data_edges_written": int(added_data_edges),
    }

