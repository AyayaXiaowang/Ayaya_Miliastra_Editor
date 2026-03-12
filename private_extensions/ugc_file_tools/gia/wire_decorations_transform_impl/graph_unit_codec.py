from __future__ import annotations

"""GraphUnit wire-level extract/patch helpers for decorations transform."""

from typing import Dict, List, Optional, Sequence, Tuple

from ugc_file_tools.gia.wire_decorations_transform_impl.constants import (
    COMPONENT_ENTRY_FIELD_KEY,
    COMPONENT_ENTRY_FIELD_TRANSFORM,
    COMPONENT_ENTRY_KEY_TRANSFORM,
    COMPONENT_TREE_FIELD_ENTRIES,
    COMPONENT_TREE_FIELD_ROOT,
    GRAPH_UNIT_FIELD_COMPONENT_TREE,
    GRAPH_UNIT_FIELD_ID,
    GRAPH_UNIT_FIELD_NAME,
    GRAPH_UNIT_FIELD_RELATED_IDS,
    GRAPH_UNIT_ID_FIELD_UNIT_ID_INT,
    PARENT_GRAPH_ENTRY_FIELD_BYTES_OR_MESSAGE,
    PARENT_GRAPH_ENTRY_KEY_ACCESSORY_BIND,
    PARENT_GRAPH_ENTRY_KEY_FIELD,
    PARENT_GRAPH_PACKED_IDS_FIELD_BYTES,
    RELATED_ID_FIELD_UNIT_ID_INT,
    WIRE_TYPE_LENGTH_DELIMITED,
    WIRE_TYPE_VARINT,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.transform_codec import (
    extract_trs_from_transform_message,
    find_first_transform_pos_in_message,
    find_first_transform_trs_in_message,
    patch_first_transform_pos_in_message,
    patch_transform_pos_only,
)
from ugc_file_tools.gia.wire_decorations_transform_impl.wire_utils import (
    WireChunk,
    decode_varint_value,
    is_valid_message_payload,
    pack_varints,
    parse_chunks,
    patch_first_varint_field,
)
from ugc_file_tools.wire.codec import decode_message_to_wire_chunks, encode_wire_chunks
from ugc_file_tools.wire.patch import build_length_delimited_value_raw, split_length_delimited_value_raw


def extract_graph_unit_id(graph_unit_bytes: bytes) -> int:
    """Extract unit_id_int from GraphUnit.id(field_1.message.field_4)."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number != GRAPH_UNIT_FIELD_ID or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, id_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(id_payload):
            continue
        id_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=id_payload, start_offset=0, end_offset=len(id_payload))
        if consumed2 != len(id_payload):
            raise ValueError("GraphUnit.id wire decode not fully consumed")
        id_parsed = parse_chunks(id_chunks_raw)
        for ic in id_parsed:
            if ic.field_number == GRAPH_UNIT_ID_FIELD_UNIT_ID_INT and ic.wire_type == WIRE_TYPE_VARINT:
                return decode_varint_value(ic.value_raw)
    raise ValueError("GraphUnit: 无法提取 id(field_1.field_4)")


def extract_graph_unit_name(graph_unit_bytes: bytes) -> str:
    """Extract GraphUnit.name(field_3) as UTF-8 text."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number == GRAPH_UNIT_FIELD_NAME and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, payload = split_length_delimited_value_raw(c.value_raw)
            return payload.decode("utf-8", errors="replace")
    return ""


def _find_component_tree_payload(graph_unit_bytes: bytes) -> Optional[bytes]:
    """Locate GraphUnit.field_12 payload bytes when it looks like a message."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number == GRAPH_UNIT_FIELD_COMPONENT_TREE and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(p):
                return bytes(p)
            return None
    return None


def _find_component_root_payload(component_tree_bytes: bytes) -> Optional[bytes]:
    """Locate component_tree.field_1 payload bytes when it looks like a message."""
    chunks_raw, consumed = decode_message_to_wire_chunks(
        data_bytes=component_tree_bytes, start_offset=0, end_offset=len(component_tree_bytes)
    )
    if consumed != len(component_tree_bytes):
        raise ValueError("GraphUnit.field_12 wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    for c in parsed:
        if c.field_number == COMPONENT_TREE_FIELD_ROOT and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(p):
                return bytes(p)
            return None
    return None


def _iter_component_entries(component_root_bytes: bytes) -> List[WireChunk]:
    """Return parsed repeated entries under component_root.field_6 when they look like messages."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=component_root_bytes, start_offset=0, end_offset=len(component_root_bytes))
    if consumed != len(component_root_bytes):
        raise ValueError("GraphUnit.field_12.field_1 wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    return [c for c in parsed if c.field_number == COMPONENT_TREE_FIELD_ENTRIES and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED]


def _pick_transform_entry_payload(entries: Sequence[WireChunk]) -> Optional[bytes]:
    """Pick the best entry payload containing a Transform message using key==1 preference."""
    chosen_transform_payload: Optional[bytes] = None
    fallback_transform_payload: Optional[bytes] = None
    for c in list(entries):
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed != len(entry_payload):
            continue
        entry_parsed = parse_chunks(entry_chunks_raw)

        entry_key: Optional[int] = None
        transform_payload: Optional[bytes] = None
        for ec in entry_parsed:
            if ec.field_number == COMPONENT_ENTRY_FIELD_KEY and ec.wire_type == WIRE_TYPE_VARINT and entry_key is None:
                entry_key = decode_varint_value(ec.value_raw)
            if ec.field_number == COMPONENT_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED and transform_payload is None:
                _lr2, p2 = split_length_delimited_value_raw(ec.value_raw)
                transform_payload = bytes(p2)
        if transform_payload is None or (not is_valid_message_payload(transform_payload)):
            continue
        if fallback_transform_payload is None:
            fallback_transform_payload = bytes(transform_payload)
        if entry_key == COMPONENT_ENTRY_KEY_TRANSFORM:
            chosen_transform_payload = bytes(transform_payload)
            break
    return chosen_transform_payload or fallback_transform_payload


def try_extract_transform_pos_from_component_tree(graph_unit_bytes: bytes) -> Optional[Tuple[float, float, float]]:
    """Try extracting Transform.position from GraphUnit via the stable component-tree path."""
    c12_payload = _find_component_tree_payload(graph_unit_bytes)
    if c12_payload is None:
        return None
    c1_payload = _find_component_root_payload(c12_payload)
    if c1_payload is None:
        return None
    entries = _iter_component_entries(c1_payload)
    if not entries:
        return None
    transform_bytes = _pick_transform_entry_payload(entries)
    if transform_bytes is None:
        return None
    pos, _rot, _scale = extract_trs_from_transform_message(bytes(transform_bytes))
    return tuple(pos)


def try_extract_transform_trs_from_component_tree(
    graph_unit_bytes: bytes,
) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]]:
    """Try extracting Transform(TRS) from GraphUnit via the stable component-tree path."""
    c12_payload = _find_component_tree_payload(graph_unit_bytes)
    if c12_payload is None:
        return None
    c1_payload = _find_component_root_payload(c12_payload)
    if c1_payload is None:
        return None
    entries = _iter_component_entries(c1_payload)
    if not entries:
        return None
    transform_bytes = _pick_transform_entry_payload(entries)
    if transform_bytes is None:
        return None
    return extract_trs_from_transform_message(bytes(transform_bytes))


