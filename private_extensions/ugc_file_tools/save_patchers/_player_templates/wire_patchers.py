from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from ...gil_dump_codec.protobuf_like import (
    decode_message_to_wire_chunks as _decode_wire_chunks,
    encode_varint as _encode_varint,
    encode_wire_chunks as _encode_wire_chunks,
)
from ...wire.patch import parse_tag_raw as _parse_tag_raw, split_length_delimited_value_raw as _split_ld_value_raw

from ..gil_codec import build_gil_bytes_from_container, read_gil_container
from .common import ROLE_EDIT_SUFFIX
from .wire_helpers import (
    SECTION_ENTRY_FIELD_NUMBER,
    WIRE_TYPE_LENGTH_DELIMITED,
    _build_group1_container_item_bytes,
    _extract_root5_ref_root4_entry_id,
    _extract_template_name_from_root5_entry_bytes,
    _is_group1_container_item_bytes,
    _is_player_template_like_root5_entry_bytes,
    _patch_group_list_field_in_entry_bytes,
    _patch_section_entries_field1_by_predicate,
    _read_single_varint_field_from_message_bytes,
)

PAYLOAD_ROOT_SECTION4_FIELD_NUMBER = 4
PAYLOAD_ROOT_SECTION5_FIELD_NUMBER = 5

ROOT5_GROUP_LIST_FIELD_NUMBER = 7
ROOT4_GROUP_LIST_FIELD_NUMBER = 8


def _decode_root_chunks_or_raise(payload: bytes) -> List[Tuple[bytes, bytes]]:
    """将 payload_root bytes 解码成 wire chunk 列表。"""
    root_chunks, consumed = _decode_wire_chunks(data_bytes=bytes(payload), start_offset=0, end_offset=len(payload))
    if int(consumed) != len(payload):
        raise ValueError("payload_root did not consume all bytes")
    return list(root_chunks)


def _extract_single_section_payload_or_raise(
    root_chunks: List[Tuple[bytes, bytes]],
    *,
    field_number: int,
) -> Tuple[int, bytes]:
    """从 payload_root 的 wire chunks 中提取唯一的 section payload bytes。"""
    found_payload: bytes | None = None
    found_idx: int | None = None
    for i, (tag_raw, value_raw) in enumerate(list(root_chunks)):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        if int(tag.field_number) != int(field_number):
            continue
        if found_payload is not None:
            raise ValueError(f"payload_root field {int(field_number)} occurs multiple times (unexpected)")
        _len_raw, found_payload = _split_ld_value_raw(value_raw)
        found_idx = int(i)
    if found_payload is None or found_idx is None:
        raise ValueError(f"payload_root missing field {int(field_number)}")
    return int(found_idx), bytes(found_payload)


def _extract_root4_root5_sections_or_raise(payload: bytes) -> Tuple[List[Tuple[bytes, bytes]], int, bytes, int, bytes]:
    """从 payload_root 提取 root4/root5 两个 section 的 payload 与其 chunk 索引。"""
    root_chunks = _decode_root_chunks_or_raise(payload)
    s4_idx, s4_payload = _extract_single_section_payload_or_raise(root_chunks, field_number=PAYLOAD_ROOT_SECTION4_FIELD_NUMBER)
    s5_idx, s5_payload = _extract_single_section_payload_or_raise(root_chunks, field_number=PAYLOAD_ROOT_SECTION5_FIELD_NUMBER)
    return root_chunks, int(s4_idx), bytes(s4_payload), int(s5_idx), bytes(s5_payload)


