from __future__ import annotations

"""Accessory(GraphUnit) payload extraction and minimal patch helpers."""

from typing import List, Optional, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    ACCESSORY_ENTRY_FIELD_TRANSFORM,
    ACCESSORY_PARENT_BIND_ENTRY_FIELD_KEY,
    ACCESSORY_PARENT_BIND_FIELD_PARENT_UNIT_ID_INT,
    ACCESSORY_PAYLOAD_FIELD_PARENT_BIND_MAP,
    ACCESSORY_PAYLOAD_FIELD_TRANSFORM_ENTRIES,
    ACCESSORY_PAYLOAD_PARENT_BIND_FIELD_NESTED,
    ACCESSORY_PAYLOAD_PARENT_BIND_KEY,
    ACCESSORY_WRAPPER_FIELD_PAYLOAD,
    WIRE_TYPE_LENGTH_DELIMITED,
    WIRE_TYPE_VARINT,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.transform_codec import (
    extract_trs_from_transform_message,
    patch_transform_trs_optional,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import (
    decode_varint_value,
    is_valid_message_payload,
    parse_chunks,
    patch_first_varint_field,
)
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, split_length_delimited_value_raw


def payload_has_transform(payload_bytes: bytes) -> bool:
    """Return True if payload_bytes contains a transform entry with a nested transform message."""
    if not is_valid_message_payload(payload_bytes):
        return False
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        return False
    parsed = parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number != ACCESSORY_PAYLOAD_FIELD_TRANSFORM_ENTRIES or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = parse_chunks(entry_chunks_raw)
        if any(ec.field_number == ACCESSORY_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED for ec in entry_parsed):
            return True
    return False


def extract_accessory_payload_bytes(accessory_unit_bytes: bytes) -> bytes:
    """Extract accessory payload bytes from an accessory GraphUnit wrapper by structural probing."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=accessory_unit_bytes, start_offset=0, end_offset=len(accessory_unit_bytes))
    if consumed != len(accessory_unit_bytes):
        raise ValueError("accessory unit: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    for c in parsed:
        if c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, wrapper_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(wrapper_payload):
            continue

        wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=wrapper_payload, start_offset=0, end_offset=len(wrapper_payload)
        )
        if consumed2 != len(wrapper_payload):
            continue
        wrapper_parsed = parse_chunks(wrapper_chunks_raw)

        for wc in wrapper_parsed:
            if wc.field_number != ACCESSORY_WRAPPER_FIELD_PAYLOAD or wc.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
                continue
            _lr2, payload_bytes = split_length_delimited_value_raw(wc.value_raw)
            if not is_valid_message_payload(payload_bytes):
                continue
            if payload_has_transform(payload_bytes):
                return bytes(payload_bytes)

    raise ValueError("accessory unit: 找不到 wrapper(payload.field_1)")


def extract_accessory_transform_bytes(payload_bytes: bytes) -> bytes:
    """Extract the Transform message bytes from a decoded accessory payload."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    for c in parsed:
        if c.field_number != ACCESSORY_PAYLOAD_FIELD_TRANSFORM_ENTRIES or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(entry_payload):
            continue

        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = parse_chunks(entry_chunks_raw)

        for ec in entry_parsed:
            if ec.field_number == ACCESSORY_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
                _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
                if not is_valid_message_payload(transform_payload):
                    raise ValueError("accessory payload: transform(field_11) 不是 message")
                return bytes(transform_payload)

    raise ValueError("accessory payload: 找不到 transform（field_5[*].field_11）")


def extract_accessory_parent_unit_id(payload_bytes: bytes) -> int:
    """Extract parent bind unit_id_int from accessory payload parent-bind map entry.key==40."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number != ACCESSORY_PAYLOAD_FIELD_PARENT_BIND_MAP or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        entry_parsed = parse_chunks(entry_chunks_raw)
        entry_key: Optional[int] = None
        nested_payload: Optional[bytes] = None
        for ec in entry_parsed:
            if ec.field_number == ACCESSORY_PARENT_BIND_ENTRY_FIELD_KEY and ec.wire_type == WIRE_TYPE_VARINT and entry_key is None:
                entry_key = decode_varint_value(ec.value_raw)
            if (
                ec.field_number == ACCESSORY_PAYLOAD_PARENT_BIND_FIELD_NESTED
                and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED
                and nested_payload is None
            ):
                _lr2, np = split_length_delimited_value_raw(ec.value_raw)
                nested_payload = bytes(np)
        if entry_key != ACCESSORY_PAYLOAD_PARENT_BIND_KEY or nested_payload is None or (not is_valid_message_payload(nested_payload)):
            continue
        nested_chunks_raw, consumed3 = decode_message_to_wire_chunks(
            data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
        )
        if consumed3 != len(nested_payload):
            continue
        nested_parsed = parse_chunks(nested_chunks_raw)
        for nc in nested_parsed:
            if nc.field_number == ACCESSORY_PARENT_BIND_FIELD_PARENT_UNIT_ID_INT and nc.wire_type == WIRE_TYPE_VARINT:
                return decode_varint_value(nc.value_raw)
    raise ValueError("accessory payload: 找不到 parent bind（field_4 entry.key==40 / field_50.field_502）")


def _patch_accessory_payload_transform_optional(
    payload_bytes: bytes,
    *,
    new_pos: Optional[Tuple[float, float, float]],
    new_rot_deg: Optional[Tuple[float, float, float]],
    new_scale: Optional[Tuple[float, float, float]],
) -> Tuple[bytes, bool]:
    """Patch the first transform entry inside accessory payload with optional TRS changes."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    out: List[Tuple[bytes, bytes]] = []
    transform_patched = False
    for c in parsed:
        if (
            (not transform_patched)
            and c.field_number == ACCESSORY_PAYLOAD_FIELD_TRANSFORM_ENTRIES
            and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED
        ):
            _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
            if not is_valid_message_payload(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 != len(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = parse_chunks(entry_chunks_raw)

            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == ACCESSORY_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not patched_entry:
                    _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
                    if not is_valid_message_payload(transform_payload):
                        new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                        continue
                    new_transform = patch_transform_trs_optional(
                        transform_payload,
                        pos=tuple(new_pos) if new_pos is not None else None,
                        rot_deg=tuple(new_rot_deg) if new_rot_deg is not None else None,
                        scale=tuple(new_scale) if new_scale is not None else None,
                    )
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(new_transform)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if patched_entry:
                out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
                transform_patched = True
            else:
                out.append((c.tag_raw, c.value_raw))
            continue

        out.append((c.tag_raw, c.value_raw))

    if not transform_patched:
        return payload_bytes, False
    return encode_wire_chunks(out), True


def _patch_accessory_payload_parent_bind_optional(payload_bytes: bytes, *, new_parent_unit_id: int) -> Tuple[bytes, bool]:
    """Patch the first parent bind entry.key==40 inside accessory payload to new_parent_unit_id."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("accessory payload: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    out: List[Tuple[bytes, bytes]] = []
    parent_bind_patched = False
    for c in parsed:
        if (
            (not parent_bind_patched)
            and c.field_number == ACCESSORY_PAYLOAD_FIELD_PARENT_BIND_MAP
            and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED
        ):
            _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
            if not is_valid_message_payload(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue

            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 != len(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = parse_chunks(entry_chunks_raw)

            entry_key: Optional[int] = None
            for ec in entry_parsed:
                if ec.field_number == ACCESSORY_PARENT_BIND_ENTRY_FIELD_KEY and ec.wire_type == WIRE_TYPE_VARINT:
                    entry_key = decode_varint_value(ec.value_raw)
                    break
            if entry_key != ACCESSORY_PAYLOAD_PARENT_BIND_KEY:
                out.append((c.tag_raw, c.value_raw))
                continue

            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == ACCESSORY_PAYLOAD_PARENT_BIND_FIELD_NESTED and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not patched_entry:
                    _lr2, nested_payload = split_length_delimited_value_raw(ec.value_raw)
                    if not is_valid_message_payload(nested_payload):
                        raise ValueError("accessory payload: parent bind nested(field_50) 不是 message")
                    patched_nested = patch_first_varint_field(
                        nested_payload,
                        field_number=ACCESSORY_PARENT_BIND_FIELD_PARENT_UNIT_ID_INT,
                        new_value=int(new_parent_unit_id),
                    )
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(patched_nested)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if not patched_entry:
                raise ValueError("accessory payload: 找不到 parent bind entry.field_50.field_502")
            out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
            parent_bind_patched = True
            continue

        out.append((c.tag_raw, c.value_raw))

    if not parent_bind_patched:
        return payload_bytes, False
    return encode_wire_chunks(out), True


def patch_accessory_payload(
    payload_bytes: bytes,
    *,
    new_pos: Optional[Tuple[float, float, float]],
    new_rot_deg: Optional[Tuple[float, float, float]],
    new_scale: Optional[Tuple[float, float, float]],
    new_parent_unit_id: Optional[int],
) -> bytes:
    """Patch accessory payload by minimally updating transform TRS and/or parent bind when requested."""
    want_transform = (new_pos is not None) or (new_rot_deg is not None) or (new_scale is not None)

    out_bytes = bytes(payload_bytes)
    if want_transform:
        out_bytes, ok = _patch_accessory_payload_transform_optional(
            out_bytes,
            new_pos=new_pos,
            new_rot_deg=new_rot_deg,
            new_scale=new_scale,
        )
        if not ok:
            raise ValueError("accessory payload: 找不到可补丁的 transform（field_5[*].field_11）")

    if new_parent_unit_id is not None:
        out_bytes, ok2 = _patch_accessory_payload_parent_bind_optional(out_bytes, new_parent_unit_id=int(new_parent_unit_id))
        if not ok2:
            raise ValueError("accessory payload: 找不到可补丁的 parent bind（field_4 entry.key==40 / field_50.field_502）")

    return bytes(out_bytes)


def patch_accessory_unit(
    accessory_unit_bytes: bytes,
    *,
    new_pos: Optional[Tuple[float, float, float]],
    new_rot_deg: Optional[Tuple[float, float, float]],
    new_scale: Optional[Tuple[float, float, float]],
    new_parent_unit_id: Optional[int],
) -> bytes:
    """Patch an accessory GraphUnit by probing its wrapper and patching the first payload that contains a transform."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=accessory_unit_bytes, start_offset=0, end_offset=len(accessory_unit_bytes))
    if consumed != len(accessory_unit_bytes):
        raise ValueError("accessory unit: wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    out: List[Tuple[bytes, bytes]] = []
    wrapper_patched = False
    for c in parsed:
        if c.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not wrapper_patched:
            _lr, wrapper_payload = split_length_delimited_value_raw(c.value_raw)
            if not is_valid_message_payload(wrapper_payload):
                out.append((c.tag_raw, c.value_raw))
                continue

            wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=wrapper_payload, start_offset=0, end_offset=len(wrapper_payload)
            )
            if consumed2 != len(wrapper_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            wrapper_parsed = parse_chunks(wrapper_chunks_raw)

            new_wrapper_chunks: List[Tuple[bytes, bytes]] = []
            inner_patched = False
            for wc in wrapper_parsed:
                if wc.field_number == ACCESSORY_WRAPPER_FIELD_PAYLOAD and wc.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not inner_patched:
                    _lr2, payload_bytes = split_length_delimited_value_raw(wc.value_raw)
                    if is_valid_message_payload(payload_bytes) and payload_has_transform(payload_bytes):
                        new_payload = patch_accessory_payload(
                            payload_bytes,
                            new_pos=new_pos,
                            new_rot_deg=new_rot_deg,
                            new_scale=new_scale,
                            new_parent_unit_id=new_parent_unit_id,
                        )
                        new_wrapper_chunks.append((wc.tag_raw, build_length_delimited_value_raw(new_payload)))
                        inner_patched = True
                        continue
                new_wrapper_chunks.append((wc.tag_raw, wc.value_raw))

            if inner_patched:
                out.append((c.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_wrapper_chunks))))
                wrapper_patched = True
                continue

        out.append((c.tag_raw, c.value_raw))

    if not wrapper_patched:
        raise ValueError("accessory unit: 找不到可补丁的 wrapper（含 field_1 payload 的 message）")
    return encode_wire_chunks(out)


def extract_accessory_trs(
    accessory_unit_bytes: bytes,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """Extract accessory local TRS from an accessory GraphUnit."""
    payload_bytes = extract_accessory_payload_bytes(accessory_unit_bytes)
    transform_bytes = extract_accessory_transform_bytes(payload_bytes)
    return extract_trs_from_transform_message(transform_bytes)


def extract_accessory_pos(accessory_unit_bytes: bytes) -> Tuple[float, float, float]:
    """Extract accessory local position from an accessory GraphUnit."""
    pos, _rot, _scale = extract_accessory_trs(accessory_unit_bytes)
    return tuple(pos)

