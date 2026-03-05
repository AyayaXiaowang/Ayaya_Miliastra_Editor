from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_test_project_enter_level_select"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "关卡大厅_进入选关",
    "parameters": [],
    "description": "用于在切换到“关卡选择(ceshi_rect)”页面时广播；接收端收到后应做一次首帧 UI 同步（根据 ui_sel_level / ui_vote_level 切按钮状态、刷新高亮与标题、清理遮罩/提示）。",
}

