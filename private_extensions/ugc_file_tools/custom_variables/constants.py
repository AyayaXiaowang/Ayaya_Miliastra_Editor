from __future__ import annotations

from typing import Dict

__all__ = [
    "UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX",
    "ITEM_DISPLAY_UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX",
    "KNOWN_VARIABLE_GROUP_ID_BY_NAME",
    "DEFAULT_VARIABLE_GROUP_NAME",
]


# observed sentinel in some dumps: uint64 max (varint 10 bytes) means "unset / unbound"
UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX = 18446744073709551615

# item_display（道具展示）也复用同样的“未绑定 sentinel”
ITEM_DISPLAY_UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX = UNBOUND_GROUP_ID_SENTINEL_UINT64_MAX

# 变量分组（真源结构中的 group_id）
KNOWN_VARIABLE_GROUP_ID_BY_NAME: Dict[str, int] = {
    "玩家自身": 100,
    "关卡": 101,
}

# 默认变量组：用于 `lv.xxx` 的 canonical 化（lv -> 关卡）
DEFAULT_VARIABLE_GROUP_NAME = "关卡"

