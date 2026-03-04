from __future__ import annotations

"""
wire-level patch helpers（小工具函数）。

实现单一真源位于 `ugc_file_tools.gil_dump_codec.wire_patch`，本模块只做命名空间收口。
"""

from ugc_file_tools.gil_dump_codec.wire_patch import (  # noqa: F401
    ParsedTag,
    build_length_delimited_value_raw,
    parse_tag_raw,
    replace_length_delimited_fields_payload_bytes_in_message_bytes,
    replace_varint_value_raw,
    split_length_delimited_value_raw,
    upsert_varint_field,
)

__all__ = [
    "ParsedTag",
    "parse_tag_raw",
    "split_length_delimited_value_raw",
    "build_length_delimited_value_raw",
    "replace_length_delimited_fields_payload_bytes_in_message_bytes",
    "replace_varint_value_raw",
    "upsert_varint_field",
]

