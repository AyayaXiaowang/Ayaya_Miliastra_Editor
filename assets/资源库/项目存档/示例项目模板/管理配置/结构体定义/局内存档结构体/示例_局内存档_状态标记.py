from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "1516981257"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_状态标记",
    "value": [
        {
            "key": "状态_是否完成新手引导",
            "param_type": "布尔值",
        },
        {
            "key": "状态_当前阶段编号",
            "param_type": "整数",
        },
        {
            "key": "状态_开关位掩码",
            "param_type": "整数",
        },
    ],
}


