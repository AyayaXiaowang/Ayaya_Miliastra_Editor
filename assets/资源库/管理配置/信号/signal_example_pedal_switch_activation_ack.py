from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_example_pedal_switch_activation_ack"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "通用踏板开关_激活确认",
    "parameters": [
        {
            "name": "开关GUID",
            "parameter_type": "GUID",
            "description": "需要被确认（回执）的踏板开关实体 GUID。",
        },
        {
            "name": "是否允许锁定",
            "parameter_type": "布尔值",
            "description": "接收端确认“已完成联动目标”（如开门）后回发；踏板若配置为一次性且该值为 True，将锁定按下状态并禁用触发器，不再回弹。",
        },
    ],
    "description": "用于演示“接收端完成联动后回发确认信号”：踏板收到后可按自身配置（如一次性）决定是否锁定按下并禁用碰撞触发器。",
}


