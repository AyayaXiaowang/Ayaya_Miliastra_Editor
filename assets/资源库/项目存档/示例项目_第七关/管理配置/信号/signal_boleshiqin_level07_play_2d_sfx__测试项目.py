from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_play_2d_sfx__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_播放2D音效",
    "parameters": [
        {
            "name": "音效资产索引",
            "parameter_type": "整数",
            "description": "需要播放的 2D 音效资产索引。",
        },
    ],
    "description": "第七关音效广播：关卡/门/流程图广播该信号；玩家实体挂载图监听后对本玩家播放对应索引的 2D 音效。",
}

