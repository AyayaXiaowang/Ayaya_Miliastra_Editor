from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_door_close_done__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_门_关闭完成",
    "parameters": [],
    "description": "第七关门控制：关门动作完成（基础运动器停止时触发）。用于驱动“关门后生成亲戚/进入结算”等后续流程。",
}

