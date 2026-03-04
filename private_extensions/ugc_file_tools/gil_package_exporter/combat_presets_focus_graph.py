from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.decode_gil import decode_bytes_to_python

from .file_io import _write_json_file


def _try_extract_location_to_ui_guid_map(decoded_object: Any) -> Tuple[Optional[str], Dict[str, int]]:
    """
    针对 focus_graph_id=1073741832 的已知结构，尝试从通用解码结果中提取：
    - 字典名称（例如“地点到界面GUID字典”）
    - 映射：界面名 -> int(GUID/资源ID)
    """
    if not isinstance(decoded_object, dict):
        return None, {}

    dictionary_name: Optional[str] = None
    field_2 = decoded_object.get("field_2")
    if isinstance(field_2, dict) and isinstance(field_2.get("utf8"), str):
        dictionary_name = field_2.get("utf8")

    map_result: Dict[str, int] = {}

    field_4 = decoded_object.get("field_4")
    if not isinstance(field_4, dict):
        return dictionary_name, map_result
    field_4_message = field_4.get("message")
    if not isinstance(field_4_message, dict):
        return dictionary_name, map_result
    field_37 = field_4_message.get("field_37")
    if not isinstance(field_37, dict):
        return dictionary_name, map_result
    field_37_message = field_37.get("message")
    if not isinstance(field_37_message, dict):
        return dictionary_name, map_result

    pairs = field_37_message.get("field_1")
    if not isinstance(pairs, list):
        return dictionary_name, map_result

    for pair_item in pairs:
        if not isinstance(pair_item, dict):
            continue
        pair_message = pair_item.get("message")
        if not isinstance(pair_message, dict):
            continue
        field_35 = pair_message.get("field_35")
        if not isinstance(field_35, dict):
            continue
        field_35_message = field_35.get("message")
        if not isinstance(field_35_message, dict):
            continue
        key_value_list = field_35_message.get("field_1")
        if not isinstance(key_value_list, list) or len(key_value_list) < 2:
            continue

        key_text: Optional[str] = None
        value_int: Optional[int] = None

        key_message = (
            key_value_list[0].get("message") if isinstance(key_value_list[0], dict) else None
        )
        if isinstance(key_message, dict):
            field_16 = key_message.get("field_16")
            if isinstance(field_16, dict):
                field_16_message = field_16.get("message")
                if isinstance(field_16_message, dict):
                    field_1 = field_16_message.get("field_1")
                    if isinstance(field_1, dict) and isinstance(field_1.get("utf8"), str):
                        key_text = field_1.get("utf8")

        value_message = (
            key_value_list[1].get("message") if isinstance(key_value_list[1], dict) else None
        )
        if isinstance(value_message, dict):
            field_12 = value_message.get("field_12")
            if isinstance(field_12, dict):
                field_12_message = field_12.get("message")
                if isinstance(field_12_message, dict):
                    field_1 = field_12_message.get("field_1")
                    if isinstance(field_1, dict) and isinstance(field_1.get("int"), int):
                        value_int = int(field_1.get("int"))

        if isinstance(key_text, str) and key_text.strip() != "" and isinstance(value_int, int):
            map_result[key_text] = value_int

    return dictionary_name, map_result


def _scan_focus_graph_hits_in_template_entry(
    *,
    template_entry: Dict[str, Any],
    template_entry_path: str,
    template_id_int: int,
    template_name: str,
    focus_graph_id: int,
    node_graph_focus_directory: Path,
    output_package_root: Path,
) -> List[Dict[str, Any]]:
    decoded_focus_hits: List[Dict[str, Any]] = []

    def walk(value: Any, path_parts: List[str]) -> None:
        if isinstance(value, dict):
            data_text = value.get("2@data")
            node_meta = value.get("1")
            if (
                isinstance(data_text, str)
                and data_text != ""
                and isinstance(node_meta, dict)
                and node_meta.get("2@int") == focus_graph_id
            ):
                decoded_bytes = base64.b64decode(data_text)
                decoded_object = decode_bytes_to_python(decoded_bytes)
                hit_index = len(decoded_focus_hits) + 1
                hit_file_name = f"hit_{hit_index:03d}_template_{template_id_int}.json"
                hit_output_path = node_graph_focus_directory / hit_file_name
                _write_json_file(hit_output_path, decoded_object)

                dictionary_name, extracted_map = _try_extract_location_to_ui_guid_map(decoded_object)
                map_output_path = None
                if extracted_map:
                    map_file_name = f"hit_{hit_index:03d}_template_{template_id_int}.map.json"
                    map_output_path = node_graph_focus_directory / map_file_name
                    _write_json_file(
                        map_output_path,
                        {
                            "name": dictionary_name,
                            "mapping": extracted_map,
                        },
                    )

                decoded_focus_hits.append(
                    {
                        "template_entry_id_int": template_id_int,
                        "template_name": template_name,
                        "path": "/".join(path_parts),
                        "output": str(hit_output_path.relative_to(output_package_root)).replace("\\", "/"),
                        "byte_size": len(decoded_bytes),
                        "decoded_name": dictionary_name,
                        "map_output": (
                            str(map_output_path.relative_to(output_package_root)).replace("\\", "/")
                            if map_output_path is not None
                            else None
                        ),
                        "map_size": len(extracted_map),
                    }
                )

            for key, child_value in value.items():
                walk(child_value, path_parts + [str(key)])
            return
        if isinstance(value, list):
            for index, child_value in enumerate(value):
                walk(child_value, path_parts + [f"[{index}]"])
            return

    walk(template_entry, [template_entry_path])
    return decoded_focus_hits


