from __future__ import annotations

"""Transform message extraction and patch helpers for wire-level operations."""

from typing import List, Optional, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    TRANSFORM_FIELD_POS,
    TRANSFORM_FIELD_ROT_DEG,
    TRANSFORM_FIELD_SCALE,
    WIRE_TYPE_LENGTH_DELIMITED,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.vector3_codec import (
    build_vector3_message,
    decode_vector3_message,
    decode_vector3_message_with_default,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import (
    is_valid_message_payload,
    parse_chunks,
)
from ugc_file_tools.gil_dump_codec.protobuf_like import encode_tag
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, split_length_delimited_value_raw


def extract_trs_from_transform_message(transform_bytes: bytes) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """Extract position/rotation/scale from a Transform-like message payload."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("transform: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    pos: Optional[Tuple[float, float, float]] = None
    rot_deg = (0.0, 0.0, 0.0)
    scale = (1.0, 1.0, 1.0)

    for c in parsed:
        if c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        if c.field_number == TRANSFORM_FIELD_POS:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            x, y, z = decode_vector3_message(payload)
            if x is None or y is None or z is None:
                raise ValueError("transform.pos(Vector3) 缺字段")
            pos = (float(x), float(y), float(z))
        elif c.field_number == TRANSFORM_FIELD_ROT_DEG:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            rot_deg = decode_vector3_message_with_default(payload, default=rot_deg)
        elif c.field_number == TRANSFORM_FIELD_SCALE:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            scale = decode_vector3_message_with_default(payload, default=scale)

    if pos is None:
        raise ValueError("transform: 缺少 position(field_1)")
    return tuple(pos), tuple(rot_deg), tuple(scale)


def patch_transform_trs_optional(
    transform_bytes: bytes,
    *,
    pos: Optional[Tuple[float, float, float]],
    rot_deg: Optional[Tuple[float, float, float]],
    scale: Optional[Tuple[float, float, float]],
) -> bytes:
    """Patch Transform-like message fields with optional TRS replacements."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("wire decode not fully consumed (transform)")
    parsed = parse_chunks(chunks_raw)

    want_pos = pos is not None
    want_rot = rot_deg is not None
    want_scale = scale is not None

    wrote_pos = False
    wrote_rot = False
    wrote_scale = False

    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.wire_type == WIRE_TYPE_LENGTH_DELIMITED and c.field_number in (TRANSFORM_FIELD_POS, TRANSFORM_FIELD_ROT_DEG, TRANSFORM_FIELD_SCALE):
            if c.field_number == TRANSFORM_FIELD_POS and want_pos and (not wrote_pos):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(build_vector3_message(float(pos[0]), float(pos[1]), float(pos[2]))),  # type: ignore[index]
                    )
                )
                wrote_pos = True
                continue
            if c.field_number == TRANSFORM_FIELD_ROT_DEG and want_rot and (not wrote_rot):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(
                            build_vector3_message(float(rot_deg[0]), float(rot_deg[1]), float(rot_deg[2]))  # type: ignore[index]
                        ),
                    )
                )
                wrote_rot = True
                continue
            if c.field_number == TRANSFORM_FIELD_SCALE and want_scale and (not wrote_scale):
                out.append(
                    (
                        c.tag_raw,
                        build_length_delimited_value_raw(
                            build_vector3_message(float(scale[0]), float(scale[1]), float(scale[2]))  # type: ignore[index]
                        ),
                    )
                )
                wrote_scale = True
                continue
        out.append((c.tag_raw, c.value_raw))

    if want_pos and (not wrote_pos):
        out.append(
            (
                encode_tag(TRANSFORM_FIELD_POS, WIRE_TYPE_LENGTH_DELIMITED),
                build_length_delimited_value_raw(build_vector3_message(float(pos[0]), float(pos[1]), float(pos[2]))),  # type: ignore[index]
            )
        )
    if want_rot and (not wrote_rot):
        out.append(
            (
                encode_tag(TRANSFORM_FIELD_ROT_DEG, WIRE_TYPE_LENGTH_DELIMITED),
                build_length_delimited_value_raw(build_vector3_message(float(rot_deg[0]), float(rot_deg[1]), float(rot_deg[2]))),  # type: ignore[index]
            )
        )
    if want_scale and (not wrote_scale):
        out.append(
            (
                encode_tag(TRANSFORM_FIELD_SCALE, WIRE_TYPE_LENGTH_DELIMITED),
                build_length_delimited_value_raw(build_vector3_message(float(scale[0]), float(scale[1]), float(scale[2]))),  # type: ignore[index]
            )
        )

    return encode_wire_chunks(out)


