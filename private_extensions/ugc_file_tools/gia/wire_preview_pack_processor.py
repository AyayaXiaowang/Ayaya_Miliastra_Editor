from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import (
    decode_message_to_wire_chunks,
    decode_varint_with_raw,
    encode_tag,
    encode_varint,
    encode_wire_chunks,
)
from ugc_file_tools.wire.patch import (
    build_length_delimited_value_raw,
    parse_tag_raw,
    split_length_delimited_value_raw,
    upsert_varint_field,
)


JsonDict = Dict[str, Any]


@dataclass(frozen=True, slots=True)
class GraphUnitId:
    class_int: int
    type_int: int
    id_int: int


@dataclass(frozen=True, slots=True)
class RootUnitRef:
    root_field_no: int  # 1 or 2
    tag_raw: bytes
    value_raw: bytes
    unit_bytes: bytes
    unit_id: GraphUnitId
    which_int: Optional[int]
    name: str
    related_ids: List[GraphUnitId]


def _decode_varint_value(value_raw: bytes) -> int:
    v, next_off, _raw, ok = decode_varint_with_raw(value_raw, 0, len(value_raw))
    if not ok or next_off != len(value_raw):
        raise ValueError("invalid varint value_raw")
    return int(v)


def _decode_f32(value_raw: bytes) -> float:
    if len(value_raw) < 4:
        raise ValueError("fixed32 too short")
    return float(struct.unpack("<f", bytes(value_raw[:4]))[0])


def _encode_f32(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _is_valid_message_payload(payload: bytes) -> bool:
    if not payload:
        return False
    try:
        chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    except Exception:
        return False
    return consumed == len(payload) and len(chunks_raw) > 0


def _extract_unit_id_and_name_and_related(unit_bytes: bytes) -> Tuple[GraphUnitId, Optional[int], str, List[GraphUnitId]]:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("unit wire decode not fully consumed")

    class_int: Optional[int] = None
    type_int: Optional[int] = None
    id_int: Optional[int] = None
    which_int: Optional[int] = None
    name = ""
    related: List[GraphUnitId] = []

    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 1 and tag.wire_type == 2 and id_int is None:
            _lr, id_payload = split_length_delimited_value_raw(value_raw)
            id_chunks, consumed2 = decode_message_to_wire_chunks(
                data_bytes=id_payload, start_offset=0, end_offset=len(id_payload)
            )
            if consumed2 != len(id_payload):
                raise ValueError("id wire decode not fully consumed")
            for itag_raw, ivalue_raw in id_chunks:
                itag = parse_tag_raw(itag_raw)
                if itag.wire_type != 0:
                    continue
                if itag.field_number == 2:
                    class_int = _decode_varint_value(ivalue_raw)
                elif itag.field_number == 3:
                    type_int = _decode_varint_value(ivalue_raw)
                elif itag.field_number == 4:
                    id_int = _decode_varint_value(ivalue_raw)
        elif tag.field_number == 5 and tag.wire_type == 0 and which_int is None:
            which_int = _decode_varint_value(value_raw)
        elif tag.field_number == 3 and tag.wire_type == 2 and name == "":
            _lr, payload = split_length_delimited_value_raw(value_raw)
            name = payload.decode("utf-8", errors="replace")
        elif tag.field_number == 2 and tag.wire_type == 2:
            _lr, rid_payload = split_length_delimited_value_raw(value_raw)
            if not _is_valid_message_payload(rid_payload):
                continue
            rid_chunks, consumed3 = decode_message_to_wire_chunks(
                data_bytes=rid_payload, start_offset=0, end_offset=len(rid_payload)
            )
            if consumed3 != len(rid_payload):
                continue
            # related id entry has two common shapes:
            # - A) message(field_1 -> GraphUnitId(fields 2/3/4))
            # - B) message directly contains GraphUnitId(fields 2/3/4)
            rid_id: Optional[GraphUnitId] = None

            # shape B: direct
            rc2: Optional[int] = None
            rt2: Optional[int] = None
            ri2: Optional[int] = None
            for rtag_raw, rvalue_raw in rid_chunks:
                rtag = parse_tag_raw(rtag_raw)
                if rtag.wire_type != 0:
                    continue
                if rtag.field_number == 2:
                    rc2 = _decode_varint_value(rvalue_raw)
                elif rtag.field_number == 3:
                    rt2 = _decode_varint_value(rvalue_raw)
                elif rtag.field_number == 4:
                    ri2 = _decode_varint_value(rvalue_raw)
            if rc2 is not None and rt2 is not None and ri2 is not None:
                rid_id = GraphUnitId(class_int=int(rc2), type_int=int(rt2), id_int=int(ri2))

            # shape A: nested field_1 (prefer it if present)
            for rtag_raw, rvalue_raw in rid_chunks:
                rtag = parse_tag_raw(rtag_raw)
                if rtag.field_number == 1 and rtag.wire_type == 2:
                    _lr2, inner = split_length_delimited_value_raw(rvalue_raw)
                    if not _is_valid_message_payload(inner):
                        continue
                    inner_chunks, consumed4 = decode_message_to_wire_chunks(
                        data_bytes=inner, start_offset=0, end_offset=len(inner)
                    )
                    if consumed4 != len(inner):
                        continue
                    rc: Optional[int] = None
                    rt: Optional[int] = None
                    ri: Optional[int] = None
                    for itag_raw, ivalue_raw in inner_chunks:
                        itag = parse_tag_raw(itag_raw)
                        if itag.wire_type != 0:
                            continue
                        if itag.field_number == 2:
                            rc = _decode_varint_value(ivalue_raw)
                        elif itag.field_number == 3:
                            rt = _decode_varint_value(ivalue_raw)
                        elif itag.field_number == 4:
                            ri = _decode_varint_value(ivalue_raw)
                    if rc is not None and rt is not None and ri is not None:
                        rid_id = GraphUnitId(class_int=int(rc), type_int=int(rt), id_int=int(ri))
                        break
            if rid_id is not None:
                related.append(rid_id)

    if class_int is None or type_int is None or id_int is None:
        raise ValueError("unit missing id fields")

    return GraphUnitId(class_int=int(class_int), type_int=int(type_int), id_int=int(id_int)), which_int, str(name), related


def _extract_root_units(proto_bytes: bytes) -> Tuple[List[Tuple[bytes, bytes]], List[RootUnitRef], str]:
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")

    base_file_path = ""
    for tag_raw, value_raw in root_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 3 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            base_file_path = payload.decode("utf-8", errors="replace")
            break

    units: List[RootUnitRef] = []
    for tag_raw, value_raw in root_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.wire_type != 2 or tag.field_number not in (1, 2):
            continue
        _lr, payload = split_length_delimited_value_raw(value_raw)
        unit_bytes = bytes(payload)
        try:
            unit_id, which_int, name, related = _extract_unit_id_and_name_and_related(unit_bytes)
        except Exception:
            continue
        units.append(
            RootUnitRef(
                root_field_no=int(tag.field_number),
                tag_raw=bytes(tag_raw),
                value_raw=bytes(value_raw),
                unit_bytes=unit_bytes,
                unit_id=unit_id,
                which_int=which_int,
                name=name,
                related_ids=list(related),
            )
        )

    return root_chunks_raw, units, base_file_path


def _decode_vector3_message(payload: bytes) -> Optional[Tuple[float, float, float]]:
    if not _is_valid_message_payload(payload):
        return None
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload, start_offset=0, end_offset=len(payload))
    if consumed != len(payload):
        return None
    x = y = z = None
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.wire_type != 5:
            continue
        if tag.field_number == 1:
            x = _decode_f32(value_raw)
        elif tag.field_number == 2:
            y = _decode_f32(value_raw)
        elif tag.field_number == 3:
            z = _decode_f32(value_raw)
    if x is None or y is None or z is None:
        return None
    return (float(x), float(y), float(z))


