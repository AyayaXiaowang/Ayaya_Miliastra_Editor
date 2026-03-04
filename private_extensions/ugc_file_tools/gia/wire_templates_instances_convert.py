from __future__ import annotations

"""
wire_templates_instances_convert.py

目标：对“元件模板 + 实体摆放(实例)”类 `.gia` bundle 做双向转换：
- component_to_entity：从 Root.field_1(templates) 生成 Root.field_2(instances)
- entity_to_component：从 Root.field_2(instances) 反推引用闭包，裁剪 Root.field_1(templates)，并清空 Root.field_2

注意：
- 该模块处理的 `.gia` 形态为 pipelines.gia_templates_and_instances_to_project_archive 中描述的 bundle：
  - templates(GraphUnit): class=1,type=1,which=1，位于 Root.field_1
  - instances(GraphUnit): class=1,type=14,which=28，位于 Root.field_2，且 wrapper.1.payload.4[*].50.502 存放 template_root_id_int
- 为提高真源可见性，component_to_entity 优先“克隆一个既有 instance 作为结构模板”再补丁必要字段；
  若输入内无可用 instance，可通过 `instance_template_gia_path` 额外提供一个真源样本。
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ugc_file_tools.gia.container import unwrap_gia_container, validate_gia_container_file, wrap_gia_container
from ugc_file_tools.gil_dump_codec.protobuf_like import decode_message_to_wire_chunks, encode_tag, encode_varint, encode_wire_chunks
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


def _decode_f32(value_raw: bytes) -> float:
    if len(value_raw) < 4:
        raise ValueError("fixed32 float payload too short")
    return float(struct.unpack("<f", bytes(value_raw[:4]))[0])


def _encode_f32(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _build_vector3_message(x: float, y: float, z: float) -> bytes:
    return encode_wire_chunks(
        [
            (encode_tag(1, 5), _encode_f32(x)),
            (encode_tag(2, 5), _encode_f32(y)),
            (encode_tag(3, 5), _encode_f32(z)),
        ]
    )


def _parse_unit_id(unit_bytes: bytes) -> GraphUnitId:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")

    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 1 or tag.wire_type != 2:
            continue
        _lr, id_payload = split_length_delimited_value_raw(value_raw)
        id_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=id_payload, start_offset=0, end_offset=len(id_payload))
        if consumed2 != len(id_payload):
            raise ValueError("GraphUnitId wire decode not fully consumed")
        parsed = [(parse_tag_raw(t), v) for t, v in id_chunks_raw]
        class_int: Optional[int] = None
        type_int: Optional[int] = None
        id_int: Optional[int] = None
        for t, v in parsed:
            if t.wire_type != 0:
                continue
            # varint raw is already v; we only need int, so reuse upsert_varint_field semantics by decoding via encode_varint?
            # Here use protobuf-like: varint bytes are little-endian base-128; easiest: re-encode roundtrip not needed.
            # We'll decode with a tiny helper to avoid extra imports.
            val = 0
            shift = 0
            for b in bytes(v):
                val |= (b & 0x7F) << shift
                if (b & 0x80) == 0:
                    break
                shift += 7
            if t.field_number == 2:
                class_int = int(val)
            elif t.field_number == 3:
                type_int = int(val)
            elif t.field_number == 4:
                id_int = int(val)
        if not (isinstance(class_int, int) and isinstance(type_int, int) and isinstance(id_int, int)):
            raise ValueError("GraphUnitId 缺少 class/type/id")
        return GraphUnitId(class_int=int(class_int), type_int=int(type_int), id_int=int(id_int))
    raise ValueError("GraphUnit 缺少 id(field_1)")


def _parse_unit_which(unit_bytes: bytes) -> Optional[int]:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 5 and tag.wire_type == 0:
            # decode varint quickly
            val = 0
            shift = 0
            for b in bytes(value_raw):
                val |= (b & 0x7F) << shift
                if (b & 0x80) == 0:
                    break
                shift += 7
            return int(val)
    return None


def _is_template_unit(unit_bytes: bytes) -> bool:
    uid = _parse_unit_id(unit_bytes)
    which = _parse_unit_which(unit_bytes)
    return bool(uid.class_int == 1 and uid.type_int == 1 and which == 1)


def _is_instance_unit(unit_bytes: bytes) -> bool:
    uid = _parse_unit_id(unit_bytes)
    which = _parse_unit_which(unit_bytes)
    return bool(uid.class_int == 1 and uid.type_int == 14 and which == 28)


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


def _extract_template_root_id_from_instance_payload(payload_bytes: bytes) -> Optional[int]:
    """
    经验路径（已用真源样本验证）：
    - payload.field_4[*].field_50.message.field_502 -> template_root_id_int
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("instance payload wire decode not fully consumed")
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 4 or tag.wire_type != 2:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(value_raw)
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload))
        if consumed2 != len(entry_payload):
            continue
        for etag_raw, evalue_raw in entry_chunks_raw:
            etag = parse_tag_raw(etag_raw)
            if etag.field_number != 50 or etag.wire_type != 2:
                continue
            _lr2, nested_payload = split_length_delimited_value_raw(evalue_raw)
            nested_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
            )
            if consumed3 != len(nested_payload):
                continue
            for ntag_raw, nvalue_raw in nested_chunks_raw:
                ntag = parse_tag_raw(ntag_raw)
                if ntag.field_number == 502 and ntag.wire_type == 0:
                    # decode varint
                    val = 0
                    shift = 0
                    for b in bytes(nvalue_raw):
                        val |= (b & 0x7F) << shift
                        if (b & 0x80) == 0:
                            break
                        shift += 7
                    return int(val)
    return None


