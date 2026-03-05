from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_level_lobby_start_level"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "关卡大厅_开始关卡",
    "parameters": [
        {
            "name": "第X关",
            "parameter_type": "整数",
            "description": "确认开始的关卡号（1~N）。接收端通过该值判断是否执行对应关卡逻辑。",
        },
    ],
    "description": "关卡大厅在确认关卡后广播的“开始关卡”信号。用于让玩家/关卡控制器按第X关路由到对应关卡逻辑。",
}

