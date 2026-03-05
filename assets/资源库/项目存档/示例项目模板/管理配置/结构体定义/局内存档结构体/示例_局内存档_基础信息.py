from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "1202219654"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_基础信息",
    "value": [
        {
            "key": "基础_版本号",
            "param_type": "整数",
        },
        {
            "key": "基础_创建时间戳",
            "param_type": "整数",
        },
        {
            "key": "基础_最近更新时间戳",
            "param_type": "整数",
        },
        {
            "key": "基础_备注标记",
            "param_type": "整数",
        },
    ],
}


