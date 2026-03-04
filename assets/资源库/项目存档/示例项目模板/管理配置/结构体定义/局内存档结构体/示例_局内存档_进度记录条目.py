from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "2383899006"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_进度记录条目",
    "value": [
        {
            "key": "记录ID",
            "param_type": "整数",
        },
        {
            "key": "记录_进度值",
            "param_type": "整数",
        },
        {
            "key": "记录_时间戳",
            "param_type": "整数",
        },
    ],
}


