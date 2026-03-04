from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_wire_chunks,
    decode_varint_with_raw,
    encode_tag,
    encode_varint,
    encode_wire_chunks,
)


JsonDict = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class DecorationItem:
    name: str
    template_id: int
    pos: Tuple[float, float, float]
    scale: Tuple[float, float, float]
    yaw_deg: Optional[float]


def _read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _as_float3(value: Any, *, field_name: str) -> Tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{field_name} 必须是长度为 3 的 list[float]，got: {value!r}")
    x, y, z = value
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not isinstance(z, (int, float)):
        raise ValueError(f"{field_name} 必须是 float/int，got: {value!r}")
    return float(x), float(y), float(z)


def load_decorations_report(report_json: Path) -> Tuple[Optional[str], List[DecorationItem]]:
    obj = _read_json(Path(report_json).resolve())
    if not isinstance(obj, dict):
        raise ValueError("decorations report 必须是 JSON object")

    parent_name: Optional[str] = None
    parent_struct = obj.get("parent_struct")
    if isinstance(parent_struct, dict):
        pn = parent_struct.get("name")
        if isinstance(pn, str) and pn.strip() != "":
            parent_name = pn.strip()

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

        items.append(
            DecorationItem(
                name=name,
                template_id=int(template_id),
                pos=pos,
                scale=scale,
                yaw_deg=yaw_deg,
            )
        )

    return parent_name, items


@dataclass(frozen=True, slots=True)
class _Chunk:
    field_number: int
    wire_type: int
    tag_raw: bytes
    value_raw: bytes


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
        out.append(_Chunk(field_number=int(field_number), wire_type=int(wire_type), tag_raw=bytes(tag_raw), value_raw=bytes(value_raw)))
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


