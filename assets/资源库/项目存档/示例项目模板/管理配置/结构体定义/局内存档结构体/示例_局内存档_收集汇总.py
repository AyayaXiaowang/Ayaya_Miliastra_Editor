from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "3314321429"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_收集汇总",
    "value": [
        {
            "key": "收集_已解锁ID列表",
            "param_type": "整数列表",
            "lenth": 5,
        },
        {
            "key": "收集_计数列表",
            "param_type": "整数列表",
            "lenth": 5,
        },
    ],
}


