from __future__ import annotations

from typing import Any, Dict

SIGNAL_ID = "signal_boleshiqin_level07_round_advance_dispatch__测试项目"

SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "第七关_回合推进派发",
    "parameters": [
        {"name": "是否最后回合", "parameter_type": "整数"},
    ],
    "description": "第七关公共回合推进派发：玩家侧（UI第七关_游戏中_交互逻辑）写入关卡实体回合推进触发数据后广播；关卡实体挂载图（第七关_回合推进执行）监听后执行结算后推进（关门/清理遮罩与回合选择/写入待办）。",
}

