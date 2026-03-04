from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_door_action__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_门_动作",
    "parameters": [
        {
            "name": "目标状态",
            "parameter_type": "字符串",
            "description": "门目标状态：\"打开\" / \"关闭\"。",
        },
    ],
    "description": "第七关门控制：请求门执行一次动作（打开/关闭）。门的运动器、音效与“关门完成”判定由门控制图自行处理。",
}

