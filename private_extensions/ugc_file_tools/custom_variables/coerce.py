from __future__ import annotations

from typing import Any

from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text

from .refs import is_number_like_text

__all__ = [
    "normalize_custom_variable_name_field2",
    "coerce_default_int",
    "coerce_default_float",
    "coerce_default_string",
    "is_blank_or_dot_text",
]


def normalize_custom_variable_name_field2(value: Any) -> str:
    """
    归一化实体自定义变量的“变量名字段”（item['2']）：
    - 兼容 lossless dump："<binary_data> .." -> bytes -> utf-8
    - 兼容真源里偶发的 NUL 结尾（"\\x00"）：仅保留第一个 NUL 前的文本
    - 最终 strip

    说明：这里的目标是“稳定查重”，避免基底里已经存在同名变量但因为编码细节导致重复写入。
    """
    text = ""
    if isinstance(value, str):
        if value.startswith("<binary_data>"):
            raw_bytes = parse_binary_data_hex_text(value)
            text = raw_bytes.decode("utf-8", errors="replace")
        else:
            text = value
    else:
        text = str(value if value is not None else "")
    if "\x00" in text:
        text = text.split("\x00", 1)[0]
    # 兼容：少量 lossless dump 可能把“utf8 字段”编码为带 protobuf tag/len 的 bytes，
    # decode 后会在开头残留控制字符（例如 "\\x15xxx"）。这里剥离前后控制字符，保证查重稳定。
    while text and ord(text[0]) < 32:
        text = text[1:]
    while text and ord(text[-1]) < 32:
        text = text[:-1]
    return str(text).strip()


def coerce_default_int(value: Any, *, key: str) -> int:
    if isinstance(value, bool):
        return int(1 if value else 0)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not (value == value):  # NaN
            raise ValueError(f"variable_defaults[{key!r}] 为 NaN")
        return int(value)
    text = str(value).strip()
    if text == "":
        raise ValueError(f"variable_defaults[{key!r}] 不能为空")
    if is_number_like_text(text):
        return int(float(text))
    raise ValueError(f"variable_defaults[{key!r}] 不是可解析的整数：{value!r}")


def coerce_default_float(value: Any, *, key: str) -> float:
    if isinstance(value, bool):
        return float(1.0 if value else 0.0)
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if not (value == value):  # NaN
            raise ValueError(f"variable_defaults[{key!r}] 为 NaN")
        return float(value)
    text = str(value).strip()
    if text == "":
        raise ValueError(f"variable_defaults[{key!r}] 不能为空")
    if is_number_like_text(text):
        return float(text)
    raise ValueError(f"variable_defaults[{key!r}] 不是可解析的浮点数：{value!r}")


def coerce_default_string(value: Any) -> str:
    return str(value if value is not None else "")


def is_blank_or_dot_text(text: str) -> bool:
    raw = str(text or "").strip()
    return raw == "" or raw == "."