def _rebuild_payload_root_with_patched_sections(
    root_chunks: List[Tuple[bytes, bytes]],
    *,
    section4_idx: int,
    patched_section4: bytes,
    section5_idx: int,
    patched_section5: bytes,
) -> bytes:
    """仅替换 payload_root 中 field4/field5 的 value_raw 并重建 payload bytes。"""
    new_root_chunks = list(root_chunks)
    tag4_raw, _old4_value_raw = new_root_chunks[int(section4_idx)]
    new_root_chunks[int(section4_idx)] = (
        bytes(tag4_raw),
        bytes(_encode_varint(len(patched_section4))) + bytes(patched_section4),
    )
    tag5_raw, _old5_value_raw = new_root_chunks[int(section5_idx)]
    new_root_chunks[int(section5_idx)] = (
        bytes(tag5_raw),
        bytes(_encode_varint(len(patched_section5))) + bytes(patched_section5),
    )
    return bytes(_encode_wire_chunks(list(new_root_chunks)))


def _find_target_root4_entry_id_or_raise(section5_payload: bytes, *, template_name: str) -> Tuple[int, int]:
    """在 root5 section 中按模板名定位引用到的唯一 root4_entry_id。"""
    s5_chunks, consumed5 = _decode_wire_chunks(
        data_bytes=bytes(section5_payload),
        start_offset=0,
        end_offset=len(section5_payload),
    )
    if int(consumed5) != len(section5_payload):
        raise ValueError("section5 did not consume all bytes")

    matched = 0
    ref_ids: List[int] = []
    for tag_raw, value_raw in list(s5_chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != SECTION_ENTRY_FIELD_NUMBER or int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _len_raw, entry_payload = _split_ld_value_raw(value_raw)
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            continue
        name = _extract_template_name_from_root5_entry_bytes(entry_payload)
        if str(name) != str(template_name):
            continue
        if str(name).endswith(ROLE_EDIT_SUFFIX):
            continue
        rid = _extract_root5_ref_root4_entry_id(entry_payload)
        if not isinstance(rid, int):
            continue
        matched += 1
        ref_ids.append(int(rid))

    if matched <= 0:
        raise ValueError(f"未在 root5 section 找到玩家模板 wrapper：template_name={str(template_name)!r}")

    ref_ids_unique = sorted(set(int(x) for x in ref_ids))
    if len(ref_ids_unique) != 1:
        raise ValueError(
            f"同名玩家模板 wrapper 引用多个 root4_entry_id：template={str(template_name)!r} ref_ids={ref_ids_unique!r}"
        )
    return int(ref_ids_unique[0]), int(matched)


def _patch_root5_wrappers_group1_in_section5(
    section5_payload: bytes,
    *,
    template_name: str,
    root4_entry_id: int,
    group1_item_bytes: bytes,
) -> Tuple[bytes, int]:
    """对 root5 section 中匹配模板名 + root4_entry_id 的 wrapper 条目补丁 group1 容器。"""

    def _should_patch_root5_entry(entry_payload: bytes) -> bool:
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            return False
        if _extract_template_name_from_root5_entry_bytes(entry_payload) != str(template_name):
            return False
        if str(template_name).endswith(ROLE_EDIT_SUFFIX):
            return False
        rid2 = _extract_root5_ref_root4_entry_id(entry_payload)
        return isinstance(rid2, int) and int(rid2) == int(root4_entry_id)

    def _patch_root5_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=ROOT5_GROUP_LIST_FIELD_NUMBER,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section5, patched_wrappers = _patch_section_entries_field1_by_predicate(
        section5_payload,
        should_patch_entry=_should_patch_root5_entry,
        patch_entry_bytes=_patch_root5_entry,
    )
    if int(patched_wrappers) <= 0:
        raise RuntimeError("internal error: matched wrappers but patched 0 entries")
    return bytes(patched_section5), int(patched_wrappers)


def _patch_root4_group1_in_section4(section4_payload: bytes, *, root4_entry_id: int, group1_item_bytes: bytes) -> Tuple[bytes, int]:
    """对 root4 section 中匹配 root4_entry_id 的条目补丁 group1 容器。"""

    def _should_patch_root4_entry(entry_payload: bytes) -> bool:
        vid = _read_single_varint_field_from_message_bytes(entry_payload, field_number=1)
        return isinstance(vid, int) and int(vid) == int(root4_entry_id)

    def _patch_root4_entry(entry_payload: bytes) -> bytes:
        return _patch_group_list_field_in_entry_bytes(
            entry_payload,
            group_field_number=ROOT4_GROUP_LIST_FIELD_NUMBER,
            new_group1_item_payload_bytes=bytes(group1_item_bytes),
        )

    patched_section4, patched_root4 = _patch_section_entries_field1_by_predicate(
        section4_payload,
        should_patch_entry=_should_patch_root4_entry,
        patch_entry_bytes=_patch_root4_entry,
    )
    return bytes(patched_section4), int(patched_root4)


def patch_player_template_custom_variable_defs_in_gil(
    *,
    input_gil: Path,
    output_gil: Path,
    template_name: str,
    variables: List[Tuple[str, int, Any]],
) -> Dict[str, Any]:
    """
    安全写回：仅对玩家模板的变量定义字段做 wire-level 补丁，避免全量 decode/encode 造成 payload drift。

    修改范围（按已验证真源结构）：
    - payload_root field 5（root5 wrappers）：对匹配 template_name 的玩家模板 wrapper 条目，补齐/替换 field 7 的 group1 变量容器
    - payload_root field 4（root4 entries）：对 wrapper 引用到的 root4_entry_id，补齐/替换 field 8 的 group1 变量容器
    """
    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    container = read_gil_container(in_path)
    payload = bytes(container.payload)
    root_chunks, s4_idx, s4_payload, s5_idx, s5_payload = _extract_root4_root5_sections_or_raise(payload)

    group1_item_bytes = _build_group1_container_item_bytes(variables=variables)
    target_root4_entry_id, _matched = _find_target_root4_entry_id_or_raise(s5_payload, template_name=target_name)

    patched_section5, patched_wrappers = _patch_root5_wrappers_group1_in_section5(
        s5_payload,
        template_name=target_name,
        root4_entry_id=int(target_root4_entry_id),
        group1_item_bytes=bytes(group1_item_bytes),
    )
    patched_section4, patched_root4 = _patch_root4_group1_in_section4(
        s4_payload,
        root4_entry_id=int(target_root4_entry_id),
        group1_item_bytes=bytes(group1_item_bytes),
    )
    if int(patched_root4) != 1:
        raise ValueError(
            f"root4 section 命中条目数量异常：expected=1 actual={int(patched_root4)} root4_entry_id={int(target_root4_entry_id)}"
        )

    new_payload = _rebuild_payload_root_with_patched_sections(
        root_chunks,
        section4_idx=int(s4_idx),
        patched_section4=bytes(patched_section4),
        section5_idx=int(s5_idx),
        patched_section5=bytes(patched_section5),
    )

    out_bytes = build_gil_bytes_from_container(base=container, new_payload=bytes(new_payload))
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    return {
        "input_gil": str(in_path),
        "output_gil": str(out_path),
        "template_name": str(target_name),
        "root4_entry_id": int(target_root4_entry_id),
        "patched_root5_wrappers": int(patched_wrappers),
        "variables_total": int(len(list(variables or []))),
    }


def extract_player_template_group1_container_item_bytes_from_gil(*, input_gil: Path, template_name: str) -> bytes:
    """
    从指定 `.gil` 中提取玩家模板（root5 wrapper）的 group1(1/1) 变量容器 item 的 message bytes（payload，不含外层 length varint）。
    """
    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    container = read_gil_container(in_path)
    payload = bytes(container.payload)
    root_chunks = _decode_root_chunks_or_raise(payload)
    _s5_idx, section5_payload = _extract_single_section_payload_or_raise(root_chunks, field_number=PAYLOAD_ROOT_SECTION5_FIELD_NUMBER)

    s5_chunks, consumed5 = _decode_wire_chunks(
        data_bytes=bytes(section5_payload),
        start_offset=0,
        end_offset=len(section5_payload),
    )
    if int(consumed5) != len(section5_payload):
        raise ValueError("section5 did not consume all bytes")

    for tag_raw, value_raw in list(s5_chunks):
        tag = _parse_tag_raw(tag_raw)
        if int(tag.field_number) != SECTION_ENTRY_FIELD_NUMBER or int(tag.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
            continue
        _len_raw, entry_payload = _split_ld_value_raw(value_raw)
        if not _is_player_template_like_root5_entry_bytes(entry_payload):
            continue
        name = _extract_template_name_from_root5_entry_bytes(entry_payload)
        if str(name) != target_name:
            continue

        # 在该 wrapper entry 内找到 field7 的 group1 item
        e_chunks, consumed_e = _decode_wire_chunks(
            data_bytes=bytes(entry_payload),
            start_offset=0,
            end_offset=len(entry_payload),
        )
        if int(consumed_e) != len(entry_payload):
            raise ValueError("entry payload did not consume all bytes")

        for t_raw, v_raw in list(e_chunks):
            t = _parse_tag_raw(t_raw)
            if int(t.field_number) != ROOT5_GROUP_LIST_FIELD_NUMBER or int(t.wire_type) != WIRE_TYPE_LENGTH_DELIMITED:
                continue
            _len_raw2, group_item_payload = _split_ld_value_raw(v_raw)
            if _is_group1_container_item_bytes(group_item_payload):
                return bytes(group_item_payload)

        raise ValueError(f"模板存在但未找到 group1 变量容器：template={target_name!r}")

    raise ValueError(f"未找到玩家模板：template_name={target_name!r}")


def patch_player_template_custom_variable_group1_item_bytes_in_gil(
    *,
    input_gil: Path,
    output_gil: Path,
    template_name: str,
    group1_container_item_bytes: bytes,
) -> Dict[str, Any]:
    """使用外部提供的 group1 容器 item bytes（原样）补丁玩家模板变量定义字段。"""
    if not isinstance(group1_container_item_bytes, (bytes, bytearray)):
        raise TypeError("group1_container_item_bytes must be bytes")
    group1_item_bytes = bytes(group1_container_item_bytes)
    if group1_item_bytes == b"":
        raise ValueError("group1_container_item_bytes 不能为空")

    in_path = Path(input_gil).resolve()
    if not in_path.is_file():
        raise FileNotFoundError(str(in_path))

    target_name = str(template_name or "").strip()
    if target_name == "":
        raise ValueError("template_name 不能为空")

    container = read_gil_container(in_path)
    payload = bytes(container.payload)
    root_chunks, s4_idx, s4_payload, s5_idx, s5_payload = _extract_root4_root5_sections_or_raise(payload)

    target_root4_entry_id, _matched = _find_target_root4_entry_id_or_raise(s5_payload, template_name=target_name)

    patched_section5, patched_wrappers = _patch_root5_wrappers_group1_in_section5(
        s5_payload,
        template_name=target_name,
        root4_entry_id=int(target_root4_entry_id),
        group1_item_bytes=bytes(group1_item_bytes),
    )
    patched_section4, patched_root4 = _patch_root4_group1_in_section4(
        s4_payload,
        root4_entry_id=int(target_root4_entry_id),
        group1_item_bytes=bytes(group1_item_bytes),
    )
    if int(patched_root4) != 1:
        raise ValueError(
            f"root4 section 命中条目数量异常：expected=1 actual={int(patched_root4)} root4_entry_id={int(target_root4_entry_id)}"
        )

    new_payload = _rebuild_payload_root_with_patched_sections(
        root_chunks,
        section4_idx=int(s4_idx),
        patched_section4=bytes(patched_section4),
        section5_idx=int(s5_idx),
        patched_section5=bytes(patched_section5),
    )

    out_bytes = build_gil_bytes_from_container(base=container, new_payload=bytes(new_payload))
    out_path = Path(output_gil).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out_bytes)

    return {
        "input_gil": str(in_path),
        "output_gil": str(out_path),
        "template_name": str(target_name),
        "root4_entry_id": int(target_root4_entry_id),
        "patched_root5_wrappers": int(patched_wrappers),
    }