def _extract_instance_payload_bytes(instance_unit_bytes: bytes) -> bytes:
    """
    经验：instances 使用 GraphUnit.field_21 作为 wrapper，wrapper.field_1 为 payload(message)。
    为稳妥起见：只要某个 length-delimited 字段 payload 里存在 field_1(message)，且其 message 内包含 field_4 或 field_5，则视为 wrapper。
    """
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=instance_unit_bytes, start_offset=0, end_offset=len(instance_unit_bytes)
    )
    if consumed != len(instance_unit_bytes):
        raise ValueError("instance unit: wire decode not fully consumed")

    # prefer field_21
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
            # quick structure check: payload has field_4 or field_5
            payload_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes)
            )
            if consumed3 != len(payload_bytes):
                continue
            has4or5 = False
            for ptag_raw, _pvalue_raw in payload_chunks_raw:
                ptag = parse_tag_raw(ptag_raw)
                if ptag.field_number in (4, 5):
                    has4or5 = True
                    break
            if has4or5:
                return bytes(payload_bytes)

    raise ValueError("instance unit: 找不到 wrapper.payload(field_1)")


def _patch_instance_payload_template_root_id(payload_bytes: bytes, *, template_root_id_int: int) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("payload: wire decode not fully consumed")

    out: List[Tuple[bytes, bytes]] = []
    patched = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if (not patched) and tag.field_number == 4 and tag.wire_type == 2:
            _lr, entry_payload = split_length_delimited_value_raw(value_raw)
            entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
            )
            if consumed2 == len(entry_payload):
                new_entry_chunks: List[Tuple[bytes, bytes]] = []
                entry_patched = False
                for etag_raw, evalue_raw in entry_chunks_raw:
                    etag = parse_tag_raw(etag_raw)
                    if etag.field_number == 50 and etag.wire_type == 2 and (not entry_patched):
                        _lr2, nested_payload = split_length_delimited_value_raw(evalue_raw)
                        nested_chunks_raw, consumed3 = decode_message_to_wire_chunks(
                            data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
                        )
                        if consumed3 == len(nested_payload):
                            nested_patched = False
                            new_nested_chunks: List[Tuple[bytes, bytes]] = []
                            for ntag_raw, nvalue_raw in nested_chunks_raw:
                                ntag = parse_tag_raw(ntag_raw)
                                if ntag.field_number == 502 and ntag.wire_type == 0 and (not nested_patched):
                                    new_nested_chunks.append((ntag_raw, encode_varint(int(template_root_id_int))))
                                    nested_patched = True
                                else:
                                    new_nested_chunks.append((ntag_raw, nvalue_raw))
                            if not nested_patched:
                                new_nested_chunks.append((encode_tag(502, 0), encode_varint(int(template_root_id_int))))
                            new_nested_payload = encode_wire_chunks(new_nested_chunks)
                            new_entry_chunks.append((etag_raw, build_length_delimited_value_raw(new_nested_payload)))
                            entry_patched = True
                            continue
                    new_entry_chunks.append((etag_raw, evalue_raw))

                if entry_patched:
                    out.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
                    patched = True
                    continue
        out.append((tag_raw, value_raw))

    if patched:
        return encode_wire_chunks(out)

    # 没有任何 field_4 entry 可补丁：追加一个最小 entry（只写 field_50.field_502）
    nested_payload = encode_wire_chunks([(encode_tag(502, 0), encode_varint(int(template_root_id_int)))])
    entry_payload = encode_wire_chunks([(encode_tag(50, 2), build_length_delimited_value_raw(nested_payload))])
    out2 = list(out)
    out2.append((encode_tag(4, 2), build_length_delimited_value_raw(entry_payload)))
    return encode_wire_chunks(out2)