def _find_first_transform_pos_in_message(message_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    if not _is_valid_message_payload(message_bytes):
        return None
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes)
    )
    if consumed != len(message_bytes):
        return None

    # heuristic: transform-like message has field_1 length-delimited which is Vector3
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 1 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            vec = _decode_vector3_message(payload)
            if vec is not None:
                return vec

    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.wire_type != 2:
            continue
        _lr, payload = split_length_delimited_value_raw(value_raw)
        if _is_valid_message_payload(payload):
            found = _find_first_transform_pos_in_message(payload)
            if found is not None:
                return found
    return None


def _patch_first_transform_pos_in_message(message_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> Tuple[bytes, bool]:
    if not _is_valid_message_payload(message_bytes):
        return message_bytes, False
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes)
    )
    if consumed != len(message_bytes):
        return message_bytes, False

    # if this is a transform-like message, rebuild only position
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 1 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            if _decode_vector3_message(payload) is None:
                continue
            # patch field_1 vector3 payload
            new_vec = encode_wire_chunks(
                [
                    (encode_tag(1, 5), _encode_f32(new_pos[0])),
                    (encode_tag(2, 5), _encode_f32(new_pos[1])),
                    (encode_tag(3, 5), _encode_f32(new_pos[2])),
                ]
            )
            out: List[Tuple[bytes, bytes]] = []
            patched = False
            for t2, v2 in chunks_raw:
                tt = parse_tag_raw(t2)
                if (not patched) and tt.field_number == 1 and tt.wire_type == 2:
                    out.append((bytes(t2), build_length_delimited_value_raw(new_vec)))
                    patched = True
                else:
                    out.append((bytes(t2), bytes(v2)))
            return encode_wire_chunks(out), True

    # otherwise recurse into first nested message
    out2: List[Tuple[bytes, bytes]] = []
    patched_any = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if (not patched_any) and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            if _is_valid_message_payload(payload):
                new_payload, ok = _patch_first_transform_pos_in_message(payload, new_pos=tuple(new_pos))
                if ok:
                    out2.append((bytes(tag_raw), build_length_delimited_value_raw(new_payload)))
                    patched_any = True
                    continue
        out2.append((bytes(tag_raw), bytes(value_raw)))
    if not patched_any:
        return message_bytes, False
    return encode_wire_chunks(out2), True


