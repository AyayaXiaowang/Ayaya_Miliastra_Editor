from __future__ import annotations

from typing import Iterable, List


def normalize_custom_variable_file_refs(value: object) -> list[str]:
    """将 custom_variable_file 的 JSON 值归一化为引用列表。

    兼容：
    - "" / None：返回 []
    - "file_id"：返回 ["file_id"]
    - ["id1", "id2"]：返回 ["id1", "id2"]

    行为：
    - 每个条目做 strip，丢弃空字符串
    - 保持顺序并去重
    """
    refs: list[str] = []

    if value is None:
        return refs

    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []

    if isinstance(value, list):
        for item in value:
            if not isinstance(item, str):
                continue
            text = item.strip()
            if text:
                refs.append(text)

    # 去重（保持顺序）
    seen: set[str] = set()
    unique: list[str] = []
    for item in refs:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def serialize_custom_variable_file_refs(refs: Iterable[str]) -> str | list[str]:
    """将 refs 序列序列化回 JSON 友好的值（字符串或列表）。"""
    normalized = normalize_custom_variable_file_refs(list(refs))
    if len(normalized) == 1:
        return normalized[0]
    return normalized


__all__ = [
    "normalize_custom_variable_file_refs",
    "serialize_custom_variable_file_refs",
]

