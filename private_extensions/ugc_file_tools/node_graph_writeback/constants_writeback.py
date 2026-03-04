from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .constants_writeback_parts.context import _build_constants_writeback_context
from .constants_writeback_parts.stage_dynamic_ports import patch_dynamic_port_records_inplace
from .constants_writeback_parts.stage_inparam_constants import write_input_constants_inplace
from .constants_writeback_parts.stage_outparams import write_outparam_types_inplace
from .constants_writeback_parts.stage_prepare_node import prepare_node_state_for_constants_writeback
from .constants_writeback_parts.stage_runtime_id import patch_node_runtime_id_inplace
from .constants_writeback_parts.stage_signal_meta import patch_signal_meta_records_if_needed
from .constants_writeback_parts.types import _ConstantsWritebackCounters


@dataclass(frozen=True)
class _ConstantsWritebackResult:
    input_constants_written: int
    enum_constants_total: int
    enum_constants_written: int
    skipped_enum_constants: List[Dict[str, Any]]


def apply_input_constants_and_outparam_types(
    *,
    sorted_nodes: List[Tuple[float, float, str, str, Dict[str, Any]]],
    edges: List[Dict[str, Any]],
    node_defs_by_name: Dict[str, Any],
    node_id_int_by_graph_node_id: Dict[str, int],
    node_type_id_by_graph_node_id: Dict[str, int],
    node_object_by_node_id_int: Dict[int, Dict[str, Any]],
    outparam_record_template_by_type_id_and_index_and_var_type: Dict[int, Dict[int, Dict[int, str]]],
    record_id_by_node_type_id_and_inparam_index: Optional[Dict[int, Dict[int, int]]] = None,
    # base `.gil` 提取：signal_name -> node_def_id（0x40000000+）
    signal_send_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_node_def_id_by_signal_name: Optional[Dict[str, int]] = None,
    signal_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_listen_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_listen_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    signal_server_send_signal_name_port_index_by_signal_name: Optional[Dict[str, int]] = None,
    signal_server_send_param_port_indices_by_signal_name: Optional[Dict[str, List[int]]] = None,
    # base `.gil` 提取：signal_name -> [param_var_type_id]（按信号规格参数顺序）
    signal_param_var_type_ids_by_signal_name: Optional[Dict[str, List[int]]] = None,
    # base `.gil` 提取：signal_name -> signal_index_int（signal_entry.field_6）
    signal_index_by_signal_name: Optional[Dict[str, int]] = None,
    graph_scope: str = "server",
    graph_variable_type_text_by_name: Optional[Dict[str, str]] = None,
) -> _ConstantsWritebackResult:
    """
    写回：
    - 节点输入常量（input_constants → InParam pins）
    - 泛型输出端口的 OutParam pin 类型（按 typed JSON 的 output_port_types 替换/追加）
    """
    counters = _ConstantsWritebackCounters()
    skipped_enum_constants: List[Dict[str, Any]] = []
    ctx = _build_constants_writeback_context(
        sorted_nodes=list(sorted_nodes),
        edges=list(edges),
        graph_scope=str(graph_scope),
        graph_variable_type_text_by_name=(dict(graph_variable_type_text_by_name or {})),
    )

    for node_item in list(sorted_nodes):
        state = prepare_node_state_for_constants_writeback(
            ctx=ctx,
            node_item=node_item,
            node_defs_by_name=node_defs_by_name,
            node_id_int_by_graph_node_id=node_id_int_by_graph_node_id,
            node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
            node_object_by_node_id_int=node_object_by_node_id_int,
            signal_send_signal_name_port_index_by_signal_name=signal_send_signal_name_port_index_by_signal_name,
            signal_send_param_port_indices_by_signal_name=signal_send_param_port_indices_by_signal_name,
            signal_listen_signal_name_port_index_by_signal_name=signal_listen_signal_name_port_index_by_signal_name,
            signal_listen_param_port_indices_by_signal_name=signal_listen_param_port_indices_by_signal_name,
            signal_server_send_signal_name_port_index_by_signal_name=signal_server_send_signal_name_port_index_by_signal_name,
            signal_server_send_param_port_indices_by_signal_name=signal_server_send_param_port_indices_by_signal_name,
            signal_send_node_def_id_by_signal_name=signal_send_node_def_id_by_signal_name,
            signal_listen_node_def_id_by_signal_name=signal_listen_node_def_id_by_signal_name,
            signal_server_send_node_def_id_by_signal_name=signal_server_send_node_def_id_by_signal_name,
            signal_param_var_type_ids_by_signal_name=signal_param_var_type_ids_by_signal_name,
            signal_index_by_signal_name=signal_index_by_signal_name,
        )
        if state is None:
            continue

        write_input_constants_inplace(
            ctx=ctx,
            state=state,
            counters=counters,
            skipped_enum_constants=skipped_enum_constants,
            node_type_id_by_graph_node_id=node_type_id_by_graph_node_id,
            record_id_by_node_type_id_and_inparam_index=record_id_by_node_type_id_and_inparam_index,
        )

        patch_signal_meta_records_if_needed(
            records=state.records,
            node_type_id_int=int(state.node_type_id_int_for_node),
            signal_binding_role=str(state.signal_binding_role),
            signal_binding_name=str(state.signal_binding_name),
            signal_binding_source_ref_node_def_id_int=state.signal_binding_source_ref_node_def_id_int,
            signal_binding_param_port_indices=state.signal_binding_param_port_indices,
            signal_binding_signal_name_port_index=state.signal_binding_signal_name_port_index,
        )
        if (
            str(state.signal_binding_role or "").strip() != ""
            and isinstance(state.signal_binding_signal_index_int, int)
            and int(state.node_type_id_int_for_node) >= 0x40000000
        ):
            # 对齐真源：signal-specific 信号节点实例写入 signal_index（node.field_9）
            state.node_obj["9"] = int(state.signal_binding_signal_index_int)

        patch_dynamic_port_records_inplace(ctx=ctx, state=state)

        write_outparam_types_inplace(
            ctx=ctx,
            state=state,
            outparam_record_template_by_type_id_and_index_and_var_type=outparam_record_template_by_type_id_and_index_and_var_type,
        )

        patch_node_runtime_id_inplace(ctx=ctx, state=state)

    return _ConstantsWritebackResult(
        input_constants_written=int(counters.input_constants_written),
        enum_constants_total=int(counters.enum_constants_total),
        enum_constants_written=int(counters.enum_constants_written),
        skipped_enum_constants=list(skipped_enum_constants),
    )