def _extract_graph_unit_pos(unit_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    """
    提取 GraphUnit 的 position（用于居中/平移）。

    注意：Root.field_2 的 instances(GraphUnit class=1,type=14,which=28) 常为 wrapper+payload 结构，
    payload 内部可能同时存在“非 Transform 的 Vector3-like message”（例如额外数据/颜色/占位字段）。
    若直接对 unit 做 DFS 取第一个 Vector3，会误读/误补丁并破坏真源可见性。
    """
    uid, which_int = _parse_unit_id_and_which(unit_bytes)
    if uid.class_int == 1 and uid.type_int == 14 and which_int == 28:
        return _extract_instance_pos(unit_bytes)
    # best-effort: DFS search first transform-like pos
    return _find_first_transform_pos_in_message(unit_bytes)


def _patch_graph_unit_pos(unit_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> bytes:
    uid, which_int = _parse_unit_id_and_which(unit_bytes)
    if uid.class_int == 1 and uid.type_int == 14 and which_int == 28:
        return _patch_instance_pos(unit_bytes, new_pos=tuple(new_pos))

    patched, ok = _patch_first_transform_pos_in_message(unit_bytes, new_pos=tuple(new_pos))
    if not ok:
        raise ValueError("GraphUnit: 找不到可补丁的 Transform.position")
    return bytes(patched)


def _parse_unit_id_and_which(unit_bytes: bytes) -> Tuple[GraphUnitId, int]:
    """
    从 GraphUnit 中提取 (GraphUnitId, which)。
    - id: unit.field_1(message).field_{2,3,4}
    - which: unit.field_5(varint)；缺失则视为 0
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("unit wire decode not fully consumed")

    class_int: Optional[int] = None
    type_int: Optional[int] = None
    id_int: Optional[int] = None
    which_int: Optional[int] = None

    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 5 and tag.wire_type == 0 and which_int is None:
            which_int = _decode_varint_value(value_raw)
            continue
        if tag.field_number == 1 and tag.wire_type == 2 and (class_int is None or type_int is None or id_int is None):
            _lr, id_payload = split_length_delimited_value_raw(value_raw)
            id_chunks, consumed2 = decode_message_to_wire_chunks(
                data_bytes=id_payload, start_offset=0, end_offset=len(id_payload)
            )
            if consumed2 != len(id_payload):
                raise ValueError("id wire decode not fully consumed")
            for itag_raw, ivalue_raw in id_chunks:
                itag = parse_tag_raw(itag_raw)
                if itag.wire_type != 0:
                    continue
                if itag.field_number == 2:
                    class_int = _decode_varint_value(ivalue_raw)
                elif itag.field_number == 3:
                    type_int = _decode_varint_value(ivalue_raw)
                elif itag.field_number == 4:
                    id_int = _decode_varint_value(ivalue_raw)

    if class_int is None or type_int is None or id_int is None:
        raise ValueError("unit missing id fields")
    if which_int is None:
        which_int = 0
    return GraphUnitId(class_int=int(class_int), type_int=int(type_int), id_int=int(id_int)), int(which_int)


def _extract_instance_payload_bytes(instance_unit_bytes: bytes) -> bytes:
    """
    instances(GraphUnit class=1,type=14,which=28) 的经验结构：
    - unit.field_21(wrapper).field_1(payload)
    - payload 内通常含 field_5(transform entries) 与 field_4(template bind)。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=instance_unit_bytes, start_offset=0, end_offset=len(instance_unit_bytes)
    )
    if consumed != len(instance_unit_bytes):
        raise ValueError("instance unit: wire decode not fully consumed")

    # prefer field_21, fallback to other length-delimited fields
    candidates: List[bytes] = []
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.wire_type != 2:
            continue
        _lr, maybe_wrapper = split_length_delimited_value_raw(value_raw)
        if tag.field_number == 21:
            candidates.insert(0, bytes(maybe_wrapper))
        else:
            candidates.append(bytes(maybe_wrapper))

    for wrapper_bytes in candidates:
        if not _is_valid_message_payload(wrapper_bytes):
            continue
        wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=wrapper_bytes, start_offset=0, end_offset=len(wrapper_bytes)
        )
        if consumed2 != len(wrapper_bytes):
            continue
        for wtag_raw, wvalue_raw in wrapper_chunks_raw:
            wtag = parse_tag_raw(wtag_raw)
            if wtag.field_number != 1 or wtag.wire_type != 2:
                continue
            _lr2, payload_bytes = split_length_delimited_value_raw(wvalue_raw)
            if not _is_valid_message_payload(payload_bytes):
                continue
            # quick structure check: payload has field_5 (transform entries)
            payload_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes)
            )
            if consumed3 != len(payload_bytes):
                continue
            has5 = False
            for ptag_raw, _pvalue_raw in payload_chunks_raw:
                ptag = parse_tag_raw(ptag_raw)
                if ptag.field_number == 5:
                    has5 = True
                    break
            if has5:
                return bytes(payload_bytes)

    raise ValueError("instance unit: 找不到 wrapper.payload(field_1)")


