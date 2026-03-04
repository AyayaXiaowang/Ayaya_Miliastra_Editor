from __future__ import annotations

import copy
from typing import Any, Dict

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text

from .models import _GROUP_CONTAINER_COMPONENT1, _GROUP_CONTAINER_META0
from .varint_stream import _encode_varint


def _set_widget_guid(record: Dict[str, Any], new_guid: int) -> None:
    guid_field = record.get("501")
    # 兼容：部分 dump-json 中该字段可能直接是 int（而非 list[int]）
    if isinstance(guid_field, int):
        old_guid = int(guid_field)
        record["501"] = int(new_guid)
    else:
        guid_list = guid_field
        if not isinstance(guid_list, list) or not guid_list:
            raise ValueError("record missing guid list at field 501")
        old_guid_value = guid_list[0]
        if not isinstance(old_guid_value, int):
            raise ValueError("record field 501[0] must be int")
        old_guid = int(old_guid_value)
        guid_list[0] = int(new_guid)

    meta_list = record.get("502")
    if not isinstance(meta_list, list) or not meta_list:
        # 部分 record（例如布局 root）不存在需要同步写入的“重复 guid”字段
        return
    # 样本中存在两种位置：
    # - progressbar 等控件：502[0]/11/501
    # - 布局 root：502[1]/11/501
    # 统一策略：同步所有 meta[*]/11/501 == old_guid 的条目
    for meta in meta_list:
        if not isinstance(meta, dict):
            continue
        node11 = meta.get("11")
        if not isinstance(node11, dict):
            continue
        current = node11.get("501")
        if isinstance(current, int) and int(current) == old_guid:
            node11["501"] = int(new_guid)


def _set_widget_parent_guid_field504(record: Dict[str, Any], parent_guid: int) -> None:
    record["504"] = int(parent_guid)


def _set_widget_name(record: Dict[str, Any], new_name: str) -> None:
    component_list = record.get("505")
    if not isinstance(component_list, list) or not component_list:
        raise ValueError("record missing component list at field 505")
    name_component = component_list[0]
    if not isinstance(name_component, dict):
        raise ValueError("record field 505[0] must be dict")
    node12 = name_component.get("12")
    if not isinstance(node12, dict):
        raise ValueError("record field 505[0]/12 must be dict")
    node12["501"] = str(new_name)


def _force_record_to_group_container_shape(record: Dict[str, Any]) -> None:
    """
    强制把一个 record 的“组容器”相关字段改为样本一致的形态：
    - meta[0]（record['502'][0]）为 `_GROUP_CONTAINER_META0`
    - component[1]（record['505'][1]）为 `_GROUP_CONTAINER_COMPONENT1`
    """
    meta_list = record.get("502")
    if not isinstance(meta_list, list) or len(meta_list) < 2:
        raise ValueError("record missing meta list at field 502 (expected len>=2)")
    meta_list[0] = copy.deepcopy(_GROUP_CONTAINER_META0)

    component_list = record.get("505")
    if not isinstance(component_list, list) or len(component_list) < 2:
        raise ValueError("record missing component list at field 505 (expected len>=2)")
    component_list[1] = copy.deepcopy(_GROUP_CONTAINER_COMPONENT1)


def _build_meta_self_guid(guid: int) -> Dict[str, Any]:
    return {"11": {"501": int(guid)}, "501": 1, "502": 5}


def _build_group_meta13_template_ref(template_root_guid: int) -> Dict[str, Any]:
    blob = format_binary_data_hex_text(encode_message({"501": int(template_root_guid)}))
    return {"13": blob, "501": 3, "502": 3}


def _build_template_root_meta14_group_ref(group_guid: int) -> Dict[str, Any]:
    """
    样本：meta['14'] 是一个 message bytes：
      field_501 (wire_type=2, bytes) = varint(group_guid)
    """
    group_guid_varint_bytes = _encode_varint(int(group_guid))
    inner_message_bytes = encode_message({"501": format_binary_data_hex_text(group_guid_varint_bytes)})
    return {"14": format_binary_data_hex_text(inner_message_bytes), "501": 4, "502": 4}


__all__ = [
    "_set_widget_guid",
    "_set_widget_parent_guid_field504",
    "_set_widget_name",
    "_force_record_to_group_container_shape",
    "_build_meta_self_guid",
    "_build_group_meta13_template_ref",
    "_build_template_root_meta14_group_ref",
]

