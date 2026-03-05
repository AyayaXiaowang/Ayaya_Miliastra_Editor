from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from ugc_file_tools.decode_gil import decode_bytes_to_python


def _try_decode_section15_meta_data(
    section15_entry: Dict[str, Any],
    meta_item_id: int,
    data_key: str,
) -> Optional[Dict[str, Any]]:
    meta_list = section15_entry.get("4")
    if not isinstance(meta_list, list):
        return None
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != meta_item_id:
            continue
        data_text = meta_item.get(data_key)
        if not isinstance(data_text, str) or data_text == "":
            continue
        decoded_bytes = base64.b64decode(data_text)
        decoded_object = decode_bytes_to_python(decoded_bytes)
        return {
            "base64": data_text,
            "byte_size": len(decoded_bytes),
            "decoded": decoded_object,
        }
    return None


def _try_extract_environment_level_from_env_config_entry(section15_entry: Dict[str, Any]) -> Optional[int]:
    meta_list = section15_entry.get("4")
    if not isinstance(meta_list, list):
        return None
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 70:
            continue
        container = meta_item.get("75")
        if not isinstance(container, dict):
            continue
        level_value = container.get("1", {}).get("1", {}).get("6@int")
        if isinstance(level_value, int):
            return int(level_value)
    return None


def _try_extract_level_settings_env_payload(section15_entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """提取关卡设置(type_code=26)中 env_config 的核心结构，并对其中的 `8@data` 做通用解码。"""
    meta_list = section15_entry.get("4")
    if not isinstance(meta_list, list):
        return None
    for meta_item in meta_list:
        if not isinstance(meta_item, dict):
            continue
        if meta_item.get("1 id@int") != 70:
            continue
        container = meta_item.get("75")
        if not isinstance(container, dict):
            continue
        container_1 = container.get("1")
        if not isinstance(container_1, dict):
            continue
        env_object = container_1.get("1")
        if not isinstance(env_object, dict):
            continue

        decoded_env_data: Optional[Dict[str, Any]] = None
        env_data_text = env_object.get("8@data")
        if isinstance(env_data_text, str) and env_data_text:
            decoded_bytes = base64.b64decode(env_data_text)
            decoded_env_data = {
                "base64": env_data_text,
                "byte_size": len(decoded_bytes),
                "decoded": decode_bytes_to_python(decoded_bytes),
            }

        return {
            "env_object": env_object,
            "decoded_8@data": decoded_env_data,
        }
    return None


