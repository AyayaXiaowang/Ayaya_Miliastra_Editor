from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_all_supported_types_example"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "测试信号_全部参数类型",
    "parameters": [
        {
            "name": "整数参数",
            "parameter_type": "整数",
            "description": "用于测试整数类型参数。",
        },
        {
            "name": "浮点数参数",
            "parameter_type": "浮点数",
            "description": "用于测试浮点数类型参数。",
        },
        {
            "name": "字符串参数",
            "parameter_type": "字符串",
            "description": "用于测试字符串类型参数。",
        },
        {
            "name": "三维向量参数",
            "parameter_type": "三维向量",
            "description": "用于测试三维向量类型参数。",
        },
        {
            "name": "布尔值参数",
            "parameter_type": "布尔值",
            "description": "用于测试布尔值类型参数。",
        },
        {
            "name": "GUID参数",
            "parameter_type": "GUID",
            "description": "用于测试 GUID 类型参数。",
        },
        {
            "name": "实体参数",
            "parameter_type": "实体",
            "description": "用于测试实体类型参数。",
        },
        {
            "name": "配置ID参数",
            "parameter_type": "配置ID",
            "description": "用于测试配置ID 类型参数。",
        },
        {
            "name": "元件ID参数",
            "parameter_type": "元件ID",
            "description": "用于测试元件ID 类型参数。",
        },
        {
            "name": "整数列表参数",
            "parameter_type": "整数列表",
            "description": "用于测试整数列表类型参数。",
        },
    ],
    "description": "用于覆盖当前信号系统支持的全部基础类型及其列表形式的测试信号。",
}