def _locate_component_tree_indices(
    graph_unit_bytes: bytes,
) -> Optional[Tuple[List[WireChunk], int, List[WireChunk], int, List[WireChunk], int]]:
    """Locate component-tree indices needed for in-place transform position patching."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed_unit = parse_chunks(chunks_raw)

    idx_12: Optional[int] = None
    c12_payload: Optional[bytes] = None
    for i, c in enumerate(parsed_unit):
        if c.field_number == GRAPH_UNIT_FIELD_COMPONENT_TREE and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(p):
                idx_12 = int(i)
                c12_payload = bytes(p)
            break
    if idx_12 is None or c12_payload is None:
        return None

    c12_chunks_raw, consumed2 = decode_message_to_wire_chunks(data_bytes=c12_payload, start_offset=0, end_offset=len(c12_payload))
    if consumed2 != len(c12_payload):
        raise ValueError("GraphUnit.field_12 wire decode not fully consumed")
    parsed_c12 = parse_chunks(c12_chunks_raw)

    idx_c1: Optional[int] = None
    c1_payload: Optional[bytes] = None
    for i, c in enumerate(parsed_c12):
        if c.field_number == COMPONENT_TREE_FIELD_ROOT and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            _lr, p = split_length_delimited_value_raw(c.value_raw)
            if is_valid_message_payload(p):
                idx_c1 = int(i)
                c1_payload = bytes(p)
            break
    if idx_c1 is None or c1_payload is None:
        return None

    c1_chunks_raw, consumed3 = decode_message_to_wire_chunks(data_bytes=c1_payload, start_offset=0, end_offset=len(c1_payload))
    if consumed3 != len(c1_payload):
        raise ValueError("GraphUnit.field_12.field_1 wire decode not fully consumed")
    parsed_c1 = parse_chunks(c1_chunks_raw)

    entry_chunks = [c for c in parsed_c1 if c.field_number == COMPONENT_TREE_FIELD_ENTRIES and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED]
    if not entry_chunks:
        return None

    chosen_entry_index: Optional[int] = None
    for i, c in enumerate(parsed_c1):
        if c.field_number != COMPONENT_TREE_FIELD_ENTRIES or c.wire_type != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        if not is_valid_message_payload(entry_payload):
            continue
        entry_chunks_raw, consumed4 = decode_message_to_wire_chunks(
            data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload)
        )
        if consumed4 != len(entry_payload):
            continue
        entry_parsed = parse_chunks(entry_chunks_raw)
        entry_key: Optional[int] = None
        has_transform = False
        for ec in entry_parsed:
            if ec.field_number == COMPONENT_ENTRY_FIELD_KEY and ec.wire_type == WIRE_TYPE_VARINT and entry_key is None:
                entry_key = decode_varint_value(ec.value_raw)
            if ec.field_number == COMPONENT_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
                _lr2, tp = split_length_delimited_value_raw(ec.value_raw)
                if is_valid_message_payload(tp):
                    has_transform = True
        if not has_transform:
            continue
        if chosen_entry_index is None:
            chosen_entry_index = int(i)
        if entry_key == COMPONENT_ENTRY_KEY_TRANSFORM:
            chosen_entry_index = int(i)
            break
    if chosen_entry_index is None:
        return None

    return parsed_unit, int(idx_12), parsed_c12, int(idx_c1), parsed_c1, int(chosen_entry_index)


def _patch_component_tree_entry_transform_pos(entry_payload: bytes, *, new_pos: Tuple[float, float, float]) -> Tuple[bytes, bool]:
    """Patch entry.field_11.transform.field_1 position inside one component entry payload."""
    entry_chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload))
    if consumed != len(entry_payload):
        return entry_payload, False
    entry_parsed = parse_chunks(entry_chunks_raw)
    new_entry_chunks: List[Tuple[bytes, bytes]] = []
    patched_entry = False
    for ec in entry_parsed:
        if ec.field_number == COMPONENT_ENTRY_FIELD_TRANSFORM and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED and not patched_entry:
            _lr2, transform_payload = split_length_delimited_value_raw(ec.value_raw)
            if not is_valid_message_payload(transform_payload):
                new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                continue
            new_transform = patch_transform_pos_only(transform_payload, pos=tuple(new_pos))
            new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(new_transform)))
            patched_entry = True
        else:
            new_entry_chunks.append((ec.tag_raw, ec.value_raw))
    if not patched_entry:
        return entry_payload, False
    return encode_wire_chunks(new_entry_chunks), True


def try_patch_transform_pos_in_component_tree(graph_unit_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> Tuple[Optional[bytes], bool]:
    """Try patching Transform.position inside GraphUnit via the stable component-tree path."""
    located = _locate_component_tree_indices(graph_unit_bytes)
    if located is None:
        return None, False
    parsed_unit, idx_12, parsed_c12, idx_c1, parsed_c1, idx_entry = located

    new_c1_chunks: List[Tuple[bytes, bytes]] = []
    patched = False
    for i, c in enumerate(parsed_c1):
        if i != int(idx_entry):
            new_c1_chunks.append((c.tag_raw, c.value_raw))
            continue
        _lr, entry_payload = split_length_delimited_value_raw(c.value_raw)
        new_entry_payload, ok = _patch_component_tree_entry_transform_pos(entry_payload, new_pos=tuple(new_pos))
        if ok:
            new_c1_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_entry_payload)))
            patched = True
        else:
            new_c1_chunks.append((c.tag_raw, c.value_raw))
    if not patched:
        return None, False

    new_c1_payload = encode_wire_chunks(new_c1_chunks)
    new_c12_chunks: List[Tuple[bytes, bytes]] = []
    for i, c in enumerate(parsed_c12):
        if i == int(idx_c1):
            new_c12_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_c1_payload)))
        else:
            new_c12_chunks.append((c.tag_raw, c.value_raw))
    new_c12_payload = encode_wire_chunks(new_c12_chunks)

    new_unit_chunks: List[Tuple[bytes, bytes]] = []
    for i, c in enumerate(parsed_unit):
        if i == int(idx_12):
            new_unit_chunks.append((c.tag_raw, build_length_delimited_value_raw(new_c12_payload)))
        else:
            new_unit_chunks.append((c.tag_raw, c.value_raw))
    return encode_wire_chunks(new_unit_chunks), True


def extract_graph_unit_pos(graph_unit_bytes: bytes) -> Tuple[float, float, float]:
    """Extract Transform.position from GraphUnit using component-tree path with DFS fallback."""
    pos = try_extract_transform_pos_from_component_tree(graph_unit_bytes)
    if pos is not None:
        return pos
    found = find_first_transform_pos_in_message(graph_unit_bytes)
    if found is None:
        raise ValueError("GraphUnit: 找不到可识别的 Transform.position")
    return found


def extract_graph_unit_trs(
    graph_unit_bytes: bytes,
) -> Tuple[Tuple[float, float, float], Tuple[float, float, float], Tuple[float, float, float]]:
    """Extract Transform(TRS) from GraphUnit using component-tree path with DFS fallback."""
    trs = try_extract_transform_trs_from_component_tree(graph_unit_bytes)
    if trs is not None:
        return trs
    found = find_first_transform_trs_in_message(graph_unit_bytes)
    if found is None:
        raise ValueError("GraphUnit: 找不到可识别的 Transform(TRS)")
    return found


def patch_graph_unit_pos(graph_unit_bytes: bytes, *, new_pos: Tuple[float, float, float]) -> bytes:
    """Patch GraphUnit Transform.position using component-tree path with DFS fallback."""
    patched_bytes, ok = try_patch_transform_pos_in_component_tree(graph_unit_bytes, new_pos=tuple(new_pos))
    if ok and patched_bytes is not None:
        return bytes(patched_bytes)
    patched2, ok2 = patch_first_transform_pos_in_message(graph_unit_bytes, new_pos=tuple(new_pos))
    if not ok2:
        raise ValueError("GraphUnit: 找不到可补丁的 Transform.position")
    return bytes(patched2)


def graph_unit_has_related_ids(graph_unit_bytes: bytes) -> bool:
    """Return True if GraphUnit has relatedIds(field_2) entries."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    return any(c.field_number == GRAPH_UNIT_FIELD_RELATED_IDS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED for c in parsed)


