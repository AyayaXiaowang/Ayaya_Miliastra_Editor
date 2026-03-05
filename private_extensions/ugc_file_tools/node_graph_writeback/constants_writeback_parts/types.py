from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class _ConstantsWritebackCounters:
    input_constants_written: int = 0
    enum_constants_total: int = 0
    enum_constants_written: int = 0


@dataclass(frozen=True)
class _ConstantsWritebackContext:
    graph_scope: str
    graph_variable_type_text_map: Dict[str, str]
    node_entry_by_id: Dict[int, Dict[str, Any]]
    enum_entry_by_id: Dict[int, Dict[str, Any]]
    nep_nodes_by_id: Dict[int, Dict[str, Any]]
    inferred_out_type_text: Dict[Tuple[str, str], str]
    inferred_in_type_text: Dict[Tuple[str, str], str]
    send_signal_nodes_with_signal_name_in_edge: set[str]
    listen_signal_nodes_with_signal_name_in_edge: set[str]
    server_send_signal_nodes_with_signal_name_in_edge: set[str]


@dataclass
class _ConstantsWritebackNodeState:
    title: str
    node_id: str
    node_payload: Dict[str, Any]
    node_def: Any
    node_id_int: int
    node_obj: Dict[str, Any]
    records: List[Any]
    data_inputs: List[str]
    node_type_id_int_for_node: int
    input_constants: Optional[Dict[str, Any]] = None

    dict_key_vt_for_node: Optional[int] = None
    dict_value_vt_for_node: Optional[int] = None
    assembly_dict_key_vt_for_node: Optional[int] = None
    assembly_dict_value_vt_for_node: Optional[int] = None

    graph_var_value_type_text: str = ""
    t_dict_in_index_of_concrete: Optional[int] = None
    t_dict_out_index_of_concrete: Optional[int] = None

    variant_primary_vt_candidates: set[int] = field(default_factory=set)
    forced_concrete_runtime_id: Optional[int] = None
    forced_index_of_concrete_by_port: Optional[Dict[str, int]] = None
    forced_out_index_of_concrete_by_port: Optional[Dict[str, int]] = None

    signal_binding_role: str = ""
    signal_binding_name: str = ""
    # 写回口径：即便节点 runtime_id 保持 generic(300000/300001/300002)，
    # 只要 base `.gil` 能提供对应 signal node_def_id（0x40000000+），仍应写入 META/source_ref 与 compositePinIndex。
    signal_binding_source_ref_node_def_id_int: Optional[int] = None
    signal_binding_param_port_indices: Optional[List[int]] = None
    signal_binding_signal_name_port_index: Optional[int] = None
    # 信号表 index（signal_entry.field_6）：用于在信号节点实例写回 field_9（对齐真源样本）。
    signal_binding_signal_index_int: Optional[int] = None
    # 发送信号参数端口 VarType（按信号规格参数顺序）；用于覆写 GraphModel 的泛型端口类型，避免编辑器端口类型错配。
    signal_binding_param_var_type_ids: Optional[List[int]] = None

