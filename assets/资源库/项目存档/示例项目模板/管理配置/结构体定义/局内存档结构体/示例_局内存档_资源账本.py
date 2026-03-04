from __future__ import annotations

from typing import Any, Dict


STRUCT_ID = "1713004341"
STRUCT_TYPE = "ingame_save"


STRUCT_PAYLOAD: Dict[str, Any] = {
    "type": "结构体",
    "struct_ype": "ingame_save",
    "struct_name": "示例_局内存档_资源账本",
    "value": [
        {
            "key": "货币_数量A",
            "param_type": "整数",
        },
        {
            "key": "货币_数量B",
            "param_type": "整数",
        },
        # 示例：并行列表（固定长度，用于演示 lenth 的含义）
        {
            "key": "资源_类型ID列表",
            "param_type": "整数列表",
            "lenth": 3,
        },
        {
            "key": "资源_数量列表",
            "param_type": "整数列表",
            "lenth": 3,
        },
    ],
}


