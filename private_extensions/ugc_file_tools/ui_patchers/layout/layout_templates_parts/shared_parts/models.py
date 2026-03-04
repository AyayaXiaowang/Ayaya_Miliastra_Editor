from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ugc_file_tools.gil_dump_codec.protobuf_like import encode_message, format_binary_data_hex_text

DEFAULT_LIBRARY_ROOT_GUID = 1073741838

# 注意：这组尺寸来自 test5/test6 的“设备模板校准”
DEFAULT_CANVAS_SIZE_BY_STATE_INDEX: Dict[int, Tuple[float, float]] = {
    0: (1600.0, 900.0),  # 电脑
    1: (1280.0, 720.0),  # 手机
    2: (1920.0, 1080.0),  # 主机
    3: (1280.0, 720.0),  # 手柄主机
}

# === 控件组（打组 / 模板 / 层级）样本常量（来自 ugc_file_tools/save/界面控件组/*.gil） ===
# 说明：
# - “控件组库根”（library_root_guid）下的“组”record 与“模板 root”record 都使用同一套 505 组件形态（component[1] 为 14/...）。
# - “保存成模板”后：
#   - 组 record 会新增 meta[2]=12(blob=field_501=1) 与 meta[3]=13(blob=field_501=template_root_guid)
#   - 模板 root record 会额外包含 meta[1]=12(blob=field_501=1) 与 meta[2]=14(blob=field_501(bytes)=group_guid_varint)
_GROUP_CONTAINER_META0: Dict[str, Any] = {
    "16": "",
    "501": 6,
    "502": 13,
    "503": {"15": "", "501": 6, "502": 13, "503": 1},
}

_GROUP_CONTAINER_COMPONENT1: Dict[str, Any] = {
    "14": {"15": "", "501": 5},
    "501": 4,
    "502": 23,
    "503": {"14": {"15": "", "501": 5}, "501": 5, "502": 23, "503": 1},
}

# Public API (no leading underscores): cross-module imports must not import underscored private names.
GROUP_CONTAINER_COMPONENT1: Dict[str, Any] = _GROUP_CONTAINER_COMPONENT1

_TEMPLATE_MARKER_BLOB_FIELD501_EQ_1 = format_binary_data_hex_text(encode_message({"501": 1}))
_GROUP_TEMPLATE_META12: Dict[str, Any] = {"12": _TEMPLATE_MARKER_BLOB_FIELD501_EQ_1, "501": 2, "502": 6}


@dataclass(frozen=True, slots=True)
class CreatedLayout:
    guid: int
    name: str
    base_layout_guid: int


@dataclass(frozen=True, slots=True)
class CreatedProgressbarTemplate:
    entry_guid: int
    template_root_guid: int
    name: str
    library_root_guid: int
    entry_cloned_from_guid: int
    root_cloned_from_guid: int


@dataclass(frozen=True, slots=True)
class PlacedProgressbarInstance:
    guid: int
    name: str
    layout_guid: int
    cloned_from_guid: int


@dataclass(frozen=True, slots=True)
class CreatedControlGroup:
    guid: int
    name: str
    library_root_guid: int
    child_guids: Tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CreatedControlGroupTemplate:
    group_guid: int
    template_root_guid: int
    name: str
    cloned_child_guids: Tuple[int, ...]


__all__ = [
    "DEFAULT_LIBRARY_ROOT_GUID",
    "DEFAULT_CANVAS_SIZE_BY_STATE_INDEX",
    "_GROUP_CONTAINER_META0",
    "_GROUP_CONTAINER_COMPONENT1",
    "GROUP_CONTAINER_COMPONENT1",
    "_GROUP_TEMPLATE_META12",
    "CreatedLayout",
    "CreatedProgressbarTemplate",
    "PlacedProgressbarInstance",
    "CreatedControlGroup",
    "CreatedControlGroupTemplate",
    # Backward-compat: some modules import this helper via shared.py
    "format_binary_data_hex_text",
]

