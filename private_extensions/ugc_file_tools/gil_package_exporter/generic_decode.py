from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python


def _extract_utf8_texts_from_generic_decoded(python_object: Any) -> List[Dict[str, Any]]:
    """
    从 decode_gil 的通用解码结果中提取所有 utf8 文本项。

    结构通常形如：
    - {"raw_hex": "...", "utf8": "..."}
    """
    utf8_records: List[Dict[str, Any]] = []

    def walk(value: Any, path_parts: List[str]) -> None:
        if isinstance(value, dict):
            utf8_value = value.get("utf8")
            raw_hex_value = value.get("raw_hex")
            if isinstance(utf8_value, str) and utf8_value.strip() != "":
                utf8_records.append(
                    {
                        "text": utf8_value,
                        "raw_hex": raw_hex_value if isinstance(raw_hex_value, str) else None,
                        "path": "/".join(path_parts),
                    }
                )
            for key, child_value in value.items():
                walk(child_value, path_parts + [str(key)])
            return
        if isinstance(value, list):
            for index, child_value in enumerate(value):
                walk(child_value, path_parts + [f"[{index}]"])
            return

    walk(python_object, [])
    return utf8_records


def _extract_field_501_named_message_records(generic_decoded_object: Any) -> List[Dict[str, Any]]:
    """
    尝试抽取“message 内包含 field_501.utf8 的记录”，这类结构在存档中常用于承载命名条目（例如变量名表）。
    """
    records: List[Dict[str, Any]] = []

    def get_int_field(message_object: Dict[str, Any], field_key: str) -> Optional[int]:
        field_value = message_object.get(field_key)
        if not isinstance(field_value, dict):
            return None
        int_value = field_value.get("int")
        if not isinstance(int_value, int):
            return None
        return int_value

    def get_nested_message_int(
        message_object: Dict[str, Any], outer_field_key: str, inner_field_key: str
    ) -> Optional[int]:
        outer_field_value = message_object.get(outer_field_key)
        if not isinstance(outer_field_value, dict):
            return None
        nested_message = outer_field_value.get("message")
        if not isinstance(nested_message, dict):
            return None
        return get_int_field(nested_message, inner_field_key)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            message_object = value.get("message")
            if isinstance(message_object, dict):
                field_501_value = message_object.get("field_501")
                if isinstance(field_501_value, dict):
                    utf8_text = field_501_value.get("utf8")
                    if isinstance(utf8_text, str) and utf8_text.strip() != "":
                        records.append(
                            {
                                "name": utf8_text,
                                "field_1_int": get_int_field(message_object, "field_1"),
                                "field_13_field_1_int": get_nested_message_int(
                                    message_object, "field_13", "field_1"
                                ),
                                "field_501_raw_hex": (
                                    field_501_value.get("raw_hex")
                                    if isinstance(field_501_value.get("raw_hex"), str)
                                    else None
                                ),
                            }
                        )
            for child_value in value.values():
                walk(child_value)
            return
        if isinstance(value, list):
            for child_value in value:
                walk(child_value)
            return

    walk(generic_decoded_object)
    return records


def _extract_all_int_values(python_object: Any, collected: Optional[List[int]] = None) -> List[int]:
    if collected is None:
        collected = []
    if isinstance(python_object, dict):
        for value in python_object.values():
            _extract_all_int_values(value, collected)
        if isinstance(python_object.get("int"), int):
            collected.append(int(python_object["int"]))
        return collected
    if isinstance(python_object, list):
        for item in python_object:
            _extract_all_int_values(item, collected)
        return collected
    return collected


def _decode_base64_to_max_int(base64_text: str) -> Optional[int]:
    if base64_text == "":
        return None
    decoded_bytes = base64.b64decode(base64_text)
    decoded_object = decode_bytes_to_python(decoded_bytes)
    int_values = _extract_all_int_values(decoded_object)
    if not int_values:
        return None
    return max(int_values)


