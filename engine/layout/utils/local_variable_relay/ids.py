from __future__ import annotations

"""局部变量 relay 的稳定 ID 约定：节点/边前缀、构造与解析工具函数。

约定目标：
- **确定性**：多次自动排版幂等，输出稳定（不使用 uuid）。
- **可解析**：coordinate_assigner 等阶段可从 node_id 推导 block/slot 信息。
- **分层**：`inserter.py` 负责插入逻辑；本模块只承载 ID 规则（避免循环依赖）。
"""

import hashlib
from typing import Optional


LOCAL_VAR_RELAY_NODE_ID_PREFIX = "node_localvar_relay_block_"
LOCAL_VAR_RELAY_SLOT_MARKER = "_slot_"
LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX = "edge_localvar_relay_chain_"
LOCAL_VAR_RELAY_EDGE_ID_MARKER = "_localvar_relay_"


def is_local_var_relay_node_id(node_id: object) -> bool:
    return isinstance(node_id, str) and node_id.startswith(LOCAL_VAR_RELAY_NODE_ID_PREFIX)


def parse_local_var_relay_block_id(node_id: str) -> str:
    """从 relay node_id 推断目标 block_id。

    约定：node_id 形如 `node_localvar_relay_block_<N>_...`
    """
    if not is_local_var_relay_node_id(node_id):
        return ""
    suffix = node_id[len(LOCAL_VAR_RELAY_NODE_ID_PREFIX) :]
    digits = []
    for char in suffix:
        if char.isdigit():
            digits.append(char)
            continue
        break
    if not digits:
        return ""
    return f"block_{int(''.join(digits))}"


def parse_local_var_relay_forced_slot_index(node_id: str) -> Optional[int]:
    """从 relay node_id 解析“强制槽位索引”（用于块内 X 轴放置）。

    约定（可选字段，兼容旧 ID）：
      `node_localvar_relay_block_<N>_slot_<S>_...`

    Returns:
        - int: 若存在 slot 信息则返回
        - None: 若旧格式或缺失 slot
    """
    if not is_local_var_relay_node_id(node_id):
        return None
    marker_index = node_id.find(LOCAL_VAR_RELAY_SLOT_MARKER)
    if marker_index == -1:
        return None
    cursor = marker_index + len(LOCAL_VAR_RELAY_SLOT_MARKER)
    digits: list[str] = []
    while cursor < len(node_id):
        char = node_id[cursor]
        if char.isdigit():
            digits.append(char)
            cursor += 1
            continue
        break
    if not digits:
        return None
    return int("".join(digits))


def _hash_edge_key(edge_key: str, *, length: int = 10) -> str:
    digest = hashlib.sha1(edge_key.encode("utf-8")).hexdigest()
    return digest[: max(6, int(length))]


def _build_relay_node_id(
    *,
    original_edge_key: str,
    relay_index: int,
    target_block_id: str,
    target_slot_index: Optional[int] = None,
) -> str:
    block_id_text = str(target_block_id or "")
    block_index_text = block_id_text.split("_", 1)[-1] if block_id_text.startswith("block_") else ""
    if not block_index_text.isdigit():
        block_index_text = "0"
    edge_hash = _hash_edge_key(original_edge_key, length=10)
    if target_slot_index is None:
        return f"{LOCAL_VAR_RELAY_NODE_ID_PREFIX}{block_index_text}_{edge_hash}_{int(relay_index):02d}"
    slot_index = int(target_slot_index)
    return (
        f"{LOCAL_VAR_RELAY_NODE_ID_PREFIX}{block_index_text}"
        f"{LOCAL_VAR_RELAY_SLOT_MARKER}{slot_index}_{edge_hash}_{int(relay_index):02d}"
    )


def _build_relay_edge_id(original_edge_id: str, link_index: int) -> str:
    return f"{str(original_edge_id)}{LOCAL_VAR_RELAY_EDGE_ID_MARKER}{int(link_index):02d}"


def _build_relay_chain_edge_id(*, chain_key: str, link_index: int) -> str:
    """为“同一源端口共享的 relay 链”生成稳定的边 ID。"""
    edge_hash = _hash_edge_key(f"relay_chain:{str(chain_key or '')}", length=10)
    return f"{LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX}{edge_hash}_{int(link_index):02d}"


__all__ = [
    "LOCAL_VAR_RELAY_NODE_ID_PREFIX",
    "LOCAL_VAR_RELAY_SLOT_MARKER",
    "LOCAL_VAR_RELAY_CHAIN_EDGE_ID_PREFIX",
    "LOCAL_VAR_RELAY_EDGE_ID_MARKER",
    "is_local_var_relay_node_id",
    "parse_local_var_relay_block_id",
    "parse_local_var_relay_forced_slot_index",
]



