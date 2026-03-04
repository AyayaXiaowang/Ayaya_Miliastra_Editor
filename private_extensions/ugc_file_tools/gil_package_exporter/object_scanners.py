from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple


def _looks_like_base64_data(text: str) -> bool:
    if len(text) < 16:
        return False
    if len(text) % 4 != 0:
        return False
    for character in text:
        if character.isalnum():
            continue
        if character in "+/=":
            continue
        return False
    return True


def _iter_leaf_values(
    python_object: Any, path_parts: Optional[List[str]] = None
) -> Iterable[Tuple[str, Any]]:
    current_path_parts = path_parts if path_parts is not None else []
    if isinstance(python_object, dict):
        for key, value in python_object.items():
            yield from _iter_leaf_values(value, current_path_parts + [str(key)])
        return
    if isinstance(python_object, list):
        for index, value in enumerate(python_object):
            yield from _iter_leaf_values(value, current_path_parts + [f"[{index}]"])
        return
    yield "/".join(current_path_parts), python_object


def _collect_string_values(python_object: Any) -> Dict[str, Dict[str, Any]]:
    string_index: Dict[str, Dict[str, Any]] = {}
    if not isinstance(python_object, dict):
        return string_index

    def walk(value: Any, path_parts: List[str]) -> None:
        if isinstance(value, dict):
            for key, child_value in value.items():
                new_path_parts = path_parts + [str(key)]
                if (
                    isinstance(child_value, str)
                    and isinstance(key, str)
                    and key.endswith("@string")
                ):
                    record = string_index.get(child_value)
                    if record is None:
                        record = {"count": 0, "paths": []}
                        string_index[child_value] = record
                    record["count"] += 1
                    if len(record["paths"]) < 20:
                        record["paths"].append("/".join(new_path_parts))
                walk(child_value, new_path_parts)
            return
        if isinstance(value, list):
            for index, child_value in enumerate(value):
                walk(child_value, path_parts + [f"[{index}]"])
            return

    walk(python_object, [])
    return string_index


def _collect_data_blobs(python_object: Any) -> List[Tuple[str, str, str]]:
    """
    返回 (json_path, key_name, base64_text) 列表。

    - 规则1：key 以 @data 结尾，且 value 非空字符串
    - 规则2：UNKNOWN/其他字段也可能以 base64 形式出现：当 value 看起来像 base64 且 key 不以 @string 结尾时，也收集
    """
    blobs: List[Tuple[str, str, str]] = []

    def walk(value: Any, path_parts: List[str]) -> None:
        if isinstance(value, dict):
            for key, child_value in value.items():
                key_text = str(key)
                new_path_parts = path_parts + [key_text]

                if isinstance(child_value, str) and child_value:
                    if key_text.endswith("@data"):
                        blobs.append(("/".join(new_path_parts), key_text, child_value))
                    elif (
                        not key_text.endswith("@string")
                        and _looks_like_base64_data(child_value)
                    ):
                        blobs.append(("/".join(new_path_parts), key_text, child_value))

                walk(child_value, new_path_parts)
            return
        if isinstance(value, list):
            for index, child_value in enumerate(value):
                walk(child_value, path_parts + [f"[{index}]"])
            return

    walk(python_object, [])
    return blobs


