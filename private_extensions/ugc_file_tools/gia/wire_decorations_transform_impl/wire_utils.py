from __future__ import annotations

"""Low-level wire helpers shared by decorations transform implementation."""

from dataclasses import dataclass
from typing import List, Sequence, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import (
    ProtobufLikeParseOptions,
    decode_varint_with_raw,
    encode_tag,
    encode_varint,
    parse_message,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    PROBE_BYTES_PREVIEW_LENGTH,
    PROBE_MAX_DEPTH,
    PROBE_MAX_LENGTH_DELIMITED_STRING_BYTES,
    PROBE_MAX_MESSAGE_BYTES_FOR_PROBE,
    PROBE_MAX_PACKED_ITEMS,
    WIRE_TYPE_VARINT,
)
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import parse_tag_raw


@dataclass(frozen=True, slots=True)
class WireChunk:
    field_number: int
    wire_type: int
    tag_raw: bytes
    value_raw: bytes


_PROBE_OPTIONS = ProtobufLikeParseOptions(
    max_depth=PROBE_MAX_DEPTH,
    bytes_preview_length=PROBE_BYTES_PREVIEW_LENGTH,
    max_length_delimited_string_bytes=PROBE_MAX_LENGTH_DELIMITED_STRING_BYTES,
    max_packed_items=PROBE_MAX_PACKED_ITEMS,
    max_message_bytes_for_probe=PROBE_MAX_MESSAGE_BYTES_FOR_PROBE,
)


def parse_chunks(chunks: List[Tuple[bytes, bytes]]) -> List[WireChunk]:
    """Parse raw wire chunks into structured WireChunk objects."""
    out: List[WireChunk] = []
    for tag_raw, value_raw in list(chunks):
        tag = parse_tag_raw(tag_raw)
        out.append(
            WireChunk(
                field_number=int(tag.field_number),
                wire_type=int(tag.wire_type),
                tag_raw=bytes(tag_raw),
                value_raw=bytes(value_raw),
            )
        )
    return out


def is_valid_message_payload(payload: bytes) -> bool:
    """Return True if payload looks like a fully-consumed protobuf-like message."""
    if not payload:
        return False
    message_json, next_offset, ok, _error = parse_message(
        byte_data=payload,
        start_offset=0,
        end_offset=len(payload),
        depth=0,
        options=_PROBE_OPTIONS,
    )
    if not ok:
        return False
    if next_offset != len(payload):
        return False
    entry_count = int(message_json.get("_meta", {}).get("entry_count", 0))
    return entry_count > 0


def decode_varint_value(value_raw: bytes) -> int:
    """Decode a varint from value_raw and require full consumption."""
    value, next_offset, _raw, ok = decode_varint_with_raw(value_raw, 0, len(value_raw))
    if not ok or next_offset != len(value_raw):
        raise ValueError("invalid varint value_raw")
    return int(value)


def pack_varints(values: Sequence[int]) -> bytes:
    """Pack a sequence of integers as concatenated varints."""
    out: List[bytes] = []
    for v in list(values):
        out.append(encode_varint(int(v)))
    return b"".join(out)


def patch_first_varint_field(message_bytes: bytes, *, field_number: int, new_value: int) -> bytes:
    """Patch the first varint field in a message, inserting it when missing."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (varint patch)")
    parsed = parse_chunks(chunks_raw)

    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == int(field_number) and c.wire_type == WIRE_TYPE_VARINT and not replaced:
            out.append((c.tag_raw, encode_varint(int(new_value))))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(int(field_number), WIRE_TYPE_VARINT), encode_varint(int(new_value))))
    return encode_wire_chunks(out)