def _patch_transform_message_pos_rot_scale(
    transform_bytes: bytes,
    *,
    pos: Tuple[float, float, float],
    rot_deg: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=transform_bytes, start_offset=0, end_offset=len(transform_bytes))
    if consumed != len(transform_bytes):
        raise ValueError("transform: wire decode not fully consumed")

    out: List[Tuple[bytes, bytes]] = []
    wrote_pos = False
    wrote_rot = False
    wrote_scale = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.wire_type == 2 and tag.field_number in (1, 2, 3):
            if tag.field_number == 1 and (not wrote_pos):
                out.append((tag_raw, build_length_delimited_value_raw(_build_vector3_message(pos[0], pos[1], pos[2]))))
                wrote_pos = True
                continue
            if tag.field_number == 2 and (not wrote_rot):
                out.append(
                    (tag_raw, build_length_delimited_value_raw(_build_vector3_message(rot_deg[0], rot_deg[1], rot_deg[2])))
                )
                wrote_rot = True
                continue
            if tag.field_number == 3 and (not wrote_scale):
                out.append(
                    (tag_raw, build_length_delimited_value_raw(_build_vector3_message(scale[0], scale[1], scale[2])))
                )
                wrote_scale = True
                continue
        out.append((tag_raw, value_raw))

    if not wrote_pos:
        out.append((encode_tag(1, 2), build_length_delimited_value_raw(_build_vector3_message(pos[0], pos[1], pos[2]))))
    if not wrote_rot:
        out.append((encode_tag(2, 2), build_length_delimited_value_raw(_build_vector3_message(rot_deg[0], rot_deg[1], rot_deg[2]))))
    if not wrote_scale:
        out.append((encode_tag(3, 2), build_length_delimited_value_raw(_build_vector3_message(scale[0], scale[1], scale[2]))))
    return encode_wire_chunks(out)


