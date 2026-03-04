from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_example_pedal_switch_state"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "通用踏板开关_状态变化",
    "parameters": [
        {
            "name": "是否激活",
            "parameter_type": "布尔值",
            "description": "踏板当前是否处于按下（激活）状态。",
        },
    ],
    "description": "用于演示如何通过信号广播踏板开关是否处于激活状态，而不是逐个修改目标实体的自定义变量；接收端可通过监听事件自带的“信号来源实体”识别发送方并完成过滤/聚合。",
}



