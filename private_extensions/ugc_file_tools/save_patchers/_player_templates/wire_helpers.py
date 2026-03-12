from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ...gil_dump_codec.protobuf_like import (  # wire-level, lossless for untouched bytes
    decode_message_to_wire_chunks as _decode_wire_chunks,
    decode_varint as _decode_varint,
    encode_tag as _encode_tag,
    encode_varint as _encode_varint,
    encode_wire_chunks as _encode_wire_chunks,
)
from ...wire.patch import parse_tag_raw as _parse_tag_raw, split_length_delimited_value_raw as _split_ld_value_raw

from ..gil_codec import encode_message
from .common import (
    GROUP1_ID,
    GROUP1_INDEX,
    GROUP_ITEM_BOX_KEY,
    GROUP_ITEM_ID_KEY,
    GROUP_ITEM_INDEX_KEY,
    GROUP_ITEM_VAR_LIST_KEY,
    META_ITEM_ID_NAME,
    META_ITEM_ID_PLAYERS,
)

WIRE_TYPE_VARINT = 0
WIRE_TYPE_LENGTH_DELIMITED = 2

ROOT5_META_LIST_FIELD_NUMBER = 5
ROOT5_REF_BOX_FIELD_NUMBER = 2
REF_ID_FIELD_NUMBER = 1

META_ITEM_ID_FIELD_NUMBER = 1
META_NAME_BOX_FIELD_NUMBER = 11
META_NAME_TEXT_FIELD_NUMBER = 1

META_PLAYERS_BOX_FIELD_NUMBER = 12
META_PLAYERS_BOX_REQUIRED_FIELD5_NUMBER = 5
META_PLAYERS_BOX_REQUIRED_FIELD6_NUMBER = 6

GROUP_ITEM_ID_FIELD_NUMBER = 1
GROUP_ITEM_INDEX_FIELD_NUMBER = 2

SECTION_ENTRY_FIELD_NUMBER = 1


def _read_single_varint_field_from_message_bytes(msg_bytes: bytes, *, field_number: int) -> int | None:
    """从 message bytes 中读取指定 varint 字段（出现多次则报错）。"""
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(msg_bytes), start_offset=0, end_offset=len(msg_bytes))
    if int(consumed) != len(msg_bytes):
        raise ValueError("message bytes did not consume all bytes")
    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(field_number) or int(tag.wire_type) != WIRE_TYPE_VARINT:
            continue
        v, next_offset, ok = _decode_varint(bytes(value_raw), 0, len(value_raw))
        if not ok or int(next_offset) != len(value_raw):
            raise ValueError("invalid varint field encoding")
        return int(v)
    return None


def _read_single_length_delimited_payload_from_message_bytes(msg_bytes: bytes, *, field_number: int) -> bytes | None:
    """从 message bytes 中读取指定 length-delimited 字段的 payload bytes（出现多次则报错）。"""
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(msg_bytes), start_offset=0, end_offset=len(msg_bytes))
    if int(consumed) != len(msg_bytes):
        raise ValueError("message bytes did not consume all bytes")
    found: bytes | None = None
    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(field_number):
            continue
        if int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            raise ValueError(f"expected wire_type=2 for field {int(field_number)}, got {int(tag.wire_type)}")
        _len_raw, payload = _split_ld_value_raw(value_raw)
        if found is not None:
            raise ValueError(f"field {int(field_number)} occurs multiple times (unexpected)")
        found = bytes(payload)
    return found


