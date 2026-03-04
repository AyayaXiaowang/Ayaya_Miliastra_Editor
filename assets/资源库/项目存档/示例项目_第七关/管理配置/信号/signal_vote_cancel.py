from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_test_project_vote_cancel"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "关卡大厅_投票取消",
    "parameters": [],
    "description": "任意玩家触发“我拒绝/取消所有投票”时广播；接收端收到后应将自身玩家的投票状态清空，并将投票按钮恢复为可用态（本信号不携带参数）。",
}