def patch_transform_pos_only(transform_bytes: bytes, *, pos: Tuple[float, float, float]) -> bytes:
    """Patch Transform-like message position(field_1) with the given vec3."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("wire decode not fully consumed (transform)")
    parsed = parse_chunks(chunks_raw)

    pos_payload = build_vector3_message(pos[0], pos[1], pos[2])
    pos_value_raw = build_length_delimited_value_raw(pos_payload)

    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == TRANSFORM_FIELD_POS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not replaced:
            out.append((c.tag_raw, pos_value_raw))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(TRANSFORM_FIELD_POS, WIRE_TYPE_LENGTH_DELIMITED), pos_value_raw))
    return encode_wire_chunks(out)


def find_first_transform_trs_in_message(
    message_bytes: bytes,
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]]:
    """Recursively search the first Transform-like TRS payload in a message."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform search)")
    parsed = parse_chunks(chunks_raw)

    pos_payload: Optional[bytes] = None
    rot_payload: Optional[bytes] = None
    scale_payload: Optional[bytes] = None
    for c in parsed:
        if c.wire_type != WIRE_TYPE_LENGTH_DELIMITED or c.field_number not in (TRANSFORM_FIELD_POS, TRANSFORM_FIELD_ROT_DEG, TRANSFORM_FIELD_SCALE):
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(payload):
            continue
        if c.field_number == TRANSFORM_FIELD_POS and pos_payload is None:
            pos_payload = bytes(payload)
        elif c.field_number == TRANSFORM_FIELD_ROT_DEG and rot_payload is None:
            rot_payload = bytes(payload)
        elif c.field_number == TRANSFORM_FIELD_SCALE and scale_payload is None:
            scale_payload = bytes(payload)

    if pos_payload is not None:
        x, y, z = decode_vector3_message(pos_payload)
        if x is not None and y is not None and z is not None:
            rot = decode_vector3_message_with_default(rot_payload or b"", default=(0.0, 0.0, 0.0))
            scl = decode_vector3_message_with_default(scale_payload or b"", default=(1.0, 1.0, 1.0))
            return (float(x), float(y), float(z)), tuple(rot), tuple(scl)

    for c in parsed:
        if c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if is_valid_message_payload(payload):
            found = find_first_transform_trs_in_message(payload)
            if found is not None:
                return found
    return None


def find_first_transform_pos_in_message(message_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    """Recursively search the first Transform-like position payload in a message."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform search)")
    parsed = parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number == TRANSFORM_FIELD_POS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, pos_payload = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(pos_payload):
                x, y, z = decode_vector3_message(pos_payload)
                if x is not None and y is not None and z is not None:
                    return float(x), float(y), float(z)

    for c in parsed:
        if c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, payload = split_length_delimited_value_raw(c.value_raw)
        if is_valid_message_payload(payload):
            found = find_first_transform_pos_in_message(payload)
            if found is not None:
                return found
    return None


def patch_first_transform_pos_in_message(message_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> Tuple[bytes, bool]:
    """Recursively patch the first Transform-like position payload inside a message."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (recursive transform patch)")
    parsed = parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number != TRANSFORM_FIELD_POS or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, pos_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(pos_payload):
            continue
        vx, vy, vz = decode_vector3_message(pos_payload)
        if vx is None or vy is None or vz is None:
            continue
        return patch_transform_pos_only(message_bytes, pos=tuple(new_pos)), True

    out: List[Tuple[bytes, bytes]] = []
    patched_any = False
    for c in parsed:
        if (not patched_any) and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(payload):
                new_payload, patched = patch_first_transform_pos_in_message(payload, new_pos=tuple(new_pos))
                if patched:
                    out.append((c.tag_raw, build_length_delimited_value_raw(new_payload)))
                    patched_any = True
                    continue
        out.append((c.tag_raw, c.value_raw))

    if not patched_any:
        return message_bytes, False
    return encode_wire_chunks(out), True

