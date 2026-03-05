from __future__ import annotations

from .inserter import insert_local_variable_relays_after_global_copy
from .ids import (
    LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX,
    LOCAL_VAR_RELAY_EDGE_ID_MARKER,
    LOCAL_VAR_RELAY_NODE_ID_PREFIX,
    LOCAL_VAR_RELAY_SLOT_MARKER,
    is_local_var_relay_node_id,
    parse_local_var_relay_block_id,
    parse_local_var_relay_forced_slot_index,
)

__all__ = [
    "LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX",
    "LOCAL_VAR_RELAY_EDGE_ID_MARKER",
    "LOCAL_VAR_RELAY_NODE_ID_PREFIX",
    "LOCAL_VAR_RELAY_SLOT_MARKER",
    "is_local_var_relay_node_id",
    "parse_local_var_relay_block_id",
    "parse_local_var_relay_forced_slot_index",
    "insert_local_variable_relays_after_global_copy",
]



