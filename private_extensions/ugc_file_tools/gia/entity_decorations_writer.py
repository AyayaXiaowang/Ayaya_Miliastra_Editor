from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    ProtobufLikeParseOptions,
    decode_message_to_wire_chunks,
    decode_varint_with_raw,
    encode_tag,
    encode_varint,
    encode_wire_chunks,
    parse_message,
)


JsonDict = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class DecorationItem:
    name: str
    template_id: int
    pos: Tuple[float, float, float]
    scale: Tuple[float, float, float]
    # rotation is stored as a Vector3-like message inside transform (deg)
    yaw_deg: Optional[float]
    rot_deg: Optional[Tuple[float, float, float]]


@dataclass(frozen=True, slots=True)
class _Chunk:
    field_number: int
    wire_type: int
    tag_raw: bytes
    value_raw: bytes


_PROBE_OPTIONS = ProtobufLikeParseOptions(
    max_depth=3,
    bytes_preview_length=32,
    max_length_delimited_string_bytes=128,
    max_packed_items=256,
    max_message_bytes_for_probe=4096,
)


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _as_float3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field_name} 必须是长度为 3 的 list[float]，got: {value!r}")
    x, y, z = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
        raise ValueError(f"{field_name} 必须是 float/int，got: {value!r}")
    return float(x), float(y), float(z)


def load_decorations_report(report_json: Path) -> List[DecorationItem]:
    obj = _read_json(Path(report_json).resolve())
    if not isinstance(obj, dict):
        raise ValueError("decorations report 必须是 JSON object")
    items_raw = obj.get("decorations")
    if not isinstance(items_raw, list):
        raise ValueError("decorations report 缺少 decorations(list)")

    items: List[DecorationItem] = []
    for idx, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            raise ValueError(f"decorations[{idx}] 必须是 object，got: {raw!r}")

        name = str(raw.get("name") or "").strip()
        if name == "":
            raise ValueError(f"decorations[{idx}].name 不能为空")

        template_id = raw.get("template_id")
        if not isinstance(template_id, int):
            raise ValueError(f"decorations[{idx}].template_id 必须是 int，got: {template_id!r}")

        pos = _as_float3(raw.get("pos"), field_name=f"decorations[{idx}].pos")
        scale = _as_float3(raw.get("scale"), field_name=f"decorations[{idx}].scale")

        yaw_raw = raw.get("yaw_deg")
        yaw_deg = float(yaw_raw) if isinstance(yaw_raw, (int, float)) else None
        rot_raw = raw.get("rot_deg")
        rot_deg: Optional[Tuple[float, float, float]] = None
        if isinstance(rot_raw, list) and len(rot_raw) == 3 and all(isinstance(v, (int, float)) for v in rot_raw):
            rot_deg = (float(rot_raw[0]), float(rot_raw[1]), float(rot_raw[2]))
        elif isinstance(yaw_deg, (int, float)):
            rot_deg = (0.0, float(yaw_deg), 0.0)

        items.append(
            DecorationItem(
                name=name,
                template_id=int(template_id),
                pos=pos,
                scale=scale,
                yaw_deg=yaw_deg,
                rot_deg=rot_deg,
            )
        )
    return items


def _parse_chunks(chunks: List[Tuple[bytes, bytes]]) -> List[_Chunk]:
    out: List[_Chunk] = []
    for tag_raw, value_raw in chunks:
        tag_value, _next, _raw, ok = decode_varint_with_raw(tag_raw, 0, len(tag_raw))
        if not ok:
            raise ValueError("invalid tag_raw varint")
        wire_type = int(tag_value) & 0x07
        field_number = int(tag_value) >> 3
        if field_number <= 0:
            raise ValueError(f"invalid field_number: {field_number}")
        out.append(
            _Chunk(
                field_number=int(field_number),
                wire_type=int(wire_type),
                tag_raw=bytes(tag_raw),
                value_raw=bytes(value_raw),
            )
        )
    return out


def _split_length_delimited(value_raw: bytes) -> Tuple[bytes, bytes]:
    length_value, next_offset, length_raw, ok = decode_varint_with_raw(value_raw, 0, len(value_raw))
    if not ok:
        raise ValueError("invalid length-delimited: length varint")
    length_int = int(length_value)
    payload = bytes(value_raw[next_offset : next_offset + length_int])
    if len(payload) != length_int:
        raise ValueError("invalid length-delimited: payload truncated")
    return bytes(length_raw), payload


def _wrap_length_delimited(payload: bytes) -> bytes:
    p = bytes(payload or b"")
    return encode_varint(len(p)) + p


def _is_valid_message_payload(payload: bytes) -> bool:
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