def _extract_template_name_from_root5_entry_bytes(entry_bytes: bytes) -> str:
    """
    root5 wrapper entry 的名字来自 meta list（field 5）：
    - meta_item(field1==1) -> field11 message -> field1 utf8 string
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("root5 entry bytes did not consume all bytes")

    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != ROOT5_META_LIST_FIELD_NUMBER or int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _len_raw, meta_payload = _split_ld_value_raw(value_raw)
        if _read_single_varint_field_from_message_bytes(meta_payload, field_number=META_ITEM_ID_FIELD_NUMBER) != META_ITEM_ID_NAME:
            continue
        name_box = _read_single_length_delimited_payload_from_message_bytes(meta_payload, field_number=META_NAME_BOX_FIELD_NUMBER)
        if name_box is None:
            continue
        raw_name = _read_single_length_delimited_payload_from_message_bytes(name_box, field_number=META_NAME_TEXT_FIELD_NUMBER)
        if raw_name is None:
            continue
        name = bytes(raw_name).decode("utf-8")
        if name.strip():
            return str(name).strip()
    return ""


def _extract_root5_ref_root4_entry_id(entry_bytes: bytes) -> int | None:
    """从 root5 wrapper entry bytes 中提取引用的 root4_entry_id。"""
    ref_box = _read_single_length_delimited_payload_from_message_bytes(entry_bytes, field_number=ROOT5_REF_BOX_FIELD_NUMBER)
    if ref_box is None:
        return None
    return _read_single_varint_field_from_message_bytes(ref_box, field_number=REF_ID_FIELD_NUMBER)


def _is_player_template_like_root5_entry_bytes(entry_bytes: bytes) -> bool:
    """
    依据真源样本的可解释特征（与结构化版本对齐，但不解码为 dict）：
    - meta list（field 5）中存在 meta_item(field1==3) 且其 field12 message 内至少包含 field5/field6(varint)
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("root5 entry bytes did not consume all bytes")

    for tag_raw, value_raw in chunks:
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != ROOT5_META_LIST_FIELD_NUMBER or int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _len_raw, meta_payload = _split_ld_value_raw(value_raw)
        if (
            _read_single_varint_field_from_message_bytes(meta_payload, field_number=META_ITEM_ID_FIELD_NUMBER)
            != META_ITEM_ID_PLAYERS
        ):
            continue
        box12 = _read_single_length_delimited_payload_from_message_bytes(meta_payload, field_number=META_PLAYERS_BOX_FIELD_NUMBER)
        if box12 is None:
            continue
        if _read_single_varint_field_from_message_bytes(box12, field_number=META_PLAYERS_BOX_REQUIRED_FIELD5_NUMBER) is None:
            continue
        if _read_single_varint_field_from_message_bytes(box12, field_number=META_PLAYERS_BOX_REQUIRED_FIELD6_NUMBER) is None:
            continue
        return True
    return False


def _is_group1_container_item_bytes(group_item_bytes: bytes) -> bool:
    """判断某个 group item bytes 是否为 group1(1/1) 容器。"""
    gid = _read_single_varint_field_from_message_bytes(group_item_bytes, field_number=GROUP_ITEM_ID_FIELD_NUMBER)
    gidx = _read_single_varint_field_from_message_bytes(group_item_bytes, field_number=GROUP_ITEM_INDEX_FIELD_NUMBER)
    return int(gid or 0) == int(GROUP1_ID) and int(gidx or 0) == int(GROUP1_INDEX)


def _build_group1_container_item_bytes(*, variables: List[Tuple[str, int, Any]]) -> bytes:
    """
    构造 group1(1/1) 变量容器 item 的 message bytes：
    - item: {1:1, 2:1, 11:{1:[var_def_item...] } }

    注意：这里用本目录的 `gil_codec.encode_message` 构造该小段 message，
    因为它能直接编码 bytes（empty bytes）并且该结构不涉及 fixed32/fixed64。
    """
    from .structured_variables import _build_player_template_custom_variable_def_item

    var_defs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for name, type_code, default_value in list(variables or []):
        nm = str(name or "").strip()
        if nm == "":
            raise ValueError("variables 中存在空 variable_name")
        if nm in seen:
            raise ValueError(f"variables 存在重复 variable_name：{nm!r}")
        seen.add(nm)
        var_defs.append(
            _build_player_template_custom_variable_def_item(name=nm, type_code=int(type_code), default_value=default_value)
        )
    if not var_defs:
        raise ValueError("variables 不能为空（至少需要 1 个变量定义）")
    item = {
        GROUP_ITEM_ID_KEY: GROUP1_ID,
        GROUP_ITEM_INDEX_KEY: GROUP1_INDEX,
        GROUP_ITEM_BOX_KEY: {GROUP_ITEM_VAR_LIST_KEY: [dict(x) for x in var_defs]},
    }
    return bytes(encode_message(dict(item)))


