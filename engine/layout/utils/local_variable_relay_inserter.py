from __future__ import annotations

"""
长连线中转节点插入器（兼容入口）。

权威实现位于 `engine.layout.utils.local_variable_relay` 子包；
本模块仅保留旧导入路径，避免布局算法与测试断链。
"""

from .local_variable_relay import (
    LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX,
    LOCAL_VAR_RELAY_EDGE_ID_MARKER,
    LOCAL_VAR_RELAY_NODE_ID_PREFIX,
    LOCAL_VAR_RELAY_SLOT_MARKER,
    insert_local_variable_relays_after_global_copy,
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



