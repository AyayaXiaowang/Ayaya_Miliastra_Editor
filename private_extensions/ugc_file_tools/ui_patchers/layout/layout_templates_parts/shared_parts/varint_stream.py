from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import format_binary_data_hex_text, parse_binary_data_hex_text


def _set_children_guids_to_parent_record(parent_record: Dict[str, Any], child_guids: List[int]) -> None:
    field503 = parent_record.get("503")
    # 兼容：某些 parent record（尤其是“控件组库根”在完全空库时）可能不包含 503 字段，
    # 此时应视为“空 children 列表”，并在首次写入时补齐。
    if field503 is None:
        field503 = [""]
        parent_record["503"] = field503
    # 兼容：部分 dump-json 中 repeated 字段在“只有 1 个元素”时可能是标量（例如 str）而不是 list。
    if isinstance(field503, str):
        field503 = [field503]
        parent_record["503"] = field503

    if not isinstance(field503, list) or not field503:
        raise ValueError("parent_record missing children list at field 503")
    first = field503[0]
    if not isinstance(first, str):
        raise ValueError("parent_record field 503[0] must be str")
    # 注意：当 bytes 为空时，DLL dump-json 会输出空字符串 ""，此时应视为有效的空 <binary_data>
    if first != "" and not first.startswith("<binary_data>"):
        raise ValueError("parent_record field 503[0] must be '<binary_data>' string or empty string")
    new_bytes = _encode_varint_stream([int(g) for g in child_guids])
    field503[0] = format_binary_data_hex_text(new_bytes)


def _append_children_guids_to_parent_record(parent_record: Dict[str, Any], child_guids: List[int]) -> None:
    field503 = parent_record.get("503")
    # 兼容：某些 parent record（尤其是“控件组库根”在完全空库时）可能不包含 503 字段，
    # 此时应视为“空 children 列表”，并在首次 append 时补齐。
    if field503 is None:
        field503 = [""]
        parent_record["503"] = field503
    # 兼容：部分 dump-json 中 repeated 字段在“只有 1 个元素”时可能是标量（例如 str）而不是 list。
    if isinstance(field503, str):
        field503 = [field503]
        parent_record["503"] = field503

    if isinstance(field503, list) and not field503:
        # 兼容：空 list 视为“空 children”，补齐为可写回形态
        field503.append("")
    if not isinstance(field503, list) or not field503:
        raise ValueError("parent_record missing children list at field 503")
    first = field503[0]
    if not isinstance(first, str):
        raise ValueError("parent_record field 503[0] must be str")
    # 注意：当 bytes 为空时，DLL dump-json 会输出空字符串 ""，此时应视为有效的空 <binary_data>
    if first == "":
        existing_bytes = b""
    else:
        if not first.startswith("<binary_data>"):
            raise ValueError("parent_record field 503[0] must be '<binary_data>' string or empty string")
        existing_bytes = parse_binary_data_hex_text(first)

    existing_ids = _decode_varint_stream(existing_bytes)

    new_bytes = bytearray(existing_bytes)
    for guid in child_guids:
        new_bytes.extend(_encode_varint(int(guid)))

    field503[0] = format_binary_data_hex_text(bytes(new_bytes))

    appended_ids = _decode_varint_stream(bytes(new_bytes))
    if len(appended_ids) != len(existing_ids) + len(child_guids):
        raise RuntimeError("parent children varint list parse mismatch after append")


def _get_children_guids_from_parent_record(parent_record: Dict[str, Any]) -> List[int]:
    field503 = parent_record.get("503")
    # 兼容：某些 parent record（尤其是“控件组库根”在完全空库时）可能不包含 503 字段，
    # 此时应视为“空 children 列表”。
    if field503 is None:
        return []
    # 兼容：部分 dump-json 中 repeated 字段在“只有 1 个元素”时可能是标量（例如 str）而不是 list。
    if isinstance(field503, str):
        field503 = [field503]

    # 兼容：某些 dump 会把“空 children”表示为 [] 而不是缺字段或 [""]。
    if isinstance(field503, list) and not field503:
        return []
    if not isinstance(field503, list) or not field503:
        raise ValueError("parent_record missing children list at field 503")
    first = field503[0]
    if not isinstance(first, str):
        raise ValueError("parent_record field 503[0] must be str")
    # 注意：当 bytes 为空时，DLL dump-json 会输出空字符串 ""，此时应视为有效的空 <binary_data>
    if first == "":
        return []
    if not first.startswith("<binary_data>"):
        raise ValueError("parent_record field 503[0] must be '<binary_data>' string or empty string")
    existing_bytes = parse_binary_data_hex_text(first)
    return _decode_varint_stream(existing_bytes)


