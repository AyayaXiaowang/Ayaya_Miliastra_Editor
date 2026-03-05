from __future__ import annotations

from typing import Any, Dict

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text


def _build_server_node_property_binary_text(*, node_id_int: int) -> str:
    """构造 server 节点 NodeProperty 的 <binary_data> 文本（genericId/concreteId 通用）。"""
    # 对齐样本：
    # - builtin 节点：field_3(kind)=22000
    # - 自定义 node_def（graph-scope 前缀 0x4000/0x4080，以及提升后的 runtime 前缀 0x6000/0x6080）：field_3(kind)=22001
    node_id_value = int(node_id_int)
    scope_prefix = int(node_id_value) & int(0xFF800000)
    node_kind_int = 22001 if scope_prefix in {0x40000000, 0x40800000, 0x60000000, 0x60800000} else 22000
    msg: Dict[str, Any] = {"1": 10001, "2": 20000, "3": int(node_kind_int), "5": int(node_id_value)}
    return format_binary_data_hex_text(encode_message(msg))


