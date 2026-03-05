from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_level07_start_game"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_开始游戏",
    "parameters": [],
    "description": "第七关开局信号（回归夹具）：零参信号，用于校验发送信号时禁止携带额外参数。",
}

