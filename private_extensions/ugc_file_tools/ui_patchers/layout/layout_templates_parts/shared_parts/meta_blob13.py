from __future__ import annotations

from typing import Any, Dict, List, Optional

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text, parse_binary_data_hex_text

from .varint_stream import _parse_protobuf_like_fields


def _has_meta_blob13(record: Dict[str, Any]) -> bool:
    """
    是否存在 meta `502/*/13` 的 <binary_data> blob。

    注意：该字段不是统一意义上的 template_id，可能用于：
    - 模板库条目 -> 指向 template_root_guid
    - 控件组子控件 -> next 指针（顺序链）
    等等。不要在不确认语义的情况下随意改写。
    """
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        return False
    for element in meta_list:
        if not isinstance(element, dict):
            continue
        blob = element.get("13")
        if isinstance(blob, str) and blob.startswith("<binary_data>"):
            return True
    return False


def _collect_existing_meta_blob13_field501_values(ui_record_list: List[Any]) -> set[int]:
    values: set[int] = set()
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        value = _try_extract_meta_blob13_field501_value(record)
        if value is not None:
            values.add(int(value))
    return values


def _try_extract_meta_blob13_field501_value(record: Dict[str, Any]) -> Optional[int]:
    """
    从 record['502'] 的 13 blob 里提取 field_501(varint)。

    注意：该值的语义依赖 record 形态，常见于：
    - 模板库条目：template_root_guid
    - 控件组子控件：next 指针（顺序链）
    """
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        return None
    for element in meta_list:
        if not isinstance(element, dict):
            continue
        blob = element.get("13")
        if not isinstance(blob, str) or not blob.startswith("<binary_data>"):
            continue
        data = parse_binary_data_hex_text(blob)
        fields, ok = _parse_protobuf_like_fields(data)
        if not ok:
            continue
        for field_number, wire_type, value in fields:
            if field_number == 501 and wire_type == 0 and isinstance(value, int):
                return int(value)
    return None


def _set_meta_blob13_field501_value(record: Dict[str, Any], value: int) -> None:
    meta_list = record.get("502")
    if not isinstance(meta_list, list):
        raise ValueError("record missing meta list at field 502")
    for element in meta_list:
        if not isinstance(element, dict):
            continue
        blob = element.get("13")
        if not isinstance(blob, str) or not blob.startswith("<binary_data>"):
            continue
        element["13"] = format_binary_data_hex_text(encode_message({"501": int(value)}))
        return
    raise ValueError("record missing <binary_data> blob at field 502/*/13")


__all__ = [
    "_has_meta_blob13",
    "_collect_existing_meta_blob13_field501_values",
    "_try_extract_meta_blob13_field501_value",
    "_set_meta_blob13_field501_value",
]