def _decode_wire_chunks_checked(message_bytes: bytes) -> List[Tuple[bytes, bytes]]:
    if not _is_valid_message_payload(message_bytes):
        raise ValueError("payload 不是可完整解析的 protobuf-like message")
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes,
        start_offset=0,
        end_offset=len(message_bytes),
    )
    if consumed != len(message_bytes):
        raise ValueError("wire decode 未消费完整 message_bytes")
    return chunks_raw


def _encode_fixed32_float(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _build_vector3_message(x: float, y: float, z: float) -> bytes:
    chunks = [
        (encode_tag(1, 5), _encode_fixed32_float(float(x))),
        (encode_tag(2, 5), _encode_fixed32_float(float(y))),
        (encode_tag(3, 5), _encode_fixed32_float(float(z))),
    ]
    return encode_wire_chunks(chunks)


def _decode_vector3_message(payload: bytes) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    Vector3-like message:
    - field_1: x (fixed32 float)
    - field_2: y (fixed32 float)
    - field_3: z (fixed32 float)
    Missing fields are returned as None.
    """
    if not payload:
        return None, None, None
    parsed = _parse_chunks(_decode_wire_chunks_checked(payload))
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None
    for c in parsed:
        if c.wire_type != 5:
            continue
        if c.field_number == 1:
            x = struct.unpack("<f", c.value_raw[:4])[0]
        elif c.field_number == 2:
            y = struct.unpack("<f", c.value_raw[:4])[0]
        elif c.field_number == 3:
            z = struct.unpack("<f", c.value_raw[:4])[0]
    return x, y, z


def _build_rotation_message(*, x: Optional[float], y: Optional[float], z: Optional[float]) -> bytes:
    chunks: List[Tuple[bytes, bytes]] = []
    if isinstance(x, (int, float)):
        chunks.append((encode_tag(1, 5), _encode_fixed32_float(float(x))))
    if isinstance(y, (int, float)):
        chunks.append((encode_tag(2, 5), _encode_fixed32_float(float(y))))
    if isinstance(z, (int, float)):
        chunks.append((encode_tag(3, 5), _encode_fixed32_float(float(z))))
    return encode_wire_chunks(chunks)


def _pack_varints(values: Sequence[int]) -> bytes:
    out: List[bytes] = []
    for v in values:
        out.append(encode_varint(int(v)))
    return b"".join(out)


def _patch_first_varint_field(message_bytes: bytes, *, field_number: int, new_value: int) -> bytes:
    parsed = _parse_chunks(_decode_wire_chunks_checked(message_bytes))
    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == int(field_number) and c.wire_type == 0 and not replaced:
            out.append((c.tag_raw, encode_varint(int(new_value))))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(int(field_number), 0), encode_varint(int(new_value))))
    return encode_wire_chunks(out)


def _patch_first_string_field(message_bytes: bytes, *, field_number: int, new_text: str) -> bytes:
    parsed = _parse_chunks(_decode_wire_chunks_checked(message_bytes))
    encoded = str(new_text).encode("utf-8")
    new_value_raw = _wrap_length_delimited(encoded)
    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == int(field_number) and c.wire_type == 2 and not replaced:
            out.append((c.tag_raw, new_value_raw))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))
    if not replaced:
        out.append((encode_tag(int(field_number), 2), new_value_raw))
    return encode_wire_chunks(out)


def _patch_parent_entity_name(parent_unit_bytes: bytes, *, new_name: str) -> bytes:
    """
    对齐真源样本的“实体命名”：
    - GraphUnit.name(field_3) 直接改名
    - parent 图内部也有一处“名字记录”（常见为 entry.key=1 / entry.field_11 为 {field_1: <name>}），同步改名
    """
    name_text = str(new_name or "").strip()
    if name_text == "":
        raise ValueError("entity_name 不能为空")

    patched_parent = _patch_first_string_field(parent_unit_bytes, field_number=3, new_text=name_text)

    def patch_message(message_bytes: bytes) -> Tuple[bytes, bool]:
        parsed = _parse_chunks(_decode_wire_chunks_checked(message_bytes))
        out: List[Tuple[bytes, bytes]] = []
        patched_here = False

        for c in parsed:
            if c.field_number == 5 and c.wire_type == 2 and not patched_here:
                _lr, entry_payload = _split_length_delimited(c.value_raw)
                if not _is_valid_message_payload(entry_payload):
                    out.append((c.tag_raw, c.value_raw))
                    continue
                entry_parsed = _parse_chunks(_decode_wire_chunks_checked(entry_payload))

                entry_key = None
                for ec in entry_parsed:
                    if ec.field_number == 1 and ec.wire_type == 0:
                        v, _n, _raw, ok = decode_varint_with_raw(ec.value_raw, 0, len(ec.value_raw))
                        if ok:
                            entry_key = int(v)
                        break
                if entry_key != 1:
                    out.append((c.tag_raw, c.value_raw))
                    continue

                new_entry_chunks: List[Tuple[bytes, bytes]] = []
                entry_patched = False
                for ec in entry_parsed:
                    if ec.field_number == 11 and ec.wire_type == 2 and not entry_patched:
                        _lrr, name_payload = _split_length_delimited(ec.value_raw)
                        if not _is_valid_message_payload(name_payload):
                            # fallback:直接写一个 {field_1: name_text} message
                            name_msg = encode_wire_chunks(
                                [(encode_tag(1, 2), _wrap_length_delimited(name_text.encode("utf-8")))]
                            )
                            new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(name_msg)))
                            entry_patched = True
                            continue
                        new_name_payload = _patch_first_string_field(name_payload, field_number=1, new_text=name_text)
                        new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(new_name_payload)))
                        entry_patched = True
                    else:
                        new_entry_chunks.append((ec.tag_raw, ec.value_raw))

                if entry_patched:
                    out.append((c.tag_raw, _wrap_length_delimited(encode_wire_chunks(new_entry_chunks))))
                    patched_here = True
                    continue

            if c.wire_type == 2 and not patched_here:
                _lr, payload = _split_length_delimited(c.value_raw)
                if _is_valid_message_payload(payload):
                    new_payload, patched = patch_message(payload)
                    if patched:
                        out.append((c.tag_raw, _wrap_length_delimited(new_payload)))
                        patched_here = True
                        continue

            out.append((c.tag_raw, c.value_raw))

        return encode_wire_chunks(out), patched_here

    new_parent_bytes, patched = patch_message(patched_parent)
    if not patched:
        # name record 缺失时允许只改 GraphUnit.name（有些样本可能不包含该 entry）
        return patched_parent
    return new_parent_bytes


def _patch_transform_message(
    transform_bytes: bytes,
    *,
    pos: Tuple[float, float, float],
    yaw_deg: Optional[float],
    rot_deg: Optional[Tuple[float, float, float]],
    scale: Tuple[float, float, float],
) -> bytes:
    parsed = _parse_chunks(_decode_wire_chunks_checked(transform_bytes))

    pos_payload = _build_vector3_message(pos[0], pos[1], pos[2])
    scale_payload = _build_vector3_message(scale[0], scale[1], scale[2])

    def _replace_or_append_ld(field_no: int, payload: bytes) -> None:
        nonlocal parsed
        for i, c in enumerate(parsed):
            if c.field_number == field_no and c.wire_type == 2:
                parsed[i] = _Chunk(
                    field_number=c.field_number,
                    wire_type=c.wire_type,
                    tag_raw=c.tag_raw,
                    value_raw=_wrap_length_delimited(payload),
                )
                return
        parsed.append(
            _Chunk(
                field_number=field_no,
                wire_type=2,
                tag_raw=encode_tag(field_no, 2),
                value_raw=_wrap_length_delimited(payload),
            )
        )

    _replace_or_append_ld(1, pos_payload)
    # field_2 is a Vector3-like rotation message (deg).
    # Merge rotation components to avoid wiping template's pre-rotated x/z (e.g. circles use x=-90).
    want_rot = rot_deg
    if want_rot is None and isinstance(yaw_deg, (int, float)):
        want_rot = (None, float(yaw_deg), None)  # type: ignore[assignment]
    if want_rot is not None:
        existing_payload: Optional[bytes] = None
        for c in parsed:
            if c.field_number == 2 and c.wire_type == 2:
                _lr0, existing_payload = _split_length_delimited(c.value_raw)
                break
        ex, ey, ez = _decode_vector3_message(existing_payload or b"")
        wx, wy, wz = want_rot
        nx = float(wx) if isinstance(wx, (int, float)) else ex
        ny = float(wy) if isinstance(wy, (int, float)) else ey
        nz = float(wz) if isinstance(wz, (int, float)) else ez
        rot_payload = _build_rotation_message(x=nx, y=ny, z=nz)
        _replace_or_append_ld(2, rot_payload)
    _replace_or_append_ld(3, scale_payload)
    return encode_wire_chunks([(c.tag_raw, c.value_raw) for c in parsed])


def _patch_accessory_payload(
    payload_bytes: bytes,
    *,
    unit_id: int,
    unit_name: str,
    template_id: int,
    parent_unit_id: int,
    pos: Tuple[float, float, float],
    yaw_deg: Optional[float],
    rot_deg: Optional[Tuple[float, float, float]],
    scale: Tuple[float, float, float],
) -> bytes:
    # payload fields (observed in truth samples):
    # - 1: unit_id (varint)
    # - 2: template_id (varint)
    # - 4: repeated entries, one of which binds to parent id (entry.field_1 == 40; entry.field_50.message.field_502 = parent_id)
    # - 5: repeated entries, one of which contains field 11 (transform message)
    patched = _patch_first_varint_field(payload_bytes, field_number=1, new_value=int(unit_id))
    patched = _patch_first_varint_field(patched, field_number=2, new_value=int(template_id))

    parsed = _parse_chunks(_decode_wire_chunks_checked(patched))
    out_payload: List[Tuple[bytes, bytes]] = []
    transform_patched = False
    parent_bind_patched = False

    for c in parsed:
        if c.field_number == 5 and c.wire_type == 2 and not transform_patched:
            _lr, entry_payload = _split_length_delimited(c.value_raw)
            if not _is_valid_message_payload(entry_payload):
                out_payload.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = _parse_chunks(_decode_wire_chunks_checked(entry_payload))
            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == 11 and ec.wire_type == 2 and not patched_entry:
                    _lrr, transform_payload = _split_length_delimited(ec.value_raw)
                    if not _is_valid_message_payload(transform_payload):
                        new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                        continue
                    new_transform = _patch_transform_message(
                        transform_payload, pos=pos, yaw_deg=yaw_deg, rot_deg=rot_deg, scale=scale
                    )
                    new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(new_transform)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))
            if patched_entry:
                out_payload.append((c.tag_raw, _wrap_length_delimited(encode_wire_chunks(new_entry_chunks))))
                transform_patched = True
            else:
                out_payload.append((c.tag_raw, c.value_raw))
            continue

        if c.field_number == 4 and c.wire_type == 2 and not parent_bind_patched:
            _lr, entry_payload = _split_length_delimited(c.value_raw)
            if not _is_valid_message_payload(entry_payload):
                out_payload.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = _parse_chunks(_decode_wire_chunks_checked(entry_payload))

            entry_key = None
            for ec in entry_parsed:
                if ec.field_number == 1 and ec.wire_type == 0:
                    v, _n, _raw, ok = decode_varint_with_raw(ec.value_raw, 0, len(ec.value_raw))
                    if ok:
                        entry_key = int(v)
                    break
            if entry_key != 40:
                out_payload.append((c.tag_raw, c.value_raw))
                continue

            new_entry_chunks = []
            patched_entry = False
            for ec in entry_parsed:
                if ec.field_number == 50 and ec.wire_type == 2 and not patched_entry:
                    _lrr, nested_payload = _split_length_delimited(ec.value_raw)
                    if not _is_valid_message_payload(nested_payload):
                        new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                        continue
                    patched_nested = _patch_first_varint_field(nested_payload, field_number=502, new_value=int(parent_unit_id))
                    new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(patched_nested)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))
            if patched_entry:
                out_payload.append((c.tag_raw, _wrap_length_delimited(encode_wire_chunks(new_entry_chunks))))
                parent_bind_patched = True
            else:
                out_payload.append((c.tag_raw, c.value_raw))
            continue

        out_payload.append((c.tag_raw, c.value_raw))

    if not transform_patched:
        raise ValueError("accessory payload: 找不到可补丁的 transform（field_5[*].field_11）")
    if not parent_bind_patched:
        raise ValueError("accessory payload: 找不到可补丁的 parent bind（field_4 entry key=40 / field_50.field_502）")

    return encode_wire_chunks(out_payload)


def _patch_accessory_unit(
    unit_bytes: bytes,
    *,
    unit_id: int,
    unit_name: str,
    template_id: int,
    parent_unit_id: int,
    pos: Tuple[float, float, float],
    yaw_deg: Optional[float],
    rot_deg: Optional[Tuple[float, float, float]],
    scale: Tuple[float, float, float],
) -> bytes:
    # Accessory GraphUnit:
    # - field 1: Id message -> patch field 4
    # - field 3: name string
    # - wrapper field (unknown numeric in truth variants) -> message with field 1 containing payload message
    parsed = _parse_chunks(_decode_wire_chunks_checked(unit_bytes))
    out: List[Tuple[bytes, bytes]] = []
    id_patched = False
    name_patched = False
    wrapper_patched = False

    for c in parsed:
        if c.field_number == 1 and c.wire_type == 2 and not id_patched:
            _lr, id_payload = _split_length_delimited(c.value_raw)
            if not _is_valid_message_payload(id_payload):
                raise ValueError("accessory unit: id payload 不是 message")
            new_id_payload = _patch_first_varint_field(id_payload, field_number=4, new_value=int(unit_id))
            out.append((c.tag_raw, _wrap_length_delimited(new_id_payload)))
            id_patched = True
            continue

        if c.field_number == 3 and c.wire_type == 2 and not name_patched:
            out.append((c.tag_raw, _wrap_length_delimited(str(unit_name).encode("utf-8"))))
            name_patched = True
            continue

        if c.wire_type == 2 and not wrapper_patched:
            _lr, wrapper_payload = _split_length_delimited(c.value_raw)
            if not _is_valid_message_payload(wrapper_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            wrapper_parsed = _parse_chunks(_decode_wire_chunks_checked(wrapper_payload))

            # wrapper must contain field 1 as length-delimited payload message
            has_field1 = False
            for wc in wrapper_parsed:
                if wc.field_number == 1 and wc.wire_type == 2:
                    has_field1 = True
                    break
            if not has_field1:
                out.append((c.tag_raw, c.value_raw))
                continue

            new_wrapper_chunks: List[Tuple[bytes, bytes]] = []
            inner_patched = False
            for wc in wrapper_parsed:
                if wc.field_number == 1 and wc.wire_type == 2 and not inner_patched:
                    _lrr, payload_bytes = _split_length_delimited(wc.value_raw)
                    if not _is_valid_message_payload(payload_bytes):
                        raise ValueError("accessory wrapper: payload(field_1) 不是 message")
                    new_payload = _patch_accessory_payload(
                        payload_bytes,
                        unit_id=int(unit_id),
                        unit_name=str(unit_name),
                        template_id=int(template_id),
                        parent_unit_id=int(parent_unit_id),
                        pos=pos,
                        yaw_deg=yaw_deg,
                        rot_deg=rot_deg,
                        scale=scale,
                    )
                    new_wrapper_chunks.append((wc.tag_raw, _wrap_length_delimited(new_payload)))
                    inner_patched = True
                else:
                    new_wrapper_chunks.append((wc.tag_raw, wc.value_raw))
            if not inner_patched:
                raise ValueError("accessory wrapper: 缺少 payload(field_1)")
            out.append((c.tag_raw, _wrap_length_delimited(encode_wire_chunks(new_wrapper_chunks))))
            wrapper_patched = True
            continue

        out.append((c.tag_raw, c.value_raw))

    if not id_patched:
        raise ValueError("accessory unit: 缺少 id(field_1)")
    if not name_patched:
        raise ValueError("accessory unit: 缺少 name(field_3)")
    if not wrapper_patched:
        raise ValueError("accessory unit: 找不到可补丁的 wrapper（含 field_1 payload 的 message）")

    return encode_wire_chunks(out)


def _patch_parent_related_ids(parent_unit_bytes: bytes, *, related_id_template: _Chunk, unit_ids: Sequence[int]) -> bytes:
    parent_parsed = _parse_chunks(_decode_wire_chunks_checked(parent_unit_bytes))

    # insertion point:
    # - if parent already has relatedIds, keep their original position
    # - else insert right after Id(field_1) for maximum compatibility with non-standard parsers
    insert_at = None
    for idx, c in enumerate(parent_parsed):
        if c.field_number == 2 and c.wire_type == 2:
            insert_at = idx
            break
    if insert_at is None:
        insert_at = 0
        for idx, c in enumerate(parent_parsed):
            if c.field_number == 1 and c.wire_type == 2:
                insert_at = idx + 1
                break

    kept: List[Tuple[bytes, bytes]] = []
    current_out_index = 0
    for idx, c in enumerate(parent_parsed):
        if idx == int(insert_at):
            # placeholder: insert later after we compute template payload
            current_out_index = len(kept)
        if c.field_number == 2 and c.wire_type == 2:
            continue
        kept.append((c.tag_raw, c.value_raw))

    _lr, related_template_payload = _split_length_delimited(related_id_template.value_raw)
    if not _is_valid_message_payload(related_template_payload):
        raise ValueError("relatedIds template payload 不是 message")

    new_related_chunks: List[Tuple[bytes, bytes]] = []
    for uid in unit_ids:
        new_related_payload = _patch_first_varint_field(related_template_payload, field_number=4, new_value=int(uid))
        new_related_chunks.append((related_id_template.tag_raw, _wrap_length_delimited(new_related_payload)))

    # splice into kept at remembered position (defaults to after field_1)
    kept = kept[:current_out_index] + new_related_chunks + kept[current_out_index:]

    return encode_wire_chunks(kept)


def _patch_packed_ids_inside_parent_graph(parent_unit_bytes: bytes, *, packed_ids: bytes) -> bytes:
    """
    真源样本中，parent Graph 内部存在一处 packed varint 列表用于列出 accessories unit_id。
    它位于某个嵌套 message 的 repeated entry 中：
    - entry.field_1 == 40
    - entry.field_50.message.field_501 == <packed varint bytes>
    我们不假设 wrapper 的字段号，只做结构匹配并递归定位。
    """

    def patch_message(message_bytes: bytes) -> Tuple[bytes, bool]:
        """
        在任意层级里寻找 entry(message)：
        - entry.field_1(varint) == 40
        - entry.field_50(bytes|message) 中包含 packed id 列表（常见为 field_501(bytes)）

        注意：真源样本中承载 entry 的 repeated 字段号不稳定（常见为 field_5 或 field_6），
        因此这里不能写死外层 field_number，只能对所有 length-delimited message 做“像 entry 吗”的结构探测。
        """

        def try_patch_entry(entry_payload: bytes) -> Tuple[bytes, bool]:
            entry_parsed = _parse_chunks(_decode_wire_chunks_checked(entry_payload))
            entry_key: Optional[int] = None
            for ec in entry_parsed:
                if ec.field_number == 1 and ec.wire_type == 0:
                    v, _n, _raw, ok = decode_varint_with_raw(ec.value_raw, 0, len(ec.value_raw))
                    if ok:
                        entry_key = int(v)
                    break
            if entry_key != 40:
                return entry_payload, False

            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            entry_patched = False
            for ec in entry_parsed:
                if ec.field_number == 50 and ec.wire_type == 2 and not entry_patched:
                    _lrr, nested_payload = _split_length_delimited(ec.value_raw)
                    # Truth samples have two shapes:
                    # - empty/older: entry.field_50 is bytes (packed varint stream, possibly empty)
                    # - newer: entry.field_50 is a message containing field_501(bytes)
                    if not _is_valid_message_payload(nested_payload):
                        new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(bytes(packed_ids))))
                        entry_patched = True
                        continue

                    nested_parsed = _parse_chunks(_decode_wire_chunks_checked(nested_payload))
                    new_nested_chunks: List[Tuple[bytes, bytes]] = []
                    bytes_patched = False
                    for nc in nested_parsed:
                        if nc.field_number == 501 and nc.wire_type == 2 and not bytes_patched:
                            new_nested_chunks.append((nc.tag_raw, _wrap_length_delimited(bytes(packed_ids))))
                            bytes_patched = True
                        else:
                            new_nested_chunks.append((nc.tag_raw, nc.value_raw))
                    if bytes_patched:
                        new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(encode_wire_chunks(new_nested_chunks))))
                        entry_patched = True
                        continue

                    # nested is a message but doesn't contain field_501 in this sample; fall back to raw bytes.
                    new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(bytes(packed_ids))))
                    entry_patched = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if not entry_patched:
                return entry_payload, False
            return encode_wire_chunks(new_entry_chunks), True

        parsed = _parse_chunks(_decode_wire_chunks_checked(message_bytes))
        out: List[Tuple[bytes, bytes]] = []
        patched_any = False

        for c in parsed:
            if c.wire_type == 2:
                _lr, payload = _split_length_delimited(c.value_raw)
                if _is_valid_message_payload(payload):
                    # 1) current payload itself is an entry?
                    new_payload, patched_entry = try_patch_entry(payload)
                    if patched_entry:
                        out.append((c.tag_raw, _wrap_length_delimited(new_payload)))
                        patched_any = True
                        continue

                    # 2) otherwise, search deeper
                    new_payload2, patched_nested = patch_message(payload)
                    if patched_nested:
                        out.append((c.tag_raw, _wrap_length_delimited(new_payload2)))
                        patched_any = True
                        continue

            out.append((c.tag_raw, c.value_raw))

        return encode_wire_chunks(out), patched_any

    new_parent_bytes, patched = patch_message(parent_unit_bytes)
    if not patched:
        # 兼容：部分真源样本的 parent graph 不包含“packed accessories id 列表”字段。
        # 这些样本仍可通过 Root.field_2 的 GraphUnit 列表识别装饰物单元；
        # 此时跳过 packed list 补丁，避免导出链路因“模板差异”直接失败。
        return parent_unit_bytes
    return new_parent_bytes


def _extract_graph_unit_id(graph_unit_bytes: bytes) -> int:
    parsed = _parse_chunks(_decode_wire_chunks_checked(graph_unit_bytes))
    for c in parsed:
        if c.field_number == 1 and c.wire_type == 2:
            _lr, id_payload = _split_length_delimited(c.value_raw)
            if not _is_valid_message_payload(id_payload):
                continue
            id_parsed = _parse_chunks(_decode_wire_chunks_checked(id_payload))
            for ic in id_parsed:
                if ic.field_number == 4 and ic.wire_type == 0:
                    v, _n, _raw, ok = decode_varint_with_raw(ic.value_raw, 0, len(ic.value_raw))
                    if ok:
                        return int(v)
    raise ValueError("GraphUnit: 无法提取 id(field_1.field_4)")


def _derive_file_path_from_base(*, base_file_path: str, output_file_name: str) -> str:
    base = str(base_file_path or "").strip()
    out_name = str(output_file_name or "").strip()
    if out_name == "":
        return base
    if base == "":
        return out_name
    marker = "\\"
    last = base.rfind(marker)
    if last < 0:
        return base + marker + out_name
    return base[: last + 1] + out_name


def build_entity_gia_with_decorations_wire(
    *,
    entity_base_gia: Path,
    accessory_template_gia: Optional[Path],
    decorations_report_json: Path,
    output_gia_path: Path,
    check_header: bool,
    limit_count: int,
    entity_name: str = "",
) -> Dict[str, Any]:
    entity_base_gia = Path(entity_base_gia).resolve()
    if check_header:
        validate_gia_container_file(entity_base_gia)
    entity_proto = unwrap_gia_container(entity_base_gia, check_header=False)

    template_proto: Optional[bytes] = None
    if accessory_template_gia is not None:
        accessory_template_gia = Path(accessory_template_gia).resolve()
        if check_header:
            validate_gia_container_file(accessory_template_gia)
        template_proto = unwrap_gia_container(accessory_template_gia, check_header=False)

    decorations_all = load_decorations_report(Path(decorations_report_json))
    decorations = decorations_all[: int(limit_count)] if int(limit_count) > 0 else decorations_all
    if not decorations:
        raise ValueError("decorations 为空")

    # decode Root of entity base
    root_chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=entity_proto,
        start_offset=0,
        end_offset=len(entity_proto),
    )
    if consumed != len(entity_proto):
        raise ValueError("entity base: root wire decode not fully consumed")
    root_parsed = _parse_chunks(root_chunks_raw)

    parent_chunk: Optional[_Chunk] = None
    file_path_text = ""
    accessories_chunks: List[_Chunk] = []
    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2 and parent_chunk is None:
            parent_chunk = c
        if c.field_number == 2 and c.wire_type == 2:
            accessories_chunks.append(c)
        if c.field_number == 3 and c.wire_type == 2:
            _lr, payload = _split_length_delimited(c.value_raw)
            file_path_text = payload.decode("utf-8", errors="replace")

    if parent_chunk is None:
        raise ValueError("entity base: missing Root.field_1 (parent GraphUnit)")
    _lr, parent_bytes = _split_length_delimited(parent_chunk.value_raw)

    entity_name_text = str(entity_name or "").strip()
    if entity_name_text != "":
        parent_bytes = _patch_parent_entity_name(parent_bytes, new_name=entity_name_text)

    # Pick templates:
    # - relatedId template (parent.field_2 first occurrence) from entity base, else from accessory_template_gia
    # - accessory unit template (Root.field_2 first occurrence) from entity base, else from accessory_template_gia
    related_id_template_chunk: Optional[_Chunk] = None
    accessory_unit_template_bytes: Optional[bytes] = None

    parent_parsed = _parse_chunks(_decode_wire_chunks_checked(parent_bytes))
    for pc in parent_parsed:
        if pc.field_number == 2 and pc.wire_type == 2:
            related_id_template_chunk = pc
            break
    if accessories_chunks:
        _lr2, accessory_unit_template_bytes = _split_length_delimited(accessories_chunks[0].value_raw)

    if (related_id_template_chunk is None or accessory_unit_template_bytes is None) and template_proto is None:
        raise ValueError("entity base 缺少装饰物模板（relatedIds/accessories），且未提供 accessory_template_gia")

    if template_proto is not None and (related_id_template_chunk is None or accessory_unit_template_bytes is None):
        template_root_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=template_proto,
            start_offset=0,
            end_offset=len(template_proto),
        )
        if consumed2 != len(template_proto):
            raise ValueError("template: root wire decode not fully consumed")
        template_root_parsed = _parse_chunks(template_root_chunks_raw)

        template_parent_chunk: Optional[_Chunk] = None
        template_accessory_chunk: Optional[_Chunk] = None
        for tc in template_root_parsed:
            if tc.field_number == 1 and tc.wire_type == 2 and template_parent_chunk is None:
                template_parent_chunk = tc
            if tc.field_number == 2 and tc.wire_type == 2 and template_accessory_chunk is None:
                template_accessory_chunk = tc
        if template_parent_chunk is None:
            raise ValueError("template: missing Root.field_1 (parent GraphUnit)")
        _ltt, template_parent_bytes = _split_length_delimited(template_parent_chunk.value_raw)
        template_parent_parsed = _parse_chunks(_decode_wire_chunks_checked(template_parent_bytes))
        if related_id_template_chunk is None:
            for tpc in template_parent_parsed:
                if tpc.field_number == 2 and tpc.wire_type == 2:
                    related_id_template_chunk = tpc
                    break
        if accessory_unit_template_bytes is None:
            if template_accessory_chunk is None:
                raise ValueError("template: missing Root.field_2 (accessory GraphUnit template)")
            _lta, accessory_unit_template_bytes = _split_length_delimited(template_accessory_chunk.value_raw)

        # 关键：当 entity_base 本身“不具备装饰物可识别 parent”时，直接用 template 的 parent 替换。
        # 经验：纯空实体（如空模型.gia）的 parent_unit_id 在真源侧可能不被当作“装饰物容器”，会导致文件直接不可检测。
        base_has_related = related_id_template_chunk is not None
        base_has_accessories = len(accessories_chunks) > 0
        if not (base_has_related and base_has_accessories):
            parent_bytes = bytes(template_parent_bytes)
            if entity_name_text != "":
                parent_bytes = _patch_parent_entity_name(parent_bytes, new_name=entity_name_text)
            # 重新解析 parent，确保后续 related_id_template_chunk 来源正确
            parent_parsed = _parse_chunks(_decode_wire_chunks_checked(parent_bytes))
            related_id_template_chunk = None
            for pc in parent_parsed:
                if pc.field_number == 2 and pc.wire_type == 2:
                    related_id_template_chunk = pc
                    break

    if related_id_template_chunk is None:
        raise ValueError("missing relatedIds template")
    if accessory_unit_template_bytes is None:
        raise ValueError("missing accessory unit template bytes")

    parent_unit_id = _extract_graph_unit_id(parent_bytes)

    # Determine unit_id_start:
    # Prefer template relatedIds template payload's field_4 as base start; then allocate sequentially.
    _lr3, related_template_payload = _split_length_delimited(related_id_template_chunk.value_raw)
    if not _is_valid_message_payload(related_template_payload):
        raise ValueError("relatedIds template payload 不是 message")
    rid_parsed = _parse_chunks(_decode_wire_chunks_checked(related_template_payload))
    unit_id_start: Optional[int] = None
    for rc in rid_parsed:
        if rc.field_number == 4 and rc.wire_type == 0:
            v, _n, _raw, ok = decode_varint_with_raw(rc.value_raw, 0, len(rc.value_raw))
            if ok:
                unit_id_start = int(v)
            break
    if unit_id_start is None:
        raise ValueError("无法从 relatedIds template 提取 unit_id_start（field_4）")

    unit_ids = [unit_id_start + i for i in range(len(decorations))]
    packed_ids = _pack_varints(unit_ids)

    # Patch parent: relatedIds + packed list
    new_parent_bytes = _patch_parent_related_ids(parent_bytes, related_id_template=related_id_template_chunk, unit_ids=unit_ids)
    new_parent_bytes = _patch_packed_ids_inside_parent_graph(new_parent_bytes, packed_ids=packed_ids)

    # Build accessories
    new_accessory_units: List[bytes] = []
    for uid, dec in zip(unit_ids, decorations, strict=True):
        new_accessory_units.append(
            _patch_accessory_unit(
                accessory_unit_template_bytes,
                unit_id=int(uid),
                unit_name=str(dec.name),
                template_id=int(dec.template_id),
                parent_unit_id=int(parent_unit_id),
                pos=dec.pos,
                yaw_deg=dec.yaw_deg,
                rot_deg=dec.rot_deg,
                scale=dec.scale,
            )
        )

    # Build new root
    output_name = Path(str(output_gia_path)).name
    new_file_path = _derive_file_path_from_base(base_file_path=file_path_text, output_file_name=output_name)
    new_file_path_value_raw = _wrap_length_delimited(new_file_path.encode("utf-8"))

    out_root_chunks: List[Tuple[bytes, bytes]] = []
    parent_written = False
    accessories_written = False
    file_path_written = False
    accessories_inserted_for_missing = False

    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2 and not parent_written:
            out_root_chunks.append((c.tag_raw, _wrap_length_delimited(new_parent_bytes)))
            parent_written = True
            continue

        if c.field_number == 2 and c.wire_type == 2:
            if not accessories_written:
                for unit in new_accessory_units:
                    out_root_chunks.append((c.tag_raw, _wrap_length_delimited(unit)))
                accessories_written = True
            continue

        # base has no accessories: insert before filePath(field_3) for maximum compatibility
        if c.field_number == 3 and c.wire_type == 2 and not accessories_written and not accessories_inserted_for_missing:
            for unit in new_accessory_units:
                out_root_chunks.append((encode_tag(2, 2), _wrap_length_delimited(unit)))
            accessories_written = True
            accessories_inserted_for_missing = True

        if c.field_number == 3 and c.wire_type == 2 and not file_path_written:
            out_root_chunks.append((c.tag_raw, new_file_path_value_raw))
            file_path_written = True
            continue

        out_root_chunks.append((c.tag_raw, c.value_raw))

    if not accessories_written:
        for unit in new_accessory_units:
            out_root_chunks.append((encode_tag(2, 2), _wrap_length_delimited(unit)))
    if not file_path_written:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    out_bytes = wrap_gia_container(out_proto)
    output_gia_path = Path(output_gia_path).resolve()
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "entity_base_gia": str(entity_base_gia),
        "accessory_template_gia": str(accessory_template_gia) if accessory_template_gia is not None else "",
        "output_gia_file": str(output_gia_path),
        "decorations_count": len(decorations),
        "unit_id_start": int(unit_id_start),
        "parent_unit_id": int(parent_unit_id),
        "file_path": new_file_path,
        "proto_size": len(out_proto),
    }


