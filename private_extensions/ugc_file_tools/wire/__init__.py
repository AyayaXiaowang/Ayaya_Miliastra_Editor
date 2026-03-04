from __future__ import annotations

"""
wire-level 相关能力命名空间。

这里聚合“protobuf-like 的 wire 层（tag/value 原始字节）”工具，避免在各功能域里出现
多套相似的 `wire_patch` / `wire_chunk` 实现。
"""

from .codec import decode_message_to_wire_chunks, encode_wire_chunks  # noqa: F401
from .patch import (  # noqa: F401
    ParsedTag,
    build_length_delimited_value_raw,
    parse_tag_raw,
    replace_length_delimited_fields_payload_bytes_in_message_bytes,
    replace_varint_value_raw,
    split_length_delimited_value_raw,
    upsert_varint_field,
)

__all__ = [
    "decode_message_to_wire_chunks",
    "encode_wire_chunks",
    "ParsedTag",
    "parse_tag_raw",
    "split_length_delimited_value_raw",
    "build_length_delimited_value_raw",
    "replace_length_delimited_fields_payload_bytes_in_message_bytes",
    "replace_varint_value_raw",
    "upsert_varint_field",
]

