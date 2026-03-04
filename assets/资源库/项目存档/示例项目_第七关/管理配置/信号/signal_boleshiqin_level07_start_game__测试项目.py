from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_start_game__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_开始游戏",
    "parameters": [],
    "description": "第七关开局信号：当新手教学倒计时结束，或在场玩家全部完成新手教学后，由场地控制器广播，玩家侧收到后执行传送与进入正式流程。",
}