def _extract_instance_pos(instance_unit_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    """
    从 instance(GraphUnit class=1,type=14,which=28) 中提取 Transform.position。
    经验路径：
    - wrapper.payload.field_5[*].field_11(transform).field_1(Vector3)
    """
    payload_bytes = _extract_instance_payload_bytes(instance_unit_bytes)
    payload_chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes)
    )
    if consumed != len(payload_bytes):
        raise ValueError("payload: wire decode not fully consumed")

    for tag_raw, value_raw in payload_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 5 or tag.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(value_raw)
        if not _is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            continue
        for etag_raw, evalue_raw in entry_chunks_raw:
            etag = parse_tag_raw(etag_raw)
            if etag.field_number != 11 or etag.wire_type != 2:
                continue
            _lr2, transform_payload = split_length_delimited_value_raw(evalue_raw)
            if not _is_valid_message_payload(transform_payload):
                continue
            # transform.field_1(Vector3)
            t_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                data_bytes=transform_payload, start_offset=0, end_offset=len(transform_payload)
            )
            if consumed3 != len(transform_payload):
                continue
            for ttag_raw, tvalue_raw in t_chunks_raw:
                ttag = parse_tag_raw(ttag_raw)
                if ttag.field_number == 1 and ttag.wire_type == 2:
                    _lr3, vec_payload = split_length_delimited_value_raw(tvalue_raw)
                    vec = _decode_vector3_message(vec_payload)
                    if vec is not None:
                        return tuple(vec)
    return None


