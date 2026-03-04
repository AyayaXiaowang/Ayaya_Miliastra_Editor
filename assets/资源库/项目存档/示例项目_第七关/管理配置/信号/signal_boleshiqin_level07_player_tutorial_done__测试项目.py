from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_player_tutorial_done__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_新手教学_玩家完成",
    "parameters": [
        {
            "name": "玩家实体",
            "parameter_type": "实体",
            "description": "完成新手教学的玩家实体。",
        },
        {
            "name": "玩家GUID",
            "parameter_type": "GUID",
            "description": "完成新手教学的玩家 GUID。",
        },
    ],
    "description": "第七关新手教学：玩家完成全部教学步骤后上报给场地控制器，用于统计完成度并在全部完成时提前开局。",
}