def _patch_instance_payload_transform(
    payload_bytes: bytes,
    *,
    pos: Tuple[float, float, float],
    rot_deg: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=payload_bytes, start_offset=0, end_offset=len(payload_bytes))
    if consumed != len(payload_bytes):
        raise ValueError("payload: wire decode not fully consumed")

    out: List[Tuple[bytes, bytes]] = []
    patched = False
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number != 5 or tag.wire_type != 2:
            out.append((tag_raw, value_raw))
            continue
        _lr, entry_payload = split_length_delimited_value_raw(value_raw)
        entry_chunks_raw, consumed2 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed2 != len(entry_payload):
            out.append((tag_raw, value_raw))
            continue
        new_entry_chunks: List[Tuple[bytes, bytes]] = []
        entry_patched = False
        for etag_raw, evalue_raw in entry_chunks_raw:
            etag = parse_tag_raw(etag_raw)
            if etag.field_number == 11 and etag.wire_type == 2 and (not entry_patched):
                _lr2, transform_payload = split_length_delimited_value_raw(evalue_raw)
                new_transform = _patch_transform_message_pos_rot_scale(
                    transform_payload, pos=tuple(pos), rot_deg=tuple(rot_deg), scale=tuple(scale)
                )
                new_entry_chunks.append((etag_raw, build_length_delimited_value_raw(new_transform)))
                entry_patched = True
            else:
                new_entry_chunks.append((etag_raw, evalue_raw))
        if entry_patched and (not patched):
            out.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_entry_chunks))))
            patched = True
        else:
            out.append((tag_raw, value_raw))

    if patched:
        return encode_wire_chunks(out)

    # 没有可补丁的 entry：追加一个最小 transform entry
    transform = _patch_transform_message_pos_rot_scale(b"", pos=tuple(pos), rot_deg=tuple(rot_deg), scale=tuple(scale))
    entry = encode_wire_chunks([(encode_tag(11, 2), build_length_delimited_value_raw(transform))])
    out2 = list(out)
    out2.append((encode_tag(5, 2), build_length_delimited_value_raw(entry)))
    return encode_wire_chunks(out2)


def _patch_graph_unit_id_and_which(unit_bytes: bytes, *, class_int: int, type_int: int, id_int: int, which_int: int) -> bytes:
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
            patched_id_chunks = upsert_varint_field(id_chunks_raw, field_number=2, new_value=int(class_int))
            patched_id_chunks = upsert_varint_field(patched_id_chunks, field_number=3, new_value=int(type_int))
            patched_id_chunks = upsert_varint_field(patched_id_chunks, field_number=4, new_value=int(id_int))
            out.append((tag_raw, build_length_delimited_value_raw(encode_wire_chunks(list(patched_id_chunks)))))
            id_patched = True
            continue
        out.append((tag_raw, value_raw))

    if not id_patched:
        raise ValueError("GraphUnit 缺少 id(field_1)")

    patched2 = upsert_varint_field(out, field_number=5, new_value=int(which_int))
    return encode_wire_chunks(list(patched2))


def _patch_graph_unit_name(unit_bytes: bytes, *, name: str) -> bytes:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")

    out: List[Tuple[bytes, bytes]] = []
    patched = False
    encoded = str(name).encode("utf-8")
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if (not patched) and tag.field_number == 3 and tag.wire_type == 2:
            out.append((tag_raw, build_length_delimited_value_raw(encoded)))
            patched = True
            continue
        out.append((tag_raw, value_raw))
    if not patched:
        out.append((encode_tag(3, 2), build_length_delimited_value_raw(encoded)))
    return encode_wire_chunks(out)