def _patch_instance_pos(instance_unit_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> bytes:
    """
    wire-level：只补丁 instances(GraphUnit class=1,type=14,which=28) 的 Transform.position。
    - 避免 DFS 误补丁 payload 内其它 Vector3-like message
    - 尽量复用既有 tag/value 以保持最小差异
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=instance_unit_bytes, start_offset=0, end_offset=len(instance_unit_bytes)
    )
    if consumed != len(instance_unit_bytes):
        raise ValueError("instance unit: wire decode not fully consumed")

    def patch_transform_message(transform_payload: bytes) -> bytes:
        t_chunks_raw, consumed_t = decode_message_to_wire_chunks(
            data_bytes=transform_payload, start_offset=0, end_offset=len(transform_payload)
        )
        if consumed_t != len(transform_payload):
            raise ValueError("transform: wire decode not fully consumed")
        new_vec = encode_wire_chunks(
            [
                (encode_tag(1, 5), _encode_f32(float(new_pos[0]))),
                (encode_tag(2, 5), _encode_f32(float(new_pos[1]))),
                (encode_tag(3, 5), _encode_f32(float(new_pos[2]))),
            ]
        )
        out_t: List[Tuple[bytes, bytes]] = []
        patched_vec = False
        for ttag_raw, tvalue_raw in t_chunks_raw:
            ttag = parse_tag_raw(ttag_raw)
            if (not patched_vec) and ttag.field_number == 1 and ttag.wire_type == 2:
                out_t.append((bytes(ttag_raw), build_length_delimited_value_raw(new_vec)))
                patched_vec = True
            else:
                out_t.append((bytes(ttag_raw), bytes(tvalue_raw)))
        if not patched_vec:
            out_t.append((encode_tag(1, 2), build_length_delimited_value_raw(new_vec)))
        return encode_wire_chunks(out_t)

    def patch_payload(payload_bytes: bytes) -> Tuple[bytes, bool]:
        payload_chunks_raw, consumed_p = decode_message_to_wire_chunks(
            data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes)
        )
        if consumed_p != len(payload_bytes):
            raise ValueError("payload: wire decode not fully consumed")
        out_p: List[Tuple[bytes, bytes]] = []
        patched = False
        for tag_raw, value_raw in payload_chunks_raw:
            tag = parse_tag_raw(tag_raw)
            if (not patched) and tag.field_number == 5 and tag.wire_type == 2:
                _lr, entry_payload = split_length_delimited_value_raw(value_raw)
                if not _is_valid_message_payload(entry_payload):
                    out_p.append((bytes(tag_raw), bytes(value_raw)))
                    continue
                entry_chunks_raw, consumed_e = decode_message_to_wire_chunks(
                    data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
                )
                if consumed_e != len(entry_payload):
                    out_p.append((bytes(tag_raw), bytes(value_raw)))
                    continue
                new_entry_chunks: List[Tuple[bytes, bytes]] = []
                entry_patched = False
                for etag_raw, evalue_raw in entry_chunks_raw:
                    etag = parse_tag_raw(etag_raw)
                    if (not entry_patched) and etag.field_number == 11 and etag.wire_type == 2:
                        _lr2, transform_payload = split_length_delimited_value_raw(evalue_raw)
                        if not _is_valid_message_payload(transform_payload):
                            new_entry_chunks.append((bytes(etag_raw), bytes(evalue_raw)))
                            continue
                        new_transform = patch_transform_message(bytes(transform_payload))
                        new_entry_chunks.append((bytes(etag_raw), build_length_delimited_value_raw(bytes(new_transform))))
                        entry_patched = True
                    else:
                        new_entry_chunks.append((bytes(etag_raw), bytes(evalue_raw)))
                if entry_patched:
                    out_p.append((bytes(tag_raw), build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
                    patched = True
                else:
                    out_p.append((bytes(tag_raw), bytes(value_raw)))
                continue
            out_p.append((bytes(tag_raw), bytes(value_raw)))
        return encode_wire_chunks(out_p), patched

    # patch first wrapper that contains field_1 payload with field_5 entries
    out_unit: List[Tuple[bytes, bytes]] = []
    wrapper_patched = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if (not wrapper_patched) and tag.wire_type == 2:
            _lr, maybe_wrapper = split_length_delimited_value_raw(value_raw)
            if _is_valid_message_payload(maybe_wrapper):
                wrapper_chunks_raw, consumed_w = decode_message_to_wire_chunks(
                    data_bytes=maybe_wrapper, start_offset=0, end_offset=len(maybe_wrapper)
                )
                if consumed_w == len(maybe_wrapper):
                    new_wrapper_chunks: List[Tuple[bytes, bytes]] = []
                    payload_patched = False
                    for wtag_raw, wvalue_raw in wrapper_chunks_raw:
                        wtag = parse_tag_raw(wtag_raw)
                        if (not payload_patched) and wtag.field_number == 1 and wtag.wire_type == 2:
                            _lr2, payload_bytes = split_length_delimited_value_raw(wvalue_raw)
                            if _is_valid_message_payload(payload_bytes):
                                new_payload, ok = patch_payload(bytes(payload_bytes))
                                if ok:
                                    new_wrapper_chunks.append((bytes(wtag_raw), build_length_delimited_value_raw(bytes(new_payload))))
                                    payload_patched = True
                                    continue
                        new_wrapper_chunks.append((bytes(wtag_raw), bytes(wvalue_raw)))
                    if payload_patched:
                        out_unit.append((bytes(tag_raw), build_length_delimited_value_raw(encode_wire_chunks(new_wrapper_chunks))))
                        wrapper_patched = True
                        continue
        out_unit.append((bytes(tag_raw), bytes(value_raw)))

    if not wrapper_patched:
        raise ValueError("instance unit: 找不到可补丁的 wrapper.payload(field_1)")
    return encode_wire_chunks(out_unit)


def _patch_graph_unit_id_type_and_which(unit_bytes: bytes, *, new_type_int: int, new_which_int: int) -> bytes:
    """
    将 GraphUnitId.type(field_1.field_3) 与 GraphUnit.which(field_5) 补丁成目标值。
    用于“把模板/控模型类 GraphUnit 实体化为 type=14, which=28”这类需求。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")

    out: List[Tuple[bytes, bytes]] = []
    id_patched = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if (not id_patched) and tag.field_number == 1 and tag.wire_type == 2:
            _lr, id_payload = split_length_delimited_value_raw(value_raw)
            id_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=id_payload, start_offset=0, end_offset=len(id_payload)
            )
            if consumed2 != len(id_payload):
                raise ValueError("GraphUnitId wire decode not fully consumed")
            patched_id_chunks = upsert_varint_field(id_chunks_raw, field_number=3, new_value=int(new_type_int))
            out.append((bytes(tag_raw), build_length_delimited_value_raw(encode_wire_chunks(list(patched_id_chunks)))))
            id_patched = True
            continue
        out.append((bytes(tag_raw), bytes(value_raw)))

    if not id_patched:
        raise ValueError("GraphUnit 缺少 id(field_1)")

    patched2 = upsert_varint_field(out, field_number=5, new_value=int(new_which_int))
    return encode_wire_chunks(list(patched2))


def _compute_center(points: Sequence[Tuple[float, float, float]], *, mode: str) -> Tuple[float, float, float]:
    m = str(mode or "").strip().lower()
    if m not in {"bbox", "mean"}:
        raise ValueError(f"invalid center mode: {mode!r}")
    if not points:
        raise ValueError("points is empty")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    zs = [float(p[2]) for p in points]
    if m == "mean":
        n = float(len(points))
        return (sum(xs) / n, sum(ys) / n, sum(zs) / n)
    return ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)


