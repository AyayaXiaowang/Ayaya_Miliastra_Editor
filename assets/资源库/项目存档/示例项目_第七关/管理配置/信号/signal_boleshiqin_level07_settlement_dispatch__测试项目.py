from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_settlement_dispatch__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_结算派发",
    "parameters": [
        {"name": "允许票", "parameter_type": "整数"},
        {"name": "拒绝票", "parameter_type": "整数"},
    ],
    "description": "第七关公共结算派发：玩家侧（UI第七关_游戏中_交互逻辑）写入关卡实体结算触发数据后广播；关卡实体挂载图（第七关_投票结算）监听后执行本回合结算与揭晓展示。",
}

