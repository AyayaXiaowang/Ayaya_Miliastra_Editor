from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_start_game"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "开始游戏",
    "parameters": [
        {
            "name": "关卡序号",
            "parameter_type": "整数",
            "description": "要开始的关卡序号（1~10）。",
        },
    ],
    "description": "关卡选择界面：玩家点击“开始挑战”后发送，用于触发进入关卡/开始流程。",
}

