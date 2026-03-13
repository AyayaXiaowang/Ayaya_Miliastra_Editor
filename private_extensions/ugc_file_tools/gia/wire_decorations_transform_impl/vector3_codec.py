from __future__ import annotations

"""Vector3(fixed32) wire-level codec helpers."""

import struct
from typing import List, Optional, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    VECTOR3_FIELD_X,
    VECTOR3_FIELD_Y,
    VECTOR3_FIELD_Z,
    VECTOR3_FIXED32_BYTES,
    WIRE_TYPE_FIXED32,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import parse_chunks
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_tag
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks


def encode_fixed32_float(value: float) -> bytes:
    """Encode a python float into protobuf fixed32 little-endian bytes."""
    return struct.pack("<f", float(value))


def build_vector3_message(x: float, y: float, z: float) -> bytes:
    """Build a Vector3 message payload from x/y/z floats."""
    chunks = [
        (encode_tag(VECTOR3_FIELD_X, WIRE_TYPE_FIXED32), encode_fixed32_float(float(x))),
        (encode_tag(VECTOR3_FIELD_Y, WIRE_TYPE_FIXED32), encode_fixed32_float(float(y))),
        (encode_tag(VECTOR3_FIELD_Z, WIRE_TYPE_FIXED32), encode_fixed32_float(float(z))),
    ]
    return encode_wire_chunks(chunks)


def decode_vector3_message(payload: bytes) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Decode a Vector3 message payload into optional x/y/z floats."""
    if not payload:
        return None, None, None
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if consumed != len(payload):
        raise ValueError("vector3 payload wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    for c in parsed:
        if c.wire_type != WIRE_TYPE_FIXED32:
            continue
        if len(c.value_raw) < VECTOR3_FIXED32_BYTES:
            raise ValueError("vector3 fixed32 value_raw truncated")
        if c.field_number == VECTOR3_FIELD_X:
            x = struct.unpack("<f", c.value_raw[:VECTOR3_FIXED32_BYTES])[0]
        elif c.field_number == VECTOR3_FIELD_Y:
            y = struct.unpack("<f", c.value_raw[:VECTOR3_FIXED32_BYTES])[0]
        elif c.field_number == VECTOR3_FIELD_Z:
            z = struct.unpack("<f", c.value_raw[:VECTOR3_FIXED32_BYTES])[0]
    return x, y, z


def decode_vector3_message_with_default(payload: bytes, *, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Decode a Vector3 message payload and fill missing fields with default."""
    x, y, z = decode_vector3_message(payload)
    dx, dy, dz = tuple(default)
    return (
        float(dx if x is None else x),
        float(dy if y is None else y),
        float(dz if z is None else z),
    )