def _patch_group_list_field_in_entry_bytes(
    entry_bytes: bytes,
    *,
    group_field_number: int,
    new_group1_item_payload_bytes: bytes,
) -> bytes:
    """
    wire-level patch：在 entry message bytes 中替换/插入 group1 容器（repeated length-delimited field）。
    - 保留其它字段的 tag/value 原始字节不变
    - 保留其它 group item（非 group1）原始字节不变
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(entry_bytes), start_offset=0, end_offset=len(entry_bytes))
    if int(consumed) != len(entry_bytes):
        raise ValueError("entry bytes did not consume all bytes")

    out: List[Tuple[bytes, bytes]] = []
    group1_insert_at: int | None = None
    group1_tag_raw: bytes | None = None

    for tag_raw, value_raw in list(chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != int(group_field_number):
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue
        if int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            raise ValueError(
                f"group field must be length-delimited: field={int(group_field_number)} got wire_type={int(tag.wire_type)}"
            )
        _len_raw, payload = _split_ld_value_raw(value_raw)
        if _is_group1_container_item_bytes(payload):
            if group1_insert_at is None:
                group1_insert_at = int(len(out))
                group1_tag_raw = bytes(tag_raw)
            # drop old group1 container
            continue
        # keep other groups untouched
        out.append((bytes(tag_raw), bytes(value_raw)))

    if group1_insert_at is None:
        # missing -> insert before first field_number greater than group_field_number (keep near-sorted)
        group1_insert_at = int(len(out))
        for i, (t_raw, _v_raw) in enumerate(list(out)):
            t = _parse_tag_raw(t_raw)
            if int(t.field_number) > int(group_field_number):
                group1_insert_at = int(i)
                break
        group1_tag_raw = bytes(_encode_tag(int(group_field_number), WIRE_TYPE_LENGTH_DELIMITED))

    if group1_tag_raw is None:
        raise RuntimeError("internal error: group1_tag_raw is None")

    new_value_raw = bytes(_encode_varint(int(len(new_group1_item_payload_bytes)))) + bytes(new_group1_item_payload_bytes)
    out.insert(int(group1_insert_at), (bytes(group1_tag_raw), bytes(new_value_raw)))
    return bytes(_encode_wire_chunks(list(out)))


def _patch_section_entries_field1_by_predicate(
    section_bytes: bytes,
    *,
    should_patch_entry: Any,
    patch_entry_bytes: Any,
) -> Tuple[bytes, int]:
    """
    对 section message bytes 中 field_1(repeated entry bytes) 做按 predicate 的定点替换。
    返回：(new_section_bytes, patched_count)
    """
    chunks, consumed = _decode_wire_chunks(data_bytes=bytes(section_bytes), start_offset=0, end_offset=len(section_bytes))
    if int(consumed) != len(section_bytes):
        raise ValueError("section bytes did not consume all bytes")

    out: List[Tuple[bytes, bytes]] = []
    patched = 0
    for tag_raw, value_raw in list(chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != SECTION_ENTRY_FIELD_NUMBER or int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue

        _len_raw, payload = _split_ld_value_raw(value_raw)
        if not bool(should_patch_entry(payload)):
            out.append((bytes(tag_raw), bytes(value_raw)))
            continue

        new_payload = bytes(patch_entry_bytes(payload))
        new_value_raw = bytes(_encode_varint(len(new_payload))) + new_payload
        out.append((bytes(tag_raw), bytes(new_value_raw)))
        patched += 1

    return bytes(_encode_wire_chunks(list(out))), int(patched)

