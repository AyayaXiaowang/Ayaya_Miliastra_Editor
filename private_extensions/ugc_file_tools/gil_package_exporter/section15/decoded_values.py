from __future__ import annotations

from typing import Any, Dict, Optional


def _try_trim_to_first_chinese(text: str) -> str:
    for index, ch in enumerate(text):
        code_point = ord(ch)
        if 0x4E00 <= code_point <= 0x9FFF:
            return text[index:].strip()
    return text.strip()


def _try_extract_utf8(value_object: Any) -> Optional[str]:
    """从 decode_gil 的 length-delimited 视图中提取 utf8。"""
    if not isinstance(value_object, dict):
        return None
    utf8_value = value_object.get("utf8")
    if isinstance(utf8_value, str) and utf8_value.strip() != "":
        return utf8_value
    return None


def _try_extract_fixed32_float(value_object: Any) -> Optional[float]:
    if not isinstance(value_object, dict):
        return None
    float_value = value_object.get("fixed32_float")
    if isinstance(float_value, (int, float)):
        return float(float_value)
    return None


def _try_extract_int(value_object: Any) -> Optional[int]:
    if not isinstance(value_object, dict):
        return None
    int_value = value_object.get("int")
    if isinstance(int_value, int):
        return int(int_value)
    return None


def _try_extract_message(value_object: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value_object, dict):
        return None
    message_value = value_object.get("message")
    if isinstance(message_value, dict):
        return message_value
    return None