def _patch_instance_unit(
    instance_template_unit_bytes: bytes,
    *,
    instance_id_int: int,
    name: str,
    template_root_id_int: int,
    pos: Tuple[float, float, float],
    rot_deg: Tuple[float, float, float],
    scale: Tuple[float, float, float],
) -> bytes:
    # 1) id + which
    out = _patch_graph_unit_id_and_which(
        instance_template_unit_bytes, class_int=1, type_int=14, id_int=int(instance_id_int), which_int=28
    )
    # 2) name
    out = _patch_graph_unit_name(out, name=str(name))

    # 3) wrapper.payload patch
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=out, start_offset=0, end_offset=len(out))
    if consumed != len(out):
        raise ValueError("instance unit: wire decode not fully consumed")

    wrapper_bytes: Optional[bytes] = None
    wrapper_index: Optional[int] = None
    for i, (tag_raw, value_raw) in enumerate(chunks_raw):
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 21 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            wrapper_bytes = bytes(payload)
            wrapper_index = int(i)
            break

    if wrapper_bytes is None or wrapper_index is None:
        raise ValueError("instance unit: 缺少 wrapper(field_21)，无法补丁 payload（请提供真源 instance 模板）")

    wrapper_chunks_raw, consumed2 = decode_message_to_wire_chunks(
        data_bytes=wrapper_bytes, start_offset=0, end_offset=len(wrapper_bytes)
    )
    if consumed2 != len(wrapper_bytes):
        raise ValueError("wrapper: wire decode not fully consumed")

    new_wrapper_chunks: List[Tuple[bytes, bytes]] = []
    payload_patched = False
    for wtag_raw, wvalue_raw in wrapper_chunks_raw:
        wtag = parse_tag_raw(wtag_raw)
        if wtag.field_number == 1 and wtag.wire_type == 2 and (not payload_patched):
            _lr, payload_bytes = split_length_delimited_value_raw(wvalue_raw)
            new_payload = _patch_instance_payload_template_root_id(payload_bytes, template_root_id_int=int(template_root_id_int))
            new_payload = _patch_instance_payload_transform(new_payload, pos=tuple(pos), rot_deg=tuple(rot_deg), scale=tuple(scale))
            new_wrapper_chunks.append((wtag_raw, build_length_delimited_value_raw(new_payload)))
            payload_patched = True
        else:
            new_wrapper_chunks.append((wtag_raw, wvalue_raw))
    if not payload_patched:
        new_payload = _patch_instance_payload_template_root_id(b"", template_root_id_int=int(template_root_id_int))
        new_payload = _patch_instance_payload_transform(new_payload, pos=tuple(pos), rot_deg=tuple(rot_deg), scale=tuple(scale))
        new_wrapper_chunks.append((encode_tag(1, 2), build_length_delimited_value_raw(new_payload)))

    new_wrapper_bytes = encode_wire_chunks(new_wrapper_chunks)

    new_unit_chunks: List[Tuple[bytes, bytes]] = []
    for i, (tag_raw, value_raw) in enumerate(chunks_raw):
        if i == int(wrapper_index):
            new_unit_chunks.append((tag_raw, build_length_delimited_value_raw(new_wrapper_bytes)))
        else:
            new_unit_chunks.append((tag_raw, value_raw))
    return encode_wire_chunks(new_unit_chunks)


def _alloc_ids(used: Set[int], *, start_hint: int, count: int) -> List[int]:
    if count <= 0:
        return []
    out: List[int] = []
    cursor = int(start_hint)
    while len(out) < int(count):
        while cursor in used:
            cursor += 1
        out.append(int(cursor))
        used.add(int(cursor))
        cursor += 1
    return out


