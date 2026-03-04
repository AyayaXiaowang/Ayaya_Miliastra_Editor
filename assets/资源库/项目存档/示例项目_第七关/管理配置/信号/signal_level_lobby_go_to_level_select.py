from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_test_project_level_lobby_go_to_level_select"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "关卡大厅_前往选关",
    "parameters": [],
    "description": (
        "用于“关卡大厅 → 选关面板”的统一导航/重置入口："
        "当任意玩家点击『关卡选择』时广播；接收端收到后应将玩家传送到选关预设点，"
        "暂停玩家背景音乐、切换职业到自带选关面板的职业，并隐藏玩家模型。"
        "触发后约 0.5 秒再读取关卡通关记录并同步选关 UI 控件的展示/隐藏。"
    ),
}

