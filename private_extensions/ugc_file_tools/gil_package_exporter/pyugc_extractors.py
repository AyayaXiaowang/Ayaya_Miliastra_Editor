from __future__ import annotations

from typing import Any, Dict, Optional


def _extract_template_entry_name(template_entry: Dict[str, Any]) -> str:
    meta_list = template_entry.get("6")
    if not isinstance(meta_list, list):
        return ""
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 1:
            continue
        container = meta_item.get("11 id1")
        if not isinstance(container, dict):
            continue
        name_value = container.get("1@string")
        if isinstance(name_value, str):
            return name_value
    return ""


def _extract_section15_entry_name(section15_entry: Dict[str, Any]) -> str:
    meta_list = section15_entry.get("4")
    if not isinstance(meta_list, list):
        return ""
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 1:
            continue
        container = meta_item.get("11 id1")
        if not isinstance(container, dict):
            continue
        name_value = container.get("1@string")
        if isinstance(name_value, str):
            return name_value
    return ""


def _extract_section15_entry_id_int(section15_entry: Dict[str, Any]) -> Optional[int]:
    entry_id_list = section15_entry.get("1")
    if not isinstance(entry_id_list, list) or not entry_id_list:
        return None
    entry_id_int = entry_id_list[0]
    if not isinstance(entry_id_int, int):
        return None
    return entry_id_int


def _extract_section15_entry_type_code(section15_entry: Dict[str, Any]) -> Optional[int]:
    type_code_value = section15_entry.get("2@int")
    if not isinstance(type_code_value, int):
        return None
    return type_code_value


