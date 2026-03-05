from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "2451880634"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_事件记录条目",
    "value": [
        {
            "key": "事件ID",
            "param_type": "整数",
        },
        {
            "key": "事件_参数",
            "param_type": "整数",
        },
        {
            "key": "事件_时间戳",
            "param_type": "整数",
        },
    ],
}