def clear_graph_unit_related_ids(graph_unit_bytes: bytes) -> bytes:
    """Remove all relatedIds(field_2) entries from GraphUnit."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)
    kept = [(c.tag_raw, c.value_raw) for c in parsed if not (c.field_number == GRAPH_UNIT_FIELD_RELATED_IDS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED)]
    return encode_wire_chunks(kept)


def patch_graph_unit_related_ids(graph_unit_bytes: bytes, *, unit_ids: Sequence[int]) -> bytes:
    """Rebuild GraphUnit.relatedIds(field_2) list using the first existing template entry."""
    chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=graph_unit_bytes, start_offset=0, end_offset=len(graph_unit_bytes))
    if consumed != len(graph_unit_bytes):
        raise ValueError("GraphUnit wire decode not fully consumed")
    parsed = parse_chunks(chunks_raw)

    related_template: Optional[WireChunk] = None
    first_related_idx: Optional[int] = None
    for idx, c in enumerate(parsed):
        if c.field_number == GRAPH_UNIT_FIELD_RELATED_IDS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            related_template = c
            first_related_idx = int(idx)
            break
    if related_template is None:
        raise ValueError("GraphUnit: 缺少 relatedIds(field_2) 模板，无法重建")

    insert_at = int(first_related_idx) if first_related_idx is not None else 0
    if first_related_idx is None:
        for idx, c in enumerate(parsed):
            if c.field_number == GRAPH_UNIT_FIELD_ID and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
                insert_at = idx + 1
                break

    insert_pos = 0
    for idx, c in enumerate(parsed):
        if idx >= int(insert_at):
            break
        if c.field_number == GRAPH_UNIT_FIELD_RELATED_IDS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
            continue
        insert_pos += 1

    kept_chunks: List[Tuple[bytes, bytes]] = [
        (c.tag_raw, c.value_raw) for c in parsed if not (c.field_number == GRAPH_UNIT_FIELD_RELATED_IDS and c.wire_type == WIRE_TYPE_LENGTH_DELIMITED)
    ]

    _lr, template_payload = split_length_delimited_value_raw(related_template.value_raw)
    if not is_valid_message_payload(template_payload):
        raise ValueError("relatedIds template payload 不是 message")

    new_related_chunks: List[Tuple[bytes, bytes]] = []
    for uid in list(unit_ids):
        new_payload = patch_first_varint_field(template_payload, field_number=RELATED_ID_FIELD_UNIT_ID_INT, new_value=int(uid))
        new_related_chunks.append((related_template.tag_raw, build_length_delimited_value_raw(new_payload)))

    spliced = kept_chunks[:insert_pos] + new_related_chunks + kept_chunks[insert_pos:]
    return encode_wire_chunks(spliced)


def patch_packed_ids_inside_parent_graph(parent_unit_bytes: bytes, *, packed_ids: bytes) -> bytes:
    """Best-effort patch the packed accessories id list inside a parent graph by structural matching."""

    def try_patch_entry(entry_payload: bytes) -> Tuple[bytes, bool]:
        """Patch one entry payload when it matches key==40 and has field_50 bytes/message."""
        entry_chunks_raw, consumed0 = decode_message_to_wire_chunks(data_bytes=entry_payload, start_offset=0, end_offset=len(entry_payload))
        if consumed0 != len(entry_payload):
            return entry_payload, False
        entry_parsed = parse_chunks(entry_chunks_raw)

        entry_key: Optional[int] = None
        for ec in entry_parsed:
            if ec.field_number == PARENT_GRAPH_ENTRY_KEY_FIELD and ec.wire_type == WIRE_TYPE_VARINT:
                entry_key = decode_varint_value(ec.value_raw)
                break
        if entry_key != PARENT_GRAPH_ENTRY_KEY_ACCESSORY_BIND:
            return entry_payload, False

        new_entry_chunks: List[Tuple[bytes, bytes]] = []
        entry_patched = False
        for ec in entry_parsed:
            if (
                ec.field_number == PARENT_GRAPH_ENTRY_FIELD_BYTES_OR_MESSAGE
                and ec.wire_type == WIRE_TYPE_LENGTH_DELIMITED
                and not entry_patched
            ):
                _lrr, nested_payload = split_length_delimited_value_raw(ec.value_raw)
                if not is_valid_message_payload(nested_payload):
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                    entry_patched = True
                    continue

                nested_chunks_raw, consumed1 = decode_message_to_wire_chunks(
                    data_bytes=nested_payload, start_offset=0, end_offset=len(nested_payload)
                )
                if consumed1 != len(nested_payload):
                    new_entry_chunks.append((ec.tag_raw, ec.value_raw))
                    continue
                nested_parsed = parse_chunks(nested_chunks_raw)

                new_nested_chunks: List[Tuple[bytes, bytes]] = []
                bytes_patched = False
                for nc in nested_parsed:
                    if (
                        nc.field_number == PARENT_GRAPH_PACKED_IDS_FIELD_BYTES
                        and nc.wire_type == WIRE_TYPE_LENGTH_DELIMITED
                        and not bytes_patched
                    ):
                        new_nested_chunks.append((nc.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                        bytes_patched = True
                    else:
                        new_nested_chunks.append((nc.tag_raw, nc.value_raw))

                if bytes_patched:
                    new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(encode_wire_chunks(new_nested_chunks))))
                    entry_patched = True
                    continue

                new_entry_chunks.append((ec.tag_raw, build_length_delimited_value_raw(bytes(packed_ids))))
                entry_patched = True
                continue

            new_entry_chunks.append((ec.tag_raw, ec.value_raw))

        if not entry_patched:
            return entry_payload, False
        return encode_wire_chunks(new_entry_chunks), True

    def patch_message(message_bytes: bytes) -> Tuple[bytes, bool]:
        """Recursively patch the first matching entry in a message bytes tree."""
        chunks_raw, consumed = decode_message_to_wire_chunks(data_bytes=message_bytes, start_offset=0, end_offset=len(message_bytes))
        if consumed != len(message_bytes):
            return message_bytes, False
        parsed = parse_chunks(chunks_raw)

        out: List[Tuple[bytes, bytes]] = []
        patched_any = False

        for c in parsed:
            if c.wire_type == WIRE_TYPE_LENGTH_DELIMITED:
                _lr, payload = split_length_delimited_value_raw(c.value_raw)
                if is_valid_message_payload(payload):
                    new_payload, patched_entry = try_patch_entry(payload)
                    if patched_entry:
                        out.append((c.tag_raw, build_length_delimited_value_raw(new_payload)))
                        patched_any = True
                        continue

                    new_payload2, patched_nested = patch_message(payload)
                    if patched_nested:
                        out.append((c.tag_raw, build_length_delimited_value_raw(new_payload2)))
                        patched_any = True
                        continue

            out.append((c.tag_raw, c.value_raw))

        return encode_wire_chunks(out), patched_any

    new_parent_bytes, patched = patch_message(parent_unit_bytes)
    if not patched:
        return parent_unit_bytes
    return new_parent_bytes


def build_packed_accessory_ids(accessory_unit_ids: Sequence[int]) -> bytes:
    """Build packed varint bytes for accessory unit id list used by parent graphs."""
    return pack_varints([int(x) for x in list(accessory_unit_ids)])


def describe_parent_units(parent_units: Sequence[bytes]) -> List[Dict[str, object]]:
    """Build a lightweight report list for parent units containing id and name."""
    out: List[Dict[str, object]] = []
    for u in list(parent_units):
        out.append({"unit_id_int": int(extract_graph_unit_id(u)), "name": str(extract_graph_unit_name(u))})
    return out