def _encode_fixed32_float(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _build_vector3_message(x: float, y: float, z: float) -> bytes:
    chunks = [
        (encode_tag(1, 5), _encode_fixed32_float(float(x))),
        (encode_tag(2, 5), _encode_fixed32_float(float(y))),
        (encode_tag(3, 5), _encode_fixed32_float(float(z))),
    ]
    return encode_wire_chunks(chunks)


def _build_yaw_message(yaw_deg: float) -> bytes:
    chunks = [
        (encode_tag(2, 5), _encode_fixed32_float(float(yaw_deg))),
    ]
    return encode_wire_chunks(chunks)


def _patch_first_varint_field(message_bytes: bytes, *, field_number: int, new_value: int) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (varint patch)")
    parsed = _parse_chunks(chunks_raw)

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
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (string patch)")
    parsed = _parse_chunks(chunks_raw)

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


def _patch_first_length_delimited_message_field(message_bytes: bytes, *, field_number: int, patcher) -> bytes:
    """
    对 field_number 的第一个 length-delimited 字段做 “payload(message)” 级补丁。
    patcher: (payload_bytes)->payload_bytes
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
    if consumed != len(message_bytes):
        raise ValueError("wire decode not fully consumed (nested patch)")
    parsed = _parse_chunks(chunks_raw)

    replaced = False
    out: List[Tuple[bytes, bytes]] = []
    for c in parsed:
        if c.field_number == int(field_number) and c.wire_type == 2 and not replaced:
            _len_raw, payload = _split_length_delimited(c.value_raw)
            new_payload = patcher(payload)
            out.append((c.tag_raw, _wrap_length_delimited(new_payload)))
            replaced = True
        else:
            out.append((c.tag_raw, c.value_raw))

    if not replaced:
        raise ValueError(f"missing nested message field_{int(field_number)} for patch")
    return encode_wire_chunks(out)


def _patch_transform_message(
    transform_bytes: bytes, *, pos: Tuple[float, float, float], yaw_deg: Optional[float], scale: Tuple[float, float, float]
) -> bytes:
    # transform message fields:
    # 1: position (length-delimited; may be empty bytes or nested message)
    # 2: yaw wrapper (length-delimited; may be empty)
    # 3: scale (length-delimited; nested message with fixed32 floats)
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("wire decode not fully consumed (transform)")
    parsed = _parse_chunks(chunks_raw)

    pos_payload = _build_vector3_message(pos[0], pos[1], pos[2])
    yaw_payload = _build_yaw_message(float(yaw_deg)) if isinstance(yaw_deg, (int, float)) else b""
    scale_payload = _build_vector3_message(scale[0], scale[1], scale[2])

    def _replace_or_append_ld(field_no: int, payload: bytes) -> None:
        nonlocal parsed
        for i, c in enumerate(parsed):
            if c.field_number == field_no and c.wire_type == 2:
                parsed[i] = _Chunk(field_number=c.field_number, wire_type=c.wire_type, tag_raw=c.tag_raw, value_raw=_wrap_length_delimited(payload))
                return
        parsed.append(_Chunk(field_number=field_no, wire_type=2, tag_raw=encode_tag(field_no, 2), value_raw=_wrap_length_delimited(payload)))

    _replace_or_append_ld(1, pos_payload)
    _replace_or_append_ld(2, yaw_payload)
    _replace_or_append_ld(3, scale_payload)

    return encode_wire_chunks([(c.tag_raw, c.value_raw) for c in parsed])


def _patch_accessory_payload(
    payload_bytes: bytes,
    *,
    unit_id: int,
    unit_name: str,
    template_id: int,
    pos: Tuple[float, float, float],
    yaw_deg: Optional[float],
    scale: Tuple[float, float, float],
) -> bytes:
    # payload fields:
    # 1: unit_id (varint)
    # 2: template_id (varint)
    # 5: repeated entries, one of which contains field 11 (transform message)
    patched = _patch_first_varint_field(payload_bytes, field_number=1, new_value=int(unit_id))
    patched = _patch_first_varint_field(patched, field_number=2, new_value=int(template_id))

    def patch_field5(payload_in: bytes) -> bytes:
        chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_in, start_offset=0, end_offset=len(payload_in))
        if consumed != len(payload_in):
            raise ValueError("wire decode not fully consumed (payload)")
        parsed = _parse_chunks(chunks_raw)

        out: List[Tuple[bytes, bytes]] = []
        for c in parsed:
            if c.field_number != 5 or c.wire_type != 2:
                out.append((c.tag_raw, c.value_raw))
                continue

            _len_raw, entry_payload = _split_length_delimited(c.value_raw)
            # entry is a message; we need to find field 11 inside it (transform)
            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 != len(entry_payload):
                out.append((c.tag_raw, c.value_raw))
                continue
            entry_parsed = _parse_chunks(entry_chunks_raw)

            patched_entry = False
            new_entry_chunks: List[Tuple[bytes, bytes]] = []
            for ec in entry_parsed:
                if ec.field_number == 11 and ec.wire_type == 2 and not patched_entry:
                    _lraw, transform_payload = _split_length_delimited(ec.value_raw)
                    new_transform = _patch_transform_message(transform_payload, pos=pos, yaw_deg=yaw_deg, scale=scale)
                    new_entry_chunks.append((ec.tag_raw, _wrap_length_delimited(new_transform)))
                    patched_entry = True
                else:
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))

            if patched_entry:
                new_entry_payload = encode_wire_chunks(new_entry_chunks)
                out.append((c.tag_raw, _wrap_length_delimited(new_entry_payload)))
            else:
                out.append((c.tag_raw, c.value_raw))

        return encode_wire_chunks(out)

    patched = patch_field5(patched)

    # Best-effort: update name in payload.field_4[*].message.field_11.field_1 (string)
    # We do not require it for visibility; keep minimal changes.
    return patched


def _patch_accessory_unit(
    unit_bytes: bytes,
    *,
    unit_id: int,
    unit_name: str,
    template_id: int,
    pos: Tuple[float, float, float],
    yaw_deg: Optional[float],
    scale: Tuple[float, float, float],
) -> bytes:
    # Top-level accessory GraphUnit:
    # - field 1: Id message (nested) -> field 4 = unit_id
    # - field 3: name string
    # - wrapper field (often 21): contains field 1 (payload message)
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("wire decode not fully consumed (unit)")
    parsed = _parse_chunks(chunks_raw)

    out: List[Tuple[bytes, bytes]] = []
    wrapper_patched = False
    id_patched = False
    name_patched = False

    for c in parsed:
        # patch Id message: field 1 (length-delimited nested message) => inside field 4 varint
        if c.field_number == 1 and c.wire_type == 2 and not id_patched:
            _lr, id_payload = _split_length_delimited(c.value_raw)
            new_id_payload = _patch_first_varint_field(id_payload, field_number=4, new_value=int(unit_id))
            out.append((c.tag_raw, _wrap_length_delimited(new_id_payload)))
            id_patched = True
            continue

        # patch GraphUnit.name: field 3 string
        if c.field_number == 3 and c.wire_type == 2 and not name_patched:
            encoded = str(unit_name).encode("utf-8")
            out.append((c.tag_raw, _wrap_length_delimited(encoded)))
            name_patched = True
            continue

        # patch wrapper: first non (1,2,3,5) length-delimited field, but easiest: if field 21 exists, patch it.
        if c.field_number in (21, 12, 14, 13) and c.wire_type == 2 and not wrapper_patched:
            # wrapper is a message with field 1 containing payload message
            _lr, wrapper_payload = _split_length_delimited(c.value_raw)

            def patch_wrapper(inner: bytes) -> bytes:
                return _patch_first_length_delimited_message_field(
                    inner,
                    field_number=1,
                    patcher=lambda payload: _patch_accessory_payload(
                        payload,
                        unit_id=int(unit_id),
                        unit_name=str(unit_name),
                        template_id=int(template_id),
                        pos=pos,
                        yaw_deg=yaw_deg,
                        scale=scale,
                    ),
                )

            new_wrapper_payload = patch_wrapper(wrapper_payload)
            out.append((c.tag_raw, _wrap_length_delimited(new_wrapper_payload)))
            wrapper_patched = True
            continue

        out.append((c.tag_raw, c.value_raw))

    return encode_wire_chunks(out)


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


def build_entity_decorations_bundle_wire(
    *,
    base_gia_path: Path,
    decorations_report_json: Path,
    output_gia_path: Path,
    check_header: bool,
    decode_max_depth: int,
    limit_count: int,
) -> Dict[str, Any]:
    base_gia_path = Path(base_gia_path).resolve()
    if check_header:
        validate_gia_container_file(base_gia_path)

    _parent_name, decorations_all = load_decorations_report(Path(decorations_report_json))
    decorations = decorations_all[: int(limit_count)] if int(limit_count) > 0 else decorations_all
    if not decorations:
        raise ValueError("decorations 为空")

    proto_bytes = unwrap_gia_container(base_gia_path, check_header=False)
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")
    root_parsed = _parse_chunks(root_chunks_raw)

    # Extract base filePath (field 3, wire2)
    base_file_path_text = ""
    for c in root_parsed:
        if c.field_number == 3 and c.wire_type == 2:
            _lr, payload = _split_length_delimited(c.value_raw)
            base_file_path_text = payload.decode("utf-8", errors="replace")
            break

    # Extract parent GraphUnit message (field 1)
    parent_chunk = None
    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2:
            parent_chunk = c
            break
    if parent_chunk is None:
        raise ValueError("base: missing Root.field_1 (parent GraphUnit)")
    _lr, parent_bytes = _split_length_delimited(parent_chunk.value_raw)

    # Extract one accessory template (field 2 first occurrence)
    accessory_chunk = None
    for c in root_parsed:
        if c.field_number == 2 and c.wire_type == 2:
            accessory_chunk = c
            break
    if accessory_chunk is None:
        raise ValueError("base: missing Root.field_2 (accessory)")
    _lr2, accessory_template_bytes = _split_length_delimited(accessory_chunk.value_raw)

    # Derive unit_id_start from parent.relatedIds (field 2 nested in parent)
    parent_chunks_raw, _cons2 = decode_message_to_wire_chunks(data_bytes=parent_bytes, start_offset=0, end_offset=len(parent_bytes))
    parent_parsed = _parse_chunks(parent_chunks_raw)
    related_template_chunk = None
    for pc in parent_parsed:
        if pc.field_number == 2 and pc.wire_type == 2:
            related_template_chunk = pc
            break
    if related_template_chunk is None:
        raise ValueError("base: parent GraphUnit missing relatedIds(field_2)")
    _lrr, related_id_payload = _split_length_delimited(related_template_chunk.value_raw)
    # relatedId is Id message: field4 is unit_id
    related_id_patched_probe = related_id_payload
    # parse field4
    rid_chunks_raw, _ = decode_message_to_wire_chunks(
        data_bytes=related_id_patched_probe, start_offset=0, end_offset=len(related_id_patched_probe)
    )
    rid_parsed = _parse_chunks(rid_chunks_raw)
    unit_id_start = None
    for rc in rid_parsed:
        if rc.field_number == 4 and rc.wire_type == 0:
            v, _n, _raw, ok = decode_varint_with_raw(rc.value_raw, 0, len(rc.value_raw))
            if ok:
                unit_id_start = int(v)
            break
    if unit_id_start is None:
        raise ValueError("base: cannot find unit_id_start from relatedId.field_4")

    # Patch parent.relatedIds to N entries (keep other chunks unchanged)
    new_parent_chunks: List[Tuple[bytes, bytes]] = []
    for pc in parent_parsed:
        if pc.field_number == 2 and pc.wire_type == 2:
            continue
        new_parent_chunks.append((pc.tag_raw, pc.value_raw))
    for i in range(len(decorations)):
        uid = unit_id_start + i
        new_related_payload = _patch_first_varint_field(related_id_payload, field_number=4, new_value=int(uid))
        new_parent_chunks.append((related_template_chunk.tag_raw, _wrap_length_delimited(new_related_payload)))
    new_parent_bytes = encode_wire_chunks(new_parent_chunks)

    # Build N accessories
    new_accessory_value_raws: List[Tuple[bytes, bytes]] = []
    for i, dec in enumerate(decorations):
        uid = unit_id_start + i
        new_unit = _patch_accessory_unit(
            accessory_template_bytes,
            unit_id=int(uid),
            unit_name=str(dec.name),
            template_id=int(dec.template_id),
            pos=dec.pos,
            yaw_deg=dec.yaw_deg,
            scale=dec.scale,
        )
        new_accessory_value_raws.append((accessory_chunk.tag_raw, _wrap_length_delimited(new_unit)))

    # Patch root: replace field1, replace all field2, and update filePath to derived name
    output_name = Path(str(output_gia_path)).name
    new_file_path = _derive_file_path_from_base(base_file_path=base_file_path_text, output_file_name=output_name)
    new_file_path_value_raw = _wrap_length_delimited(new_file_path.encode("utf-8"))

    out_root_chunks: List[Tuple[bytes, bytes]] = []
    file_path_patched = False
    parent_patched = False
    accessories_inserted = False
    for c in root_parsed:
        if c.field_number == 1 and c.wire_type == 2 and not parent_patched:
            out_root_chunks.append((c.tag_raw, _wrap_length_delimited(new_parent_bytes)))
            parent_patched = True
            continue
        if c.field_number == 2 and c.wire_type == 2:
            if not accessories_inserted:
                out_root_chunks.extend(new_accessory_value_raws)
                accessories_inserted = True
            continue
        if c.field_number == 3 and c.wire_type == 2 and not file_path_patched:
            out_root_chunks.append((c.tag_raw, new_file_path_value_raw))
            file_path_patched = True
            continue
        out_root_chunks.append((c.tag_raw, c.value_raw))

    if not accessories_inserted:
        out_root_chunks.extend(new_accessory_value_raws)
    if not file_path_patched:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    out_bytes = wrap_gia_container(out_proto)
    output_gia_path = Path(output_gia_path).resolve()
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "base_gia_file": str(base_gia_path),
        "output_gia_file": str(output_gia_path),
        "decorations_count": len(decorations),
        "unit_id_start": int(unit_id_start),
        "file_path": new_file_path,
        "proto_size": len(out_proto),
    }


