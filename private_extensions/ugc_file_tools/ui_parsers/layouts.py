from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import parse_binary_data_hex_text
from ugc_file_tools.ui.readable_dump import (
    extract_primary_guid as _extract_primary_guid,
    extract_primary_name as _extract_primary_name,
    extract_ui_record_list as _extract_ui_record_list,
    extract_visibility_flag_values as _extract_visibility_flag_values,
)


def build_layout_dump(dll_dump_object: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析“布局注册表 + 每个布局的固有子控件”。

    样本确认：
    - 布局注册表：4/9/501[0]（<binary_data>），内容为 varint stream：
      [默认布局, 自定义布局1, 自定义布局2, ..., (可选更多), 1073741838]
      末尾固定的 1073741838 为“控件组库根”。
    - 每个布局 root record：
      - guid 在 record['501'][0]
      - children guid 列表在 record['503'][0]（<binary_data> varint stream）
    - “可见性/关闭”开关（仅部分固有控件存在）：
      record['505'][1]['503']['14']['502'] = 1 表示该控件在该布局下被设置为不可见/关闭。
      若 502 缺失则视为默认（可见）。
    """
    root_data = dll_dump_object.get("4")
    if not isinstance(root_data, dict):
        raise ValueError("DLL dump JSON 缺少根字段 '4'（期望为 dict）。")

    node9 = root_data.get("9")
    if not isinstance(node9, dict):
        raise ValueError("DLL dump JSON 缺少字段 '4/9'（期望为 dict）。")

    layout_registry_blob_list = node9.get("501")
    # repeated 兼容：当只有 1 个元素时，dump-json 可能把 repeated string 退化为标量 str
    if isinstance(layout_registry_blob_list, str):
        layout_registry_blob_list = [layout_registry_blob_list]
        node9["501"] = layout_registry_blob_list
    if not isinstance(layout_registry_blob_list, list) or not layout_registry_blob_list:
        raise ValueError("DLL dump JSON 缺少字段 '4/9/501'（期望为非空 list）。")
    first = layout_registry_blob_list[0]
    if not isinstance(first, str) or not first.startswith("<binary_data>"):
        raise ValueError("字段 '4/9/501[0]' 期望为 '<binary_data>' 字符串。")

    layout_registry_bytes = parse_binary_data_hex_text(first)
    layout_registry_ids = _decode_varint_stream(layout_registry_bytes)

    library_root_guid: Optional[int] = None
    if layout_registry_ids:
        last = int(layout_registry_ids[-1])
        if 1073000000 <= last <= 1075000000:
            library_root_guid = last

    layout_root_guids = layout_registry_ids[:-1] if library_root_guid is not None else list(layout_registry_ids)

    ui_record_list = _extract_ui_record_list(dll_dump_object)
    guid_to_record: Dict[int, Dict[str, Any]] = {}
    for record in ui_record_list:
        if not isinstance(record, dict):
            continue
        guid_value = _extract_primary_guid(record)
        if isinstance(guid_value, int):
            guid_to_record[int(guid_value)] = record

    layouts: List[Dict[str, Any]] = []
    for layout_guid in layout_root_guids:
        layout_record = guid_to_record.get(int(layout_guid))
        if layout_record is None:
            continue

        children_guids = _extract_children_guids_from_layout_record(layout_record)
        children: List[Dict[str, Any]] = []
        for child_guid in children_guids:
            child_record = guid_to_record.get(int(child_guid))
            child_name = _extract_primary_name(child_record) if isinstance(child_record, dict) else None
            visibility_flag_values = _extract_visibility_flag_values(child_record) if isinstance(child_record, dict) else []

            visibility_override = _try_extract_layout_visibility_override(child_record) if isinstance(child_record, dict) else None

            children.append(
                {
                    "guid": int(child_guid),
                    "name": child_name,
                    "visibility_flag_values": visibility_flag_values,
                    "layout_visibility_override": visibility_override,
                }
            )

        layouts.append(
            {
                "guid": int(layout_guid),
                "name": _extract_primary_name(layout_record),
                "children_guids": [int(g) for g in children_guids],
                "children": children,
            }
        )

    return {
        "layout_registry_guids": [int(v) for v in layout_registry_ids],
        "layout_root_guids": [int(v) for v in layout_root_guids],
        "library_root_guid": int(library_root_guid) if library_root_guid is not None else None,
        "layout_total": len(layouts),
        "layouts": layouts,
        "assumptions": {
            "layout_registry_path": "4/9/501[0]",
            "layout_children_path": "record/503[0]",
            "layout_visibility_override_path": "record/505[1]/503/14/502",
            "layout_visibility_override_code_meaning": {0: "默认(显示)", 1: "不可见/关闭"},
        },
    }


def _extract_children_guids_from_layout_record(record: Dict[str, Any]) -> List[int]:
    field503 = record.get("503")
    # repeated 兼容：当只有 1 个元素时，dump-json 可能把 repeated string 退化为标量 str
    if isinstance(field503, str):
        field503 = [field503]
    # 兼容：空 children 可能表示为 [] / 缺失字段 / [""]（空 binary_data）
    if not isinstance(field503, list) or not field503:
        return []
    first = field503[0]
    if not isinstance(first, str):
        return []
    if first == "":
        return []
    if not first.startswith("<binary_data>"):
        return []
    data = parse_binary_data_hex_text(first)
    return _decode_varint_stream(data)


def _try_extract_layout_visibility_override(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    返回:
    - None：该控件没有“布局可见性开关”（编辑器里不会出现“可见性/关闭”设置）
    - dict：包含是否写入 override 以及 override_code
    """
    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) <= 1:
        return None
    component = component_list[1]
    if not isinstance(component, dict):
        return None
    nested = component.get("503")
    if not isinstance(nested, dict):
        return None
    node14 = nested.get("14")
    if not isinstance(node14, dict):
        return None

    override_code = node14.get("502")
    return {
        "supported": True,
        "node14": dict(node14),
        "override_code": int(override_code) if isinstance(override_code, int) else None,
        "is_hidden_guess": True if isinstance(override_code, int) and int(override_code) == 1 else False,
    }


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


