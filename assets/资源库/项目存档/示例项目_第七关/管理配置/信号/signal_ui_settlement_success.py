from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_test_project_ui_settlement_success"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "关卡大厅_结算成功",
    "parameters": [],
    "description": "用于在 UI 中点击“进行结算”且满足门槛后广播；接收端收到后应将所有玩家结算状态设为“胜利”并触发关卡结算流程。",
}