def _extract_level_key(name: str, *, level_regex: str) -> str:
    text = str(name or "")
    try:
        m = re.search(level_regex, text)
    except re.error as e:
        raise ValueError(f"invalid level_regex: {level_regex!r}: {e}") from e
    if not m:
        return ""
    return str(m.group(0))


def _extract_related_id_int_from_related_value_raw(value_raw: bytes) -> Optional[int]:
    """
    从 parent GraphUnit 的 field_2(value_raw) 里尽力抽取 related child 的 id_int。
    兼容两种常见形态：
    - rid.message.field_1 -> GraphUnitId(fields 2/3/4)
    - rid.message 直接包含 GraphUnitId(fields 2/3/4)
    返回 child_id_int；失败返回 None（合并时会用 bytes 去重兜底）。
    """
    try:
        _lr, rid_payload = split_length_delimited_value_raw(value_raw)
    except Exception:
        return None
    if not _is_valid_message_payload(rid_payload):
        return None
    try:
        rid_chunks, consumed = decode_message_to_wire_chunks(
            data_bytes=rid_payload, start_offset=0, end_offset=len(rid_payload)
        )
    except Exception:
        return None
    if consumed != len(rid_payload):
        return None

    # shape B: direct field_4
    for t, v in rid_chunks:
        tag = parse_tag_raw(t)
        if tag.field_number == 4 and tag.wire_type == 0:
            try:
                return int(_decode_varint_value(v))
            except Exception:
                return None

    # shape A: nested field_1 -> GraphUnitId
    for t, v in rid_chunks:
        tag = parse_tag_raw(t)
        if tag.field_number == 1 and tag.wire_type == 2:
            try:
                _lr2, inner = split_length_delimited_value_raw(v)
            except Exception:
                continue
            if not _is_valid_message_payload(inner):
                continue
            try:
                inner_chunks, consumed2 = decode_message_to_wire_chunks(
                    data_bytes=inner, start_offset=0, end_offset=len(inner)
                )
            except Exception:
                continue
            if consumed2 != len(inner):
                continue
            for it, iv in inner_chunks:
                itag = parse_tag_raw(it)
                if itag.field_number == 4 and itag.wire_type == 0:
                    try:
                        return int(_decode_varint_value(iv))
                    except Exception:
                        return None
    return None