def _extract_unit_name(unit_bytes: bytes) -> str:
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=unit_bytes, start_offset=0, end_offset=len(unit_bytes))
    if consumed != len(unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    for tag_raw, value_raw in chunks_raw:
        tag = parse_tag_raw(tag_raw)
        if tag.field_number == 3 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(value_raw)
            return payload.decode("utf-8", errors="replace")
    return ""


def convert_component_entity_bundle_gia_wire(
    *,
    input_gia_path: Path,
    output_gia_path: Path,
    check_header: bool,
    mode: str,
    keep_file_path: bool,
    file_path_override: str,
    keep_unreferenced_templates: bool,
    instance_template_gia_path: Optional[Path],
    template_name_contains: str,
    drop_existing_instances: bool,
    pos_mode: str,
    grid_step: Tuple[float, float, float],
    start_pos: Tuple[float, float, float],
    default_rot_deg: Tuple[float, float, float],
    default_scale: Tuple[float, float, float],
) -> Dict[str, Any]:
    """
    转换 “元件模板+实体摆放” `.gia` bundle：
    - mode=component_to_entity：为每个 template 生成一个 instance，并写入 Root.field_2；保留 templates。
    - mode=entity_to_component：清空 Root.field_2，并按引用裁剪 templates（可选保留未引用模板）。
    """
    input_gia_path = Path(input_gia_path).resolve()
    if check_header:
        validate_gia_container_file(input_gia_path)

    m = str(mode or "").strip().lower()
    if m not in {"component_to_entity", "entity_to_component"}:
        raise ValueError(f"invalid mode: {mode!r}")

    proto_bytes = unwrap_gia_container(input_gia_path, check_header=False)
    root_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=proto_bytes, start_offset=0, end_offset=len(proto_bytes))
    if consumed != len(proto_bytes):
        raise ValueError("root wire decode not fully consumed")

    root_parsed = [(parse_tag_raw(t), t, v) for t, v in root_chunks_raw]
    base_file_path_text = ""
    for tag, _t, v in root_parsed:
        if tag.field_number == 3 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(v)
            base_file_path_text = payload.decode("utf-8", errors="replace")
            break

    templates_units: List[bytes] = []
    instances_units: List[bytes] = []
    used_ids: Set[int] = set()
    for tag, _t, v in root_parsed:
        if tag.field_number == 1 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(v)
            b = bytes(payload)
            templates_units.append(b)
            used_ids.add(_parse_unit_id(b).id_int)
        elif tag.field_number == 2 and tag.wire_type == 2:
            _lr, payload = split_length_delimited_value_raw(v)
            b = bytes(payload)
            instances_units.append(b)
            used_ids.add(_parse_unit_id(b).id_int)

    templates_only = [u for u in templates_units if _is_template_unit(u)]
    instances_only = [u for u in instances_units if _is_instance_unit(u)]

    if m == "entity_to_component":
        referenced: Set[int] = set()
        for inst in instances_only:
            payload_bytes = _extract_instance_payload_bytes(inst)
            tid = _extract_template_root_id_from_instance_payload(payload_bytes)
            if isinstance(tid, int):
                referenced.add(int(tid))
        if not referenced:
            # 允许空引用：退化为“清空 instances”，templates 保持不变（或保持 templates_only?）
            referenced = set()

        if bool(keep_unreferenced_templates):
            new_templates = list(templates_units)
        else:
            new_templates = [u for u in templates_units if (_parse_unit_id(u).id_int in referenced)]
        new_instances: List[bytes] = []

        center_policy = ""
        instance_template_used = False

    else:
        # component_to_entity
        if not templates_only:
            raise ValueError("未找到任何 template GraphUnit（Root.field_1 中 class=1,type=1,which=1）")

        name_contains = str(template_name_contains or "").strip()
        if name_contains != "":
            templates_only = [t for t in templates_only if (name_contains in _extract_unit_name(t))]
        if not templates_only:
            raise ValueError(f"component_to_entity: 过滤后未找到任何模板（template_name_contains={name_contains!r}）")

        instance_template_unit: Optional[bytes] = None
        if instances_only:
            instance_template_unit = bytes(instances_only[0])
        else:
            if instance_template_gia_path is None:
                raise ValueError("输入内无可克隆的 instance，请提供 --instance-template-gia（真源含实例的 bundle.gia）")
            sample_path = Path(instance_template_gia_path).resolve()
            if check_header:
                validate_gia_container_file(sample_path)
            sample_proto = unwrap_gia_container(sample_path, check_header=False)
            sample_chunks_raw, consumed2 = decode_message_to_wire_chunks(
                data_bytes=sample_proto, start_offset=0, end_offset=len(sample_proto)
            )
            if consumed2 != len(sample_proto):
                raise ValueError("sample root wire decode not fully consumed")
            for st, sv in sample_chunks_raw:
                stag = parse_tag_raw(st)
                if stag.field_number == 2 and stag.wire_type == 2:
                    _lr, payload = split_length_delimited_value_raw(sv)
                    candidate = bytes(payload)
                    if _is_instance_unit(candidate):
                        instance_template_unit = candidate
                        break
            if instance_template_unit is None:
                raise ValueError("instance_template_gia 中未找到可用的 instance(GraphUnit class=1,type=14,which=28)")

        # decide positions
        pm = str(pos_mode or "").strip().lower()
        if pm not in {"origin", "grid"}:
            raise ValueError(f"invalid pos_mode: {pos_mode!r}")

        start_x, start_y, start_z = float(start_pos[0]), float(start_pos[1]), float(start_pos[2])
        step_x, step_y, step_z = float(grid_step[0]), float(grid_step[1]), float(grid_step[2])

        # allocate instance ids
        # choose a start hint close to existing max to reduce collision with editor internal ids
        max_id = max(used_ids) if used_ids else 1077936128
        new_ids = _alloc_ids(used_ids, start_hint=int(max_id + 1), count=len(templates_only))

        new_instances = [] if bool(drop_existing_instances) else list(instances_units)
        for idx, (tpl, new_iid) in enumerate(zip(templates_only, new_ids, strict=True)):
            tpl_id = _parse_unit_id(tpl).id_int
            tpl_name = _extract_unit_name(tpl).strip() or f"template_{tpl_id}"
            if pm == "origin":
                pos = (start_x, start_y, start_z)
            else:
                # simple 1D grid along x by default; keep y/z steps if user sets
                pos = (start_x + step_x * float(idx), start_y + step_y * float(idx), start_z + step_z * float(idx))

            inst_bytes = _patch_instance_unit(
                bytes(instance_template_unit),
                instance_id_int=int(new_iid),
                name=str(tpl_name),
                template_root_id_int=int(tpl_id),
                pos=tuple(pos),
                rot_deg=tuple(default_rot_deg),
                scale=tuple(default_scale),
            )
            new_instances.append(bytes(inst_bytes))

        new_templates = list(templates_units)
        center_policy = ""
        instance_template_used = True

    # filePath
    output_gia_path = Path(output_gia_path).resolve()
    output_name = output_gia_path.name
    file_path_text = str(file_path_override or "").strip()
    if file_path_text != "":
        new_file_path = file_path_text
    elif bool(keep_file_path):
        new_file_path = base_file_path_text
    else:
        new_file_path = _derive_file_path_from_base(base_file_path=base_file_path_text, output_file_name=output_name)

    new_file_path_value_raw = build_length_delimited_value_raw(new_file_path.encode("utf-8"))

    # rebuild root preserving unknown fields
    out_root_chunks: List[Tuple[bytes, bytes]] = []
    wrote_templates = False
    wrote_instances = False
    wrote_file_path = False
    for tag, tag_raw, value_raw in root_parsed:
        if tag.field_number == 1 and tag.wire_type == 2:
            if not wrote_templates:
                for u in list(new_templates):
                    out_root_chunks.append((encode_tag(1, 2), build_length_delimited_value_raw(bytes(u))))
                wrote_templates = True
            continue
        if tag.field_number == 2 and tag.wire_type == 2:
            if not wrote_instances:
                for u in list(new_instances):
                    out_root_chunks.append((encode_tag(2, 2), build_length_delimited_value_raw(bytes(u))))
                wrote_instances = True
            continue
        if tag.field_number == 3 and tag.wire_type == 2 and (not wrote_file_path):
            out_root_chunks.append((tag_raw, new_file_path_value_raw))
            wrote_file_path = True
            continue
        out_root_chunks.append((tag_raw, value_raw))

    if not wrote_templates:
        for u in list(new_templates):
            out_root_chunks.append((encode_tag(1, 2), build_length_delimited_value_raw(bytes(u))))
    if not wrote_instances:
        for u in list(new_instances):
            out_root_chunks.append((encode_tag(2, 2), build_length_delimited_value_raw(bytes(u))))
    if not wrote_file_path:
        out_root_chunks.append((encode_tag(3, 2), new_file_path_value_raw))

    out_proto = encode_wire_chunks(out_root_chunks)
    out_bytes = wrap_gia_container(out_proto)
    output_gia_path.parent.mkdir(parents=True, exist_ok=True)
    output_gia_path.write_bytes(out_bytes)

    return {
        "input_gia_file": str(input_gia_path),
        "output_gia_file": str(output_gia_path),
        "mode": str(m),
        "templates_in": int(len(templates_units)),
        "instances_in": int(len(instances_units)),
        "templates_out": int(len(new_templates)),
        "instances_out": int(len(new_instances)),
        "keep_unreferenced_templates": bool(keep_unreferenced_templates),
        "instance_template_used": bool(instance_template_used),
        "template_name_contains": str(template_name_contains or "").strip(),
        "drop_existing_instances": bool(drop_existing_instances),
        "pos_mode": str(pos_mode),
        "file_path": str(new_file_path),
        "proto_size": int(len(out_proto)),
    }


__all__ = ["convert_component_entity_bundle_gia_wire"]

