from __future__ import annotations

from typing import Any, Dict


SIGNAL_ID = "signal_test_project_ui_level_select_level7_refresh_preview"


SIGNAL_PAYLOAD: Dict[str, Any] = {
    "signal_id": SIGNAL_ID,
    "signal_name": "UI选关页_第七关_刷新预览",
    "parameters": [
        {
            "name": "目标玩家",
            "parameter_type": "实体",
            "description": "需要刷新预览展示的目标玩家实体。",
        },
        {
            "name": "目标关卡",
            "parameter_type": "整数",
            "description": "目标关卡号（0 表示仅清理预览，不创建）。",
        },
    ],
    "description": "第七关选关页：刷新单人关卡预览（清理旧预览并按目标关卡创建新预览）。",
}