def _rewrite_parent_related_ids_using_existing_chunks(
    parent_unit_bytes: bytes, *, related_value_raw_list: Sequence[bytes]
) -> bytes:
    """
    保真合并：不重建 relatedId message，只复用输入里已有的 field_2(value_raw) chunks。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=parent_unit_bytes, start_offset=0, end_offset=len(parent_unit_bytes)
    )
    if consumed != len(parent_unit_bytes):
        raise ValueError("parent unit: wire decode not fully consumed")
    kept: List[Tuple[bytes, bytes]] = []
    for t, v in chunks_raw:
        tag = parse_tag_raw(t)
        if tag.field_number == 2 and tag.wire_type == 2:
            continue
        kept.append((bytes(t), bytes(v)))

    # append related chunks in given order
    out = list(kept)
    for vr in list(related_value_raw_list):
        out.append((encode_tag(2, 2), bytes(vr)))
    return encode_wire_chunks(out)


def process_preview_entities_in_pack_wire(
    *,
    input_gia_path: Path,
    output_gia_path: Path,
    check_header: bool,
    name_contains: str,
    center_mode: str,
    level_regex: str,
    merge_same_level: bool,
    drop_other_parents: bool,
    entityize_parents: bool,
    keep_file_path: bool,
    file_path_override: str,
) -> Dict[str, Any]:
    """
    针对“打包 .gia”内的预览实体做处理：
    - 找到 name 包含 name_contains 且 relatedIds 非空的 GraphUnit 作为 parent（控模型）
    - 计算其 relatedIds 指向的子 GraphUnit 的 position 中心
    - 将 parent.position 设置为中心
    - 然后将 parent 与所有子物体整体平移，使 parent 落在原点（0,0,0）
    - 可选：按 level_regex 提取关卡 key，将同关多 parent 合并（relatedIds 并集），并删除/保留其它 parent
    """
    input_gia_path = Path(input_gia_path).resolve()
    if check_header:
        validate_gia_container_file(input_gia_path)
    proto_bytes = unwrap_gia_container(input_gia_path, check_header=False)
    root_chunks_raw, units, base_file_path = _extract_root_units(proto_bytes)

    contains = str(name_contains or "").strip()
    if contains == "":
        raise ValueError("name_contains 不能为空")

    # map: unit_id_int -> RootUnitRef
    by_id: Dict[int, RootUnitRef] = {}
    for u in units:
        if u.unit_id.id_int not in by_id:
            by_id[int(u.unit_id.id_int)] = u

    parents = [u for u in units if (contains in u.name) and len(u.related_ids) > 0]
    if not parents:
        candidates = sorted(
            [u for u in units if len(u.related_ids) > 0],
            key=lambda x: (len(x.related_ids), x.name),
            reverse=True,
        )
        lines = [
            f"未找到任何 name 包含 {contains!r} 且 relatedIds 非空的 parent GraphUnit。",
            "可选候选（按 relatedIds 数量降序，最多 20 条）：",
        ]
        for c in candidates[:20]:
            lines.append(
                f"- id={c.unit_id.id_int} (c={c.unit_id.class_int},t={c.unit_id.type_int},w={c.which_int}) "
                f"related={len(c.related_ids)} name={c.name!r}"
            )
        if not candidates:
            lines.append("- (none) 当前解析未发现任何 relatedIds 非空的 GraphUnit（可能该 .gia 不是 relatedIds 组织形态）")
        raise ValueError("\n".join(lines))

    # group by level key
    groups: Dict[str, List[RootUnitRef]] = {}
    for p in parents:
        key = _extract_level_key(p.name, level_regex=str(level_regex))
        if key == "":
            key = p.name  # fallback: name as key to avoid accidental merge
        groups.setdefault(key, []).append(p)

    merged_parent_ids: Set[int] = set()
    removed_parent_ids: Set[int] = set()
    entityized_parent_ids: Set[int] = set()
    parents_need_related_ids_rewrite: Set[int] = set()
    related_value_raw_list_by_parent_id: Dict[int, List[bytes]] = {}

    # build parent -> child ids
    child_ids_by_parent: Dict[int, List[int]] = {}
    for p in parents:
        child_ids: List[int] = []
        for rid in p.related_ids:
            child_ids.append(int(rid.id_int))
        child_ids_by_parent[int(p.unit_id.id_int)] = child_ids

    # merge same level: union relatedId chunks under one keeper (保真：复用原 field_2 value_raw)
    keeper_by_level: Dict[str, int] = {}
    for level_key, plist in groups.items():
        if (not bool(merge_same_level)) or len(plist) <= 1:
            keeper_by_level[level_key] = int(plist[0].unit_id.id_int)
            continue
        keeper = plist[0]
        keeper_id = int(keeper.unit_id.id_int)
        keeper_by_level[level_key] = keeper_id

        # collect original field_2(value_raw) chunks from all parents in this level
        related_value_raw_union: List[bytes] = []
        seen_child_ids: Set[int] = set()
        seen_raw: Set[bytes] = set()
        for p in plist:
            # parse unit chunks to fetch field_2 value_raw
            p_chunks, consumed_p = decode_message_to_wire_chunks(
                data_bytes=p.unit_bytes, start_offset=0, end_offset=len(p.unit_bytes)
            )
            if consumed_p != len(p.unit_bytes):
                continue
            for t, v in p_chunks:
                tag = parse_tag_raw(t)
                if tag.field_number != 2 or tag.wire_type != 2:
                    continue
                raw = bytes(v)
                child_id = _extract_related_id_int_from_related_value_raw(raw)
                if isinstance(child_id, int) and child_id > 0:
                    if int(child_id) in seen_child_ids:
                        continue
                    seen_child_ids.add(int(child_id))
                    related_value_raw_union.append(raw)
                else:
                    # fallback: dedupe by raw bytes
                    if raw in seen_raw:
                        continue
                    seen_raw.add(raw)
                    related_value_raw_union.append(raw)

        # store derived child ids list for later centering
        union_ids: List[int] = []
        for cid in sorted(seen_child_ids):
            union_ids.append(int(cid))
        child_ids_by_parent[keeper_id] = union_ids
        related_value_raw_list_by_parent_id[int(keeper_id)] = list(related_value_raw_union)
        merged_parent_ids.add(keeper_id)
        parents_need_related_ids_rewrite.add(keeper_id)
        for p in plist[1:]:
            other_id = int(p.unit_id.id_int)
            if bool(drop_other_parents):
                removed_parent_ids.add(other_id)
            else:
                # keep other parent but clear its relatedIds by setting empty list (we'll rebuild field_2 to empty by dropping chunks)
                child_ids_by_parent[other_id] = []
                parents_need_related_ids_rewrite.add(other_id)
                related_value_raw_list_by_parent_id[int(other_id)] = []
                removed_parent_ids.discard(other_id)

    # Patch units: we only patch parents + their children; others are left untouched.
    patched_units_by_id: Dict[int, bytes] = {}

    processed_groups = 0
    for level_key, keeper_id in keeper_by_level.items():
        if keeper_id in removed_parent_ids:
            continue
        parent_ref = by_id.get(int(keeper_id))
        if parent_ref is None:
            continue

        child_ids = child_ids_by_parent.get(int(keeper_id), [])
        child_positions: List[Tuple[float, float, float]] = []
        existing_child_ids: List[int] = []
        for cid in child_ids:
            child_ref = by_id.get(int(cid))
            if child_ref is None:
                continue
            pos = _extract_graph_unit_pos(child_ref.unit_bytes)
            if pos is None:
                continue
            existing_child_ids.append(int(cid))
            child_positions.append(tuple(pos))

        if not child_positions:
            # nothing to center; skip group but still may have merged relatedIds
            continue

        center = _compute_center(child_positions, mode=str(center_mode))

        # 1) set parent to center (without moving children)
        parent_patched = _patch_graph_unit_pos(parent_ref.unit_bytes, new_pos=tuple(center))

        # 2) shift parent + children so parent goes to origin
        shift = center
        parent_final = _patch_graph_unit_pos(parent_patched, new_pos=(0.0, 0.0, 0.0))
        patched_units_by_id[int(keeper_id)] = bytes(parent_final)

        for cid in existing_child_ids:
            child_ref = by_id.get(int(cid))
            if child_ref is None:
                continue
            pos0 = _extract_graph_unit_pos(child_ref.unit_bytes)
            if pos0 is None:
                continue
            new_pos = (float(pos0[0] - shift[0]), float(pos0[1] - shift[1]), float(pos0[2] - shift[2]))
            patched_units_by_id[int(cid)] = _patch_graph_unit_pos(child_ref.unit_bytes, new_pos=tuple(new_pos))

        processed_groups += 1

    # entityize parents (best-effort): 对齐真源“实体导出.gia”：type=2, which=3
    if bool(entityize_parents):
        for p in parents:
            pid = int(p.unit_id.id_int)
            if pid in removed_parent_ids:
                continue
            # use already patched bytes if present
            base_unit = patched_units_by_id.get(pid, p.unit_bytes)
            try:
                patched_units_by_id[pid] = _patch_graph_unit_id_type_and_which(
                    base_unit, new_type_int=2, new_which_int=3
                )
                entityized_parent_ids.add(pid)
            except Exception:
                # fail-fast is not desired here: best-effort for pack variety
                continue

    # Rebuild root: replace patched units, drop removed parents, and (only when needed) update relatedIds for parents we merged/cleared.
    # 注意：relatedIds 更新必须保真复用既有 chunks，否则真源可能整包不可解析。

    # filePath
    output_gia_path = Path(output_gia_path).resolve()
    output_name = output_gia_path.name
    file_path_text = str(file_path_override or "").strip()
    if file_path_text != "":
        new_file_path = file_path_text
    elif bool(keep_file_path):
        new_file_path = str(base_file_path)
    else:
        # keep dir part, replace file name
        base = str(base_file_path or "").strip()
        marker = "\\"
        last = base.rfind(marker)
        if last >= 0:
            new_file_path = base[: last + 1] + output_name
        else:
            new_file_path = output_name

    new_file_path_value_raw = build_length_delimited_value_raw(str(new_file_path).encode("utf-8"))

    out_root_chunks: List[Tuple[bytes, bytes]] = []
    file_path_written = False
    for tag_raw, value_raw in root_chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number in (1, 2) and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            unit_bytes = bytes(payload)
            try:
                uid, _which, _name, _related = _extract_unit_id_and_name_and_related(unit_bytes)
            except Exception:
                out_root_chunks.append((bytes(tag_raw), bytes(value_raw)))
                continue

            unit_id_int = int(uid.id_int)
            if unit_id_int in removed_parent_ids:
                continue

            out_unit = patched_units_by_id.get(unit_id_int, unit_bytes)

            # update relatedIds only for parents that actually need rewrite (merge/clear)
            if unit_id_int in parents_need_related_ids_rewrite:
                out_unit = _rewrite_parent_related_ids_using_existing_chunks(
                    out_unit,
                    related_value_raw_list=related_value_raw_list_by_parent_id.get(int(unit_id_int), []),
                )

            out_root_chunks.append((bytes(tag_raw), build_length_delimited_value_raw(bytes(out_unit))))
            continue

        if tag.field_number == 3 and tag.wire_type == 2 and (not file_path_written):
            out_root_chunks.append((bytes(tag_raw), bytes(new_file_path_value_raw)))
            file_path_written = True
            continue

        out_root_chunks.append((bytes(tag_raw), bytes(value_raw)))

    if not file_path_written:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    out_bytes = wrap_gia_container(out_proto)
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "input_gia_file": str(input_gia_path),
        "output_gia_file": str(output_gia_path),
        "matched_parents_count": int(len(parents)),
        "level_groups_count": int(len(groups)),
        "processed_groups_count": int(processed_groups),
        "merged_parent_ids_count": int(len(merged_parent_ids)),
        "removed_parent_ids_count": int(len(removed_parent_ids)),
        "entityized_parent_ids_count": int(len(entityized_parent_ids)),
        "file_path": str(new_file_path),
        "proto_size": int(len(out_proto)),
    }


__all__ = ["process_preview_entities_in_pack_wire"]

