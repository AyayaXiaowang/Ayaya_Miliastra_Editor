from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_switch_level"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "切换关卡",
    "parameters": [
        {
            "name": "关卡序号",
            "parameter_type": "整数",
            "description": "目标关卡序号（1~10）。",
        },
    ],
    "description": "关卡选择界面：当玩家选择关卡（数字键/列表按钮）或通过左右切换时发送，用于驱动预览/关卡状态同步。",
}