def _replace_children_guids_in_parent_record(
    parent_record: Dict[str, Any],
    *,
    remove_child_guids: List[int],
    insert_child_guids: List[int],
) -> None:
    """
    从 parent_record.children 中移除若干 guid，并在“第一个被移除元素的位置”插入新的 guid 列表。

    用于实现“打组”：library_root.children 中把 [a,b,c] 替换为 [group_guid]。
    """
    remove_set = {int(g) for g in remove_child_guids}
    if not remove_set:
        raise ValueError("remove_child_guids 不能为空")

    existing = _get_children_guids_from_parent_record(parent_record)
    removed_positions = [idx for idx, g in enumerate(existing) if int(g) in remove_set]
    if not removed_positions:
        raise ValueError("remove_child_guids 在 parent.children 中未命中任何元素")
    if len(removed_positions) != len(remove_set):
        missing = sorted(remove_set - {int(g) for g in existing})
        raise ValueError(f"remove_child_guids 存在缺失：{missing}")

    min_pos = min(removed_positions)
    insert_values = [int(g) for g in insert_child_guids]
    if len(set(insert_values)) != len(insert_values):
        raise ValueError("insert_child_guids 存在重复值")
    if any(int(g) in set(existing) for g in insert_values):
        raise ValueError("insert_child_guids 与现有 children 存在重复 guid（会导致树重复引用）")

    new_children: List[int] = []
    for idx, g in enumerate(existing):
        if idx == min_pos:
            new_children.extend(insert_values)
        if int(g) in remove_set:
            continue
        new_children.append(int(g))

    _set_children_guids_to_parent_record(parent_record, new_children)


def _encode_varint_stream(values: List[int]) -> bytes:
    chunks = []
    for v in values:
        chunks.append(_encode_varint(int(v)))
    return b"".join(chunks)


def _decode_varint_stream(data: bytes) -> List[int]:
    values: List[int] = []
    offset = 0
    end_offset = len(data)
    while offset < end_offset:
        value, offset, ok = _decode_varint(data, offset)
        if not ok:
            raise ValueError("invalid varint stream")
        values.append(int(value))
    return values


def _decode_varint(data: bytes, offset: int) -> Tuple[int, int, bool]:
    value = 0
    shift_bits = 0
    current_offset = offset
    while True:
        if current_offset >= len(data):
            return 0, current_offset, False
        current_byte = data[current_offset]
        current_offset += 1
        value |= (current_byte & 0x7F) << shift_bits
        if (current_byte & 0x80) == 0:
            return value, current_offset, True
        shift_bits += 7
        if shift_bits >= 64:
            return 0, current_offset, False


def _encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError(f"varint value must be >= 0, got {value}")
    parts: List[int] = []
    remaining = int(value)
    while True:
        byte_value = remaining & 0x7F
        remaining >>= 7
        if remaining:
            parts.append(byte_value | 0x80)
        else:
            parts.append(byte_value)
            break
    return bytes(parts)


def _parse_protobuf_like_fields(data: bytes) -> Tuple[List[Tuple[int, int, Any]], bool]:
    """
    解析 protobuf-like message，只实现本模块需要的子集（wire_type 0/2/5/1）。
    """
    fields: List[Tuple[int, int, Any]] = []
    current_offset = 0
    end_offset = len(data)
    while current_offset < end_offset:
        tag, current_offset, ok = _decode_varint(data, current_offset)
        if not ok or tag == 0:
            return fields, False
        field_number = int(tag) >> 3
        wire_type = int(tag) & 0x07
        if field_number <= 0:
            return fields, False

        if wire_type == 0:
            value, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return fields, False
            fields.append((field_number, 0, int(value)))
            continue

        if wire_type == 5:
            if current_offset + 4 > end_offset:
                return fields, False
            fields.append((field_number, 5, data[current_offset : current_offset + 4]))
            current_offset += 4
            continue

        if wire_type == 1:
            if current_offset + 8 > end_offset:
                return fields, False
            fields.append((field_number, 1, data[current_offset : current_offset + 8]))
            current_offset += 8
            continue

        if wire_type == 2:
            length, current_offset, ok = _decode_varint(data, current_offset)
            if not ok:
                return fields, False
            length_int = int(length)
            if length_int < 0 or current_offset + length_int > end_offset:
                return fields, False
            value_bytes = data[current_offset : current_offset + length_int]
            current_offset += length_int
            fields.append((field_number, 2, value_bytes))
            continue

        return fields, False

    return fields, True


__all__ = [
    "_set_children_guids_to_parent_record",
    "_append_children_guids_to_parent_record",
    "_get_children_guids_from_parent_record",
    "_replace_children_guids_in_parent_record",
    "_encode_varint_stream",
    "_decode_varint_stream",
    "_decode_varint",
    "_encode_varint",
    "_parse_protobuf_like_fields",
]

