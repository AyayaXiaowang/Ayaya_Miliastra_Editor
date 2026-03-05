from __future__ import annotations

"""
wire-level 编解码：按 tag_raw/value_raw 拆分与重组。

实现单一真源位于 `ugc_file_tools.gil_dump_codec.protobuf_like`，本模块只做命名空间收口。
"""

from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_wire_chunks, encode_wire_chunks

__all__ = ["decode_message_to_wire_chunks", "encode_wire_chunks"]

